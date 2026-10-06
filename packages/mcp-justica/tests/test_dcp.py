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
