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
    Indice, Item, carregar_indice, contar_paginas, decidir_estrategia,
    maior_evento, numero_do_evento,
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
