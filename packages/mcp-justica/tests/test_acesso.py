"""Configuracao do acesso autenticado."""

import os

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
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_PERFIL", "RJ000111")
    c = config_portal("trf2", "eproc")
    assert (c.tribunal, c.sistema, c.perfil) == ("TRF2", "eproc", "RJ000111")


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


# --------------------------------------------------------------------------
# A chave de segundo grau nao pode virar um portal a parte
# --------------------------------------------------------------------------

def test_a_chave_de_segundo_grau_nao_inventa_um_portal(monkeypatch):
    """Em 26/10/2026, logo depois de a chave de segundo grau ser criada, a
    listagem do ambiente passou a mostrar um portal `TJRJ_EPROC / 2g`, que
    nao existe: a varredura parte a chave no ultimo sublinhado. A mesma funcao
    alimenta a lista de sistemas que a extensao mostra ao advogado, entao o
    fantasma nao era cosmetico."""
    from justica_mcp.core.acesso import portais_configurados, rotulos_no_ambiente

    for chave in list(os.environ):
        if chave.startswith("JUSTICA_PORTAL_"):
            monkeypatch.delenv(chave, raising=False)
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_EPROC_URL", "https://um/")
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_EPROC_2G_URL", "https://dois/")

    assert rotulos_no_ambiente() == ["TJRJ / eproc"]
    assert [c.rotulo for c in portais_configurados()] == ["TJRJ / eproc"]


def test_o_segundo_grau_continua_chegando_pela_configuracao(monkeypatch):
    """Nao basta sumir da listagem: ele tem que continuar sendo lido como o
    outro endereco do MESMO portal."""
    from justica_mcp.core.acesso import config_portal

    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_EPROC_URL", "https://um/")
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_EPROC_2G_URL", "https://dois/")
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_EPROC_PERFIL", "RJ000000")

    config = config_portal("TJRJ", "eproc")
    assert config.url_do_grau(1) == "https://um/"
    assert config.url_do_grau(2) == "https://dois/"
    # Sem perfil proprio de segundo grau, o do primeiro e reaproveitado.
    assert config.perfil_do_grau(2) == "RJ000000"


def test_sistema_sem_segundo_grau_devolve_nada_e_nao_o_primeiro(monkeypatch):
    """None aqui significa "nao da para procurar no segundo grau deste
    sistema", nunca "o processo nao esta la". Devolver o endereco do primeiro
    grau faria a varredura autenticar duas vezes no mesmo lugar."""
    from justica_mcp.core.acesso import config_portal

    monkeypatch.delenv("JUSTICA_PORTAL_TJRJ_PJE_2G_URL", raising=False)
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_URL", "https://um/")
    assert config_portal("TJRJ", "pje").url_do_grau(2) is None
