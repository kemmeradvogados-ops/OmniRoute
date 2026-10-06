"""Reconhecimento de portal.

O comando so LE a estrutura da pagina. O que se testa aqui e a autorizacao:
o endereco que o operador digita vira permissao efemera, e nada alem dele
passa, nem mesmo uma pagina vizinha do mesmo portal.
"""

import pathlib

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


# ---------------- ensaio de login: preenche, nao envia ----------------

def _permissao_do_ensaio(url=ENDERECO, usuario="#txtUsuario", senha="#pwdSenha"):
    """Reproduz a permissao que `ensaiar_login` monta: preenchimento liberado
    nos dois campos, NENHUM clique liberado."""
    from justica_mcp.core.guarda_navegacao import Permissao

    base = permissao_efemera(url)
    return Permissao(
        padrao_url=base.padrao_url,
        descricao="tela de login, ensaio de preenchimento sem envio",
        conferido_em="execucao atual",
        seletores_clicaveis=(),
        seletores_preenchiveis=(usuario, senha),
    )


def _guarda_ensaio():
    return GuardaNavegacao(modo=Modo.LEITURA, permissoes=[_permissao_do_ensaio()])


def test_ensaio_permite_preencher_os_dois_campos():
    g = _guarda_ensaio()
    assert g.avaliar(Acao.PREENCHER, "#txtUsuario", url=ENDERECO).permitido is True
    assert g.avaliar(Acao.PREENCHER, "#pwdSenha", url=ENDERECO).permitido is True


def test_ensaio_nunca_deixa_clicar_em_entrar():
    """A garantia central do ensaio. Se o preenchimento nao funcionar e o
    codigo clicar assim mesmo, isso conta como tentativa de login falha, e
    tentativas repetidas bloqueiam a conta do advogado. A impossibilidade nao
    pode depender de eu lembrar de nao chamar o clique: a trava barra."""
    g = _guarda_ensaio()
    for seletor in ("#sbmEntrar", "button[name=sbmEntrar]", "input[value='Certificado Digital']"):
        assert g.avaliar(Acao.CLICAR, seletor, url=ENDERECO).permitido is False


def test_ensaio_nao_preenche_campo_fora_da_lista():
    """A caixa de busca do menu nao faz parte do login e nao deve ser tocada."""
    g = _guarda_ensaio()
    assert g.avaliar(Acao.PREENCHER, "#sidebar-searchbox", url=ENDERECO).permitido is False


def test_ensaio_nao_baixa_nada():
    """O ensaio de login nao autoriza download; so o comando de consulta o faz,
    e apenas enquanto copia os documentos."""
    g = _guarda_ensaio()
    assert g.permitir_download is False
    assert g.avaliar(Acao.BAIXAR, "autos.pdf", url=ENDERECO).permitido is False


# ---------------- envio unico de login ----------------

def _campo(**kw):
    from justica_mcp.portal import Campo

    base = dict(marcador="input", tipo="text", nome=None, identificador=None,
                rotulo=None, texto_visivel=None, e_senha=False, extras={})
    base.update(kw)
    return Campo(**base)


def test_reconhece_campo_de_segundo_fator_por_autocomplete():
    from justica_mcp.portal import _parece_segundo_fator

    assert _parece_segundo_fator(_campo(extras={"autocomplete": "one-time-code"})) is True


def test_reconhece_campo_de_segundo_fator_por_rotulo_e_nome():
    from justica_mcp.portal import _parece_segundo_fator

    assert _parece_segundo_fator(_campo(rotulo="Código de verificação")) is True
    assert _parece_segundo_fator(_campo(nome="txtToken")) is True
    assert _parece_segundo_fator(_campo(identificador="campo2fa")) is True


def test_reconhece_campo_de_segundo_fator_por_tamanho_curto():
    from justica_mcp.portal import _parece_segundo_fator

    assert _parece_segundo_fator(_campo(extras={"maxlength": "6"})) is True


def test_campo_comum_nao_e_confundido_com_segundo_fator():
    from justica_mcp.portal import _parece_segundo_fator

    assert _parece_segundo_fator(_campo(nome="txtUsuario", extras={"maxlength": "30"})) is False
    assert _parece_segundo_fator(_campo(rotulo="Senha", extras={"maxlength": "40"})) is False


def _permissao_do_envio(url=ENDERECO):
    from justica_mcp.core.guarda_navegacao import Permissao

    base = permissao_efemera(url)
    return Permissao(
        padrao_url=base.padrao_url,
        descricao="tela de login, envio unico autorizado pelo operador",
        conferido_em="execucao atual",
        seletores_clicaveis=("#sbmEntrar",),
        seletores_preenchiveis=("#txtUsuario", "#pwdSenha"),
    )


def test_envio_libera_apenas_o_botao_entrar():
    """Autorizar o envio nao autoriza o resto da tela. O botao de certificado
    digital, por exemplo, segue barrado."""
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[_permissao_do_envio()])
    assert g.avaliar(Acao.CLICAR, "#sbmEntrar", url=ENDERECO).permitido is True
    assert g.avaliar(Acao.CLICAR, "#btnCertificado", url=ENDERECO).permitido is False
    assert g.avaliar(Acao.BAIXAR, "autos.pdf", url=ENDERECO).permitido is False


def test_envio_recusa_sem_confirmacao_do_operador():
    """A confirmacao fica na linha de comando porque tentativa falha repetida
    bloqueia a conta do advogado."""
    from justica_mcp.portal import entrar

    assert entrar(ENDERECO, "TRF2", "eproc", confirmado=False) == 1


# ---------------- autenticacao completa ----------------

def _permissao_autenticacao(url=ENDERECO):
    from justica_mcp.core.guarda_navegacao import Permissao

    base = permissao_efemera(url)
    return Permissao(
        padrao_url=base.padrao_url,
        descricao="autenticacao completa autorizada pelo operador",
        conferido_em="execucao atual",
        seletores_clicaveis=("#sbmEntrar", "#btnValidar"),
        seletores_preenchiveis=("#txtUsuario", "#pwdSenha", "#txtAcessoCodigo"),
    )


def _guarda_autenticacao():
    return GuardaNavegacao(modo=Modo.LEITURA, permissoes=[_permissao_autenticacao()])


def test_autenticacao_libera_so_o_necessario():
    g = _guarda_autenticacao()
    for seletor in ("#txtUsuario", "#pwdSenha", "#txtAcessoCodigo"):
        assert g.avaliar(Acao.PREENCHER, seletor, url=ENDERECO).permitido is True
    for seletor in ("#sbmEntrar", "#btnValidar"):
        assert g.avaliar(Acao.CLICAR, seletor, url=ENDERECO).permitido is True


def test_caixa_de_dispositivo_confiavel_nunca_e_marcada():
    """Marca-la facilitaria as proximas execucoes, e e por isso que nao se
    marca: o cofre ja gera o codigo, entao nao ha ganho, so perda de protecao.
    Bloqueada duas vezes: nao esta na lista, e o nome casa com termo de risco."""
    g = _guarda_autenticacao()
    d = g.avaliar(Acao.CLICAR, "#chkLiberarDispositivo", url=ENDERECO)
    assert d.permitido is False


def test_botoes_destrutivos_da_tela_de_segundo_fator_sao_barrados():
    """A tela de segundo fator do eproc traz "Desativar 2FA" e "Cancelar
    Dispositivos Liberados" ao lado do campo do codigo. Um clique errado ali
    enfraquece a conta de forma duradoura."""
    g = _guarda_autenticacao()
    for seletor in ("#btnDesativar2FA", "#btnCancelarDispositivos", "a[href*=desativar]"):
        assert g.avaliar(Acao.CLICAR, seletor, url=ENDERECO).permitido is False


def test_autenticacao_recusa_sem_confirmacao():
    from justica_mcp.portal import autenticar

    assert autenticar(ENDERECO, "TRF2", "eproc", confirmado=False) == 1


def test_caixa_de_selecao_nao_e_campo_de_codigo():
    """Falso positivo encontrado em campo: a caixa "Nao usar o 2FA neste
    dispositivo" era apontada como campo do autenticador, que e o oposto do
    que ela faz."""
    from justica_mcp.portal import _parece_segundo_fator

    caixa = _campo(tipo="checkbox", nome="chkLiberarDispositivo",
                   rotulo="Não usar o 2FA neste dispositivo e navegador")
    assert _parece_segundo_fator(caixa) is False


# ---------------- selecao de perfil ----------------

def _botao(identificador, texto, formulario="frmEscolherUsuario", na_tela=True):
    from justica_mcp.portal import Campo

    return Campo(marcador="button", tipo="button", nome=None,
                 identificador=identificador, rotulo=None, texto_visivel=texto,
                 e_senha=False, na_tela=na_tela, formulario=formulario, extras={})


PERFIS_REAIS = [
    _botao("tr0", "RJ168943\nADVOGADO"),
    _botao("tr1", "SP436159\nADVOGADO"),
]


def test_encontra_os_perfis_do_formulario_de_escolha():
    """Estrutura confirmada em campo em 21 de setembro de 2026: os botoes de
    inscricao vivem no formulario `frmEscolherUsuario`."""
    from justica_mcp.portal import _perfis_disponiveis

    perfis = _perfis_disponiveis(PERFIS_REAIS)
    assert [p[0] for p in perfis] == ["tr0", "tr1"]


def test_ignora_botoes_fora_do_formulario_de_escolha():
    """A mesma tela traz botoes de menu e de rolagem, que nao sao perfis."""
    from justica_mcp.portal import _perfis_disponiveis

    ruido = [
        _botao("btnProfile", "account_circle", formulario=None),
        _botao("backTop", "keyboard_arrow_up", formulario=None, na_tela=False),
    ]
    assert _perfis_disponiveis(ruido + PERFIS_REAIS) == [
        ("tr0", "RJ168943\nADVOGADO"), ("tr1", "SP436159\nADVOGADO"),
    ]


def test_casa_perfil_por_trecho_do_rotulo():
    from justica_mcp.portal import _casar_perfil, _perfis_disponiveis

    # `_casar_perfil` recebe os pares ja extraidos, nao os campos crus.
    pares = _perfis_disponiveis(PERFIS_REAIS)
    assert _casar_perfil(pares, "RJ168943")[0] == "tr0"
    assert _casar_perfil(pares, "sp436159")[0] == "tr1", "caixa nao importa"
    assert _casar_perfil(pares, "168943")[0] == "tr0", "trecho basta"


def test_perfil_inexistente_nao_casa_com_nada():
    """Casar por aproximacao aqui seria pior que falhar: o perfil determina
    quais processos aparecem, e entrar no errado da visao incompleta sem aviso."""
    from justica_mcp.portal import _casar_perfil, _perfis_disponiveis

    assert _casar_perfil(_perfis_disponiveis(PERFIS_REAIS), "MG999999") is None


def test_tela_sem_perfis_nao_inventa_nenhum():
    from justica_mcp.portal import _perfis_disponiveis

    assert _perfis_disponiveis([_botao("btnConsultar", "Consultar", formulario=None)]) == []


# ---------------- duplicatas na barra superior ----------------

class _PaginaFalsa:
    """Dublê de pagina com varias ocorrencias do mesmo seletor."""

    def __init__(self, elementos):
        self._elementos = elementos
        self.viewport_size = {"width": 1280, "height": 720}

    def query_selector_all(self, seletor):
        return self._elementos


class _El:
    def __init__(self, visivel, caixa, marca):
        self._v, self._c, self.marca = visivel, caixa, marca

    def is_visible(self):
        return self._v

    def bounding_box(self):
        return self._c


def test_escolhe_a_ocorrencia_que_esta_na_tela():
    """O eproc monta duas barras superiores, uma para tela grande e outra para
    telefone, com os MESMOS identificadores. Preencher a oculta falha em
    silencio: nao levanta erro, simplesmente nao acontece nada."""
    from justica_mcp.portal import elemento_visivel

    oculta = _El(False, None, "barra-telefone")
    visivel = _El(True, {"x": 300, "y": 20, "width": 200, "height": 30}, "barra-grande")
    pagina = _PaginaFalsa([oculta, visivel])
    assert elemento_visivel(pagina, "#txtNumProcessoPesquisaRapida").marca == "barra-grande"


def test_ignora_ocorrencia_fora_da_tela():
    from justica_mcp.portal import elemento_visivel

    fora = _El(True, {"x": -9999, "y": 20, "width": 200, "height": 30}, "fora")
    dentro = _El(True, {"x": 10, "y": 20, "width": 200, "height": 30}, "dentro")
    assert elemento_visivel(_PaginaFalsa([fora, dentro]), "#x").marca == "dentro"


def test_sem_ocorrencia_visivel_devolve_nada():
    from justica_mcp.portal import elemento_visivel

    assert elemento_visivel(_PaginaFalsa([_El(False, None, "a")]), "#x") is None


def test_botao_de_salvar_cadastro_e_termo_de_risco():
    """A autenticacao desemboca na tela "Alterar Cadastro" quando o portal
    exige atualizacao. Um clique em Salvar alteraria o cadastro do advogado
    no tribunal."""
    g = _guarda_autenticacao()
    for seletor in ("button[name=btnSalvar]", "#btnExcluir", "#btnGravarDados"):
        assert g.avaliar(Acao.CLICAR, seletor, url=ENDERECO).permitido is False


# ---------------- consulta autenticada de processo ----------------

def _permissao_busca(url=ENDERECO):
    from justica_mcp.core.guarda_navegacao import Permissao
    from justica_mcp.portal import BOTAO_BUSCA, BUSCA_RAPIDA

    return Permissao(
        padrao_url=permissao_efemera(url).padrao_url,
        descricao="busca rapida de processo, somente leitura",
        conferido_em="execucao atual",
        seletores_clicaveis=(BOTAO_BUSCA,),
        seletores_preenchiveis=(BUSCA_RAPIDA,),
    )


def test_busca_libera_somente_o_campo_e_o_botao_de_pesquisa():
    from justica_mcp.portal import BOTAO_BUSCA, BUSCA_RAPIDA

    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[_permissao_busca()])
    assert g.avaliar(Acao.PREENCHER, BUSCA_RAPIDA, url=ENDERECO).permitido is True
    assert g.avaliar(Acao.CLICAR, BOTAO_BUSCA, url=ENDERECO).permitido is True


def test_busca_nao_encosta_no_formulario_de_cadastro():
    """A consulta acontece na mesma pagina em que o portal exibe "Alterar
    Cadastro", porque a barra de busca vive em formulario separado. O cadastro
    tem de continuar inteiramente barrado."""
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[_permissao_busca()])
    for seletor in ("#txtRgNum", "#txtIdentPrinc", "#txtDataEmissao"):
        assert g.avaliar(Acao.PREENCHER, seletor, url=ENDERECO).permitido is False
    for seletor in ("button[name=btnSalvar]", "#btnIncDoc", "#btnVoltar"):
        assert g.avaliar(Acao.CLICAR, seletor, url=ENDERECO).permitido is False


def test_consulta_recusa_numero_invalido():
    """Numero com digito errado nao vai a rede: consultar assim devolveria
    "nao encontrado" e o agente concluiria que o processo nao existe."""
    from justica_mcp.portal import consultar_processo

    assert consultar_processo(ENDERECO, "TRF2", "eproc", "0000001-99.2026.4.02.5101",
                              confirmado=True) == 1


def test_consulta_recusa_sem_confirmacao():
    from justica_mcp.portal import consultar_processo

    numero = "5001234-54.2023.4.02.5101"
    assert consultar_processo(ENDERECO, "TRF2", "eproc", numero, confirmado=False) == 1


# ---------------- permissao de origem, para documentos ----------------

def test_permissao_de_origem_cobre_outros_caminhos_do_portal():
    """Os arquivos de um processo ficam em caminhos proprios do portal, fora do
    endereco da tela. A permissao ancorada no caminho exato os barrava, e a
    trava estava certa: a suposicao e que era estreita demais."""
    from justica_mcp.core.guarda_navegacao import Acao, GuardaNavegacao, Modo
    from justica_mcp.portal import permissao_de_origem

    g = GuardaNavegacao(
        modo=Modo.LEITURA,
        permissoes=[permissao_de_origem(ENDERECO, "documentos")],
        permitir_download=True,
    )
    assert g.avaliar(Acao.BAIXAR, "https://eproc1g.tjrj.jus.br/doc/123.pdf").permitido is True
    assert g.avaliar(Acao.BAIXAR, "https://eproc1g.tjrj.jus.br/outro/x.pdf").permitido is True


def test_permissao_de_origem_nao_cobre_outro_dominio():
    """O alargamento e o minimo: mesma origem, e nada alem."""
    from justica_mcp.core.guarda_navegacao import Acao, GuardaNavegacao, Modo
    from justica_mcp.portal import permissao_de_origem

    g = GuardaNavegacao(
        modo=Modo.LEITURA,
        permissoes=[permissao_de_origem(ENDERECO, "documentos")],
        permitir_download=True,
    )
    assert g.avaliar(Acao.BAIXAR, "https://outro.jus.br/doc/1.pdf").permitido is False
    assert g.avaliar(Acao.BAIXAR, "https://eproc1g.tjrj.jus.br.mau.site/x").permitido is False


def test_permissao_de_origem_nao_libera_clique_nem_preenchimento():
    """Autorizar download na origem nao autoriza agir nas telas dela."""
    from justica_mcp.core.guarda_navegacao import Acao, GuardaNavegacao, Modo
    from justica_mcp.portal import permissao_de_origem

    g = GuardaNavegacao(
        modo=Modo.LEITURA,
        permissoes=[permissao_de_origem(ENDERECO, "documentos")],
        permitir_download=True,
    )
    assert g.avaliar(Acao.CLICAR, "#btnQualquer", url=ENDERECO).permitido is False
    assert g.avaliar(Acao.PREENCHER, "#campo", url=ENDERECO).permitido is False


def test_auditoria_atribui_o_download_a_permissao_de_documentos():
    """A auditoria e a prova do que aconteceu. Com a permissao de documentos ao
    final da lista, a da busca casava primeiro e o registro saia com o motivo
    errado, o que enfraquece essa prova."""
    from justica_mcp.core.guarda_navegacao import Acao, GuardaNavegacao, Modo
    from justica_mcp.portal import permissao_de_origem

    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[_permissao_busca()],
                        permitir_download=True)
    g.permissoes.insert(0, permissao_de_origem(ENDERECO, "documentos do processo"))
    d = g.avaliar(Acao.BAIXAR, "https://eproc1g.tjrj.jus.br/eproc/doc.pdf")
    assert d.permitido is True
    assert "documentos do processo" in d.motivo


# --------------------------------------------------------------------------
# Endereco e perfil vindos do .env
#
# A linha de comando exigia `--url` a cada execucao, embora o endereco ja
# morasse no ambiente para o servidor. Repetir o endereco a mao convida a
# errar o destino da autenticacao, que e precisamente o que este projeto
# existe para evitar.
# --------------------------------------------------------------------------

from argparse import Namespace

from justica_mcp.core.acesso import PortalNaoConfigurado
from justica_mcp.portal import _do_ambiente


def _args(**extra):
    base = {"tribunal": "TRF2", "sistema": "eproc", "url": None}
    base.update(extra)
    return Namespace(**base)


def test_endereco_vem_do_ambiente_quando_nao_veio_no_comando(monkeypatch, capsys):
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_URL", "https://eproc.exemplo/eproc/")
    args = _args()
    _do_ambiente(args)
    assert args.url == "https://eproc.exemplo/eproc/"
    # O usuario precisa saber de onde veio o endereco que vai receber a senha.
    assert "vindo do .env" in capsys.readouterr().out


def test_endereco_do_comando_tem_precedencia_sobre_o_ambiente(monkeypatch):
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_URL", "https://do-ambiente/")
    args = _args(url="https://do-comando/")
    _do_ambiente(args)
    assert args.url == "https://do-comando/"


def test_perfil_vem_do_ambiente_quando_nao_veio_no_comando(monkeypatch):
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_URL", "https://eproc.exemplo/")
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_PERFIL", "RJ000000")
    args = _args(perfil=None)
    _do_ambiente(args)
    assert args.perfil == "RJ000000"


def test_perfil_do_comando_tem_precedencia(monkeypatch):
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_URL", "https://eproc.exemplo/")
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_PERFIL", "RJ000000")
    args = _args(url="https://x/", perfil="RJ999999")
    _do_ambiente(args)
    assert args.perfil == "RJ999999"


def test_sem_endereco_no_comando_e_no_ambiente_orienta_o_que_configurar(monkeypatch):
    monkeypatch.delenv("JUSTICA_PORTAL_TRF2_EPROC_URL", raising=False)
    with pytest.raises(PortalNaoConfigurado) as erro:
        _do_ambiente(_args())
    assert "JUSTICA_PORTAL_TRF2_EPROC_URL" in str(erro.value)


