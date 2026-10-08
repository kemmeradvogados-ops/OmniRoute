"""Visualizador de Processos Eletronicos do Tribunal de Justica do Rio de Janeiro.

Telas lidas em campo em 05 e 06/10/2026: o acompanhamento conduzido pelo
advogado deu a barra de ferramentas, e as fotos que ele enviou deram a caixa
de download, com o texto exato dos tres botoes.

A barra nao da identificador a nenhum botao, e o texto visivel de cada um e o
nome do icone. Quem diz o que o botao faz e o rotulo acessivel.
"""

import pytest

from justica_mcp.dcp import (
    BOTAO_DE_DOWNLOAD, ESCOLHA_CANCELAR, ESCOLHA_INTEGRAL, ESCOLHA_MARCADOS,
    DownloadIndisponivel, achar_botao_de_download, achar_escolha,
    baixar_integra, caixa_de_download_aberta,
)


class _Elemento:
    def __init__(self, pagina, texto="", rotulo=None, visivel=True):
        self.pagina, self.texto, self.rotulo, self.visivel = pagina, texto, rotulo, visivel

    def inner_text(self):
        return self.texto

    def get_attribute(self, nome):
        return {"aria-label": self.rotulo}.get(nome)

    def is_visible(self):
        return self.visivel

    def bounding_box(self):
        return {"x": 10, "y": 10, "width": 40, "height": 40}

    def click(self):
        self.pagina.cliques.append(self.rotulo or self.texto)
        self.pagina.depois_do_clique()


class _Baixado:
    suggested_filename = "0045025-93.2021.8.19.0002.pdf"

    def __init__(self):
        self.gravado_em = None

    def save_as(self, caminho):
        self.gravado_em = caminho
        with open(caminho, "w", encoding="utf-8") as saida:
            saida.write("")


class _Espera:
    def __init__(self, baixado):
        self.value = baixado

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Visualizador:
    """A tela do visualizador, com a caixa de download fechada no comeco."""

    url = "https://www3.tjrj.jus.br/visproc/#/token"
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, tem_botao=True, abre_caixa=True, integral=True,
                 entrega_arquivo=True):
        self.cliques = []
        self.abre_caixa, self.integral = abre_caixa, integral
        self.entrega_arquivo = entrega_arquivo
        self.caixa_aberta = False
        self.baixado = _Baixado()
        self.barra = []
        if tem_botao:
            self.barra.append(
                _Elemento(self, "download_for_offline", BOTAO_DE_DOWNLOAD))

    def depois_do_clique(self):
        if self.abre_caixa:
            self.caixa_aberta = True

    def _botoes_da_caixa(self):
        if not self.caixa_aberta:
            return []
        textos = [ESCOLHA_CANCELAR, ESCOLHA_MARCADOS]
        if self.integral:
            textos.append(ESCOLHA_INTEGRAL)
        return [_Elemento(self, t) for t in textos]

    def query_selector_all(self, seletor):
        if seletor.startswith("[aria-label"):
            return list(self.barra)
        if seletor.startswith("[title") or seletor.startswith("[alt"):
            return []
        return self._botoes_da_caixa() + list(self.barra)

    def wait_for_timeout(self, _):
        pass

    def expect_download(self, timeout=None):
        if not self.entrega_arquivo:
            raise RuntimeError("TimeoutError: nenhum download chegou")
        return _Espera(self.baixado)


class _Guarda:
    def __init__(self):
        self.permissoes = []
        self.autorizados = []

    def pode_executar(self, acao, seletor, url=None):
        self.autorizados.append(seletor)


# ---------------- achar o botao da barra ----------------

def test_o_botao_da_barra_e_achado_pelo_rotulo():
    """Texto visivel e o nome do icone; quem diz o que ele faz e o rotulo."""
    tela = _Visualizador()
    assert achar_botao_de_download(tela) is not None


def test_barra_sem_o_botao_devolve_nada():
    assert achar_botao_de_download(_Visualizador(tem_botao=False)) is None


# ---------------- a caixa de download ----------------

def test_a_caixa_so_conta_como_aberta_com_as_duas_escolhas():
    """Titulo e texto solto e pode aparecer noutro lugar; os dois botoes juntos
    so existem nessa caixa."""
    tela = _Visualizador()
    assert caixa_de_download_aberta(tela) is False
    tela.caixa_aberta = True
    assert caixa_de_download_aberta(tela) is True


def test_as_escolhas_sao_achadas_pelo_texto_exato():
    tela = _Visualizador()
    tela.caixa_aberta = True
    assert achar_escolha(tela, ESCOLHA_INTEGRAL) is not None
    assert achar_escolha(tela, ESCOLHA_MARCADOS) is not None
    assert achar_escolha(tela, "Salvar") is None


# ---------------- o download ----------------

def test_o_caminho_completo_grava_o_arquivo(tmp_path):
    tela, guarda = _Visualizador(), _Guarda()
    arquivo = baixar_integra(tela, guarda, tmp_path, "0045025", segundos=5)
    assert arquivo.startswith(str(tmp_path))
    assert tela.cliques == [BOTAO_DE_DOWNLOAD, ESCOLHA_INTEGRAL]


def test_a_escolha_e_sempre_a_integral_nunca_a_dos_marcados(tmp_path):
    """Um PDF parcial guardado como integra e pior que arquivo nenhum, porque
    ninguem volta a conferir o que ja esta na pasta."""
    tela, guarda = _Visualizador(), _Guarda()
    baixar_integra(tela, guarda, tmp_path, "0045025", segundos=5)
    assert ESCOLHA_MARCADOS not in tela.cliques


def test_sem_a_escolha_integral_o_caminho_para(tmp_path):
    tela, guarda = _Visualizador(integral=False), _Guarda()
    with pytest.raises(DownloadIndisponivel, match="Carregados"):
        baixar_integra(tela, guarda, tmp_path, "0045025", segundos=5)
    assert ESCOLHA_MARCADOS not in tela.cliques


def test_a_recusa_explica_por_que_nao_usa_os_marcados(tmp_path):
    tela, guarda = _Visualizador(integral=False), _Guarda()
    with pytest.raises(DownloadIndisponivel) as erro:
        baixar_integra(tela, guarda, tmp_path, "0045025", segundos=5)
    recado = str(erro.value)
    assert "so o que foi marcado" in recado
    assert "pior que arquivo nenhum" in recado


def test_sem_o_botao_da_barra_nada_e_clicado(tmp_path):
    tela, guarda = _Visualizador(tem_botao=False), _Guarda()
    with pytest.raises(DownloadIndisponivel, match="nao esta na barra"):
        baixar_integra(tela, guarda, tmp_path, "0045025", segundos=5)
    assert tela.cliques == []


def test_processo_grande_que_nao_baixa_diz_o_que_fazer(tmp_path):
    """O advogado informou em 06/10/2026 que processo grande as vezes nao baixa
    de uma vez."""
    tela, guarda = _Visualizador(entrega_arquivo=False), _Guarda()
    with pytest.raises(DownloadIndisponivel) as erro:
        baixar_integra(tela, guarda, tmp_path, "0045025", segundos=5)
    recado = str(erro.value)
    assert "nao baixa de uma vez" in recado
    # E a corrida gasta traz o indice junto, para que a proxima ja saiba
    # marcar os documentos em vez de descobrir isso numa rodada so para isso.
    assert "O INDICE DE DOCUMENTOS, para baixar em partes" in recado
    # Neste falso nao ha o botao da caixa de selecao, e o relato diz isso em
    # vez de calar: "nao li o indice" e diferente de "o indice esta vazio".
    assert "Exibir caixa de seleção" in recado


# ---------------- a trava ----------------

def test_a_trava_autoriza_so_os_dois_cliques_deste_caminho(tmp_path):
    tela, guarda = _Visualizador(), _Guarda()
    baixar_integra(tela, guarda, tmp_path, "0045025", segundos=5)
    assert guarda.autorizados == [
        f'[aria-label="{BOTAO_DE_DOWNLOAD}"]', f"texto={ESCOLHA_INTEGRAL}"]
    # A autorizacao nomeia os dois, e nenhum terceiro botao da caixa.
    liberados = guarda.permissoes[0].seletores_clicaveis
    assert ESCOLHA_MARCADOS not in " ".join(liberados)
    assert ESCOLHA_CANCELAR not in " ".join(liberados)


def test_o_arquivo_nao_e_declarado_completo():
    """Quem confere a completude e o acervo, contra o indice."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.baixar_integra)
    assert "NAO e declarado completo aqui" in fonte
    assert "Quem confere a completude e o acervo" in fonte


# ==========================================================================
# Consulta processual do Portal de Servicos
#
# Telas fotografadas em 06/10/2026, versao 5.25.2. O numero NAO e dividido em
# seis campos como no PJe: sao dois, com `.8.19.` escrito fixo entre eles.
# ==========================================================================

from justica_mcp.core.cnj import parse_numero  # noqa: E402
from justica_mcp.dcp import (  # noqa: E402
    BOTAO_PESQUISAR, BOTAO_VISUALIZADOR, CAMPO_INICIO, CAMPO_ORIGEM,
    ConsultaIndisponivel, buscar, conferir_tribunal, endereco_da_consulta,
    partes_do_numero, quadro_da_consulta,
)

PROCESSO = "0045025-93.2021.8.19.0002"
LOGIN = "https://www3.tjrj.jus.br/idserverjus-front/#/login?indGet=true&sgSist=X"


def test_o_endereco_da_consulta_vem_do_de_login():
    assert endereco_da_consulta(LOGIN) == (
        "https://www3.tjrj.jus.br/portalservicos/#/consproc/consultaportal")


def test_sem_endereco_de_login_nao_ha_consulta():
    with pytest.raises(ConsultaIndisponivel, match="Sem endereco"):
        endereco_da_consulta("")


def test_o_numero_e_dividido_em_dois_campos():
    """O primeiro leva sequencial, digito e ano juntos; o segundo so a origem.
    Entre eles o portal escreve `.8.19.` e nao pergunta nada."""
    assert partes_do_numero(parse_numero(PROCESSO)) == ("0045025-93.2021", "0002")


def test_numero_de_outro_tribunal_e_recusado_antes_de_digitar():
    """O portal impoe segmento e tribunal. Mandar numero de outro montaria,
    em silencio, o numero de UM PROCESSO QUE NAO E O PEDIDO."""
    with pytest.raises(ConsultaIndisponivel, match="so serve ao Tribunal de"):
        conferir_tribunal(parse_numero("0000001-78.2020.8.26.0100"))


def test_numero_do_rio_passa():
    conferir_tribunal(parse_numero(PROCESSO))


# ---------------- a tela da consulta ----------------

class _CampoDoNumero:
    def __init__(self, quadro, identificador, nome=None, aceita=True,
                 aceita_teclado=True):
        self.quadro, self.identificador, self.nome = quadro, identificador, nome
        self.aceita, self.valor, self.marcado = aceita, "", False
        self.aceita_teclado = aceita_teclado

    def get_attribute(self, nome):
        return {"id": self.identificador, "name": self.nome}.get(nome)

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 200, "height": 30}

    def click(self):
        self.marcado = True
        self.quadro.cliques.append(self.identificador or self.nome)

    def fill(self, valor):
        if self.aceita or valor == "":
            self.valor = valor

    def type(self, valor, delay=None):
        if self.aceita_teclado:
            self.valor = valor

    def evaluate(self, roteiro):
        if "checked" in roteiro:
            return self.marcado
        if "replace" in roteiro:
            return "".join(c for c in self.valor if c.isdigit())
        return self.valor

    def inner_text(self):
        return ""


class _BotaoDoQuadro:
    def __init__(self, quadro, texto):
        self.quadro, self.texto = quadro, texto

    def inner_text(self):
        return self.texto

    def get_attribute(self, _):
        return None

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 90, "height": 30}

    def click(self):
        self.quadro.cliques.append(self.texto)
        # Clicar em "Entrar" na tela do tipo de usuario TIRA dela: e o que o
        # portal faz, e desde 07/10/2026 e o que a prova positiva exige. Falso
        # que fica parado na mesma tela estaria descrevendo um portal que nao
        # existe, e reprovaria o programa por fazer a coisa certa.
        if self.texto == "Entrar":
            destino = getattr(self.quadro, "destino_do_entrar", None)
            if destino is not None:
                self.quadro.url = destino


class _QuadroDaConsulta:
    url = "https://www3.tjrj.jus.br/consultaprocessual/#/consultaportal"
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, sem=(), aceita=True, unica_marcada=True,
                 aceita_teclado=True):
        self.cliques = []
        self.sem = set(sem)
        self.inicio = _CampoDoNumero(self, None, "numeroProcesso", aceita,
                                     aceita_teclado)
        self.origem = _CampoDoNumero(self, "inputSufixoUnica3", None, aceita,
                                     aceita_teclado)
        self.unica = _CampoDoNumero(self, "numeracaoUnica")
        self.unica.marcado = unica_marcada
        self.botoes = [_BotaoDoQuadro(self, BOTAO_PESQUISAR),
                       _BotaoDoQuadro(self, "Limpar Filtros")]

    def query_selector_all(self, seletor):
        if seletor == CAMPO_INICIO:
            return [] if CAMPO_INICIO in self.sem else [self.inicio]
        if seletor == CAMPO_ORIGEM:
            return [] if CAMPO_ORIGEM in self.sem else [self.origem]
        return list(self.botoes)

    def query_selector(self, seletor):
        if seletor == "#numeracaoUnica":
            return self.unica
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None


class _ItemDeMenu:
    def __init__(self, portal, nome, leva_a_consulta=False):
        self.portal, self.nome = portal, nome
        self.leva_a_consulta = leva_a_consulta

    def inner_text(self):
        return self.nome

    def get_attribute(self, _):
        return None

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 120, "height": 30}

    def click(self):
        self.portal.cliques.append(self.nome)
        if self.nome == "menu":
            self.portal.menu_aberto = True
        if self.leva_a_consulta and self.portal.o_menu_funciona:
            self.portal.url = (
                "https://www3.tjrj.jus.br/portalservicos/#/consproc/consultaportal")


class _PortalDeServicos:
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, quadro, comeca_na_consulta=True, tem_menu=True,
                 o_menu_funciona=True):
        self.quadro = quadro
        self.frames = [self, quadro]
        self.navegou = []
        self.cliques = []
        self.menu_aberto = False
        self.tem_menu = tem_menu
        self.o_menu_funciona = o_menu_funciona
        self.url = ("https://www3.tjrj.jus.br/portalservicos/#/consproc/consultaportal"
                    if comeca_na_consulta
                    else "https://www3.tjrj.jus.br/portalservicos/#/dashboard")

    def goto(self, destino, **kw):
        self.navegou.append(destino)

    def query_selector_all(self, seletor):
        if seletor == "#CONSULTAS":
            return [_ItemDeMenu(self, "menu")] if self.tem_menu else []
        if self.menu_aberto:
            return [_ItemDeMenu(self, "Consultas Processuais", True)]
        return []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def wait_for_timeout(self, _):
        pass

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_timeout(self, _):
        pass


def test_o_quadro_embutido_e_escolhido_pelo_caminho():
    """O relato da pagina de fora dizia '0 campos': o que importa esta no
    quadro."""
    quadro = _QuadroDaConsulta()
    assert quadro_da_consulta(_PortalDeServicos(quadro)) is quadro


def test_pagina_sem_quadro_devolve_ela_mesma():
    class _Sozinha:
        url = "https://x/y"
        frames = []

    sozinha = _Sozinha()
    assert quadro_da_consulta(sozinha) is sozinha


def test_a_busca_preenche_os_dois_campos_e_pesquisa():
    quadro = _QuadroDaConsulta()
    portal = _PortalDeServicos(quadro)
    buscar(portal, _Guarda(), parse_numero(PROCESSO), LOGIN, 5)
    assert quadro.inicio.valor == "0045025-93.2021"
    assert quadro.origem.valor == "0002"
    assert quadro.cliques[-1] == BOTAO_PESQUISAR


def test_a_numeracao_unica_ja_marcada_nao_e_clicada_de_novo():
    quadro = _QuadroDaConsulta(unica_marcada=True)
    buscar(_PortalDeServicos(quadro), _Guarda(), parse_numero(PROCESSO), LOGIN, 5)
    assert "numeracaoUnica" not in quadro.cliques


def test_numeracao_antiga_marcada_e_corrigida():
    """Digitar o numero unico com 'Antiga' marcada devolve 'nada encontrado',
    que o advogado leria como processo inexistente."""
    quadro = _QuadroDaConsulta(unica_marcada=False)
    buscar(_PortalDeServicos(quadro), _Guarda(), parse_numero(PROCESSO), LOGIN, 5)
    assert "numeracaoUnica" in quadro.cliques


def test_tela_sem_um_dos_campos_para_antes_de_digitar():
    quadro = _QuadroDaConsulta(sem=[CAMPO_ORIGEM])
    with pytest.raises(ConsultaIndisponivel, match="inputSufixoUnica3"):
        buscar(_PortalDeServicos(quadro), _Guarda(), parse_numero(PROCESSO), LOGIN, 1)
    assert quadro.cliques == []


def test_campo_que_so_aceita_teclado_nao_derruba_a_busca():
    """`fill` sozinho desiste em silencio em campo controlado por framework, e
    aqui desistir custaria o login inteiro."""
    quadro = _QuadroDaConsulta(aceita=False)
    buscar(_PortalDeServicos(quadro), _Guarda(), parse_numero(PROCESSO), LOGIN, 5)
    assert quadro.inicio.valor == "0045025-93.2021"
    assert quadro.cliques[-1] == BOTAO_PESQUISAR


def test_campo_que_engole_o_valor_nao_vira_pesquisa():
    """Mascara que recusa o formato deixa o campo vazio sem reclamar, e a busca
    volta 'nada encontrado' por defeito nosso."""
    quadro = _QuadroDaConsulta(aceita=False, aceita_teclado=False)
    with pytest.raises(ConsultaIndisponivel, match="nao confere"):
        buscar(_PortalDeServicos(quadro), _Guarda(), parse_numero(PROCESSO), LOGIN, 5)
    assert BOTAO_PESQUISAR not in quadro.cliques


def test_numero_de_outro_tribunal_nem_chega_a_navegar():
    quadro = _QuadroDaConsulta()
    portal = _PortalDeServicos(quadro)
    with pytest.raises(ConsultaIndisponivel, match="so serve ao Tribunal de"):
        buscar(portal, _Guarda(), parse_numero("0000001-78.2020.8.26.0100"), LOGIN, 5)
    assert portal.navegou == []


# ==========================================================================
# O caminho inteiro, ligado ao comando de consulta
# ==========================================================================

def test_o_dcp_entrou_na_lista_de_sistemas_com_consulta():
    from justica_mcp.portal import SISTEMAS_COM_CONSULTA

    assert "dcp" in SISTEMAS_COM_CONSULTA


def test_consultar_sem_documentos_nao_abre_o_visualizador():
    """Consultar e ler a capa; abrir o visualizador e entrar nos autos, e as
    duas coisas nao se confundem so porque ficam na mesma tela."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split('identidade.sistema == "dcp"')[1].split(
        'identidade.sistema == "pje"')[0]
    assert 'documentos == "nenhum"' in trecho
    assert trecho.index('documentos == "nenhum"') < trecho.index("abrir_visualizador(")


