"""Acervo de copias, com indice de folhas.

Regra definida pelo operador em 21 de setembro de 2026:
    sem copia -> integra;  com copia -> complemento, informando as folhas.

A numeracao de folhas e a da COPIA DA BANCA, continua e crescente. Nao e a do
tribunal, que o eproc nem usa (la sao eventos). Serve para citar "fls. 245/250
da copia" e achar o documento.
"""

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from justica_mcp.core.acervo import (
    VARIAVEL_PASTA, Indice, Item, carregar_indice, contar_paginas,
    decidir_estrategia, garantir_pasta, maior_evento, numero_do_evento,
    pdfs_fora_do_indice,
)


def _pdf(destino: Path, paginas: int) -> Path:
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=595, height=842)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as arquivo:
        escritor.write(arquivo)
    return destino


def _evento(numero, docs=()):
    return {"evento": str(numero), "descricao": f"Evento {numero}",
            "documentos": [{"rotulo": r, "endereco": f"/doc/{r}"} for r in docs]}


# ---------------- contagem de folhas ----------------

def test_conta_paginas_de_pdf(tmp_path):
    assert contar_paginas(_pdf(tmp_path / "a.pdf", 12)) == 12


def test_nao_inventa_contagem_para_o_que_nao_e_pdf(tmp_path):
    """Sem contagem confiavel o indice registra a ausencia: folha errada em
    citacao e pior que folha ausente."""
    arquivo = tmp_path / "a.html"
    arquivo.write_text("<html>", encoding="utf-8")
    assert contar_paginas(arquivo) is None


def test_pdf_corrompido_nao_quebra(tmp_path):
    arquivo = tmp_path / "a.pdf"
    arquivo.write_bytes(b"nao e um pdf")
    assert contar_paginas(arquivo) is None


# ---------------- numeracao continua ----------------

def test_folhas_seguem_de_onde_a_anterior_parou(tmp_path):
    indice = Indice(numero="x", pasta=tmp_path)
    primeiro = indice.acrescentar(_pdf(tmp_path / "a.pdf", 240), "integra", evento_ate=69)
    segundo = indice.acrescentar(_pdf(tmp_path / "b.pdf", 7), "documento", evento="70", rotulo="P")
    assert (primeiro.folha_inicial, primeiro.folha_final) == (1, 240)
    assert (segundo.folha_inicial, segundo.folha_final) == (241, 247)
    assert indice.ultima_folha == 247


def test_faixa_legivel_para_citacao(tmp_path):
    indice = Indice(numero="x", pasta=tmp_path)
    assert indice.acrescentar(_pdf(tmp_path / "a.pdf", 240), "integra").faixa() == "fls. 1/240"
    assert indice.acrescentar(_pdf(tmp_path / "b.pdf", 1), "documento").faixa() == "fl. 241"


def test_item_sem_contagem_nao_ocupa_folhas(tmp_path):
    indice = Indice(numero="x", pasta=tmp_path)
    arquivo = tmp_path / "a.html"
    arquivo.write_text("<html>", encoding="utf-8")
    item = indice.acrescentar(arquivo, "documento")
    assert item.folha_inicial is None and "nao contadas" in item.faixa()


# ---------------- estrategia ----------------

def test_sem_copia_pede_integra(tmp_path):
    e = decidir_estrategia(Indice(numero="x", pasta=tmp_path), [_evento(1, ["A"])])
    assert e["acao"] == "integra"


def test_complemento_ignora_o_que_a_integra_ja_cobre(tmp_path):
    """Sem este filtro o complemento recopiaria o processo inteiro a cada
    consulta, porque a integra contem os documentos dos eventos anteriores."""
    indice = Indice(numero="x", pasta=tmp_path)
    indice.acrescentar(_pdf(tmp_path / "i.pdf", 240), "integra", evento_ate=69)
    eventos = [_evento(70, ["NOVO"]), _evento(69, ["ANTIGO"]), _evento(1, ["INICIAL"])]
    e = decidir_estrategia(indice, eventos)
    assert e["acao"] == "complemento"
    assert [f["documento"]["rotulo"] for f in e["faltantes"]] == ["NOVO"]


def test_nada_novo_desde_a_integra(tmp_path):
    indice = Indice(numero="x", pasta=tmp_path)
    indice.acrescentar(_pdf(tmp_path / "i.pdf", 10), "integra", evento_ate=69)
    e = decidir_estrategia(indice, [_evento(69, ["A"]), _evento(68, ["B"])])
    assert e["faltantes"] == [] and "Nada novo" in e["motivo"]


def test_complemento_nao_repete_complemento_anterior(tmp_path):
    indice = Indice(numero="x", pasta=tmp_path)
    indice.acrescentar(_pdf(tmp_path / "i.pdf", 10), "integra", evento_ate=69)
    indice.acrescentar(_pdf(tmp_path / "d.pdf", 5), "documento", evento="70", rotulo="NOVO")
    e = decidir_estrategia(indice, [_evento(70, ["NOVO"])])
    assert e["faltantes"] == []


