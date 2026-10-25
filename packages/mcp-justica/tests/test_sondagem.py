"""Sondagem em lote: uma autenticacao por sistema, e nunca um chute.

A sonda e injetada nos testes: nenhum portal e aberto aqui. O que se mede e a
ORDEM dos sistemas, a regra de parada, a economia de autenticacao e,
sobretudo, a recusa a escolher sozinho quando a resposta e ambigua.
"""

import tempfile
from pathlib import Path

import pytest

from justica_mcp.core.cnj import parse_numero
from justica_mcp.core.estado import Estado
from justica_mcp.core.sondagem import (
    ProcessosDeTribunaisDiferentes, sondar_em_lote,
)
from justica_mcp.core.tribunais import Sistema


@pytest.fixture
def estado():
    return Estado(Path(tempfile.mkdtemp()) / "estado.sqlite3")


def _num(txt):
    return parse_numero(txt, validar_digito=False)


UM = "0000001-88.2019.8.19.0001"
DOIS = "0000002-88.2019.8.19.0001"
TRES = "0000003-88.2019.8.19.0001"


def _sonda(mapa, registro=None):
    """Sonda falsa: `mapa` diz o que cada sistema responde por numero."""
    async def sonda(sistema, numeros):
        if registro is not None:
            registro.append((sistema.value, [n.apenas_digitos for n in numeros]))
        return {n.apenas_digitos: mapa.get(sistema.value, {}).get(n.formatado)
                for n in numeros}
    return sonda


async def test_todos_achados_no_eproc_custam_uma_autenticacao(estado):
    """A economia inteira do sondador esta aqui: sistema com fila vazia nao e
    aberto. Se tudo esta no mais novo, nao se autentica nos outros dois."""
    visitas: list = []
    relato = await sondar_em_lote(
        [_num(UM), _num(DOIS)], estado,
        _sonda({"eproc": {UM: True, DOIS: True}}, visitas),
    )
    assert relato["autenticacoes"] == 1
    assert relato["sistemas_abertos"] == ["eproc"]
    assert [v[0] for v in visitas] == ["eproc"]
    assert all(l["sistema"] == "eproc" for l in relato["linhas"])
    assert all(l["confianca"] == "alta" for l in relato["linhas"])


async def test_a_ordem_e_eproc_pje_dcp_e_a_fila_encolhe(estado):
    """Regra do operador: o mais novo primeiro, o DCP por ultimo, porque
    comecar pelo mais antigo acharia copia de processo ja migrado."""
    visitas: list = []
    await sondar_em_lote(
        [_num(UM), _num(DOIS), _num(TRES)], estado,
        _sonda({"eproc": {UM: True}, "pje": {DOIS: True}, "dcp": {TRES: True}},
               visitas),
    )
    assert [v[0] for v in visitas] == ["eproc", "pje", "dcp"]
    # Quem foi achado sai da fila do sistema seguinte.
    assert len(visitas[0][1]) == 3
    assert len(visitas[1][1]) == 2
    assert len(visitas[2][1]) == 1


async def test_achado_em_dois_sistemas_nao_e_escolhido_sozinho(estado):
    """Processo que aparece em dois sistemas e o caso em que errar custa caro.
    A resposta avisa e devolve a decisao ao advogado."""
    relato = await sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: True}, "dcp": {UM: True}}),
        conferir_segundo_grau=True,
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] is None
    assert linha["confianca"] == "media"
    assert "mais de um sistema" in linha["observacao"]
    assert relato["autenticacoes"] == 3


async def test_sem_conferir_segundo_grau_para_no_primeiro_achado(estado):
    relato = await sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: True}, "dcp": {UM: True}}),
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] == "pje"
    assert relato["sistemas_abertos"] == ["eproc", "pje"]
    # O achado no PJe avisa que pode haver segundo grau noutro sistema.
    assert "segundo grau" in linha["observacao"]


async def test_nao_consegui_ver_nao_vira_nao_existe(estado):
    """None e 'ninguem olhou'. Tratar como 'nao existe' faria o relatorio
    afirmar ausencia que ninguem conferiu, e processo dado como inexistente e
    prazo perdido."""
    relato = await sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: None}, "dcp": {UM: False}}),
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] is None
    assert linha["confianca"] == "baixa"
    assert "nao conseguiu responder" in linha["observacao"]
    assert "pje" in linha["observacao"]


async def test_nenhum_sistema_reconheceu_diz_isso_com_todas_as_letras(estado):
    relato = await sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: False}, "dcp": {UM: False}}),
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] is None
    assert "nenhum reconheceu" in linha["observacao"]
    assert "transcricao" in linha["observacao"]


async def test_tribunais_diferentes_na_mesma_varredura_sao_recusados(estado):
    with pytest.raises(ProcessosDeTribunaisDiferentes, match="um tribunal"):
        await sondar_em_lote(
            [_num(UM), _num("0000001-88.2019.8.26.0100")], estado, _sonda({}),
        )


async def test_o_resultado_confirmado_vai_para_o_cache_do_resolvedor(estado):
    """Sondado uma vez, resolvido para sempre dentro da validade: a proxima
    pergunta sobre este processo nao gasta autenticacao nenhuma."""
    from justica_mcp.core.resolver import resolver_sistema

    await sondar_em_lote([_num(UM)], estado, _sonda({"eproc": {UM: True}}))
    depois = await resolver_sistema(_num(UM), estado)
    assert depois.sistema == "eproc"
    assert depois.origem_da_resolucao == "cache"


async def test_lista_vazia_nao_abre_portal_nenhum(estado):
    relato = await sondar_em_lote([], estado, _sonda({}))
    assert relato["linhas"] == []