def test_o_tamanho_do_arquivo_e_sempre_dito():
    """Um PDF parcial guardado como integra nao se denuncia sozinho."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split('identidade.sistema == "dcp"')[1].split(
        'identidade.sistema == "pje"')[0]
    assert "Tamanho:" in trecho
    assert "CONFIRA se o arquivo tem o processo inteiro" in trecho
    assert "nao baixa de uma vez" in trecho


def test_a_janela_do_visualizador_e_fechada_mesmo_com_falha():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split('identidade.sistema == "dcp"')[1].split(
        'identidade.sistema == "pje"')[0]
    assert "finally:" in trecho and "_fechar(janela)" in trecho


# ==========================================================================
# A entrada no Portal de Servicos nao se pula
#
# Conferido em campo em 06/10/2026: navegar DIRETO para a consulta devolveu a
# pagina publica do tribunal, em `www.tjrj.jus.br`. A sessao do IdServerJus
# existe, e o Portal de Servicos so e alcancado pela entrega que o formulario
# de selecao de sistemas faz.
# ==========================================================================

from justica_mcp.dcp import (  # noqa: E402
    ABRIR_EM_ABA, BOTAO_ENVIAR, LISTA_DE_SISTEMAS, SIGLA_DO_PORTAL,
    entrar_no_portal_de_servicos, escolher_opcao_do_portal,
)


class _ListaDeSistemas:
    def __init__(self, tela, opcoes):
        self.tela, self.opcoes = tela, opcoes
        self.escolhido = None

    def evaluate(self, _):
        return [list(par) for par in self.opcoes]

    def select_option(self, valor):
        self.escolhido = valor

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 200, "height": 30}


class _OpcaoDeAbertura:
    def __init__(self, tela, identificador):
        self.tela, self.identificador = tela, identificador

    def click(self):
        self.tela.cliques.append(self.identificador)

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 20, "height": 20}


class _AbaNova:
    url = "https://www3.tjrj.jus.br/portalservicos/#/dashboard"

    def wait_for_load_state(self, *a, **kw):
        pass

    def is_closed(self):
        return False


class _EsperaDeAba:
    def __init__(self, tela):
        self.tela = tela

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def value(self):
        if not self.tela.abre_aba:
            raise RuntimeError("TimeoutError")
        return _AbaNova()


class _Contexto:
    def __init__(self, tela, abas=None):
        self.tela = tela
        self.pages = list(abas or [tela])

    def expect_page(self, timeout=None):
        if not self.tela.abre_aba:
            raise RuntimeError("TimeoutError: nenhuma aba nova")
        return _EsperaDeAba(self.tela)


class _TelaDeSelecao:
    url = "https://www3.tjrj.jus.br/idserverjus-front/#/selecao-sistemas"
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, opcoes=None, tem_lista=True, tem_enviar=True,
                 abre_aba=True, outras_abas=None):
        self.cliques = []
        self.abre_aba = abre_aba
        self.context = _Contexto(self, [self] + list(outras_abas or []))
        padrao = [("", "Selecione"), (SIGLA_DO_PORTAL, "Portal de Serviços"),
                  ("PORTALSEGURO", "Portal Seguro")]
        self.lista = (_ListaDeSistemas(self, opcoes if opcoes is not None else padrao)
                      if tem_lista else None)
        self.aba = _OpcaoDeAbertura(self, ABRIR_EM_ABA)
        self.enviar = _BotaoDoQuadro(self, BOTAO_ENVIAR) if tem_enviar else None

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def query_selector_all(self, seletor):
        # Responde por seletor, como o navegador: um fake que devolve o mesmo
        # elemento para tudo faz a lista de sistemas ser achada no botao.
        if seletor == LISTA_DE_SISTEMAS:
            return [self.lista] if self.lista else []
        if seletor == ABRIR_EM_ABA:
            return [self.aba]
        return [self.enviar] if self.enviar else []

    def wait_for_timeout(self, _):
        pass

    def is_closed(self):
        return False


def test_a_opcao_do_portal_e_achada_pela_sigla():
    tela = _TelaDeSelecao()
    assert escolher_opcao_do_portal(tela.lista) == SIGLA_DO_PORTAL


def test_a_opcao_do_portal_e_achada_pelo_nome_quando_a_sigla_muda():
    tela = _TelaDeSelecao(opcoes=[("PS2", "Portal de Serviços"), ("X", "Outro")])
    assert escolher_opcao_do_portal(tela.lista) == "PS2"


def test_duas_opcoes_parecidas_nao_viram_escolha():
    """Escolher no escuro levaria a sessao para outro sistema sem dizer nada."""
    tela = _TelaDeSelecao(opcoes=[("A", "Portal de Serviços"),
                                  ("B", "Portal de Serviços antigo")])
    assert escolher_opcao_do_portal(tela.lista) is None


def test_lista_sem_o_portal_devolve_nada():
    tela = _TelaDeSelecao(opcoes=[("SISENVARQ", "Envio de Arquivos")])
    assert escolher_opcao_do_portal(tela.lista) is None


def test_a_entrada_escolhe_marca_a_aba_e_envia():
    tela, guarda = _TelaDeSelecao(), _Guarda()
    janela = entrar_no_portal_de_servicos(tela, guarda, 5)
    assert tela.lista.escolhido == SIGLA_DO_PORTAL
    assert tela.cliques == [ABRIR_EM_ABA, BOTAO_ENVIAR]
    assert janela is not tela


def test_a_abertura_pedida_e_em_aba_nunca_em_janela_destacada():
    """Aba e o que o navegador entrega de forma previsivel; janela destacada
    pode ser barrada sem aviso nenhum."""
    from justica_mcp.dcp import ABRIR_EM_JANELA

    tela, guarda = _TelaDeSelecao(), _Guarda()
    entrar_no_portal_de_servicos(tela, guarda, 5)
    assert ABRIR_EM_JANELA not in tela.cliques


def test_sem_aba_nova_e_sem_portal_o_comando_recusa():
    """Este teste guardava o contrario ate 06/10/2026.

    Ele exigia `is tela`: sem janela nova, devolver a propria aba de selecao e
    deixar a conferencia do formulario julgar. O acompanhamento conduzido pelo
    advogado mostrou que a aba de origem volta para `www.tjrj.jus.br`, e a
    consulta seguia procurando o processo na pagina publica do tribunal. Parar
    aqui, dizendo onde o programa esta, e melhor que seguir na tela errada.
    """
    tela, guarda = _TelaDeSelecao(abre_aba=False), _Guarda()
    with pytest.raises(ConsultaIndisponivel, match="janela propria"):
        entrar_no_portal_de_servicos(tela, guarda, 5)


def test_sem_aba_nova_a_propria_tela_serve_quando_ELA_e_o_portal():
    """O portal as vezes abre na propria aba, e ai nao ha nada a recusar."""
    tela, guarda = _TelaDeSelecao(abre_aba=False), _Guarda()
    tela.url = "https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil"
    assert entrar_no_portal_de_servicos(tela, guarda, 5) is tela


def test_tela_sem_a_lista_para_sem_escolher():
    tela, guarda = _TelaDeSelecao(tem_lista=False), _Guarda()
    with pytest.raises(ConsultaIndisponivel, match="nao tem #sistema"):
        entrar_no_portal_de_servicos(tela, guarda, 1)
    assert tela.cliques == []


def test_tela_sem_o_enviar_para_sem_escolher():
    tela, guarda = _TelaDeSelecao(tem_enviar=False), _Guarda()
    with pytest.raises(ConsultaIndisponivel, match="Enviar"):
        entrar_no_portal_de_servicos(tela, guarda, 5)
    assert tela.lista.escolhido is None


def test_a_consulta_passa_pela_selecao_antes_de_buscar():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split('identidade.sistema == "dcp"')[1].split(
        'identidade.sistema == "pje"')[0]
    assert trecho.index("entrar_no_portal_de_servicos(") < trecho.index("buscar_dcp(")
    assert "devolveu a" in trecho and "pagina publica" in trecho


# ==========================================================================
# Tipo de usuario, em `#/usuarios/alterar-perfil`
#
# Tela fotografada em 06/10/2026, logo depois de o Portal de Servicos abrir.
# Duas opcoes, "Usuario Comum" e "Advogado", e o botao "Entrar" so habilita
# depois da escolha.
# ==========================================================================

from justica_mcp.dcp import (  # noqa: E402
    PerfilNaoInformado, escolher_perfil, na_tela_de_perfil, perfis_oferecidos,
)


class _ListaDePerfil:
    def __init__(self, tela, textos):
        self.tela, self.textos = tela, textos
        self.escolhido = None

    def evaluate(self, roteiro):
        if "selectedOptions" in roteiro or roteiro == "e => e.value || ''":
            return self.escolhido or ""
        return list(self.textos)

    def select_option(self, label=None, **kw):
        self.escolhido = label

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 200, "height": 30}


class _CaixaComRotulo:
    """A caixa do tipo de usuario e `input[type=text]`, nao botao: o unico
    rotulo dela e o texto cinza que mostra."""

    def __init__(self, tela, rotulo):
        self.tela, self.rotulo = tela, rotulo
        self.valor = ""

    def get_attribute(self, nome):
        return self.rotulo if nome == "placeholder" else None

    def evaluate(self, _):
        return self.valor

    def inner_text(self):
        return self.valor

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 200, "height": 30}

    def click(self):
        self.tela.cliques.append(self.rotulo)
        if self.tela.abre_no_clique:
            self.tela.aberta = True

    def type(self, texto, delay=None):
        self.tela.digitado = texto
        self.tela.aberta = True
        self.valor = ""


class _ItemDaLista:
    """Opcao empilhada por script, que nao e botao nem `option`."""

    def __init__(self, tela, texto):
        self.tela, self.texto = tela, texto

    def inner_text(self):
        return self.texto

    def get_attribute(self, _):
        return None

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 180, "height": 24}

    def click(self):
        self.tela.cliques.append(self.texto)
        if self.tela.caixa is not None and self.tela.assume_o_valor:
            self.tela.caixa.valor = self.texto


class _ListaAberta:
    """O `ul#resultados` da tela de perfil, presente so quando a lista abriu."""

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 10, "y": 120, "width": 240, "height": 90}


class _TelaDePerfil:
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, url="https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil",
                 com_select=True, textos=("Usuário Comum", "Advogado"),
                 abre_no_clique=True, assume_o_valor=True):
        self.url = url
        self.cliques = []
        self.aberta = False
        self.abre_no_clique = abre_no_clique
        self.assume_o_valor = assume_o_valor
        self.digitado = None
        self.textos = list(textos)
        self.lista = _ListaDePerfil(self, textos) if com_select else None
        self.caixa = (None if com_select
                      else _CaixaComRotulo(self, "Selecione perfil do usuário"))
        self.botoes = [_BotaoDoQuadro(self, "Entrar"),
                       _BotaoDoQuadro(self, "Cancelar")]
        self.destino_do_entrar = (
            "https://www3.tjrj.jus.br/portalservicos/#/dashboard")

    def query_selector_all(self, seletor):
        from justica_mcp.dcp import (CAIXA_DO_PERFIL, CAMPO_DO_PERFIL,
                                     ITEM_DA_LISTA, LISTA_DE_RESULTADOS,
                                     SETA_DO_PERFIL)

        if seletor.startswith("select"):
            return [self.lista] if self.lista else []
        # O `input` de verdade, dentro do custom element. No portal real o
        # MESMO `placeholder` esta no hospedeiro e no campo, e ate 07/10/2026
        # o programa pegava o hospedeiro. Aqui os dois seletores levam ao
        # mesmo objeto: o que o teste exerce e o caminho, nao a casca.
        if seletor == CAMPO_DO_PERFIL:
            return [self.caixa] if self.caixa else []
        if seletor in (CAIXA_DO_PERFIL, SETA_DO_PERFIL):
            return []
        if seletor.startswith("[") and "placeholder" in seletor:
            return [self.caixa] if self.caixa else []
        if seletor.startswith("["):
            return []
        # O `ul` da lista, pelo identificador real lido na tela em 06/10/2026.
        # So existe quando a lista esta aberta: e ele que separa "a lista nao
        # abriu" de "a lista abriu e nao tem essa opcao".
        if seletor == LISTA_DE_RESULTADOS:
            return [_ListaAberta()] if self.aberta else []
        if seletor in (ITEM_DA_LISTA, "li"):
            return ([_ItemDaLista(self, t) for t in self.textos]
                    if self.aberta else [])
        # `option` e lugar de opcao, nao de botao: devolver os botoes aqui
        # fazia "Entrar" e "Cancelar" entrarem no relato das opcoes.
        if seletor == "option":
            return []
        return list(self.botoes)

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def wait_for_timeout(self, _):
        pass

    def wait_for_load_state(self, *a, **kw):
        pass


def test_a_tela_de_perfil_e_reconhecida_pelo_endereco():
    assert na_tela_de_perfil(_TelaDePerfil()) is True


def test_outra_tela_nao_e_confundida_com_a_de_perfil():
    tela = _TelaDePerfil(url="https://www3.tjrj.jus.br/portalservicos/#/dashboard")
    tela.botoes = [_BotaoDoQuadro(tela, "Atualizar")]
    assert na_tela_de_perfil(tela, segundos=1) is False


def test_os_perfis_oferecidos_sao_lidos():
    assert perfis_oferecidos(_TelaDePerfil()) == ["Usuário Comum", "Advogado"]


def test_sem_perfil_informado_o_comando_para_e_lista_as_opcoes():
    """Entrar como 'Usuario Comum' devolveria uma visao reduzida sem avisar, e
    consulta que volta vazia e indistinguivel de processo inexistente."""
    with pytest.raises(PerfilNaoInformado) as erro:
        escolher_perfil(_TelaDePerfil(), _Guarda(), None, 5)
    recado = str(erro.value)
    assert "--perfil" in recado
    assert "Advogado" in recado and "Usuário Comum" in recado
    assert "visao reduzida" in recado


def test_o_perfil_nomeado_pelo_operador_e_escolhido_e_enviado():
    tela, guarda = _TelaDePerfil(), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 5)
    assert tela.lista.escolhido == "Advogado"
    assert tela.cliques == ["Entrar"]


def test_o_acento_do_perfil_nao_atrapalha():
    tela, guarda = _TelaDePerfil(), _Guarda()
    escolher_perfil(tela, guarda, "Usuario Comum", 5)
    assert tela.lista.escolhido == "Usuário Comum"


def test_perfil_que_nao_casa_com_uma_opcao_para():
    with pytest.raises(PerfilNaoInformado, match="nao casa com UMA opcao"):
        escolher_perfil(_TelaDePerfil(), _Guarda(), "Magistrado", 5)


def test_lista_montada_por_script_e_aberta_pelo_proprio_rotulo():
    """Sem `select`, a tela e aberta pelo rotulo que ela mostra e a opcao e
    clicada por texto exato, que foi o que o operador nomeou."""
    tela, guarda = _TelaDePerfil(com_select=False), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 5)
    assert tela.cliques == ["Selecione perfil do usuário", "Advogado", "Entrar"]


def test_a_consulta_pergunta_o_perfil_antes_de_buscar():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split('identidade.sistema == "dcp"')[1].split(
        'identidade.sistema == "pje"')[0]
    assert trecho.index("na_tela_de_perfil(pagina)") < trecho.index("buscar_dcp(")
    assert "escolher_perfil(pagina, guarda, perfil, segundos)" in trecho


# ==========================================================================
# O portal abre em JANELA PROPRIA
#
# Conferido em campo em 06/10/2026: o comando anunciava "a lista nao esta
# nela" com o endereco em `www.tjrj.jus.br`, enquanto o Portal de Servicos
# estava aberto e pedindo o tipo de usuario em outra janela, que o advogado
# estava vendo na tela. A aba de origem volta para a pagina publica do
# tribunal, e olhar so nela nunca acha o portal.
# ==========================================================================

from justica_mcp.dcp import MARCA_DO_PORTAL, achar_aba_do_portal  # noqa: E402


def test_o_portal_e_achado_em_outra_aba():
    portal_aberto = _AbaNova()
    tela = _TelaDeSelecao(outras_abas=[portal_aberto])
    assert achar_aba_do_portal(tela, 2) is portal_aberto


def test_sem_aba_do_portal_devolve_nada():
    assert achar_aba_do_portal(_TelaDeSelecao(), 1) is None


def test_a_entrada_usa_a_janela_ja_aberta_sem_selecionar_nada():
    """Se o portal ja esta aberto noutra janela, selecionar de novo seria
    mexer numa tela que ja cumpriu o papel dela."""
    portal_aberto = _AbaNova()
    tela, guarda = _TelaDeSelecao(outras_abas=[portal_aberto]), _Guarda()
    assert entrar_no_portal_de_servicos(tela, guarda, 5) is portal_aberto
    assert tela.cliques == []
    assert tela.lista.escolhido is None


def test_a_aba_de_origem_na_pagina_publica_nao_vira_recusa():
    """O endereco da aba de origem nao diz nada sobre onde o portal esta."""
    publica = _TelaDeSelecao(tem_lista=False,
                             outras_abas=[_AbaNova()])
    publica.url = "https://www.tjrj.jus.br/"
    janela = entrar_no_portal_de_servicos(publica, _Guarda(), 5)
    assert MARCA_DO_PORTAL in janela.url


# ==========================================================================
# A caixa do tipo de usuario e CAMPO, e as opcoes nao sao botoes
#
# Relatorio da tela real, 06/10/2026:
#   CAMPOS NA TELA: (sem id) tipo=text rotulo='Selecione perfil do usuário'
#   BOTOES NA TELA: 'Entrar', 'Cancelar'
# A caixa aparece entre os CAMPOS, nao entre os botoes. Procurar por texto de
# botao nao acha nada ali, porque texto de campo nao e texto de botao.
# ==========================================================================

from justica_mcp.dcp import achar_opcao_na_lista  # noqa: E402


def test_a_caixa_e_achada_pelo_texto_cinza_que_ela_mostra():
    from justica_mcp.portal import elemento_por_rotulo

    tela = _TelaDePerfil(com_select=False)
    achada = elemento_por_rotulo(tela, "Selecione perfil do usuário")
    assert achada is not None


def test_a_opcao_e_achada_mesmo_sem_ser_botao():
    """Lista montada por script empilha `li`, que nao entra na busca por
    elemento clicavel."""
    tela = _TelaDePerfil(com_select=False)
    tela.aberta = True
    assert achar_opcao_na_lista(tela, "Advogado") is not None


def test_a_opcao_nao_casa_por_prefixo():
    """"Advogado" e "Advogado (suspenso)" sao escolhas diferentes, e aceitar
    prefixo escolheria a errada."""
    tela = _TelaDePerfil(com_select=False, textos=("Advogado (suspenso)",))
    tela.aberta = True
    assert achar_opcao_na_lista(tela, "Advogado") is None


def test_lista_fechada_nao_entrega_opcao():
    tela = _TelaDePerfil(com_select=False)
    assert achar_opcao_na_lista(tela, "Advogado") is None


def test_o_caminho_sem_select_abre_a_caixa_escolhe_e_entra():
    tela, guarda = _TelaDePerfil(com_select=False), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 5)
    assert tela.cliques == ["Selecione perfil do usuário", "Advogado", "Entrar"]


# ==========================================================================
# A lista nao abre instantaneamente, e pode nem abrir no clique
#
# 06/10/2026: a caixa foi clicada, conforme o relato da trava, e a opcao foi
# anunciada como ausente. Olhar meio segundo depois do clique pegava a tela
# ainda sem a lista, que e montada por script e com animacao.
# ==========================================================================

from justica_mcp.dcp import esperar_opcao_na_lista, opcoes_a_vista  # noqa: E402


class _ListaLenta(_TelaDePerfil):
    """A lista so aparece depois de algumas olhadas."""

    def __init__(self, olhadas_ate_abrir, **kw):
        super().__init__(com_select=False, **kw)
        self.olhadas = 0
        self.ate_abrir = olhadas_ate_abrir
        self.aberta = True

    def query_selector_all(self, seletor):
        from justica_mcp.dcp import ITEM_DA_LISTA

        # Os DOIS lugares, e nao so `li`: desde que o identificador real
        # `li[id^=itemAutocomplete]` passou a ser a primeira tentativa, atrasar
        # apenas `li` deixava a opcao aparecer de imediato pelo outro caminho,
        # e a lista "lenta" deixava de ser lenta sem que o nome do teste
        # mudasse.
        if seletor in (ITEM_DA_LISTA, "li"):
            self.olhadas += 1
            if self.olhadas < self.ate_abrir:
                return []
        return super().query_selector_all(seletor)


def test_opcao_que_demora_a_aparecer_e_esperada():
    tela = _ListaLenta(olhadas_ate_abrir=4)
    assert esperar_opcao_na_lista(tela, "Advogado", 5) is not None


def test_opcao_que_nunca_aparece_devolve_nada():
    tela = _ListaLenta(olhadas_ate_abrir=10**9)
    assert esperar_opcao_na_lista(tela, "Advogado", 1) is None


def test_caixa_que_nao_abre_no_clique_recebe_o_nome_digitado():
    """A caixa e `input[type=text]`: pode ser de digitar e filtrar, e nesse
    caso o clique sozinho nao abre lista nenhuma."""
    tela, guarda = _TelaDePerfil(com_select=False, abre_no_clique=False), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 2)
    assert tela.digitado == "Advogado"
    assert tela.cliques[-1] == "Entrar"


def test_digitar_usa_o_nome_que_o_operador_deu():
    """Digitar nao e escolher por conta propria: e o mesmo valor, por outro
    caminho."""
    tela, guarda = _TelaDePerfil(com_select=False, abre_no_clique=False), _Guarda()
    escolher_perfil(tela, guarda, "Usuario Comum", 2)
    assert tela.digitado == "Usuario Comum"


def test_a_recusa_diz_o_que_a_lista_mostrou():
    tela = _TelaDePerfil(com_select=False, textos=("Usuário Comum",))
    tela.aberta = True
    with pytest.raises(PerfilNaoInformado) as erro:
        escolher_perfil(tela, _Guarda(), "Advogado", 2)
    recado = str(erro.value)
    assert "A lista mostra: Usuário Comum" in recado
    assert "digitado nela" in recado


def test_a_recusa_diz_quando_a_lista_abriu_e_esta_vazia():
    """Lista aberta e sem opcao nenhuma e informacao sobre o PORTAL.

    Ate 06/10/2026 este caso saia com a mesma frase de "a lista nao abriu",
    porque a unica prova era haver ou nao texto de opcao. Com `ul#resultados`,
    lido na tela naquele dia, as duas perguntas se separam.
    """
    tela = _TelaDePerfil(com_select=False, abre_no_clique=False, textos=())
    with pytest.raises(PerfilNaoInformado, match="ESTA aberta e vazia"):
        escolher_perfil(tela, _Guarda(), "Advogado", 2)


def test_a_recusa_diz_quando_a_lista_nao_chegou_a_abrir():
    """Lista que nao abre e defeito MEU, de clique ou de espera.

    O operador nao pode fazer nada a respeito, e precisa saber disso: a frase
    antiga o mandava conferir o nome do perfil, que estava certo o tempo todo.
    """
    tela = _TelaDePerfil(com_select=False, abre_no_clique=False, textos=())

    # Nem o clique nem o que for digitado abrem esta lista.
    tela.caixa.type = lambda texto, delay=None: None

    with pytest.raises(PerfilNaoInformado, match="nao chegou a abrir"):
        escolher_perfil(tela, _Guarda(), "Advogado", 2)


def test_o_relato_das_opcoes_corta_texto_longo():
    """A mesma forma de lista serve para escolher processo, e ali o texto seria
    dado de cliente."""
    tela = _TelaDePerfil(com_select=False, textos=("Advogado", "x" * 80))
    tela.aberta = True
    assert opcoes_a_vista(tela) == ["Advogado"]


# ==========================================================================
# A trava barrando o proprio programa
#
# 06/10/2026: o comando terminou em traceback no meio da escolha do perfil. A
# autorizacao liberava `select` para preencher, e o caminho de digitar usa a
# caixa. A trava fez o que devia; a autorizacao e que estava incompleta.
# ==========================================================================

def test_a_caixa_e_liberada_para_clicar_e_para_preencher():
    """Ela e clicada para abrir a lista e, quando a lista nao abre, recebe o
    nome digitado."""
    from justica_mcp.dcp import SELETOR_DA_CAIXA_DE_PERFIL

    tela, guarda = _TelaDePerfil(com_select=False, abre_no_clique=False), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 2)
    permissao = guarda.permissoes[0]
    assert SELETOR_DA_CAIXA_DE_PERFIL in permissao.seletores_clicaveis
    assert SELETOR_DA_CAIXA_DE_PERFIL in permissao.seletores_preenchiveis


def test_o_select_continua_liberado_para_preencher():
    from justica_mcp.dcp import SELETOR_DA_CAIXA_DE_PERFIL

    tela, guarda = _TelaDePerfil(), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 2)
    assert "select" in guarda.permissoes[0].seletores_preenchiveis


def test_trava_barrando_o_programa_nao_vira_traceback():
    """O operador nao tem o que fazer com um traceback, e ele parece defeito
    grave do navegador."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split('identidade.sistema == "dcp"')[1].split(
        'identidade.sistema == "pje"')[0]
    assert "except NavegacaoBloqueada as exc:" in trecho
    assert "defeito deste programa, nao do portal" in trecho