def test_motivo_informa_folha_e_alcance(tmp_path):
    indice = Indice(numero="x", pasta=tmp_path)
    indice.acrescentar(_pdf(tmp_path / "i.pdf", 240), "integra", evento_ate=69)
    e = decidir_estrategia(indice, [_evento(70, ["A"])])
    assert "folha 240" in e["motivo"] and "evento 69" in e["motivo"]


# ---------------- numeros de evento ----------------

@pytest.mark.parametrize("bruto,esperado", [
    ("70", 70), (" 8 ", 8), ("", None), ("7-A", None), (None, None),
])
def test_leitura_do_numero_do_evento(bruto, esperado):
    assert numero_do_evento({"evento": bruto}) == esperado


def test_maior_evento_ignora_nao_numericos():
    assert maior_evento([_evento(70), _evento("x"), _evento(69)]) == 70


def test_maior_evento_de_lista_vazia():
    assert maior_evento([]) == 0


# ---------------- persistencia ----------------

def test_indice_sobrevive_entre_consultas(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTICA_PASTA_COPIAS", str(tmp_path))
    indice = carregar_indice("12345", "1-2.3.4.5.6")
    indice.acrescentar(_pdf(tmp_path / "12345" / "i.pdf", 240), "integra", evento_ate=69)
    indice.gravar()

    relido = carregar_indice("12345", "1-2.3.4.5.6")
    assert relido.ultima_folha == 240
    assert relido.evento_coberto_pela_integra == 69
    assert relido.tem_integra is True


def test_indice_corrompido_nao_trava_a_copia(tmp_path, monkeypatch):
    """Indice ilegivel nao pode impedir o trabalho: segue como vazio e a
    gravacao o refaz."""
    monkeypatch.setenv("JUSTICA_PASTA_COPIAS", str(tmp_path))
    pasta = tmp_path / "12345"
    pasta.mkdir(parents=True)
    (pasta / "indice.json").write_text("{ isso nao e json", encoding="utf-8")
    assert carregar_indice("12345", "x").vazio is True


def test_gravacao_registra_o_total_de_folhas(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTICA_PASTA_COPIAS", str(tmp_path))
    indice = carregar_indice("999", "x")
    indice.acrescentar(_pdf(tmp_path / "999" / "a.pdf", 12), "integra", evento_ate=3)
    destino = indice.gravar()
    assert json.loads(destino.read_text(encoding="utf-8"))["folhas_totais"] == 12


# --------------------------------------------------------------------------
# Pasta do processo
# --------------------------------------------------------------------------

def test_cria_a_pasta_do_processo_quando_nao_existe(tmp_path, monkeypatch):
    """A pasta so nascia ao gravar o primeiro arquivo. Uma consulta que nao
    copiasse nada nao deixava pasta nenhuma, e o advogado procuraria no Drive
    um lugar que nunca foi criado."""
    monkeypatch.setenv(VARIAVEL_PASTA, str(tmp_path))
    pasta = garantir_pasta("50684566820254025101")
    assert pasta.is_dir()
    assert pasta.name == "50684566820254025101"
    assert pasta.parent == tmp_path


def test_criar_a_pasta_duas_vezes_nao_quebra_nem_apaga(tmp_path, monkeypatch):
    monkeypatch.setenv(VARIAVEL_PASTA, str(tmp_path))
    pasta = garantir_pasta("123")
    (pasta / "ja-existia.pdf").write_bytes(b"x")
    assert garantir_pasta("123") == pasta
    assert (pasta / "ja-existia.pdf").is_file()


def test_pdf_solto_na_pasta_e_sinalizado(tmp_path, monkeypatch):
    """A pasta de copias e do escritorio e pode ja conter copias baixadas a
    mao. Elas nao contam como copia, porque nao ha como saber o que cobrem,
    mas o advogado precisa ser avisado de que estao ali."""
    monkeypatch.setenv(VARIAVEL_PASTA, str(tmp_path))
    pasta = garantir_pasta("123")
    (pasta / "peticao-do-estagiario.pdf").write_bytes(b"x")
    (pasta / "anotacoes.txt").write_bytes(b"x")
    indice = carregar_indice("123", "0000123-00.0000.0.00.0000")
    assert pdfs_fora_do_indice(indice) == ["peticao-do-estagiario.pdf"]


def test_arquivo_ja_no_indice_nao_e_sinalizado(tmp_path, monkeypatch):
    monkeypatch.setenv(VARIAVEL_PASTA, str(tmp_path))
    pasta = garantir_pasta("123")
    arquivo = pasta / "ev0070-DESP70.pdf"
    arquivo.write_bytes(b"x")
    indice = carregar_indice("123", "0000123-00.0000.0.00.0000")
    indice.acrescentar(arquivo, "documento", evento="70", rotulo="DESP70")
    assert pdfs_fora_do_indice(indice) == []


def test_pasta_inexistente_nao_quebra_a_varredura(tmp_path, monkeypatch):
    monkeypatch.setenv(VARIAVEL_PASTA, str(tmp_path / "nunca-criada"))
    indice = carregar_indice("123", "0000123-00.0000.0.00.0000")
    assert pdfs_fora_do_indice(indice) == []


# --------------------------------------------------------------------------
# Copia repetida nao pode virar folha nova
#
# Em 22/09/2026 a integra do mesmo processo entrou duas vezes, e a segunda foi
# numerada como fls. 115/228: o acervo passou a dizer que o processo tem 228
# folhas quando tem 114. Folha errada em citacao e o pior defeito possivel
# neste indice: o advogado cita "fls. 245/250 da copia" e o juiz procura no
# lugar que nao existe.
# --------------------------------------------------------------------------

def _pdf_marcado(caminho, paginas=1, marca="manha"):
    """Como `_pdf`, mas com marca no conteudo: dois PDFs de mesmo tamanho e
    conteudo diferente, que e o caso que o portal produz ao regerar a integra
    com outra data de geracao dentro do arquivo."""
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=595, height=842)
    escritor.add_metadata({"/Producer": marca})
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "wb") as saida:
        escritor.write(saida)
    return caminho