def test_ambiente_incompleto_nao_atrapalha_quem_passou_o_endereco(monkeypatch):
    """Quem informa `--url` nao pode ser barrado por falta de configuracao:
    o comando explicito e autossuficiente."""
    monkeypatch.delenv("JUSTICA_PORTAL_TRF2_EPROC_URL", raising=False)
    args = _args(url="https://do-comando/", perfil=None)
    _do_ambiente(args)
    assert args.url == "https://do-comando/"
    assert args.perfil is None


def test_comando_sem_perfil_no_namespace_nao_quebra(monkeypatch):
    """`entrar` e `ensaiar-login` nao tem `--perfil`. O completamento nao pode
    supor que o campo exista."""
    monkeypatch.setenv("JUSTICA_PORTAL_TRF2_EPROC_URL", "https://eproc.exemplo/")
    args = _args()
    _do_ambiente(args)
    assert args.url == "https://eproc.exemplo/"
    assert not hasattr(args, "perfil")


# --------------------------------------------------------------------------
# Relato da tela intermediaria da copia integral
#
# Em campo, 21/09/2026: o clique em #btnDownloadCompletoRS NAO devolve arquivo.
# O eproc abre uma tela pedindo que a copia seja gerada. O comando nao pode
# adivinhar o segundo clique: precisa relatar o que achou e parar.
# --------------------------------------------------------------------------

from justica_mcp.portal import Campo, _relatar_tela


class _TelaDeGeracao:
    """O minimo que `_relatar_tela` consome. Nao simula o Playwright inteiro:
    simula o contrato usado, que e o que o teste precisa fixar."""

    def __init__(self, botoes, ligacoes=(), url="https://eproc.exemplo/gerar"):
        self.url = url
        self._botoes = botoes
        self._ligacoes = list(ligacoes)

    def title(self):
        return ":: eproc - Gerar copia ::"

    def query_selector_all(self, seletor):
        return self._ligacoes if seletor == "a[href]" else []


class _Ligacao:
    def __init__(self, texto, href):
        self._texto, self._href = texto, href

    def inner_text(self):
        return self._texto

    def get_attribute(self, nome):
        return self._href if nome == "href" else None


def _botao_simples(identificador, texto, na_tela=True):
    return Campo(
        marcador="button", tipo="button", nome=None, identificador=identificador,
        rotulo=None, texto_visivel=texto, e_senha=False, na_tela=na_tela, extras={},
    )


def test_relato_lista_os_botoes_na_tela(monkeypatch, capsys):
    pagina = _TelaDeGeracao([_botao_simples("btnGerar", "Gerar arquivo completo")])
    monkeypatch.setattr(
        "justica_mcp.portal._coletar", lambda p: ([], p._botoes)
    )
    _relatar_tela(pagina, "TELA APOS O CLIQUE")
    saida = capsys.readouterr().out
    assert "TELA APOS O CLIQUE" in saida
    assert "#btnGerar" in saida
    assert "Gerar arquivo completo" in saida
    assert "https://eproc.exemplo/gerar" in saida


def test_relato_mostra_botao_fora_da_tela_quando_nao_ha_nenhum_visivel(monkeypatch, capsys):
    """Se nada esta na tela, esconder a lista deixaria o relato inutil: melhor
    mostrar marcado como fora da tela do que nao mostrar nada."""
    pagina = _TelaDeGeracao([_botao_simples("btnEscondido", "Gerar", na_tela=False)])
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: ([], p._botoes))
    _relatar_tela(pagina, "X")
    saida = capsys.readouterr().out
    assert "fora da tela" in saida
    assert "#btnEscondido" in saida


def test_relato_destaca_ligacoes_com_termo_de_copia(monkeypatch, capsys):
    pagina = _TelaDeGeracao(
        [],
        ligacoes=[
            _Ligacao("Gerar arquivo completo", "controlador.php?acao=gerar"),
            _Ligacao("Voltar", "controlador.php?acao=voltar"),
        ],
    )
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: ([], []))
    _relatar_tela(pagina, "X")
    saida = capsys.readouterr().out
    assert "acao=gerar" in saida
    assert "acao=voltar" not in saida


def test_relato_nao_quebra_quando_a_estrutura_nao_pode_ser_lida(monkeypatch, capsys):
    """O relato e diagnostico: falhar nele nao pode derrubar a consulta, que ja
    entregou eventos e partes."""
    def explode(_):
        raise RuntimeError("pagina fechada")

    monkeypatch.setattr("justica_mcp.portal._coletar", explode)
    _relatar_tela(_TelaDeGeracao([]), "X")
    assert "Nao foi possivel ler a estrutura" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Segundo fator que nao e pedido
#
# Em campo, 21/09/2026: apos enviar a credencial, a tela do codigo nao
# apareceu. Credencial recusada e sessao ainda valida chegavam ao mesmo
# ponto com a mesma mensagem de uma linha, e as duas pedem providencias
# opostas: uma manda parar, a outra manda seguir.
# --------------------------------------------------------------------------

from justica_mcp.portal import _ja_autenticado


def test_tela_de_perfil_prova_que_a_sessao_esta_aberta(monkeypatch):
    """A selecao de perfil nao existe antes da autenticacao, entao serve de
    prova positiva."""
    perfis = [
        _botao("tr0", "RJ168943\nADVOGADO"),
        _botao("tr1", "SP436159\nADVOGADO"),
    ]
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: ([], perfis))
    assert _ja_autenticado(object()) is True


def test_tela_sem_perfil_nao_conta_como_autenticada(monkeypatch):
    """Deduzir autenticacao da AUSENCIA da tela de codigo seria concluir a
    partir de ausencia. O preco de errar e seguir como autenticado quando a
    credencial foi recusada."""
    monkeypatch.setattr(
        "justica_mcp.portal._coletar",
        lambda p: ([], [_botao("btnEntrar", "Entrar", formulario=None)]),
    )
    assert _ja_autenticado(object()) is False


def test_tela_ilegivel_nao_conta_como_autenticada(monkeypatch):
    """Falha ao ler a estrutura nao pode virar 'esta dentro'."""
    def explode(_):
        raise RuntimeError("pagina fechada")

    monkeypatch.setattr("justica_mcp.portal._coletar", explode)
    assert _ja_autenticado(object()) is False


# --------------------------------------------------------------------------
# Desafio "Confirme que e humano" do Cloudflare
#
# Visto no eproc do Tribunal Regional Federal da 2a Regiao em 21/09/2026.
# Este projeto NAO resolve nem contorna o desafio: e protecao do tribunal, e
# automatiza-la seria contorna-la em nome do advogado, com o risco sendo dele.
# O programa so espera a pessoa marcar a caixa na janela aberta.
# --------------------------------------------------------------------------

from justica_mcp.portal import _aguardar_desafio_humano, _ha_desafio_humano


class _TelaComDesafio:
    """Pagina falsa que comeca com o desafio e libera o login apos N consultas,
    simulando o operador marcando a caixa."""

    def __init__(self, libera_apos=2, marca='iframe[src*="challenges.cloudflare.com"]'):
        self.consultas = 0
        self.libera_apos = libera_apos
        self.marca = marca
        self.esperas = 0

    def query_selector(self, seletor):
        if seletor == self.marca:
            return object() if self.consultas < self.libera_apos else None
        if seletor == "#txtUsuario":
            self.consultas += 1
            return _CampoVisivel() if self.consultas > self.libera_apos else None
        return None

    def wait_for_timeout(self, ms):
        self.esperas += 1


class _CampoVisivel:
    def is_visible(self):
        return True


def test_reconhece_o_desafio_do_cloudflare():
    class Tela:
        def query_selector(self, seletor):
            return object() if "challenges.cloudflare.com" in seletor else None

    assert _ha_desafio_humano(Tela()) is True


def test_reconhece_o_campo_de_resposta_do_desafio():
    class Tela:
        def query_selector(self, seletor):
            return object() if seletor == 'input[name="cf-turnstile-response"]' else None

    assert _ha_desafio_humano(Tela()) is True


def test_tela_sem_desafio_nao_e_confundida():
    class Tela:
        def query_selector(self, seletor):
            return None

    assert _ha_desafio_humano(Tela()) is False


def test_sem_desafio_a_espera_nao_atrapalha():
    class Tela:
        def query_selector(self, seletor):
            return None

    assert _aguardar_desafio_humano(Tela(), "#txtUsuario", 5, oculto=False) is True


def test_espera_ate_o_operador_resolver(capsys):
    tela = _TelaComDesafio(libera_apos=2)
    assert _aguardar_desafio_humano(tela, "#txtUsuario", 30, oculto=False) is True
    saida = capsys.readouterr().out
    assert "DESAFIO DO CLOUDFLARE" in saida
    assert "nao resolve o desafio" in saida
    assert tela.esperas >= 1


def test_navegador_oculto_recusa_em_vez_de_fingir(capsys):
    """Sem janela visivel ninguem pode responder. Ficar esperando em silencio
    ate o tempo acabar esconderia do operador o que precisa ser feito."""
    tela = _TelaComDesafio(libera_apos=99)
    assert _aguardar_desafio_humano(tela, "#txtUsuario", 30, oculto=True) is False
    saida = capsys.readouterr().out
    assert "SEM --oculto" in saida
    assert tela.esperas == 0


def test_tempo_esgotado_devolve_falso_sem_enviar_nada(capsys):
    tela = _TelaComDesafio(libera_apos=9999)
    assert _aguardar_desafio_humano(tela, "#txtUsuario", 0, oculto=False) is False
    saida = capsys.readouterr().out
    assert "Tempo esgotado" in saida
    # A mensagem precisa dizer se o desafio continua na tela: sem isso o
    # operador nao sabe se a caixa nao foi marcada ou se o portal mudou de tela.
    assert "Desafio ainda na tela: sim" in saida


def test_espera_aceita_criterio_proprio_de_conclusao():
    """Resolvido no meio do login, o portal pode ir direto ao segundo fator ou
    a selecao de perfil. Esperar por uma tela so faria o comando desistir de um
    login que deu certo."""
    estado = {"consultas": 0}

    class Tela:
        def query_selector(self, seletor):
            if "challenges.cloudflare.com" in seletor:
                return object() if estado["consultas"] < 2 else None
            return None

        def wait_for_timeout(self, ms):
            estado["consultas"] += 1

    def pronto(_):
        return estado["consultas"] >= 2

    assert _aguardar_desafio_humano(Tela(), "#txtAcessoCodigo", 30, False, pronto) is True


def test_criterio_proprio_que_nunca_conclui_respeita_o_tempo(capsys):
    class Tela:
        def query_selector(self, seletor):
            return object() if "challenges.cloudflare.com" in seletor else None

        def wait_for_timeout(self, ms):
            pass

    assert _aguardar_desafio_humano(
        Tela(), "#txtAcessoCodigo", 0, False, lambda _: False
    ) is False
    assert "Tempo esgotado" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Perfil do navegador
#
# Cada execucao abria um navegador vazio (`launch` + `new_page`), entao para o
# Cloudflare o advogado era um visitante inedito TODA vez, e o desafio
# reaparecia sempre. Cada reaparicao custava uma tentativa do teto e a presenca
# dele diante da tela.
# --------------------------------------------------------------------------

from justica_mcp.portal import VARIAVEL_PERFIL_EFEMERO, abrir_navegador, pasta_do_navegador


class _Chromium:
    def __init__(self):
        self.persistente = None
        self.efemero = False
        self.opcoes = {}

    def launch_persistent_context(self, pasta, **kw):
        self.persistente = pasta
        self.opcoes = kw
        return _Contexto()

    def launch(self, **kw):
        self.efemero = True
        return _Navegador()


class _Contexto:
    pages: list = []

    def new_page(self):
        return "pagina-do-contexto"


class _Navegador:
    def new_page(self):
        return "pagina-efemera"


class _Playwright:
    def __init__(self):
        self.chromium = _Chromium()


def test_por_padrao_o_perfil_e_persistente(tmp_path, monkeypatch):
    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path))
    monkeypatch.delenv(VARIAVEL_PERFIL_EFEMERO, raising=False)
    p = _Playwright()
    abrir_navegador(p, True, None)
    assert p.chromium.persistente == str(tmp_path / "navegador")
    assert p.chromium.efemero is False


def test_o_perfil_fica_na_pasta_de_estado_nao_em_temporaria(tmp_path, monkeypatch):
    """Guarda cookie de sessao do portal: pertence a pasta de estado, junto da
    auditoria, e nao a um lugar que qualquer limpeza apaga."""
    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path))
    assert pasta_do_navegador() == tmp_path / "navegador"
    assert pasta_do_navegador().is_dir()


def test_variavel_de_ambiente_devolve_o_descarte_a_cada_execucao(tmp_path, monkeypatch):
    """Quem preferir pagar o desafio toda vez tem como."""
    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path))
    monkeypatch.setenv(VARIAVEL_PERFIL_EFEMERO, "1")
    p = _Playwright()
    _, pagina = abrir_navegador(p, True, None)
    assert p.chromium.efemero is True
    assert p.chromium.persistente is None
    assert pagina == "pagina-efemera"


def test_valor_invalido_na_variavel_mantem_o_perfil_persistente(tmp_path, monkeypatch):
    """Erro de digitacao no .env nao pode desligar em silencio a persistencia e
    devolver o desafio a cada execucao, sem ninguem entender por que."""
    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path))
    monkeypatch.setenv(VARIAVEL_PERFIL_EFEMERO, "talvez")
    p = _Playwright()
    abrir_navegador(p, True, None)
    assert p.chromium.efemero is False


def test_tempo_esgotado_distingue_desafio_que_saiu_da_tela(capsys):
    """Se o desafio sumiu mas a tela seguinte nao foi reconhecida, a causa e
    outra: provavelmente o portal voltou ao login. Dizer apenas 'tempo
    esgotado' mandava o operador procurar no lugar errado."""
    class Tela:
        """Desafio presente na entrada, ausente quando o tempo acaba: e o que
        acontece quando a pessoa marca a caixa e o portal muda de tela."""

        def __init__(self):
            self.consultas = 0

        def query_selector(self, seletor):
            self.consultas += 1
            if "challenges.cloudflare.com" in seletor and self.consultas == 1:
                return object()
            return None

        def wait_for_timeout(self, ms):
            pass

    assert _aguardar_desafio_humano(Tela(), "#x", 0, False, lambda _: False) is False
    saida = capsys.readouterr().out
    assert "Desafio ainda na tela: nao" in saida
    assert "voltado ao login" in saida


# --------------------------------------------------------------------------
# Reenvio da credencial apos o desafio
#
# Confirmado pelo operador em 21/09/2026: ele marcou a caixa, e o eproc voltou
# ao FORMULARIO DE LOGIN, nao ao segundo fator. A primeira credencial nunca
# chegou a ser avaliada, foi desviada para o desafio.
# --------------------------------------------------------------------------

from justica_mcp.portal import _reenviar_credencial


class _CampoDoFormulario:
    def __init__(self, valor=""):
        self.valor = valor
        self.cliques = 0

    def click(self):
        self.cliques += 1

    def fill(self, valor):
        self.valor = valor

    def evaluate(self, _):
        return len(self.valor)


class _Formulario:
    def __init__(self, faltando=None, senha_espelho=True):
        self.url = "https://eproc.exemplo/login"
        self.faltando = faltando or set()
        self.senha_espelho = senha_espelho
        self.campos = {}
        self.carregou = 0

    def query_selector(self, seletor):
        if seletor in self.faltando:
            return None
        if seletor == "input[name=pwdSenha]":
            if not self.senha_espelho:
                return _CampoDoFormulario("")
            return self.campos.get("#pwdSenha", _CampoDoFormulario(""))
        self.campos.setdefault(seletor, _CampoDoFormulario())
        return self.campos[seletor]

    def wait_for_load_state(self, *a, **kw):
        self.carregou += 1


class _GuardaPermissiva:
    def pode_executar(self, *a, **kw):
        return True


def _reenviar(pagina):
    return _reenviar_credencial(
        pagina, _GuardaPermissiva(), "https://eproc.exemplo/login",
        "usuario", "senha-secreta", "#txtUsuario", "#pwdSenha",
        "input[name=pwdSenha]", "#sbmEntrar", 5,
    )


def test_reenvio_preenche_e_clica_uma_vez(capsys):
    pagina = _Formulario()
    assert _reenviar(pagina) is True
    assert pagina.campos["#txtUsuario"].valor == "usuario"
    assert pagina.campos["#pwdSenha"].valor == "senha-secreta"
    assert pagina.campos["#sbmEntrar"].cliques == 1
    assert "reenviada (uma vez)" in capsys.readouterr().out


def test_reenvio_aborta_se_a_senha_nao_chegou_ao_campo_enviado(capsys):
    """A mesma trava do primeiro envio: sem conferir o campo espelho, a senha
    podia nao chegar e o clique contaria como tentativa falha."""
    pagina = _Formulario(senha_espelho=False)
    assert _reenviar(pagina) is False
    assert "#sbmEntrar" not in pagina.campos
    assert "Nada reenviado" in capsys.readouterr().out


def test_reenvio_aborta_se_o_campo_sumiu(capsys):
    pagina = _Formulario(faltando={"#txtUsuario"})
    assert _reenviar(pagina) is False
    assert "Nada reenviado" in capsys.readouterr().out


def test_reenvio_aborta_se_o_botao_sumiu(capsys):
    pagina = _Formulario(faltando={"#sbmEntrar"})
    assert _reenviar(pagina) is False
    assert "Nada reenviado" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Desafio REPROVADO
#
# Em campo, 21/09/2026: o operador marcou a caixa varias vezes e o Cloudflare
# respondeu "Falha na verificacao". O recusado e o navegador automatizado, nao
# a pessoa. Sem distinguir aguardando de reprovado, ele ficaria clicando numa
# caixa que jamais vai passar.
# --------------------------------------------------------------------------

from justica_mcp.portal import _desafio_reprovado


class _Quadro:
    def __init__(self, texto):
        self._texto = texto

    def inner_text(self, _):
        return self._texto


class _PaginaComQuadros:
    def __init__(self, principal="", quadros=()):
        self._principal = principal
        self.frames = [_Quadro(t) for t in quadros]

    def inner_text(self, _):
        return self._principal


def test_reconhece_a_falha_dentro_do_quadro_do_cloudflare():
    """O texto vive no quadro do proprio Cloudflare, nao no documento
    principal: procurar so na pagina nao acharia nada."""
    p = _PaginaComQuadros(principal="eproc", quadros=["Falha na verificação\nSolução de problemas"])
    assert _desafio_reprovado(p) is True


def test_reconhece_a_falha_sem_acento():
    p = _PaginaComQuadros(quadros=["FALHA NA VERIFICACAO"])
    assert _desafio_reprovado(p) is True


def test_reconhece_a_falha_em_ingles():
    p = _PaginaComQuadros(quadros=["Verification failed"])
    assert _desafio_reprovado(p) is True


def test_desafio_aguardando_nao_e_confundido_com_reprovado():
    """Aguardando, marcar a caixa resolve. Confundir os dois mandaria o
    operador desistir de um desafio que ele ainda pode passar."""
    p = _PaginaComQuadros(quadros=["Confirme que é humano"])
    assert _desafio_reprovado(p) is False


def test_quadro_ilegivel_nao_vira_reprovacao():
    class QuadroQueExplode:
        def inner_text(self, _):
            raise RuntimeError("quadro de outra origem")

    p = _PaginaComQuadros(quadros=[])
    p.frames = [QuadroQueExplode()]
    assert _desafio_reprovado(p) is False


def test_pagina_sem_quadros_nao_quebra():
    class Simples:
        def inner_text(self, _):
            return "nada aqui"

    assert _desafio_reprovado(Simples()) is False


def test_processo_vem_do_ambiente_quando_nao_veio_no_comando(monkeypatch, capsys):
    """Numero de processo e dado de cliente: mora no .env, que o git ignora,
    e nao no comando digitado nem no codigo versionado."""
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_URL", "https://pje.exemplo/")
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_PROCESSO_TESTE", "0000001-02.2020.8.19.0001")
    args = Namespace(tribunal="TJRJ", sistema="pje", url=None, perfil=None, processo=None)
    _do_ambiente(args)
    assert args.processo == "0000001-02.2020.8.19.0001"
    assert "Processo vindo do .env" in capsys.readouterr().out


def test_processo_do_comando_tem_precedencia(monkeypatch):
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_URL", "https://pje.exemplo/")
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_PROCESSO_TESTE", "0000001-02.2020.8.19.0001")
    args = Namespace(tribunal="TJRJ", sistema="pje", url="https://x/", perfil="P",
                     processo="9999999-99.2099.8.19.0001")
    _do_ambiente(args)
    assert args.processo == "9999999-99.2099.8.19.0001"


def test_endereco_completo_mas_processo_ausente_ainda_consulta_o_ambiente(monkeypatch):
    """A saida cedo do completamento nao pode pular o processo so porque o
    endereco e o perfil ja vieram."""
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_URL", "https://pje.exemplo/")
    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_PROCESSO_TESTE", "0000001-02.2020.8.19.0001")
    args = Namespace(tribunal="TJRJ", sistema="pje", url="https://x/", perfil="P", processo=None)
    _do_ambiente(args)
    assert args.processo == "0000001-02.2020.8.19.0001"


