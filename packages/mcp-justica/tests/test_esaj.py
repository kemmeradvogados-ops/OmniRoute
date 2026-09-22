"""Consulta no e-SAJ do Tribunal de Justica de Sao Paulo.

Estrutura conferida em campo em 21 de setembro de 2026, com sessao autenticada.
O e-SAJ nao tem a barra de busca rapida do eproc: tem duas telas, uma por grau,
e elas pedem o numero PARTIDO em dois campos.
"""

import pytest

from justica_mcp.core.cnj import parse_numero
from justica_mcp.core.guarda_navegacao import Acao, GuardaNavegacao, Modo
from justica_mcp.esaj import (
    PRIMEIRO_GRAU, SEGUNDO_GRAU, ConsultaESAJIndisponivel, buscar,
    partes_do_numero, tela_para,
)

PRIMEIRA = "1037850-62.2023.8.26.0100"
SEGUNDA = "2081722-17.2026.8.26.0000"


# --------------------------------------------------------------------------
# Escolha da tela
# --------------------------------------------------------------------------

def test_processo_de_primeira_instancia_vai_para_a_tela_de_primeiro_grau():
    assert tela_para(parse_numero(PRIMEIRA)) is PRIMEIRO_GRAU


def test_processo_originario_do_tribunal_vai_para_a_tela_de_segundo_grau():
    assert tela_para(parse_numero(SEGUNDA)) is SEGUNDO_GRAU


def test_os_dois_graus_tem_botoes_diferentes():
    """Conferido em campo: `#botaoConsultarProcessos` no primeiro grau e
    `#pbConsultar` no segundo. Usar um no lugar do outro nao acha o botao."""
    assert PRIMEIRO_GRAU.botao_consultar != SEGUNDO_GRAU.botao_consultar


def test_as_duas_telas_tem_enderecos_diferentes():
    assert PRIMEIRO_GRAU.url != SEGUNDO_GRAU.url


# --------------------------------------------------------------------------
# Particao do numero
# --------------------------------------------------------------------------

def test_treze_primeiros_sao_sequencial_digito_e_ano():
    treze, quatro = partes_do_numero(parse_numero(PRIMEIRA))
    assert treze == "1037850-62.2023"
    assert len([c for c in treze if c.isdigit()]) == 13


def test_quatro_ultimos_sao_a_unidade_de_origem():
    _, quatro = partes_do_numero(parse_numero(PRIMEIRA))
    assert quatro == "0100"
    assert len(quatro) == 4


def test_particao_do_originario_do_tribunal():
    treze, quatro = partes_do_numero(parse_numero(SEGUNDA))
    assert treze == "2081722-17.2026"
    assert quatro == "0000"


def test_a_particao_nao_perde_nem_inventa_digito():
    """Somados, os dois campos tem de reproduzir o numero sem o trecho J.TR,
    que o portal ja sabe e mantem num campo desabilitado."""
    n = parse_numero(PRIMEIRA)
    treze, quatro = partes_do_numero(n)
    digitos = "".join(c for c in treze if c.isdigit()) + quatro
    assert digitos == n.apenas_digitos.replace(f"{n.segmento}{n.tribunal}", "", 1)


# --------------------------------------------------------------------------
# Busca
# --------------------------------------------------------------------------

class _Campo:
    def __init__(self, aceita=True):
        self.valor = ""
        self.aceita = aceita
        self.cliques = 0

    def click(self):
        self.cliques += 1

    def fill(self, valor):
        self.valor = valor if self.aceita else ""

    def evaluate(self, _):
        return self.valor

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 10, "y": 10, "width": 100, "height": 20}


class _PaginaESAJ:
    def __init__(self, faltando=(), mascara_quebrada=()):
        self.url = "https://esaj.tjsp.jus.br/esaj/"
        self.navegou = []
        self.faltando = set(faltando)
        self.campos = {}
        self.mascara_quebrada = set(mascara_quebrada)
        self.viewport_size = {"width": 1280, "height": 720}

    def goto(self, destino, **kw):
        self.navegou.append(destino)
        self.url = destino

    def query_selector_all(self, seletor):
        if seletor in self.faltando:
            return []
        self.campos.setdefault(
            seletor, _Campo(aceita=seletor not in self.mascara_quebrada)
        )
        return [self.campos[seletor]]

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


