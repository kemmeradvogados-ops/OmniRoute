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


def test_so_o_pje_tem_assinatura_de_ausencia_conferida():
    """Cada entrada desta tabela corresponde a uma tela REAL que alguem olhou.

    O PJe ganhou a sua em 26/10/2026, da tela
    `20261026T021247509-sonda-pje-sem-resultado.json`. Os outros tres seguem
    vazios porque ninguem viu ainda a tela de "nada encontrado" deles, e
    enquanto nao virem nao podem responder `False`.
    """
    assert set(sondas.ASSINATURAS_DE_AUSENCIA) == {"dcp", "pje", "eproc", "esaj"}
    assert sondas.ASSINATURAS_DE_AUSENCIA["pje"]
    assert sondas.ASSINATURAS_DE_AUSENCIA["dcp"] == ()
    assert sondas.ASSINATURAS_DE_AUSENCIA["eproc"] == ()
    assert sondas.ASSINATURAS_DE_AUSENCIA["esaj"] == ()


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


def test_so_a_sonda_do_pje_pode_responder_que_nao_esta_la():
    """Varredura estrutural: `False` so pode sair de onde alguem viu a tela.

    Hoje isso e so `procurar_no_pje`. Se alguem acrescentar um `False` noutra
    sonda sem antes olhar a tela daquele portal, este teste cai: afirmar que
    um processo nao esta num sistema onde ninguem olhou e o pior desfecho
    deste programa, porque processo dado como inexistente e prazo perdido.
    """
    import inspect

    for nome, sonda in sondas.PROCURADORES.items():
        fonte = inspect.getsource(sonda)
        devolve_falso = "Resposta(\n            False" in fonte or \
                        "Resposta(False" in fonte or "valor=False" in fonte
        if nome == "pje":
            assert devolve_falso, "a sonda do PJe deveria confirmar ausencia"
        else:
            assert not devolve_falso, (
                f"a sonda de {nome} responde False sem tela conferida")


def test_pje_sem_tabela_montada_nao_afirma_ausencia(monkeypatch):
    """Tabela ausente e tela que nao terminou de montar, que e coisa
    diferente de processo que nao esta la."""
    monkeypatch.setattr("justica_mcp.pje.buscar_autenticado", lambda *a, **k: "url")
    monkeypatch.setattr("justica_mcp.pje.achar_link_do_processo",
                        lambda *a, **k: None)
    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela",
                        lambda *a, **k: "/telas/sonda.json")

    class _SemTabela(_Pagina):
        def query_selector(self, *a, **k):
            return None

    r = sondas.procurar_no_pje(_SemTabela(), None, _num(), "https://x", 5)
    assert r.valor is None
    assert "nao montou" in r.detalhe


def test_pje_com_tabela_montada_e_sem_o_numero_confirma_a_ausencia(monkeypatch):
    monkeypatch.setattr("justica_mcp.pje.buscar_autenticado", lambda *a, **k: "url")
    monkeypatch.setattr("justica_mcp.pje.achar_link_do_processo",
                        lambda *a, **k: None)
    monkeypatch.setattr("justica_mcp.pje.linhas_do_resultado", lambda *a, **k: 1)

    class _ComTabela(_Pagina):
        def query_selector(self, *a, **k):
            return object()

    r = sondas.procurar_no_pje(_ComTabela(), None, _num(), "https://x", 5)
    assert r.valor is False
    assert "Ausencia confirmada" in r.detalhe


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


def test_dcp_refaz_a_entrada_quando_o_formulario_sumiu(monkeypatch):
    """Em 26/10/2026 o portal abriu o processo sozinho depois de uma busca que
    devolveu uma linha, e dali em diante nao havia formulario. A volta ao
    portal e tentada UMA vez: insistir esconderia qual e o problema."""
    from justica_mcp.dcp import ConsultaIndisponivel

    tentativas: list = []

    def buscar(pagina, guarda, numero, url, segundos, linha=1):
        tentativas.append(linha)
        if len(tentativas) == 1:
            raise ConsultaIndisponivel("A tela da consulta nao tem o campo.")
        return "quadro"

    entradas: list = []

    def preparar_dcp(pagina, guarda, perfil, segundos):
        entradas.append(perfil)
        return sondas.Preparo(pagina, True, "portal reaberto")

    monkeypatch.setattr("justica_mcp.dcp.buscar", buscar)
    monkeypatch.setattr(sondas, "preparar_dcp", preparar_dcp)
    monkeypatch.setattr("justica_mcp.dcp.esperar_a_lista_de_resultado",
                        lambda *a, **k: ["linha"])
    r = sondas.procurar_no_dcp(_Pagina(), None, _num(), "https://x", 5,
                               "Advogado")
    assert r.valor is True
    assert tentativas == [0, 0]
    assert entradas == ["Advogado"]


def test_dcp_desiste_quando_a_volta_ao_portal_tambem_falha(monkeypatch):
    from justica_mcp.dcp import ConsultaIndisponivel

    def buscar(*a, **k):
        raise ConsultaIndisponivel("A tela da consulta nao tem o campo.")

    monkeypatch.setattr("justica_mcp.dcp.buscar", buscar)
    monkeypatch.setattr(
        sondas, "preparar_dcp",
        lambda pagina, guarda, perfil, segundos:
            sondas.Preparo(pagina, False, "nao deu para entrar"))
    monkeypatch.setattr("justica_mcp.telas.gravar_a_tela",
                        lambda *a, **k: "/telas/sonda.json")
    r = sondas.procurar_no_dcp(_Pagina(), None, _num(), "https://x", 5, None)
    assert r.valor is None
    assert "a volta ao portal tambem" in r.detalhe


