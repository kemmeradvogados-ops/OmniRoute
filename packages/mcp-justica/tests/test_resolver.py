"""O resolvedor nao pode chutar: quando nao sabe, precisa dizer que nao sabe."""

import tempfile
from pathlib import Path

import pytest

from justica_mcp.core.cnj import parse_numero
from justica_mcp.core.estado import Estado
from justica_mcp.core.resolver import resolver_sistema
from justica_mcp.core.tribunais import TribunalForaDoEscopo, identificar_tribunal


@pytest.fixture
def estado():
    return Estado(Path(tempfile.mkdtemp()) / "estado.sqlite3")


def _num(txt):
    return parse_numero(txt, validar_digito=False)


def test_tribunal_e_deterministico():
    assert identificar_tribunal("8.19").codigo == "TJRJ"
    assert identificar_tribunal("8.26").codigo == "TJSP"
    assert identificar_tribunal("5.01").codigo == "TRT1"
    assert identificar_tribunal("4.02").codigo == "TRF2"


def test_tribunal_fora_do_escopo_explica_a_recusa():
    with pytest.raises(TribunalForaDoEscopo, match="fora do escopo"):
        identificar_tribunal("8.13")


async def test_acervo_antigo_do_tjrj_fica_indeterminado(estado):
    """Sem sonda autenticada, processo de 2019 no Rio pode estar em PJe ou DCP.
    Responder 'eproc' ali seria chute com cara de resposta."""
    r = await resolver_sistema(_num("0000001-88.2019.8.19.0001"), estado)
    assert r.sistema == "indeterminado"
    assert r.origem_da_resolucao == "indeterminado"
    assert r.confianca.value == "baixa"
    assert r.candidatos == ["eproc", "pje", "dcp"]


async def test_distribuicao_nova_no_tjrj_usa_pista_de_migracao(estado):
    r = await resolver_sistema(_num("0000001-69.2026.8.19.0001"), estado)
    assert r.sistema == "eproc"
    assert r.origem_da_resolucao == "regra_migracao"
    # Pista nunca vira certeza.
    assert r.confianca.value != "alta"
    assert "nao confirmacao" in (r.motivo or "")


async def test_segunda_consulta_vem_do_cache_com_validade_declarada(estado):
    numero = _num("0000001-69.2026.8.19.0001")
    await resolver_sistema(numero, estado)
    r = await resolver_sistema(numero, estado)
    assert r.origem_da_resolucao == "cache"
    assert r.valido_ate, "cache sem validade envelheceria em silencio"


async def test_sondagem_tem_prioridade_sobre_regra_de_migracao(estado, monkeypatch):
    """Quando a Fase 2 registrar sondas, a evidencia deve vencer a heuristica."""
    from justica_mcp.core import resolver as mod
    from justica_mcp.core.tribunais import Sistema

    async def sonda_pje(_numero):
        return True

    monkeypatch.setitem(mod._SONDAS, ("TJRJ", Sistema.PJE), sonda_pje)
    r = await resolver_sistema(_num("0000001-69.2026.8.19.0001"), estado, ignorar_cache=True)
    assert r.sistema == "pje"
    assert r.origem_da_resolucao == "sondagem"
    assert r.confianca.value == "alta"
