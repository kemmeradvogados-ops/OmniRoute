"""Trabalhos demorados, corridos FORA da chamada que os pediu.

Por que isto existe. O download dos autos leva de minutos a horas: o portal
gera o arquivo quando se pede, o eproc avisa por e-mail e pode demorar, e o
Portal de Servicos baixa documento por documento. Uma ferramenta do servidor
que ficasse esperando tudo isso dentro da propria chamada seria uma chamada
que nao responde, e o cliente a encerraria antes do fim achando que travou.

Entao a ferramenta PEDE e volta na hora. Quem faz o trabalho e um processo
separado, e ha uma segunda ferramenta para perguntar como ele vai.

Por que PROCESSO separado, e nao linha de execucao dentro do servidor. Tres
razoes, e a primeira sozinha decidiria:

  1. o servidor conversa pela SAIDA PADRAO, e a corrida do download imprime
     relato nela o tempo todo. Dividir a mesma saida entre os dois corromperia
     o protocolo, e capturar a saida inteira do processo por quinze minutos
     calaria tambem as respostas do servidor, porque `redirect_stdout` troca a
     saida do programa INTEIRO, e nao a da linha de execucao que a chamou;
  2. o download abre um navegador de verdade. Navegador que morre leva junto o
     processo que o abriu, e nao o servidor;
  3. o relato do processo separado chega linha a linha, que e o que permite
     dizer em que pe esta sem inventar progresso.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .core.estado import diretorio_estado

EM_CURSO = "em curso"
CONCLUIDO = "concluido"
FALHOU = "falhou"
# Estado que so existe porque o servidor pode cair no meio. Diferente de
# FALHOU: falhar e o comando terminar mal, e interromper e nem chegar a
# terminar. Quem le precisa distinguir, porque a providencia e outra: um
# download interrompido se RETOMA, e a retomada pula o que ja esta em disco.
INTERROMPIDO = "interrompido"

# Quantas linhas do relato ficam guardadas por trabalho. O relato do download
# de processo grande passa de mil linhas, e guardar tudo encheria a memoria do
# servidor sem ajudar ninguem: o que importa e o comeco, que diz o que foi
# pedido, e o fim, que diz como terminou.
TETO_DE_LINHAS = 400

# Quantos trabalhos ficam na memoria. Os mais antigos ja terminados saem.
TETO_DE_TRABALHOS = 20


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def diretorio_dos_trabalhos() -> Path:
    """Onde os trabalhos ficam anotados, para sobreviverem ao servidor.

    Dentro do diretorio de estado, que ja e por maquina e por usuario, do
    mesmo jeito que a auditoria e o contador de tentativas.
    """
    pasta = diretorio_estado() / "trabalhos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def processo_vivo(pid: Optional[int], desde: Optional[str]) -> bool:
    """O processo daquele trabalho ainda esta de pe?

    O NUMERO SOZINHO NAO BASTA. O sistema operacional reaproveita
    identificadores, entao um numero que responde pode ser de outro programa
    que nasceu depois. Por isso o instante de inicio entra na conta: um
    processo mais novo que a anotacao nao e o nosso.

    Sem psutil nao da para ler o inicio de um processo alheio de forma
    portavel, entao a conferencia fica no que se pode afirmar: numero que nao
    responde e morte certa, e isso ja basta para nao mentir dizendo "em
    curso". Numero que responde continua sendo tratado como vivo, com a
    ressalva registrada aqui.
    """
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            SYNCHRONIZE = 0x00100000
            mao = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
            if not mao:
                return False
            ctypes.windll.kernel32.CloseHandle(mao)
            return True
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, AttributeError):
        return False


def trabalhos_gravados(pasta: Optional[Path] = None) -> list[dict]:
    """O que esta anotado em disco, do mais recente para o mais antigo.

    Linha corrompida e PULADA em silencio, de proposito: um arquivo pela
    metade, escrito quando o servidor morreu no meio da gravacao, nao pode
    derrubar a listagem inteira.
    """
    pasta = pasta or diretorio_dos_trabalhos()
    achados = []
    for arquivo in pasta.glob("*.json"):
        try:
            achados.append(json.loads(arquivo.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    achados.sort(key=lambda t: t.get("comecou_em") or "", reverse=True)
    return achados


@dataclass
class Trabalho:
    identificador: str
    acao: str
    numero: str
    estado: str = EM_CURSO
    comecou_em: str = field(default_factory=_agora)
    terminou_em: Optional[str] = None
    codigo: Optional[int] = None
    relato: list = field(default_factory=list)
    cortadas: int = 0
    # Os dois campos que permitem reconhecer o trabalho depois de o servidor
    # reiniciar: onde ele escreve e qual processo o faz.
    arquivo_de_relato: Optional[str] = None
    pid: Optional[int] = None
    observacao: Optional[str] = None

    def anotar(self, linha: str) -> None:
        if len(self.relato) >= TETO_DE_LINHAS:
            # Descarta do MEIO, nao do comeco: a primeira linha diz o que foi
            # pedido e a ultima diz como terminou. Perder qualquer uma das duas
            # seria perder justamente a resposta.
            del self.relato[TETO_DE_LINHAS // 2]
            self.cortadas += 1
        self.relato.append(linha.rstrip())

    def resumo(self, ultimas: int = 12) -> dict:
        corpo = {
            "trabalho": self.identificador,
            "acao": self.acao,
            "processo": self.numero,
            "estado": self.estado,
            "comecou_em": self.comecou_em,
            "terminou_em": self.terminou_em,
            "codigo_de_saida": self.codigo,
            "linhas_do_relato": len(self.relato) + self.cortadas,
            "ultimas_linhas": self.relato[-ultimas:] or self._ultimas_do_arquivo(ultimas),
        }
        if self.observacao:
            corpo["observacao"] = self.observacao
        return corpo

    def _ultimas_do_arquivo(self, quantas: int) -> list:
        """O relato do filho mora em arquivo, e so ele o escreve.

        Por isso o resumo le dali quando nao ha nada em memoria, que e o caso
        de todo trabalho herdado de um servidor anterior.
        """
        if not self.arquivo_de_relato:
            return []
        try:
            linhas = Path(self.arquivo_de_relato).read_text(
                encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return [linha.rstrip() for linha in linhas[-quantas:]]

    def anotacao(self) -> dict:
        """O que vai para o disco. Sem o relato: ele ja esta no arquivo."""
        return {
            "trabalho": self.identificador,
            "acao": self.acao,
            "processo": self.numero,
            "estado": self.estado,
            "comecou_em": self.comecou_em,
            "terminou_em": self.terminou_em,
            "codigo_de_saida": self.codigo,
            "arquivo_de_relato": self.arquivo_de_relato,
            "pid": self.pid,
            "observacao": self.observacao,
        }

    @classmethod
    def da_anotacao(cls, dados: dict) -> "Trabalho":
        t = cls(identificador=dados.get("trabalho") or "",
                acao=dados.get("acao") or "",
                numero=dados.get("processo") or "")
        t.estado = dados.get("estado") or EM_CURSO
        t.comecou_em = dados.get("comecou_em") or _agora()
        t.terminou_em = dados.get("terminou_em")
        t.codigo = dados.get("codigo_de_saida")
        t.arquivo_de_relato = dados.get("arquivo_de_relato")
        t.pid = dados.get("pid")
        t.observacao = dados.get("observacao")
        return t


class Mural:
    """Os trabalhos em curso e os que ja terminaram, nesta execucao."""

    def __init__(self, teto: int = TETO_DE_TRABALHOS) -> None:
        self._trabalhos: dict = {}
        self._ordem: list = []
        self._trava = threading.Lock()
        self._teto = teto
        self._reconhecer_o_que_ficou()

    def _reconhecer_o_que_ficou(self) -> None:
        """Le o que ficou anotado por um servidor anterior.

        Ate 29/10/2026 o mural nascia vazio, e a lista voltava vazia depois de
        um reinicio. Isso e pior que voltar dizendo "interrompido": lista
        vazia se le como "nao havia nada", e foi assim que um download morto
        passou por nao ter existido.

        Trabalho que diz EM_CURSO e cujo processo nao responde mais nao esta
        em curso: esta interrompido, e o resumo diz por que.
        """
        for dados in reversed(trabalhos_gravados()):
            trabalho = Trabalho.da_anotacao(dados)
            if not trabalho.identificador:
                continue
            if trabalho.estado == EM_CURSO and not processo_vivo(
                    trabalho.pid, trabalho.comecou_em):
                trabalho.estado = INTERROMPIDO
                trabalho.terminou_em = trabalho.terminou_em or _agora()
                trabalho.observacao = (
                    "O servidor da extensao reiniciou antes de este trabalho "
                    "terminar, e o processo que o executava nao responde "
                    "mais. Nada do que ja foi gravado em disco se perdeu: o "
                    "download documento a documento pula o que ja esta la, "
                    "entao retomar custa uma autenticacao, e nao a corrida "
                    "inteira.")
            self._trabalhos[trabalho.identificador] = trabalho
            self._ordem.append(trabalho.identificador)

    # ---- consulta ----------------------------------------------------

    def ver(self, identificador: str) -> Optional[Trabalho]:
        with self._trava:
            return self._trabalhos.get(identificador)

    def em_curso_para(self, numero: str) -> Optional[Trabalho]:
        """O trabalho vivo deste processo, se houver.

        Serve para RECUSAR um segundo pedido igual. Dois downloads do mesmo
        processo ao mesmo tempo gastam duas tentativas de autenticacao, abrem
        dois navegadores e escrevem na mesma pasta.
        """
        with self._trava:
            for identificador in reversed(self._ordem):
                trabalho = self._trabalhos[identificador]
                if trabalho.numero == numero and trabalho.estado == EM_CURSO:
                    return trabalho
        return None

    def listar(self, limite: int = 10) -> list:
        with self._trava:
            vivos = list(reversed(self._ordem))[:limite]
            return [self._trabalhos[i].resumo(ultimas=3) for i in vivos]

    # ---- inicio ------------------------------------------------------

    def _guardar(self, trabalho: Trabalho) -> None:
        with self._trava:
            self._trabalhos[trabalho.identificador] = trabalho
            self._ordem.append(trabalho.identificador)
            while len(self._ordem) > self._teto:
                antigo = None
                for i, identificador in enumerate(self._ordem):
                    if self._trabalhos[identificador].estado != EM_CURSO:
                        antigo = i
                        break
                if antigo is None:
                    break
                saiu = self._ordem.pop(antigo)
                self._trabalhos.pop(saiu, None)

    def comecar(self, acao: str, numero: str, argumentos: list,
                _abrir=None) -> Trabalho:
        """Dispara o comando e volta na hora, com o trabalho ja anotado."""
        trabalho = Trabalho(identificador=uuid.uuid4().hex[:12], acao=acao,
                            numero=numero)
        trabalho.arquivo_de_relato = str(
            diretorio_dos_trabalhos() / f"{trabalho.identificador}.log")
        self._guardar(trabalho)
        abrir = _abrir or _abrir_processo

        try:
            # A segunda chamada fica DENTRO da protecao de baixo. Deixa-la
            # fora, como estava, fazia um erro real do comando escapar do
            # `except Exception` e subir ate quem pediu o download.
            try:
                processo = abrir(argumentos,
                                 arquivo_de_relato=trabalho.arquivo_de_relato)
            except TypeError:
                # Quem substitui `_abrir` nos testes nem sempre aceita o
                # segundo parametro. O caminho de producao aceita.
                processo = abrir(argumentos)
        except Exception as erro:
            trabalho.anotar(f"O comando nao pode ser iniciado: {type(erro).__name__}.")
            trabalho.estado = FALHOU
            trabalho.terminou_em = _agora()
            self._gravar(trabalho)
            return trabalho

        trabalho.pid = getattr(processo, "pid", None)
        # GRAVADO AGORA, e nao ao terminar. O reinicio do servidor pode chegar
        # antes do fim, e foi exatamente o que aconteceu em 29/10/2026:
        # anotar so no fim e nao anotar nada quando mais importa.
        self._gravar(trabalho)

        linha = threading.Thread(
            target=self._acompanhar, args=(trabalho, processo),
            name=f"trabalho-{trabalho.identificador}", daemon=True)
        linha.start()
        return trabalho

    def _acompanhar(self, trabalho: Trabalho, processo) -> None:
        """Espera o filho e anota o desfecho.

        Nao le mais o cano: o relato do filho vai direto para o arquivo dele.
        Esta linha de execucao so aguarda o fim, e se o servidor morrer antes
        disso o filho segue vivo, escrevendo no mesmo arquivo.
        """
        try:
            if processo.stdout is not None:
                # Caminho dos testes, que ainda entregam um cano fingido.
                for linha in processo.stdout:
                    trabalho.anotar(linha)
            codigo = processo.wait()
        except Exception as erro:
            trabalho.anotar(f"A espera do comando falhou: {type(erro).__name__}.")
            codigo = -1
        trabalho.codigo = codigo
        trabalho.estado = CONCLUIDO if codigo == 0 else FALHOU
        trabalho.terminou_em = _agora()
        self._gravar(trabalho)

    # ---- disco -------------------------------------------------------

    def _gravar(self, trabalho: Trabalho) -> None:
        """Anota o trabalho em disco. Falha de escrita NAO derruba o trabalho.

        Perder a anotacao e ruim; parar o download por causa dela seria pior,
        e o download e o que o advogado pediu.
        """
        try:
            pasta = diretorio_dos_trabalhos()
            alvo = pasta / f"{trabalho.identificador}.json"
            # ESCRITA ATOMICA: arquivo temporario e depois troca de nome.
            #
            # Escrever direto no alvo deixa uma janela em que ele existe pela
            # METADE, e `trabalhos_gravados` pula JSON invalido em silencio.
            # O leitor que chegasse nessa janela nao via o trabalho, e a lista
            # voltava sem ele: o mesmo sintoma que este modulo esta corrigindo,
            # por outra causa. Encontrado em 29/10/2026 por um teste que
            # falhava de forma intermitente.
            #
            # `os.replace` e atomico no Windows e nos demais, e sobrescreve.
            provisorio = pasta / f"{trabalho.identificador}.json.parcial"
            provisorio.write_text(
                json.dumps(trabalho.anotacao(), ensure_ascii=False),
                encoding="utf-8")
            os.replace(provisorio, alvo)
        except OSError:
            pass
        self._limpar_o_disco()

    def _limpar_o_disco(self) -> None:
        """O teto do mural valia so para a memoria. Em disco, sem limpeza,
        trocariamos um defeito por outro."""
        try:
            pasta = diretorio_dos_trabalhos()
            anotados = sorted(pasta.glob("*.json"),
                              key=lambda a: a.stat().st_mtime, reverse=True)
            for velho in anotados[self._teto:]:
                relato = velho.with_suffix(".log")
                velho.unlink(missing_ok=True)
                relato.unlink(missing_ok=True)
        except OSError:
            pass


def _abrir_processo(argumentos: list, arquivo_de_relato=None):
    """Abre o comando com o MESMO Python que roda o servidor.

    `sys.executable` e o do ambiente virtual do projeto. Chamar `python` solto
    pegaria o do sistema, que nao tem as dependencias e falharia com uma
    mensagem que nao explica nada.

    O RELATO VAI PARA ARQUIVO, E NAO PARA CANO. Ate 29/10/2026 era
    `stdout=subprocess.PIPE`, e a ponta de leitura desse cano pertencia ao
    servidor. Servidor morto, ponta fechada, e a proxima linha de progresso
    que o filho escrevesse receberia cano quebrado: o download parava de
    verdade, e nao so sumia da lista. Em arquivo, o filho nao depende de
    ninguem estar lendo.

    E ele nasce SOLTO do grupo do servidor, para que um sinal dirigido ao
    servidor nao o leve junto. No Windows isso e `DETACHED_PROCESS`; nos
    demais, uma sessao nova.
    """
    solta: dict = {}
    if sys.platform == "win32":
        # 0x00000008 e DETACHED_PROCESS; 0x00000200 e CREATE_NEW_PROCESS_GROUP.
        solta["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                                  | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP",
                                            0x00000200))
    else:
        solta["start_new_session"] = True

    destino = (open(arquivo_de_relato, "w", encoding="utf-8", errors="replace")
               if arquivo_de_relato is not None else subprocess.DEVNULL)
    return subprocess.Popen(
        [sys.executable, "-m", "justica_mcp.portal"] + list(argumentos),
        stdout=destino, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
        **solta,
    )


MURAL = Mural()
