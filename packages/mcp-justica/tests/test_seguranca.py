"""A fronteira de somente leitura precisa ser estrutural, nao uma promessa."""

import pytest

from justica_mcp.core.capabilities import (
    MATRIZ, Capacidade, Declaracao, Situacao, adaptadores_para,
)
from justica_mcp.core.seguranca import FronteiraViolada, verificar_somente_leitura


def test_versao_1_sobe_somente_leitura():
    verificar_somente_leitura()


def test_habilitar_ciencia_por_engano_aborta_a_inicializacao(monkeypatch):
    """Dar ciencia consome prazo (lei nº. 11.419/06, artigo 5º, §3º).
    Se algum dia isso for declarado disponivel sem decisao expressa, o servidor
    deve se recusar a subir em vez de expor a ferramenta."""
    monkeypatch.setitem(
        MATRIZ["eproc"], Capacidade.DAR_CIENCIA_INTIMACAO,
        Declaracao(Situacao.DISPONIVEL, ""),
    )
    with pytest.raises(FronteiraViolada, match="somente leitura"):
        verificar_somente_leitura()


def test_nenhum_adaptador_da_ciencia_hoje():
    assert adaptadores_para(Capacidade.DAR_CIENCIA_INTIMACAO) == []


def test_busca_por_parte_nao_e_prometida_por_ninguem():
    """DataJud nao publica partes. Declarar isso evita que o agente invente
    uma explicacao quando a busca voltar vazia."""
    assert adaptadores_para(Capacidade.BUSCAR_POR_PARTE) == []


def test_integra_nao_e_prometida_na_fase_1():
    assert adaptadores_para(Capacidade.BAIXAR_INTEGRA) == []