def _guarda():
    return GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])


def test_busca_abre_a_tela_do_grau_e_preenche_os_dois_campos():
    pagina = _PaginaESAJ()
    tela = buscar(pagina, _guarda(), parse_numero(PRIMEIRA), 10)
    assert tela is PRIMEIRO_GRAU
    assert pagina.navegou == [PRIMEIRO_GRAU.url]
    assert pagina.campos["#numeroDigitoAnoUnificado"].valor == "1037850-62.2023"
    assert pagina.campos["#foroNumeroUnificado"].valor == "0100"
    assert pagina.campos["#botaoConsultarProcessos"].cliques == 1


def test_busca_de_segundo_grau_usa_o_outro_botao():
    pagina = _PaginaESAJ()
    buscar(pagina, _guarda(), parse_numero(SEGUNDA), 10)
    assert pagina.navegou == [SEGUNDO_GRAU.url]
    assert pagina.campos["#pbConsultar"].cliques == 1


def test_campo_que_nao_aceitou_o_valor_aborta_sem_consultar():
    """A mascara pode recusar o preenchimento programatico. Consultar assim
    buscaria numero diferente do pedido e devolveria o processo errado, sem
    nada indicar o engano."""
    pagina = _PaginaESAJ(mascara_quebrada={"#numeroDigitoAnoUnificado"})
    with pytest.raises(ConsultaESAJIndisponivel) as erro:
        buscar(pagina, _guarda(), parse_numero(PRIMEIRA), 10)
    assert "nao foi consultado" in str(erro.value).lower() or "Nada foi consultado" in str(erro.value)
    assert "#botaoConsultarProcessos" not in pagina.campos


def test_campo_ausente_aborta_com_orientacao():
    pagina = _PaginaESAJ(faltando={"#foroNumeroUnificado"})
    with pytest.raises(ConsultaESAJIndisponivel) as erro:
        buscar(pagina, _guarda(), parse_numero(PRIMEIRA), 10)
    assert "reconhecimento" in str(erro.value)


def test_a_permissao_criada_nao_libera_mais_que_o_necessario():
    """A tela tem links de peticionamento e de certidao ao lado. A autorizacao
    da consulta nao pode alcancar nenhum deles."""
    pagina = _PaginaESAJ()
    guarda = _guarda()
    buscar(pagina, guarda, parse_numero(PRIMEIRA), 10)
    liberados = set()
    for p in guarda.permissoes:
        liberados.update(p.seletores_clicaveis)
        liberados.update(p.seletores_preenchiveis)
    assert liberados == {
        "#numeroDigitoAnoUnificado", "#foroNumeroUnificado",
        "#botaoConsultarProcessos",
    }
    # A permissao de origem existe para navegar, e nao pode liberar acao
    # nenhuma: e ela que alcanca o portal inteiro.
    for p in guarda.permissoes:
        if "origem" in p.descricao or "mesmo portal" in p.descricao:
            assert not p.seletores_clicaveis
            assert not p.seletores_preenchiveis


# --------------------------------------------------------------------------
# Despacho por sistema
# --------------------------------------------------------------------------

def test_a_consulta_despacha_pelo_sistema_e_nao_trata_tudo_como_eproc():
    """O eproc tem barra de busca rapida em toda tela; o e-SAJ tem duas telas
    de consulta com o numero partido. Tratar tudo como eproc foi possivel
    enquanto so havia eproc."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert 'identidade.sistema == "esaj"' in fonte
    assert "buscar as buscar_esaj" in fonte
    # e o caminho do eproc continua sendo o outro ramo, nao foi removido
    assert "BUSCA_RAPIDA" in fonte