# ==========================================================================
# Prova positiva antes de enviar
#
# Nas telas fotografadas em 06/10/2026 o botao "Entrar" nasce desabilitado,
# em verde claro, e so fica verde forte depois de o controle assumir o perfil.
# Clicar nele antes disso nao faz nada, e sem conferir o comando seguiria como
# se tivesse entrado.
# ==========================================================================

from justica_mcp.dcp import perfil_assumido_pelo_controle  # noqa: E402


def test_o_select_que_assumiu_o_perfil_e_prova():
    tela, guarda = _TelaDePerfil(), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 2)
    assert perfil_assumido_pelo_controle(tela, "Advogado") is True


def test_a_caixa_que_assumiu_o_perfil_e_prova():
    tela, guarda = _TelaDePerfil(com_select=False), _Guarda()
    escolher_perfil(tela, guarda, "Advogado", 2)
    assert perfil_assumido_pelo_controle(tela, "Advogado") is True


def test_controle_que_nao_assume_impede_o_envio():
    """Clicar num botao que ainda nao habilitou nao faz nada, e seguir dali
    seria dar o perfil por escolhido sem estar."""
    tela = _TelaDePerfil(com_select=False, assume_o_valor=False)
    with pytest.raises(PerfilNaoInformado, match="nao passou a mostra-la"):
        escolher_perfil(tela, _Guarda(), "Advogado", 2)
    assert "Entrar" not in tela.cliques


def test_a_prova_vem_antes_do_clique_em_entrar():
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.escolher_perfil)
    assert fonte.index("perfil_assumido_pelo_controle(") < fonte.index(
        "clicar_com_jeito(entrar)")


# ==========================================================================
# A consulta se alcanca pelo MENU, nunca por endereco
#
# 06/10/2026: navegar para `#/consproc/consultaportal` com a sessao aberta
# devolveu a pagina publica do tribunal. Rota `#/` nao e endereco novo para o
# navegador, e sim estado interno da aplicacao: mandar o navegador ir ate la
# RECARREGA a pagina, a aplicacao perde o que tinha em memoria e o portal
# manda o visitante para fora.
# ==========================================================================

from justica_mcp.dcp import (  # noqa: E402
    ITEM_DA_CONSULTA, MENU_DE_CONSULTAS, abrir_consulta_pelo_menu,
    ja_esta_na_consulta,
)


def test_a_consulta_e_alcancada_clicando_no_menu():
    portal = _PortalDeServicos(_QuadroDaConsulta(), comeca_na_consulta=False)
    abrir_consulta_pelo_menu(portal, _Guarda(), 5)
    assert portal.cliques == ["menu", ITEM_DA_CONSULTA]
    assert ja_esta_na_consulta(portal)


def test_quem_ja_esta_na_consulta_nao_clica_em_nada():
    portal = _PortalDeServicos(_QuadroDaConsulta(), comeca_na_consulta=True)
    abrir_consulta_pelo_menu(portal, _Guarda(), 5)
    assert portal.cliques == []


def test_a_busca_nao_navega_por_endereco():
    """O `goto` para rota `#/` e justamente o que derrubava a sessao."""
    portal = _PortalDeServicos(_QuadroDaConsulta(), comeca_na_consulta=False)
    buscar(portal, _Guarda(), parse_numero(PROCESSO), LOGIN, 5)
    assert portal.navegou == []


def test_sem_o_menu_a_busca_para_sem_digitar():
    quadro = _QuadroDaConsulta()
    portal = _PortalDeServicos(quadro, comeca_na_consulta=False, tem_menu=False)
    with pytest.raises(ConsultaIndisponivel, match=MENU_DE_CONSULTAS):
        buscar(portal, _Guarda(), parse_numero(PROCESSO), LOGIN, 1)
    assert quadro.cliques == []


def test_clique_que_nao_leva_a_consulta_e_denunciado():
    """Prova positiva de que o clique levou aonde devia, em vez de confiar
    nele."""
    quadro = _QuadroDaConsulta()
    portal = _PortalDeServicos(quadro, comeca_na_consulta=False,
                               o_menu_funciona=False)
    with pytest.raises(ConsultaIndisponivel, match="nao chegou a consulta"):
        buscar(portal, _Guarda(), parse_numero(PROCESSO), LOGIN, 1)
    assert quadro.cliques == []


def test_a_janela_do_portal_e_a_mais_RECENTE():
    """Janela nova e acrescentada ao fim da lista, e a aba de ORIGEM pode
    exibir o endereco do portal por um instante durante a entrega, antes de
    voltar para a pagina publica. Pegando a primeira, o programa ficava com a
    aba que ia embora."""
    origem = _AbaNova()
    origem.url = "https://www3.tjrj.jus.br/portalservicos/"
    nova = _AbaNova()
    tela = _TelaDeSelecao(outras_abas=[origem, nova])
    assert achar_aba_do_portal(tela, 2) is nova


# ==========================================================================
# A janela do portal, conferida em vez de suposta
#
# O acompanhamento conduzido pelo advogado em 06/10/2026 provou tres coisas
# que ate ali eram deducao: o portal abre em JANELA PROPRIA, a aba de origem
# volta para `www.tjrj.jus.br`, e o menu `#CONSULTAS` so existe no painel,
# depois de o tipo de usuario ser escolhido. O caminho terminava em
# `return pagina`, devolvia a aba de origem, e a consulta seguia em cima da
# pagina publica do tribunal.
# ==========================================================================

class _AbaComEndereco:
    def __init__(self, url, contexto=None):
        self.url = url
        self.context = contexto

    def is_closed(self):
        return False

    def wait_for_timeout(self, _ms):
        pass


class _ContextoDeAbas:
    def __init__(self, abas):
        self.pages = abas


def test_a_janela_que_e_o_portal_e_devolvida():
    from justica_mcp.dcp import MARCA_DO_PORTAL, conferir_janela_do_portal

    janela = _AbaComEndereco(f"https://www3.tjrj.jus.br{MARCA_DO_PORTAL}/#/dashboard")
    origem = _AbaComEndereco("https://www.tjrj.jus.br/")
    assert conferir_janela_do_portal(janela, origem) is janela


def test_a_aba_de_origem_serve_quando_o_portal_abriu_nela_mesma():
    from justica_mcp.dcp import MARCA_DO_PORTAL, conferir_janela_do_portal

    origem = _AbaComEndereco(f"https://www3.tjrj.jus.br{MARCA_DO_PORTAL}/#/x")
    assert conferir_janela_do_portal(None, origem) is origem


def test_a_janela_que_nao_e_o_portal_cede_lugar_a_aba_certa():
    """`expect_page` entrega qualquer janela nova, nao necessariamente o portal."""
    from justica_mcp.dcp import MARCA_DO_PORTAL, conferir_janela_do_portal

    certa = _AbaComEndereco(f"https://www3.tjrj.jus.br{MARCA_DO_PORTAL}/#/dashboard")
    propaganda = _AbaComEndereco("https://aviso.example/promo")
    origem = _AbaComEndereco("https://www.tjrj.jus.br/")
    contexto = _ContextoDeAbas([origem, certa, propaganda])
    for aba in (certa, propaganda, origem):
        aba.context = contexto

    assert conferir_janela_do_portal(propaganda, origem) is certa


def test_sem_portal_em_aba_nenhuma_o_comando_recusa_em_vez_de_seguir():
    """Devolver a aba errada e pior que parar: a consulta leria outra tela."""
    from justica_mcp.dcp import ConsultaIndisponivel, conferir_janela_do_portal

    origem = _AbaComEndereco("https://www.tjrj.jus.br/")
    origem.context = _ContextoDeAbas([origem])

    try:
        conferir_janela_do_portal(None, origem, segundos=1)
    except ConsultaIndisponivel as erro:
        recado = str(erro)
        assert "janela propria" in recado
        assert "Nada foi consultado." in recado
        # A recusa diz ONDE o programa esta, senao o operador tenta de novo as cegas.
        assert "https://www.tjrj.jus.br/" in recado
    else:
        raise AssertionError("seguiu com a aba de origem")


def test_a_recusa_nao_leva_parametro_de_aba():
    """E no parametro que viajam identificador de cliente e numero de processo."""
    from justica_mcp.dcp import ConsultaIndisponivel, conferir_janela_do_portal

    origem = _AbaComEndereco("https://www.tjrj.jus.br/busca?processo=0045025&parte=Fulano")
    origem.context = _ContextoDeAbas([origem])

    try:
        conferir_janela_do_portal(None, origem, segundos=1)
    except ConsultaIndisponivel as erro:
        assert "0045025" not in str(erro)
        assert "Fulano" not in str(erro)
    else:
        raise AssertionError("seguiu com a aba de origem")


