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


def test_chave_vazia_explicita_nao_cai_no_ambiente(monkeypatch):
    """Regressao encontrada em campo em 21 de setembro de 2026.

    Com a chave presente no ambiente, `chave=""` passava a usar a chave
    ambiente por causa do encadeamento com `or`. Quem passasse uma configuracao
    vazia esperando ficar sem chave acabava consultando com a chave de outro
    contexto, sem nenhum aviso.
    """
    monkeypatch.setenv("DATAJUD_API_KEY", "chave-do-ambiente")
    assert AdaptadorDataJud(chave="").configurado is False
    assert AdaptadorDataJud(chave="   ").configurado is False, "so espacos tambem e vazio"


def test_chave_none_le_do_ambiente(monkeypatch):
    """`None` continua significando 'leia do ambiente'."""
    monkeypatch.setenv("DATAJUD_API_KEY", "chave-do-ambiente")
    assert AdaptadorDataJud().configurado is True
    assert AdaptadorDataJud(chave=None).configurado is True


def test_sem_chave_no_ambiente_e_sem_argumento(monkeypatch):
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    assert AdaptadorDataJud().configurado is False


def test_chave_explicita_vence_o_ambiente(monkeypatch):
    monkeypatch.setenv("DATAJUD_API_KEY", "do-ambiente")
    a = AdaptadorDataJud(chave="explicita")
    assert a._cabecalhos()["Authorization"] == "APIKey explicita"


# ==========================================================================
# NAO_SUPORTADO fala da FONTE; NAO_IMPLEMENTADO fala deste projeto
#
# Confundir as duas e pior que nao ter matriz nenhuma: escrever NAO_SUPORTADO
# para dizer "nao pretendo construir" poe na boca do servidor uma afirmacao
# falsa sobre o tribunal, e o advogado deixa de procurar no portal uma coisa
# que esta la. Foi o que aconteceu com o DCP do Tribunal de Justica do Rio de
# Janeiro ate 06/10/2026, quando o operador confirmou que o portal baixa a
# integra do processo.
# ==========================================================================

def test_o_dcp_nao_declara_mais_que_o_portal_nao_baixa_a_integra():
    from justica_mcp.core.capabilities import Situacao, consultar

    decl = consultar("dcp", Capacidade.BAIXAR_INTEGRA)
    assert decl.situacao is not Situacao.NAO_SUPORTADO
    assert decl.situacao is Situacao.NAO_IMPLEMENTADO


def test_o_motivo_do_dcp_diz_que_falta_o_adaptador_e_nao_o_portal():
    from justica_mcp.core.capabilities import consultar

    motivo = consultar("dcp", Capacidade.BAIXAR_INTEGRA).motivo
    assert "o portal baixa a integra" in motivo.lower()
    assert "adaptador ainda nao foi escrito" in motivo


def test_o_que_a_fonte_realmente_nao_expoe_continua_nao_suportado():
    """A correcao do DCP nao afrouxa a matriz: o DataJud publica metadados e
    movimentos, e isso e desenho da fonte, nao falta de trabalho nosso."""
    from justica_mcp.core.capabilities import Situacao, consultar

    assert consultar("datajud", Capacidade.BAIXAR_INTEGRA).situacao is (
        Situacao.NAO_SUPORTADO)


def test_nenhuma_capacidade_do_dcp_ficou_sem_declaracao():
    from justica_mcp.core.capabilities import Situacao, consultar

    for capacidade in Capacidade:
        decl = consultar("dcp", capacidade)
        assert decl.situacao is Situacao.NAO_IMPLEMENTADO, capacidade
        assert decl.motivo, capacidade
