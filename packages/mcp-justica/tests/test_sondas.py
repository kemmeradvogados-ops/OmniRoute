"""Sondas de portal: achar e dizer. E, sobretudo, NAO dizer o que nao viu.

O que estes testes protegem e uma unica regra: a sonda nunca afirma que um
processo NAO esta num sistema enquanto ninguem tiver visto a tela de "nada
encontrado" daquele portal. Afirmar ausencia que ninguem conferiu faz o
advogado procurar o processo em outro lugar, e processo dado como
inexistente e prazo perdido.
"""

import pytest

from justica_mcp import sondas
from justica_mcp.core.cnj import parse_numero

UM = "0000001-88.2019.8.19.0001"


def _num():
    return parse_numero(UM, validar_digito=False)


class _Pagina:
    url = "https://portal.exemplo/consulta"

    def query_selector_all(self, *a, **k):
        return []


def test_a_tabela_de_assinaturas_nasce_vazia():
    """Se esta tabela deixar de estar vazia sem que alguem tenha olhado uma
    tela real, o `False` volta a ser chute."""
    assert set(sondas.ASSINATURAS_DE_AUSENCIA) == {"dcp", "pje", "eproc", "esaj"}
    assert all(v == () for v in sondas.ASSINATURAS_DE_AUSENCIA.values())


def test_nao_confirmado_devolve_none_e_nunca_false(monkeypatch):
    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela",
                        lambda *a, **k: "/telas/sonda.json")
    r = sondas._nao_confirmado("dcp", _Pagina(), "A lista voltou vazia.")
    assert r.valor is None
    assert r.valor is not False
    assert "NAO foi confirmada" in r.detalhe
    assert r.tela_gravada is True


def test_falha_ao_gravar_a_tela_nao_derruba_a_sonda(monkeypatch):
    def explodir(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela", explodir)
    r = sondas._nao_confirmado("pje", _Pagina(), "Nada na lista.")
    assert r.valor is None
    assert r.tela_gravada is False
    assert "NAO FOI GRAVADA" in r.detalhe


def test_sistema_sem_sonda_nao_vira_ausencia():
    r = sondas.procurar("cpe", _Pagina(), None, _num(), "https://x", 5)
    assert r.valor is None
    assert "ninguem olhou" in r.detalhe


def test_sonda_que_quebra_devolve_none_em_vez_de_derrubar(monkeypatch):
    def explodir(*a, **k):
        raise RuntimeError("sessao caiu")

    monkeypatch.setitem(sondas.PROCURADORES, "dcp", explodir)
    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela",
                        lambda *a, **k: "/telas/sonda.json")
    r = sondas.procurar("dcp", _Pagina(), None, _num(), "https://x", 5)
    assert r.valor is None
    assert "RuntimeError" in r.detalhe
    # A MENSAGEM, e nao so o tipo: ela e o diagnostico. Em 26/10/2026 as
    # quatro sondas do Portal de Servicos falharam e a saida imprimiu so o
    # nome da classe, custando uma corrida inteira de diagnostico.
    assert "sessao caiu" in r.detalhe
    assert "NAO foi confirmada" in r.detalhe
    # O caminho da excecao tambem colhe a tela: e o que menos se sabe.
    assert r.tela_gravada is True


