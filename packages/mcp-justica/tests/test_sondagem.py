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
    LinhaDaSondagem,
    ProcessosDeTribunaisDiferentes,
    _conclusao,
    sondar_em_lote,
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
    def sonda(sistema, grau, numeros):
        if registro is not None:
            registro.append((sistema.value, [n.apenas_digitos for n in numeros]))
        return {n.apenas_digitos: mapa.get(sistema.value, {}).get(n.formatado)
                for n in numeros}
    return sonda


def test_todos_achados_no_eproc_custam_uma_autenticacao(estado):
    """A economia inteira do sondador esta aqui: sistema com fila vazia nao e
    aberto. Se tudo esta no mais novo, nao se autentica nos outros dois."""
    visitas: list = []
    relato = sondar_em_lote(
        [_num(UM), _num(DOIS)], estado,
        _sonda({"eproc": {UM: True, DOIS: True}}, visitas),
    )
    assert relato["autenticacoes"] == 1
    assert relato["sistemas_abertos"] == ["eproc 1g"]
    assert [v[0] for v in visitas] == ["eproc"]
    assert all(l["sistema"] == "eproc" for l in relato["linhas"])
    assert all(l["confianca"] == "alta" for l in relato["linhas"])


def test_a_ordem_e_eproc_pje_dcp_e_a_fila_encolhe(estado):
    """Regra do operador: o mais novo primeiro, o DCP por ultimo, porque
    comecar pelo mais antigo acharia copia de processo ja migrado."""
    visitas: list = []
    sondar_em_lote(
        [_num(UM), _num(DOIS), _num(TRES)], estado,
        _sonda({"eproc": {UM: True}, "pje": {DOIS: True}, "dcp": {TRES: True}},
               visitas),
    )
    assert [v[0] for v in visitas] == ["eproc", "pje", "dcp"]
    # Quem foi achado sai da fila do sistema seguinte.
    assert len(visitas[0][1]) == 3
    assert len(visitas[1][1]) == 2
    assert len(visitas[2][1]) == 1


def test_achado_em_dois_sistemas_nao_e_escolhido_sozinho(estado):
    """Processo que aparece em dois sistemas e o caso em que errar custa caro.
    A resposta avisa e devolve a decisao ao advogado."""
    relato = sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: True}, "dcp": {UM: True}}),
        conferir_segundo_grau=True,
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] is None
    assert linha["confianca"] == "media"
    assert "mais de um sistema" in linha["observacao"]
    assert relato["autenticacoes"] == 3


def test_sem_conferir_segundo_grau_para_no_primeiro_achado(estado):
    relato = sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: True}, "dcp": {UM: True}}),
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] == "pje"
    # Nome por extenso, nao a chave interna: esta lista vai para o relato
    # que uma pessoa le.
    assert relato["sistemas_abertos"] == [
        "eproc 1g", "Processo Judicial Eletronico 1g",
    ]
    # O achado no PJe avisa que pode haver segundo grau noutro sistema.
    assert "segundo grau" in linha["observacao"]


def test_nao_consegui_ver_nao_vira_nao_existe(estado):
    """None e 'ninguem olhou'. Tratar como 'nao existe' faria o relatorio
    afirmar ausencia que ninguem conferiu, e processo dado como inexistente e
    prazo perdido."""
    relato = sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: None}, "dcp": {UM: False}}),
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] is None
    assert linha["confianca"] == "baixa"
    assert "nao conseguiu responder" in linha["observacao"]
    assert "Processo Judicial Eletronico" in linha["observacao"]


def test_nenhum_sistema_reconheceu_diz_isso_com_todas_as_letras(estado):
    relato = sondar_em_lote(
        [_num(UM)], estado,
        _sonda({"eproc": {UM: False}, "pje": {UM: False}, "dcp": {UM: False}}),
    )
    linha = relato["linhas"][0]
    assert linha["sistema"] is None
    assert "nenhum reconheceu" in linha["observacao"]
    assert "transcricao" in linha["observacao"]


def test_tribunais_diferentes_na_mesma_varredura_sao_recusados(estado):
    with pytest.raises(ProcessosDeTribunaisDiferentes, match="um tribunal"):
        sondar_em_lote(
            [_num(UM), _num("0000001-88.2019.8.26.0100")], estado, _sonda({}),
        )


async def test_o_resultado_confirmado_vai_para_o_cache_do_resolvedor(estado):
    """Sondado uma vez, resolvido para sempre dentro da validade: a proxima
    pergunta sobre este processo nao gasta autenticacao nenhuma."""
    from justica_mcp.core.resolver import resolver_sistema

    sondar_em_lote([_num(UM)], estado, _sonda({"eproc": {UM: True}}))
    depois = await resolver_sistema(_num(UM), estado)
    assert depois.sistema == "eproc"
    assert depois.origem_da_resolucao == "cache"


def test_lista_vazia_nao_abre_portal_nenhum(estado):
    relato = sondar_em_lote([], estado, _sonda({}))
    assert relato["linhas"] == []


# --------------------------------------------------------------------------
# Nome interno nao vaza para texto que uma PESSOA le.
#
# Em 26/10/2026 o relatorio do resolvedor devolveu "DCP" ao advogado, que
# perguntou o que era. A chave interna e `dcp`; o nome do sistema e Portal de
# Servicos. Este teste existe para que a proxima chave nova nao repita isso.

from justica_mcp.core.tribunais import NOME_DO_SISTEMA, Sistema, nome_do_sistema


def test_todo_sistema_tem_nome_por_extenso():
    for sistema in Sistema:
        assert sistema.value in NOME_DO_SISTEMA, (
            f"o sistema {sistema.value} nao tem nome para pessoa ler"
        )


def test_nome_aceita_enum_e_string():
    assert nome_do_sistema(Sistema.DCP) == "Portal de Servicos"
    assert nome_do_sistema("dcp") == "Portal de Servicos"
    assert nome_do_sistema("pje") == "Processo Judicial Eletronico"


def test_desconhecido_volta_como_veio():
    # Some com a informacao seria pior que devolver um nome feio.
    assert nome_do_sistema("sistema_que_nao_existe") == "sistema_que_nao_existe"


def test_observacao_da_sondagem_usa_o_nome_e_nao_a_chave():
    linha = LinhaDaSondagem(numero="0000001-88.2019.8.19.0001")
    linha.por_sistema = {"dcp": True}
    _conclusao(linha, ["dcp"], conferiu_tudo=True)
    assert "Portal de Servicos" in linha.observacao
    assert "dcp" not in linha.observacao


def test_observacao_de_sistema_cego_tambem_usa_o_nome():
    linha = LinhaDaSondagem(numero="0000001-88.2019.8.19.0001")
    linha.por_sistema = {"dcp": None, "eproc": False}
    _conclusao(linha, ["eproc", "dcp"], conferiu_tudo=True)
    assert "Portal de Servicos" in linha.observacao
    assert "dcp" not in linha.observacao


def test_observacao_de_varios_achados_tambem_usa_o_nome():
    linha = LinhaDaSondagem(numero="0000001-88.2019.8.19.0001")
    linha.por_sistema = {"dcp": True, "pje": True}
    _conclusao(linha, ["pje", "dcp"], conferiu_tudo=True)
    assert "Portal de Servicos" in linha.observacao
    assert "Processo Judicial Eletronico" in linha.observacao
    assert "dcp" not in linha.observacao
