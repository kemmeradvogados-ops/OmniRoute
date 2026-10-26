"""Historico da banca: a sondagem que um advogado pagou serve a todos.

Todos os testes apontam `JUSTICA_PASTA_COPIAS` para uma pasta temporaria: o
historico de verdade mora no Google Drive do escritorio e nenhum teste pode
encostar nele.
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from justica_mcp.core import historico_sistemas as hist
from justica_mcp.core.cnj import parse_numero
from justica_mcp.core.estado import Estado

UM = "0000001-88.2019.8.19.0001"
DOIS = "0000002-88.2019.8.19.0001"


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTICA_PASTA_COPIAS", str(tmp_path))
    return tmp_path


def _num(txt):
    return parse_numero(txt, validar_digito=False)


def test_sem_arquivo_o_historico_e_vazio_e_nao_levanta(pasta):
    assert hist.consultar("00000018820198190001") is None
    assert hist.listar() == []


def test_grava_e_le_de_volta(pasta):
    n = _num(UM)
    hist.registrar(n.apenas_digitos, n.formatado, "dcp",
                   origem="sondagem no portal", por="fulano")
    guardado = hist.consultar(n.apenas_digitos)
    assert guardado["sistema"] == "dcp"
    assert guardado["origem"] == "sondagem no portal"
    assert hist.recente(guardado) is True
    assert (pasta / "sistemas.json").is_file()


def test_gravar_o_segundo_nao_apaga_o_primeiro(pasta):
    """A pasta e compartilhada: dois advogados sondam no mesmo dia."""
    a, b = _num(UM), _num(DOIS)
    hist.registrar(a.apenas_digitos, a.formatado, "dcp", origem="sondagem")
    hist.registrar(b.apenas_digitos, b.formatado, "pje", origem="sondagem")
    assert hist.consultar(a.apenas_digitos)["sistema"] == "dcp"
    assert hist.consultar(b.apenas_digitos)["sistema"] == "pje"
    assert len(hist.listar()) == 2


def test_arquivo_corrompido_nao_derruba_a_consulta(pasta):
    """O historico e uma economia, nao um requisito. Se ele quebrar, a
    consulta volta a custar uma tentativa; se ele derrubar a consulta, o
    advogado fica sem o processo, que e pior."""
    (pasta / "sistemas.json").write_text("{isto nao e json", encoding="utf-8")
    assert hist.consultar("00000018820198190001") is None
    assert hist.listar() == []


def test_confirmacao_antiga_nao_passa_por_recente(pasta):
    n = _num(UM)
    hist.registrar(n.apenas_digitos, n.formatado, "dcp", origem="sondagem")
    arquivo = pasta / "sistemas.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    velho = datetime.now(timezone.utc) - timedelta(days=hist.DIAS_RECENTE + 5)
    dados["processos"][n.apenas_digitos]["confirmado_em"] = velho.isoformat()
    arquivo.write_text(json.dumps(dados), encoding="utf-8")

    guardado = hist.consultar(n.apenas_digitos)
    assert hist.recente(guardado) is False
    assert hist.dias_desde(guardado) >= hist.DIAS_RECENTE


def test_esquecer_tira_o_registro_e_guarda_o_motivo(pasta):
    """Chamado quando o processo NAO esta mais onde o historico dizia:
    manter o registro mandaria o proximo advogado ao portal errado."""
    n = _num(UM)
    hist.registrar(n.apenas_digitos, n.formatado, "dcp", origem="sondagem")
    assert hist.esquecer(n.apenas_digitos, "nao achado no dcp em nova consulta")
    assert hist.consultar(n.apenas_digitos) is None
    dados = json.loads((pasta / "sistemas.json").read_text(encoding="utf-8"))
    assert dados["desfeitos"][0]["motivo"].startswith("nao achado")
    assert hist.esquecer(n.apenas_digitos, "de novo") is False


# --------------------------------------------------------------------------
# O encaixe no resolvedor
# --------------------------------------------------------------------------

async def test_o_resolvedor_usa_o_historico_antes_de_sondar(pasta, tmp_path):
    from justica_mcp.core.resolver import resolver_sistema

    n = _num(UM)
    hist.registrar(n.apenas_digitos, n.formatado, "dcp", origem="sondagem")
    estado = Estado(tmp_path / "estado.sqlite3")
    r = await resolver_sistema(n, estado)
    assert r.sistema == "dcp"
    assert r.origem_da_resolucao == "historico_da_banca"
    assert r.confianca.value == "media"
    assert "confirmou" in r.motivo


async def test_historico_antigo_responde_com_confianca_baixa_e_ressalva(
        pasta, tmp_path):
    from justica_mcp.core.resolver import resolver_sistema

    n = _num(UM)
    hist.registrar(n.apenas_digitos, n.formatado, "dcp", origem="sondagem")
    arquivo = pasta / "sistemas.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    velho = datetime.now(timezone.utc) - timedelta(days=hist.DIAS_RECENTE + 5)
    dados["processos"][n.apenas_digitos]["confirmado_em"] = velho.isoformat()
    arquivo.write_text(json.dumps(dados), encoding="utf-8")

    estado = Estado(tmp_path / "estado.sqlite3")
    r = await resolver_sistema(n, estado)
    assert r.confianca.value == "baixa"
    assert "pode ter migrado" in r.motivo


async def test_a_sondagem_alimenta_o_historico_da_banca(pasta, tmp_path):
    """E o ponto inteiro: a tentativa que um advogado gastou nao e gasta de
    novo por ninguem."""
    from justica_mcp.core.sondagem import sondar_em_lote

    async def sonda(sistema, numeros):
        return {n.apenas_digitos: sistema.value == "eproc" for n in numeros}

    n = _num(UM)
    estado = Estado(tmp_path / "estado.sqlite3")
    await sondar_em_lote([n], estado, sonda)
    guardado = hist.consultar(n.apenas_digitos)
    assert guardado["sistema"] == "eproc"
    assert guardado["origem"] == "sondagem no portal"


def test_a_suite_nunca_aponta_para_a_pasta_de_copias_de_verdade():
    """Guarda do proprio conserto: se o `_acervo_isolado` do conftest sumir,
    este teste cai antes de algum teste escrever na pasta do Google Drive
    compartilhada do escritorio."""
    import os

    from justica_mcp.core.acervo import pasta_de_copias

    apontada = os.environ.get("JUSTICA_PASTA_COPIAS", "")
    assert apontada, "JUSTICA_PASTA_COPIAS nao esta apontada para pasta de teste"
    assert "acervo-de-teste" in apontada or "tmp" in apontada.lower()
    assert str(pasta_de_copias()) == apontada
