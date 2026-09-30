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


# ==========================================================================
# Consulta autenticada
#
# O caminho foi fotografado pelo operador em 30/09/2026. As fotos provam tres
# coisas, e sao elas que estes testes guardam: o numero vai em SEIS campos, o
# clique no numero levanta um aviso de responsabilidade em caixa do proprio
# navegador, e os autos abrem em ABA NOVA.
#
# O que as fotos NAO mostram: os identificadores dos campos. Por isso nenhum
# esta escrito no codigo, e os testes abaixo exercitam a busca pela forma.
# ==========================================================================

from justica_mcp.pje import (  # noqa: E402
    SELETOR_CANDIDATO_DO_NUMERO, TAMANHOS_DAS_PARTES, abrir_processo,
    achar_botao_pesquisar, achar_link_do_processo, buscar_autenticado,
    campos_do_numero, conferir_forma_dos_campos,
    endereco_da_consulta_autenticada, ler_aviso,
    parece_aviso_de_responsabilidade, partes_do_numero,
)

# Texto do aviso que o portal do Rio mostrou em 30/09/2026, resumido ao que
# importa para o reconhecimento. Nao e conteudo de processo.
AVISO_REAL = (
    "O acesso aos autos de processo em que nao atua sera registrado e podera "
    "ensejar responsabilizacao civil, administrativa e criminal, nos termos da "
    "Resolucao nº. 121 do Conselho Nacional de Justica."
)


class _AutCampo:
    """Um dos seis campos do numero."""

    def __init__(self, pagina, identificador, maxlength=None, visivel=True,
                 tipo="text", readonly=None, disabled=None, engole=False):
        self.pagina = pagina
        self.atributos = {"id": identificador, "type": tipo,
                          "maxlength": maxlength, "readonly": readonly,
                          "disabled": disabled}
        self.visivel = visivel
        self.engole = engole
        self.valor = ""

    def get_attribute(self, nome):
        return self.atributos.get(nome)

    def is_visible(self):
        return self.visivel

    def click(self):
        self.pagina.cliques.append(self.atributos["id"])

    def fill(self, valor):
        if not self.engole:
            self.valor = valor
        self.pagina.preenchidos[self.atributos["id"]] = self.valor

    def evaluate(self, _):
        return "".join(c for c in self.valor if c.isdigit())


class _AutBotao:
    def __init__(self, pagina, identificador, rotulo, visivel=True):
        self.pagina, self.rotulo, self.visivel = pagina, rotulo, visivel
        self.identificador = identificador

    def get_attribute(self, nome):
        return {"id": self.identificador, "value": self.rotulo}.get(nome)

    def is_visible(self):
        return self.visivel

    def inner_text(self):
        return self.rotulo

    def click(self):
        self.pagina.cliques.append(self.identificador)


LOGIN_AUT = "https://tjrj.pje.jus.br/1g/login.seam"
TELA_AUT = "https://tjrj.pje.jus.br/1g/Processo/ConsultaProcesso/listView.seam"


class _AutTela:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, campos=None, botao=True, engole=False, destino=None):
        self.url = TELA_AUT
        self.destino = destino
        self.cliques = []
        self.preenchidos = {}
        self.navegou = []
        self.campos = campos if campos is not None else [
            _AutCampo(self, f"f:parte{i}", maxlength=str(t), engole=engole)
            for i, t in enumerate(TAMANHOS_DAS_PARTES, 1)
        ]
        self.botao = _AutBotao(self, "f:pesquisar", "Pesquisar") if botao else None

    def goto(self, url, **kw):
        self.navegou.append(url)
        self.url = self.destino or url

    def query_selector_all(self, seletor):
        if seletor == SELETOR_CANDIDATO_DO_NUMERO:
            return list(self.campos)
        if seletor == "input[type=submit], button":
            return [self.botao] if self.botao else []
        return []

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


PARTES_ESPERADAS = ("0809090", "88", "2023", "8", "19", "0001")


# ---------------- o endereco e as partes ----------------

def test_o_endereco_da_consulta_autenticada_vem_do_login():
    assert endereco_da_consulta_autenticada(LOGIN_AUT) == TELA_AUT


def test_o_numero_vira_seis_partes_na_ordem_da_tela():
    assert partes_do_numero(parse_numero(PROCESSO)) == PARTES_ESPERADAS


# ---------------- a forma dos seis campos ----------------

