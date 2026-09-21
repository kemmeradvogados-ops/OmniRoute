"""Reconhecimento de portal.

O comando so LE a estrutura da pagina. O que se testa aqui e a autorizacao:
o endereco que o operador digita vira permissao efemera, e nada alem dele
passa, nem mesmo uma pagina vizinha do mesmo portal.
"""

import pytest

from justica_mcp.core.guarda_navegacao import Acao, GuardaNavegacao, Modo
from justica_mcp.portal import PortalIndisponivel, permissao_efemera

ENDERECO = "https://eproc1g.tjrj.jus.br/eproc/externo_controlador.php?acao=principal"


def _guarda(url=ENDERECO):
    return GuardaNavegacao(modo=Modo.ENSAIO, permissoes=[permissao_efemera(url)])


def test_autoriza_o_endereco_digitado_pelo_operador():
    assert _guarda().avaliar(Acao.NAVEGAR, ENDERECO).permitido is True


def test_nao_autoriza_pagina_vizinha_do_mesmo_portal():
    """Autorizar um endereco nao pode liberar o portal inteiro: a pagina ao
    lado pode ser justamente a de expedientes."""
    vizinha = "https://eproc1g.tjrj.jus.br/eproc/outra_pagina.php"
    assert _guarda().avaliar(Acao.NAVEGAR, vizinha).permitido is False


def test_nao_autoriza_outro_dominio():
    assert _guarda().avaliar(Acao.NAVEGAR, "https://outro.jus.br/eproc").permitido is False


def test_query_string_diferente_no_mesmo_caminho_continua_autorizada():
    """A ancora e esquema, dominio e caminho. Parametro de consulta varia a
    cada sessao e travar nele tornaria o comando inutilizavel."""
    outra = ENDERECO.replace("acao=principal", "acao=principal&x=1")
    assert _guarda().avaliar(Acao.NAVEGAR, outra).permitido is True


def test_termo_de_risco_bloqueia_mesmo_o_endereco_digitado():
    """Se o operador colar sem querer o endereco de abertura de expediente, a
    trava barra. A autorizacao dele nao vence a segunda camada."""
    perigoso = "https://eproc1g.tjrj.jus.br/eproc/dar-ciencia.php?id=9"
    assert _guarda(perigoso).avaliar(Acao.NAVEGAR, perigoso).permitido is False


def test_endereco_sem_esquema_e_recusado_com_orientacao():
    with pytest.raises(PortalIndisponivel, match="barra do navegador"):
        permissao_efemera("eproc1g.tjrj.jus.br/eproc")


def test_esquema_de_arquivo_e_recusado():
    with pytest.raises(PortalIndisponivel):
        permissao_efemera("file:///C:/algum/arquivo.html")


def test_clique_continua_bloqueado_mesmo_na_tela_autorizada():
    """Reconhecimento e somente leitura: autorizar o endereco nao autoriza
    interagir com ele."""
    g = _guarda()
    assert g.avaliar(Acao.CLICAR, "#btnEntrar", url=ENDERECO).permitido is False
    assert g.avaliar(Acao.PREENCHER, "#txtSenha", url=ENDERECO).permitido is False


def test_leitura_de_estrutura_e_permitida():
    assert _guarda().avaliar(Acao.LER, "formulario").permitido is True


# ---------------- campo real contra campo espelho ----------------

class _Elemento:
    """Dublê do elemento do Playwright, com apenas a caixa delimitadora."""

    def __init__(self, caixa):
        self._caixa = caixa

    def bounding_box(self):
        return self._caixa


def _caixa(x, y, largura=120, altura=24):
    return {"x": x, "y": y, "width": largura, "height": altura}


def test_campo_dentro_da_tela():
    from justica_mcp.portal import _na_tela

    assert _na_tela(_Elemento(_caixa(10, 200)), 1280, 720) is True


def test_campo_empurrado_para_fora_da_tela():
    """Padrao classico de campo espelho: `position:absolute; left:-9999px`.
    O `is_visible` do Playwright devolve verdadeiro nesse caso, porque so exige
    caixa nao vazia, entao confiar nele confundiria o espelho com o campo real
    e o preenchimento falharia sem mensagem. Defeito encontrado ao testar o
    reconhecimento contra uma pagina que reproduz a estrutura do eproc."""
    from justica_mcp.portal import _na_tela

    assert _na_tela(_Elemento(_caixa(-9999, 200)), 1280, 720) is False


def test_campo_acima_ou_abaixo_da_area_visivel():
    from justica_mcp.portal import _na_tela

    assert _na_tela(_Elemento(_caixa(10, -500)), 1280, 720) is False
    assert _na_tela(_Elemento(_caixa(10, 5000)), 1280, 720) is False
    assert _na_tela(_Elemento(_caixa(5000, 200)), 1280, 720) is False


def test_elemento_sem_caixa_nao_esta_na_tela():
    """`display:none` nao produz caixa."""
    from justica_mcp.portal import _na_tela

    assert _na_tela(_Elemento(None), 1280, 720) is False


def test_campo_na_borda_ainda_conta_como_na_tela():
    from justica_mcp.portal import _na_tela

    assert _na_tela(_Elemento(_caixa(-10, 200)), 1280, 720) is True, "parcialmente visivel"
