"""Adaptador do PJe: consulta publica, que nao custa login.

Todos os seletores exercitados aqui foram lidos da tela real da consulta
publica do PJe do Rio, em 30 de setembro de 2026.
"""

import pytest

from justica_mcp.core.cnj import parse_numero
from justica_mcp.core.guarda_navegacao import GuardaNavegacao, Modo
from justica_mcp.pje import (
    BOTAO_PESQUISAR, CAMPO_NUMERO, ConsultaPJeIndisponivel, buscar_publico,
    endereco_da_consulta_publica, linhas_do_resultado,
)

# Numero valido pelo digito verificador da resolucao nº. 65/2008, montado
# para teste: nao e processo de cliente.
PROCESSO = "0809090-88.2023.8.19.0001"
LOGIN_RJ = "https://tjrj.pje.jus.br/1g/login.seam"


def _guarda():
    return GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])


# ---------------- o endereco ----------------

def test_o_endereco_vem_do_login_configurado():
    """Endereco fixo no codigo apontaria para o Rio para sempre, e o mesmo PJe
    atende dezenas de tribunais."""
    assert endereco_da_consulta_publica(LOGIN_RJ) == (
        "https://tjrj.pje.jus.br/1g/ConsultaPublica/listView.seam")


def test_outro_tribunal_da_outro_endereco():
    assert endereco_da_consulta_publica(
        "https://pje.trt1.jus.br/primeirograu/login.seam").startswith(
        "https://pje.trt1.jus.br/primeirograu/ConsultaPublica")


def test_parametros_do_login_nao_vao_para_o_endereco():
    assert "?" not in endereco_da_consulta_publica(f"{LOGIN_RJ}?x=1#aba")


def test_endereco_vazio_e_recusado():
    with pytest.raises(ConsultaPJeIndisponivel):
        endereco_da_consulta_publica("")


# ---------------- a busca ----------------

class _Campo:
    def __init__(self, pagina, seletor):
        self.pagina, self.seletor = pagina, seletor
        self.valor = ""

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def click(self):
        self.pagina.cliques.append(self.seletor)

    def fill(self, valor):
        self.valor = valor
        self.pagina.preenchidos[self.seletor] = valor

    def evaluate(self, _):
        return len([c for c in self.valor if c.isdigit()])


class _PaginaPJe:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, sem=(), mascara_come_tudo=False):
        self.url = "https://tjrj.pje.jus.br/1g/ConsultaPublica/listView.seam"
        self.sem = set(sem)
        self.navegou = []
        self.cliques = []
        self.preenchidos = {}
        self.mascara_come_tudo = mascara_come_tudo

    def goto(self, url, **kw):
        self.navegou.append(url)
        self.url = url

    def query_selector_all(self, seletor):
        if seletor in self.sem:
            return []
        campo = _Campo(self, seletor)
        if self.mascara_come_tudo and seletor == CAMPO_NUMERO:
            campo.fill = lambda _v: None
        return [campo]

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


def test_a_busca_navega_preenche_e_pesquisa():
    pagina = _PaginaPJe()
    buscar_publico(pagina, _guarda(), parse_numero(PROCESSO), LOGIN_RJ, 10)

    assert pagina.navegou == [
        "https://tjrj.pje.jus.br/1g/ConsultaPublica/listView.seam"]
    assert pagina.preenchidos[CAMPO_NUMERO] == parse_numero(PROCESSO).formatado
    assert BOTAO_PESQUISAR in pagina.cliques


def test_numero_que_a_mascara_engole_nao_vira_pesquisa():
    """Mascara que rejeita o formato deixa o campo vazio sem reclamar: a busca
    volta 'nada encontrado' e o operador conclui que o processo nao existe."""
    pagina = _PaginaPJe(mascara_come_tudo=True)
    with pytest.raises(ConsultaPJeIndisponivel, match="20 digitos"):
        buscar_publico(pagina, _guarda(), parse_numero(PROCESSO), LOGIN_RJ, 10)
    assert BOTAO_PESQUISAR not in pagina.cliques


def test_tela_sem_o_campo_e_relatada_e_nao_adivinhada():
    pagina = _PaginaPJe(sem=[CAMPO_NUMERO])
    with pytest.raises(ConsultaPJeIndisponivel, match="campo do numero"):
        buscar_publico(pagina, _guarda(), parse_numero(PROCESSO), LOGIN_RJ, 10)