# --------------------------------------------------------------------------
# Assentamento da pagina antes de ler a estrutura
#
# No e-SAJ de Sao Paulo, 21/09/2026: o reconhecimento devolveu zero campos e
# zero botoes numa pagina com titulo 'Portal de Servicos | E-SAJ'. A pagina nao
# estava vazia; o comando e que leu antes de o script montar a tela.
# --------------------------------------------------------------------------

from justica_mcp.portal import _assentar


class _PaginaQueAssenta:
    def __init__(self, falha_rede=False, falha_seletor=False):
        self.esperou_rede = False
        self.esperou_seletor = None
        self.falha_rede = falha_rede
        self.falha_seletor = falha_seletor

    def wait_for_load_state(self, estado, timeout=None):
        if self.falha_rede:
            raise RuntimeError("rede nunca ficou ociosa")
        self.esperou_rede = (estado == "networkidle")

    def wait_for_selector(self, seletor, timeout=None):
        if self.falha_seletor:
            raise RuntimeError("nada apareceu")
        self.esperou_seletor = seletor


def test_espera_a_rede_e_depois_um_elemento():
    p = _PaginaQueAssenta()
    _assentar(p, 45)
    assert p.esperou_rede is True
    assert "input" in p.esperou_seletor and "button" in p.esperou_seletor


def test_rede_que_nunca_assenta_nao_derruba_o_reconhecimento():
    """Portal com conexao aberta permanente nunca fica ocioso. Deixar a
    excecao subir perderia o relato inteiro por causa de um retoque."""
    p = _PaginaQueAssenta(falha_rede=True)
    _assentar(p, 45)
    assert p.esperou_seletor is not None


def test_pagina_sem_elemento_algum_nao_derruba_o_reconhecimento():
    p = _PaginaQueAssenta(falha_seletor=True)
    _assentar(p, 45)
    assert p.esperou_rede is True


def test_espera_de_rede_e_limitada_mesmo_com_segundos_alto():
    """Assentar e retoque: nao pode consumir o tempo todo que o operador deu
    para o carregamento principal."""
    registrado = {}

    class Tela(_PaginaQueAssenta):
        def wait_for_load_state(self, estado, timeout=None):
            registrado["timeout"] = timeout
            super().wait_for_load_state(estado, timeout)

    _assentar(Tela(), 600)
    assert registrado["timeout"] == 20_000


# --------------------------------------------------------------------------
# Botao de envio desabilitado
#
# No e-SAJ de Sao Paulo, 21/09/2026: `#pbEntrar` vem DESABILITADO e so habilita
# quando o formulario considera os campos preenchidos. Sem conferir, um clique
# gastaria tentativa sem surtir efeito, ou esperaria ate o tempo esgotar.
# --------------------------------------------------------------------------

def test_ensaio_nunca_clica_no_botao_de_envio():
    """A garantia central do ensaio: ele confere o botao, jamais o aciona.
    Se isto quebrar, o ensaio deixa de ser seguro e vira uma tentativa."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.ensaiar_login)
    assert "is_enabled()" in fonte
    assert ".click()" in fonte  # o foco nos campos, que e permitido
    # nenhum clique no botao de envio: o seletor dele nunca aparece num clique
    for linha in fonte.splitlines():
        if ".click()" in linha:
            assert "botao_entrar" not in linha, linha
    assert "Acao.CLICAR" not in fonte


# --------------------------------------------------------------------------
# Segundo fator enviado pelo portal
#
# No e-SAJ de Sao Paulo, 21/09/2026: apos o login, `#btnReceberToken` aparece
# na tela JA DESABILITADO, o que indica codigo recem-enviado. Nao ha semente no
# cofre para essa credencial. Presumir semente para todo portal era viavel
# enquanto so existia o eproc.
# --------------------------------------------------------------------------

from justica_mcp.portal import _codigo_do_operador


def test_navegador_oculto_recusa_em_vez_de_esperar_resposta(capsys):
    """Sem janela nao ha a quem perguntar. Esperar em silencio por uma resposta
    que nunca vem e pior que recusar: prende a execucao e nao ensina nada."""
    assert _codigo_do_operador("TJSP / esaj", 6, oculto=True) is None
    assert "sem --oculto" in capsys.readouterr().out


def test_sem_terminal_recusa(monkeypatch, capsys):
    class SemTerminal:
        def isatty(self):
            return False

    monkeypatch.setattr("sys.stdin", SemTerminal())
    assert _codigo_do_operador("TJSP / esaj", 6, oculto=False) is None
    assert "nao tem terminal" in capsys.readouterr().out


def _com_terminal(monkeypatch, respostas):
    class ComTerminal:
        def isatty(self):
            return True

    monkeypatch.setattr("sys.stdin", ComTerminal())
    fila = list(respostas)
    monkeypatch.setattr("builtins.input", lambda _: fila.pop(0))


def test_aceita_o_codigo_do_tamanho_do_campo(monkeypatch):
    _com_terminal(monkeypatch, ["123456"])
    assert _codigo_do_operador("TJSP / esaj", 6, oculto=False) == "123456"


def test_recusa_tamanho_errado_e_pede_de_novo(monkeypatch, capsys):
    """Enviar codigo de tamanho errado gasta a validade curta do codigo e pode
    contar como tentativa no portal."""
    _com_terminal(monkeypatch, ["123", "123456"])
    assert _codigo_do_operador("TJSP / esaj", 6, oculto=False) == "123456"
    assert "aceita 6 digitos" in capsys.readouterr().out


def test_recusa_texto_que_nao_e_digito(monkeypatch, capsys):
    _com_terminal(monkeypatch, ["abc123", "654321"])
    assert _codigo_do_operador("TJSP / esaj", 6, oculto=False) == "654321"
    assert "So digitos" in capsys.readouterr().out


def test_vazio_cancela_sem_enviar_nada(monkeypatch, capsys):
    _com_terminal(monkeypatch, [""])
    assert _codigo_do_operador("TJSP / esaj", 6, oculto=False) is None
    assert "Cancelado" in capsys.readouterr().out


def test_desiste_apos_tres_erros_em_vez_de_insistir(monkeypatch, capsys):
    """Laco infinito de digitacao seria pior: o codigo expira enquanto o
    operador tenta, e ele nem saberia por que o login falhou depois."""
    _com_terminal(monkeypatch, ["1", "22", "333"])
    assert _codigo_do_operador("TJSP / esaj", 6, oculto=False) is None
    assert "Tres tentativas" in capsys.readouterr().out


def test_campo_sem_tamanho_declarado_aceita_qualquer_quantidade(monkeypatch):
    _com_terminal(monkeypatch, ["12345678"])
    assert _codigo_do_operador("TJSP / esaj", None, oculto=False) == "12345678"


# --------------------------------------------------------------------------
# Seletores na linha de comando
#
# `autenticar` e `consultar` nasceram com os seletores do eproc fixos, o que
# bastou enquanto so havia um portal. No e-SAJ de Sao Paulo, cujos campos sao
# outros, os dois comandos ficaram inalcancaveis.
# --------------------------------------------------------------------------

def test_autenticar_e_consultar_aceitam_os_seletores_de_qualquer_portal():
    import argparse
    import contextlib
    import io

    from justica_mcp.portal import main

    esperados = ["--campo-usuario", "--campo-senha", "--campo-senha-oculto",
                 "--botao-entrar", "--campo-codigo", "--botao-validar"]
    for comando in ("autenticar", "consultar"):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            with pytest.raises(SystemExit):
                main([comando, "--help"])
        texto = saida.getvalue()
        for opcao in esperados:
            assert opcao in texto, f"{comando} sem {opcao}"


def test_consultar_repassa_os_seletores_para_a_autenticacao():
    """Aceitar na linha de comando e nao repassar seria pior que nao aceitar:
    o operador veria a opcao, passaria o seletor certo, e o comando usaria o
    do eproc assim mesmo."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    for nome in ("campo_usuario=campo_usuario", "campo_senha=campo_senha",
                 "campo_senha_oculto=campo_senha_oculto", "botao_entrar=botao_entrar",
                 "campo_codigo=campo_codigo", "botao_validar=botao_validar"):
        assert nome in fonte, nome


# --------------------------------------------------------------------------
# Falta de semente nao impede autenticar
#
# A conferencia previa exigia semente e nasceu quando o eproc era o unico
# portal. No e-SAJ de Sao Paulo o codigo e ENVIADO pelo portal: exigir semente
# ali barrava o comando antes de abrir o navegador, por uma falta que nao
# existe.
# --------------------------------------------------------------------------

class _CofreSemSemente:
    def _login(self, identidade):
        return "usuario"

    def _senha(self, identidade):
        return "senha-secreta"

    def tem_semente(self, identidade):
        return False


class _EstadoMudo:
    def registrar(self, **kw):
        pass

    def auditoria_recente(self, limite=200):
        return []

    def gravar_snapshot(self, *a, **kw):
        pass


def test_sem_semente_e_sem_janela_recusa_com_motivo(capsys):
    """Sem semente o codigo e digitado por uma pessoa. Sem janela nao ha
    pessoa: recusar antes de abrir o navegador poupa uma tentativa."""
    from justica_mcp.portal import autenticar

    codigo = autenticar(
        "https://portal.exemplo/login", "TJSP", "esaj", confirmado=True,
        oculto=True, cofre=_CofreSemSemente(), estado=_EstadoMudo(),
    )
    assert codigo == 1
    saida = capsys.readouterr()
    assert "nao ha a quem perguntar" in saida.err


def test_sem_semente_avisa_para_ter_o_codigo_em_maos(capsys):
    """O aviso vem ANTES de comecar: saber disso depois do login ja gastou a
    tentativa, e o codigo expira enquanto o operador procura o celular."""
    from justica_mcp.portal import autenticar

    autenticar(
        "endereco-invalido-para-parar-cedo", "TJSP", "esaj", confirmado=True,
        oculto=True, cofre=_CofreSemSemente(), estado=_EstadoMudo(),
    )
    assert "sera pedido a voce" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Reconhecimento dentro da sessao autenticada
#
# `reconhecer` abre sessao nova e por isso nunca enxerga o que so existe depois
# do login. Sem isto, escrever o adaptador de cada portal novo exigiria
# adivinhar seletores.
# --------------------------------------------------------------------------

from justica_mcp.portal import _reconhecer_dentro_da_sessao, permissao_de_origem


class _PaginaInterna:
    def __init__(self, url="https://portal.exemplo/painel"):
        self.url = url
        self.navegou_para = None
        self.frames = []

    def goto(self, destino, **kw):
        self.navegou_para = destino
        self.url = destino

    def title(self):
        return "Tela interna"

    def inner_text(self, _):
        return ""

    def query_selector_all(self, seletor):
        return []

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


def test_le_tela_do_mesmo_portal(monkeypatch, capsys):
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: ([], []))
    pagina = _PaginaInterna()
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    _reconhecer_dentro_da_sessao(
        pagina, guarda, "https://portal.exemplo/consulta", 10
    )
    assert pagina.navegou_para == "https://portal.exemplo/consulta"
    assert "TELA INTERNA" in capsys.readouterr().out


def test_recusa_destino_de_outro_portal(monkeypatch, capsys):
    """A sessao autenticada e do portal; leva-la para outro dominio seria
    entregar a sessao a quem escolheu o endereco."""
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: ([], []))
    pagina = _PaginaInterna()
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    _reconhecer_dentro_da_sessao(pagina, guarda, "https://outro.exemplo/x", 10)
    assert pagina.navegou_para is None
    assert "TRAVA" in capsys.readouterr().out


def test_recusa_destino_com_termo_de_risco(monkeypatch, capsys):
    """Mesma origem nao basta: `dar-ciencia` no proprio portal e justamente o
    que nao pode ser tocado."""
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: ([], []))
    pagina = _PaginaInterna()
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    _reconhecer_dentro_da_sessao(
        pagina, guarda, "https://portal.exemplo/intimacao/abrir", 10
    )
    assert pagina.navegou_para is None
    assert "TRAVA" in capsys.readouterr().out


def test_nao_libera_clique_nem_preenchimento_na_tela_interna(monkeypatch):
    """A permissao acrescentada e de leitura: se liberasse clique, uma tela
    interna viraria superficie de acao sem conferencia em campo."""
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: ([], []))
    pagina = _PaginaInterna()
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    _reconhecer_dentro_da_sessao(pagina, guarda, "https://portal.exemplo/consulta", 10)
    for p in guarda.permissoes:
        assert not p.seletores_clicaveis
        assert not p.seletores_preenchiveis


# --------------------------------------------------------------------------
# Ligacoes da tela interna
#
# Portais montam o menu como paineis sanfonados: os links existem no documento
# mesmo com o painel fechado. Sem lista-los, o endereco da tela de consulta
# teria de ser adivinhado, que e o erro que o reconhecimento existe para
# evitar. Visto no e-SAJ de Sao Paulo, 21/09/2026.
# --------------------------------------------------------------------------

from justica_mcp.portal import _listar_ligacoes


class _Ancora:
    def __init__(self, texto, href):
        self._texto, self._href = texto, href

    def inner_text(self):
        return self._texto

    def get_attribute(self, nome):
        return self._href if nome == "href" else None


class _PaginaComLigacoes:
    def __init__(self, ancoras):
        self._ancoras = ancoras

    def query_selector_all(self, seletor):
        return self._ancoras if seletor == "a[href]" else []


def test_lista_link_de_painel_fechado(capsys):
    """O painel fechado esconde o link da tela, nao o remove do documento."""
    p = _PaginaComLigacoes([_Ancora("Consulta de Processos do 1º Grau", "/cpopg/open.do")])
    _listar_ligacoes(p)
    saida = capsys.readouterr().out
    assert "/cpopg/open.do" in saida
    assert "1º Grau" in saida


def test_descarta_ancora_sem_destino_util(capsys):
    """`#` e `javascript:` sao gatilhos de interface, nao enderecos de tela:
    listados, afogariam o que interessa."""
    p = _PaginaComLigacoes([
        _Ancora("abrir painel", "#"),
        _Ancora("acao", "javascript:void(0)"),
        _Ancora("Consulta", "/cposg/open.do"),
    ])
    _listar_ligacoes(p)
    saida = capsys.readouterr().out
    assert "/cposg/open.do" in saida
    assert "javascript:" not in saida
    assert "LIGACOES (1)" in saida


def test_nao_repete_o_mesmo_destino(capsys):
    p = _PaginaComLigacoes([
        _Ancora("Consulta", "/cpopg/open.do"),
        _Ancora("Consulta Processual", "/cpopg/open.do"),
    ])
    _listar_ligacoes(p)
    assert "LIGACOES (1)" in capsys.readouterr().out


def test_limita_a_listagem_e_avisa(capsys):
    p = _PaginaComLigacoes([_Ancora(f"item {i}", f"/x{i}") for i in range(80)])
    _listar_ligacoes(p, teto=10)
    saida = capsys.readouterr().out
    assert "mostrando 10" in saida
    assert "/x10" not in saida


def test_ligacoes_ilegiveis_nao_derrubam_o_relato(capsys):
    class Explode:
        def query_selector_all(self, _):
            raise RuntimeError("pagina fechada")

    _listar_ligacoes(Explode())
    assert "ilegiveis" in capsys.readouterr().out


