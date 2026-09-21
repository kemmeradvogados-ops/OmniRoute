"""Comando `justica-credenciais`."""

import pytest

from justica_mcp.credenciais import _pares_esperados, _resolver


def test_pares_esperados_vem_do_registro_de_tribunais():
    """A banca declarou credencial para PJe, eproc e DCP no Rio, eproc em Sao
    Paulo e na Justica Federal, e PJe no Tribunal Regional do Trabalho."""
    chaves = {i.chave for i in _pares_esperados()}
    assert chaves == {
        "TJRJ:pje", "TJRJ:eproc", "TJRJ:dcp",
        "TJSP:eproc", "TJSP:esaj", "TRT1:pje", "TRF2:eproc",
    }


def test_resolver_aceita_par_previsto():
    assert _resolver("tjrj", "EPROC").chave == "TJRJ:eproc"


def test_esaj_de_sao_paulo_entrou_no_escopo():
    """Credencial fornecida em 21 de setembro de 2026. Cobre o acervo do
    Tribunal de Justica do Estado de Sao Paulo ainda nao migrado para o eproc."""
    assert _resolver("TJSP", "esaj").chave == "TJSP:esaj"


def test_resolver_recusa_par_fora_do_escopo():
    with pytest.raises(SystemExit, match="nao consta do escopo"):
        _resolver("TRT1", "eproc")


def test_resolver_recusa_tribunal_desconhecido():
    with pytest.raises(SystemExit):
        _resolver("TJMG", "pje")