def test_o_caminho_do_portal_nao_devolve_mais_a_aba_de_origem_as_cegas():
    """O `return pagina` cego foi o que entregou a pagina publica a consulta."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.entrar_no_portal_de_servicos)
    # Os dois finais passam pela conferencia.
    assert fonte.count("conferir_janela_do_portal(") == 2
    # Sobram dois `return pagina`, e CADA UM deles vem logo depois de conferir
    # o endereco: devolvem a aba de origem porque O PORTAL ESTA NELA. O que foi
    # removido era o do fim, que a devolvia sem olhar endereco nenhum.
    linhas = fonte.splitlines()
    devolucoes = [i for i, l in enumerate(linhas) if l.strip() == "return pagina"]
    assert devolucoes, "o caminho deixou de poder devolver a propria aba"
    for i in devolucoes:
        anteriores = "\n".join(linhas[max(0, i - 3):i])
        assert "MARCA_DO_PORTAL in (pagina.url" in anteriores, (
            f"a linha {i + 1} devolve a aba de origem sem conferir o endereco")


# ==========================================================================
# O menu da consulta so existe DEPOIS do tipo de usuario
# ==========================================================================

def test_a_recusa_do_menu_diz_que_ele_so_existe_depois_do_perfil():
    from justica_mcp.dcp import (ConsultaIndisponivel, MENU_DE_CONSULTAS,
                                 TELA_DE_PERFIL, abrir_consulta_pelo_menu)

    class _SemMenu:
        url = "https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil"

        def query_selector(self, _s):
            return None

        def query_selector_all(self, _s):
            return []

        def wait_for_timeout(self, _ms):
            pass

    class _Guarda:
        permissoes = []

        def pode_executar(self, *a, **k):
            pass

    try:
        abrir_consulta_pelo_menu(_SemMenu(), _Guarda(), segundos=1)
    except ConsultaIndisponivel as erro:
        recado = str(erro)
        assert MENU_DE_CONSULTAS in recado
        assert TELA_DE_PERFIL in recado
        assert "TIPO DE USUARIO" in recado
    else:
        raise AssertionError("nao recusou")


# ==========================================================================
# Os identificadores reais da lista de perfil
# ==========================================================================

def test_a_opcao_do_perfil_e_achada_pelo_identificador_real():
    """`li#itemAutocomplete0`, lido na tela em 06/10/2026."""
    from justica_mcp.dcp import ITEM_DA_LISTA, achar_opcao_na_lista

    class _Item:
        def __init__(self, texto):
            self.texto = texto

        def inner_text(self):
            return self.texto

        def is_visible(self):
            return True

        def bounding_box(self):
            return {"x": 10, "y": 10, "width": 180, "height": 30}

    comum, advogado = _Item("Usuário Comum"), _Item("Advogado")

    class _Tela:
        url = "https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil"
        pedidos = []

        def query_selector_all(self, seletor):
            _Tela.pedidos.append(seletor)
            return [comum, advogado] if seletor == ITEM_DA_LISTA else []

        def evaluate(self, _s):
            return {"width": 1280, "height": 800}

    assert achar_opcao_na_lista(_Tela(), "Advogado") is advogado
    # O identificador real e a PRIMEIRA tentativa, e nao a ultima.
    assert _Tela.pedidos[0] == ITEM_DA_LISTA


def test_a_recusa_separa_lista_que_nao_abriu_de_lista_sem_a_opcao():
    """Sao duas falhas diferentes: uma e minha, a outra e do portal."""
    from justica_mcp.dcp import LISTA_DE_RESULTADOS, lista_de_opcoes_aberta

    class _Lista:
        def is_visible(self):
            return True

        def bounding_box(self):
            return {"x": 10, "y": 10, "width": 200, "height": 80}

    class _Aberta:
        def query_selector_all(self, seletor):
            return [_Lista()] if seletor == LISTA_DE_RESULTADOS else []

        def evaluate(self, _s):
            return {"width": 1280, "height": 800}

    class _Fechada:
        def query_selector_all(self, _s):
            return []

        def evaluate(self, _s):
            return {"width": 1280, "height": 800}

    assert lista_de_opcoes_aberta(_Aberta()) is True
    assert lista_de_opcoes_aberta(_Fechada()) is False


# ==========================================================================
# A aba que o programa segura NAO e estavel
#
# Corrida de 06/10/2026: `expect_page` entregou uma janela em
# `/portalservicos/`, sem rota nenhuma. O endereco conferia no instante em
# que foi olhado. Um segundo depois aquela janela era `www.tjrj.jus.br`, e o
# portal de verdade estava em OUTRA, ja em `#/usuarios/alterar-perfil`. O
# comando levou a pagina publica do tribunal por tres passos e parou
# anunciando, a cada um, um defeito que nao existia.
# ==========================================================================

class _AbaDeRota(_AbaComEndereco):
    """Aba que muda de endereco depois de ser olhada N vezes."""

    def __init__(self, inicial, depois, olhadas_ate_mudar, contexto=None):
        super().__init__(inicial, contexto)
        self._depois = depois
        self._olhadas = 0
        self._ate_mudar = olhadas_ate_mudar

    @property
    def url(self):
        self._olhadas += 1
        return self._valor if self._olhadas <= self._ate_mudar else self._depois

    @url.setter
    def url(self, valor):
        self._valor = valor


def test_a_raiz_do_portal_nao_e_aceita_quando_ha_uma_rota():
    from justica_mcp.dcp import conferir_janela_do_portal

    passagem = _AbaComEndereco("https://www3.tjrj.jus.br/portalservicos/")
    certa = _AbaComEndereco(
        "https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil")
    origem = _AbaComEndereco("https://www.tjrj.jus.br/")
    contexto = _ContextoDeAbas([origem, passagem, certa])
    for aba in (origem, passagem, certa):
        aba.context = contexto

    # A janela de passagem casa com `/portalservicos`, e e justamente ela que
    # vai embora. A que ja assumiu rota e a que fica.
    assert conferir_janela_do_portal(passagem, origem) is certa


def test_a_raiz_ainda_serve_quando_rota_nenhuma_aparece():
    """Recusar seria pior: o portal pode so estar demorando a montar."""
    from justica_mcp.dcp import conferir_janela_do_portal

    raiz = _AbaComEndereco("https://www3.tjrj.jus.br/portalservicos/")
    origem = _AbaComEndereco("https://www.tjrj.jus.br/")
    contexto = _ContextoDeAbas([origem, raiz])
    for aba in (origem, raiz):
        aba.context = contexto

    assert conferir_janela_do_portal(raiz, origem, segundos=1) is raiz


def test_a_rota_e_distinguida_da_raiz():
    from justica_mcp.dcp import tem_rota_do_portal

    assert tem_rota_do_portal(
        "https://www3.tjrj.jus.br/portalservicos/#/dashboard") is True
    assert tem_rota_do_portal("https://www3.tjrj.jus.br/portalservicos/") is False
    assert tem_rota_do_portal("https://www.tjrj.jus.br/") is False
    assert tem_rota_do_portal(None) is False


def test_o_portal_e_reencontrado_quando_a_aba_segurada_foi_embora():
    """O coracao do defeito: a pagina que o programa segura mudou sozinha."""
    from justica_mcp.dcp import reencontrar_o_portal

    foi_embora = _AbaComEndereco("https://www.tjrj.jus.br/")
    certa = _AbaComEndereco(
        "https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil")
    contexto = _ContextoDeAbas([foi_embora, certa])
    for aba in (foi_embora, certa):
        aba.context = contexto

    assert reencontrar_o_portal(foi_embora, segundos=1) is certa


def test_reencontrar_nao_recusa_quando_nao_acha():
    """Quem recusa e o passo seguinte, que sabe o que procurava."""
    from justica_mcp.dcp import reencontrar_o_portal

    sozinha = _AbaComEndereco("https://www.tjrj.jus.br/")
    sozinha.context = _ContextoDeAbas([sozinha])

    assert reencontrar_o_portal(sozinha, segundos=1) is sozinha


def test_a_aba_escolhida_e_trazida_para_a_frente():
    """Em janela visivel, o Chromium nao calcula posicao de aba que esta atras,
    e o clique do Playwright depende disso."""
    from justica_mcp.dcp import reencontrar_o_portal

    class _AbaQueAnota(_AbaComEndereco):
        def __init__(self, url):
            super().__init__(url)
            self.veio_para_a_frente = False

        def bring_to_front(self):
            self.veio_para_a_frente = True

    certa = _AbaQueAnota(
        "https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil")
    certa.context = _ContextoDeAbas([certa])

    assert reencontrar_o_portal(certa, segundos=1) is certa
    assert certa.veio_para_a_frente is True


def test_navegador_que_recusa_o_foco_nao_derruba_a_consulta():
    """Perder a consulta por causa do foco seria desproporcional."""
    from justica_mcp.dcp import trazer_para_a_frente

    class _Recusa:
        def bring_to_front(self):
            raise RuntimeError("sem suporte")

    aba = _Recusa()
    assert trazer_para_a_frente(aba) is aba


def test_o_caminho_reencontra_o_portal_a_cada_fronteira():
    """Guarda de fonte: carregar a pagina entre passos foi o defeito."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert fonte.count("reencontrar_o_portal(pagina") == 2
    # A primeira vem antes de a tela de perfil ser olhada.
    assert fonte.index("reencontrar_o_portal(pagina") < fonte.index(
        "if na_tela_de_perfil(pagina):")


# ==========================================================================
# "e possivel listar as opcoes que aparecem?"
#
# Pergunta do advogado em 06/10/2026, depois de a escolha do perfil falhar
# duas vezes. As buscas desta familia exigem elemento VISIVEL e DENTRO da
# janela; quando nao acham nada, as duas exigencias ficam indistinguiveis de
# "nao existe". Sao tres respostas diferentes, com tres consertos
# diferentes, e ate aqui saiam todas com a mesma frase.
# ==========================================================================

class _ElementoDeTela:
    def __init__(self, texto, visivel=True, caixa=None):
        self.texto, self._visivel = texto, visivel
        self._caixa = caixa if caixa is not None else {
            "x": 10, "y": 100, "width": 200, "height": 28}

    def inner_text(self):
        return self.texto

    def is_visible(self):
        return self._visivel

    def bounding_box(self):
        return self._caixa


class _TelaCrua:
    """Tela que devolve exatamente o que lhe for registrado, por seletor."""

    viewport_size = {"width": 1280, "height": 800}
    url = "https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil"

    def __init__(self, por_seletor):
        self.por_seletor = por_seletor

    def query_selector_all(self, seletor):
        return list(self.por_seletor.get(seletor, []))

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def evaluate(self, _s):
        return self.viewport_size

    def wait_for_timeout(self, _ms):
        pass


def test_o_relato_diz_o_que_nao_esta_no_documento():
    from justica_mcp.dcp import LISTA_DE_RESULTADOS, relatar_a_lista_de_perfil

    linhas = relatar_a_lista_de_perfil(_TelaCrua({}))
    texto = "\n".join(linhas)
    assert f"{LISTA_DE_RESULTADOS}): nao esta no documento" in texto


def test_o_relato_separa_fora_da_janela_de_oculto():
    """As duas coisas pedem consertos diferentes e saiam com a mesma frase."""
    from justica_mcp.dcp import ITEM_DA_LISTA, relatar_a_lista_de_perfil

    abaixo_da_dobra = _ElementoDeTela(
        "Advogado", caixa={"x": 10, "y": 2400, "width": 200, "height": 28})
    escondido = _ElementoDeTela("Usuário Comum", visivel=False)

    linhas = relatar_a_lista_de_perfil(
        _TelaCrua({ITEM_DA_LISTA: [abaixo_da_dobra, escondido]}))
    texto = "\n".join(linhas)

    assert "'Advogado': visivel" in texto
    assert "FORA da janela" in texto
    assert "'Usuário Comum': oculto" in texto


def test_o_relato_corta_texto_longo():
    """A mesma forma de lista serve para escolher processo, e ali o texto seria
    dado de cliente."""
    from justica_mcp.dcp import ITEM_DA_LISTA, relatar_a_lista_de_perfil

    linhas = relatar_a_lista_de_perfil(
        _TelaCrua({ITEM_DA_LISTA: [_ElementoDeTela("x" * 80)]}))
    assert not any("xxxx" in l for l in linhas)
    # E ainda assim DIZ que ha um elemento ali, com o estado dele.
    assert any("1 no documento" in l for l in linhas)


def test_a_opcao_abaixo_da_dobra_e_achada_so_com_a_regra_afrouxada():
    from justica_mcp.dcp import ITEM_DA_LISTA, achar_opcao_na_lista

    abaixo = _ElementoDeTela(
        "Advogado", caixa={"x": 10, "y": 2400, "width": 200, "height": 28})
    tela = _TelaCrua({ITEM_DA_LISTA: [abaixo]})

    assert achar_opcao_na_lista(tela, "Advogado") is None
    assert achar_opcao_na_lista(tela, "Advogado", exigir_posicao=False) is abaixo


def test_o_campo_espelho_continua_recusado_mesmo_com_a_regra_afrouxada():
    """A regra de posicao existe por um motivo real e nao foi dispensada: o
    campo empurrado para `left:-9999px` e OCULTO, e a visibilidade continua
    sendo exigida nos dois modos."""
    from justica_mcp.dcp import ITEM_DA_LISTA, achar_opcao_na_lista

    espelho = _ElementoDeTela(
        "Advogado", visivel=False,
        caixa={"x": -9999, "y": 10, "width": 200, "height": 28})
    tela = _TelaCrua({ITEM_DA_LISTA: [espelho]})

    assert achar_opcao_na_lista(tela, "Advogado") is None
    assert achar_opcao_na_lista(tela, "Advogado", exigir_posicao=False) is None


def test_a_recusa_carrega_o_estado_da_tela():
    from justica_mcp.dcp import PerfilNaoInformado, escolher_perfil

    tela = _TelaPerfilSemLista()
    try:
        escolher_perfil(tela, _Guarda(), "Advogado", 2)
    except PerfilNaoInformado as erro:
        recado = str(erro)
        assert "O QUE EXISTE NA TELA DO TIPO DE USUARIO" in recado
        assert "nao esta no documento" in recado
    else:
        raise AssertionError("nao recusou")


class _TelaPerfilSemLista(_TelaDePerfil):
    """Caixa que existe e lista que nunca abre, em lugar nenhum."""

    def __init__(self):
        super().__init__(com_select=False, abre_no_clique=False)
        self.caixa.type = lambda texto, delay=None: None

    def query_selector_all(self, seletor):
        from justica_mcp.dcp import ITEM_DA_LISTA, LISTA_DE_RESULTADOS

        if seletor in (ITEM_DA_LISTA, LISTA_DE_RESULTADOS, "li", "[role=option]"):
            return []
        return super().query_selector_all(seletor)


# ==========================================================================
# `aria-expanded` e o caminho de teclado
#
# Sugestoes trazidas pelo advogado em 07/10/2026, de uma analise externa.
# Duas delas acrescentam sinal que o relato nao tinha. Uma terceira partia de
# premissa errada sobre este codigo (que a digitacao usava `fill`), e por
# isso nao foi aplicada: a digitacao sempre foi tecla a tecla.
# ==========================================================================

class _CaixaQueAnotaTeclas:
    def __init__(self, atributos=None, falha_em=None):
        self.teclas = []
        self.atributos = atributos or {}
        self.falha_em = falha_em

    def press(self, tecla):
        if tecla == self.falha_em:
            raise RuntimeError("sem suporte")
        self.teclas.append(tecla)

    def get_attribute(self, nome):
        return self.atributos.get(nome)

    def evaluate(self, _codigo):
        return "INPUT"


class _PaginaMuda:
    def wait_for_timeout(self, _ms):
        pass


def test_o_teclado_tenta_seta_e_enter_nessa_ordem():
    from justica_mcp.dcp import escolher_pelo_teclado

    caixa = _CaixaQueAnotaTeclas()
    assert escolher_pelo_teclado(caixa, _PaginaMuda()) is True
    assert caixa.teclas == ["ArrowDown", "Enter"]


def test_o_teclado_que_falha_nao_mente_que_escolheu():
    from justica_mcp.dcp import escolher_pelo_teclado

    caixa = _CaixaQueAnotaTeclas(falha_em="ArrowDown")
    assert escolher_pelo_teclado(caixa, _PaginaMuda()) is False


def test_o_estado_da_caixa_traz_o_aria_expanded():
    """A leitura que separa 'o clique nao abriu' de 'o meu seletor esta errado'."""
    from justica_mcp.dcp import estado_da_caixa

    linha = estado_da_caixa(_CaixaQueAnotaTeclas(
        {"aria-expanded": "true", "aria-controls": "resultados",
         "role": "combobox"}))
    assert "aria-expanded='true'" in linha
    assert "aria-controls='resultados'" in linha
    assert "role='combobox'" in linha


def test_o_estado_da_caixa_nao_quebra_sem_caixa():
    from justica_mcp.dcp import estado_da_caixa

    assert "nao foi encontrada" in estado_da_caixa(None)


def test_o_estado_da_caixa_nao_le_o_valor_digitado():
    """Em tela de escolha de PROCESSO a mesma funcao leria dado de cliente."""
    from justica_mcp.dcp import PERGUNTAS_A_CAIXA

    assert "value" not in PERGUNTAS_A_CAIXA


def test_a_marcacao_do_componente_e_relatada_e_limpa():
    from justica_mcp.dcp import CAIXA_DO_PERFIL, envoltorio_da_caixa

    class _Envoltorio:
        def evaluate(self, _c):
            return ('<app-dropdown id="dropdownPerfil" class="ng-star-inserted">'
                    '\n   <input placeholder="Selecione perfil do usuario">'
                    ' 0045025-93.2021.8.19.0002</app-dropdown>')

    class _Tela:
        def query_selector(self, seletor):
            return _Envoltorio() if seletor == CAIXA_DO_PERFIL else None

    lido = envoltorio_da_caixa(_Tela())
    assert "app-dropdown" in lido
    assert "ng-star-inserted" in lido
    # Numero de processo nao viaja em relato, nem dentro de marcacao.
    assert "0045025" not in lido


def test_a_marcacao_diz_quando_o_componente_nao_existe():
    from justica_mcp.dcp import CAIXA_DO_PERFIL, envoltorio_da_caixa

    class _Vazia:
        def query_selector(self, _s):
            return None

    assert CAIXA_DO_PERFIL in envoltorio_da_caixa(_Vazia())
    assert "nao esta no documento" in envoltorio_da_caixa(_Vazia())


def test_a_digitacao_do_perfil_e_tecla_a_tecla_e_nao_fill():
    """Guarda de fonte, contra uma correcao que seria regressao.

    A analise de 07/10/2026 apontou `fill()` como causa provavel, deduzindo-o
    do rotulo 'preencher' do relato da trava. O rotulo e meu; a chamada sempre
    foi `type(..., delay=40)`, que dispara keydown, keypress, input e keyup por
    caractere. Se alguem "consertar" isto trocando por `fill`, o componente
    deixa de receber os eventos e o defeito nasce de verdade.
    """
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.escolher_perfil)
    assert "caixa.type(" in fonte
    assert "delay=" in fonte
    assert "caixa.fill(" not in fonte


def test_o_clique_na_opcao_so_acontece_quando_ha_opcao():
    """O caminho de teclado nao tem opcao para clicar."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.escolher_perfil)
    assert "if opcao is not None:" in fonte
    assert fonte.index("if opcao is not None:") < fonte.index("opcao.click()")


# ==========================================================================
# Relato que depende de QUAL recusa foi nao e relato: e sorte
#
# 07/10/2026: o caminho de teclado deu certo o bastante para pular o ramo que
# relatava, e a recusa que de fato aconteceu, a da prova positiva, nao
# trazia diagnostico nenhum. A corrida custou uma tentativa de login e
# contou MENOS que a anterior teria contado.
# ==========================================================================

def test_toda_recusa_da_escolha_de_perfil_carrega_o_diagnostico():
    """Guarda de fonte, porque o defeito era uma recusa ter ficado de fora."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.escolher_perfil)
    # As duas recusas que acontecem com a caixa na tela.
    assert fonte.count("relato_da_escolha(pagina") == 2
    # E a da prova positiva e uma delas.
    prova = fonte.index("perfil_assumido_pelo_controle(pagina")
    assert "relato_da_escolha(pagina" in fonte[prova:]


def test_a_caixa_somente_de_leitura_e_denunciada():
    """`type()` numa caixa somente de leitura NAO levanta erro e NAO escreve.

    O relato dizia 'preencher' e nada acontecia, e a prova positiva recusava
    porque o valor nunca chegou a existir. Sem esta pergunta, as duas coisas
    ficavam indistinguiveis de digitacao que o componente ignorou.
    """
    from justica_mcp.dcp import estado_da_caixa

    class _SomenteLeitura:
        def evaluate(self, codigo):
            if "tagName" in codigo:
                return "INPUT"
            return "readOnly" in codigo

        def get_attribute(self, nome):
            return "true" if nome == "readonly" else None

        def inner_text(self):
            return ""

    linha = estado_da_caixa(_SomenteLeitura(), "Advogado")
    assert "readonly='true'" in linha
    assert "readOnly=True (propriedade)" in linha


def test_a_propriedade_e_perguntada_mesmo_sem_o_atributo():
    """Componente montado por script marca `readOnly` sem escrever o atributo."""
    from justica_mcp.dcp import estado_da_caixa

    class _SemAtributo:
        def evaluate(self, codigo):
            if "tagName" in codigo:
                return "INPUT"
            return "readOnly" in codigo

        def get_attribute(self, _nome):
            return None

        def inner_text(self):
            return ""

    assert "readOnly=True (propriedade)" in estado_da_caixa(_SemAtributo(), "X")


def test_o_relato_diz_se_o_que_foi_digitado_entrou_sem_imprimir_o_valor():
    from justica_mcp.dcp import valor_da_caixa_frente_ao_pedido

    class _Caixa:
        def __init__(self, valor):
            self.valor = valor

        def evaluate(self, _c):
            return self.valor

    assert "VAZIO" in valor_da_caixa_frente_ao_pedido(_Caixa(""), "Advogado")
    assert "IGUAL" in valor_da_caixa_frente_ao_pedido(_Caixa("Advogado"), "Advogado")
    # Acento nao decide: "Usuário" e "Usuario" sao o mesmo nome.
    assert "IGUAL" in valor_da_caixa_frente_ao_pedido(
        _Caixa("Usuário Comum"), "Usuario Comum")


def test_o_valor_diferente_e_contado_e_nao_impresso():
    """A mesma caixa, noutra tela, teria numero de processo ou nome de parte."""
    from justica_mcp.dcp import valor_da_caixa_frente_ao_pedido

    class _Caixa:
        def evaluate(self, _c):
            return "0045025-93.2021.8.19.0002"

    lido = valor_da_caixa_frente_ao_pedido(_Caixa(), "Advogado")
    assert "0045025" not in lido
    assert "25 caractere(s)" in lido


def test_o_relato_nao_quebra_quando_a_caixa_sumiu():
    from justica_mcp.dcp import estado_da_caixa

    assert "nao foi encontrada" in estado_da_caixa(None, "Advogado")


# ==========================================================================
# "Entrar nao esta na tela", com "Entrar" na tela logo abaixo
#
# 07/10/2026. A escolha do perfil finalmente funcionou: a lista abriu, a
# opcao foi clicada, a prova positiva passou. O comando entao recusou
# dizendo que o botao de enviar nao estava na tela, e o relato impresso na
# linha seguinte listava 'Entrar' entre os botoes visiveis.
#
# Nao havia contradicao, havia meio segundo: a escolha do perfil redesenha o
# formulario, e `elemento_visivel` olha UMA vez. E a mesma classe de defeito
# que ja apareceu neste projeto na tela de login, na de selecao de sistemas
# e na da consulta, agora numa funcao nova.
# ==========================================================================