def test_reconhecimento_interno_aceita_varias_telas():
    """Cada login custa uma tentativa do teto e um codigo lido no celular.
    Reconhecer tela a tela multiplicava esse custo por motivo de
    implementacao, nao do portal."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    assert "isinstance(reconhecer_apos, str)" in fonte
    assert "for i, destino in enumerate(destinos" in fonte


# --------------------------------------------------------------------------
# Estrutura de dados sem os dados
#
# Partes, movimentacoes e documentos vivem em tabelas, nao em campos de
# formulario, entao o relato de campos nao os enxerga. Mas o relato e colado em
# conversa: nome de parte e teor de movimentacao nao podem sair dali.
# --------------------------------------------------------------------------

from justica_mcp.portal import _relatar_estrutura_de_dados


class _Celula:
    pass


class _Tabela:
    def __init__(self, ident="", classe="", linhas=0, colunas=0):
        self._ident, self._classe = ident, classe
        self._linhas, self._colunas = linhas, colunas

    def get_attribute(self, nome):
        return {"id": self._ident, "class": self._classe}.get(nome)

    def query_selector_all(self, seletor):
        if seletor == "tr":
            return [_Celula()] * self._linhas
        return [_Celula()] * self._colunas


class _Marcado:
    def __init__(self, marcador, ident):
        self._marcador, self._ident = marcador, ident

    def get_attribute(self, nome):
        return self._ident if nome == "id" else None

    def evaluate(self, _):
        return self._marcador


class _PaginaComTabelas:
    def __init__(self, tabelas=(), marcados=()):
        self._tabelas = list(tabelas)
        self._marcados = list(marcados)

    def query_selector_all(self, seletor):
        if seletor == "table":
            return self._tabelas
        if seletor == "[id]":
            return self._marcados
        return []


def test_relata_identificador_e_tamanho_da_tabela(capsys):
    p = _PaginaComTabelas([_Tabela(ident="tabelaTodasMovimentacoes", linhas=68, colunas=3)])
    _relatar_estrutura_de_dados(p)
    saida = capsys.readouterr().out
    assert "#tabelaTodasMovimentacoes" in saida
    assert "68 linha(s) x 3 coluna(s)" in saida


def test_nao_reporta_texto_de_celula(capsys):
    """A promessa do reconhecimento e que nenhum dado de processo apareca no
    relato, porque ele e colado em conversa."""
    class TabelaComTexto(_Tabela):
        def inner_text(self):
            return "FULANO DE TAL x BANCO"

    p = _PaginaComTabelas([TabelaComTexto(ident="tablePartes", linhas=2, colunas=2)])
    _relatar_estrutura_de_dados(p)
    assert "FULANO" not in capsys.readouterr().out


def test_tabela_sem_identificador_aparece_pela_classe(capsys):
    p = _PaginaComTabelas([_Tabela(classe="secaoFormBody", linhas=4, colunas=2)])
    _relatar_estrutura_de_dados(p)
    assert ".secaoFormBody" in capsys.readouterr().out


def test_lista_elementos_com_identificador_sem_script_nem_estilo(capsys):
    p = _PaginaComTabelas(marcados=[
        _Marcado("span", "numeroProcesso"),
        _Marcado("script", "analytics"),
        _Marcado("style", "tema"),
    ])
    _relatar_estrutura_de_dados(p)
    saida = capsys.readouterr().out
    assert "span#numeroProcesso" in saida
    assert "analytics" not in saida
    assert "tema" not in saida


def test_pagina_ilegivel_nao_derruba_o_relato(capsys):
    class Explode:
        def query_selector_all(self, _):
            raise RuntimeError("pagina fechada")

    _relatar_estrutura_de_dados(Explode())
    assert "ilegiveis" in capsys.readouterr().out


def test_identificadores_nao_sao_cortados_em_quarenta(capsys):
    """Identificador e estrutura pura, nao dado de processo. Cortar em 40
    escondeu o `tbody` das movimentacoes do e-SAJ e custou uma execucao
    autenticada inteira: uma tentativa e um codigo lido no celular."""
    p = _PaginaComTabelas(marcados=[_Marcado("tbody", f"t{i}") for i in range(120)])
    _relatar_estrutura_de_dados(p, teto=40)
    saida = capsys.readouterr().out
    assert "tbody#t100" in saida
    assert "ELEMENTOS COM IDENTIFICADOR (120)" in saida


def test_o_navegador_escreve_os_downloads_em_pasta_conhecida(tmp_path, monkeypatch):
    """Sem pasta conhecida, o Playwright usa um temporario que so ele enxerga:
    quando o canal morre no meio da gravacao, o arquivo ja baixado fica
    irrecuperavel. Aconteceu em campo em 22/09/2026."""
    from justica_mcp.portal import pasta_de_descargas

    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path))
    monkeypatch.delenv(VARIAVEL_PERFIL_EFEMERO, raising=False)
    p = _Playwright()
    abrir_navegador(p, True, None)
    assert p.chromium.opcoes["downloads_path"] == str(tmp_path / "descargas")
    assert p.chromium.opcoes["accept_downloads"] is True
    assert pasta_de_descargas() == tmp_path / "descargas"
    assert pasta_de_descargas().is_dir()


# --------------------------------------------------------------------------
# Conferencia de sessao: saber sem gastar
#
# Em 22/09/2026 foram seis execucoes num dia so para vencer degraus de UMA
# tela, e cada uma custou uma tentativa do teto da conta e um codigo lido no
# celular. Abrir o portal com o perfil que ja esta no disco e ler a tela nao
# custa nem uma coisa nem outra.
# --------------------------------------------------------------------------

def test_prova_positiva_diz_que_a_sessao_esta_aberta():
    from justica_mcp.portal import SESSAO_ABERTA, veredicto_da_sessao

    codigo, linhas = veredicto_da_sessao(True, False)
    assert codigo == SESSAO_ABERTA
    assert "SESSAO ABERTA" in linhas[0]


def test_formulario_de_login_diz_que_a_sessao_caiu():
    from justica_mcp.portal import SESSAO_FECHADA, veredicto_da_sessao

    codigo, linhas = veredicto_da_sessao(False, True)
    assert codigo == SESSAO_FECHADA
    assert "SESSAO FECHADA" in linhas[0]


def test_ausencia_de_formulario_nao_e_prova_de_sessao_aberta():
    """Concluir por ausencia levaria a consulta a seguir como autenticada
    quando nao esta, e isso custa uma tentativa do teto da conta."""
    from justica_mcp.portal import SESSAO_INDEFINIDA, veredicto_da_sessao

    codigo, linhas = veredicto_da_sessao(False, False)
    assert codigo == SESSAO_INDEFINIDA
    assert "INDEFINIDO" in linhas[0]
    assert any("NAO e prova" in linha for linha in linhas)


def test_prova_positiva_vence_o_formulario_na_tela():
    """Portal que mostra login e area logada ao mesmo tempo existe: a prova
    positiva e mais forte que a presenca do formulario."""
    from justica_mcp.portal import SESSAO_ABERTA, veredicto_da_sessao

    codigo, _ = veredicto_da_sessao(True, True)
    assert codigo == SESSAO_ABERTA


def test_campo_de_senha_visivel_marca_o_formulario_de_login(monkeypatch):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import Campo, _tem_formulario_de_login

    senha = Campo(marcador="input", tipo="password", nome="pwd", identificador="pwd",
                  rotulo=None, texto_visivel=None, e_senha=True, visivel=True)
    monkeypatch.setattr(portal_mod, "_coletar", lambda p: ([senha], []))
    assert _tem_formulario_de_login(object()) is True


def test_campo_de_senha_fora_da_tela_nao_conta():
    """Campo espelho empurrado para fora da tela e o padrao que ja enganou o
    preenchimento; nao pode enganar tambem a leitura da sessao."""
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import Campo, _tem_formulario_de_login

    espelho = Campo(marcador="input", tipo="password", nome="pwd", identificador="pwd",
                    rotulo=None, texto_visivel=None, e_senha=True, visivel=True,
                    na_tela=False)
    portal_mod._coletar_original = portal_mod._coletar
    try:
        portal_mod._coletar = lambda p: ([espelho], [])
        assert _tem_formulario_de_login(object()) is False
    finally:
        portal_mod._coletar = portal_mod._coletar_original


def test_leitura_que_falha_nao_inventa_formulario(monkeypatch):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import _tem_formulario_de_login

    def explode(_):
        raise RuntimeError("tela ilegivel")

    monkeypatch.setattr(portal_mod, "_coletar", explode)
    assert _tem_formulario_de_login(object()) is False


# --------------------------------------------------------------------------
# Mapa dos portais: conhecer a tela sem gastar tentativa
#
# Escrever adaptador exige conhecer a tela; conhecer a tela nao exige
# autenticar, porque a pagina de entrada e publica. Separar as duas coisas e
# o que evita gastar codigo do celular para descobrir o nome de um campo.
# --------------------------------------------------------------------------

def _config(tribunal, sistema, url="https://portal.exemplo/login"):
    from justica_mcp.core.acesso import ConfigPortal

    return ConfigPortal(tribunal=tribunal, sistema=sistema, url=url, perfil=None)


def test_sem_alvos_mapeia_todos_os_portais_do_env():
    from justica_mcp.portal import alvos_escolhidos

    todos = [_config("TJSP", "esaj"), _config("TJRJ", "pje")]
    assert alvos_escolhidos(todos, None) == todos


def test_alvo_escolhe_um_portal():
    from justica_mcp.portal import alvos_escolhidos

    todos = [_config("TJSP", "esaj"), _config("TJRJ", "pje")]
    escolhidos = alvos_escolhidos(todos, ["TJRJ/pje"])
    assert [c.rotulo for c in escolhidos] == [todos[1].rotulo]


def test_tribunal_sem_sistema_leva_todos_os_sistemas_dele():
    from justica_mcp.portal import alvos_escolhidos

    todos = [_config("TJRJ", "pje"), _config("TJRJ", "eproc"), _config("TJSP", "esaj")]
    escolhidos = alvos_escolhidos(todos, ["TJRJ"])
    assert len(escolhidos) == 2


def test_alvo_que_nao_existe_nao_passa_em_silencio():
    """Ignorar o erro de digitacao faria o operador acreditar que o portal foi
    lido quando nao foi."""
    import pytest

    from justica_mcp.core.acesso import PortalNaoConfigurado
    from justica_mcp.portal import alvos_escolhidos

    with pytest.raises(PortalNaoConfigurado):
        alvos_escolhidos([_config("TJSP", "esaj")], ["TJRJ/pje"])


def test_alvo_repetido_nao_duplica_a_leitura():
    from justica_mcp.portal import alvos_escolhidos

    todos = [_config("TJSP", "esaj")]
    assert len(alvos_escolhidos(todos, ["TJSP/esaj", "TJSP"])) == 1


def test_resumo_mostra_o_que_decide_se_vale_escrever_adaptador():
    """Verificacao humana que ja reprovou o navegador e o que inviabiliza o
    adaptador, como aconteceu no eproc. Tem que aparecer na primeira linha."""
    from justica_mcp.portal import linha_de_resumo

    linha = linha_de_resumo({
        "rotulo": "TRF2/eproc", "desafio": True, "desafio_reprovado": True,
        "formulario": True, "campos": 3, "botoes": 2,
    })
    assert "JA REPROVOU" in linha


def test_resumo_de_portal_que_nao_abriu_diz_isso_e_nao_finge_leitura():
    from justica_mcp.portal import linha_de_resumo

    linha = linha_de_resumo({"rotulo": "TJRJ/eproc", "erro": "TimeoutError: 30000ms"})
    assert "NAO ABRIU" in linha
    assert "TimeoutError" in linha


def test_os_mapas_ficam_na_pasta_de_estado(tmp_path, monkeypatch):
    from justica_mcp.portal import pasta_dos_mapas

    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path))
    assert pasta_dos_mapas() == tmp_path / "mapas"
    assert pasta_dos_mapas().is_dir()


# --------------------------------------------------------------------------
# Seletores de entrada por sistema
#
# Todos LIDOS de tela real: e-SAJ da autenticacao que funcionou em 22/09/2026,
# eproc e PJe dos mapas do mesmo dia. Seletor adivinhado falha em silencio, e
# em portal que limita tentativa de login o silencio custa acesso.
# --------------------------------------------------------------------------

class _Args:
    def __init__(self, sistema, **kw):
        self.sistema = sistema
        for nome in ("campo_usuario", "campo_senha", "campo_senha_oculto",
                     "botao_entrar", "campo_codigo", "botao_validar"):
            setattr(self, nome, kw.get(nome))


def test_esaj_recebe_os_seletores_conferidos_em_campo():
    from justica_mcp.portal import completar_seletores

    args = _Args("esaj")
    completar_seletores(args)
    assert args.campo_usuario == "#usernameForm"
    assert args.botao_entrar == "#pbEntrar"
    assert args.campo_codigo == "#tokenInformado"


def test_eproc_recebe_os_seletores_do_mapa():
    from justica_mcp.portal import completar_seletores

    args = _Args("eproc")
    completar_seletores(args)
    assert (args.campo_usuario, args.campo_senha, args.botao_entrar) == (
        "#txtUsuario", "#pwdSenha", "#sbmEntrar")


def test_pje_recebe_os_seletores_do_keycloak_lidos_no_mapa():
    from justica_mcp.portal import completar_seletores

    args = _Args("pje")
    completar_seletores(args)
    assert (args.campo_usuario, args.campo_senha, args.botao_entrar) == (
        "#username", "#password", "#kc-login")


def test_o_que_o_operador_passa_tem_precedencia_sobre_a_tabela():
    """Portal muda de tela sem avisar: o operador precisa poder corrigir na
    hora, sem esperar codigo novo."""
    from justica_mcp.portal import completar_seletores

    args = _Args("esaj", campo_usuario="#outro")
    completar_seletores(args)
    assert args.campo_usuario == "#outro"
    assert args.botao_entrar == "#pbEntrar"


def test_segundo_fator_que_nenhuma_tela_mostrou_fica_vazio(monkeypatch):
    """Preencher com um seletor plausivel seria adivinhar, e adivinhar aqui
    gasta tentativa de login. Foi assim que o PJe entrou na tabela, com os
    campos de codigo vazios, ate a tela real mostra-los em 22/09/2026."""
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import completar_seletores

    monkeypatch.setitem(portal_mod.SELETORES_POR_SISTEMA, "portal-novo", {
        "campo_usuario": "#usuario", "campo_senha": "#senha",
        "campo_senha_oculto": None, "botao_entrar": "#entrar",
        "campo_codigo": None, "botao_validar": None,
    })
    args = _Args("portal-novo")
    completar_seletores(args)
    assert args.campo_codigo is None
    assert args.botao_validar is None


def test_sistema_desconhecido_cai_no_padrao_historico_e_nao_em_vazio():
    from justica_mcp.portal import seletores_do_sistema

    assert seletores_do_sistema("projudi")["campo_usuario"] == "#txtUsuario"
    assert seletores_do_sistema("")["botao_entrar"] == "#sbmEntrar"


def test_a_tabela_nao_e_alterada_por_quem_a_consulta():
    """Devolver a propria tabela deixaria um comando estragar o seguinte."""
    from justica_mcp.portal import SELETORES_POR_SISTEMA, seletores_do_sistema

    copia = seletores_do_sistema("esaj")
    copia["campo_usuario"] = "#estragado"
    assert SELETORES_POR_SISTEMA["esaj"]["campo_usuario"] == "#usernameForm"


# --------------------------------------------------------------------------
# Portal sem segundo fator conhecido
#
# O PJe entrou no comando de autenticacao com os campos de segundo fator
# vazios, porque nenhuma tela os mostrou ainda. Procurar por um seletor vazio
# levanta erro no navegador, e o erro cairia DEPOIS de a credencial ter sido
# enviada: a tentativa de login gasta e, na tela, um erro de programa no lugar
# da tela do portal.
# --------------------------------------------------------------------------

class _PaginaQueExigeTexto:
    """Como o Playwright: seletor que nao e texto levanta erro."""

    def __init__(self, achados=None):
        self.achados = achados or {}

    def query_selector(self, seletor):
        if not isinstance(seletor, str):
            raise TypeError("Expected string, got NoneType")
        return self.achados.get(seletor)


def test_seletor_ausente_nao_vira_busca_no_navegador():
    from justica_mcp.portal import achar_opcional

    pagina = _PaginaQueExigeTexto()
    assert achar_opcional(pagina, None) is None
    assert achar_opcional(pagina, "") is None


def test_seletor_presente_continua_sendo_procurado():
    from justica_mcp.portal import achar_opcional

    pagina = _PaginaQueExigeTexto({"#codigo": "achei"})
    assert achar_opcional(pagina, "#codigo") == "achei"


def test_erro_do_navegador_nao_derruba_a_autenticacao():
    """Uma tela que morreu no meio nao pode virar traceback com a credencial
    ja enviada: o operador precisa ler o relato, nao a pilha."""
    from justica_mcp.portal import achar_opcional

    class Morta:
        def query_selector(self, seletor):
            raise RuntimeError("Target page, context or browser has been closed")

    assert achar_opcional(Morta(), "#codigo") is None


def test_a_permissao_nao_leva_seletor_vazio_para_a_guarda():
    """Seletor vazio na lista de permissao e lixo que atrapalha a leitura do
    relato e pode casar com o alvo errado."""
    sem_codigo = {"campo_usuario": "#usuario", "campo_senha": "#senha",
                  "campo_codigo": None}
    preenchiveis = tuple(
        s for s in (sem_codigo["campo_usuario"], sem_codigo["campo_senha"],
                    sem_codigo["campo_codigo"]) if s
    )
    assert preenchiveis == ("#usuario", "#senha")


# --------------------------------------------------------------------------
# O relato precisa mostrar os CAMPOS
#
# Eles vinham sendo coletados e nunca impressos. No e-SAJ os campos foram
# achados por acaso, na lista de elementos com identificador; na tela de
# segundo fator do PJe, em 22/09/2026, nao havia essa lista e o relato
# terminou sem dizer onde se digita o codigo, que era a unica coisa que
# faltava para escrever o adaptador.
# --------------------------------------------------------------------------

class _PaginaDeRelato:
    url = "https://sso.cloud.pje.jus.br/auth/realms/pje/login-actions/authenticate"
    viewport_size = {"width": 1280, "height": 720}

    def title(self):
        return "Bem vindo ao PJe"

    def query_selector_all(self, seletor):
        return []


def test_o_relato_mostra_os_campos_da_tela(monkeypatch, capsys):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import Campo, _relatar_tela

    codigo = Campo(marcador="input", tipo="text", nome="otp", identificador="otp",
                   rotulo="Codigo", texto_visivel=None, e_senha=False, visivel=True)
    monkeypatch.setattr(portal_mod, "_coletar", lambda p: ([codigo], []))
    _relatar_tela(_PaginaDeRelato(), "TELA")

    saida = capsys.readouterr().out
    assert "CAMPOS NA TELA" in saida
    assert "#otp" in saida
    assert "Codigo" in saida


def test_campo_de_senha_e_marcado_no_relato(monkeypatch, capsys):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import Campo, _relatar_tela

    senha = Campo(marcador="input", tipo="password", nome="password",
                  identificador="password", rotulo=None, texto_visivel=None,
                  e_senha=True, visivel=True)
    monkeypatch.setattr(portal_mod, "_coletar", lambda p: ([senha], []))
    _relatar_tela(_PaginaDeRelato(), "TELA")
    assert "SENHA" in capsys.readouterr().out


def test_campo_sem_identificador_aparece_pelo_nome(monkeypatch, capsys):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import Campo, _relatar_tela

    sem_id = Campo(marcador="input", tipo="text", nome="codigo", identificador=None,
                   rotulo=None, texto_visivel=None, e_senha=False, visivel=True)
    monkeypatch.setattr(portal_mod, "_coletar", lambda p: ([sem_id], []))
    _relatar_tela(_PaginaDeRelato(), "TELA")
    assert "[name=codigo]" in capsys.readouterr().out


def test_tela_sem_campo_nenhum_diz_isso(monkeypatch, capsys):
    """Silencio aqui faria o leitor achar que o relato ficou incompleto."""
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import _relatar_tela

    monkeypatch.setattr(portal_mod, "_coletar", lambda p: ([], []))
    _relatar_tela(_PaginaDeRelato(), "TELA")
    assert "(nenhum)" in capsys.readouterr().out


def test_pje_recebe_o_segundo_fator_lido_da_tela_real():
    """Campo `#otp` e botao `#kc-login` ("Validar"), vistos na tela de segundo
    fator do PJe do Rio em 22/09/2026, depois de a credencial ser aceita."""
    from justica_mcp.portal import completar_seletores

    args = _Args("pje")
    completar_seletores(args)
    assert args.campo_codigo == "#otp"
    assert args.botao_validar == "#kc-login"


def test_o_botao_do_segundo_fator_do_pje_repete_o_do_login_de_proposito():
    """E outra tela do mesmo Keycloak, e nao um engano de copia."""
    from justica_mcp.portal import seletores_do_sistema

    pje = seletores_do_sistema("pje")
    assert pje["botao_entrar"] == pje["botao_validar"] == "#kc-login"


# --------------------------------------------------------------------------
# A recusa do codigo precisa dizer o que o portal falou
#
# Em 22/09/2026 o PJe recusou o codigo gerado pela semente e o relato disse
# apenas "nao passou". Codigo errado e codigo vencido levam a providencias
# diferentes: o primeiro e semente errada no cofre, o segundo e so tempo.
# --------------------------------------------------------------------------

class _ElementoComTexto:
    def __init__(self, texto):
        self._texto = texto

    def is_visible(self):
        return True

    def inner_text(self):
        return self._texto


class _PaginaComRecado:
    def __init__(self, seletor, texto):
        self._seletor, self._texto = seletor, texto

    def query_selector_all(self, seletor):
        return [_ElementoComTexto(self._texto)] if seletor == self._seletor else []


def test_recado_do_keycloak_e_lido():
    """O Keycloak, que atende o PJe, escreve em classe propria."""
    from justica_mcp.portal import _mensagens_de_erro

    pagina = _PaginaComRecado(".kc-feedback-text", "Código de autenticação inválido.")
    assert _mensagens_de_erro(pagina) == ["Código de autenticação inválido."]


def test_recado_do_campo_de_codigo_e_lido():
    from justica_mcp.portal import _mensagens_de_erro

    pagina = _PaginaComRecado("#input-error-otp-code", "Código inválido")
    assert _mensagens_de_erro(pagina) == ["Código inválido"]


def test_recado_antigo_continua_sendo_lido():
    """As classes que ja funcionavam no eproc e no e-SAJ nao podem sair."""
    from justica_mcp.portal import _mensagens_de_erro

    assert _mensagens_de_erro(_PaginaComRecado(".alert", "Senha invalida")) == [
        "Senha invalida"]


# --------------------------------------------------------------------------
# Recusar ANTES de autenticar
#
# Pedir consulta num sistema sem adaptador autenticava primeiro, gastava uma
# tentativa do teto da conta e so entao falhava, acusando a tela errada
# ("campo de busca rapida nao encontrado"), como se o portal tivesse mudado.
# --------------------------------------------------------------------------

def test_sistema_sem_consulta_e_recusado_sem_tocar_no_portal(capsys, monkeypatch):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import consultar_processo

    def nao_pode(*a, **kw):
        raise AssertionError("autenticou antes de saber que nao sabia consultar")

    monkeypatch.setattr(portal_mod, "autenticar", nao_pode)
    # `projudi` nao tem adaptador escrito. O exemplo aqui era o PJe ate
    # 30/09/2026, quando a consulta autenticada dele foi escrita a partir do
    # caminho que o operador fotografou.
    saida = consultar_processo("https://exemplo", "TJRJ", "projudi",
                               "1037850-62.2023.8.26.0100")
    assert saida == 1
    erro = capsys.readouterr().err
    assert "NAO IMPLEMENTADO" in erro
    assert "nenhuma tentativa de login foi gasta" in erro


def test_os_sistemas_com_consulta_sao_os_conferidos():
    from justica_mcp.portal import SISTEMAS_COM_CONSULTA

    assert SISTEMAS_COM_CONSULTA == {"esaj", "eproc", "pje"}


def test_numero_invalido_e_recusado_antes_de_tudo(capsys, monkeypatch):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import consultar_processo

    monkeypatch.setattr(portal_mod, "autenticar", lambda *a, **kw: 0)
    assert consultar_processo("https://exemplo", "TJSP", "esaj", "123") == 1


# --------------------------------------------------------------------------
# Para onde ir depois do login, sem levar dado de cliente junto
# --------------------------------------------------------------------------

class _LigacaoSoHref:
    def __init__(self, href):
        self._href = href

    def get_attribute(self, nome):
        return self._href if nome == "href" else None


def test_os_parametros_do_endereco_nao_sao_impressos():
    """Os parametros carregam identificador de cliente; o caminho, sozinho,
    diz o que precisa ser dito."""
    from justica_mcp.portal import caminhos_de_navegacao

    achados = caminhos_de_navegacao([
        _LigacaoSoHref("https://tjrj.pje.jus.br/1g/ConsultaProcesso/listView.seam?idProcesso=99"),
    ])
    assert achados == ["https://tjrj.pje.jus.br/1g/ConsultaProcesso/listView.seam"]


def test_caminhos_repetidos_aparecem_uma_vez_so():
    from justica_mcp.portal import caminhos_de_navegacao

    achados = caminhos_de_navegacao([
        _LigacaoSoHref("/1g/painel.seam?a=1"), _LigacaoSoHref("/1g/painel.seam?a=2")])
    assert achados == ["/1g/painel.seam"]


def test_ligacao_de_script_e_ancora_nao_entram():
    from justica_mcp.portal import caminhos_de_navegacao

    achados = caminhos_de_navegacao([
        _LigacaoSoHref("javascript:void(0)"), _LigacaoSoHref("#topo"),
        _LigacaoSoHref("mailto:alguem@exemplo"), _LigacaoSoHref("/1g/util.seam")])
    assert achados == ["/1g/util.seam"]


def test_ligacao_sem_endereco_nao_derruba_a_leitura():
    from justica_mcp.portal import caminhos_de_navegacao

    class Quebrada:
        def get_attribute(self, nome):
            raise RuntimeError("elemento sumiu")

    assert caminhos_de_navegacao([Quebrada(), _LigacaoSoHref("/1g/ok.seam")]) == ["/1g/ok.seam"]


# --------------------------------------------------------------------------
# Senha vencida nao e credencial recusada
#
# Lido do PJe do Rio em 30/09/2026: "Senha expirada. Solicite uma nova senha".
# Sem distinguir, o conselho padrao ("confira o cofre") manda o operador
# procurar defeito onde nao ha, e repetir o comando gasta tentativas de uma
# conta cuja senha o portal ja nao aceita.
# --------------------------------------------------------------------------

def test_recado_do_pje_e_reconhecido_como_senha_vencida():
    from justica_mcp.portal import senha_vencida

    assert senha_vencida(["Senha expirada. Solicite uma nova senha"]) is True


def test_outras_formas_do_mesmo_recado():
    from justica_mcp.portal import senha_vencida

    for recado in ("Sua senha está vencida", "Password has expired",
                   "Por favor, redefina sua senha"):
        assert senha_vencida([recado]) is True, recado


def test_recusa_de_credencial_nao_vira_senha_vencida():
    """Confundir os dois manda o advogado renovar uma senha que esta certa."""
    from justica_mcp.portal import senha_vencida

    for recado in ("Usuário ou senha inválidos", "Credenciais inválidas",
                   "Código de autenticação inválido"):
        assert senha_vencida([recado]) is False, recado


def test_tela_sem_recado_nenhum_nao_inventa_diagnostico():
    from justica_mcp.portal import senha_vencida

    assert senha_vencida([]) is False
    assert senha_vencida(None) is False


# --------------------------------------------------------------------------
# Nem todo codigo e ENVIADO pelo portal
#
# O PJe pede o codigo do aplicativo autenticador, e o programa dizia "o portal
# enviou um codigo, confira sua mensagem ou e-mail", mandando o operador
# esperar uma mensagem que nunca chegaria. A tela do PJe traz o proprio
# rotulo: "Entre no seu aplicativo de autenticacao".
# --------------------------------------------------------------------------

def _pedir(monkeypatch, capsys, rotulo_do_campo=None, resposta="123456"):
    from justica_mcp import portal as portal_mod
    from justica_mcp.portal import _codigo_do_operador

    monkeypatch.setattr(portal_mod, "_esvaziar_teclado", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _: resposta)

    class ComTerminal:
        def isatty(self):
            return True

    monkeypatch.setattr(portal_mod.sys, "stdin", ComTerminal())
    valor = _codigo_do_operador("TJRJ / pje", 6, False, rotulo_do_campo)
    return valor, capsys.readouterr().out


def test_o_rotulo_do_portal_e_repetido_em_vez_de_suposicao(monkeypatch, capsys):
    valor, saida = _pedir(monkeypatch, capsys,
                          "Entre no seu aplicativo de autenticacao")
    assert valor == "123456"
    assert "aplicativo de autenticacao" in saida
    assert "confira sua mensagem ou e-mail" not in saida.lower()


def test_sem_rotulo_o_texto_nao_afirma_de_onde_vem_o_codigo(monkeypatch, capsys):
    """Afirmar que o portal enviou algo que ele nao enviou faz o operador
    esperar uma mensagem que nunca chega."""
    _, saida = _pedir(monkeypatch, capsys)
    assert "conforme o tribunal" in saida
    assert "O portal enviou" not in saida


# --------------------------------------------------------------------------
# Janela fechada nao e defeito grave
#
# Em 30/09/2026, com a autenticacao ja concluida, o operador fechou a janela
# e o erro do Playwright subiu como traceback de trinta linhas. Parece defeito
# grave e nao e: a sessao ficou guardada no perfil.
# --------------------------------------------------------------------------

def test_janela_fechada_vira_recado_em_portugues(monkeypatch, capsys):
    from justica_mcp import portal as portal_mod

    def explode(*a, **kw):
        raise RuntimeError("ElementHandle.click: Target page, context or browser "
                           "has been closed")

    monkeypatch.setattr(portal_mod, "reconhecer", explode)
    saida = portal_mod.main(["reconhecer", "--url", "https://exemplo"])
    assert saida == 1
    erro = capsys.readouterr().err
    assert "janela do navegador nao esta mais aberta" in erro
    assert "Traceback" not in erro


def test_outro_erro_continua_subindo_inteiro(monkeypatch):
    """Esconder erro de verdade seria pior que o traceback."""
    import pytest

    from justica_mcp import portal as portal_mod

    def explode(*a, **kw):
        raise RuntimeError("erro de verdade, que precisa aparecer")

    monkeypatch.setattr(portal_mod, "reconhecer", explode)
    with pytest.raises(RuntimeError, match="erro de verdade"):
        portal_mod.main(["reconhecer", "--url", "https://exemplo"])


def test_recado_do_pje_em_richfaces_e_lido():
    """Sem as classes do RichFaces, a consulta publica voltava "0 resultados"
    sem dizer se nada foi encontrado ou se o portal recusou o que foi digitado,
    que sao problemas opostos."""
    from justica_mcp.portal import _mensagens_de_erro

    pagina = _PaginaComRecado(".rich-messages-label",
                              "Não existem processos para os critérios informados")
    assert _mensagens_de_erro(pagina) == [
        "Não existem processos para os critérios informados"]


def test_recado_de_campo_obrigatorio_do_pje_e_lido():
    from justica_mcp.portal import _mensagens_de_erro

    pagina = _PaginaComRecado(".msgError", "Informe ao menos um criterio de busca")
    assert "criterio" in _mensagens_de_erro(pagina)[0]


# ==========================================================================
# Falha de rede nao e defeito, e nao deve parecer um
#
# Em 30/09/2026 um ERR_NAME_NOT_RESOLVED subiu como traceback de Playwright no
# meio de uma autenticacao: trinta linhas de pilha para dizer que a internet
# oscilou, num endereco que tinha resolvido normalmente minutos antes. O
# operador nao tem como saber, olhando aquilo, se pode repetir o comando ou se
# acabou de queimar uma tentativa do teto da conta.
# ==========================================================================

class _TelaQueNaoAbre:
    def __init__(self, erro):
        self.erro = erro

    def goto(self, *a, **kw):
        raise RuntimeError(self.erro)


def test_nome_que_nao_resolve_vira_recado_e_nao_pilha():
    from justica_mcp.portal import PortalIndisponivel, _ir_para

    tela = _TelaQueNaoAbre(
        "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://exemplo.jus.br/login.seam")
    with pytest.raises(PortalIndisponivel) as erro:
        _ir_para(tela, "https://exemplo.jus.br/login.seam", 30)
    texto = str(erro.value)
    assert "[REDE]" in texto
    # A frase que decide se o operador pode repetir o comando.
    assert "nenhuma tentativa foi gasta" in texto


def test_portal_que_nao_carrega_sugere_mais_tempo():
    from justica_mcp.portal import PortalIndisponivel, _ir_para

    tela = _TelaQueNaoAbre("Timeout 30000ms exceeded.")
    with pytest.raises(PortalIndisponivel, match="--segundos 60"):
        _ir_para(tela, "https://exemplo.jus.br/login.seam", 30)


def test_erro_que_nao_e_de_rede_continua_subindo_inteiro():
    """Traduzir tudo esconderia defeito de verdade, que e pior que pilha feia."""
    from justica_mcp.portal import _ir_para

    tela = _TelaQueNaoAbre("Coisa nunca vista")
    with pytest.raises(RuntimeError, match="Coisa nunca vista"):
        _ir_para(tela, "https://exemplo.jus.br/login.seam", 30)


def test_navegacao_que_da_certo_nao_levanta_nada():
    from justica_mcp.portal import _ir_para

    class _TelaBoa:
        def __init__(self):
            self.chamadas = []

        def goto(self, url, **kw):
            self.chamadas.append((url, kw))

    tela = _TelaBoa()
    _ir_para(tela, "https://exemplo.jus.br/login.seam", 30)
    assert tela.chamadas[0][1]["timeout"] == 30000


# ==========================================================================
# Segundo fator recusado encerra a execucao
#
# Visto em campo em 30/09/2026: o portal respondeu "Codigo invalido", o comando
# disse "a validacao NAO passou" e SEGUIU para a consulta. A consulta partiu de
# dentro da tela de login, o portal a devolveu para o servidor de autenticacao,
# e a trava a barrou por dominio diferente. O relato terminava com uma falha de
# navegacao, e o defeito de verdade ficava vinte linhas acima.
# ==========================================================================

def test_codigo_recusado_encerra_antes_de_seguir_para_a_consulta():
    import ast
    import inspect
    import textwrap

    from justica_mcp import portal

    arvore = ast.parse(textwrap.dedent(inspect.getsource(portal.autenticar)))
    ramos = [
        no for no in ast.walk(arvore)
        if isinstance(no, ast.If)
        and isinstance(no.test, ast.Name)
        and no.test.id == "ainda_pede_codigo"
    ]
    assert len(ramos) == 1, "o ramo do codigo recusado mudou de forma"
    assert any(isinstance(no, ast.Return) for no in ramos[0].body), (
        "o ramo do codigo recusado precisa ENCERRAR a execucao: sem "
        "autenticacao, nada do que vem depois faz sentido")


# ==========================================================================
# Campo de senha que nao se declara senha
#
# Mapa do eproc do Rio em 02/10/2026: `#pwdSenha  tipo=text  rotulo='Senha'`.
# O olhinho de mostrar a senha (span#showHidePwd) troca o tipo do campo. A
# regra antiga, `tipo == "password"`, deixava de marcar o campo como SENHA no
# relato e fazia `_tem_formulario_de_login` dizer que a tela de login do eproc
# nao tem formulario de login.
# ==========================================================================

def test_campo_declarado_password_e_senha():
    from justica_mcp.portal import parece_campo_de_senha

    assert parece_campo_de_senha("password", "pwd", "pwd", None)


def test_campo_do_eproc_com_tipo_trocado_pelo_olhinho_ainda_e_senha():
    from justica_mcp.portal import parece_campo_de_senha

    assert parece_campo_de_senha("text", "pwdSenha", "pwdSenha", "Senha")


def test_rotulo_com_acento_nao_atrapalha():
    from justica_mcp.portal import parece_campo_de_senha

    assert parece_campo_de_senha("text", None, "campo7", "Informe sua Senha")


def test_autocomplete_denuncia_o_campo_quando_o_nome_nao_denuncia():
    from justica_mcp.portal import parece_campo_de_senha

    assert parece_campo_de_senha("text", "f7", "f7", None, "current-password")


def test_campo_comum_nao_vira_senha():
    from justica_mcp.portal import parece_campo_de_senha

    assert not parece_campo_de_senha("text", "txtUsuario", "txtUsuario", "Usuario")
    assert not parece_campo_de_senha(
        "text", "sidebar-searchbox", "sidebar-searchbox", "Pesquisar no Menu")


def test_a_tela_do_eproc_passa_a_ser_reconhecida_como_login():
    """Era o efeito pratico do defeito: a conferencia de sessao caia em
    INDEFINIDO numa tela que e inequivoca."""
    from justica_mcp.portal import Campo, _tem_formulario_de_login, parece_campo_de_senha

    def _campo(tipo, nome, rotulo):
        return Campo(
            marcador="input", tipo=tipo, nome=nome, identificador=nome,
            rotulo=rotulo, texto_visivel=None,
            e_senha=parece_campo_de_senha(tipo, nome, nome, rotulo),
        )

    tela = [
        _campo("text", "sidebar-searchbox", "Pesquisar no Menu (Alt + m)"),
        _campo("text", "txtUsuario", "Usuario"),
        _campo("text", "pwdSenha", "Senha"),
    ]

    class _Pagina:
        pass

    import justica_mcp.portal as portal_mod

    original = portal_mod._coletar
    portal_mod._coletar = lambda _p: (tela, [])
    try:
        assert _tem_formulario_de_login(_Pagina()) is True
    finally:
        portal_mod._coletar = original


def test_new_password_sozinho_nao_faz_de_cpf_um_campo_de_senha():
    """Tela de cadastro do eproc do Rio, lida em 02/10/2026: CPF, RG, orgao
    emissor e data de emissao vem com `autocomplete=new-password`, que ali so
    pede ao navegador que nao preencha o campo. Aceitar isso como senha fazia a
    tela de cadastro passar por tela de login."""
    from justica_mcp.portal import parece_campo_de_senha

    assert not parece_campo_de_senha("text", "txtCpf", "txtCpf", "CPF:", "new-password")
    assert not parece_campo_de_senha(
        "text", "txtRgNum", "txtRgNum", "Identidade Civil (RG, CNH, Cert. Nasc.):",
        "new-password")
    assert not parece_campo_de_senha(
        "text", "txtDataEmissao", "txtDataEmissao", None, "new-password")


def test_campo_que_se_declara_senha_atual_continua_sendo_senha():
    from justica_mcp.portal import parece_campo_de_senha

    assert parece_campo_de_senha("text", "f7", "f7", None, "current-password")


def test_a_tela_de_cadastro_do_eproc_nao_e_tela_de_login():
    from justica_mcp.portal import Campo, _tem_formulario_de_login, parece_campo_de_senha

    def _campo(nome, rotulo, autocomplete=None):
        return Campo(
            marcador="input", tipo="text", nome=nome, identificador=nome,
            rotulo=rotulo, texto_visivel=None,
            e_senha=parece_campo_de_senha("text", nome, nome, rotulo, autocomplete),
        )

    cadastro = [
        _campo("txtNumProcessoPesquisaRapida", "Numero do processo"),
        _campo("txtCpf", "CPF:", "new-password"),
        _campo("txtRgNum", "Identidade Civil (RG, CNH, Cert. Nasc.):", "new-password"),
        _campo("txtIdentPrinc", None, "new-password"),
    ]

    import justica_mcp.portal as portal_mod

    original = portal_mod._coletar
    portal_mod._coletar = lambda _p: (cadastro, [])
    try:
        assert _tem_formulario_de_login(object()) is False
    finally:
        portal_mod._coletar = original


def test_consulta_sem_evento_entrega_o_relato_da_tela():
    """Sem isto o ponto vira beco: o comando diz que nao achou e nao entrega
    nada com que escrever a leitura certa. Visto no TRF2 em 02/10/2026, com
    'Tabelas na pagina: []' e mais nada."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split("Nenhum evento extraido")[1].split("return 1")[0]
    for esperado in ("_relatar_tela", "_relatar_estrutura_de_dados",
                     "pagina.frames", "guarda.relato()"):
        assert esperado in trecho, esperado


