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
    assert "Nada foi enviado" in capsys.readouterr().out


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
    assert "Nada foi enviado" in capsys.readouterr().out