class _BotaoDeTela:
    def __init__(self, texto, visivel=True, habilitado=True, dentro=True):
        self.texto, self._visivel = texto, visivel
        self._habilitado, self._dentro = habilitado, dentro
        self.rolou = False
        self.clicado = False

    def inner_text(self):
        return self.texto

    def get_attribute(self, _n):
        return None

    def is_visible(self):
        return self._visivel

    def is_enabled(self):
        return self._habilitado

    def bounding_box(self):
        return ({"x": 10, "y": 300, "width": 90, "height": 34} if self._dentro
                else {"x": 10, "y": 3000, "width": 90, "height": 34})

    def scroll_into_view_if_needed(self):
        self.rolou = True

    def click(self):
        self.clicado = True


class _TelaQueDemora:
    """O botao so aparece depois de algumas olhadas, como o formulario que
    esta sendo redesenhado."""

    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, botao, olhadas_ate_aparecer):
        self.botao, self.olhadas = botao, 0
        self.ate_aparecer = olhadas_ate_aparecer

    def query_selector_all(self, _seletor):
        self.olhadas += 1
        return [] if self.olhadas < self.ate_aparecer else [self.botao]

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def evaluate(self, _c):
        return self.viewport_size

    def wait_for_timeout(self, _ms):
        pass


def test_o_botao_que_demora_a_ser_redesenhado_e_esperado():
    from justica_mcp.dcp import achar_o_entrar

    botao = _BotaoDeTela("Entrar")
    assert achar_o_entrar(_TelaQueDemora(botao, 4), segundos=5) is botao


def test_o_botao_empurrado_para_baixo_da_dobra_e_alcancado():
    """A lista aberta empurra o rodape do formulario para fora da janela. Um
    botao fora da janela nao esta ausente: esta a um rolar de distancia."""
    from justica_mcp.dcp import achar_o_entrar

    botao = _BotaoDeTela("Entrar", dentro=False)
    achado = achar_o_entrar(_TelaQueDemora(botao, 1), segundos=1)
    assert achado is botao
    assert botao.rolou is True


def test_o_botao_que_nunca_aparece_devolve_nada():
    from justica_mcp.dcp import achar_o_entrar

    assert achar_o_entrar(_TelaQueDemora(_BotaoDeTela("Entrar"), 10**9),
                          segundos=1) is None


def test_a_recusa_do_entrar_lista_os_botoes_a_vista():
    from justica_mcp.dcp import botoes_a_vista

    class _Tela:
        def query_selector_all(self, _s):
            return [_BotaoDeTela("Entrar", habilitado=False),
                    _BotaoDeTela("Cancelar"),
                    _BotaoDeTela("", visivel=True)]

    lido = botoes_a_vista(_Tela())
    assert "Entrar (desabilitado)" in lido
    assert "Cancelar" in lido
    # Botao mudo nao entra: nao diz nada a quem le.
    assert "" not in lido


def test_o_relato_dos_botoes_corta_texto_longo():
    """Noutra tela, o rotulo de um botao e o proprio andamento do processo."""
    from justica_mcp.dcp import botoes_a_vista

    class _Tela:
        def query_selector_all(self, _s):
            return [_BotaoDeTela("Alternar 45 - Juntada - Extrato - dia 27/04/2018")]

    assert botoes_a_vista(_Tela()) == []


def test_o_entrar_nao_e_mais_procurado_com_uma_olhada_so():
    """Guarda de fonte contra a regressao exata de 07/10/2026."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.escolher_perfil)
    assert "achar_o_entrar(pagina" in fonte
    assert "elemento_visivel(pagina, alvo_do_entrar)" not in fonte


# ==========================================================================
# O botao achado pela ARVORE ACESSIVEL
#
# Rede sugerida em 07/10/2026 e que as duas buscas por texto nao cobrem:
# `_por_texto_exato` olha `inner_text` e `value` de uma lista fixa de
# etiquetas, entao perde o botao cujo nome vem de `aria-label`, e perde
# qualquer elemento com `role=button` que nao seja `<button>`.
# ==========================================================================

class _LocalizadorDePapel:
    """O que `get_by_role` devolve: um localizador, nao um elemento."""

    def __init__(self, candidatos):
        self.candidatos = candidatos

    def count(self):
        return len(self.candidatos)

    def nth(self, i):
        return self.candidatos[i]


class _TelaComArvoreAcessivel:
    """Tela onde a busca por TEXTO nao acha nada e a por PAPEL acha."""

    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, por_papel, pedidos=None):
        self.por_papel = por_papel
        self.pedidos = pedidos if pedidos is not None else []

    def query_selector_all(self, _seletor):
        return []

    def query_selector(self, _seletor):
        return None

    def evaluate(self, _c):
        return self.viewport_size

    def wait_for_timeout(self, _ms):
        pass

    def get_by_role(self, papel, name=None, exact=None):
        self.pedidos.append((papel, name, exact))
        return _LocalizadorDePapel(self.por_papel)


def test_o_entrar_e_aceito_quando_so_a_arvore_acessivel_o_acha():
    """O caso que esta rede existe para cobrir."""
    from justica_mcp.dcp import achar_o_entrar

    botao = _BotaoDeTela("Entrar")
    tela = _TelaComArvoreAcessivel([botao])

    assert achar_o_entrar(tela, segundos=1) is botao
    # E foi pedido pelo nome exato, nao por prefixo: "Entrar" e "Entrar como
    # convidado" sao escolhas diferentes.
    assert tela.pedidos[0] == ("button", "Entrar", True)


def test_entre_varios_candidatos_fica_o_visivel_e_nao_o_primeiro():
    from justica_mcp.dcp import achar_pela_arvore_acessivel

    escondido = _BotaoDeTela("Entrar", visivel=False)
    aparente = _BotaoDeTela("Entrar")

    achado = achar_pela_arvore_acessivel(
        _TelaComArvoreAcessivel([escondido, aparente]), "Entrar")
    assert achado is aparente


def test_a_posicao_nao_desempata_na_arvore_acessivel():
    """Escolher pelo lugar na tela seria escolher no escuro."""
    from justica_mcp.dcp import achar_pela_arvore_acessivel

    fora_da_janela = _BotaoDeTela("Entrar", dentro=False)
    dentro = _BotaoDeTela("Entrar")

    # O primeiro VISIVEL vence, mesmo estando fora da area util.
    achado = achar_pela_arvore_acessivel(
        _TelaComArvoreAcessivel([fora_da_janela, dentro]), "Entrar")
    assert achado is fora_da_janela


def test_navegador_sem_arvore_acessivel_nao_quebra():
    """Quadro embutido e os falsos dos testes nao tem `get_by_role`."""
    from justica_mcp.dcp import achar_pela_arvore_acessivel

    assert achar_pela_arvore_acessivel(object(), "Entrar") is None


def test_a_busca_por_texto_continua_vindo_primeiro():
    """Guarda de fonte: a arvore e rede, nao substituicao. Afrouxar
    `_por_texto_exato` ou `_na_tela` afetaria outros portais."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.achar_clicavel)
    assert fonte.index("esperar_elemento(") < fonte.index(
        "achar_pela_arvore_acessivel(pagina, nome)")


def test_o_diagnostico_descreve_cada_candidato_ao_botao():
    from justica_mcp.dcp import relato_dos_candidatos

    class _ComAriaLabel(_BotaoDeTela):
        def __init__(self):
            super().__init__("", dentro=False)

        def get_attribute(self, nome):
            return "Entrar" if nome == "aria-label" else None

        def evaluate(self, _c):
            return "DIV"

    class _Tela:
        def query_selector_all(self, _s):
            return [_ComAriaLabel(), _BotaoDeTela("Cancelar")]

    linhas = relato_dos_candidatos(_Tela())
    assert len(linhas) == 1
    assert "tag='DIV'" in linhas[0]
    assert "aria-label='Entrar'" in linhas[0]
    assert "caixa=x10 y3000" in linhas[0]
    assert "visivel=True" in linhas[0]


def test_o_diagnostico_diz_quando_nao_ha_candidato_nenhum():
    from justica_mcp.dcp import relato_dos_candidatos

    class _Vazia:
        def query_selector_all(self, _s):
            return []

    assert "nenhum elemento com o nome EXATO" in relato_dos_candidatos(_Vazia())[0]


def test_o_diagnostico_separa_tela_vazia_de_tela_ilegivel():
    """Sao respostas diferentes: a primeira diz que o item nao esta la, a
    segunda que nao se sabe."""
    from justica_mcp.dcp import relato_dos_candidatos

    class _Ilegivel:
        def query_selector_all(self, _s):
            raise RuntimeError("Execution context was destroyed")

    assert "nao foi possivel ler" in relato_dos_candidatos(_Ilegivel())[0]


def test_a_autorizacao_da_trava_continua_sendo_por_texto():
    """A arvore acessivel muda como o botao e ACHADO, nao como ele e
    autorizado: a trava segue nomeando `texto=Entrar`."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.escolher_perfil)
    assert 'alvo_do_entrar = f"{PREFIXO_DE_TEXTO}{BOTAO_ENTRAR_NO_PERFIL}"' in fonte
    assert "pode_executar(Acao.CLICAR, alvo_do_entrar" in fonte


# ==========================================================================
# O 'Entrar' de zero por zero
#
# Diagnostico de 07/10/2026, trazido pelo proprio relato que eu tinha
# acabado de construir:
#
#   tag='A'; visivel=False; habilitado=True; texto='Entrar';
#   caixa=x460 y499 l0 a0
#
# Um `<a>` renderizado, no lugar certo da tela, com largura e altura zero.
# `is_visible()` do Playwright devolve falso para caixa vazia, e TODAS as
# tres buscas anteriores exigem `is_visible()`. Elas falharam juntas e
# nenhuma estava errada sobre o que procurava.
#
# E corrige uma leitura minha do dia anterior: eu disse que o relato provava
# que 'Entrar' estava NA TELA, logo era tempo. O relato filtra por POSICAO
# (`na_tela`), nao por visibilidade, entao ele nunca disse isso.
# ==========================================================================

class _AncoraSemTamanho:
    def __init__(self, texto="Entrar", habilitado=True):
        self.texto, self._habilitado = texto, habilitado
        self.clicado_pelo_documento = False
        self.clicado_pelo_mouse = False

    def inner_text(self):
        return self.texto

    def get_attribute(self, _n):
        return None

    def is_visible(self):
        return False

    def is_enabled(self):
        return self._habilitado

    def bounding_box(self):
        return {"x": 460, "y": 499, "width": 0, "height": 0}

    def evaluate(self, codigo):
        if "click" in codigo:
            self.clicado_pelo_documento = True
            return None
        if "tagName" in codigo:
            return "A"
        return "<a>Entrar</a>"

    def click(self):
        self.clicado_pelo_mouse = True

    def scroll_into_view_if_needed(self):
        pass


def test_a_ancora_sem_tamanho_e_achada_quando_as_outras_redes_falham():
    from justica_mcp.dcp import candidato_sem_tamanho

    ancora = _AncoraSemTamanho()

    class _Tela:
        def query_selector_all(self, _s):
            return [_BotaoDeTela("Cancelar"), ancora]

    assert candidato_sem_tamanho(_Tela()) is ancora


def test_o_desabilitado_nao_serve_nem_sem_tamanho():
    """Habilitado e a unica coisa que ainda se exige: clicar no desabilitado
    nao faz nada e o comando seguiria como se tivesse entrado."""
    from justica_mcp.dcp import candidato_sem_tamanho

    class _Tela:
        def query_selector_all(self, _s):
            return [_AncoraSemTamanho(habilitado=False)]

    assert candidato_sem_tamanho(_Tela()) is None


def test_o_nome_errado_nao_serve_nem_sem_tamanho():
    from justica_mcp.dcp import candidato_sem_tamanho

    class _Tela:
        def query_selector_all(self, _s):
            return [_AncoraSemTamanho(texto="Cancelar")]

    assert candidato_sem_tamanho(_Tela()) is None


def test_o_clique_sem_tamanho_e_disparado_no_proprio_elemento():
    """`click()` do Playwright mira o centro da caixa, e nao ha centro."""
    from justica_mcp.dcp import clicar_pelo_documento

    ancora = _AncoraSemTamanho()
    assert clicar_pelo_documento(ancora) is True
    assert ancora.clicado_pelo_documento is True
    assert ancora.clicado_pelo_mouse is False


def test_o_clique_pelo_documento_que_falha_nao_mente():
    from justica_mcp.dcp import clicar_pelo_documento

    class _Recusa:
        def evaluate(self, _c):
            raise RuntimeError("sem suporte")

    assert clicar_pelo_documento(_Recusa()) is False


def test_a_saida_da_tela_de_perfil_e_conferida_pelo_endereco():
    from justica_mcp.dcp import saiu_da_tela_de_perfil

    class _Tela:
        def __init__(self, url):
            self.url = url

        def wait_for_timeout(self, _ms):
            pass

    assert saiu_da_tela_de_perfil(
        _Tela("https://www3.tjrj.jus.br/portalservicos/#/dashboard"), 1) is True
    assert saiu_da_tela_de_perfil(
        _Tela("https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil"),
        1) is False


def test_clicar_no_invisivel_so_vale_com_prova_depois():
    """Guarda de fonte. Clicar num elemento que o Playwright considera
    invisivel e aceitavel SOMENTE porque a tela e conferida em seguida: sem
    isso, seria uma acao declarada feita sem nada que a comprove."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.escolher_perfil)
    assert "clicar_com_jeito(entrar)" in fonte
    assert "saiu_da_tela_de_perfil(pagina" in fonte
    # A prova vem DEPOIS do clique, e nao ha caminho que a pule.
    assert fonte.index("clicar_com_jeito(entrar)") < fonte.index(
        "saiu_da_tela_de_perfil(pagina")
    # E a busca geral ainda alcanca o elemento sem tamanho.
    assert "candidato_sem_tamanho(pagina, nome)" in inspect.getsource(
        dcp.achar_clicavel)


def test_o_diagnostico_traz_a_marcacao_do_candidato():
    """E o que falta para entender POR QUE a caixa e de zero por zero."""
    from justica_mcp.dcp import relato_dos_candidatos

    class _Tela:
        def query_selector_all(self, _s):
            return [_AncoraSemTamanho()]

    linha = relato_dos_candidatos(_Tela())[0]
    assert "marcacao=" in linha
    assert "caixa=x460 y499 l0 a0" in linha


def test_o_envio_que_nao_tira_da_tela_de_perfil_e_recusado():
    """A prova positiva do ENVIO, e nao so da escolha.

    Clicar num elemento que o Playwright considera invisivel so se justifica
    com conferencia depois. Sem ela, isto seria uma acao declarada feita sem
    nada que a comprove, que e o oposto do que este programa faz.
    """
    tela = _TelaDePerfil(com_select=False)
    tela.destino_do_entrar = None  # o portal nao sai da tela

    with pytest.raises(PerfilNaoInformado, match="nao tirou a tela"):
        escolher_perfil(tela, _Guarda(), "Advogado", 2)


# ==========================================================================
# A sequencia foi descoberta TRES vezes antes de virar uma funcao so
#
#   06/10  a opcao do perfil        nao vinha em `option`, e sim em `li`
#   07/10  o botao 'Entrar'         tinha caixa de zero por zero
#   07/10  'Consultas Processuais'  estava fora da janela, com 26 outros
#
# Sao sintomas diferentes da mesma coisa: o elemento EXISTE e nao satisfaz
# alguma exigencia da busca. Cada exigencia tem razao de ser, e nenhuma foi
# removida das buscas gerais de `portal.py`, que protegem outras telas e
# outros portais. O que mudou e que aqui se tenta mais de uma.
# ==========================================================================

def test_a_busca_geral_alcanca_o_que_esta_fora_da_janela():
    from justica_mcp.dcp import achar_clicavel

    item = _BotaoDeTela("Consultas Processuais", dentro=False)

    class _Tela:
        viewport_size = {"width": 1280, "height": 800}

        def query_selector_all(self, _s):
            return [item]

        def query_selector(self, _s):
            return None

        def evaluate(self, _c):
            return self.viewport_size

        def wait_for_timeout(self, _ms):
            pass

    achado = achar_clicavel(_Tela(), "Consultas Processuais", segundos=1)
    assert achado is item
    assert item.rolou is True


def test_a_busca_geral_alcanca_o_que_nao_tem_tamanho():
    from justica_mcp.dcp import achar_clicavel

    ancora = _AncoraSemTamanho(texto="Consultas Processuais")

    class _Tela:
        viewport_size = {"width": 1280, "height": 800}

        def query_selector_all(self, _s):
            return [ancora]

        def query_selector(self, _s):
            return None

        def evaluate(self, _c):
            return self.viewport_size

        def wait_for_timeout(self, _ms):
            pass

    assert achar_clicavel(_Tela(), "Consultas Processuais", segundos=1) is ancora


def test_o_clique_escolhe_o_jeito_e_diz_qual_foi():
    """Dizer qual foi importa: clique de documento nao passa pelas mesmas
    conferencias do navegador, e quem chama precisa relatar isso."""
    from justica_mcp.dcp import clicar_com_jeito

    comum = _BotaoDeTela("Entrar")
    assert clicar_com_jeito(comum) == "mouse"

    ancora = _AncoraSemTamanho()
    assert clicar_com_jeito(ancora) == "documento"
    assert ancora.clicado_pelo_documento is True


def test_o_clique_que_nao_acontece_de_jeito_nenhum_e_declarado():
    from justica_mcp.dcp import clicar_com_jeito

    class _Teimoso:
        def bounding_box(self):
            return None

        def evaluate(self, _c):
            raise RuntimeError("sem suporte")

    assert clicar_com_jeito(_Teimoso()) == "nenhum"


def test_o_item_do_menu_usa_a_mesma_busca_que_o_entrar():
    """Guarda de fonte contra o conserto pontual: as tres telas sao a mesma
    pergunta, e eu a respondi tres vezes antes de perceber."""
    import inspect

    from justica_mcp import dcp

    menu = inspect.getsource(dcp.abrir_consulta_pelo_menu)
    assert "achar_clicavel(pagina, ITEM_DA_CONSULTA" in menu
    assert "clicar_com_jeito(item)" in menu
    assert inspect.getsource(dcp.achar_o_entrar).count("achar_clicavel(") == 1


def test_a_arvore_acessivel_tenta_botao_link_e_item_de_menu():
    """Item de menu nao e `button`: no portal ele veio como `A`."""
    from justica_mcp.dcp import PAPEIS_CLICAVEIS, achar_pela_arvore_acessivel

    assert PAPEIS_CLICAVEIS == ("button", "link", "menuitem")

    item = _BotaoDeTela("Consultas Processuais")
    pedidos = []

    class _So_Link:
        def get_by_role(self, papel, name=None, exact=None):
            pedidos.append(papel)
            return _LocalizadorDePapel([item] if papel == "link" else [])

    achado = achar_pela_arvore_acessivel(_So_Link(), "Consultas Processuais")
    assert achado is item
    assert pedidos == ["button", "link"]