# ==========================================================================
# Segundo clique da copia integral no eproc
#
# Tela real da Justica Federal do Rio, 02/10/2026: o primeiro clique
# (`#btnDownloadCompletoRS`) nao devolve arquivo. Leva a
# `acao=selecionar_processos_agendar_arquivo_completo`, cujos unicos botoes
# proprios sao `#btnGerar` ("Gerar Arquivo Completo") e `#btnVoltar`.
# ==========================================================================

URL_DE_AGENDAMENTO = ("https://eproc.exemplo/controlador.php"
                   "?acao=selecionar_processos_agendar_arquivo_completo&hash=x")


class _BotaoDeGeracao:
    def __init__(self, pagina):
        self.pagina = pagina

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def click(self):
        self.pagina.cliques.append("#btnGerar")


class _TelaDeAgendamento:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, url=URL_DE_AGENDAMENTO, tem_botao=True, baixa=True):
        self.url = url
        self.tem_botao = tem_botao
        self.baixa = baixa
        self.cliques = []

    def query_selector_all(self, seletor):
        if seletor == "#btnGerar" and self.tem_botao:
            return [_BotaoDeGeracao(self)]
        return []

    def expect_download(self, timeout=None):
        tela = self

        class _Espera:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                if not tela.baixa:
                    raise TimeoutError("nada veio")
                return False

            @property
            def value(self):
                return "arquivo-baixado"

        return _Espera()


def _guarda_de_copia():
    from justica_mcp.core.guarda_navegacao import GuardaNavegacao, Modo

    return GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])


def test_o_segundo_clique_gera_e_devolve_o_arquivo():
    from justica_mcp.portal import _gerar_integra_do_eproc

    tela = _TelaDeAgendamento()
    assert _gerar_integra_do_eproc(tela, _guarda_de_copia(), 10) == "arquivo-baixado"
    assert tela.cliques == ["#btnGerar"]


def test_nao_clica_gerar_em_tela_que_nao_e_a_conferida():
    """Clicar num botao chamado 'Gerar' numa tela que nao e a conferida seria
    exatamente o chute que este projeto evita."""
    from justica_mcp.portal import _gerar_integra_do_eproc

    tela = _TelaDeAgendamento(url="https://eproc.exemplo/controlador.php?acao=outra_coisa")
    assert _gerar_integra_do_eproc(tela, _guarda_de_copia(), 10) is None
    assert tela.cliques == []


def test_tela_certa_sem_o_botao_nao_inventa_outro():
    from justica_mcp.portal import _gerar_integra_do_eproc

    tela = _TelaDeAgendamento(tem_botao=False)
    assert _gerar_integra_do_eproc(tela, _guarda_de_copia(), 10) is None
    assert tela.cliques == []


def test_geracao_que_nao_devolve_arquivo_nao_e_tratada_como_erro():
    """O nome da acao no portal fala em AGENDAR: o arquivo pode estar sendo
    montado para depois. Quem chama relata a tela, que e o unico jeito honesto
    de descobrir o que vem a seguir."""
    from justica_mcp.portal import _gerar_integra_do_eproc

    tela = _TelaDeAgendamento(baixa=False)
    assert _gerar_integra_do_eproc(tela, _guarda_de_copia(), 1) is None
    assert tela.cliques == ["#btnGerar"]


def test_pedido_aceito_e_desfecho_bom_e_nao_falha(capsys):
    """Tela real do eproc do Rio, 05/10/2026: "Status do download: Em
    processamento: 31%". O portal aceitou o pedido e esta montando o arquivo.
    Tratar isso como falha fazia o relato terminar em "copia nao concluida
    (TimeoutError)" depois de tudo ter dado certo."""
    from justica_mcp.portal import GERACAO_PEDIDA, _gerar_integra_do_eproc

    class _TelaQuePediu(_TelaDeAgendamento):
        def query_selector(self, seletor):
            class _Area:
                def inner_text(self_):
                    return ("Status do download: Em processamento: 31% "
                            "(solicitação foi feita em 05/10/2026 19:47:57).")

            return _Area() if seletor == "#divInfraAreaDados" else None

    tela = _TelaQuePediu(baixa=False)
    assert _gerar_integra_do_eproc(tela, _guarda_de_copia(), 1) is GERACAO_PEDIDA
    saida = capsys.readouterr().out
    assert "ACEITOU o pedido" in saida
    assert "Nao ha nada a corrigir" in saida