def test_campo_escondido_desligado_ou_so_leitura_nao_conta():
    """Digitar em campo oculto nao levanta erro: simplesmente nao acontece
    nada, e a busca volta vazia como se o processo nao existisse."""
    tela = _AutTela(campos=[])
    tela.campos = [
        _AutCampo(tela, "visivel"),
        _AutCampo(tela, "oculto", tipo="hidden"),
        _AutCampo(tela, "invisivel", visivel=False),
        _AutCampo(tela, "so-leitura", readonly="readonly"),
        _AutCampo(tela, "desligado", disabled="disabled"),
    ]
    assert [c.get_attribute("id") for c in campos_do_numero(tela)] == ["visivel"]


def test_tela_com_outro_numero_de_campos_para_antes_de_digitar():
    tela = _AutTela()
    tela.campos = tela.campos[:5]
    with pytest.raises(ConsultaPJeIndisponivel, match="5 campo"):
        buscar_autenticado(tela, _guarda(), parse_numero(PROCESSO), LOGIN_AUT, 10)
    assert tela.preenchidos == {}


def test_campos_fora_de_ordem_sao_recusados_pelo_tamanho_declarado():
    """Campo na ordem trocada aceita o que se digita e a busca volta 'nada
    encontrado'. O advogado leria isso como processo inexistente."""
    tela = _AutTela()
    tela.campos[0], tela.campos[2] = tela.campos[2], tela.campos[0]
    with pytest.raises(ConsultaPJeIndisponivel, match="ordem dos campos"):
        conferir_forma_dos_campos(tela.campos)


def test_tela_sem_tamanho_declarado_passa_pela_conferencia():
    """Ausencia de maxlength nao e prova de tela errada: a conferencia de
    verdade e o numero remontado depois de digitado."""
    tela = _AutTela(campos=[])
    tela.campos = [_AutCampo(tela, f"f:p{i}") for i in range(6)]
    conferir_forma_dos_campos(tela.campos)


# ---------------- a busca ----------------

def test_a_busca_autenticada_preenche_as_seis_partes_e_pesquisa():
    tela = _AutTela()
    guarda = _guarda()
    buscar_autenticado(tela, guarda, parse_numero(PROCESSO), LOGIN_AUT, 10)

    assert tela.navegou == [TELA_AUT]
    assert tuple(tela.preenchidos.values()) == PARTES_ESPERADAS
    assert tela.cliques[-1] == "f:pesquisar"
    assert [r["acao"] for r in guarda.registro].count("preencher") == 6


def test_numero_que_nao_entrou_inteiro_nao_vira_pesquisa():
    tela = _AutTela(engole=True)
    with pytest.raises(ConsultaPJeIndisponivel, match="nao confere"):
        buscar_autenticado(tela, _guarda(), parse_numero(PROCESSO), LOGIN_AUT, 10)
    assert "f:pesquisar" not in tela.cliques


def test_tela_sem_botao_de_pesquisar_nao_digita_nada():
    tela = _AutTela(botao=False)
    with pytest.raises(ConsultaPJeIndisponivel, match="pesquisar"):
        buscar_autenticado(tela, _guarda(), parse_numero(PROCESSO), LOGIN_AUT, 10)
    assert tela.preenchidos == {}


def test_a_consulta_autenticada_recusa_ir_parar_em_outra_tela():
    tela = _AutTela(destino="https://tjrj.pje.jus.br/1g/login.seam")
    with pytest.raises(ConsultaPJeIndisponivel, match="outra tela"):
        buscar_autenticado(tela, _guarda(), parse_numero(PROCESSO), LOGIN_AUT, 10)
    assert tela.preenchidos == {}


def test_o_botao_e_achado_pelo_que_esta_escrito_nele():
    tela = _AutTela()
    assert achar_botao_pesquisar(tela) is tela.botao
    tela.botao = _AutBotao(tela, "f:limpar", "Limpar")
    assert achar_botao_pesquisar(tela) is None


# ---------------- o link, o aviso e a aba nova ----------------

class _AutLink:
    def __init__(self, pagina, texto):
        self.pagina, self.texto = pagina, texto

    def inner_text(self):
        return self.texto

    def click(self):
        self.pagina.cliques.append("link")
        self.pagina.disparar_aviso()


class _AutDialogo:
    def __init__(self, texto):
        self.message = texto
        self.decisao = None

    def accept(self):
        self.decisao = "aceito"

    def dismiss(self):
        self.decisao = "dispensado"


