"""Reconhecimento optico das folhas digitalizadas na leitura das pecas.

O que estes testes guardam, e por que:

- folha lida por reconhecimento volta MARCADA, com a confianca. Texto
  reconhecido nao pode se misturar ao texto digital como se fosse igual: no
  teste de 06/11/2026 o reconhecimento leu a data de um aviso de recebimento
  como 2025 (era 2023);
- confianca baixa vira `folhas_para_conferir`, e o aviso diz o que conferir;
- sem Tesseract, sem o idioma portugues ou sem `pypdfium2`, a leitura segue
  exatamente como antes, e diz o que falta. Faltar reconhecimento nunca
  derruba a leitura;
- o teto de folhas novas por chamada corta COM aviso e lugar para continuar;
  folha ja reconhecida vem do cache e nao gasta o teto.

A maior parte usa um reconhecedor falso, para nao depender do Tesseract na
maquina de quem roda os testes. O teste de ponta a ponta so roda onde houver
Tesseract com portugues, `pypdfium2` e Pillow; nos outros lugares ele e pulado
dizendo por que.
"""

import pytest

from test_pecas import DIGITOS, FORMATADO, _pasta_com


@pytest.fixture
def ocr_ligado(monkeypatch, tmp_path):
    monkeypatch.setenv("JUSTICA_OCR", "1")
    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path / "estado"))
    from justica_mcp import ocr

    monkeypatch.setattr(ocr, "_cache_disponibilidade", None)
    return ocr


@pytest.fixture
def reconhecedor_falso(ocr_ligado, monkeypatch):
    """Reconhecedor que devolve texto e confianca combinados por folha."""
    ocr = ocr_ligado
    respostas = {}
    chamadas = []
    em_cache = set()

    monkeypatch.setattr(ocr, "disponibilidade",
                        lambda renovar=False: ocr.Disponibilidade(True, "", "x"))
    monkeypatch.setattr(ocr, "do_cache",
                        lambda arquivo, folha: ({"texto": respostas[folha][0],
                                                 "confianca": respostas[folha][1]}
                                                if folha in em_cache else None))

    def reconhecer(arquivo, folha):
        chamadas.append(folha)
        texto, confianca = respostas[folha]
        veio_do_cache = folha in em_cache
        em_cache.add(folha)
        return {"texto": texto, "confianca": confianca, "palavras": 5,
                "do_cache": veio_do_cache}

    monkeypatch.setattr(ocr, "reconhecer", reconhecer)
    return respostas, chamadas, em_cache


def test_folha_digitalizada_volta_lida_e_marcada(tmp_path, monkeypatch,
                                                 reconhecedor_falso):
    from justica_mcp.pecas import ler_peca

    respostas, _, _ = reconhecedor_falso
    respostas[2] = ("AVISO DE RECEBIMENTO data de entrega 29/06/2023", 92.4)
    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "folha um com bastante texto digital", "",
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert lido["folhas_com_texto"] == 2
    assert lido["folhas_sem_texto"] == []
    assert lido["folhas_por_ocr"] == [{"folha": 2, "confianca": 92.4}]
    assert lido["folhas_para_conferir"] == []
    assert "--- folha 1 ---" in lido["texto"]
    assert ("--- folha 2 (lida por reconhecimento optico, confianca 92.4%) ---"
            in lido["texto"])
    assert "29/06/2023" in lido["texto"]


def test_confianca_baixa_vai_para_conferencia(tmp_path, monkeypatch,
                                              reconhecedor_falso):
    """O caso real do CNPJ lido com virgula, em folha de 65% de confianca."""
    from justica_mcp.pecas import ler_peca

    respostas, _, _ = reconhecedor_falso
    respostas[1] = ("TERMO DE AUTENTICACAO CNPJ 19.419,179/0001-44", 65.1)
    _pasta_com(tmp_path, monkeypatch, {"proc-pagina88-Contrato.pdf": [""]})
    lido = ler_peca(DIGITOS, FORMATADO, 88)
    assert lido["folhas_para_conferir"] == [1]
    assert "CONFERIR NO ORIGINAL" in lido["texto"]
    assert "CNPJ" in lido["aviso"] and "conferidos no original" in lido["aviso"]


def test_sem_tesseract_a_leitura_segue_como_antes(tmp_path, monkeypatch,
                                                  ocr_ligado):
    from justica_mcp.pecas import ler_peca

    monkeypatch.setattr(ocr_ligado, "_achar_tesseract", lambda: None)
    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "folha um com bastante texto", "", "folha tres com bastante texto",
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert lido["folhas_sem_texto"] == [2]
    assert lido["folhas_com_texto"] == 2
    assert "Tesseract" in lido["ocr_indisponivel"]
    assert "1 folha(s) sem camada de texto" in lido["aviso"]
    assert "indisponivel" in lido["aviso"]