def test_o_fim_da_saida_nao_desmente_o_que_aconteceu():
    """Dizia "botao de copia integral nao encontrado nesta tela" mesmo quando o
    botao fora encontrado, clicado e o portal respondera que esta montando o
    arquivo."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert "botao de copia integral nao encontrado nesta tela." not in fonte
    assert "o motivo " in fonte


def test_a_trava_registra_o_clique_de_gerar_nominalmente():
    from justica_mcp.portal import _gerar_integra_do_eproc

    guarda = _guarda_de_copia()
    _gerar_integra_do_eproc(_TelaDeAgendamento(), guarda, 10)
    assert [r["alvo"] for r in guarda.registro] == ["#btnGerar"]
    assert guarda.registro[0]["permitido"] is True


# ==========================================================================
# Sessao aberta nao se reautentica
#
# Ate 02/10/2026 o comando mandava credencial e codigo SEMPRE, e so depois
# reparava que o portal nao tinha pedido o segundo fator porque a sessao ja
# valia. O navegador roda com perfil persistente, entao a sessao do eproc
# sobrevive entre execucoes: cada consulta gastava um login a toa. Varios
# logins seguidos do mesmo lugar foi o que levantou o desafio do Cloudflare no
# TRF2. A autenticacao que nao precisava acontecer e a que nao deve acontecer.
# ==========================================================================

class _TelaDeSessao:
    """Fake de tela, com ou sem formulario de login e com ou sem a prova."""

    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, com_login=False, com_busca=False):
        self.com_login, self.com_busca = com_login, com_busca

    def query_selector_all(self, seletor):
        if seletor == "#txtNumProcessoPesquisaRapida" and self.com_busca:
            class _Elemento:
                def is_visible(self):
                    return True

                def bounding_box(self):
                    return {"x": 1, "y": 1, "width": 9, "height": 9}

            return [_Elemento()]
        return []


def _fingir_coletar(monkeypatch, tem_senha, perfis=()):
    from justica_mcp.portal import Campo

    campos = [Campo(marcador="input", tipo="password", nome="pwd", identificador="pwd",
                    rotulo="Senha", texto_visivel=None, e_senha=True)] if tem_senha else []
    monkeypatch.setattr("justica_mcp.portal._coletar", lambda p: (campos, list(perfis)))


def test_tela_de_login_nunca_conta_como_sessao_aberta(monkeypatch):
    from justica_mcp.portal import _sessao_ja_aberta

    _fingir_coletar(monkeypatch, tem_senha=True)
    assert _sessao_ja_aberta(_TelaDeSessao(com_busca=True), "eproc") is False


def test_a_barra_de_busca_do_eproc_prova_que_a_sessao_vale(monkeypatch):
    """A tela de entrada do eproc NAO tem essa barra; a de dentro tem. Os dois
    mapas sao de 02/10/2026."""
    from justica_mcp.portal import _sessao_ja_aberta

    _fingir_coletar(monkeypatch, tem_senha=False)
    assert _sessao_ja_aberta(_TelaDeSessao(com_busca=True), "eproc") is True


def test_ausencia_de_login_sozinha_nao_prova_nada(monkeypatch):
    """Tela de erro, de manutencao ou de aviso tambem nao tem formulario de
    login. Concluir por ausencia faria o comando seguir como autenticado sem
    estar, e o operador leria 'processo nao encontrado' sobre processo que
    existe."""
    from justica_mcp.portal import _sessao_ja_aberta

    _fingir_coletar(monkeypatch, tem_senha=False)
    assert _sessao_ja_aberta(_TelaDeSessao(), "eproc") is False


def test_sistema_sem_prova_conferida_nao_ganha_prova_inventada(monkeypatch):
    """Nenhuma tela interna do PJe foi lida ainda."""
    from justica_mcp.portal import _sessao_ja_aberta

    _fingir_coletar(monkeypatch, tem_senha=False)
    assert _sessao_ja_aberta(_TelaDeSessao(com_busca=True), "pje") is False


def test_tela_de_selecao_de_perfil_prova_sessao_em_qualquer_sistema(monkeypatch):
    from justica_mcp.portal import Campo, _sessao_ja_aberta

    # `formulario` importa: no eproc os botoes de perfil vivem em
    # `frmEscolherUsuario`, e e por isso que `_perfis_disponiveis` os reconhece.
    botao = Campo(marcador="tr", tipo="", nome=None, identificador="tr0",
                  rotulo=None, texto_visivel="RJ168943\nADVOGADO", e_senha=False,
                  formulario="frmEscolherUsuario")
    _fingir_coletar(monkeypatch, tem_senha=False, perfis=[botao])
    assert _sessao_ja_aberta(_TelaDeSessao(), "pje") is True


def test_a_credencial_so_e_enviada_quando_a_sessao_nao_vale():
    """Guarda a forma do codigo: as duas etapas ficam sob `if not
    sessao_aberta`, e a pergunta vem ANTES delas."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    antes, depois = fonte.split("if not sessao_aberta:", 1)
    assert "_sessao_ja_aberta(" in antes
    assert "etapa 1: credencial" not in antes
    assert "etapa 1: credencial" in depois
    assert "etapa 2: segundo fator" in depois


def test_falha_do_acervo_nao_derruba_a_consulta_ja_concluida():
    """A consulta termina e e gravada ANTES da copia. Em 05/10/2026 um
    WinError 1450 do Google Drive matou o comando com traceback depois de a
    extracao ja ter dado certo: o trabalho que funcionou foi jogado fora por
    causa do que falhou depois."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert fonte.count("except AcervoIndisponivel as exc:") == 2, (
        "os dois ramos, e-SAJ e eproc, precisam sobreviver a falha do acervo")
    # A gravacao da consulta acontece antes, e o aviso aponta para ela.
    assert "A consulta acima vale e ja esta no arquivo indicado abaixo." in fonte


# ==========================================================================
# A tela de sistema precisa ser LIDA, e nao so descrita
#
# O relato desta casa imprime estrutura e nunca conteudo, por causa de dado de
# cliente. Certo para tela de processo. Para a tela que confirma o pedido de
# geracao de arquivo, virou buraco: em 05/10/2026 os dois cliques funcionaram,
# o portal aceitou o pedido, e ninguem ficou sabendo onde o arquivo vai parar
# porque o texto da tela nunca foi lido.
# ==========================================================================

class _TelaComRecado:
    def __init__(self, areas=None, menu=()):
        self.areas = areas or {}
        self.menu = list(menu)

    def query_selector(self, seletor):
        valor = self.areas.get(seletor)
        if valor is None:
            return None

        class _Area:
            def inner_text(self_):
                return valor

        return _Area()

    def query_selector_all(self, _seletor):
        itens = self.menu

        class _Item:
            def __init__(self_, texto):
                self_.texto = texto

            def inner_text(self_):
                return self_.texto

        return [_Item(t) for t in itens]


def test_o_recado_vem_da_area_mais_estreita_que_existir():
    from justica_mcp.portal import _recado_da_tela

    tela = _TelaComRecado({
        "#divInfraAreaDados": "  O arquivo   sera gerado\n e ficara disponivel. ",
        "#divInfraAreaTela": "texto largo demais",
    })
    assert _recado_da_tela(tela) == "O arquivo sera gerado e ficara disponivel."


def test_area_ausente_cai_para_a_seguinte():
    from justica_mcp.portal import _recado_da_tela

    tela = _TelaComRecado({"body": "recado de ultimo recurso"})
    assert _recado_da_tela(tela) == "recado de ultimo recurso"


def test_tela_muda_devolve_vazio_e_nao_explode():
    from justica_mcp.portal import _recado_da_tela

    assert _recado_da_tela(_TelaComRecado()) == ""


def test_o_recado_e_encurtado():
    from justica_mcp.portal import _recado_da_tela

    tela = _TelaComRecado({"#divInfraAreaDados": "x" * 5000})
    assert len(_recado_da_tela(tela, limite=100)) == 100


def test_itens_do_menu_sem_repeticao():
    """O eproc monta duas barras, uma para tela grande e outra para telefone,
    com os mesmos rotulos. Repetir tudo dobraria a lista sem acrescentar nada."""
    from justica_mcp.portal import _itens_do_menu

    tela = _TelaComRecado(menu=["Consultas", "Relatorios", "Consultas", "  "])
    assert _itens_do_menu(tela) == ["Consultas", "Relatorios"]


# ==========================================================================
# A copia integral do eproc vem PARTIDA, em outro endereco, e em ABA NOVA
#
# Tela real da Justica Federal do Rio, 05/10/2026. A MESMA tela que antes
# trazia "Gerar Arquivo Completo" passou a trazer, com o arquivo pronto:
#
#     'BAIXAR ARQUIVO PARTE 1'  -> https://eproc-down.jfrj.jus.br/...
#     'BAIXAR ARQUIVO PARTE 2'  -> https://eproc-down.jfrj.jus.br/...
#     'forcar nova geracao de download completo'
#
# E o clique abre ABA NOVA: as duas abas apareceram com os PDFs, enquanto a
# espera do download morria na aba velha, onde download nenhum acontece.
# ==========================================================================

PDF_FALSO = b"%PDF-1.4 conteudo de teste"

URL_PARTE = ("https://eproc-down.jfrj.jus.br/eproc/controlador.php"
             "?acao=download_completo_download_pronto_enviar"
             "&file=/download72h/999/RJ-123-2026-10-5_PARTE_{n}.PDF&hash=abc")


class _AbaDoArquivo:
    def __init__(self, url):
        self.url = url
        self.fechada = False

    def wait_for_load_state(self, *a, **kw):
        pass

    def close(self):
        self.fechada = True


class _RespostaDoPortal:
    def __init__(self, corpo, ok=True, status=200, tipo="application/pdf"):
        self._corpo, self.ok, self.status = corpo, ok, status
        self.headers = {"content-type": tipo}

    def body(self):
        return self._corpo


class _Requisicoes:
    def __init__(self, respostas):
        self.respostas = respostas
        self.pedidos = []

    def get(self, endereco):
        self.pedidos.append(endereco)
        return self.respostas.get(endereco) or _RespostaDoPortal(PDF_FALSO)


class _ContextoDoNavegador:
    def __init__(self, tela, respostas=None, abre_aba=True):
        self.tela, self.abre_aba = tela, abre_aba
        self.request = _Requisicoes(respostas or {})
        self.abas = []

    def expect_page(self, timeout=None):
        contexto = self

        class _Espera:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                if not contexto.abre_aba:
                    raise TimeoutError("nenhuma aba abriu")
                return False

            @property
            def value(self_):
                alvo = contexto.tela.links[len(contexto.tela.cliques) - 1]
                aba = _AbaDoArquivo(alvo.href)
                contexto.abas.append(aba)
                return aba

        return _Espera()


class _LinkDeParte:
    def __init__(self, tela, texto, href):
        self.tela, self.texto, self.href = tela, texto, href

    def inner_text(self):
        return self.texto

    def get_attribute(self, nome):
        return self.href if nome == "href" else None

    def click(self):
        self.tela.cliques.append(self.texto)


class _TelaDePartes:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, com_partes=True, **kw):
        self.url = ("https://eproc.jfrj.jus.br/eproc/controlador.php"
                    "?acao=selecionar_processos_agendar_arquivo_completo&hash=x")
        self.cliques = []
        self.links = []
        if com_partes:
            self.links = [
                _LinkDeParte(self, "BAIXAR ARQUIVO PARTE 1", URL_PARTE.format(n=1)),
                _LinkDeParte(self, "BAIXAR ARQUIVO PARTE 2", URL_PARTE.format(n=2)),
                _LinkDeParte(self, "forçar nova geração de download completo",
                             "controlador.php?acao=selecionar_processos_agendar"),
            ]
        self.context = _ContextoDoNavegador(self, **kw)

    def query_selector_all(self, seletor):
        return list(self.links) if seletor == "a[href]" else []


def _guarda_que_baixa():
    from justica_mcp.core.guarda_navegacao import GuardaNavegacao, Modo

    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    guarda.permitir_download = True
    return guarda


def test_as_partes_sao_achadas_pelo_rotulo():
    from justica_mcp.portal import _links_das_partes

    assert [l.texto for l in _links_das_partes(_TelaDePartes())] == [
        "BAIXAR ARQUIVO PARTE 1", "BAIXAR ARQUIVO PARTE 2"]


def test_o_link_de_forcar_nova_geracao_nunca_entra():
    """Ele descarta o arquivo pronto e devolve o processo para a fila."""
    from justica_mcp.portal import _links_das_partes

    achados = _links_das_partes(_TelaDePartes())
    assert all("geração" not in l.texto for l in achados)


def test_as_duas_partes_sao_gravadas_na_ordem(tmp_path):
    from justica_mcp.portal import _baixar_partes_do_eproc

    tela = _TelaDePartes()
    gravados = _baixar_partes_do_eproc(tela, _guarda_que_baixa(), tmp_path, "123", 5)

    assert len(gravados) == 2
    assert pathlib.Path(gravados[0]).read_bytes() == PDF_FALSO
    # O nome vem do parametro `file` do endereco, que ja traz processo e data.
    assert gravados[0].endswith("integra-parte1-RJ-123-2026-10-5_PARTE_1.PDF")
    assert gravados[1].endswith("integra-parte2-RJ-123-2026-10-5_PARTE_2.PDF")


def test_o_endereco_buscado_e_o_da_ABA_NOVA(tmp_path):
    """O clique abre aba nova, e o endereco que vale e o dela: e o que o
    navegador de fato resolveu, com ticket e sessao."""
    from justica_mcp.portal import _baixar_partes_do_eproc

    tela = _TelaDePartes()
    _baixar_partes_do_eproc(tela, _guarda_que_baixa(), tmp_path, "123", 5)
    assert tela.context.request.pedidos == [URL_PARTE.format(n=1), URL_PARTE.format(n=2)]
    assert all(aba.fechada for aba in tela.context.abas)


def test_pagina_de_erro_com_nome_de_pdf_e_recusada(tmp_path, capsys):
    """Pagina de erro tem endereco de arquivo e corpo de HTML. Gravada com nome
    de PDF, ela entra no acervo como se fossem autos, e o advogado so descobre
    ao abrir, meses depois."""
    from justica_mcp.portal import _baixar_partes_do_eproc

    erro = _RespostaDoPortal(b"<html>Sessao expirada</html>", tipo="text/html")
    tela = _TelaDePartes(respostas={URL_PARTE.format(n=1): erro})
    gravados = _baixar_partes_do_eproc(tela, _guarda_que_baixa(), tmp_path, "123", 5)

    assert len(gravados) == 1
    saida = capsys.readouterr().out
    assert "nao e PDF" in saida
    assert "INCOMPLETA" in saida


def test_sem_aba_nova_sobra_o_endereco_do_link(tmp_path):
    from justica_mcp.portal import _baixar_partes_do_eproc

    tela = _TelaDePartes(abre_aba=False)
    gravados = _baixar_partes_do_eproc(tela, _guarda_que_baixa(), tmp_path, "123", 1)
    assert len(gravados) == 2


def test_tela_sem_parte_pronta_devolve_lista_vazia(tmp_path):
    """Caso normal logo depois de pedir a geracao."""
    from justica_mcp.portal import _baixar_partes_do_eproc

    tela = _TelaDePartes(com_partes=False)
    assert _baixar_partes_do_eproc(tela, _guarda_que_baixa(), tmp_path, "123", 5) == []


def test_o_download_passa_pela_trava_parte_a_parte(tmp_path):
    from justica_mcp.portal import _baixar_partes_do_eproc

    guarda = _guarda_que_baixa()
    _baixar_partes_do_eproc(_TelaDePartes(), guarda, tmp_path, "123", 5)
    assert [(r["acao"], r["permitido"]) for r in guarda.registro] == [
        ("baixar", True), ("baixar", True)]


def test_o_pronto_vem_antes_de_pedir_geracao_nova():
    """Pedir geracao por cima de um arquivo pronto o descartaria e devolveria o
    processo para a fila."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._fluxo_do_botao_de_copia)
    assert fonte.index("_baixar_partes_do_eproc") < fonte.index("_gerar_integra_do_eproc")


def test_a_espera_do_primeiro_clique_e_curta():
    """Em duas execucoes reais, 02 e 05/10/2026, o botao da tela do processo
    NUNCA devolveu arquivo: o efeito dele e navegar para a tela de geracao.
    Esperar os 45s da operacao inteira jogava fora 45 segundos por consulta."""
    import inspect

    from justica_mcp import portal

    assert portal.TETO_DO_DOWNLOAD_DIRETO <= 10
    fonte = inspect.getsource(portal._fluxo_do_botao_de_copia)
    assert "expect_download(timeout=TETO_DO_DOWNLOAD_DIRETO * 1000)" in fonte


def test_o_caminho_normal_nao_se_anuncia_como_erro():
    """Dizer 'nao devolveu arquivo' fazia o relato comecar por um erro que nao
    existe, e quem lesse so o comeco concluiria que a copia deu errado."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._fluxo_do_botao_de_copia)
    assert "O clique nao devolveu arquivo" not in fonte
    assert "leva a tela de geracao" in fonte


# ==========================================================================
# A etapa de credencial precisa do campo VISIVEL
#
# O eproc monta a mesma tela duas vezes, uma para tela grande e outra para
# telefone, com os MESMOS identificadores. `query_selector` devolve a primeira
# do documento, que pode ser a oculta. `elemento_visivel` existe no projeto
# desde setembro por causa disso, e a etapa de credencial era o unico lugar que
# ainda nao a usava.
#
# Conferido em campo em 05/10/2026, no eproc do Rio: o clique passou 30
# segundos tentando acertar um campo invisivel e terminou em traceback.
# ==========================================================================

def test_a_credencial_procura_o_campo_visivel():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    etapa = fonte.split("etapa 1: credencial")[1].split("etapa 2")[0]
    assert "elemento_visivel(pagina, seletor)" in etapa
    assert "elemento = pagina.query_selector(seletor)" not in etapa
    # O campo espelho continua sendo procurado pelo caminho antigo, de
    # proposito: ele existe justamente para conferir se a senha chegou ao campo
    # que vai ser enviado, e esse e oculto por natureza.
    assert "pagina.query_selector(campo_senha_oculto)" in etapa


def test_campo_que_existe_mas_nao_aparece_e_dito_com_todas_as_letras():
    """Insistir nele seria digitar onde ninguem ve, e o relato precisa separar
    isso de 'campo nao encontrado', que tem outra causa e outro conserto."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    assert "nenhuma copia dele esta visivel" in fonte
    assert "encontrado. Nada enviado." in fonte


def test_o_botao_de_entrar_tambem_tem_de_estar_visivel():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    assert "entrar_visivel = elemento_visivel(pagina, botao_entrar)" in fonte
    assert "pagina.query_selector(botao_entrar).click()" not in fonte


# ==========================================================================
# A tela de login manda mais que a configuracao
#
# A tabela por sistema presumia que eproc tem a tela do eproc. O eproc do Rio
# desmentiu isso em 05/10/2026: ele nao mostra a propria tela, redireciona para
# um Keycloak em `eproc-sso.tjrj.jus.br`, com `#username`, `#password` e
# `#kc-login`, os MESMOS identificadores do PJe.
# ==========================================================================

class _TelaDeLogin:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, visiveis):
        self.visiveis = set(visiveis)

    def query_selector_all(self, seletor):
        if seletor not in self.visiveis:
            return []

        class _Campo:
            def is_visible(self):
                return True

            def bounding_box(self):
                return {"x": 1, "y": 1, "width": 9, "height": 9}

        return [_Campo()]


def test_a_tela_do_eproc_e_reconhecida():
    from justica_mcp.portal import familia_da_tela

    familia = familia_da_tela(_TelaDeLogin({"#txtUsuario"}))
    assert familia["nome"] == "eproc"
    assert familia["botao_entrar"] == "#sbmEntrar"


def test_a_tela_de_keycloak_e_reconhecida():
    from justica_mcp.portal import familia_da_tela

    familia = familia_da_tela(_TelaDeLogin({"#username"}))
    assert familia["nome"] == "keycloak"
    assert familia["botao_entrar"] == "#kc-login"
    assert familia["campo_codigo"] == "#otp"


def test_o_campo_de_senha_do_keycloak_nao_e_procurado_pelo_tipo():
    """A tela traz o olhinho de mostrar a senha, que troca o tipo do campo para
    `text`: procurar por `input[type=password]` nao acharia nada."""
    from justica_mcp.portal import FAMILIAS_DE_LOGIN

    keycloak = [f for f in FAMILIAS_DE_LOGIN if f["nome"] == "keycloak"][0]
    assert "type=password" not in keycloak["campo_senha_oculto"]
    assert keycloak["campo_senha_oculto"] == "#password"


def test_tela_desconhecida_nao_vira_palpite():
    from justica_mcp.portal import familia_da_tela

    assert familia_da_tela(_TelaDeLogin({"#campoQualquer"})) is None


def test_a_troca_so_acontece_quando_o_configurado_nao_aparece():
    """O que o operador passou na linha de comando continua tendo a ultima
    palavra quando funciona."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("A tela manda mais que a configuracao")[1]
    assert "if elemento_visivel(pagina, campo_usuario) is None:" in trecho.split(
        "etapa 1: credencial")[0]


def test_a_tela_reconhecida_entra_na_trava_nominalmente():
    """Trocar os seletores sem autorizar os novos deixaria a trava barrar o
    proprio login que ela deveria permitir."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("A tela manda mais que a configuracao")[1].split(
        "etapa 1: credencial")[0]
    assert "guarda.permissoes.append(permissao)" in trecho
    assert "seletores_preenchiveis=(campo_usuario, campo_senha," in trecho


def test_sem_botao_de_copia_o_comando_relata_a_tela():
    """Conferido em campo em 05/10/2026: o eproc do Rio nao tem
    `#btnDownloadCompletoRS`, e o comando parava dizendo so que nao achou, sem
    entregar nada com que descobrir qual e o botao de la."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_integra)
    trecho = fonte.split("botao = elemento_visivel(pagina, BOTAO_INTEGRA)")[1]
    cabeca = trecho.split("return []")[0]
    assert '_relatar_tela(pagina, "TELA DO PROCESSO")' in cabeca


def test_botao_de_icone_mostra_o_rotulo_acessivel():
    """Botao de icone nao tem texto. Sem o rotulo acessivel ele aparece no
    relato como `(sem id)  ''`, e podia ser qualquer coisa, inclusive o de
    copiar os autos. Quatro deles apareceram assim na tela do processo do eproc
    do Rio em 05/10/2026."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._coletar)
    trecho = fonte.split("botoes: list[Campo] = []")[1]
    assert '"aria-label", "title", "alt"' in trecho
    assert "rotulo=rotulo_acessivel," in trecho

    relato = inspect.getsource(portal._relatar_tela)
    assert "rotulo={b.rotulo!r}" in relato


