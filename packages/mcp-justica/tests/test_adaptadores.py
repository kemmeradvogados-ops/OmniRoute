"""Adaptador recusa o que nao sabe fazer ANTES de gastar chamada de rede."""

import pytest

from justica_mcp.adapters import AdaptadorDataJud, AdaptadorDJEN
from justica_mcp.adapters.base import CapacidadeIndisponivel
from justica_mcp.core.capabilities import Capacidade


def test_datajud_recusa_busca_por_parte_com_motivo_e_sem_rede():
    with pytest.raises(CapacidadeIndisponivel) as exc:
        AdaptadorDataJud(chave="irrelevante").exigir_capacidade(Capacidade.BUSCAR_POR_PARTE)
    assert "Portaria nº. 160/2020" in str(exc.value)


def test_datajud_recusa_documentos():
    with pytest.raises(CapacidadeIndisponivel, match="nao expoe documentos"):
        AdaptadorDataJud(chave="x").exigir_capacidade(Capacidade.BAIXAR_INTEGRA)


def test_djen_aponta_o_adaptador_certo_para_andamentos():
    """Recusa util indica para onde ir, em vez de so negar."""
    with pytest.raises(CapacidadeIndisponivel) as exc:
        AdaptadorDJEN().exigir_capacidade(Capacidade.LISTAR_ANDAMENTOS)
    assert "datajud" in str(exc.value)


def test_djen_separa_publicacao_de_expediente_do_portal():
    """Distincao critica: ler o Diario nao dispara ciencia; abrir expediente dispara."""
    with pytest.raises(CapacidadeIndisponivel) as exc:
        AdaptadorDJEN().exigir_capacidade(Capacidade.LISTAR_INTIMACOES_PENDENTES)
    assert "NAO dispara ciencia" in str(exc.value)


def test_datajud_sem_chave_da_erro_acionavel():
    from justica_mcp.adapters.datajud import ChaveDataJudAusente

    a = AdaptadorDataJud(chave="")
    assert not a.configurado
    with pytest.raises(ChaveDataJudAusente, match="datajud-wiki.cnj.jus.br"):
        a._cabecalhos()


def test_chave_ausente_vira_erro_de_configuracao_nao_erro_interno():
    """Falta de configuracao e acionavel pelo operador; 'erro interno' esconderia isso."""
    import asyncio
    import json

    from justica_mcp.tools import _tratar
    from justica_mcp.adapters.datajud import ChaveDataJudAusente

    resposta = json.loads(_tratar(ChaveDataJudAusente()))
    assert resposta["codigo"] == "configuracao_ausente"
    assert "DATAJUD_API_KEY" in resposta["erro"]