def test_peca_toda_digitalizada_sem_ocr_nao_e_peca_em_branco(
        tmp_path, monkeypatch, ocr_ligado):
    from justica_mcp.pecas import ler_peca

    monkeypatch.setattr(ocr_ligado, "_achar_tesseract", lambda: None)
    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": ["", ""]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert lido["folhas_sem_texto"] == [1, 2]
    assert "NAO significa que a peca esteja em branco" in lido["aviso"]
    assert "indisponivel nesta maquina" in lido["aviso"]


def test_ocr_falso_na_chamada_nao_reconhece(tmp_path, monkeypatch,
                                            reconhecedor_falso):
    from justica_mcp.pecas import ler_peca

    respostas, chamadas, _ = reconhecedor_falso
    respostas[1] = ("nao devia ser lido nesta chamada", 99.0)
    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [""]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666, ocr=False)
    assert chamadas == []
    assert lido["folhas_sem_texto"] == [1]
    assert "ocr=false" in lido["aviso"]


def test_o_teto_de_reconhecimento_corta_com_lugar_para_continuar(
        tmp_path, monkeypatch, reconhecedor_falso):
    """Sem teto, peca digitalizada de 130 folhas prenderia a ferramenta por
    mais de dez minutos. Cortar e aceitavel; cortar em silencio nao e."""
    from justica_mcp.pecas import texto_das_folhas

    respostas, chamadas, _ = reconhecedor_falso
    for folha in (1, 2, 3):
        respostas[folha] = (f"conteudo reconhecido da folha numero {folha}", 90.0)
    pasta = _pasta_com(tmp_path, monkeypatch,
                       {"proc-pagina1666-B.pdf": ["", "", ""]})
    arquivo = pasta / "proc-pagina1666-B.pdf"

    primeira = texto_das_folhas(arquivo, 1, None, teto_ocr=2)
    assert chamadas == [1, 2]
    assert primeira["cortado"] is True
    assert primeira["ate"] == 2
    assert "de=3" in primeira["aviso"]
    assert "folha numero 3" not in primeira["texto"]

    # Continuacao: a folha 3 e nova; as anteriores, se pedidas de novo, vem do
    # cache e nao gastam o teto.
    segunda = texto_das_folhas(arquivo, 1, None, teto_ocr=1)
    assert segunda["cortado"] is False
    assert "folha numero 1" in segunda["texto"]
    assert "folha numero 3" in segunda["texto"]


def test_reconhecimento_que_nao_acha_texto_fica_sem_texto(tmp_path, monkeypatch,
                                                          reconhecedor_falso):
    from justica_mcp.pecas import ler_peca

    respostas, _, _ = reconhecedor_falso
    respostas[1] = ("", 0.0)
    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [""]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert lido["folhas_sem_texto"] == [1]
    assert "NAO significa que a peca esteja em branco" in lido["aviso"]
    assert "foto, assinatura, carimbo" in lido["aviso"]


def test_a_tsv_do_tesseract_vira_texto_e_confianca_ponderada():
    from justica_mcp.ocr import _texto_da_tsv

    cab = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    linhas = [
        cab,
        "5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t96\tProcesso",
        "5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t90\t0000001-86.2013.8.19.0078",
        "5\t1\t2\t1\t1\t1\t0\t0\t1\t1\t20\tx",
        "4\t1\t2\t1\t1\t0\t0\t0\t1\t1\t-1\t",
    ]
    texto, confianca, palavras = _texto_da_tsv("\n".join(linhas))
    assert texto == "Processo 0000001-86.2013.8.19.0078\n\nx"
    assert palavras == 3
    # O "x" de 20% quase nao pesa: a media fica perto das palavras longas.
    assert confianca > 88


def test_o_cache_fica_no_estado_e_nao_na_pasta_de_copias(tmp_path, monkeypatch,
                                                         ocr_ligado):
    """A pasta de copias e o acervo compartilhado no Google Drive. O cache do
    reconhecimento e desta maquina."""
    pasta = _pasta_com(tmp_path, monkeypatch, {"proc-pagina1-A.pdf": [""]})
    arquivo = pasta / "proc-pagina1-A.pdf"
    ocr_ligado._para_o_cache(arquivo, 1, {"texto": "t", "confianca": 1.0})
    assert ocr_ligado.do_cache(arquivo, 1)["texto"] == "t"
    assert sorted(p.name for p in pasta.iterdir()) == ["proc-pagina1-A.pdf"]
    assert any((tmp_path / "estado" / "ocr").iterdir())


