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

import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

EM_CURSO = "em curso"
CONCLUIDO = "concluido"
FALHOU = "falhou"

# Quantas linhas do relato ficam guardadas por trabalho. O relato do download
# de processo grande passa de mil linhas, e guardar tudo encheria a memoria do
# servidor sem ajudar ninguem: o que importa e o comeco, que diz o que foi
# pedido, e o fim, que diz como terminou.
TETO_DE_LINHAS = 400

# Quantos trabalhos ficam na memoria. Os mais antigos ja terminados saem.
TETO_DE_TRABALHOS = 20


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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

    def anotar(self, linha: str) -> None:
        if len(self.relato) >= TETO_DE_LINHAS:
            # Descarta do MEIO, nao do comeco: a primeira linha diz o que foi
            # pedido e a ultima diz como terminou. Perder qualquer uma das duas
            # seria perder justamente a resposta.
            del self.relato[TETO_DE_LINHAS // 2]
            self.cortadas += 1
        self.relato.append(linha.rstrip())

    def resumo(self, ultimas: int = 12) -> dict:
        return {
            "trabalho": self.identificador,
            "acao": self.acao,
            "processo": self.numero,
            "estado": self.estado,
            "comecou_em": self.comecou_em,
            "terminou_em": self.terminou_em,
            "codigo_de_saida": self.codigo,
            "linhas_do_relato": len(self.relato) + self.cortadas,
            "ultimas_linhas": self.relato[-ultimas:],
        }


class Mural:
    """Os trabalhos em curso e os que ja terminaram, nesta execucao."""

    def __init__(self, teto: int = TETO_DE_TRABALHOS) -> None:
        self._trabalhos: dict = {}
        self._ordem: list = []
        self._trava = threading.Lock()
        self._teto = teto

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
        self._guardar(trabalho)
        abrir = _abrir or _abrir_processo
        linha = threading.Thread(
            target=self._correr, args=(trabalho, argumentos, abrir),
            name=f"trabalho-{trabalho.identificador}", daemon=True)
        linha.start()
        return trabalho

    def _correr(self, trabalho: Trabalho, argumentos: list, abrir) -> None:
        try:
            processo = abrir(argumentos)
        except Exception as erro:
            trabalho.anotar(f"O comando nao pode ser iniciado: {type(erro).__name__}.")
            trabalho.estado = FALHOU
            trabalho.terminou_em = _agora()
            return
        try:
            if processo.stdout is not None:
                for linha in processo.stdout:
                    trabalho.anotar(linha)
            codigo = processo.wait()
        except Exception as erro:
            trabalho.anotar(f"A leitura do relato falhou: {type(erro).__name__}.")
            codigo = -1
        trabalho.codigo = codigo
        trabalho.estado = CONCLUIDO if codigo == 0 else FALHOU
        trabalho.terminou_em = _agora()


def _abrir_processo(argumentos: list):
    """Abre o comando com o MESMO Python que roda o servidor.

    `sys.executable` e o do ambiente virtual do projeto. Chamar `python` solto
    pegaria o do sistema, que nao tem as dependencias e falharia com uma
    mensagem que nao explica nada.
    """
    return subprocess.Popen(
        [sys.executable, "-m", "justica_mcp.portal"] + list(argumentos),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
    )


MURAL = Mural()