def test_dcp_achou_quando_a_lista_traz_o_numero(monkeypatch):
    monkeypatch.setattr("justica_mcp.dcp.buscar", lambda *a, **k: "quadro")
    monkeypatch.setattr("justica_mcp.dcp.esperar_a_lista_de_resultado",
                        lambda *a, **k: ["linha"])
    r = sondas.procurar_no_dcp(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is True
    assert "1 linha(s)" in r.detalhe


def test_dcp_sem_linha_nao_afirma_ausencia(monkeypatch):
    monkeypatch.setattr("justica_mcp.dcp.buscar", lambda *a, **k: "quadro")
    monkeypatch.setattr("justica_mcp.dcp.esperar_a_lista_de_resultado",
                        lambda *a, **k: [])
    monkeypatch.setattr("justica_mcp.dcp.resumo_da_lista",
                        lambda *a, **k: "Na tela ha 0 tabela(s).")
    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela",
                        lambda *a, **k: "/telas/sonda.json")
    r = sondas.procurar_no_dcp(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is None
    assert r.tela_gravada is True


def test_eproc_conta_a_capa_como_achado(monkeypatch):
    """'capa' e a tela do processo sem os eventos carregados. O processo esta
    la, que e o que a sonda pergunta."""
    monkeypatch.setattr("justica_mcp.portal.buscar_no_eproc",
                        lambda *a, **k: (True, "busca enviada"))
    monkeypatch.setattr("justica_mcp.extracao.esperar_tela_do_processo",
                        lambda *a, **k: "capa")
    r = sondas.procurar_no_eproc(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is True
    assert "capa" in r.detalhe


def test_eproc_tela_que_nao_montou_nao_vira_ausencia(monkeypatch):
    monkeypatch.setattr("justica_mcp.portal.buscar_no_eproc",
                        lambda *a, **k: (True, "busca enviada"))
    monkeypatch.setattr("justica_mcp.extracao.esperar_tela_do_processo",
                        lambda *a, **k: "nada")
    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela",
                        lambda *a, **k: "/telas/sonda.json")
    r = sondas.procurar_no_eproc(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is None


def test_pje_achou_quando_ha_link_do_processo(monkeypatch):
    monkeypatch.setattr("justica_mcp.pje.buscar_autenticado", lambda *a, **k: "url")
    monkeypatch.setattr("justica_mcp.pje.achar_link_do_processo",
                        lambda *a, **k: object())
    r = sondas.procurar_no_pje(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is True


def test_pje_sem_link_nao_afirma_ausencia(monkeypatch):
    monkeypatch.setattr("justica_mcp.pje.buscar_autenticado", lambda *a, **k: "url")
    monkeypatch.setattr("justica_mcp.pje.achar_link_do_processo",
                        lambda *a, **k: None)
    monkeypatch.setattr("justica_mcp.pje.linhas_do_resultado", lambda *a, **k: 0)
    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela",
                        lambda *a, **k: "/telas/sonda.json")
    r = sondas.procurar_no_pje(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is None


def test_esaj_achou_quando_ha_movimentacao(monkeypatch):
    monkeypatch.setattr("justica_mcp.esaj.buscar", lambda *a, **k: None)
    monkeypatch.setattr("justica_mcp.esaj.extrair_movimentacoes",
                        lambda *a, **k: [1, 2, 3])
    r = sondas.procurar_no_esaj(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is True
    assert "3 movimentacao" in r.detalhe


def test_nenhuma_sonda_devolve_false_hoje(monkeypatch):
    """Varredura estrutural: enquanto a tabela de assinaturas estiver vazia,
    nenhum caminho deste modulo pode responder `False`."""
    import inspect

    fonte = inspect.getsource(sondas)
    # `Resposta(False` ou `valor=False` seriam as duas formas de escrever isso.
    assert "Resposta(False" not in fonte
    assert "valor=False" not in fonte


def test_gravacao_desligada_nao_vira_tela_gravada(monkeypatch):
    """Em 26/10/2026 a sonda anunciou "tela gravada" cinco vezes numa corrida
    que nao gravou nada: `gravar_a_tela` devolve None em silencio quando a
    gravacao esta desligada, e a sonda lia "nao levantou excecao" como
    "gravou". Tres autenticacoes e colheita vazia, sem aviso."""
    monkeypatch.delenv("JUSTICA_GRAVAR_TELAS", raising=False)
    r = sondas._nao_confirmado("eproc", _Pagina(), "A tela nao montou.")
    assert r.tela_gravada is False
    assert "A TELA NAO FOI GRAVADA" in r.detalhe


def test_a_sonda_do_portal_de_servicos_nao_abre_o_processo(monkeypatch):
    """Sondar e perguntar se esta la, nao entrar. Abrir a linha do resultado
    custa tempo, aumenta a superficie de falha e, quando a busca por numero
    exato devolve mais de uma linha, pode abrir o processo de outra pessoa."""
    pedidos: list = []

    def buscar(pagina, guarda, numero, url, segundos, linha=1):
        pedidos.append(linha)
        return "quadro"

    monkeypatch.setattr("justica_mcp.dcp.buscar", buscar)
    monkeypatch.setattr("justica_mcp.dcp.esperar_a_lista_de_resultado",
                        lambda *a, **k: ["linha"])
    sondas.procurar_no_dcp(_Pagina(), None, _num(), "https://x", 5)
    # Linha zero nao existe: a abertura devolve sem clicar.
    assert pedidos == [0]
