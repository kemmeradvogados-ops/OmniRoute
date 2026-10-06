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
    assert "nao baixar de uma vez" in recado
    assert "caixa de selecao" in recado


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


class _PortalDeServicos:
    url = "https://www3.tjrj.jus.br/portalservicos/#/consproc/consultaportal"
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, quadro):
        self.quadro = quadro
        self.frames = [self, quadro]
        self.navegou = []

    def goto(self, destino, **kw):
        self.navegou.append(destino)

    def query_selector_all(self, _):
        return []

    def query_selector(self, _):
        return None

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
    def __init__(self, tela):
        self.tela = tela

    def expect_page(self, timeout=None):
        if not self.tela.abre_aba:
            raise RuntimeError("TimeoutError: nenhuma aba nova")
        return _EsperaDeAba(self.tela)


class _TelaDeSelecao:
    url = "https://www3.tjrj.jus.br/idserverjus-front/#/selecao-sistemas"
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, opcoes=None, tem_lista=True, tem_enviar=True,
                 abre_aba=True):
        self.cliques = []
        self.abre_aba = abre_aba
        self.context = _Contexto(self)
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


def test_sem_aba_nova_devolve_a_propria_tela():
    """Pode ter aberto na propria aba. Quem julga e a conferencia do formulario
    da consulta, que diz o que achou."""
    tela, guarda = _TelaDeSelecao(abre_aba=False), _Guarda()
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

    def evaluate(self, _):
        return list(self.textos)

    def select_option(self, label=None, **kw):
        self.escolhido = label

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 5, "y": 5, "width": 200, "height": 30}


class _TelaDePerfil:
    viewport_size = {"width": 1280, "height": 800}

    def __init__(self, url="https://www3.tjrj.jus.br/portalservicos/#/usuarios/alterar-perfil",
                 com_select=True, textos=("Usuário Comum", "Advogado")):
        self.url = url
        self.cliques = []
        self.lista = _ListaDePerfil(self, textos) if com_select else None
        self.botoes = [_BotaoDoQuadro(self, "Entrar"),
                       _BotaoDoQuadro(self, "Cancelar")]
        if not com_select:
            self.botoes.append(_BotaoDoQuadro(self, "Selecione perfil do usuário"))
            self.botoes.extend(_BotaoDoQuadro(self, t) for t in textos)

    def query_selector_all(self, seletor):
        if seletor.startswith("select"):
            return [self.lista] if self.lista else []
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