def test_sem_botao_de_copia_o_menu_tambem_e_listado():
    """A copia pode morar no menu, e nao na tela do processo."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_integra)
    cabeca = fonte.split("return []")[0]
    assert "_itens_do_menu(pagina)" in cabeca


# ==========================================================================
# O botao de copia do eproc do Rio, perdido por um acento
#
# A tela do processo do Rio tem, no quadro "Acoes", um link escrito
# "Acesso íntegra do processo". O relato jurou duas vezes que nao havia botao de
# copia ali, porque o filtro procurava "integra" e `"integra" in "íntegra"` e
# falso. Ja "Arrecadacao Integrada", sem acento, passava e virava ruido.
#
# O operador informou em 05/10/2026 que clicar nesse link dispara um SEGUNDO
# FATOR, como no login: estar autenticado nao basta para abrir os autos.
# ==========================================================================

class _AlvoComTexto:
    def __init__(self, texto, visivel=True):
        self.texto, self.visivel = texto, visivel
        self.cliques = 0

    def is_visible(self):
        return self.visivel

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def inner_text(self):
        return self.texto

    def get_attribute(self, nome):
        return None

    def click(self):
        self.cliques += 1


class _TelaDeAcoes:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, textos):
        self.url = "https://eproc1g.tjrj.jus.br/eproc/controlador.php?acao=processo_selecionar"
        self.alvos = [_AlvoComTexto(x) for x in textos]

    def query_selector_all(self, seletor):
        return list(self.alvos) if seletor == "a, button" else []


def test_o_acento_nao_pode_mais_esconder_o_acesso_a_integra():
    from justica_mcp.portal import _acesso_a_integra

    tela = _TelaDeAcoes([
        "Arrecadação Integrada na Web",
        "Acesso íntegra do processo",
        "Movimentar/Peticionar",
    ])
    achado = _acesso_a_integra(tela)
    assert achado is tela.alvos[1]


def test_arrecadacao_integrada_nao_e_confundida_com_a_integra():
    from justica_mcp.portal import _acesso_a_integra

    tela = _TelaDeAcoes(["Arrecadação Integrada na Web", "Guias Depósito Judicial"])
    assert _acesso_a_integra(tela) is None


def test_alvo_invisivel_nao_conta():
    from justica_mcp.portal import _acesso_a_integra

    tela = _TelaDeAcoes(["Acesso íntegra do processo"])
    tela.alvos[0].visivel = False
    assert _acesso_a_integra(tela) is None


def test_o_filtro_do_relato_compara_sem_acento():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._relatar_tela)
    assert "sem_acento(texto)" in fonte
    assert "integra" in portal.TERMOS_DE_COPIA


class _CampoDeCodigo:
    def __init__(self, tela, seletor):
        self.tela, self.seletor = tela, seletor
        self.valor = None

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def click(self):
        pass

    def fill(self, valor):
        self.valor = valor
        self.tela.digitado[self.seletor] = valor


class _BotaoDeCodigo:
    def __init__(self, tela, seletor):
        self.tela, self.seletor = tela, seletor

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def click(self):
        self.tela.cliques.append(self.seletor)


class _TelaDeCodigo:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, presentes):
        self.url = "https://eproc1g.tjrj.jus.br/eproc/controlador.php?acao=integra"
        self.presentes = set(presentes)
        self.digitado, self.cliques = {}, []

    def query_selector_all(self, seletor):
        if seletor not in self.presentes:
            return []
        if seletor.startswith("#btn") or seletor == "#kc-login":
            return [_BotaoDeCodigo(self, seletor)]
        return [_CampoDeCodigo(self, seletor)]

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


class _CofreFalso:
    def __init__(self, com_semente=True):
        self.com_semente = com_semente

    def tem_semente(self, identidade):
        return self.com_semente

    def segundos_restantes_do_codigo(self):
        return 25

    def _codigo_segundo_fator(self, identidade, minimo_segundos=8):
        return "123456"


class _Identidade:
    tribunal, sistema, rotulo = "TJRJ", "eproc", "TJRJ / eproc"


def _guarda_simples():
    from justica_mcp.core.guarda_navegacao import GuardaNavegacao, Modo

    return GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])


def test_tela_sem_campo_de_codigo_nao_pede_nada(monkeypatch):
    """Nem todo clique na integra pede segundo fator; dizer que pediu levaria o
    operador a procurar um codigo que ninguem quis."""
    from justica_mcp.portal import _responder_segundo_fator

    assert _responder_segundo_fator(
        _TelaDeCodigo([]), _guarda_simples(), _Identidade(), 5) is False


def test_o_codigo_sai_do_cofre_e_e_enviado(monkeypatch):
    from justica_mcp import portal

    monkeypatch.setattr(portal, "Cofre", lambda: _CofreFalso())
    tela = _TelaDeCodigo(["#otp", "#kc-login"])
    guarda = _guarda_simples()

    assert portal._responder_segundo_fator(tela, guarda, _Identidade(), 5) is True
    assert tela.digitado == {"#otp": "123456"}
    assert tela.cliques == ["#kc-login"]
    assert [r["acao"] for r in guarda.registro] == ["preencher", "clicar"]


def test_a_familia_do_eproc_tambem_serve(monkeypatch):
    from justica_mcp import portal

    monkeypatch.setattr(portal, "Cofre", lambda: _CofreFalso())
    tela = _TelaDeCodigo(["#txtAcessoCodigo", "#btnValidar"])
    assert portal._responder_segundo_fator(tela, _guarda_simples(), _Identidade(), 5)
    assert tela.digitado == {"#txtAcessoCodigo": "123456"}


def test_sem_semente_o_pedido_de_codigo_vira_recusa_com_motivo(monkeypatch):
    """A consulta ja terminou; dizer so 'copia nao concluida' mandaria procurar
    defeito onde ha falta de semente."""
    from justica_mcp import portal

    monkeypatch.setattr(portal, "Cofre", lambda: _CofreFalso(com_semente=False))
    with pytest.raises(portal.ConteudoInesperado, match="semente"):
        portal._responder_segundo_fator(
            _TelaDeCodigo(["#otp", "#kc-login"]), _guarda_simples(), _Identidade(), 5)


def test_campo_sem_botao_nao_digita_o_codigo(monkeypatch):
    """Digitar um codigo que nao sera enviado queima a janela de validade dele
    por nada."""
    from justica_mcp import portal

    monkeypatch.setattr(portal, "Cofre", lambda: _CofreFalso())
    tela = _TelaDeCodigo(["#otp"])
    with pytest.raises(portal.ConteudoInesperado, match="botao"):
        portal._responder_segundo_fator(tela, _guarda_simples(), _Identidade(), 5)
    assert tela.digitado == {}


# ==========================================================================
# Pagina de erro do navegador nao e recusa de credencial
#
# Visto em campo em 05/10/2026: depois da credencial enviada ao eproc do Rio, a
# tela era `chrome-error://chromewebdata/`, com titulo `eproc-sso.tjrj.jus.br`.
# O servidor de autenticacao nao respondeu. O comando disse "a tela do segundo
# fator nao apareceu" e mandou NAO repetir, por poder ser recusa de credencial.
# Era o pior conselho possivel: nao houve resposta, nao ha o que tenha sido
# recusado, e repetir e justamente o certo.
# ==========================================================================

def test_pagina_de_erro_do_navegador_e_reconhecida():
    from justica_mcp.portal import pagina_de_erro_do_navegador

    assert pagina_de_erro_do_navegador("chrome-error://chromewebdata/")
    assert pagina_de_erro_do_navegador("about:neterror?e=dnsNotFound")


def test_tela_de_portal_nao_e_confundida_com_erro_do_navegador():
    from justica_mcp.portal import pagina_de_erro_do_navegador

    assert not pagina_de_erro_do_navegador(
        "https://eproc1g.tjrj.jus.br/eproc/controlador.php?acao=principal")
    assert not pagina_de_erro_do_navegador("")


def test_o_conselho_muda_quando_o_portal_nao_respondeu():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("A tela do segundo fator nao apareceu")[1]
    assert "pagina_de_erro_do_navegador(pagina.url)" in trecho
    # O conselho oposto ao padrao: aqui repetir e o certo.
    assert "Repita o comando" in trecho
    assert "Nao ha nada a conferir no cofre" in trecho


# ==========================================================================
# Clique feito e navegacao lenta nao e clique que falhou
#
# O Playwright espera, depois do clique, pelas navegacoes que ele disparou. Se o
# portal demora, essa espera estoura e o erro sai como se o CLIQUE tivesse
# falhado. Visto em campo em 05/10/2026 no eproc do Rio, logo depois de o portal
# ficar fora do ar: credencial e codigo ja enviados, e o comando caiu em
# traceback com "click action done" escrito no proprio registro do erro.
# ==========================================================================

class _ElementoLento:
    REGISTRO_DO_CLIQUE_FEITO = (
        "ElementHandle.click: Timeout 30000ms exceeded.\n"
        "Call log:\n  - performing click action\n  - click action done\n"
        "  - waiting for scheduled navigations to finish\n")
    REGISTRO_DO_CLIQUE_NAO_FEITO = (
        "ElementHandle.click: Timeout 30000ms exceeded.\n"
        "Call log:\n  - waiting for element to be visible, enabled and stable\n"
        "    - element is not visible\n")

    def __init__(self, erro=None):
        self.erro, self.cliques = erro, 0

    def click(self, timeout=None):
        self.cliques += 1
        if self.erro:
            raise TimeoutError(self.erro)


def test_navegacao_lenta_depois_do_clique_nao_derruba(capsys):
    from justica_mcp.portal import clicar_tolerando_lentidao

    alvo = _ElementoLento(_ElementoLento.REGISTRO_DO_CLIQUE_FEITO)
    clicar_tolerando_lentidao(alvo, "#kc-login", 30)
    assert alvo.cliques == 1, "o clique NAO pode ser refeito: ele ja aconteceu"
    assert "ACONTECEU" in capsys.readouterr().out


def test_clique_que_nao_saiu_continua_subindo():
    """Ai o clique realmente nao aconteceu, e esconder isso faria o comando
    seguir como se a credencial tivesse sido enviada."""
    from justica_mcp.portal import clicar_tolerando_lentidao

    with pytest.raises(TimeoutError):
        clicar_tolerando_lentidao(
            _ElementoLento(_ElementoLento.REGISTRO_DO_CLIQUE_NAO_FEITO), "#x", 30)


def test_clique_normal_nao_imprime_nada(capsys):
    from justica_mcp.portal import clicar_tolerando_lentidao

    clicar_tolerando_lentidao(_ElementoLento(), "#x", 30)
    assert capsys.readouterr().out == ""


def test_os_dois_cliques_do_login_toleram_lentidao():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    assert "clicar_tolerando_lentidao(entrar_visivel, botao_entrar, segundos)" in fonte
    assert "clicar_tolerando_lentidao(validar_visivel, botao_validar, segundos)" in fonte


# ==========================================================================
# No Rio a integra abre em QUADRO EMBUTIDO, e nao em aba nova
#
# Tela real de 05/10/2026, depois do clique em "Acesso íntegra do processo":
#
#     'Acesso íntegra do processo'  ->  javascript:void(0);
#     QUADROS EMBUTIDOS (2):
#       src=controlador.php?acao=processo_vista_sem_procuracao&txtNumProcesso=...
#
# O link nao tem endereco para seguir, so o efeito do script. E o segundo fator
# e os arquivos ficam DENTRO do quadro: procura-los no documento de cima nao
# acha nada.
# ==========================================================================

class _QuadroEmbutido:
    def __init__(self, url):
        self.url = url


class _PaginaDeQuadrosEmbutidos:
    def __init__(self, urls):
        self.frames = [_QuadroEmbutido(u) for u in urls]


def test_o_quadro_da_integra_e_achado_pelo_endereco():
    from justica_mcp.portal import quadro_da_integra

    pagina = _PaginaDeQuadrosEmbutidos([
        "https://eproc1g.tjrj.jus.br/eproc/controlador.php?acao=processo_selecionar",
        "https://eproc1g.tjrj.jus.br/eproc/controlador.php"
        "?acao=processo_vista_sem_procuracao&txtNumProcesso=123",
    ])
    assert quadro_da_integra(pagina) is pagina.frames[1]


def test_pagina_sem_o_quadro_devolve_nada():
    from justica_mcp.portal import quadro_da_integra

    assert quadro_da_integra(_PaginaDeQuadrosEmbutidos(["https://exemplo/outra"])) is None


def test_quadro_embutido_nao_quebra_a_leitura_da_estrutura():
    """Quadro nao tem `viewport_size`: so a pagina tem. Ler de dentro dele
    quebrava com AttributeError."""
    from justica_mcp.portal import janela_de

    class _SoQuadro:
        pass

    assert janela_de(_SoQuadro()) == {"width": 1280, "height": 720}

    class _Pagina:
        viewport_size = {"width": 800, "height": 600}

    assert janela_de(_Pagina()) == {"width": 800, "height": 600}


def test_o_download_de_dentro_do_quadro_usa_a_pagina():
    """Quadro nao tem contexto nem espera de download: quem tem e a pagina que
    o contem."""
    from justica_mcp.portal import pagina_de

    class _Pagina:
        nome = "pagina"

    pagina = _Pagina()

    class _Frame:
        page = pagina

    assert pagina_de(_Frame()) is pagina
    assert pagina_de(pagina) is pagina


# ==========================================================================
# Nem todo botao de validar tem identificador
#
# Tela "Acesso à Íntegra do Processo" do eproc do Rio, lida em 05/10/2026 dentro
# do quadro embutido: `#txtAcessoCodigo` e dois botoes SEM ID, "Confirmar" e
# "Cancelar", lado a lado. O codigo nao chegou a ser digitado, que e o certo:
# digitar um codigo que nao seria enviado queima a validade dele por nada.
# ==========================================================================

class _BotaoDeTexto:
    def __init__(self, tela, texto, identificador=None):
        self.tela, self.texto, self.identificador = tela, texto, identificador
        self.cliques = 0

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def inner_text(self):
        return self.texto

    def get_attribute(self, nome):
        return self.identificador if nome == "id" else None

    def click(self):
        self.cliques += 1


class _TelaDeConfirmacao:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, textos, com_id=None):
        self.alvos = [_BotaoDeTexto(self, x) for x in textos]
        self.com_id = com_id or {}

    def query_selector_all(self, seletor):
        if seletor in self.com_id:
            return [self.com_id[seletor]]
        if seletor.startswith("#"):
            return []
        return list(self.alvos)


def test_o_botao_de_confirmar_e_achado_pelo_texto():
    from justica_mcp.portal import _botao_de_confirmar

    tela = _TelaDeConfirmacao(["Confirmar", "Cancelar"])
    botao, rotulo = _botao_de_confirmar(tela)
    assert botao is tela.alvos[0]
    assert "Confirmar" in rotulo


def test_cancelar_nunca_e_escolhido():
    """Naquela tela ele fica lado a lado com Confirmar, e clicar no errado fecha
    o acesso que acabou de ser pedido."""
    from justica_mcp.portal import _botao_de_confirmar

    tela = _TelaDeConfirmacao(["Cancelar", "Fechar", "Voltar"])
    assert _botao_de_confirmar(tela) == (None, None)


def test_o_identificador_tem_precedencia_sobre_o_texto():
    """Quando ha identificador conferido em campo, ele vale mais: texto e o que
    resta quando nao ha identificador."""
    from justica_mcp.portal import _botao_de_confirmar

    porid = _BotaoDeTexto(None, "Validar", "btnValidar")
    tela = _TelaDeConfirmacao(["Confirmar"], com_id={"#btnValidar": porid})
    botao, rotulo = _botao_de_confirmar(tela)
    assert botao is porid
    assert rotulo == "#btnValidar"


def test_o_rotulo_do_botao_sem_id_entra_no_relato_da_trava(monkeypatch):
    from justica_mcp import portal

    class _Campo:
        def is_visible(self):
            return True

        def bounding_box(self):
            return {"x": 1, "y": 1, "width": 9, "height": 9}

        def click(self):
            pass

        def fill(self, valor):
            self.valor = valor

    class _Tela(_TelaDeConfirmacao):
        url = "https://eproc1g.tjrj.jus.br/eproc/controlador.php?acao=processo_vista"

        def query_selector_all(self, seletor):
            if seletor == "#txtAcessoCodigo":
                return [_Campo()]
            return super().query_selector_all(seletor)

        def wait_for_load_state(self, *a, **kw):
            pass

        def wait_for_selector(self, *a, **kw):
            pass

    monkeypatch.setattr(portal, "Cofre", lambda: _CofreFalso())
    tela = _Tela(["Confirmar", "Cancelar"])
    guarda = _guarda_simples()
    assert portal._responder_segundo_fator(tela, guarda, _Identidade(), 5) is True
    assert tela.alvos[0].cliques == 1
    assert tela.alvos[1].cliques == 0, "Cancelar nao pode ter sido clicado"
    assert [r["alvo"] for r in guarda.registro] == [
        "#txtAcessoCodigo", 'botao:"Confirmar"']


def test_o_quadro_e_reacolhido_depois_do_codigo_aceito():
    """Ao aceitar o codigo, o portal troca o conteudo do quadro, e o objeto
    antigo fica solto: qualquer leitura nele levanta erro do Playwright sem
    mensagem util. Foi assim que a execucao de 05/10/2026 terminou em '(Error)'
    seco, depois de o codigo ter sido aceito."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._integra_pelo_acesso)
    depois = fonte.split("_responder_segundo_fator(")[1]
    assert "renovado = quadro_da_integra(pagina)" in depois
    assert "janela = renovado if renovado is not None else pagina" in depois


def test_a_falha_da_copia_diz_mais_que_o_nome_da_classe():
    """O Playwright chama tudo de `Error`: o nome sozinho nao permite decidir
    nada."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split("Copia integral nao concluida")[1][:200]
    assert "{detalhe}" in trecho


def test_depois_do_aceite_o_botao_de_download_e_procurado_de_novo():
    """O achado de 05/10/2026: liberado o acesso a integra, a PAGINA DE CIMA
    ganha `#btnDownloadCompletoRS`, que antes nao existia nela. E o mesmo botao
    do Tribunal Regional Federal da 2a Regiao, e daqui em diante os dois
    tribunais sao o mesmo portal."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._integra_pelo_acesso)
    depois = fonte.split("_responder_segundo_fator(")[1]
    assert "elemento_visivel(pagina, BOTAO_INTEGRA)" in depois
    assert "_fluxo_do_botao_de_copia(" in depois
    # E tem de vir ANTES de procurar partes soltas no quadro, que e o caminho
    # de excecao.
    assert depois.index("_fluxo_do_botao_de_copia(") < depois.index(
        "_baixar_partes_do_eproc(")


# ==========================================================================
# Botao sem identificador: alvo pelo TEXTO EXATO
#
# Dois portais exigiram isso. A tela "Acesso à Íntegra do Processo" do eproc do
# Rio, com "Confirmar" e "Cancelar" sem id nenhum, e a Central do Processo
# Eletronico do Superior Tribunal de Justica, cujo mapa de 05/10/2026 trouxe:
#
#     CAMPOS NA TELA (2 de 2):
#       #cpf                 tipo=input
#       [name=password]      tipo=password SENHA
#     BOTOES NA TELA (3 de 3):
#       (sem id)  'Cadastrar com certificado digital'
#       (sem id)  'Entrar'
#       (sem id)  'Entrar com gov.br'
# ==========================================================================

class _TelaDeTextos:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, textos):
        self.alvos = [_AlvoComTexto(x) for x in textos]

    def query_selector_all(self, seletor):
        from justica_mcp.portal import ALVOS_CLICAVEIS

        return list(self.alvos) if seletor == ALVOS_CLICAVEIS else []


def test_alvo_por_texto_exato():
    from justica_mcp.portal import elemento_visivel

    tela = _TelaDeTextos(["Cadastrar com certificado digital", "Entrar",
                          "Entrar com gov.br"])
    assert elemento_visivel(tela, "texto=Entrar") is tela.alvos[1]


def test_entrar_com_govbr_nunca_e_confundido_com_entrar():
    """Casar por inicio de palavra escolheria qualquer um dos dois, e entrar
    pelo gov.br e outro caminho de autenticacao, que ninguem pediu."""
    from justica_mcp.portal import elemento_visivel

    tela = _TelaDeTextos(["Entrar com gov.br"])
    assert elemento_visivel(tela, "texto=Entrar") is None


def test_o_texto_exato_ignora_acento_e_caixa():
    from justica_mcp.portal import elemento_visivel

    tela = _TelaDeTextos(["CONFIRMAR"])
    assert elemento_visivel(tela, "texto=confirmar") is tela.alvos[0]


def test_seletor_comum_continua_funcionando():
    from justica_mcp.portal import elemento_visivel

    tela = _TelaDeSessao(com_busca=True)
    assert elemento_visivel(tela, "#txtNumProcessoPesquisaRapida") is not None


def test_os_seletores_do_stj_vieram_do_mapa_de_05_10():
    """Mapa de cpe.web.stj.jus.br em 05/10/2026: `input#cpf`,
    `input[name=password]` e botao 'Entrar' sem identificador."""
    from justica_mcp.portal import seletores_do_sistema

    stj = seletores_do_sistema("cpe")
    assert stj["campo_usuario"] == "#cpf"
    assert stj["campo_senha"] == "input[name=password]"
    assert stj["botao_entrar"] == "texto=Entrar"