# ==========================================================================
# O menu deste portal NAO e feito de botoes
#
# 08/10/2026. A escolha do perfil passou pela SEGUNDA vez, e o diagnostico
# do item do menu respondeu de uma vez:
#
#   CANDIDATOS AO ITEM:
#   nenhum clicavel com o nome 'Consultas Processuais' na tela
#
# Verdade sobre botoes e ancoras, e falso sobre a tela. O acompanhamento de
# 06/10 ja tinha mostrado `div#CONSULTAS`, `li#CONSULTAS` e `span#CONSULTAS`,
# e eu li aquilo como detalhe do menu de primeiro nivel em vez de como a
# forma do menu INTEIRO.
#
# Por isso a escolha do perfil funcionava e o item do menu nao: a escolha usa
# a busca ampla desde 06/10, e as buscas de clicavel so olhavam `button` e
# `a`. Eram duas buscas para a mesma pergunta, e so uma sabia a resposta.
# ==========================================================================

class _ItemEmEtiquetaMuda:
    """O item como o portal o monta: `li`, sem semantica de clique.

    Nome proprio porque `_ItemDeMenu` ja existe neste arquivo, com outra
    assinatura. Falso novo que reusa nome de falso antigo o sobrescreve em
    silencio e quebra os testes do outro, que foi o que aconteceu aqui.
    """

    def __init__(self, texto, dentro=True):
        self.texto, self._dentro = texto, dentro
        self.clicado = False

    def inner_text(self):
        return self.texto

    def get_attribute(self, _n):
        return None

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def bounding_box(self):
        return ({"x": 20, "y": 200, "width": 180, "height": 32} if self._dentro
                else {"x": 20, "y": 2600, "width": 180, "height": 32})

    def evaluate(self, codigo):
        if "tagName" in codigo:
            return "LI"
        return "LI#itemMenu@200,20"

    def click(self):
        self.clicado = True

    def scroll_into_view_if_needed(self):
        pass


def _tela_de_menu(itens, so_em=("li",)):
    class _Tela:
        viewport_size = {"width": 1280, "height": 800}
        url = "https://www3.tjrj.jus.br/portalservicos/#/tela-menu"

        def query_selector_all(self, seletor):
            return list(itens) if seletor in so_em else []

        def query_selector(self, seletor):
            achados = self.query_selector_all(seletor)
            return achados[0] if achados else None

        def evaluate(self, _c):
            return self.viewport_size

        def wait_for_timeout(self, _ms):
            pass

    return _Tela()


def test_o_item_de_menu_em_li_e_alcancado():
    from justica_mcp.dcp import achar_clicavel

    item = _ItemEmEtiquetaMuda("Consultas Processuais")
    achado = achar_clicavel(_tela_de_menu([item]), "Consultas Processuais", 1)
    assert achado is item


def test_o_item_de_menu_em_li_fora_da_janela_tambem():
    from justica_mcp.dcp import achar_clicavel

    item = _ItemEmEtiquetaMuda("Consultas Processuais", dentro=False)
    achado = achar_clicavel(_tela_de_menu([item]), "Consultas Processuais", 1)
    assert achado is item


def test_o_item_em_div_tambem_e_alcancado():
    """O acompanhamento de 06/10 mostrou `div#CONSULTAS` junto de `li` e
    `span`: o portal monta o mesmo item em mais de uma etiqueta."""
    from justica_mcp.dcp import achar_clicavel

    item = _ItemEmEtiquetaMuda("Consultas Processuais")
    achado = achar_clicavel(
        _tela_de_menu([item], so_em=("div",)), "Consultas Processuais", 1)
    assert achado is item


def test_o_nome_diferente_continua_sendo_recusado():
    """Ampliar onde se procura nao e afrouxar o QUE se procura: 'Consultas
    Processuais' e 'Consultas Processuais Antigas' sao itens diferentes."""
    from justica_mcp.dcp import achar_clicavel

    item = _ItemEmEtiquetaMuda("Consultas Processuais Antigas")
    assert achar_clicavel(
        _tela_de_menu([item]), "Consultas Processuais", 1) is None


def test_o_diagnostico_enxerga_o_item_que_nao_e_botao():
    """A frase antiga mandava procurar no lugar errado."""
    from justica_mcp.dcp import relato_dos_candidatos

    item = _ItemEmEtiquetaMuda("Consultas Processuais")
    linhas = relato_dos_candidatos(
        _tela_de_menu([item]), "Consultas Processuais")
    assert len(linhas) == 1
    assert "tag='LI'" in linhas[0]


def test_a_opcao_do_perfil_e_o_item_do_menu_usam_a_MESMA_busca():
    """Guarda de fonte. Eram duas buscas para a mesma pergunta, e so uma
    sabia a resposta."""
    import inspect

    from justica_mcp import dcp

    assert "achar_por_texto_em_qualquer_lugar(pagina, texto, exigir_posicao)" \
        in inspect.getsource(dcp.achar_opcao_na_lista)
    assert "achar_por_texto_em_qualquer_lugar(pagina, nome, exigir)" \
        in inspect.getsource(dcp.achar_clicavel)


# ==========================================================================
# O item nao estava invisivel: estava num grupo FECHADO
#
# 08/10/2026, com a marcacao finalmente no relato:
#
#   tag='LI'; visivel=False; habilitado=True; texto='Consultas Processuais';
#   caixa=nenhuma;
#   marcacao='<li class="collapse submenu ng-star-inserted">Consultas
#             Processuais</li>'
#
# `collapse` sem `show` quer dizer `display: none`, e por isso a caixa veio
# NENHUMA em vez de zero por zero. Sao coisas diferentes: o 'Entrar' da tela
# de perfil ocupa lugar e nao tem tamanho; este item nao esta sendo
# desenhado. O primeiro so precisa de outro jeito de clique; este precisa que
# o grupo seja ABERTO, que e o que o operador faz com o mouse.
# ==========================================================================

class _ItemRecolhido:
    def __init__(self, classes="collapse submenu ng-star-inserted"):
        self.classes = classes

    def get_attribute(self, nome):
        return self.classes if nome == "class" else None

    def inner_text(self):
        return "Consultas Processuais"

    def is_visible(self):
        return "show" in self.classes.split()

    def is_enabled(self):
        return True

    def bounding_box(self):
        return None

    def evaluate(self, codigo):
        if "tagName" in codigo:
            return "LI"
        return "LI#@0,0"


def test_o_grupo_fechado_e_reconhecido():
    from justica_mcp.dcp import esta_recolhido

    assert esta_recolhido(_ItemRecolhido()) is True
    # Aberto nao e recolhido, nas duas marcas que as bibliotecas usam.
    assert esta_recolhido(_ItemRecolhido("collapse submenu show")) is False
    assert esta_recolhido(_ItemRecolhido("collapse submenu in")) is False
    # E quem nao e de grupo nenhum tambem nao.
    assert esta_recolhido(_ItemRecolhido("submenu")) is False
    assert esta_recolhido(object()) is False


def test_recolhido_nao_se_confunde_com_sem_tamanho():
    """O 'Entrar' da tela de perfil OCUPA lugar e nao tem tamanho; o item do
    menu nao esta sendo desenhado. Sao dois consertos diferentes."""
    from justica_mcp.dcp import esta_recolhido

    assert esta_recolhido(_AncoraSemTamanho()) is False


def test_o_grupo_e_aberto_antes_de_o_item_ser_procurado_de_novo():
    from justica_mcp.dcp import abrir_o_grupo_do_menu

    class _MenuQueAbre:
        viewport_size = {"width": 1280, "height": 800}
        url = "https://www3.tjrj.jus.br/portalservicos/#/tela-menu"

        def __init__(self):
            self.aberto = False
            self.cliques = 0
            self.cabecalho = _BotaoDeTela("CONSULTAS")

        def query_selector_all(self, seletor):
            from justica_mcp.dcp import MENU_DE_CONSULTAS

            if seletor == MENU_DE_CONSULTAS:
                return [self.cabecalho]
            if seletor == "li":
                return [_ItemEmEtiquetaMuda("Consultas Processuais")] \
                    if self.aberto else []
            return []

        def query_selector(self, seletor):
            achados = self.query_selector_all(seletor)
            return achados[0] if achados else None

        def evaluate(self, _c):
            return self.viewport_size

        def wait_for_timeout(self, _ms):
            self.cliques += 1
            self.aberto = True

    tela = _MenuQueAbre()
    assert abrir_o_grupo_do_menu(tela, _Guarda(), segundos=1) is True
    assert tela.cabecalho.clicado is True


def test_o_grupo_que_nao_abre_e_declarado():
    from justica_mcp.dcp import abrir_o_grupo_do_menu

    class _MenuTeimoso:
        viewport_size = {"width": 1280, "height": 800}
        url = "https://www3.tjrj.jus.br/portalservicos/#/tela-menu"

        def query_selector_all(self, seletor):
            from justica_mcp.dcp import MENU_DE_CONSULTAS

            return [_BotaoDeTela("CONSULTAS")] if seletor == MENU_DE_CONSULTAS else []

        def query_selector(self, seletor):
            achados = self.query_selector_all(seletor)
            return achados[0] if achados else None

        def evaluate(self, _c):
            return self.viewport_size

        def wait_for_timeout(self, _ms):
            pass

    assert abrir_o_grupo_do_menu(_MenuTeimoso(), _Guarda(), segundos=1) is False


def test_sem_cabecalho_nao_ha_o_que_abrir():
    from justica_mcp.dcp import abrir_o_grupo_do_menu

    class _SemMenu:
        viewport_size = {"width": 1280, "height": 800}
        url = "https://www3.tjrj.jus.br/portalservicos/#/tela-menu"

        def query_selector_all(self, _s):
            return []

        def query_selector(self, _s):
            return None

        def evaluate(self, _c):
            return self.viewport_size

    assert abrir_o_grupo_do_menu(_SemMenu(), _Guarda(), segundos=1) is False


def test_o_relato_diz_que_o_candidato_esta_recolhido():
    """Sem isto, "visivel=False; caixa=nenhuma" parecia o mesmo caso do
    'Entrar', e o conserto seria o errado."""
    from justica_mcp.dcp import relato_dos_candidatos

    class _Tela:
        def query_selector_all(self, seletor):
            return [_ItemRecolhido()] if seletor == "li" else []

    linha = relato_dos_candidatos(_Tela(), "Consultas Processuais")[0]
    assert "RECOLHIDO (grupo fechado)" in linha


def test_a_rede_sem_tamanho_tambem_olha_etiqueta_muda():
    """Ate 08/10/2026 ela olhava so `button` e `a`, e por isso nao alcancava
    o item do menu."""
    from justica_mcp.dcp import candidato_sem_tamanho

    item = _ItemRecolhido()

    class _Tela:
        def query_selector_all(self, seletor):
            return [item] if seletor == "li" else []

    assert candidato_sem_tamanho(_Tela(), "Consultas Processuais") is item


# ==========================================================================
# A tela de justificativa, entre o clique e o Visualizador
#
# Lida em campo em 08/10/2026. Clicar em "Processo Eletronico - Visualizador"
# NAO abre janela: abre um formulario, no mesmo quadro:
#
#   <input type=password id=senhaProvisoria
#          rotulo='Senha para visualizar o processo eletronico*'>
#   <textarea id=motivo rotulo='Motivo*' maxlength=499>
#   botao 'Visualizar Processo'
#
# Instrucao do advogado, por escrito: digitar 'consulta' no motivo, tecla a
# tecla. A senha NAO e preenchida, e nem entra na lista de preenchiveis da
# trava: e credencial de acesso aos autos, e inventa-la seria exatamente o
# que este projeto nao faz.
# ==========================================================================

class _CampoDoMotivo:
    def __init__(self, aceita=True):
        self.digitado = ""
        self.clicado = False
        self.aceita = aceita
        self.delays = []

    def click(self):
        self.clicado = True

    def type(self, texto, delay=None):
        if not self.aceita:
            raise RuntimeError("somente leitura")
        self.digitado += texto
        self.delays.append(delay)

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 10, "y": 300, "width": 400, "height": 90}


class _QuadroComJustificativa:
    viewport_size = {"width": 1280, "height": 800}
    url = "https://www3.tjrj.jus.br/consultaprocessual/#/consultar/detalhes-processo"

    def __init__(self, com_senha=True, com_botao=True, campo=None):
        self.campo = campo if campo is not None else _CampoDoMotivo()
        self.com_senha = com_senha
        self.botao = _BotaoDeTela("Visualizar Processo") if com_botao else None
        self.visualizador = _BotaoDeTela("Processo Eletrônico - Visualizador")

    def query_selector_all(self, seletor):
        from justica_mcp.dcp import (BOTAO_VISUALIZADOR, CAMPO_DA_SENHA_PROVISORIA,
                                     CAMPO_DO_MOTIVO)
        from justica_mcp.portal import PREFIXO_DE_TEXTO

        if seletor == CAMPO_DO_MOTIVO:
            return [self.campo]
        if seletor == CAMPO_DA_SENHA_PROVISORIA:
            return [_BotaoDeTela("")] if self.com_senha else []
        if seletor.startswith(PREFIXO_DE_TEXTO):
            return []
        achados = []
        if self.botao is not None:
            achados.append(self.botao)
        achados.append(self.visualizador)
        return achados

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def evaluate(self, _c):
        return self.viewport_size

    def wait_for_timeout(self, _ms):
        pass


class _PaginaComQuadro:
    """A pagina de fora, que hospeda o quadro e a janela nova."""

    url = "https://www3.tjrj.jus.br/portalservicos/#/consproc/consultaportal"
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, quadro, abre_na_confirmacao=True):
        self.quadro = quadro
        self.frames = [self, quadro]
        self.abre_na_confirmacao = abre_na_confirmacao
        self.context = self
        self.janela = object()

    def expect_page(self, timeout=None):
        quadro = self.quadro
        pagina = self

        class _Espera:
            def __enter__(_s):
                return _s

            def __exit__(_s, *a):
                # A janela so abre na confirmacao, nunca no primeiro clique.
                if not (pagina.abre_na_confirmacao and quadro.campo.digitado):
                    raise RuntimeError("TimeoutError: nenhuma janela nova")
                return False

            @property
            def value(_s):
                return pagina.janela

        return _Espera()

    def query_selector_all(self, _s):
        return []

    def query_selector(self, _s):
        return None

    def evaluate(self, _c):
        return self.viewport_size

    def wait_for_timeout(self, _ms):
        pass


def test_o_motivo_e_digitado_tecla_a_tecla_e_o_processo_abre():
    from justica_mcp.dcp import abrir_visualizador

    quadro = _QuadroComJustificativa()
    pagina = _PaginaComQuadro(quadro)

    janela = abrir_visualizador(pagina, _Guarda(), 2, motivo="consulta")

    assert janela is pagina.janela
    assert quadro.campo.digitado == "consulta"
    # Tecla a tecla, como o advogado pediu, e nao `fill`.
    assert quadro.campo.delays and all(d for d in quadro.campo.delays)
    assert quadro.botao.clicado is True


def test_sem_motivo_o_comando_para_em_vez_de_inventar_um():
    """Declarar o motivo do acesso aos autos e ato do advogado."""
    from justica_mcp.dcp import MotivoNaoInformado, abrir_visualizador

    quadro = _QuadroComJustificativa()
    with pytest.raises(MotivoNaoInformado, match="--motivo"):
        abrir_visualizador(_PaginaComQuadro(quadro), _Guarda(), 2, motivo="   ")
    assert quadro.campo.digitado == ""


def test_a_senha_provisoria_nao_entra_nos_preenchiveis_da_trava():
    """Ela e credencial de acesso aos autos, dada ao titular. A trava barra o
    proprio programa se algum caminho futuro tentar preenche-la."""
    from justica_mcp.dcp import CAMPO_DA_SENHA_PROVISORIA, abrir_visualizador

    quadro = _QuadroComJustificativa()
    guarda = _Guarda()
    abrir_visualizador(_PaginaComQuadro(quadro), guarda, 2, motivo="consulta")

    for permissao in guarda.permissoes:
        assert CAMPO_DA_SENHA_PROVISORIA not in (
            permissao.seletores_preenchiveis or ())