def _ponta_a_ponta_disponivel():
    try:
        import PIL  # noqa: F401
        import pypdfium2  # noqa: F401
    except Exception:
        return False
    from justica_mcp import ocr

    import os
    anterior = os.environ.get("JUSTICA_OCR")
    os.environ["JUSTICA_OCR"] = "1"
    try:
        ocr._cache_disponibilidade = None
        return ocr.disponibilidade(renovar=True).pronto
    finally:
        if anterior is None:
            os.environ.pop("JUSTICA_OCR", None)
        else:
            os.environ["JUSTICA_OCR"] = anterior
        ocr._cache_disponibilidade = None


@pytest.mark.skipif(not _ponta_a_ponta_disponivel(),
                    reason="sem Tesseract com portugues, pypdfium2 ou Pillow")
def test_ponta_a_ponta_com_o_tesseract(tmp_path, monkeypatch, ocr_ligado):
    """Folha digitalizada de verdade: imagem, sem camada de texto."""
    from PIL import Image, ImageDraw, ImageFont

    from justica_mcp.pecas import ler_peca

    imagem = Image.new("L", (2480, 3508), 255)
    desenho = ImageDraw.Draw(imagem)
    try:
        fonte = ImageFont.truetype("DejaVuSerif.ttf", 60)
    except Exception:
        fonte = ImageFont.load_default(size=60)
    desenho.text((150, 300), "CERTIDÃO DE PUBLICAÇÃO", font=fonte, fill=0)
    desenho.text((150, 450), "Execução de cotas condominiais", font=fonte,
                 fill=0)
    pasta = tmp_path / "00000018620138190078"
    pasta.mkdir()
    imagem.save(pasta / "proc-pagina10-Certidao.pdf", resolution=300)
    from justica_mcp import pecas

    monkeypatch.setattr(pecas, "pasta_do_processo", lambda *a: pasta)
    lido = ler_peca(DIGITOS, FORMATADO, 10)
    assert lido["folhas_por_ocr"], lido
    assert "PUBLICAÇÃO" in lido["texto"]
    assert "Execução" in lido["texto"]
    # Segunda leitura vem do cache.
    de_novo = ler_peca(DIGITOS, FORMATADO, 10)
    assert de_novo["texto"] == lido["texto"]


def _com_pillow_e_pdfium():
    try:
        import PIL  # noqa: F401
        import pypdfium2  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _com_pillow_e_pdfium(), reason="sem Pillow ou pypdfium2")
def test_folha_escaneada_com_carimbo_do_pje_vai_ao_reconhecimento(
        tmp_path, monkeypatch, reconhecedor_falso):
    """No PDF do PJe toda folha escaneada traz o carimbo digital por cima, com
    umas 400 letras. Antes, essa folha passava por folha com texto e o
    conteudo da imagem nunca era lido."""
    import io

    from PIL import Image
    from pypdf import PdfReader, PdfWriter

    from justica_mcp.pecas import ler_peca
    from test_pecas import pdf_com_textos

    respostas, chamadas, _ = reconhecedor_falso
    respostas[1] = ("CONTRATO SOCIAL conteudo que so existe na imagem", 91.0)

    imagem = io.BytesIO()
    Image.new("L", (1275, 1650), 200).save(imagem, "PDF", resolution=150)
    folha = PdfReader(io.BytesIO(imagem.getvalue())).pages[0]
    carimbo = PdfReader(io.BytesIO(pdf_com_textos(
        ["Num. 123 - Pag. 1 Assinado eletronicamente por: FULANO DE TAL"]
    ))).pages[0]
    escritor = PdfWriter()
    escritor.add_page(folha)
    escritor.pages[0].merge_page(carimbo)
    pasta = tmp_path / "00000018620138190078"
    pasta.mkdir()
    with open(pasta / "proc-pagina5-Contrato.pdf", "wb") as saida:
        escritor.write(saida)
    from justica_mcp import pecas

    monkeypatch.setattr(pecas, "pasta_do_processo", lambda *a: pasta)
    lido = ler_peca(DIGITOS, FORMATADO, 5)
    assert chamadas == [1]
    assert "conteudo que so existe na imagem" in lido["texto"]
    assert lido["folhas_por_ocr"] == [{"folha": 1, "confianca": 91.0}]


def test_peticao_digital_nao_vai_ao_reconhecimento(tmp_path, monkeypatch,
                                                   reconhecedor_falso):
    """Folha de texto digital, sem imagem, nunca passa pelo reconhecimento:
    o texto digital e a leitura mais fiel que existe."""
    from justica_mcp.pecas import ler_peca

    respostas, chamadas, _ = reconhecedor_falso
    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1-Peticao.pdf": [
        "EXCELENTISSIMO SENHOR DOUTOR JUIZ, a autora vem requerer",
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1)
    assert chamadas == []
    assert lido["folhas_por_ocr"] == []