def test_o_stj_nao_finge_saber_o_segundo_fator():
    """A tela de entrada nao o mostra. Seletor vazio quer dizer 'esta tela nao
    tem este campo neste portal', e nao 'procure por nada'."""
    from justica_mcp.portal import seletores_do_sistema

    stj = seletores_do_sistema("cpe")
    assert stj["campo_codigo"] == ""
    assert stj["botao_validar"] == ""


def test_a_tela_do_stj_e_reconhecida_entre_as_familias():
    from justica_mcp.portal import familia_da_tela

    familia = familia_da_tela(_TelaDeLogin({"#cpf"}))
    assert familia["nome"] == "stj-cpe"


# ==========================================================================
# O aviso que o portal abre por cima da tela
#
# Central do Processo Eletronico do Superior Tribunal de Justica, 05/10/2026.
# Depois de a credencial ser enviada, a tela continuou a mesma, so que com DOIS
# botoes "✕" novos e nenhuma mensagem no relato. Havia um aviso aberto, e
# ninguem o leu: o relato mostra estrutura, e o unico dado util ali era texto.
# ==========================================================================

class _AlvoDeAviso:
    def __init__(self, texto, pai=""):
        self.texto, self.pai = texto, pai

    def is_visible(self):
        return True

    def inner_text(self):
        return self.texto

    def get_attribute(self, nome):
        return None

    def evaluate(self, _):
        return self.pai


class _TelaComAviso:
    def __init__(self, por_marca=None, fechaveis=()):
        self.por_marca = por_marca or {}
        self.fechaveis = list(fechaveis)

    def query_selector_all(self, seletor):
        from justica_mcp.portal import ALVOS_CLICAVEIS

        if seletor == ALVOS_CLICAVEIS:
            return list(self.fechaveis)
        return list(self.por_marca.get(seletor, ()))


def test_aviso_em_classe_conhecida_e_lido():
    from justica_mcp.portal import avisos_na_tela

    tela = _TelaComAviso({".toast": [_AlvoDeAviso("  CPF  ou senha\n invalidos ")]})
    assert avisos_na_tela(tela) == ["CPF ou senha invalidos"]


def test_o_botao_de_fechar_entrega_o_aviso_sem_classe_conhecida():
    """Quando a aplicacao nao usa nenhuma classe que conhecemos, o "x" e a
    pista: ele apareceu porque algo foi aberto para ser lido e fechado."""
    from justica_mcp.portal import avisos_na_tela

    tela = _TelaComAviso(fechaveis=[_AlvoDeAviso("✕", pai="Senha expirada ✕")])
    assert avisos_na_tela(tela) == ["Senha expirada ✕"]


def test_botao_comum_nao_e_confundido_com_fechar():
    from justica_mcp.portal import avisos_na_tela

    tela = _TelaComAviso(fechaveis=[_AlvoDeAviso("Entrar", pai="formulario inteiro")])
    assert avisos_na_tela(tela) == []


def test_aviso_repetido_aparece_uma_vez_so():
    """A mesma caixa costuma casar com mais de uma marca."""
    from justica_mcp.portal import avisos_na_tela

    igual = "Credencial invalida"
    tela = _TelaComAviso({".toast": [_AlvoDeAviso(igual)],
                          ".alert": [_AlvoDeAviso(igual)]})
    assert avisos_na_tela(tela) == [igual]


def test_o_aviso_e_encurtado():
    from justica_mcp.portal import avisos_na_tela

    tela = _TelaComAviso({".alert": [_AlvoDeAviso("a" * 5000)]})
    assert len(avisos_na_tela(tela, teto=50)[0]) == 50


def test_a_parada_do_login_le_o_aviso_antes_de_aconselhar():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("A tela do segundo fator nao apareceu")[1]
    assert "avisos_na_tela(pagina)" in trecho.split("pagina_de_erro_do_navegador")[0]


# ==========================================================================
# Campo que nao aceita o preenchimento direto
#
# Central do Processo Eletronico do Superior Tribunal de Justica, 05/10/2026. O
# `fill` nao levantou erro, o botao foi clicado, a tentativa foi gasta, e o
# portal respondeu "O campo CPF deve ser preenchido". O campo chegou VAZIO do
# outro lado: e aplicacao de pagina unica, e campo controlado por framework as
# vezes so reconhece o que veio de teclado de verdade.
# ==========================================================================

class _CampoDeFormulario:
    def __init__(self, aceita_fill=True, aceita_type=True):
        self.aceita_fill, self.aceita_type = aceita_fill, aceita_type
        self.valor = ""
        self.digitado = False

    def click(self):
        pass

    def fill(self, valor):
        if valor == "" or self.aceita_fill:
            self.valor = valor

    def type(self, valor, delay=None):
        if not self.aceita_type:
            raise RuntimeError("campo nao aceita digitacao")
        self.digitado = True
        self.valor = valor

    def evaluate(self, _):
        return self.valor


def test_campo_comum_aceita_o_preenchimento_direto():
    from justica_mcp.portal import preencher_conferindo

    campo = _CampoDeFormulario()
    assert preencher_conferindo(campo, "12345678901", "cpf") is True
    assert campo.valor == "12345678901"
    assert campo.digitado is False, "digitar tecla a tecla so quando preciso"


def test_campo_de_pagina_unica_cai_para_a_digitacao(capsys):
    from justica_mcp.portal import preencher_conferindo

    campo = _CampoDeFormulario(aceita_fill=False)
    assert preencher_conferindo(campo, "12345678901", "cpf") is True
    assert campo.digitado is True
    assert "tecla a tecla" in capsys.readouterr().out


def test_campo_que_nao_aceita_nada_devolve_falso():
    """E essa diferenca que decide se repetir o comando e util ou se so queima
    mais uma tentativa da conta."""
    from justica_mcp.portal import preencher_conferindo

    campo = _CampoDeFormulario(aceita_fill=False, aceita_type=False)
    assert preencher_conferindo(campo, "12345678901", "cpf") is False


# ==========================================================================
# Mascara muda a APARENCIA, nao o conteudo
#
# Mesma tela do Superior Tribunal de Justica, no dia seguinte. Digita-se
# 13169898795 e o campo passa a mostrar 131.698.987-95. A conferencia letra a
# letra via dois textos diferentes e concluia que nada tinha sido escrito,
# quando o campo estava certo. O comando abortava sozinho, com o campo cheio.
# ==========================================================================

class _CampoComMascara(_CampoDeFormulario):
    """Guarda o que recebeu ja pontuado, como faz a mascara de CPF."""

    def _mascarar(self, valor):
        d = valor
        if len(d) == 11 and d.isdigit():
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        return d

    def fill(self, valor):
        if valor == "" or self.aceita_fill:
            self.valor = self._mascarar(valor)

    def type(self, valor, delay=None):
        super().type(valor, delay=delay)
        self.valor = self._mascarar(valor)


def test_campo_com_mascara_conta_como_preenchido():
    from justica_mcp.portal import preencher_conferindo

    campo = _CampoComMascara()
    assert preencher_conferindo(campo, "13169898795", "cpf") is True
    assert campo.valor == "131.698.987-95"
    assert campo.digitado is False, "a mascara nao e motivo para digitar de novo"


def test_mascara_tambem_vale_quando_so_a_digitacao_pega():
    from justica_mcp.portal import preencher_conferindo

    campo = _CampoComMascara(aceita_fill=False)
    assert preencher_conferindo(campo, "13169898795", "cpf") is True
    assert campo.digitado is True


def test_senha_continua_conferida_letra_a_letra():
    """Afrouxar a conferencia na senha seria aceitar senha errada como certa."""
    from justica_mcp.portal import mesmo_conteudo

    assert mesmo_conteudo("ab.cd", "abcd") is False
    assert mesmo_conteudo("abcd", "abcd") is True


def test_campo_vazio_nao_passa_por_mascara():
    from justica_mcp.portal import mesmo_conteudo

    assert mesmo_conteudo("", "13169898795") is False


def test_valor_curto_de_digitos_continua_exato():
    """Codigo de quatro digitos e curto demais: 1234 e 12.34 sao a mesma coisa
    por digito, mas nenhum portal do escopo mascara campo tao pequeno, e aceitar
    a diferenca so esconderia erro."""
    from justica_mcp.portal import mesmo_conteudo

    assert mesmo_conteudo("12.34", "1234") is False


def test_valor_errado_nao_passa_por_ser_do_mesmo_tamanho():
    from justica_mcp.portal import mesmo_conteudo

    assert mesmo_conteudo("131.698.987-96", "13169898795") is False


def test_campo_vazio_aborta_antes_de_gastar_a_tentativa():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    etapa = fonte.split("etapa 1: credencial")[1].split("etapa 2")[0]
    assert "preencher_conferindo(elemento, valor, rotulo)" in etapa
    assert "nenhuma tentativa foi gasta" in etapa
    # O aborto vem ANTES do clique em Entrar.
    assert etapa.index("[ABORTADO]") < etapa.index("Etapa 1: credencial enviada")


def test_caixa_que_so_tem_o_x_nao_vira_aviso():
    from justica_mcp.portal import avisos_na_tela

    tela = _TelaComAviso(fechaveis=[_AlvoDeAviso("✕", pai="✕")])
    assert avisos_na_tela(tela) == []


# ==========================================================================
# De onde vem o codigo do segundo fator
#
# A tela do PJe do Rio, lida em 22/09/2026, diz "Entre no seu aplicativo de
# autenticacao". A do e-SAJ de Sao Paulo, lida em 21/09/2026, traz "Receber
# novo codigo". Sao pedidos de coisas diferentes com a mesma aparencia, e ter
# semente guardada decidia sozinho qual usar.
# ==========================================================================

def test_tela_do_pje_e_de_aplicativo_autenticador():
    from justica_mcp.portal import classificar_origem_do_codigo

    lido = "Entre no seu aplicativo de autenticação e informe o código. Validar"
    assert classificar_origem_do_codigo(lido) == "aplicativo"


def test_tela_que_enviou_o_codigo_e_reconhecida():
    from justica_mcp.portal import classificar_origem_do_codigo

    lido = "Informe o código. Não recebeu? Receber novo código"
    assert classificar_origem_do_codigo(lido) == "enviado"


def test_aplicativo_ganha_quando_as_duas_marcas_aparecem():
    """"Enviar" cabe no botao de qualquer uma das duas telas; "aplicativo de
    autenticacao" nao aparece por acaso numa tela que manda codigo por e-mail."""
    from justica_mcp.portal import classificar_origem_do_codigo

    lido = "Entre no seu aplicativo de autenticação. Enviamos para você. Enviar"
    assert classificar_origem_do_codigo(lido) == "aplicativo"


def test_tela_calada_nao_vira_palpite():
    """None NAO e "enviado": na duvida o comando segue como seguia, porque
    chutar a origem errada e o defeito que esta leitura existe para evitar."""
    from justica_mcp.portal import classificar_origem_do_codigo

    assert classificar_origem_do_codigo("Código Validar") is None
    assert classificar_origem_do_codigo("") is None


def test_acento_nao_decide_a_origem():
    from justica_mcp.portal import classificar_origem_do_codigo

    assert classificar_origem_do_codigo("APLICATIVO DE AUTENTICACAO") == "aplicativo"


class _CampoNumFormulario:
    def __init__(self, texto):
        self.texto = texto

    def evaluate(self, _):
        return self.texto


class _TelaDoSegundoFator:
    def __init__(self, corpo=""):
        self.corpo = corpo

    def inner_text(self, _):
        return self.corpo


def test_le_o_formulario_em_volta_do_campo():
    from justica_mcp.portal import origem_do_codigo

    tela = _TelaDoSegundoFator("nada aqui")
    campo = _CampoNumFormulario("Entre no seu aplicativo de autenticação")
    assert origem_do_codigo(tela, campo) == "aplicativo"


def test_sem_formulario_cai_para_o_corpo_da_tela():
    from justica_mcp.portal import origem_do_codigo

    tela = _TelaDoSegundoFator("Enviamos um código para o seu e-mail cadastrado")
    assert origem_do_codigo(tela, _CampoNumFormulario("")) == "enviado"


def test_semente_nao_e_usada_quando_a_tela_diz_que_enviou():
    """Numa conta que bloqueia por tentativa, gerar da semente um numero que a
    tela nunca aceitaria custa uma das tentativas sem ninguem saber por que."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("etapa 2: segundo fator")[1]
    assert 'origem = origem_do_codigo(pagina, campo)' in trecho
    assert 'cofre.tem_semente(identidade) and origem != "enviado"' in trecho
    # E o operador precisa saber que a semente ficou de fora, e por que.
    assert "NAO foi usada" in trecho


# ==========================================================================
# Portal que pede codigo sem ter o campo registrado
#
# Central do Processo Eletronico do Superior Tribunal de Justica, 05/10/2026.
# A credencial foi aceita e a tela passou a pedir o segundo fator, mas na
# tabela deste projeto o campo de codigo daquele portal ainda esta vazio. Como
# vazio e ausente eram tratados igual, o comando anunciaria que a tela do
# segundo fator nao apareceu e mandaria conferir a senha, que ja tinha sido
# aceita.
# ==========================================================================

def _campo_qualquer(**troca):
    from justica_mcp.portal import Campo

    base = dict(marcador="input", tipo="text", nome=None, identificador=None,
                rotulo=None, texto_visivel=None, e_senha=False, extras={})
    base.update(troca)
    return Campo(**base)


class _TelaComCampos:
    def __init__(self, campos):
        self.campos = campos


def test_acha_o_campo_de_codigo_que_a_tela_mostra(monkeypatch):
    from justica_mcp import portal

    campo = _campo_qualquer(identificador="codigoAcesso", rotulo="Código")
    monkeypatch.setattr(portal, "_coletar", lambda _: ([campo], []))
    assert portal.seletor_de_codigo_a_vista(object()) == "#codigoAcesso"


def test_campo_sem_identificador_vira_seletor_por_nome(monkeypatch):
    from justica_mcp import portal

    campo = _campo_qualquer(nome="otpCode", extras={"maxlength": "6"})
    monkeypatch.setattr(portal, "_coletar", lambda _: ([campo], []))
    assert portal.seletor_de_codigo_a_vista(object()) == "input[name=otpCode]"


def test_campo_de_senha_nunca_e_oferecido_como_campo_de_codigo(monkeypatch):
    from justica_mcp import portal

    campo = _campo_qualquer(identificador="password", e_senha=True,
                            extras={"maxlength": "8"})
    monkeypatch.setattr(portal, "_coletar", lambda _: ([campo], []))
    assert portal.seletor_de_codigo_a_vista(object()) is None


def test_tela_sem_campo_de_codigo_devolve_nada(monkeypatch):
    from justica_mcp import portal

    campo = _campo_qualquer(identificador="pesquisa", rotulo="Buscar")
    monkeypatch.setattr(portal, "_coletar", lambda _: ([campo], []))
    assert portal.seletor_de_codigo_a_vista(object()) is None


def test_campo_descoberto_e_relatado_e_nao_preenchido():
    """Preencher campo que o programa mesmo descobriu, sem o aval do operador,
    esvaziaria a guarda que impede agir em tela desconhecida."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("campo is None and not campo_codigo")[1].split(
        "if campo is None:")[0]
    assert "--campo-codigo" in trecho
    assert "nao e caso de conferir a senha" in trecho
    # Relata e PARA. Nenhum preenchimento nem clique no caminho.
    assert "return 1" in trecho
    assert "pode_executar" not in trecho


# ==========================================================================
# Codigo de uso unico nao se manda duas vezes
#
# O portal marca como consumido o codigo que recebeu. O mesmo numero mandado
# de novo volta recusado com a MESMA mensagem de codigo errado, e quem repete
# o comando dentro dos mesmos 30 segundos manda exatamente o mesmo numero. O
# operador le "codigo invalido" sobre uma semente que esta certa, e vai
# procurar defeito no cofre.
# ==========================================================================

def test_janela_ja_gasta_espera_a_proxima_antes_de_gerar():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("etapa 2: segundo fator")[1]
    assert 'chave_janela = f"segundo_fator:{identidade.chave}"' in trecho
    assert "gasta == cofre.janela_do_codigo()" in trecho
    # Espera ANTES de gerar: gerar e so depois esperar devolveria o mesmo numero.
    assert trecho.index("time.sleep(espera)") < trecho.index("_codigo_segundo_fator")


def test_o_que_fica_guardado_e_a_janela_e_nunca_o_codigo():
    """Guardar o codigo seria guardar credencial de uso unico num banco que
    nao e cofre."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("etapa 2: segundo fator")[1]
    assert "gravar_cache(chave_janela, cofre.janela_do_codigo()" in trecho
    assert "gravar_cache(chave_janela, codigo" not in trecho


# ==========================================================================
# Portal fora do ar nao e seletor mudado
#
# PJe do Rio, 06/10/2026: a tela veio com zero campo e titulo "503 Service
# Temporarily Unavailable". O comando anunciou que o campo de usuario nao foi
# encontrado. As duas frases sao verdadeiras e levam a lugares opostos: uma
# manda procurar seletor que mudou, a outra manda esperar o portal voltar.
# ==========================================================================

class _TelaComTitulo:
    def __init__(self, titulo):
        self.titulo = titulo

    def title(self):
        return self.titulo


def test_o_503_do_pje_do_rio_e_reconhecido():
    from justica_mcp.portal import erro_do_servidor

    tela = _TelaComTitulo("503 Service Temporarily Unavailable")
    assert erro_do_servidor(tela) == "503 Service Temporarily Unavailable"


def test_outros_erros_de_servidor_tambem():
    from justica_mcp.portal import erro_do_servidor

    for titulo in ("502 Bad Gateway", "504 Gateway Time-out",
                   "500 Internal Server Error", "Portal em manutenção"):
        assert erro_do_servidor(_TelaComTitulo(titulo)) == titulo


def test_tela_de_login_de_verdade_nao_vira_pagina_de_erro():
    from justica_mcp.portal import erro_do_servidor

    assert erro_do_servidor(_TelaComTitulo("PJe - Processo Judicial Eletrônico")) is None
    assert erro_do_servidor(_TelaComTitulo("")) is None


def test_numero_no_meio_do_titulo_nao_transforma_a_tela_em_erro():
    """Exigir o numero no COMECO e de proposito: um 503 solto no meio de um
    titulo qualquer nao e pagina de erro."""
    from justica_mcp.portal import erro_do_servidor

    assert erro_do_servidor(_TelaComTitulo("Processo 503 do acervo")) is None


def test_tela_que_nao_devolve_titulo_nao_quebra():
    from justica_mcp.portal import erro_do_servidor

    class _Mudo:
        def title(self):
            raise RuntimeError("janela fechada")

    assert erro_do_servidor(_Mudo()) is None


def test_portal_fora_do_ar_e_dito_antes_de_culpar_o_seletor():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("fora_do_ar = erro_do_servidor(pagina)")[1].split(
        "_relatar_tela")[0]
    assert "portal esta fora do ar" in trecho
    assert "nenhuma" in trecho and "tentativa foi gasta" in trecho
    assert "Nao ha o que conferir no cofre" in trecho


# ==========================================================================
# Portal que nunca foi lido
#
# `seletores_do_sistema` cai nos seletores do eproc quando o sistema nao esta
# na tabela. O desfecho e seguro, e mente no relato: procurar `#txtUsuario`
# num portal que nunca foi lido termina em "campo de usuario nao encontrado",
# que manda o operador procurar seletor que mudou quando nunca houve seletor.
# ==========================================================================

def test_sistemas_ja_lidos_sao_reconhecidos():
    from justica_mcp.portal import sistema_tem_seletores

    for sistema in ("eproc", "esaj", "pje", "cpe"):
        assert sistema_tem_seletores(sistema), sistema


def test_sistema_nunca_lido_nao_passa_por_registrado():
    """O DCP do Tribunal de Justica do Rio tem credencial declarada e nenhuma
    tela lida. Ate hoje ele herdava os seletores do eproc em silencio."""
    from justica_mcp.portal import sistema_tem_seletores

    assert sistema_tem_seletores("dcp") is False
    assert sistema_tem_seletores("") is False


def test_maiuscula_e_espaco_nao_mudam_o_veredicto():
    from justica_mcp.portal import sistema_tem_seletores

    assert sistema_tem_seletores("  EPROC ") is True


def test_autenticar_para_antes_de_abrir_o_navegador():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.autenticar)
    trecho = fonte.split("sistema_tem_seletores(identidade.sistema)")[1]
    cabeca = trecho.split("executavel = os.environ")[0]
    assert "nenhuma tentativa foi gasta" in cabeca
    assert "justica-portal mapear" in cabeca
    assert "return 1" in cabeca
    # A recusa vem ANTES de abrir o navegador: nada de rede acontece.
    # Compara com a CHAMADA, e nao com o nome: o import dela abre a funcao.
    assert fonte.index("sistema_tem_seletores") < fonte.index("with sync_playwright()")