def test_o_programa_nunca_digita_na_senha_provisoria():
    """Guarda de fonte, que e o que sobrevive a um refatoramento distraido."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp)
    assert "CAMPO_DA_SENHA_PROVISORIA" in fonte
    for linha in fonte.splitlines():
        if "CAMPO_DA_SENHA_PROVISORIA" in linha:
            assert ".type(" not in linha and ".fill(" not in linha


def test_sem_o_botao_de_confirmar_o_comando_para_e_relata():
    from justica_mcp.dcp import ConsultaIndisponivel, abrir_visualizador

    quadro = _QuadroComJustificativa(com_botao=False)
    with pytest.raises(ConsultaIndisponivel, match="CANDIDATOS AO BOTAO"):
        abrir_visualizador(_PaginaComQuadro(quadro), _Guarda(), 2,
                           motivo="consulta")


def test_sem_justificativa_e_sem_janela_o_recado_diz_as_duas_coisas():
    from justica_mcp.dcp import ConsultaIndisponivel, abrir_visualizador

    class _QuadroSeco(_QuadroComJustificativa):
        def query_selector_all(self, seletor):
            from justica_mcp.dcp import CAMPO_DO_MOTIVO

            if seletor == CAMPO_DO_MOTIVO:
                return []
            return super().query_selector_all(seletor)

    quadro = _QuadroSeco()
    with pytest.raises(ConsultaIndisponivel, match="nao pediu justificativa"):
        abrir_visualizador(_PaginaComQuadro(quadro, abre_na_confirmacao=False),
                           _Guarda(), 2, motivo="consulta")


# ==========================================================================
# DOIS botoes chamados "Visualizar Processo"
#
# Relato de 08/10/2026: a tela do processo tem dois botoes com esse nome
# exato. A busca por nome devolve o primeiro do documento, e o que vale e o
# do dialogo da justificativa. O advogado disse qual: "o botao visualizar
# processo a ser clicado e o abaixo da caixa motivo".
#
# Duas formas de achar o mesmo botao, e a primeira nao depende de posicao.
# ==========================================================================

class _CampoComDialogo(_CampoDoMotivo):
    """Campo que sabe responder qual botao esta no dialogo dele."""

    def __init__(self, botao_do_dialogo=None, y=300):
        super().__init__()
        self._do_dialogo = botao_do_dialogo
        self._y = y

    def bounding_box(self):
        return {"x": 10, "y": self._y, "width": 400, "height": 90}

    def evaluate_handle(self, _js, _alvo=None):
        dono = self._do_dialogo

        class _Punho:
            def as_element(self):
                return dono

        return _Punho()


def test_o_botao_e_escolhido_pelo_dialogo_e_nao_pela_ordem():
    from justica_mcp.dcp import BOTAO_VISUALIZAR_PROCESSO, botao_do_mesmo_dialogo

    certo = _BotaoDeTela("Visualizar Processo")
    campo = _CampoComDialogo(botao_do_dialogo=certo)

    assert botao_do_mesmo_dialogo(campo, BOTAO_VISUALIZAR_PROCESSO) is certo


def test_dialogo_que_nao_desempata_devolve_nada():
    """Chutar entre dois seria escolher no escuro."""
    from justica_mcp.dcp import BOTAO_VISUALIZAR_PROCESSO, botao_do_mesmo_dialogo

    campo = _CampoComDialogo(botao_do_dialogo=None)
    assert botao_do_mesmo_dialogo(campo, BOTAO_VISUALIZAR_PROCESSO) is None
    # E campo que nem sabe responder tambem nao quebra.
    assert botao_do_mesmo_dialogo(object(), BOTAO_VISUALIZAR_PROCESSO) is None


def test_a_regra_do_advogado_escolhe_o_de_baixo():
    """"O botao visualizar processo a ser clicado e o abaixo da caixa motivo"."""
    from justica_mcp.dcp import BOTAO_VISUALIZAR_PROCESSO, botao_abaixo_do_campo

    de_cima = _BotaoDeTela("Visualizar Processo")
    de_cima.bounding_box = lambda: {"x": 10, "y": 120, "width": 160, "height": 34}
    logo_abaixo = _BotaoDeTela("Visualizar Processo")
    logo_abaixo.bounding_box = lambda: {"x": 10, "y": 420, "width": 160, "height": 34}
    bem_abaixo = _BotaoDeTela("Visualizar Processo")
    bem_abaixo.bounding_box = lambda: {"x": 10, "y": 900, "width": 160, "height": 34}

    class _Tela:
        def query_selector_all(self, _s):
            return [de_cima, bem_abaixo, logo_abaixo]

    campo = _CampoComDialogo(y=300)
    # "Logo abaixo" e o de menor distancia entre os que comecam abaixo, e nao
    # qualquer um que esteja mais para baixo.
    assert botao_abaixo_do_campo(_Tela(), campo,
                                 BOTAO_VISUALIZAR_PROCESSO) is logo_abaixo


def test_sem_nenhum_abaixo_a_regra_espacial_devolve_nada():
    from justica_mcp.dcp import BOTAO_VISUALIZAR_PROCESSO, botao_abaixo_do_campo

    acima = _BotaoDeTela("Visualizar Processo")
    acima.bounding_box = lambda: {"x": 10, "y": 100, "width": 160, "height": 34}

    class _Tela:
        def query_selector_all(self, _s):
            return [acima]

    assert botao_abaixo_do_campo(_Tela(), _CampoComDialogo(y=300),
                                 BOTAO_VISUALIZAR_PROCESSO) is None


def test_a_estrutura_vem_antes_da_posicao():
    """Posicao e a ultima coisa em que se confia para desempatar: ela muda com
    o tamanho da janela."""
    from justica_mcp.dcp import achar_o_visualizar_processo

    pelo_dialogo = _BotaoDeTela("Visualizar Processo")
    outro = _BotaoDeTela("Visualizar Processo")
    outro.bounding_box = lambda: {"x": 10, "y": 420, "width": 160, "height": 34}

    class _Tela:
        def query_selector_all(self, _s):
            return [outro]

    achado, criterio = achar_o_visualizar_processo(
        _Tela(), _CampoComDialogo(botao_do_dialogo=pelo_dialogo), 1)
    assert achado is pelo_dialogo
    assert "dialogo" in criterio


def test_a_escolha_entre_homonimos_nunca_e_calada():
    """Guarda de fonte: o criterio vai para o relato."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.abrir_visualizador)
    assert "achar_o_visualizar_processo(" in fonte
    assert "escolhido {criterio}" in fonte


# ==========================================================================
# "O portal disse" sobre um rodape permanente
# ==========================================================================

def test_o_aviso_permanente_nao_entra_na_recusa_como_se_fosse_erro():
    """Em 08/10/2026 ele saiu DUAS vezes dentro de uma recusa, depois de "O
    portal disse:", como se fosse a explicacao da falha. Dizer isso sobre um
    rodape permanente manda procurar onde nao ha."""
    from justica_mcp.dcp import _recados_do_quadro

    aviso = ("As informações aqui contidas não produzem efeitos legais. "
             "Somente a publicação no DJERJ oficializa despachos e decisões.")

    class _Quadro:
        def query_selector_all(self, seletor):
            if seletor != ".alert":
                return []

            class _Recado:
                def __init__(self, texto):
                    self.texto = texto

                def is_visible(self):
                    return True

                def inner_text(self):
                    return self.texto

            return [_Recado(aviso), _Recado(aviso),
                    _Recado("Senha provisoria obrigatoria"),
                    _Recado("Senha provisoria obrigatoria")]

    recados = _recados_do_quadro(_Quadro())
    # O aviso sai; o recado de verdade fica, uma vez so.
    assert recados == ["Senha provisoria obrigatoria"]


# ==========================================================================
# Baixar em PARTES: a leitura do indice
#
# 08/10/2026, com o Visualizador finalmente aberto e a integra nao baixando:
# "o erro foi do proprio site. Nessas situacoes colocar duas opcoes, baixar
# alguma peca especifica ou baixar de 300 em 300 paginas".
#
# As duas precisam MARCAR itens do indice, e o indice nunca foi lido com a
# caixa de selecao aberta. Entao a corrida que falha passa a traze-lo, em vez
# de so falhar: a tentativa ja foi gasta de qualquer jeito.
# ==========================================================================

def test_do_rotulo_do_item_so_o_NUMERO_e_aproveitado():
    """O resto e o proprio andamento do processo, e foi o que vazou para uma
    conversa em 06/10/2026."""
    from justica_mcp.dcp import pagina_inicial_do_item

    assert pagina_inicial_do_item(
        "Alternar 45 - Juntada - Extrato da GRERJ - dia 27/04/2018") == 45
    assert pagina_inicial_do_item("Alternar 7 - Peticao") == 7
    # Sem acento e sem depender de maiusculas.
    assert pagina_inicial_do_item("ALTERNAR 12 - algo") == 12
    # O que nao e item do indice nao vira numero nenhum.
    assert pagina_inicial_do_item("Baixar o processo atual em PDF") is None
    assert pagina_inicial_do_item("Alternar todos") is None
    assert pagina_inicial_do_item("") is None
    assert pagina_inicial_do_item(None) is None


def test_o_relato_do_indice_nao_imprime_o_andamento():
    """A regra que falhou uma vez e a que precisa de teste."""
    from justica_mcp.dcp import relatar_o_indice

    class _Item:
        def __init__(self, rotulo):
            self.rotulo = rotulo

        def get_attribute(self, nome):
            return self.rotulo if nome == "aria-label" else None

        def query_selector_all(self, _s):
            return []

        def evaluate_handle(self, _js):
            raise RuntimeError("sem pai")

    class _Indice:
        def query_selector_all(self, seletor):
            if seletor != "[aria-label]":
                return []
            return [_Item("Alternar 45 - Juntada - Extrato da GRERJ - dia 27/04/2018"),
                    _Item("Alternar 46 - Sentenca - dia 03/05/2019"),
                    _Item("Baixar o processo atual em PDF")]

    linhas = relatar_o_indice(_Indice())
    texto = "\n".join(linhas)

    assert "2 item(ns) no indice" in texto
    assert "45, 46" in texto
    # Nada do andamento sai, em linha nenhuma.
    assert "Juntada" not in texto
    assert "GRERJ" not in texto
    assert "Sentenca" not in texto
    assert "27/04/2018" not in texto


def test_o_relato_diz_onde_esta_a_marca_de_selecao():
    """E o que falta saber para marcar um documento especifico."""
    from justica_mcp.dcp import relatar_o_indice

    class _Marca:
        pass

    class _Item:
        def get_attribute(self, nome):
            return "Alternar 45 - algo" if nome == "aria-label" else None

        def query_selector_all(self, seletor):
            return [_Marca()] if seletor == "input[type=checkbox]" else []

        def evaluate_handle(self, _js):
            raise RuntimeError("sem pai")

    class _Indice:
        def query_selector_all(self, seletor):
            return [_Item()] if seletor == "[aria-label]" else []

    linhas = relatar_o_indice(_Indice())
    assert any("input[type=checkbox] x1 dentro" in l for l in linhas)


def test_o_relato_diz_quando_nao_ha_marca_nenhuma():
    from justica_mcp.dcp import relatar_o_indice

    class _Item:
        def get_attribute(self, nome):
            return "Alternar 45 - algo" if nome == "aria-label" else None

        def query_selector_all(self, _s):
            return []

        def evaluate_handle(self, _js):
            raise RuntimeError("sem pai")

    class _Indice:
        def query_selector_all(self, seletor):
            return [_Item()] if seletor == "[aria-label]" else []

    linhas = relatar_o_indice(_Indice())
    assert any("nenhuma marca de selecao perto dele" in l for l in linhas)


def test_indice_vazio_e_dito_com_todas_as_letras():
    from justica_mcp.dcp import relatar_o_indice

    class _Vazio:
        def query_selector_all(self, _s):
            return []

    assert "nao tem item nenhum" in relatar_o_indice(_Vazio())[0]


def test_a_falha_da_integra_traz_o_indice_junto():
    """Guarda de fonte: a corrida ja foi gasta, e o mapa sai nela."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.baixar_integra)
    assert "abrir_caixa_de_selecao(pagina, guarda)" in fonte
    assert "relatar_o_indice(pagina)" in fonte
    assert "O INDICE DE DOCUMENTOS, para baixar em partes" in fonte


# ==========================================================================
# O numero ao lado do documento e a PAGINA em que ele comeca
#
# Correcao do advogado em 08/10/2026, com a tela do indice: "ao lado do nome
# do documento vem o numero da pagina que inicia o documento". Eu vinha
# lendo aquele numero como SEQUENCIA, e nao e.
#
# A tela confirma, porque os numeros saltam: 3, 12, 13, 14, 15, 16, 23, 25,
# 31, 33, 48, 66, 69, 70, 74, 75, 77, 92, 93. Sequencia nao salta de 16 para
# 23; pagina inicial, sim.
#
# A diferenca decide tudo o que vem depois: com ela, "de 300 em 300 paginas"
# vira conta exata, e nao chute por quantidade de documentos.
# ==========================================================================

# As paginas iniciais da tela que o advogado mandou em 08/10/2026.
INDICE_REAL = [3, 12, 13, 14, 15, 16, 23, 25, 31, 33, 48, 66, 69, 70, 74, 75,
               77, 92, 93]


def test_a_pagina_inicial_sai_como_numero_e_nao_como_texto():
    """E numero porque vai ser somado e comparado, nao exibido."""
    from justica_mcp.dcp import pagina_inicial_do_item

    assert pagina_inicial_do_item("Alternar 92 - Extrato da GRERJ") == 92
    assert isinstance(pagina_inicial_do_item("Alternar 3 - algo"), int)


def test_o_indice_inteiro_cabe_em_um_lote_de_300():
    """O processo da tela vai da pagina 3 a 93: 300 paginas o cobrem."""
    from justica_mcp.dcp import lotes_por_pagina

    assert lotes_por_pagina(INDICE_REAL) == [list(range(len(INDICE_REAL)))]


def test_os_lotes_sao_cortados_pela_distancia_entre_paginas():
    from justica_mcp.dcp import lotes_por_pagina

    # Com 30 paginas por lote, o corte cai onde a distancia chega a 30.
    lotes = lotes_por_pagina(INDICE_REAL, 30)
    assert [[INDICE_REAL[i] for i in lote] for lote in lotes] == [
        [3, 12, 13, 14, 15, 16, 23, 25, 31],
        [33, 48],
        [66, 69, 70, 74, 75, 77, 92, 93],
    ]


def test_documento_que_nao_cabe_em_lote_nenhum_vai_sozinho():
    """Acervo com buraco silencioso e pior que download que falha na cara do
    operador."""
    from justica_mcp.dcp import lotes_por_pagina

    # Um salto maior que o lote inteiro.
    assert lotes_por_pagina([1, 2, 900, 901], 100) == [[0, 1], [2, 3]]


def test_lote_vazio_e_lote_de_um_nao_quebram():
    from justica_mcp.dcp import lotes_por_pagina

    assert lotes_por_pagina([]) == []
    assert lotes_por_pagina(None) == []
    assert lotes_por_pagina([7]) == [[0]]
    # Tamanho absurdo nao divide por zero nem devolve lote vazio.
    assert lotes_por_pagina([1, 2, 3], 0) == [[0], [1], [2]]


def test_a_pagina_sem_numero_nao_entra_na_conta():
    """Item cujo rotulo nao traz pagina nao pode deslocar os lotes."""
    from justica_mcp.dcp import lotes_por_pagina

    assert lotes_por_pagina([1, None, 2, "x", 3], 100) == [[0, 2, 4]]


def test_o_relato_do_indice_ja_mostra_os_lotes():
    """Para que a proxima corrida nao precise ser gasta so para contar."""
    from justica_mcp.dcp import relatar_o_indice

    class _Item:
        def __init__(self, pagina):
            self.pagina = pagina

        def get_attribute(self, nome):
            return (f"Alternar {self.pagina} - andamento que nao pode sair"
                    if nome == "aria-label" else None)

        def query_selector_all(self, _s):
            return []

        def evaluate_handle(self, _js):
            raise RuntimeError("sem pai")

    class _Indice:
        def query_selector_all(self, seletor):
            return ([_Item(p) for p in (1, 400, 800)]
                    if seletor == "[aria-label]" else [])

    texto = "\n".join(relatar_o_indice(_Indice()))
    assert "comecam nas paginas: 1, 400, 800" in texto
    assert "em lotes de 300 paginas dariam 3 download(s)" in texto
    # E o andamento continua fora.
    assert "andamento" not in texto


# ==========================================================================
# Baixar em PARTES: as duas opcoes pedidas
#
# Conferido em campo em 08/10/2026, com o Visualizador aberto no processo do
# advogado: 164 documentos, ultima pagina 1541, e a marca de selecao de cada
# item e um `input[type=checkbox]` que fica no elemento PAI dele. Em lotes de
# 300 paginas aquele processo dava 4 downloads.
#
# As duas formas nascem do mesmo mecanismo: marcar itens e usar "Salvar
# Documentos Selecionados". A diferenca e so quais itens se marca.
# ==========================================================================

class _Marca:
    """A caixa de marcacao, como o Angular Material a monta: `input`
    escondido atras de um desenho, que nao aceita clique de mouse."""

    def __init__(self, aceita_documento=True):
        self.marcada = False
        self.aceita_documento = aceita_documento

    def bounding_box(self):
        return None  # escondida: clique de mouse nao tem onde cair

    def evaluate(self, codigo):
        if "checked" in codigo and "click" not in codigo:
            return self.marcada
        if "click" in codigo:
            if not self.aceita_documento:
                raise RuntimeError("nao aceita")
            self.marcada = not self.marcada
            return None
        return None


class _ItemComMarca:
    def __init__(self, inicio, marca=None):
        self.inicio = inicio
        self.marca = marca if marca is not None else _Marca()
        self.pai = self

    def get_attribute(self, nome):
        if nome == "aria-label":
            return f"Alternar {self.inicio} - andamento que nao pode sair"
        return None

    def query_selector_all(self, seletor):
        if seletor == "input[type=checkbox]" and self.marca is not None:
            return [self.marca]
        return []

    def evaluate_handle(self, _js):
        dono = self

        class _Punho:
            def as_element(self):
                return dono

        return _Punho()


class _BotaoDaBarra(_BotaoDeTela):
    """Botao da barra do Visualizador: texto e nome de icone, quem diz o que
    ele faz e o `aria-label`."""

    def __init__(self, rotulo, tela=None):
        super().__init__("download_for_offline")
        self.rotulo = rotulo
        self.tela = tela

    def get_attribute(self, nome):
        return self.rotulo if nome == "aria-label" else None

    def click(self):
        super().click()
        if self.tela is not None:
            self.tela.caixa_aberta = True


class _BotaoDaCaixaDeSelecao:
    """O botao que liga as marcas, e que TROCA de rotulo quando elas ligam."""

    def __init__(self, tela):
        self.tela = tela

    def get_attribute(self, nome):
        from justica_mcp.dcp import (BOTAO_CAIXA_DE_SELECAO,
                                     BOTAO_OCULTAR_SELECAO)

        if nome != "aria-label":
            return None
        return (BOTAO_OCULTAR_SELECAO if self.tela.selecao_aberta
                else BOTAO_CAIXA_DE_SELECAO)

    def inner_text(self):
        return "check_circle_outline"

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 32, "height": 32}

    def scroll_into_view_if_needed(self):
        pass

    def click(self):
        self.tela.selecao_aberta = not self.tela.selecao_aberta


class _VisualizadorComIndice:
    """O Visualizador com o indice aberto e a caixa de selecao ligada."""

    viewport_size = {"width": 1280, "height": 800}
    url = "https://www3.tjrj.jus.br/visproc/#/xyz"

    def __init__(self, inicios, entrega=True, tem_caixa=True):
        self.itens = [_ItemComMarca(i) for i in inicios]
        self.entrega = entrega
        self.tem_caixa = tem_caixa
        self.downloads = 0
        self.marcados_por_download = []
        # A caixa de download so mostra as escolhas depois de o botao da barra
        # ser clicado, como no portal.
        self.caixa_aberta = False
        from justica_mcp.dcp import (BOTAO_CAIXA_DE_SELECAO, BOTAO_DE_DOWNLOAD,
                                     ESCOLHA_MARCADOS)
        # Os botoes da barra sao achados pelo ROTULO ACESSIVEL, nao pelo
        # texto: o texto deles e o nome do icone ("download_for_offline").
        self.botao = _BotaoDaBarra(BOTAO_DE_DOWNLOAD, self)
        # O botao da caixa de selecao TROCA de rotulo quando a caixa abre, como
        # no portal. Falso que nao troca esconderia o defeito de 08/10/2026.
        self.caixa = _BotaoDaCaixaDeSelecao(self)
        self.selecao_aberta = False
        self.escolha = _BotaoDeTela(ESCOLHA_MARCADOS)
        self._marcados = ESCOLHA_MARCADOS

    def query_selector_all(self, seletor):
        from justica_mcp.dcp import BOTAO_CAIXA_DE_SELECAO, BOTAO_DE_DOWNLOAD
        from justica_mcp.portal import PREFIXO_DE_TEXTO

        from justica_mcp.portal import ALVOS_CLICAVEIS

        if seletor == "[aria-label]":
            return list(self.itens) + [self.botao, self.caixa]
        # `_por_texto_exato` pergunta pelos clicaveis e compara o texto; e
        # assim que a escolha da caixa de download e achada.
        if seletor == ALVOS_CLICAVEIS:
            return [self.escolha] if self.caixa_aberta else []
        return []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def evaluate(self, _c):
        return self.viewport_size

    def wait_for_timeout(self, _ms):
        pass

    def expect_download(self, timeout=None):
        tela = self

        class _Espera:
            def __enter__(_s):
                return _s

            def __exit__(_s, *a):
                if not tela.entrega:
                    raise RuntimeError("TimeoutError: nenhum arquivo")
                tela.downloads += 1
                tela.marcados_por_download.append(
                    [i.inicio for i in tela.itens if i.marca.marcada])
                return False

            @property
            def value(_s):
                class _Arquivo:
                    suggested_filename = "processo.pdf"

                    def save_as(self, caminho):
                        import pathlib

                        pathlib.Path(caminho).write_bytes(b"%PDF-1.4 teste")

                return _Arquivo()

        return _Espera()


def _rotulo_da_caixa(tela, rotulo):
    """`elemento_por_rotulo` procura por atributo; os botoes falsos respondem
    pelo texto. Esta ponte evita reescrever os falsos antigos."""
    return None


def test_a_marca_do_item_e_achada_no_PAI_dele():
    """Conferido em 08/10/2026: `input[type=checkbox] x1 no pai`."""
    from justica_mcp.dcp import marca_do_item

    item = _ItemComMarca(92)
    assert marca_do_item(item) is item.marca


def test_marcar_confere_que_ficou_marcado():
    """Lote com documento de menos vira um PDF incompleto que ninguem volta a
    conferir."""
    from justica_mcp.dcp import esta_marcado, marcar_item

    marca = _Marca()
    assert esta_marcado(marca) is False

    class _Tela:
        def wait_for_timeout(self, _ms):
            pass

    assert marcar_item(marca, _Tela()) is True
    assert esta_marcado(marca) is True
    # Marcar o que ja esta marcado nao desmarca.
    assert marcar_item(marca, _Tela()) is True
    assert esta_marcado(marca) is True


def test_a_marca_que_nao_aceita_clique_e_denunciada():
    from justica_mcp.dcp import marcar_item

    class _Tela:
        def wait_for_timeout(self, _ms):
            pass

    assert marcar_item(_Marca(aceita_documento=False), _Tela()) is False


def test_desmarcar_limpa_o_lote_anterior():
    """Marca que sobra entra no PDF seguinte, e dois arquivos com o mesmo
    documento dentro nao se denunciam sozinhos."""
    from justica_mcp.dcp import desmarcar_tudo, esta_marcado

    marcas = [_Marca(), _Marca(), _Marca()]
    for m in marcas:
        m.marcada = True

    class _Tela:
        def wait_for_timeout(self, _ms):
            pass

    assert desmarcar_tudo(marcas, _Tela()) == 3
    assert all(esta_marcado(m) is False for m in marcas)


def test_o_indice_com_paginas_junta_pagina_item_e_marca():
    from justica_mcp.dcp import indice_com_paginas

    tela = _VisualizadorComIndice([3, 93, 97])
    lido = indice_com_paginas(tela)

    assert [p for p, _, _ in lido] == [3, 93, 97]
    assert all(marca is not None for _, _, marca in lido)


def test_o_item_sem_pagina_legivel_fica_de_fora_da_conta():
    """Documento que some em silencio e o defeito que isto existe para nao ter:
    por isso ele fica de fora da CONTA, e nao da lista de problemas."""
    from justica_mcp.dcp import indice_com_paginas

    class _SemPagina(_ItemComMarca):
        def get_attribute(self, nome):
            return "Baixar o processo atual em PDF" if nome == "aria-label" else None

    tela = _VisualizadorComIndice([3, 93])
    tela.itens.append(_SemPagina(0))

    assert [p for p, _, _ in indice_com_paginas(tela)] == [3, 93]


def test_a_peca_pedida_pela_pagina_e_a_unica_marcada(tmp_path):
    """A pagina e a que aparece ao lado do nome no indice: e ela que
    identifica o documento para quem olha a tela."""
    from justica_mcp.dcp import baixar_uma_peca

    tela = _VisualizadorComIndice([3, 93, 97, 99])
    arquivo = baixar_uma_peca(tela, _Guarda(), tmp_path, "0045025", 93,
                              segundos=2)

    assert tela.downloads == 1
    assert tela.marcados_por_download == [[93]]
    assert "pagina93" in arquivo


def test_pagina_que_nao_existe_no_indice_e_recusada_com_a_lista(tmp_path):
    from justica_mcp.dcp import DownloadIndisponivel, baixar_uma_peca

    tela = _VisualizadorComIndice([3, 93, 97])
    with pytest.raises(DownloadIndisponivel) as erro:
        baixar_uma_peca(tela, _Guarda(), tmp_path, "0045025", 500, segundos=2)

    recado = str(erro.value)
    assert "Nenhum documento comeca na pagina 500" in recado
    assert "3, 93, 97" in recado
    assert tela.downloads == 0


def test_duas_pecas_na_mesma_pagina_param_em_vez_de_chutar(tmp_path):
    """Baixar o errado seria pior que nao baixar."""
    from justica_mcp.dcp import DownloadIndisponivel, baixar_uma_peca

    tela = _VisualizadorComIndice([3, 93, 93])
    with pytest.raises(DownloadIndisponivel, match="2 documentos comecam"):
        baixar_uma_peca(tela, _Guarda(), tmp_path, "0045025", 93, segundos=2)
    assert tela.downloads == 0


def test_os_lotes_saem_na_ordem_e_sem_repetir_documento(tmp_path):
    """Cada documento entra em UM arquivo. Marca que sobra do lote anterior
    entra no PDF seguinte, e isso nao se denuncia sozinho."""
    from justica_mcp.dcp import baixar_em_lotes

    tela = _VisualizadorComIndice([1, 50, 100, 400, 450, 900])
    arquivos = baixar_em_lotes(tela, _Guarda(), tmp_path, "0045025",
                               tamanho=300, segundos=2)

    assert tela.downloads == 3
    assert tela.marcados_por_download == [[1, 50, 100], [400, 450], [900]]
    assert len(arquivos) == 3
    assert "lote1-paginas1a100" in arquivos[0]
    assert "lote3-paginas900a900" in arquivos[2]


def test_um_lote_que_falha_nao_derruba_os_que_deram_certo(tmp_path):
    """Eles ja estao em disco e valem."""
    from justica_mcp.dcp import baixar_em_lotes

    tela = _VisualizadorComIndice([1, 400, 900])
    # O documento do meio nao aceita marcacao.
    tela.itens[1].marca.aceita_documento = False

    arquivos = baixar_em_lotes(tela, _Guarda(), tmp_path, "0045025",
                               tamanho=300, segundos=2)

    assert len(arquivos) == 2
    assert tela.marcados_por_download == [[1], [900]]


def test_sem_nenhum_lote_gravado_o_comando_recusa(tmp_path):
    from justica_mcp.dcp import DownloadIndisponivel, baixar_em_lotes

    tela = _VisualizadorComIndice([1, 400], entrega=False)
    with pytest.raises(DownloadIndisponivel, match="Nenhum lote foi gravado"):
        baixar_em_lotes(tela, _Guarda(), tmp_path, "0045025", 300, segundos=2)


def test_o_indice_vazio_para_antes_de_marcar_qualquer_coisa(tmp_path):
    from justica_mcp.dcp import DownloadIndisponivel, baixar_em_lotes

    tela = _VisualizadorComIndice([])
    with pytest.raises(DownloadIndisponivel, match="nao foi lido"):
        baixar_em_lotes(tela, _Guarda(), tmp_path, "0045025", 300, segundos=2)
    assert tela.downloads == 0


def test_o_caminho_da_selecao_usa_SALVAR_SELECIONADOS_e_nao_CARREGADOS():
    """Guarda de fonte. 'Carregados' traz o processo integral; se o caminho
    dos lotes o usasse, cada lote seria o processo inteiro e ninguem notaria
    pelos arquivos."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.baixar_marcados)
    assert "ESCOLHA_MARCADOS" in fonte
    assert "ESCOLHA_INTEGRAL" not in fonte


