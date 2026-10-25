"""Acervo de copias: pasta por processo, com indice de folhas.

Regra de negocio definida pelo operador em 21 de setembro de 2026:

    Sem copia na pasta  -> baixa a INTEGRA.
    Com copia na pasta  -> baixa so o que falta, COMPLEMENTANDO, e informa
                           quais folhas o complemento cobre.

A numeracao de folhas e a da COPIA DA BANCA, continua e crescente: a integra
ocupa de 1 ate N, e cada complemento segue de N+1 em diante. Nao e a numeracao
do tribunal, que o eproc nem usa (la sao eventos). Serve para o advogado citar
"fls. 245/250 da copia" e achar o documento.

O indice fica na propria pasta do processo, em `indice.json`. Ele e a memoria
do que ja foi copiado: sem ele, todo complemento viraria copia repetida.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

NOME_INDICE = "indice.json"
VARIAVEL_PASTA = "JUSTICA_PASTA_COPIAS"


def pasta_de_copias() -> Path:
    """Raiz das copias. Padrao no diretorio de estado; o operador aponta para
    a pasta do escritorio, tipicamente dentro do Google Drive sincronizado."""
    from .estado import diretorio_estado

    bruto = os.environ.get(VARIAVEL_PASTA, "").strip()
    return Path(bruto).expanduser() if bruto else diretorio_estado() / "processos"


# A pasta das LEITURAS, que nao e o acervo. Ela guarda os autos que o advogado
# pediu para ler sem guardar: ficam na maquina, fora do Google Drive, nao sao
# indexados e podem ser apagados a qualquer momento sem perder nada.
#
# Por que existe. Baixar e guardar e o certo para processo que o escritorio vai
# trabalhar: uma autenticacao e a equipe inteira le de graca, para sempre. Mas
# para processo que se consulta uma vez, encher o acervo de PDF de sessenta
# megabytes e peso sem proveito. Entao ha as duas formas, e quem escolhe e o
# advogado.
#
# O mecanismo e o mesmo do acervo, e de proposito: muda so a raiz. Como
# `pasta_de_copias` le a variavel de ambiente a cada chamada, apontar a
# variavel para ca durante uma corrida redireciona TUDO, em qualquer portal,
# sem uma linha de codigo por portal.
NOME_DA_PASTA_DE_LEITURAS = "leituras"


def pasta_de_leituras() -> Path:
    """Raiz das leituras que nao vao para o acervo. Sempre local."""
    from .estado import diretorio_estado

    return diretorio_estado() / NOME_DA_PASTA_DE_LEITURAS


class AcervoIndisponivel(RuntimeError):
    """A pasta de copias nao pode ser lida ou escrita agora."""


# A pasta de copias mora no Google Drive montado como unidade (G:\Meu Drive).
# Isso nao e um disco comum: e um sistema de arquivos virtual que fala com a
# rede, e ele falha de formas que disco local nao falha. Visto em campo em
# 05/10/2026, ao ler o indice de um processo:
#
#     OSError: [WinError 1450] Nao existem recursos de sistema suficientes
#     para concluir o servico solicitado
#
# Esse erro e tipicamente passageiro. Tentar de novo depois de um instante
# costuma bastar, e e muito melhor que derrubar uma consulta que ja terminou.
TENTATIVAS_NO_ACERVO = 4
ESPERA_ENTRE_TENTATIVAS = 0.4


def _insistir(descricao: str, operacao):
    """Executa a operacao, repetindo enquanto o sistema de arquivos recusar.

    Esgotadas as tentativas, levanta `AcervoIndisponivel` com o motivo real.
    NUNCA devolve um valor de consolo: quem chama precisa saber a diferenca
    entre "nao existe" e "nao consegui olhar", e essa diferenca vale folha de
    processo.
    """
    import time

    ultimo = None
    for tentativa in range(TENTATIVAS_NO_ACERVO):
        try:
            return operacao()
        except OSError as exc:
            ultimo = exc
            if tentativa + 1 < TENTATIVAS_NO_ACERVO:
                time.sleep(ESPERA_ENTRE_TENTATIVAS * (tentativa + 1))
    raise AcervoIndisponivel(
        f"Nao consegui {descricao} na pasta de copias apos "
        f"{TENTATIVAS_NO_ACERVO} tentativas: {ultimo}. A pasta fica no Google "
        "Drive, que responde pela rede e as vezes recusa por instantes. A "
        "consulta em si nao foi perdida; so a parte de copia nao rodou."
    ) from None


def pasta_do_processo(numero_digitos: str) -> Path:
    return pasta_de_copias() / numero_digitos


def garantir_pasta(numero_digitos: str) -> Path:
    """Cria a pasta do processo quando ainda nao existe, e a devolve.

    Antes a pasta so nascia no instante de gravar o primeiro arquivo. Uma
    consulta que nao copiasse nada nao deixava pasta nenhuma, e o advogado ia
    procurar no Drive um lugar que nunca foi criado. A pasta passa a existir
    desde a consulta, mesmo vazia: ela e o endereco do processo no acervo, nao
    um efeito colateral do download.
    """
    pasta = pasta_do_processo(numero_digitos)
    _insistir("criar a pasta do processo", lambda: pasta.mkdir(parents=True, exist_ok=True))
    return pasta


def pdfs_fora_do_indice(indice: "Indice") -> list[str]:
    """Arquivos PDF na pasta que o indice nao conhece.

    A pasta de copias e do escritorio, compartilhada, e pode ja conter copias
    que alguem baixou a mao. Sem o indice nao ha como saber o que elas cobrem,
    e tratar a pasta como vazia por causa disso seria concluir demais a partir
    da ausencia de um arquivo de controle.
    """
    if not indice.pasta.is_dir():
        return []
    conhecidos = {Path(i.arquivo).name for i in indice.itens}
    return sorted(
        a.name for a in indice.pasta.iterdir()
        if a.is_file() and a.suffix.lower() == ".pdf" and a.name not in conhecidos
    )


# Quantos bytes do FIM se olha atras da marca de encerramento. A norma do PDF
# admite lixo depois dela, e leitor nenhum reclama enquanto ela aparecer perto
# do fim. Dois kilobytes cobrem com folga o que os geradores de verdade poem
# ali.
FOLGA_DA_MARCA_DE_FIM = 2048

MARCA_DE_FIM_DO_PDF = b"%%EOF"


def parece_truncado(arquivo: Path) -> Optional[bool]:
    """O arquivo parece ter sido cortado no meio do download?

    Conferir so o COMECO nao basta, e isto custou um achado em 25/10/2026: a
    guarda que impedia pagina de erro de entrar no acervo olhava a marca
    `%PDF-` nas primeiras linhas, e download interrompido tem essa marca
    tambem. O que ele nao tem e a marca de encerramento no fim.

    O sinal que levantou a suspeita foi o tamanho: 5.242.880 bytes, cinco
    mebibytes exatos. Tamanho redondo assim e assinatura de transferencia
    cortada em limite de bloco, nao de documento.

    Devolve `None` quando nao da para saber, e nao `False`: dizer que esta
    inteiro sem ter conferido seria pior que admitir a duvida.
    """
    try:
        if not arquivo.is_file():
            return None
        tamanho = arquivo.stat().st_size
        if tamanho <= 0:
            return True
        with open(arquivo, "rb") as leitura:
            leitura.seek(max(0, tamanho - FOLGA_DA_MARCA_DE_FIM))
            fim = leitura.read()
    except OSError:
        return None
    return MARCA_DE_FIM_DO_PDF not in fim


def contar_paginas(arquivo: Path) -> Optional[int]:
    """Paginas de um PDF. Devolve None quando nao da para saber.

    Nao inventa numero: sem contagem confiavel, o indice registra a ausencia em
    vez de chutar, porque folha errada em citacao e pior que folha ausente.
    """
    if arquivo.suffix.lower() != ".pdf":
        return None
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(arquivo)).pages)
    except Exception:
        return None


def impressao_do_arquivo(arquivo: Path) -> Optional[str]:
    """Impressao digital do conteudo, para reconhecer copia repetida.

    Lida em pedacos: a integra de um processo grande nao cabe confortavelmente
    na memoria, e ler tudo de uma vez para calcular um resumo seria desperdicio
    em cima de arquivo que ja esta no disco.
    """
    import hashlib

    try:
        digestor = hashlib.sha256()
        with open(arquivo, "rb") as fonte:
            for pedaco in iter(lambda: fonte.read(1024 * 1024), b""):
                digestor.update(pedaco)
        return digestor.hexdigest()
    except OSError:
        return None


REPETIDA_IGUAL = "igual"
REPETIDA_NO_TEXTO = "igual-no-texto"
REPETIDA_SUSPEITA = "suspeita"
NOVA = "nova"


def mesmo_texto(primeiro: Path, segundo: Path) -> Optional[bool]:
    """Diz se dois PDFs tem o MESMO TEXTO, folha a folha. `None` se nao deu.

    Existe por causa da corrida de 22/10/2026 no e-SAJ. O acervo ja tinha a
    integra de um processo, de setembro; a corrida baixou de novo, e as duas
    copias tinham 114 folhas e bytes diferentes. O programa classificou como
    `suspeita` e, corretamente, nao numerou: folha errada em citacao e o pior
    defeito deste indice.

    So que "suspeita" devolvia a pergunta ao advogado sem lhe dar como
    responde-la. A resposta foi obtida a mao, comparando o texto das 114 folhas
    com um comando escrito na hora: ZERO folhas diferentes. Era a mesma
    integra, e o que mudava era o carimbo de geracao que o proprio portal
    escreve dentro do PDF, fora da camada de texto.

    Medir isso e barato e cabe ao programa. `None` quando nao deu para ler:
    aqui a recusa precisa ser distinguivel do "sao diferentes", senao um PDF
    corrompido viraria "mesma copia" e seria descartado.
    """
    import logging

    try:
        from pypdf import PdfReader
    except Exception:
        return None

    # O pypdf grita por folha quando falta `fontTools`, e uma integra de 114
    # folhas rende centenas de linhas que escondem o que importa. O aviso e
    # sobre decodificar fonte, nao sobre o texto, e aqui so o texto interessa.
    calado = logging.getLogger("pypdf")
    nivel = calado.level
    calado.setLevel(logging.ERROR)
    try:
        a, b = PdfReader(str(primeiro)), PdfReader(str(segundo))
        if len(a.pages) != len(b.pages):
            return False
        houve_texto = False
        for folha_a, folha_b in zip(a.pages, b.pages):
            texto_a, texto_b = folha_a.extract_text(), folha_b.extract_text()
            if texto_a != texto_b:
                return False
            if (texto_a or "").strip():
                houve_texto = True
        # AUSENCIA DE TEXTO NAO E PROVA DE IGUALDADE, e esta linha impede uma
        # perda de arquivo. Integra DIGITALIZADA e imagem pura: nao tem camada
        # de texto, e toda folha dela extrai string vazia. Sem esta guarda,
        # duas integras digitalizadas DIFERENTES, com o mesmo numero de folhas,
        # dariam "mesmo texto" e uma seria APAGADA pelo programa.
        #
        # Encontrado em 22/10/2026 por um teste que ja existia e passou a
        # falhar: ele monta PDFs de paginas em branco, que e o mesmo caso.
        # A falha foi do conserto, nao do teste.
        return True if houve_texto else None
    except Exception:
        return None
    finally:
        calado.setLevel(nivel)


@dataclass
class Item:
    tipo: str                      # "integra" ou "documento"
    arquivo: str
    em: str
    paginas: Optional[int] = None
    folha_inicial: Optional[int] = None
    folha_final: Optional[int] = None
    evento: Optional[str] = None
    rotulo: Optional[str] = None
    # Para a integra: maior numero de evento existente quando ela foi tirada.
    # Sem isso o complemento recopia o processo inteiro, porque a integra ja
    # contem os documentos dos eventos anteriores a ela.
    evento_ate: Optional[int] = None
    # Resumo do conteudo, para reconhecer a mesma copia baixada duas vezes.
    # Nasceu vazio nos indices antigos, e e por isso que ele tem valor padrao.
    impressao: Optional[str] = None

    @property
    def chave(self) -> Optional[str]:
        """Identidade do documento no processo, para nao copiar duas vezes."""
        return f"{self.evento}|{self.rotulo}" if self.evento else None

    def faixa(self) -> str:
        if self.folha_inicial is None:
            return "folhas nao contadas"
        if self.folha_inicial == self.folha_final:
            return f"fl. {self.folha_inicial}"
        return f"fls. {self.folha_inicial}/{self.folha_final}"


@dataclass
class Indice:
    numero: str
    pasta: Path
    itens: list[Item] = field(default_factory=list)
    criado_em: Optional[str] = None

    @property
    def vazio(self) -> bool:
        return not self.itens

    @property
    def tem_integra(self) -> bool:
        return any(i.tipo == "integra" for i in self.itens)

    @property
    def ultima_folha(self) -> int:
        return max((i.folha_final or 0) for i in self.itens) if self.itens else 0

    @property
    def chaves_copiadas(self) -> set[str]:
        return {i.chave for i in self.itens if i.chave}

    @property
    def evento_coberto_pela_integra(self) -> int:
        """Ate qual evento a integra mais recente cobre. Zero se nao ha."""
        return max((i.evento_ate or 0) for i in self.itens) if self.itens else 0

    def avaliar_repeticao(self, arquivo: Path) -> tuple[str, Optional[Item]]:
        """Diz se este arquivo ja esta no acervo, antes de gastar numeracao.

        Em 22 de setembro de 2026 a integra do mesmo processo entrou duas
        vezes, e a segunda foi numerada como fls. 115/228: o acervo passou a
        dizer que o processo tem 228 folhas quando tem 114. Folha errada em
        citacao e o pior defeito possivel neste indice, porque o advogado cita
        "fls. 245/250 da copia" e o juiz procura no lugar que nao existe.

        Tres desfechos, e nao dois, porque as certezas sao diferentes:

        `igual`    o conteudo bate byte a byte. E a mesma copia, sem duvida.
        `suspeita` e uma integra com o mesmo numero de paginas de outra que ja
                   esta no acervo, mas o conteudo difere. Provavelmente e a
                   mesma copia com data de geracao diferente, coisa que o
                   proprio portal escreve dentro do PDF; pode tambem ser outra
                   coisa. Quem decide e o operador, nao este codigo.
        `nova`     nao se parece com nada que ja esteja aqui.
        """
        impressao = impressao_do_arquivo(arquivo)
        if impressao:
            for item in self.itens:
                if item.impressao and item.impressao == impressao:
                    return REPETIDA_IGUAL, item
        paginas = contar_paginas(arquivo)
        if paginas:
            for item in self.itens:
                if item.tipo != "integra" or item.paginas != paginas:
                    continue
                # Antes de devolver a pergunta ao advogado, MEDIR. Texto igual
                # folha a folha e a mesma copia, e isso nao e julgamento: e
                # leitura. So o que a medida nao resolver vira `suspeita`.
                if mesmo_texto(Path(item.arquivo), arquivo) is True:
                    return REPETIDA_NO_TEXTO, item
                return REPETIDA_SUSPEITA, item
        return NOVA, None

    def acrescentar(
        self, arquivo: Path, tipo: str, *,
        evento: Optional[str] = None, rotulo: Optional[str] = None,
        evento_ate: Optional[int] = None,
    ) -> Item:
        paginas = contar_paginas(arquivo)
        inicial = final = None
        if paginas:
            inicial = self.ultima_folha + 1
            final = inicial + paginas - 1
        item = Item(
            tipo=tipo, arquivo=str(arquivo),
            em=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            paginas=paginas, folha_inicial=inicial, folha_final=final,
            evento=evento, rotulo=rotulo, evento_ate=evento_ate,
            impressao=impressao_do_arquivo(arquivo),
        )
        self.itens.append(item)
        return item

    def gravar(self) -> Path:
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino = self.pasta / NOME_INDICE
        destino.write_text(json.dumps({
            "numero": self.numero,
            "criado_em": self.criado_em or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "folhas_totais": self.ultima_folha,
            "itens": [vars(i) for i in self.itens],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return destino


def carregar_indice(numero_digitos: str, numero_formatado: str) -> Indice:
    pasta = pasta_do_processo(numero_digitos)
    arquivo = pasta / NOME_INDICE
    # Falha do sistema de arquivos NAO pode virar "nao existe indice". Seria o
    # pior desfecho possivel: o acervo recomecaria a numeracao do zero e a
    # proxima copia entraria como fls. 1, por cima de um historico que esta la.
    # Numerar folha errada e pior que nao numerar, e citar folha errada numa
    # peca e pior ainda. Por isso aqui se insiste e, no limite, se recusa.
    if not _insistir("olhar o indice", arquivo.is_file):
        return Indice(numero=numero_formatado, pasta=pasta)
    bruto_texto = _insistir("ler o indice", lambda: arquivo.read_text(encoding="utf-8"))
    try:
        bruto = json.loads(bruto_texto)
    except json.JSONDecodeError:
        # Indice CORROMPIDO e outra coisa, e aqui a decisao antiga continua
        # valendo: conteudo ilegivel nao pode travar a copia, e a gravacao o
        # refaz. O que mudou e que erro de leitura deixou de ser confundido
        # com conteudo quebrado.
        return Indice(numero=numero_formatado, pasta=pasta)
    return Indice(
        numero=bruto.get("numero", numero_formatado),
        pasta=pasta,
        criado_em=bruto.get("criado_em"),
        itens=[Item(**i) for i in bruto.get("itens", [])],
    )


# COBERTURA DA PASTA, em paginas do PROCESSO.
#
# Esta conta eu fiz a mao em 20/10/2026, com os numeros que o `reindexar`
# imprimia, e ela mostrou duas coisas que ninguem veria de outro jeito numa
# pasta de 35 arquivos e 624 folhas:
#
#   - quatro arquivos eram subconjunto EXATO do anterior, sempre com a mesma
#     pagina final, porque o documento de uma folha so traz o seguinte inteiro
#     junto. Eram 264 folhas contadas duas vezes, 42% da pasta;
#   - 26 paginas numeradas pelo indice nao estavam em arquivo nenhum, e eram
#     justamente certidoes de publicacao e atos ordinatorios, que sao as pecas
#     que fixam termo inicial de prazo.
#
# Enquanto esta conta for feita a mao, nenhuma pasta do escritorio tem essa
# conferencia, porque ninguem a faz duas vezes. A folha do PROCESSO nao e a
# folha do acervo: o acervo numera em sequencia de chegada, e a do processo vem
# do NOME do arquivo, que carrega a pagina em que a peca comeca no indice do
# portal. Sem essa distincao a conta nao fecha.
PADRAO_DA_PAGINA_NO_NOME = re.compile(r"-pagina(\d+)-")


def pagina_do_nome(nome: str) -> Optional[int]:
    """A pagina do PROCESSO em que esta peca comeca, lida do nome do arquivo."""
    achado = PADRAO_DA_PAGINA_NO_NOME.search(nome or "")
    return int(achado.group(1)) if achado else None


def _faixas(numeros: list) -> list:
    """Numeros soltos viram faixas: [1,2,3,7] vira [(1,3),(7,7)]."""
    saida: list = []
    inicio = anterior = None
    for numero in numeros:
        if inicio is None:
            inicio = anterior = numero
        elif numero == anterior + 1:
            anterior = numero
        else:
            saida.append((inicio, anterior))
            inicio = anterior = numero
    if inicio is not None:
        saida.append((inicio, anterior))
    return saida


def processos_guardados(teto: int = 200) -> list:
    """Os processos que ha na raiz das copias, com o tamanho de cada um.

    Nasceu de uma limitacao boba e real: para perguntar qualquer coisa ao
    conector era preciso saber o numero do processo de cor. A pasta sabe.

    Nao abre PDF nenhum: le o indice quando ha, e conta arquivos quando nao
    ha. Abrir todos os arquivos de todos os processos para contar folha
    tornaria a listagem lenta justamente quando o acervo cresce, que e quando
    ela passa a ser util.
    """
    raiz = pasta_de_copias()
    if not raiz.is_dir():
        return []
    achados: list = []
    for pasta in sorted(raiz.iterdir()):
        try:
            if not pasta.is_dir():
                continue
        except OSError:
            continue
        digitos = pasta.name
        if not (digitos.isdigit() and len(digitos) == 20):
            continue
        arquivos = [a for a in pasta.glob("*.pdf") if a.is_file()]
        bytes_totais = 0
        modificado = None
        for arquivo in arquivos:
            try:
                dados = arquivo.stat()
            except OSError:
                continue
            bytes_totais += dados.st_size
            if modificado is None or dados.st_mtime > modificado:
                modificado = dados.st_mtime
        folhas = None
        indice_bruto = pasta / NOME_INDICE
        if indice_bruto.is_file():
            try:
                folhas = json.loads(
                    indice_bruto.read_text(encoding="utf-8")).get("folhas_totais")
            except (OSError, json.JSONDecodeError, AttributeError):
                folhas = None
        achados.append({
            "numero": formatar_numero(digitos),
            "digitos": digitos,
            "arquivos": len(arquivos),
            "folhas_no_indice": folhas,
            "bytes": bytes_totais,
            "modificado_em": (
                datetime.fromtimestamp(modificado, tz=timezone.utc).isoformat(
                    timespec="seconds") if modificado else None),
        })
        if len(achados) >= teto:
            break
    achados.sort(key=lambda p: p["modificado_em"] or "", reverse=True)
    return achados


def formatar_numero(digitos: str) -> str:
    """Os vinte digitos na forma da numeracao unica, sem validar nada.

    Aqui nao se confere digito verificador: o nome da pasta ja existe, e
    recusar a listagem por causa dele esconderia do advogado uma pasta que
    esta la.
    """
    if len(digitos) != 20 or not digitos.isdigit():
        return digitos
    return (f"{digitos[:7]}-{digitos[7:9]}.{digitos[9:13]}."
            f"{digitos[13]}.{digitos[14:16]}.{digitos[16:]}")


def cobertura_do_acervo(indice: "Indice") -> dict:
    """Que paginas do processo a pasta cobre, o que cobre duas vezes e o que falta.

    Nao apaga nem move nada: so conta. Quem decide o que fazer com uma peca
    contida noutra e o advogado, porque a conteneza e medida pela FAIXA de
    paginas e nao pelo conteudo byte a byte, e peca de autos nao se descarta
    por inferencia.
    """
    if not indice.pasta.is_dir():
        return {"existe": False, "pecas": [], "sem_pagina": [], "contidas": [],
                "folhas_repetidas": 0, "distintas": 0, "faltam": [],
                "faixas_que_faltam": [], "primeira": None, "ultima": None,
                "truncados": []}

    pecas: list = []
    sem_pagina: list = []
    truncados: list = []
    for arquivo in sorted(indice.pasta.glob("*.pdf")):
        try:
            if not arquivo.is_file() or arquivo.stat().st_size <= 0:
                continue
        except OSError:
            continue
        if parece_truncado(arquivo):
            truncados.append({"arquivo": arquivo.name,
                              "bytes": arquivo.stat().st_size})
        inicio = pagina_do_nome(arquivo.name)
        folhas = contar_paginas(arquivo)
        if inicio is None or not folhas:
            sem_pagina.append(arquivo.name)
            continue
        pecas.append({"arquivo": arquivo.name, "inicio": inicio,
                      "folhas": folhas, "fim": inicio + folhas - 1})
    pecas.sort(key=lambda p: (p["inicio"], p["fim"]))

    contidas: list = []
    repetidas = 0
    for i, peca in enumerate(pecas):
        for outra in pecas[:i]:
            if outra["inicio"] <= peca["inicio"] and peca["fim"] <= outra["fim"]:
                contidas.append({"arquivo": peca["arquivo"],
                                 "dentro_de": outra["arquivo"],
                                 "folhas": peca["folhas"],
                                 "faixa": (peca["inicio"], peca["fim"])})
                repetidas += peca["folhas"]
                break

    cobertas: set = set()
    for peca in pecas:
        cobertas.update(range(peca["inicio"], peca["fim"] + 1))
    primeira = min(cobertas) if cobertas else None
    ultima = max(cobertas) if cobertas else None
    faltam = (sorted(set(range(primeira, ultima + 1)) - cobertas)
              if cobertas else [])
    return {"existe": True, "pecas": pecas, "sem_pagina": sem_pagina,
            "contidas": contidas, "folhas_repetidas": repetidas,
            "distintas": len(cobertas), "faltam": faltam,
            "faixas_que_faltam": _faixas(faltam),
            "primeira": primeira, "ultima": ultima,
            "truncados": truncados}


def relatar_a_cobertura(cobertura: dict, teto: int = 12) -> list:
    """A cobertura em linhas. Nenhuma delas carrega conteudo do processo."""
    if not cobertura.get("existe"):
        return ["A pasta nao existe."]
    pecas = cobertura["pecas"]
    if not pecas:
        return ["Nenhuma peca com pagina legivel no nome: a cobertura nao "
                "pode ser conferida."]
    somadas = sum(p["folhas"] for p in pecas)
    linhas = [
        f"COBERTURA: {len(pecas)} peca(s), {somadas} folha(s) somadas, "
        f"cobrindo {cobertura['distintas']} pagina(s) distinta(s) do processo "
        f"(da {cobertura['primeira']} a {cobertura['ultima']})."
    ]
    if cobertura.get("truncados"):
        linhas.append(
            f"CORTADO: {len(cobertura['truncados'])} arquivo(s) nao tem a "
            "marca de fim do PDF e podem ser download interrompido.")
        for item in cobertura["truncados"][:teto]:
            linhas.append(f"  {item['arquivo']} ({item['bytes']} byte(s))")
        linhas.append(
            "  Nada foi apagado. Confira e baixe de novo o que estiver "
            "incompleto: PDF cortado abre e mostra so o comeco.")
    if cobertura["sem_pagina"]:
        linhas.append(
            f"{len(cobertura['sem_pagina'])} arquivo(s) sem pagina legivel no "
            "nome ficaram FORA desta conta.")
    if cobertura["contidas"]:
        linhas.append(
            f"REPETIDO: {len(cobertura['contidas'])} peca(s) estao inteiras "
            f"dentro de outra, somando {cobertura['folhas_repetidas']} folha(s) "
            f"contadas duas vezes de {somadas}.")
        for item in cobertura["contidas"][:teto]:
            linhas.append(
                f"  {item['arquivo']} (fls. {item['faixa'][0]}-"
                f"{item['faixa'][1]}) esta dentro de {item['dentro_de']}")
        if len(cobertura["contidas"]) > teto:
            linhas.append(f"  e mais {len(cobertura['contidas']) - teto}.")
        linhas.append(
            "  Nada foi apagado: a conteneza aqui e medida pela FAIXA de "
            "paginas, nao pelo conteudo byte a byte, e peca de autos nao se "
            "descarta por inferencia.")
    if cobertura["faltam"]:
        faixas = ", ".join(f"{a}" if a == b else f"{a}-{b}"
                           for a, b in cobertura["faixas_que_faltam"][:teto])
        linhas.append(
            f"FALTAM {len(cobertura['faltam'])} pagina(s) dentro do intervalo "
            f"que a pasta cobre: {faixas}"
            + (" e mais." if len(cobertura["faixas_que_faltam"]) > teto else ""))
        linhas.append(
            "  Pagina que falta dentro do intervalo e peca que o indice numera "
            "e a pasta nao tem. Pode ser certidao de publicacao ou ato "
            "ordinatorio, que sao as pecas que fixam termo inicial de prazo.")
    if not cobertura["contidas"] and not cobertura["faltam"]:
        linhas.append(
            "Sem repeticao e sem buraco DENTRO do intervalo coberto. Isto nao "
            "diz que a copia esta completa: o intervalo pode comecar depois do "
            "inicio dos autos. So o indice do portal diz onde o processo "
            "comeca.")
    return linhas


FORMA_DA_PARTE = re.compile(r"^integra-parte(\d+)-", re.IGNORECASE)


def parte_da_integra(nome: str) -> Optional[int]:
    """O numero da parte quando o arquivo e pedaco de uma integra partida.

    So reconhece o nome que o proprio programa escreve (`integra-parte3-...`),
    nunca o nome que veio do portal: portal nomeia como quer, e adivinhar
    ordem a partir do nome dele e adivinhar numero de folha.
    """
    achado = FORMA_DA_PARTE.match(nome)
    return int(achado.group(1)) if achado else None


def ordem_da_numeracao(arquivos: list, ja_indexados: list) -> list:
    """A ordem em que os arquivos recebem folha.

    Nasceu de um estrago real: em 25/10/2026 a parte 1 de uma integra de tres
    partes foi baixada de novo, ficou com a hora de hoje e, como a ordem era a
    hora do arquivo, o indice passou a numerar parte2 como fls. 1/2084 e parte1
    como fls. 2156/2237. O total continuou certo, 2237 folhas, e por isso a
    conferencia de cobertura nao acusava nada: so a ordem estava errada. Citar
    "fls. 100" nessa copia apontaria para a peca errada, e folha errada em peca
    protocolada nao se desfaz.

    Duas regras, nesta ordem:

    1. Peca que o indice antigo ja numerou nao muda de lugar. O numero dela
       pode ja ter sido citado em peca protocolada, e so por isso a hora do
       arquivo perde para a posicao no indice. Arquivo novo entra depois dos
       que o indice ja conhecia, na ordem de chegada.
    2. Integra partida e numerada na sequencia das partes, no lugar da parte
       que chegou primeiro. Parte 2 nunca vem antes da parte 1, qualquer que
       seja a hora dos arquivos.
    """
    posicao = {nome: i for i, nome in enumerate(ja_indexados)}

    def chegada(arquivo) -> tuple:
        if arquivo.name in posicao:
            return (0, posicao[arquivo.name], 0.0, arquivo.name)
        return (1, 0, arquivo.stat().st_mtime, arquivo.name)

    partes = [a for a in arquivos if parte_da_integra(a.name) is not None]
    ancora_das_partes = min((chegada(a) for a in partes), default=None)

    def chave(arquivo) -> tuple:
        numero = parte_da_integra(arquivo.name)
        if numero is None:
            return (chegada(arquivo), 0, chegada(arquivo))
        return (ancora_das_partes, numero, chegada(arquivo))

    return sorted(arquivos, key=chave)


def planejar_reindexacao(indice: "Indice") -> dict:
    """Monta o plano de refazer o indice a partir dos arquivos que existem.

    Nasceu de um estrago real: em 22/09/2026 a mesma integra entrou duas vezes
    e o indice passou a dizer 228 folhas num processo de 114. Consertar isso na
    mao significaria editar JSON, que e pedir para errar folha.

    O plano NAO e executado aqui. Quem varre e quem apaga sao passos separados
    de proposito: o operador le o que vai acontecer com os arquivos do
    escritorio antes de qualquer coisa acontecer.

    Regras:
      - arquivos de conteudo identico sao uma copia so; fica o que ja estava
        indexado (e portanto ja pode ter sido citado) e, entre dois nao
        indexados, o mais antigo; os outros saem;
      - a ordem da numeracao e a de `ordem_da_numeracao`, nao a hora do
        arquivo: peca que ja tem folha no indice nao muda de lugar, e integra
        partida e numerada na sequencia das partes;
      - o que o indice antigo sabia sobre um arquivo que fica (se e integra ou
        documento, o evento, o rotulo) e preservado, porque isso nao esta no
        PDF e seria perdido para sempre.
    """
    if not indice.pasta.is_dir():
        return {"manter": [], "apagar": [], "total": 0}

    antigos = {Path(i.arquivo).name: i for i in indice.itens}
    arquivos = ordem_da_numeracao(
        [a for a in indice.pasta.iterdir()
         if a.is_file() and a.suffix.lower() == ".pdf"],
        [Path(i.arquivo).name for i in indice.itens],
    )

    manter: list[dict] = []
    apagar: list[dict] = []
    vistos: dict[str, Path] = {}
    folha = 0
    for arquivo in arquivos:
        impressao = impressao_do_arquivo(arquivo)
        if impressao and impressao in vistos:
            apagar.append({"arquivo": arquivo, "igual_a": vistos[impressao]})
            continue
        if impressao:
            vistos[impressao] = arquivo
        antigo = antigos.get(arquivo.name)
        paginas = contar_paginas(arquivo)
        inicial = final = None
        if paginas:
            inicial, final = folha + 1, folha + paginas
            folha = final
        manter.append({
            "arquivo": arquivo, "paginas": paginas,
            "folha_inicial": inicial, "folha_final": final,
            "impressao": impressao,
            "tipo": antigo.tipo if antigo else (
                "integra" if arquivo.name.startswith("integra") else "documento"),
            "evento": antigo.evento if antigo else None,
            "rotulo": antigo.rotulo if antigo else None,
            "evento_ate": antigo.evento_ate if antigo else None,
            "em": antigo.em if antigo else None,
        })
    return {"manter": manter, "apagar": apagar, "total": folha}


def aplicar_reindexacao(indice: "Indice", plano: dict, *, apagar_repetidos: bool) -> list[str]:
    """Executa o plano e devolve o que foi feito, linha por linha."""
    feito = []
    if apagar_repetidos:
        for repetido in plano["apagar"]:
            try:
                repetido["arquivo"].unlink()
                feito.append(f"apagado {repetido['arquivo'].name} "
                             f"(identico a {repetido['igual_a'].name})")
            except OSError as exc:
                feito.append(f"NAO consegui apagar {repetido['arquivo'].name}: {exc}")

    indice.itens = [
        Item(tipo=m["tipo"], arquivo=str(m["arquivo"]),
             em=m["em"] or datetime.now(timezone.utc).isoformat(timespec="seconds"),
             paginas=m["paginas"], folha_inicial=m["folha_inicial"],
             folha_final=m["folha_final"], evento=m["evento"], rotulo=m["rotulo"],
             evento_ate=m["evento_ate"], impressao=m["impressao"])
        for m in plano["manter"]
    ]
    feito.append(f"indice refeito com {len(indice.itens)} item(ns), "
                 f"{indice.ultima_folha} folha(s)")
    indice.gravar()
    return feito


def numero_do_evento(evento: dict) -> Optional[int]:
    bruto = str(evento.get("evento") or "").strip()
    return int(bruto) if bruto.isdigit() else None


def maior_evento(eventos: list[dict]) -> int:
    numeros = [n for n in (numero_do_evento(e) for e in eventos) if n is not None]
    return max(numeros) if numeros else 0


def decidir_estrategia(indice: Indice, eventos: list[dict]) -> dict[str, Any]:
    """Integra quando nao ha copia; complemento quando ha.

    O complemento traz apenas o que a copia existente NAO cobre. Dois filtros,
    e os dois sao necessarios:

    1. Eventos posteriores ao que a integra alcancou. A integra contem os
       documentos dos eventos anteriores a ela, e sem este filtro o complemento
       recopiaria o processo inteiro a cada consulta.
    2. Documentos ainda nao registrados no indice, para nao repetir os
       complementos anteriores.
    """
    if indice.vazio:
        return {"acao": "integra", "motivo": "Nao ha copia na pasta deste processo."}

    coberto = indice.evento_coberto_pela_integra
    faltantes = []
    for evento in eventos:
        numero = numero_do_evento(evento)
        if numero is not None and numero <= coberto:
            continue
        for documento in evento.get("documentos") or []:
            chave = f"{evento.get('evento')}|{documento.get('rotulo')}"
            if chave not in indice.chaves_copiadas:
                faltantes.append({"evento": evento, "documento": documento})

    alcance = f" A integra cobre ate o evento {coberto}." if coberto else ""
    return {
        "acao": "complemento",
        "faltantes": faltantes,
        "evento_coberto": coberto,
        "motivo": (
            f"Ja ha copia ate a folha {indice.ultima_folha}.{alcance} "
            f"{len(faltantes)} documento(s) por copiar."
            if faltantes else
            f"Ja ha copia ate a folha {indice.ultima_folha}.{alcance} Nada novo a copiar."
        ),
    }
