"""Configuracao do acesso autenticado."""

import pytest

from justica_mcp.core.acesso import (
    PortalNaoConfigurado, autenticado_habilitado, config_portal, portais_configurados,
)


def test_desligado_por_padrao(monkeypatch):
    """Ligar permite disparar autenticacao real no tribunal com a credencial do
    advogado. E decisao do operador, nao um comportamento herdado."""
    monkeypatch.delenv("JUSTICA_ACESSO_AUTENTICADO", raising=False)
    assert autenticado_habilitado() is False


@pytest.mark.parametrize("valor,esperado", [
    ("1", True), ("true", True), ("sim", True),
    ("0", False), ("nao", False), ("", False),
])
def test_leitura_do_interruptor(monkeypatch, valor, esperado):
    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", valor)
    assert autenticado_habilitado() is esperado


def test_endereco_do_portal_vem_do_ambiente(monkeypatch):
    """O agente nao deve precisar saber o endereco do portal, nem ter como
    apontar a autenticacao para outro lugar."""
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_URL", "https://eproc.exemplo/x")
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_PERFIL", "RJ168943")
    c = config_portal("trf2", "eproc")
    assert (c.tribunal, c.sistema, c.perfil) == ("TRF2", "eproc", "RJ168943")


def test_portal_sem_endereco_ensina_a_configurar(monkeypatch):
    monkeypatch.delenv("JUSTICA_PORTAL_TJRJ_PJE_URL", raising=False)
    with pytest.raises(PortalNaoConfigurado, match="JUSTICA_PORTAL_TJRJ_PJE_URL"):
        config_portal("TJRJ", "pje")


def test_perfil_ausente_vira_nulo(monkeypatch):
    monkeypatch.setenv("JUSTICA_PORTAL_TRT1_PJE_URL", "https://pje.exemplo")
    monkeypatch.delenv("JUSTICA_PORTAL_TRT1_PJE_PERFIL", raising=False)
    assert config_portal("TRT1", "pje").perfil is None


def test_listagem_nao_expoe_endereco_por_engano(monkeypatch):
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_URL", "https://eproc.exemplo/x")
    rotulos = [c.rotulo for c in portais_configurados()]
    assert "TRF2 / eproc" in rotulos
