"""Reconhecimento optico das folhas que sao imagem digitalizada.

POR QUE ISTO EXISTE. Ate a versao 0.9.9, `ler_peca` devolvia o texto das folhas
com camada de texto e so AVISAVA das outras ("folhas_sem_texto": imagem
digitalizada, nao folha em branco). O aviso era honesto, mas deixava a analise
cega justamente onde os autos antigos mais pesam: processo fisico digitalizado
do Portal de Servicos, aviso de recebimento, documento juntado pela parte.

O teste de 06/11/2026, com tres copias reais do acervo (2.341 folhas), mostrou
o que o reconhecimento entrega e o que ele erra:

- em portugues, o Tesseract leu 31 de 32 palavras acentuadas numa folha de
  peticao; em ingles, que e o padrao de quase toda ferramenta, leu 2 de 32.
  Por isso o idioma e FIXO em portugues aqui, e nao configuravel por engano;
- num aviso de recebimento, leu a data como 29/06/2025 (era 2023) e trocou
  digitos dos numeros da intimacao e da decisao; num termo da Junta
  Comercial, leu o CNPJ com virgula no lugar do ponto. As duas folhas tinham
  confianca abaixo de 80%. Por isso toda folha lida assim volta MARCADA com a
  confianca, e as de confianca baixa voltam em `folhas_para_conferir`.

O QUE ESTE MODULO NAO FAZ: nao escreve nada na pasta de copias. A pasta e o
acervo da banca no Google Drive, compartilhado; o resultado do reconhecimento
fica no diretorio de estado DESTA maquina (`ocr/`), como cache. Apagar esse
cache so custa reconhecer de novo.

DEPENDENCIAS, e o que acontece sem elas. O reconhecimento precisa de duas
coisas fora do `pypdf`: o programa Tesseract com o pacote de idioma portugues
(`por`), e o `pypdfium2`, que transforma a folha do PDF em imagem. Sem
qualquer das duas, `disponibilidade()` diz qual falta e como instalar, e a
leitura segue exatamente como era antes: o texto das folhas com camada de
texto, e o aviso das outras. Faltar o reconhecimento nunca derruba a leitura.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

IDIOMA = "por"

# Abaixo disto, a folha volta marcada para conferencia no original. O valor
# saiu do teste de 06/11/2026: os dois erros que mudariam uma peticao (data do
# aviso de recebimento e CNPJ) estavam em folhas com 65% e 79% de confianca.
LIMIAR_DE_CONFERENCIA = 80.0

# Resolucao da imagem da folha. 300 pontos por polegada e o que o proprio
# Tesseract recomenda; abaixo disso a leitura de acento cai visivelmente.
RESOLUCAO = 300

# Tempo maximo por folha. Folha que passa disso e foto de pagina inteira ou
# lixo de digitalizacao, e esperar mais nao a torna legivel.
TEMPO_POR_FOLHA = 90

# Caminhos onde o instalador do Tesseract para Windows costuma deixar o
# programa, quando ele nao esta no PATH. Conferido no instalador da
# Universidade de Mannheim, que e o que a documentacao do Tesseract indica.
CAMINHOS_WINDOWS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

# Versao do formato do cache. Mudou a forma de reconhecer? Muda o numero, e o
# cache velho deixa de valer sozinho, sem ninguem precisar lembrar de apaga-lo.
VERSAO_DO_CACHE = 1


@dataclass(frozen=True)
class Disponibilidade:
    pronto: bool
    motivo: str = ""
    tesseract: Optional[str] = None


def ligado() -> bool:
    """O reconhecimento esta ligado, salvo se `JUSTICA_OCR` disser que nao."""
    valor = (os.environ.get("JUSTICA_OCR") or "").strip().lower()
    return valor not in ("0", "nao", "não", "desligado", "false", "off")


def _achar_tesseract() -> Optional[str]:
    explicito = (os.environ.get("JUSTICA_TESSERACT") or "").strip().strip('"')
    if explicito:
        return explicito if Path(explicito).is_file() else None
    achado = shutil.which("tesseract")
    if achado:
        return achado
    for caminho in CAMINHOS_WINDOWS:
        if Path(caminho).is_file():
            return caminho
    return None


_cache_disponibilidade: Optional[Disponibilidade] = None


def disponibilidade(renovar: bool = False) -> Disponibilidade:
    """Se da para reconhecer, e, se nao der, o que falta. Nunca levanta erro."""
    global _cache_disponibilidade
    if _cache_disponibilidade is not None and not renovar:
        return _cache_disponibilidade

    if not ligado():
        resposta = Disponibilidade(False, "reconhecimento desligado por "
                                          "JUSTICA_OCR.")
    else:
        try:
            import pypdfium2  # noqa: F401
            tem_pdfium = True
        except Exception:
            tem_pdfium = False
        caminho = _achar_tesseract()
        if not tem_pdfium:
            resposta = Disponibilidade(
                False, "falta o pypdfium2 no ambiente do conector "
                       "(.venv\\Scripts\\pip install pypdfium2).")
        elif caminho is None:
            resposta = Disponibilidade(
                False, "o programa Tesseract nao foi encontrado. Instale-o "
                       "(no Windows, pelo instalador da Universidade de "
                       "Mannheim, marcando o idioma Portuguese) ou aponte "
                       "JUSTICA_TESSERACT para o tesseract.exe.")
        else:
            try:
                saida = subprocess.run(
                    [caminho, "--list-langs"], capture_output=True, text=True,
                    timeout=30)
                idiomas = (saida.stdout or "").split()
            except Exception as erro:
                idiomas = []
                resposta = Disponibilidade(
                    False, f"o Tesseract nao respondeu ({type(erro).__name__}).",
                    caminho)
            else:
                if IDIOMA in idiomas:
                    resposta = Disponibilidade(True, "", caminho)
                else:
                    resposta = Disponibilidade(
                        False, "o Tesseract esta instalado, mas sem o pacote "
                               "de idioma portugues ('por'). Sem ele a leitura "
                               "erra quase toda palavra acentuada.", caminho)
    _cache_disponibilidade = resposta
    return resposta


# ------------------------- folha com carimbo -------------------------
#
# No PDF do Processo Judicial Eletronico, TODA folha escaneada traz o carimbo
# digital do sistema ("Assinado eletronicamente por...", "Num. ... - Pag. ..."),
# com umas 400 letras. Medir so a quantidade de texto, como a leitura fazia,
# faz a folha escaneada parecer folha com texto, e ela nunca chega ao
# reconhecimento. Visto no teste de 06/11/2026: das 48 folhas digitalizadas de
# uma copia do Juizado de Teresopolis, nenhuma seria reconhecida.
#
# O criterio que separa as duas: quanto da folha e IMAGEM. Peticao digital tem
# logotipo e codigo QR (menos da metade da folha); folha escaneada e uma imagem
# do tamanho da folha, com o carimbo por cima.
COBERTURA_DE_FOLHA_ESCANEADA = 0.5
TEXTO_MAXIMO_DE_CARIMBO = 1500


class MedidorDeImagem:
    """Abre o PDF uma vez e mede, folha a folha, quanto dela e imagem."""

    def __init__(self, arquivo: Path) -> None:
        self._documento = None
        try:
            import pypdfium2 as pdfium

            self._documento = pdfium.PdfDocument(str(arquivo))
        except Exception:
            self._documento = None

    def cobertura(self, folha: int) -> Optional[float]:
        if self._documento is None:
            return None
        try:
            import pypdfium2.raw as cru

            pagina = self._documento[folha - 1]
            largura, altura = pagina.get_size()
            area = largura * altura
            soma = 0.0
            for objeto in pagina.get_objects(filter=(cru.FPDF_PAGEOBJ_IMAGE,),
                                             max_depth=3):
                obter = getattr(objeto, "get_bounds", None) or objeto.get_pos
                esquerda, baixo, direita, topo = obter()
                soma += max(0.0, direita - esquerda) * max(0.0, topo - baixo)
            pagina.close()
            return min(1.0, soma / area) if area else None
        except Exception:
            return None

    def parece_escaneada(self, folha: int, letras: int) -> bool:
        if letras >= TEXTO_MAXIMO_DE_CARIMBO:
            return False
        cobertura = self.cobertura(folha)
        return cobertura is not None and cobertura >= COBERTURA_DE_FOLHA_ESCANEADA

    def fechar(self) -> None:
        try:
            if self._documento is not None:
                self._documento.close()
        except Exception:
            pass


# ------------------------------- cache -------------------------------

def _pasta_do_cache() -> Path:
    from .core.estado import diretorio_estado

    pasta = diretorio_estado() / "ocr"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _chave(arquivo: Path, folha: int) -> str:
    """Nome, tamanho e data de modificacao do arquivo, mais a folha.

    Nao e o conteudo inteiro de proposito: hashear 25 MB a cada leitura
    custaria mais do que o reconhecimento de uma folha. Se o arquivo for
    regravado, tamanho ou data mudam e a chave muda junto.
    """
    info = arquivo.stat()
    base = f"{arquivo.name}|{info.st_size}|{int(info.st_mtime)}|{folha}|" \
           f"{VERSAO_DO_CACHE}|{RESOLUCAO}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def do_cache(arquivo: Path, folha: int) -> Optional[dict]:
    try:
        caminho = _pasta_do_cache() / f"{_chave(arquivo, folha)}.json"
        if caminho.is_file():
            return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _para_o_cache(arquivo: Path, folha: int, dados: dict) -> None:
    try:
        caminho = _pasta_do_cache() / f"{_chave(arquivo, folha)}.json"
        caminho.write_text(json.dumps(dados, ensure_ascii=False),
                           encoding="utf-8")
    except Exception:
        pass  # cache e conveniencia; falhar nele nao derruba a leitura


# --------------------------- reconhecimento ---------------------------

def _imagem_da_folha(arquivo: Path, folha: int, destino: Path) -> None:
    """Grava a folha como imagem em tons de cinza (PGM), que o Tesseract le.

    PGM e de proposito: e o formato mais simples que existe (um cabecalho de
    texto e os bytes da imagem), entao nao exige biblioteca de imagem nenhuma
    alem do `pypdfium2`, que ja e o que desenha a folha.
    """
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(str(arquivo))
    try:
        pagina = documento[folha - 1]
        mapa = pagina.render(scale=RESOLUCAO / 72, grayscale=True)
        largura, altura = mapa.width, mapa.height
        passo, canais = mapa.stride, max(1, int(mapa.n_channels))
        bruto = bytes(mapa.buffer)
        with open(destino, "wb") as saida:
            saida.write(b"P5\n%d %d\n255\n" % (largura, altura))
            for linha in range(altura):
                inicio = linha * passo
                # A linha pode ter enchimento no fim (passo > largura).
                fatia = bruto[inicio:inicio + largura * canais]
                if canais > 1:
                    # Mapa colorido mesmo pedindo cinza: um canal basta para
                    # texto preto em papel claro.
                    fatia = fatia[::canais]
                saida.write(fatia)
        mapa.close()
        pagina.close()
    finally:
        documento.close()


def _texto_da_tsv(tsv: str) -> tuple[str, float, int]:
    """Texto montado linha a linha e a confianca media ponderada pelo tamanho
    das palavras. Palavra curta de confianca baixa (um "x" de formulario) nao
    deve pesar como um numero de processo."""
    linhas: dict = {}
    ordem: list = []
    soma = 0.0
    peso = 0
    paragrafo_anterior = None
    for registro in tsv.splitlines()[1:]:
        campos = registro.split("\t")
        if len(campos) < 12:
            continue
        palavra = campos[11].strip()
        try:
            confianca = float(campos[10])
        except ValueError:
            continue
        if not palavra or confianca < 0:
            continue
        chave = (campos[2], campos[3], campos[4])
        paragrafo = (campos[2], campos[3])
        if chave not in linhas:
            if paragrafo_anterior is not None and paragrafo != paragrafo_anterior:
                ordem.append(None)
            linhas[chave] = []
            ordem.append(chave)
            paragrafo_anterior = paragrafo
        linhas[chave].append(palavra)
        soma += confianca * len(palavra)
        peso += len(palavra)
    texto = "\n".join("" if c is None else " ".join(linhas[c]) for c in ordem)
    media = round(soma / peso, 1) if peso else 0.0
    return texto.strip(), media, sum(len(v) for v in linhas.values())


def reconhecer(arquivo: Path, folha: int) -> dict:
    """Le UMA folha por reconhecimento optico, usando o cache quando houver.

    Devolve {"texto", "confianca", "palavras", "do_cache"} ou {"erro"}.
    """
    guardado = do_cache(arquivo, folha)
    if guardado is not None:
        guardado["do_cache"] = True
        return guardado

    estado = disponibilidade()
    if not estado.pronto:
        return {"erro": estado.motivo}

    with tempfile.TemporaryDirectory(prefix="justica-ocr-") as tmp:
        imagem = Path(tmp) / "folha.pgm"
        try:
            _imagem_da_folha(arquivo, folha, imagem)
        except Exception as erro:
            return {"erro": f"a folha nao pode ser desenhada "
                            f"({type(erro).__name__})."}
        try:
            saida = subprocess.run(
                [estado.tesseract, str(imagem), "stdout", "-l", IDIOMA,
                 "--psm", "3", "tsv"],
                capture_output=True, timeout=TEMPO_POR_FOLHA)
        except subprocess.TimeoutExpired:
            return {"erro": f"o reconhecimento passou de {TEMPO_POR_FOLHA} s "
                            "nesta folha."}
        except Exception as erro:
            return {"erro": f"o Tesseract falhou ({type(erro).__name__})."}
        if saida.returncode != 0:
            return {"erro": "o Tesseract terminou com erro "
                            f"(codigo {saida.returncode})."}
        tsv = saida.stdout.decode("utf-8", errors="replace")

    texto, confianca, palavras = _texto_da_tsv(tsv)
    dados = {"texto": texto, "confianca": confianca, "palavras": palavras,
             "versao": VERSAO_DO_CACHE}
    _para_o_cache(arquivo, folha, dados)
    dados["do_cache"] = False
    return dados