def test_tela_sem_o_botao_nao_pesquisa_no_escuro():
    pagina = _PaginaPJe(sem=[BOTAO_PESQUISAR])
    with pytest.raises(ConsultaPJeIndisponivel, match="Pesquisar"):
        buscar_publico(pagina, _guarda(), parse_numero(PROCESSO), LOGIN_RJ, 10)


def test_a_trava_registra_a_navegacao_o_preenchimento_e_o_clique():
    guarda = _guarda()
    buscar_publico(_PaginaPJe(), guarda, parse_numero(PROCESSO), LOGIN_RJ, 10)
    acoes = [r["acao"] for r in guarda.registro]
    assert acoes == ["navegar", "preencher", "clicar"]


# ---------------- o resultado ----------------

class _Tabela:
    def __init__(self, linhas):
        self._linhas = linhas

    def query_selector_all(self, _):
        return ["linha"] * self._linhas


class _PaginaComResultado:
    def __init__(self, linhas=0, sem_tabela=False):
        self._tabela = None if sem_tabela else _Tabela(linhas)

    def query_selector(self, _):
        return self._tabela


def test_contagem_de_linhas_do_resultado():
    assert linhas_do_resultado(_PaginaComResultado(3)) == 3


def test_tabela_ausente_conta_zero_e_nao_explode():
    assert linhas_do_resultado(_PaginaComResultado(sem_tabela=True)) == 0


def test_leitura_que_falha_conta_zero():
    class Quebrada:
        def query_selector(self, _):
            raise RuntimeError("tela morta")

    assert linhas_do_resultado(Quebrada()) == 0


# --------------------------------------------------------------------------
# O portal redireciona a consulta publica
#
# Conferido em campo em 30/09/2026: `/1g/ConsultaPublica/listView.seam` leva a
# `/pje/ConsultaPublica/listView.seam`. A trava barrou o preenchimento, e
# estava CERTA: a permissao valia para a tela de partida. A correcao nao e
# afrouxar a trava, e sim conferir que a chegada e a mesma tela do mesmo
# portal e autoriza-la nominalmente.
# --------------------------------------------------------------------------

class _PaginaQueRedireciona(_PaginaPJe):
    def __init__(self, destino_real, **kw):
        super().__init__(**kw)
        self._destino_real = destino_real

    def goto(self, url, **kw):
        self.navegou.append(url)
        self.url = self._destino_real


def test_redirecionamento_do_proprio_portal_e_aceito():
    pagina = _PaginaQueRedireciona(
        "https://tjrj.pje.jus.br/pje/ConsultaPublica/listView.seam")
    guarda = _guarda()
    final = buscar_publico(pagina, guarda, parse_numero(PROCESSO), LOGIN_RJ, 10)

    assert final.endswith("/pje/ConsultaPublica/listView.seam")
    assert BOTAO_PESQUISAR in pagina.cliques


def test_redirecionamento_para_outro_dominio_e_recusado():
    """Outro dominio nao esta sob a autorizacao dada."""
    pagina = _PaginaQueRedireciona(
        "https://outro.exemplo/pje/ConsultaPublica/listView.seam")
    with pytest.raises(ConsultaPJeIndisponivel, match="outro dominio"):
        buscar_publico(pagina, _guarda(), parse_numero(PROCESSO), LOGIN_RJ, 10)
    assert pagina.preenchidos == {}


def test_redirecionamento_para_outra_tela_e_recusado():
    """Preencher e clicar as cegas numa tela que nao e a pedida e onde mora o
    estrago."""
    pagina = _PaginaQueRedireciona("https://tjrj.pje.jus.br/pje/login.seam")
    with pytest.raises(ConsultaPJeIndisponivel, match="outra tela"):
        buscar_publico(pagina, _guarda(), parse_numero(PROCESSO), LOGIN_RJ, 10)
    assert pagina.cliques == []


def test_sem_redirecionamento_nao_ha_permissao_extra():
    guarda = _guarda()
    buscar_publico(_PaginaPJe(), guarda, parse_numero(PROCESSO), LOGIN_RJ, 10)
    assert len(guarda.permissoes) == 1