def test_o_perfil_so_chega_a_quem_precisa_dele(monkeypatch):
    """O Portal de Servicos usa o perfil para refazer a entrada; os outros
    nao tem o que fazer com ele, e passar um argumento a mais quebraria."""
    recebidos: list = []

    def sonda_sem_perfil(pagina, guarda, numero, url, segundos):
        recebidos.append("sem perfil")
        return sondas.Resposta(True, "simulado")

    monkeypatch.setitem(sondas.PROCURADORES, "eproc", sonda_sem_perfil)
    r = sondas.procurar("eproc", _Pagina(), None, _num(), "https://x", 5,
                        "Advogado")
    assert r.valor is True
    assert recebidos == ["sem perfil"]


# --------------------------------------------------------------------------
# Busca que devolve UMA linha abre o processo sozinha
#
# Tres corridas seguidas, 25 e 26/10/2026: sempre que uma busca do Portal de
# Servicos devolveu 1 linha, a busca SEGUINTE nao achou o formulario; quando
# devolveu 5, a seguinte funcionou. A tela gravada mostrou o quadro embutido
# em `.../consultar/detalhes-processo`.
# --------------------------------------------------------------------------

class _Quadro:
    def __init__(self, url, alvos=()):
        self.url = url
        self._alvos = set(alvos)

    def query_selector(self, seletor):
        return object() if seletor in self._alvos else None


class _Clicavel:
    def __init__(self, registro, seletor, sai):
        self._registro, self._seletor, self._sai = registro, seletor, sai

    def click(self):
        self._registro.append(self._seletor)
        self._sai()


def test_a_tela_do_processo_e_reconhecida_pelo_endereco(monkeypatch):
    monkeypatch.setattr(
        "justica_mcp.dcp.quadro_da_consulta",
        lambda pagina: _Quadro("https://x/consultaprocessual/#/consultar/detalhes-processo"))
    assert sondas.dentro_da_tela_do_processo(_Pagina()) is True

    monkeypatch.setattr(
        "justica_mcp.dcp.quadro_da_consulta",
        lambda pagina: _Quadro("https://x/consultaprocessual/#/consultaportal"))
    assert sondas.dentro_da_tela_do_processo(_Pagina()) is False


def test_a_volta_usa_a_trilha_do_portal_antes_do_botao_voltar(monkeypatch):
    """A ordem e a da tela gravada: a trilha de navegacao primeiro."""
    cliques: list = []
    estado = {"dentro": True}

    class _Guarda:
        permissoes: list = []

        def pode_executar(self, *a, **k):
            return True

    quadro = _Quadro("https://x/#/consultar/detalhes-processo")
    monkeypatch.setattr("justica_mcp.dcp.quadro_da_consulta", lambda p: quadro)
    monkeypatch.setattr("justica_mcp.portal._assentar", lambda *a, **k: None)
    monkeypatch.setattr(
        "justica_mcp.portal.elemento_visivel",
        lambda alvo, seletor: _Clicavel(
            cliques, seletor, lambda: estado.update(dentro=False))
        if seletor == "texto=Consultas / Consulta Processual" else None)
    monkeypatch.setattr(sondas, "dentro_da_tela_do_processo",
                        lambda p: estado["dentro"])

    assert sondas.voltar_da_tela_do_processo(_Pagina(), _Guarda(), 5) is True
    assert cliques == ["texto=Consultas / Consulta Processual"]


def test_a_sonda_sai_da_tela_do_processo_antes_de_buscar(monkeypatch, capsys):
    saidas: list = []
    monkeypatch.setattr(sondas, "dentro_da_tela_do_processo",
                        lambda p: not saidas)
    monkeypatch.setattr(
        sondas, "voltar_da_tela_do_processo",
        lambda p, g, s: (saidas.append("voltou"), True)[1])
    monkeypatch.setattr("justica_mcp.dcp.buscar", lambda *a, **k: "quadro")
    monkeypatch.setattr("justica_mcp.dcp.esperar_a_lista_de_resultado",
                        lambda *a, **k: ["linha"])
    r = sondas.procurar_no_dcp(_Pagina(), None, _num(), "https://x", 5)
    assert r.valor is True
    assert saidas == ["voltou"]
    assert "[VOLTOU]" in capsys.readouterr().out


def test_quando_a_volta_falha_a_sonda_avisa_em_vez_de_calar(
        monkeypatch, capsys):
    monkeypatch.setattr(sondas, "dentro_da_tela_do_processo", lambda p: True)
    monkeypatch.setattr(sondas, "voltar_da_tela_do_processo",
                        lambda p, g, s: False)
    monkeypatch.setattr("justica_mcp.dcp.buscar", lambda *a, **k: "quadro")
    monkeypatch.setattr("justica_mcp.dcp.esperar_a_lista_de_resultado",
                        lambda *a, **k: ["linha"])
    sondas.procurar_no_dcp(_Pagina(), None, _num(), "https://x", 5)
    assert "[ATENCAO]" in capsys.readouterr().out
