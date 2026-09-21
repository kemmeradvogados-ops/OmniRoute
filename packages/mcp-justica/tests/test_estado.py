"""Cache, snapshots e auditoria."""

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

from justica_mcp.core.estado import Estado
from justica_mcp.core.resiliencia import (
    Disjuntor, EstadoDisjuntor, PortalIndisponivel,
)


@pytest.fixture
def estado():
    return Estado(Path(tempfile.mkdtemp()) / "estado.sqlite3")


def test_cache_vencido_volta_marcado_em_vez_de_sumir(estado):
    """Sumir em silencio faria o agente tratar dado velho como ausente."""
    estado.gravar_cache("k", {"a": 1}, timedelta(seconds=-1))
    registro = estado.obter_cache("k")
    assert registro is not None and registro["vencido"] is True


def test_snapshot_nao_duplica_quando_nada_mudou(estado):
    assert estado.gravar_snapshot("P", [{"m": 1}])["mudou"] is True
    assert estado.gravar_snapshot("P", [{"m": 1}])["mudou"] is False
    assert estado.gravar_snapshot("P", [{"m": 1}, {"m": 2}])["mudou"] is True


def test_diferenca_identifica_movimento_novo(estado):
    estado.gravar_snapshot("P", [{"data_hora": "2026-09-01", "codigo": 1, "nome": "a"}])
    anterior = estado.ultimo_snapshot("P")
    atuais = [
        {"data_hora": "2026-09-10", "codigo": 2, "nome": "b"},
        {"data_hora": "2026-09-01", "codigo": 1, "nome": "a"},
    ]
    vistos = {(m["data_hora"], m["codigo"], m["nome"]) for m in anterior["conteudo"]}
    novos = [m for m in atuais if (m["data_hora"], m["codigo"], m["nome"]) not in vistos]
    assert len(novos) == 1 and novos[0]["codigo"] == 2


def test_auditoria_registra_chamada(estado):
    estado.registrar(acao="consultar_processo", tribunal="TJRJ", numero="X", resultado="ok")
    registros = estado.auditoria_recente()
    assert len(registros) == 1 and registros[0]["acao"] == "consultar_processo"


def test_disjuntor_abre_e_recupera_sozinho():
    """Recuperacao preguicosa: ler o estado promove ABERTO para MEIO_ABERTO."""
    d = Disjuntor("portal", limite_falhas=2, espera_segundos=0.0)
    d.registrar_falha()
    d.registrar_falha()
    assert d.estado is EstadoDisjuntor.MEIO_ABERTO
    d.registrar_sucesso()
    assert d.estado is EstadoDisjuntor.FECHADO


def test_disjuntor_bloqueia_insistencia():
    d = Disjuntor("portal", limite_falhas=1, espera_segundos=60.0)
    d.registrar_falha()
    with pytest.raises(PortalIndisponivel, match="Nao insista"):
        d.exigir_passagem()