class _AutContexto:
    def __init__(self, pagina):
        self.pagina = pagina

    def expect_page(self, timeout=None):
        return self.pagina.espera_de_aba()


class _AutResultado:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, textos=None, aviso=AVISO_REAL, abre_aba=True):
        self.url = TELA_AUT
        self.cliques = []
        self.links = [_AutLink(self, t) for t in
                      (textos if textos is not None else [PROCESSO])]
        self.aviso = aviso
        self.abre_aba = abre_aba
        self.ouvintes = []
        self.dialogos = []
        self.context = _AutContexto(self)
        self.aba = None

    def on(self, evento, funcao):
        if evento == "dialog":
            self.ouvintes.append(funcao)

    def disparar_aviso(self):
        if self.aviso is None:
            return
        dialogo = _AutDialogo(self.aviso)
        self.dialogos.append(dialogo)
        for ouvinte in self.ouvintes:
            ouvinte(dialogo)

    def query_selector_all(self, seletor):
        return list(self.links) if seletor == "a" else []

    def wait_for_timeout(self, *a):
        pass

    def espera_de_aba(resultado):
        class _Espera:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                if not resultado.abre_aba:
                    raise TimeoutError("nenhuma aba abriu")
                return False

            @property
            def value(self):
                resultado.aba = _AutAba()
                return resultado.aba

        return _Espera()


class _AutAba:
    def wait_for_load_state(self, *a, **kw):
        pass


def test_o_link_e_achado_pelos_digitos_do_numero_pedido():
    """Clicar na primeira linha seria clicar no que a tela ofereceu, e nao no
    que se procurou."""
    tela = _AutResultado(textos=["0000001-11.2020.8.19.0001", PROCESSO])
    achado = achar_link_do_processo(tela, parse_numero(PROCESSO))
    assert achado is tela.links[1]


def test_numero_ausente_da_tabela_nao_abre_nada():
    tela = _AutResultado(textos=["0000001-11.2020.8.19.0001"])
    with pytest.raises(ConsultaPJeIndisponivel, match="nao aparece como link"):
        abrir_processo(tela, _guarda(), parse_numero(PROCESSO), aceitar_termo=False)
    assert tela.cliques == []


def test_sem_aceite_o_aviso_e_guardado_e_nada_e_aberto():
    """O Playwright dispensa a caixa sozinho e em silencio. Sem tratar o
    dialogo, o programa decidiria por conta propria uma questao de
    responsabilizacao civil, administrativa e criminal do advogado."""
    tela = _AutResultado()
    aba, avisos = abrir_processo(
        tela, _guarda(), parse_numero(PROCESSO), aceitar_termo=False)

    assert aba is None
    assert avisos == [AVISO_REAL]
    assert tela.dialogos[0].decisao == "dispensado"


def test_com_aceite_do_operador_a_aba_nova_e_devolvida():
    tela = _AutResultado()
    aba, avisos = abrir_processo(
        tela, _guarda(), parse_numero(PROCESSO), aceitar_termo=True)

    assert aba is tela.aba
    assert tela.dialogos[0].decisao == "aceito"
    assert avisos == [AVISO_REAL]


def test_aceite_dado_e_aba_que_nao_abre_vira_falha_explicita():
    tela = _AutResultado(abre_aba=False)
    with pytest.raises(ConsultaPJeIndisponivel, match="nao abriu"):
        abrir_processo(tela, _guarda(), parse_numero(PROCESSO),
                       aceitar_termo=True, segundos=1)


def test_o_aviso_de_responsabilidade_e_reconhecido_pelo_texto():
    assert parece_aviso_de_responsabilidade(AVISO_REAL)
    assert not parece_aviso_de_responsabilidade("Deseja imprimir a lista?")


def test_o_tratador_do_dialogo_nao_deixa_erro_vazar():
    class _Mudo:
        message = property(lambda self: (_ for _ in ()).throw(RuntimeError("morto")))

        def dismiss(self):
            raise RuntimeError("tarde demais")

    class _Pagina:
        def __init__(self):
            self.ouvinte = None

        def on(self, _evento, funcao):
            self.ouvinte = funcao

    pagina, registro = _Pagina(), []
    ler_aviso(pagina, False, registro)
    pagina.ouvinte(_Mudo())
    assert registro == ["(aviso sem texto legivel)"]