def test_arquivo_identico_e_reconhecido_como_repeticao(tmp_path):
    from justica_mcp.core.acervo import REPETIDA_IGUAL, Indice

    indice = Indice(numero="1", pasta=tmp_path)
    primeiro = _pdf(tmp_path / "integra-a.pdf", 3)
    indice.acrescentar(primeiro, "integra")

    import shutil

    segundo = tmp_path / "integra-b.pdf"
    shutil.copyfile(primeiro, segundo)

    veredicto, gemeo = indice.avaliar_repeticao(segundo)
    assert veredicto == REPETIDA_IGUAL
    assert gemeo.arquivo == str(primeiro)


def test_integra_com_o_mesmo_numero_de_paginas_vira_suspeita_e_nao_certeza(tmp_path):
    """O portal escreve a data de geracao dentro do PDF, entao a mesma copia
    pode ter conteudo diferente. Decidir sozinho aqui seria concluir demais."""
    from justica_mcp.core.acervo import REPETIDA_SUSPEITA, Indice

    indice = Indice(numero="1", pasta=tmp_path)
    indice.acrescentar(_pdf_marcado(tmp_path / "integra-a.pdf", 3, "manha"), "integra")
    outro = _pdf_marcado(tmp_path / "integra-b.pdf", 3, "tarde")

    veredicto, gemeo = indice.avaliar_repeticao(outro)
    assert veredicto == REPETIDA_SUSPEITA
    assert gemeo is not None


def test_copia_realmente_nova_passa(tmp_path):
    from justica_mcp.core.acervo import NOVA, Indice

    indice = Indice(numero="1", pasta=tmp_path)
    indice.acrescentar(_pdf(tmp_path / "integra.pdf", 3), "integra")
    veredicto, gemeo = indice.avaliar_repeticao(_pdf(tmp_path / "novo.pdf", 5))
    assert veredicto == NOVA
    assert gemeo is None


def test_indice_vazio_nao_ve_repeticao_em_lugar_nenhum(tmp_path):
    from justica_mcp.core.acervo import NOVA, Indice

    indice = Indice(numero="1", pasta=tmp_path)
    veredicto, _ = indice.avaliar_repeticao(_pdf(tmp_path / "integra.pdf", 1))
    assert veredicto == NOVA


def test_indice_antigo_sem_impressao_continua_carregando(tmp_path):
    """Indices gravados antes desta mudanca nao tem o campo. Quebrar na leitura
    apagaria o historico de folhas ja citadas."""
    import json

    from justica_mcp.core.acervo import NOME_INDICE, carregar_indice, pasta_do_processo

    pasta = pasta_do_processo("123")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / NOME_INDICE).write_text(json.dumps({
        "numero": "1", "itens": [
            {"tipo": "integra", "arquivo": "x.pdf", "em": "2026-09-21T00:00:00+00:00",
             "paginas": 114, "folha_inicial": 1, "folha_final": 114},
        ],
    }), encoding="utf-8")
    indice = carregar_indice("123", "1")
    assert indice.ultima_folha == 114
    assert indice.itens[0].impressao is None


def test_a_impressao_e_gravada_para_as_copias_novas(tmp_path):
    from justica_mcp.core.acervo import Indice

    indice = Indice(numero="1", pasta=tmp_path)
    item = indice.acrescentar(_pdf(tmp_path / "integra.pdf", 1), "integra")
    assert item.impressao and len(item.impressao) == 64