# ==========================================================================
# Os lotes como PADRAO, e nao como opcao que o operador precisa lembrar
#
# Instrucao do advogado em 08/10/2026, depois de ver as duas opcoes prontas:
# "eu queria isso como padrao para problemas como esse".
#
# Cair para os lotes sozinho e seguro porque a parte nao se disfarca de
# inteiro: cada arquivo nasce com a faixa de paginas no nome, e o comando diz
# que caiu. O risco que este projeto evita e o CONTRARIO, um PDF parcial
# gravado como integra, e esse continua impossivel.
# ==========================================================================

def test_a_integra_que_nao_vem_cai_sozinha_para_os_lotes():
    """Guarda de fonte: o padrao tenta a integra e, so entao, os lotes."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    # A queda existe, e vem DEPOIS da tentativa de integra.
    assert "INTEGRA NAO VEIO" in fonte
    assert fonte.index("baixar_integra(") < fonte.index("INTEGRA NAO VEIO")
    assert fonte.index("INTEGRA NAO VEIO") < fonte.index(
        "baixar_em_lotes(\n                            janela")


def test_o_nome_do_arquivo_de_lote_carrega_a_faixa_de_paginas(tmp_path):
    """E o que impede uma parte de ser confundida com o processo inteiro."""
    from justica_mcp.dcp import baixar_em_lotes

    tela = _VisualizadorComIndice([1, 400])
    arquivos = baixar_em_lotes(tela, _Guarda(), tmp_path, "0045025",
                               tamanho=300, segundos=2)

    assert all("lote" in a and "paginas" in a for a in arquivos)
    # E nenhum deles se chama "integra".
    assert not any("integra" in a for a in arquivos)


# ==========================================================================
# A tela do processo que ainda nao chegou
#
# 08/10/2026. Esta etapa ja tinha funcionado DUAS vezes e falhou, com o
# quadro ainda em `#/consultaportal` em vez de `#/consultar/detalhes-processo`:
# a busca tinha sido enviada e a tela do processo ainda nao tinha chegado.
#
# E a mesma classe de defeito que ja apareceu na tela de login, na de selecao
# de sistemas, no menu e no botao de enviar o perfil. Eu disse mais de uma
# vez que ia generaliza-la, e aqui ela reapareceu numa funcao que eu mesmo
# mexi no mesmo dia.
# ==========================================================================

class _QuadroQueDemora:
    """O quadro que so vira a tela do processo depois de algumas olhadas."""

    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, olhadas_ate_chegar):
        self.olhadas = 0
        self.ate_chegar = olhadas_ate_chegar
        self.botao = _BotaoDeTela("Processo Eletrônico - Visualizador")

    @property
    def url(self):
        return ("https://www3.tjrj.jus.br/consultaprocessual/#/consultar/"
                "detalhes-processo" if self.olhadas >= self.ate_chegar
                else "https://www3.tjrj.jus.br/consultaprocessual/#/consultaportal")

    def query_selector_all(self, _seletor):
        self.olhadas += 1
        return [self.botao] if self.olhadas >= self.ate_chegar else []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def evaluate(self, _c):
        return self.viewport_size


class _PaginaDoQuadroLento:
    url = "https://www3.tjrj.jus.br/portalservicos/#/consproc/consultaportal"
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, quadro):
        self.quadro = quadro
        self.frames = [self, quadro]

    def query_selector_all(self, _s):
        return []

    def query_selector(self, _s):
        return None

    def evaluate(self, _c):
        return self.viewport_size

    def wait_for_timeout(self, _ms):
        pass


def test_a_tela_do_processo_e_esperada_e_nao_olhada_uma_vez():
    from justica_mcp.dcp import esperar_a_tela_do_processo

    quadro = _QuadroQueDemora(olhadas_ate_chegar=4)
    _achado, botao = esperar_a_tela_do_processo(
        _PaginaDoQuadroLento(quadro), segundos=5)

    assert botao is quadro.botao


def test_a_tela_que_nunca_chega_e_dita_com_o_endereco_do_quadro():
    """Para que a recusa diga EM QUE TELA parou, em vez de so que nao achou."""
    from justica_mcp.dcp import ConsultaIndisponivel, abrir_visualizador

    quadro = _QuadroQueDemora(olhadas_ate_chegar=10**9)
    with pytest.raises(ConsultaIndisponivel) as erro:
        abrir_visualizador(_PaginaDoQuadroLento(quadro), _Guarda(), 1)

    recado = str(erro.value)
    assert "nao apareceu na tela do processo" in recado
    assert "consultaportal" in recado
    assert "a pesquisa nao chegou a devolver o processo" in recado


def test_o_quadro_e_reconsultado_a_cada_volta():
    """Quando a aplicacao troca de rota, o quadro que se tinha em maos pode
    nao ser mais o que esta na tela."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.esperar_a_tela_do_processo)
    # A reconsulta esta DENTRO do laco, e nao so antes dele.
    corpo = fonte[fonte.index("while True:"):]
    assert "quadro_da_consulta(pagina)" in corpo


def test_o_visualizador_nao_olha_mais_uma_vez_so():
    """Guarda de fonte contra a regressao exata de 08/10/2026."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.abrir_visualizador)
    assert "esperar_a_tela_do_processo(pagina, segundos)" in fonte
    assert 'elemento_visivel(quadro, f"texto={BOTAO_VISUALIZADOR}")' not in fonte


# ==========================================================================
# O botao que troca de nome quando a caixa abre
#
# 08/10/2026. O download em lotes recusou dizendo que "Exibir caixa de
# seleção" nao estava na barra, e o relato da mesma corrida mostrava
# `rotulo='Ocultar caixa de seleção'`. Nao havia contradicao: o botao e o
# mesmo e troca de rotulo, e quem tinha aberto a caixa fui EU, no
# reconhecimento do indice que roda quando a integra falha.
#
# Chamar duas vezes nao pode desfazer o que a primeira fez.
# ==========================================================================

def test_abrir_a_caixa_duas_vezes_nao_a_fecha():
    from justica_mcp.dcp import abrir_caixa_de_selecao, caixa_de_selecao_aberta

    tela = _VisualizadorComIndice([3, 93])
    guarda = _Guarda()

    assert abrir_caixa_de_selecao(tela, guarda) is True
    assert caixa_de_selecao_aberta(tela) is True
    # A segunda chamada nao clica em nada, e a caixa continua aberta.
    assert abrir_caixa_de_selecao(tela, guarda) is True
    assert caixa_de_selecao_aberta(tela) is True


def test_a_abertura_tem_prova_positiva():
    """Marcar documento numa caixa fechada nao marca nada."""
    from justica_mcp.dcp import abrir_caixa_de_selecao

    tela = _VisualizadorComIndice([3])
    # Um botao que aceita o clique e nao abre coisa nenhuma.
    tela.caixa.click = lambda: None

    assert abrir_caixa_de_selecao(tela, _Guarda()) is False


def test_os_lotes_funcionam_com_a_caixa_JA_aberta(tmp_path):
    """O caminho exato de 08/10/2026: o reconhecimento abriu, os lotes vieram
    depois."""
    from justica_mcp.dcp import abrir_caixa_de_selecao, baixar_em_lotes

    tela = _VisualizadorComIndice([1, 400, 900])
    guarda = _Guarda()
    abrir_caixa_de_selecao(tela, guarda)  # como faz o reconhecimento

    arquivos = baixar_em_lotes(tela, guarda, tmp_path, "0045025", 300,
                               segundos=2)
    assert len(arquivos) == 3


# ==========================================================================
# Prazo de TELA e prazo de ARQUIVO sao grandezas diferentes
#
# 08/10/2026, a corrida mais longe de todas. As 164 marcacoes deram certo,
# nos quatro lotes: 45 de 45, 32 de 32, 53 de 53, 34 de 34. Os quatro
# downloads morreram em 45 segundos.
#
# O 45 vem de `--segundos`, que e prazo de tela, e estava passando por cima
# de `TETO_DO_DOWNLOAD`, que existe exatamente para isto. O portal nao tem o
# PDF pronto: ele o GERA quando se pede. A tela que nao monta em 45s esta
# quebrada; o PDF de 300 paginas que nao chega em 45s esta so sendo gerado.
# ==========================================================================

def test_o_prazo_do_arquivo_nunca_e_menor_que_o_teto():
    from justica_mcp.dcp import TETO_DO_DOWNLOAD, espera_do_arquivo

    assert TETO_DO_DOWNLOAD >= 300
    # O prazo de tela nao encurta o de arquivo.
    assert espera_do_arquivo(45) == TETO_DO_DOWNLOAD
    assert espera_do_arquivo(0) == TETO_DO_DOWNLOAD
    # Mas um prazo MAIOR, pedido de proposito, vale.
    assert espera_do_arquivo(900) == 900


def test_prazo_ilegivel_nao_vira_espera_zero():
    """Espera zero faria todo download falhar na hora, sem explicacao."""
    from justica_mcp.dcp import TETO_DO_DOWNLOAD, espera_do_arquivo

    assert espera_do_arquivo(None) == TETO_DO_DOWNLOAD
    assert espera_do_arquivo("muito") == TETO_DO_DOWNLOAD


def test_o_download_usa_o_prazo_de_arquivo_e_nao_o_de_tela():
    """Guarda de fonte contra a regressao exata de 08/10/2026."""
    import inspect

    from justica_mcp import dcp

    for funcao in (dcp.baixar_marcados, dcp.baixar_integra):
        fonte = inspect.getsource(funcao)
        assert "espera_do_arquivo(segundos)" in fonte
        assert "timeout=segundos * 1000" not in fonte


def test_a_espera_longa_e_anunciada_antes_de_comecar():
    """Sem isso, cinco minutos de silencio parecem travamento."""
    import inspect

    from justica_mcp import dcp

    fonte = inspect.getsource(dcp.baixar_marcados)
    assert "Esperando ate" in fonte
    assert "gera o PDF" in fonte


# ==========================================================================
# UM lote so
#
# Pedido do advogado em 08/10/2026: "queria que o teste fosse so de um grupo
# mesmo". E uma falha que estava a vista: a propria recusa dizia "repita o
# comando para os que faltam", e o programa nao tinha como repetir um lote.
#
# A divisao nao muda: o lote 2 de quatro tem as mesmas paginas, baixado
# sozinho ou no meio dos outros. Se mudasse, repetir um lote que falhou
# traria outro pedaco do processo, e os arquivos em disco deixariam de se
# encaixar.
# ==========================================================================

def test_um_lote_so_traz_as_MESMAS_paginas_que_traria_no_conjunto(tmp_path):
    from justica_mcp.dcp import baixar_em_lotes

    paginas = [1, 50, 100, 400, 450, 900]

    todos = _VisualizadorComIndice(paginas)
    baixar_em_lotes(todos, _Guarda(), tmp_path, "0045025", 300, segundos=2)

    sozinho = _VisualizadorComIndice(paginas)
    baixar_em_lotes(sozinho, _Guarda(), tmp_path, "0045025", 300, segundos=2,
                    apenas=2)

    assert todos.marcados_por_download[1] == sozinho.marcados_por_download[0]
    assert sozinho.downloads == 1


def test_o_primeiro_lote_e_o_de_numero_1():
    """Contado a partir de 1, como o relato o mostra ("Lote 1/4")."""
    from justica_mcp.dcp import baixar_em_lotes
    import tempfile

    tela = _VisualizadorComIndice([1, 50, 400])
    with tempfile.TemporaryDirectory() as pasta:
        baixar_em_lotes(tela, _Guarda(), pasta, "0045025", 300, segundos=2,
                        apenas=1)
    assert tela.marcados_por_download == [[1, 50]]


def test_lote_que_nao_existe_para_e_diz_quantos_ha(tmp_path):
    from justica_mcp.dcp import DownloadIndisponivel, baixar_em_lotes

    tela = _VisualizadorComIndice([1, 400])
    with pytest.raises(DownloadIndisponivel, match="tem 2 lote"):
        baixar_em_lotes(tela, _Guarda(), tmp_path, "0045025", 300, segundos=2,
                        apenas=9)
    assert tela.downloads == 0
