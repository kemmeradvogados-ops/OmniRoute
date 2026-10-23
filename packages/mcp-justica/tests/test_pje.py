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
    SELETOR_CANDIDATO_DO_NUMERO, TAMANHOS_DAS_PARTES, TIPOS_DE_BOTAO,
    abrir_processo,
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
                 tipo="text", readonly=None, disabled=None, engole=False,
                 so_teclado=False):
        self.pagina = pagina
        self.atributos = {"id": identificador, "type": tipo,
                          "maxlength": maxlength, "readonly": readonly,
                          "disabled": disabled}
        self.visivel = visivel
        self.engole = engole
        # Campo que ignora `fill` e so reconhece o que vem de teclado de
        # verdade, porque e a sequencia de eventos de tecla que dispara a
        # atualizacao interna do framework.
        self.so_teclado = so_teclado
        self.valor = ""
        self.digitado = False

    def get_attribute(self, nome):
        return self.atributos.get(nome)

    def is_visible(self):
        return self.visivel

    def click(self):
        self.pagina.cliques.append(self.atributos["id"])

    def fill(self, valor):
        if not self.engole and not (self.so_teclado and valor):
            self.valor = valor
        self.pagina.preenchidos[self.atributos["id"]] = self.valor

    def type(self, valor, delay=None):
        if self.engole:
            return
        self.digitado = True
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

    def evaluate(self, expressao):
        if "tagName" in expressao:
            return "INPUT"
        return None

    def click(self):
        self.pagina.cliques.append(self.identificador)


LOGIN_AUT = "https://tjrj.pje.jus.br/1g/login.seam"
TELA_AUT = "https://tjrj.pje.jus.br/1g/Processo/ConsultaProcesso/listView.seam"


class _AutTela:
    viewport_size = {"width": 1280, "height": 720}

    def __init__(self, campos=None, botao=True, engole=False, destino=None,
                 so_teclado=False):
        self.url = TELA_AUT
        self.destino = destino
        self.cliques = []
        self.preenchidos = {}
        self.navegou = []
        self.campos = campos if campos is not None else [
            _AutCampo(self, f"f:parte{i}", maxlength=str(t), engole=engole,
                      so_teclado=so_teclado)
            for i, t in enumerate(TAMANHOS_DAS_PARTES, 1)
        ]
        self.botao = _AutBotao(self, "f:pesquisar", "Pesquisar") if botao else None

    def goto(self, url, **kw):
        self.navegou.append(url)
        self.url = self.destino or url

    def query_selector(self, seletor):
        """O caminho pelo IDENTIFICADOR conferido, acrescentado em 23/10/2026.

        Este duble devolve None de proposito: os testes que ja existiam cobrem
        a busca POR TEXTO, que continua valendo como segundo caminho quando o
        identificador do JSF mudar de versao. O caminho pelo identificador tem
        teste proprio.
        """
        return None

    def query_selector_all(self, seletor):
        if seletor == SELETOR_CANDIDATO_DO_NUMERO:
            return list(self.campos)
        # Na tela de verdade `input` pega todo campo, inclusive os que o
        # seletor deduzido do numero nao pega. E justamente o que o relato de
        # "nao achei nada" precisa enxergar.
        if seletor == "input":
            return list(self.campos)
        # Pela CONSTANTE, e nao por uma copia escrita a mao. Ate 23/10/2026
        # este duble fixava "input[type=submit], button", que era exatamente a
        # lista incompleta do defeito: o teste passava por fixar o erro.
        if seletor == TIPOS_DE_BOTAO:
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


# ==========================================================================
# O que a tela ensina quando a forma nao bate
#
# `SELETOR_CANDIDATO_DO_NUMERO` foi escrito por deducao, e nao lido em tela
# real. Quando ele nao acha nada, a hipotese mais provavel e que o palpite
# errou. Sem relatar o que a tela tem, cada tentativa frustrada gasta um login
# e nao ensina nada, e o palpite seguinte sai tao no escuro quanto o primeiro.
# ==========================================================================

def test_tela_sem_nenhum_campo_relata_o_que_ela_tem():
    from justica_mcp.pje import campos_de_texto_a_vista

    tela = _AutTela(campos=[])
    tela.campos = [
        _AutCampo(tela, "f:numeroUnico", maxlength="20"),
        _AutCampo(tela, "f:classe"),
    ]
    with pytest.raises(ConsultaPJeIndisponivel) as erro:
        conferir_forma_dos_campos([], tela)
    recado = str(erro.value)
    assert "deduzido e errou o alvo" in recado
    assert "f:numeroUnico" in recado and "maxlength=20" in recado
    assert campos_de_texto_a_vista(tela)[0].startswith("id=f:numeroUnico")


def test_o_relato_da_tela_traz_forma_e_nunca_conteudo():
    """Tela de busca tem campo vazio, e ainda assim a regra vale: o que sai
    daqui e estrutura."""
    from justica_mcp.pje import campos_de_texto_a_vista

    tela = _AutTela(campos=[])
    campo = _AutCampo(tela, "f:parte0", maxlength="7")
    campo.valor = "0809090"
    tela.campos = [campo]
    assert campos_de_texto_a_vista(tela) == ["id=f:parte0 maxlength=7"]


def test_botao_e_campo_oculto_ficam_de_fora_do_relato():
    from justica_mcp.pje import campos_de_texto_a_vista

    tela = _AutTela(campos=[])
    tela.campos = [
        _AutCampo(tela, "f:enviar", tipo="submit"),
        _AutCampo(tela, "f:estado", tipo="hidden"),
        _AutCampo(tela, "f:invisivel", visivel=False),
    ]
    assert campos_de_texto_a_vista(tela) == []


def test_conferencia_sem_a_tela_continua_valendo():
    """A tela e opcional: quem chama so para conferir a forma nao precisa dela,
    e os chamadores antigos nao mudam."""
    with pytest.raises(ConsultaPJeIndisponivel, match="5 campo"):
        conferir_forma_dos_campos(_AutTela().campos[:5])


# ==========================================================================
# Campo que ignora `fill`
#
# Aprendido na Central do Processo Eletronico do Superior Tribunal de Justica,
# em 05/10/2026: campo controlado por framework as vezes so reconhece o que
# veio de teclado de verdade. Aqui desistir no `fill` custa o login inteiro,
# porque a conferencia do numero remontado pararia o comando com a sessao ja
# gasta.
# ==========================================================================

def test_campo_que_so_aceita_teclado_nao_perde_a_busca():
    tela = _AutTela(so_teclado=True)
    buscar_autenticado(tela, _guarda(), parse_numero(PROCESSO), LOGIN_AUT, 10)
    assert tuple(tela.preenchidos.values()) == PARTES_ESPERADAS
    assert all(c.digitado for c in tela.campos)
    assert tela.cliques[-1] == "f:pesquisar"


def test_campo_comum_nao_e_digitado_tecla_a_tecla():
    tela = _AutTela()
    buscar_autenticado(tela, _guarda(), parse_numero(PROCESSO), LOGIN_AUT, 10)
    assert not any(c.digitado for c in tela.campos)


# ==========================================================================
# O BOTAO DE PESQUISAR DA CONSULTA AUTENTICADA
#
# Corrida de 23/10/2026: a autenticacao no PJe do Rio de Janeiro passou,
# login e segundo fator, e o comando parou dizendo que o botao de pesquisar
# nao estava na tela. Ele estava. O relato da propria tela trazia
# `input#fPP:searchProcessos`, e a captura mostrou "PESQUISAR" no fim do
# painel da esquerda, abaixo da dobra.
#
# Duas causas, e as duas foram consertadas:
#
#   - a busca olhava `input[type=submit], button`, e o RichFaces, que desenha
#     o PJe, renderiza botao de comando como `input[type=button]`;
#   - o identificador do JSF nunca tinha sido lido em tela real, e por isso a
#     busca era so por texto. Agora foi lido.
# ==========================================================================


class _BotaoDeMentira:
    def __init__(self, etiqueta="input", identificador=None, valor=None,
                 texto="", tipo=None, rotulo_acessivel=None,
                 onde_fica_o_rotulo="aria-label"):
        self.etiqueta = etiqueta
        self.identificador = identificador
        self.valor = valor
        self.texto = texto
        self.tipo = tipo
        self.rotulo_acessivel = rotulo_acessivel
        # Em `title`, e nao em `aria-label`, e foi exatamente isso que parou a
        # corrida de 23/10/2026: o seletor olhava so `aria-label`.
        self.onde_fica_o_rotulo = onde_fica_o_rotulo

    def get_attribute(self, nome):
        if nome == self.onde_fica_o_rotulo and self.rotulo_acessivel:
            return self.rotulo_acessivel
        return {"id": self.identificador, "value": self.valor,
                "type": self.tipo}.get(nome)

    def inner_text(self):
        return self.texto

    def evaluate(self, expressao):
        if "tagName" in expressao:
            return self.etiqueta.upper()
        return None


class _PaginaDeMentira:
    def __init__(self, botoes, com_identificador=None):
        self.botoes = botoes
        self.com_identificador = com_identificador

    def query_selector(self, seletor):
        return self.com_identificador

    def query_selector_all(self, seletor):
        return self.botoes


def test_acha_pelo_identificador_conferido_em_tela_real():
    from justica_mcp.pje import BOTAO_PESQUISAR_AUTENTICADO, achar_botao_pesquisar

    alvo = _BotaoDeMentira(identificador="fPP:searchProcessos", valor="PESQUISAR")
    pagina = _PaginaDeMentira([], com_identificador=alvo)
    assert achar_botao_pesquisar(pagina) is alvo
    assert "fPP:searchProcessos" in BOTAO_PESQUISAR_AUTENTICADO


def test_acha_input_type_button_que_a_versao_anterior_perdia():
    """RichFaces renderiza botao de comando como `input[type=button]`. A busca
    antiga olhava so `input[type=submit], button`, e era essa a causa."""
    from justica_mcp.pje import TIPOS_DE_BOTAO, achar_botao_pesquisar

    assert "input[type=button]" in TIPOS_DE_BOTAO
    alvo = _BotaoDeMentira(tipo="button", valor="PESQUISAR")
    pagina = _PaginaDeMentira([_BotaoDeMentira(valor="LIMPAR"), alvo])
    assert achar_botao_pesquisar(pagina) is alvo


def test_a_posicao_na_tela_nao_recusa_o_botao():
    """Guarda de fonte. Abaixo da dobra NAO e escondido, e quem decide se da
    para clicar e o proprio Playwright, que rola sozinho. Recusar por posicao
    parou quatro corridas no Portal de Servicos em outubro."""
    import inspect

    from justica_mcp import pje

    fonte = inspect.getsource(pje.achar_botao_pesquisar)
    sem_comentario = "\n".join(
        linha for linha in fonte.splitlines()
        if not linha.strip().startswith(("#", '"', "*")))
    assert "is_visible" not in sem_comentario
    assert "bounding_box" not in sem_comentario


def test_o_seletor_da_trava_casa_com_o_elemento_de_verdade():
    """Montava-se `input[id="..."]` sempre. Para um `<button>` sem id isso
    saia como `input[id="None"]`, que a trava autorizaria sem nomear nada."""
    from justica_mcp.pje import seletor_do_elemento

    com_id = _BotaoDeMentira(etiqueta="input", identificador="fPP:searchProcessos")
    assert seletor_do_elemento(com_id, "pesquisar") == 'input[id="fPP:searchProcessos"]'

    sem_id = _BotaoDeMentira(etiqueta="button")
    saida = seletor_do_elemento(sem_id, "pesquisar")
    assert "None" not in saida
    assert saida.startswith("button")


def test_botao_sem_rotulo_nenhum_nao_e_escolhido():
    """Escolher qualquer botao aqui seria clicar as cegas numa tela que tem
    'LIMPAR' ao lado de 'PESQUISAR'."""
    from justica_mcp.pje import achar_botao_pesquisar

    pagina = _PaginaDeMentira([_BotaoDeMentira(valor="LIMPAR"),
                               _BotaoDeMentira(valor=None, texto="")])
    assert achar_botao_pesquisar(pagina) is None


# ==========================================================================
# A LINHA DO TEMPO DOS AUTOS
#
# Escrita contra a tela real de 23/10/2026, a primeira em que os autos do PJe
# do Rio de Janeiro abriram. Os identificadores de conteiner e de paginacao
# saem dali; os dos ITENS, nao: a tela os traz como
# `divTimeLine:j_id410:0:j_id412:1:j_id423`, e `j_id` e gerado pelo JavaServer
# Faces e muda a cada versao do portal. Ler por eles funcionaria hoje e
# falharia na proxima atualizacao devolvendo ZERO eventos, como se o processo
# nao tivesse nenhum.
# ==========================================================================


class _PaginaComLinhaDoTempo:
    def __init__(self, resposta):
        self.resposta = resposta
        self.url = "https://tjrj.pje.jus.br/1g/Processo/ConsultaProcesso/Detalhe/x.seam"

    def evaluate(self, _js):
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def test_a_data_do_grupo_vira_data_de_verdade():
    from justica_mcp.pje import data_do_grupo

    assert data_do_grupo("15 out 2026") == "2026-10-15"
    assert data_do_grupo("  3 jan 2025 ") == "2025-01-03"
    assert data_do_grupo("outubro") is None
    assert data_do_grupo("312678280 - Notificacao") is None


def test_o_rotulo_separa_documento_de_movimento():
    """So documento entra na faixa do download. Pedir o download de um
    movimento devolveria nada."""
    from justica_mcp.pje import partir_o_rotulo

    assert partir_o_rotulo("128507266 - Petição Inicial") == ("128507266", "Petição Inicial")
    assert partir_o_rotulo("312678280 - Notificação") == ("312678280", "Notificação")
    identificador, descricao = partir_o_rotulo(
        "MIGRADA A TRAMITAÇÃO DO PROCESSO DO SISTEMA ELETRÔNICO")
    assert identificador is None
    assert descricao.startswith("MIGRADA")


def test_le_eventos_com_data_herdada_do_grupo():
    from justica_mcp.pje import ler_a_linha_do_tempo

    pagina = _PaginaComLinhaDoTempo({
        "itens": [
            {"etiqueta": "div", "texto": "15 out 2026", "profundidade": 1},
            {"etiqueta": "a", "texto": "312678280 - Notificação",
             "endereco": "/1g/doc/312678280", "profundidade": 3},
            {"etiqueta": "div", "texto": "EXPEDIÇÃO DE OUTROS DOCUMENTOS.",
             "profundidade": 2},
            {"etiqueta": "div", "texto": "24 jun 2024", "profundidade": 1},
            {"etiqueta": "a", "texto": "128507266 - Petição Inicial",
             "endereco": "/1g/doc/128507266", "profundidade": 3},
        ],
        "total_de_paginas": 3, "pagina_atual": 1,
    })
    lido = ler_a_linha_do_tempo(pagina)
    assert lido["paginas"] == 3 and lido["pagina"] == 1
    assert [e["data"] for e in lido["eventos"]] == [
        "2026-10-15", "2026-10-15", "2024-06-24"]
    assert [e["identificador"] for e in lido["eventos"]] == [
        "312678280", None, "128507266"]
    assert [e["e_documento"] for e in lido["eventos"]] == [True, False, True]


def test_conteiner_ausente_nao_vira_processo_sem_movimento():
    """"Nenhum evento" e "nao achei a linha do tempo" sao conclusoes
    diferentes, e confundi-las faria o advogado achar que o processo nao tem
    movimento."""
    from justica_mcp.pje import ler_a_linha_do_tempo

    lido = ler_a_linha_do_tempo(_PaginaComLinhaDoTempo(None))
    assert lido["eventos"] == []
    assert "NAO quer dizer" in lido["aviso"]


def test_falha_na_leitura_sai_como_aviso_e_nao_como_pilha():
    from justica_mcp.pje import ler_a_linha_do_tempo

    lido = ler_a_linha_do_tempo(_PaginaComLinhaDoTempo(RuntimeError("caiu")))
    assert lido["eventos"] == []
    assert "falhou" in lido["aviso"]


def test_item_repetido_entra_uma_vez_so():
    """A tela repete o rotulo em niveis diferentes da arvore: o mesmo
    documento aparece no card e na lista de anexos."""
    from justica_mcp.pje import ler_a_linha_do_tempo

    pagina = _PaginaComLinhaDoTempo({
        "itens": [
            {"etiqueta": "div", "texto": "15 out 2026", "profundidade": 1},
            {"etiqueta": "a", "texto": "312678280 - Notificação", "profundidade": 3},
            {"etiqueta": "span", "texto": "312678280 - Notificação", "profundidade": 5},
        ],
        "total_de_paginas": 1, "pagina_atual": 1,
    })
    assert len(ler_a_linha_do_tempo(pagina)["eventos"]) == 1


def test_a_faixa_para_o_download_sai_dos_documentos():
    """O painel pede 'ID a partir de' e 'Ate'. Movimento nao tem identificador
    e nao pode entrar na conta."""
    from justica_mcp.pje import faixa_de_identificadores

    eventos = [
        {"identificador": "128507266"},
        {"identificador": None},
        {"identificador": "312678280"},
        {"identificador": "130640678"},
    ]
    assert faixa_de_identificadores(eventos) == (128507266, 312678280)
    assert faixa_de_identificadores([{"identificador": None}]) == (None, None)
    assert faixa_de_identificadores([]) == (None, None)


def test_a_leitura_nao_usa_identificador_gerado_pelo_jsf():
    """Guarda de fonte. `j_id410`, `j_id412`, `j_id423` sao gerados pelo
    JavaServer Faces e mudam a cada versao do portal. Ler por eles funcionaria
    hoje e falharia depois devolvendo ZERO eventos, em silencio."""
    from justica_mcp.pje import JS_DA_LINHA_DO_TEMPO

    assert "j_id" not in JS_DA_LINHA_DO_TEMPO
    assert "divEventosTimeLine" in JS_DA_LINHA_DO_TEMPO


def test_o_texto_lido_e_o_PROPRIO_do_no():
    """Guarda de fonte, e ela protege um defeito ja vivido: em 21/10/2026 o
    indice do Visualizador devolveu a arvore inteira numa string so, porque
    lia o texto do no COM o dos filhos."""
    from justica_mcp.pje import JS_DA_LINHA_DO_TEMPO

    assert "nodeType === 3" in JS_DA_LINHA_DO_TEMPO
    assert "innerText" not in JS_DA_LINHA_DO_TEMPO
    assert "textContent" not in JS_DA_LINHA_DO_TEMPO


# ==========================================================================
# O DOWNLOAD DOS AUTOS
#
# Procedimento descrito pelo advogado em 23/10/2026, com capturas: abrir o
# painel pelo icone de seta para baixo, escolher cronologia CRESCENTE,
# informar a faixa de identificadores e clicar em DOWNLOAD.
# ==========================================================================


class _Opcao:
    def __init__(self, texto, valor):
        self.texto, self.valor = texto, valor

    def inner_text(self):
        return self.texto

    def get_attribute(self, nome):
        return self.valor if nome == "value" else None


class _Lista:
    def __init__(self, opcoes):
        self.opcoes = opcoes
        self.escolhido = None

    def query_selector_all(self, _seletor):
        return self.opcoes

    def select_option(self, value=None):
        self.escolhido = value


class _CampoDoPainel:
    def __init__(self, mascara_engole=False):
        self.valor = ""
        self.mascara_engole = mascara_engole

    def fill(self, valor):
        self.valor = "" if self.mascara_engole else valor

    def evaluate(self, _js):
        return "".join(c for c in self.valor if c.isdigit())


class _PaginaDoDownload:
    def __init__(self, *, abridor=True, campos_engolem=False,
                 tem_crescente=True, tem_botao=True):
        self.url = "https://tjrj.pje.jus.br/1g/Processo/ConsultaProcesso/Detalhe/x.seam"
        self.cliques = []
        self.de = _CampoDoPainel(campos_engolem)
        self.ate = _CampoDoPainel(campos_engolem)
        opcoes = [_Opcao("Decrescente", "0")]
        if tem_crescente:
            opcoes.append(_Opcao("Crescente", "1"))
        self.cronologia = _Lista(opcoes)
        # Os dois irmaos que a tela real tem, e que trariam a coisa errada:
        # "Download do documento" baixa UMA peca, "Download favoritos" baixa os
        # marcados. Eles vem ANTES do certo na lista, como na tela.
        self.outros_downloads = [
            _BotaoDeMentira(valor="", rotulo_acessivel="Download do documento"),
            _BotaoDeMentira(valor="", rotulo_acessivel="Download favoritos"),
        ]
        for irmao in self.outros_downloads:
            irmao.click = lambda: self.cliques.append("download-errado")
        self.abridor = _BotaoDeMentira(
            valor="", rotulo_acessivel="Download autos do processo",
            onde_fica_o_rotulo="title") if abridor else None
        if self.abridor is not None:
            self.abridor.click = lambda: self.cliques.append("abrir")
        self.botao = _BotaoDeMentira(valor="DOWNLOAD",
                                     identificador="navbar:j_id246") if tem_botao else None
        if self.botao is not None:
            self.botao.click = lambda: self.cliques.append("download")

    def query_selector(self, seletor):
        from justica_mcp.pje import (CAMPO_IDENTIFICADOR_FINAL,
                                     CAMPO_IDENTIFICADOR_INICIAL,
                                     CONTEINER_DOS_BOTOES_DE_DOWNLOAD,
                                     ESCOLHA_DA_CRONOLOGIA)
        return {
            CAMPO_IDENTIFICADOR_INICIAL: self.de,
            CAMPO_IDENTIFICADOR_FINAL: self.ate,
            ESCOLHA_DA_CRONOLOGIA: self.cronologia,
            CONTEINER_DOS_BOTOES_DE_DOWNLOAD: None,
        }.get(seletor)

    def query_selector_all(self, seletor):
        # `a, button` e a busca do abridor do painel; a outra e a do botao de
        # enviar. A tela real tem TRES icones de download, e o duble carrega os
        # tres de proposito: so assim o teste prova que o certo e escolhido.
        if seletor == "a, button":
            return [c for c in (self.outros_downloads + [self.abridor]) if c]
        return [self.botao] if self.botao else []

    def wait_for_selector(self, *a, **kw):
        pass


class _GuardaDeMentira:
    def __init__(self):
        self.permissoes = []
        self.autorizados = []

    def pode_executar(self, acao, alvo, url=None):
        self.autorizados.append((str(acao), alvo))
        return True


def test_pede_o_download_na_faixa_que_recebeu():
    from justica_mcp.pje import pedir_o_download_dos_autos

    pagina, guarda = _PaginaDoDownload(), _GuardaDeMentira()
    feito = pedir_o_download_dos_autos(pagina, guarda, de=128507266, ate=130640678)
    assert pagina.de.valor == "128507266"
    assert pagina.ate.valor == "130640678"
    assert pagina.cliques == ["abrir", "download"]
    assert feito["enviado"] is True
    assert feito["faixa"] == [128507266, 130640678]


def test_a_cronologia_escolhida_e_crescente_pelo_TEXTO():
    """Pelo texto, e nao pelo valor: o valor de uma lista do JavaServer Faces
    e um indice interno, e fixar `value="1"` seria apostar que 'Crescente' e a
    segunda opcao para sempre."""
    from justica_mcp.pje import pedir_o_download_dos_autos

    pagina = _PaginaDoDownload()
    pedir_o_download_dos_autos(pagina, _GuardaDeMentira(), de=1, ate=2)
    assert pagina.cronologia.escolhido == "1"


def test_sem_a_opcao_crescente_nada_e_pedido():
    """Ordem invertida produz um indice em que 'fls. 1' e a ultima peca."""
    import pytest

    from justica_mcp.pje import (DownloadDoPJeIndisponivel,
                                 pedir_o_download_dos_autos)

    pagina = _PaginaDoDownload(tem_crescente=False)
    with pytest.raises(DownloadDoPJeIndisponivel) as erro:
        pedir_o_download_dos_autos(pagina, _GuardaDeMentira(), de=1, ate=2)
    assert "Crescente" in str(erro.value)
    assert "download" not in pagina.cliques


def test_campo_com_mascara_que_engole_para_antes_do_clique():
    """Campo com mascara rejeita o formato EM SILENCIO, e o download sairia
    com faixa vazia. Descobrir isso depois custa a espera inteira da geracao."""
    import pytest

    from justica_mcp.pje import (DownloadDoPJeIndisponivel,
                                 pedir_o_download_dos_autos)

    pagina = _PaginaDoDownload(campos_engolem=True)
    with pytest.raises(DownloadDoPJeIndisponivel):
        pedir_o_download_dos_autos(pagina, _GuardaDeMentira(), de=1, ate=2)
    assert "download" not in pagina.cliques


def test_sem_o_botao_de_abrir_o_painel_nada_acontece():
    import pytest

    from justica_mcp.pje import (DownloadDoPJeIndisponivel,
                                 pedir_o_download_dos_autos)

    pagina = _PaginaDoDownload(abridor=False)
    with pytest.raises(DownloadDoPJeIndisponivel):
        pedir_o_download_dos_autos(pagina, _GuardaDeMentira(), de=1, ate=2)
    assert pagina.cliques == []


def test_sem_o_botao_de_enviar_a_faixa_fica_mas_nada_e_enviado():
    import pytest

    from justica_mcp.pje import (DownloadDoPJeIndisponivel,
                                 pedir_o_download_dos_autos)

    pagina = _PaginaDoDownload(tem_botao=False)
    with pytest.raises(DownloadDoPJeIndisponivel) as erro:
        pedir_o_download_dos_autos(pagina, _GuardaDeMentira(), de=1, ate=2)
    assert "nada foi enviado" in str(erro.value)
    assert pagina.cliques == ["abrir"]


def test_a_trava_autoriza_antes_de_cada_acao():
    """O clique de enviar so e autorizado DEPOIS de a faixa estar conferida."""
    from justica_mcp.pje import pedir_o_download_dos_autos

    guarda = _GuardaDeMentira()
    pedir_o_download_dos_autos(_PaginaDoDownload(), guarda, de=1, ate=2)
    alvos = [alvo for _, alvo in guarda.autorizados]
    assert 'input[id="navbar:idDe"]' in alvos
    assert 'input[id="navbar:idAte"]' in alvos
    assert alvos[-1].startswith("input[id=")


def test_o_botao_de_enviar_nao_e_procurado_por_identificador_do_jsf():
    """Guarda de fonte: a tela o trouxe como `input#navbar:j_id246`, que o
    JavaServer Faces renumera a cada versao, e OCULTO antes de o painel abrir."""
    import ast
    import inspect
    import textwrap

    from justica_mcp import pje

    # O corpo, SEM a explicacao: o texto que explica por que nao se usa `j_id`
    # precisa citar `j_id`, e a guarda nao pode tropecar na propria razao de
    # existir. Erro que ja cometi tres vezes neste projeto.
    arvore = ast.parse(textwrap.dedent(
        inspect.getsource(pje.achar_botao_de_enviar_o_download)))
    funcao = arvore.body[0]
    corpo = funcao.body[1:] if (
        isinstance(funcao.body[0], ast.Expr)
        and isinstance(funcao.body[0].value, ast.Constant)) else funcao.body
    codigo = "\n".join(ast.unparse(no) for no in corpo)
    assert "j_id" not in codigo


def test_decrescente_nao_e_escolhida_quando_se_pede_crescente():
    """O defeito que um teste pegou em 23/10/2026: "decrescente" CONTEM
    "crescente". Procurar por conteudo escolheria a ordem invertida justamente
    ao pedir a crescente, e o acervo numera as folhas na ordem em que elas
    entram: 'fls. 1' viraria a ultima peca."""
    from justica_mcp.pje import escolher_por_rotulo

    class _So:
        def __init__(self, lista):
            self.lista = lista

        def query_selector(self, _s):
            return self.lista

    # A ordem das opcoes e a da tela real: Decrescente vem primeiro.
    lista = _Lista([_Opcao("Decrescente", "0"), _Opcao("Crescente", "1")])
    assert escolher_por_rotulo(_So(lista), "qualquer", "crescente") == "1"
    assert lista.escolhido == "1"


def test_a_escolha_por_palavra_inteira_tolera_rotulo_mais_longo():
    """Igualdade exata resolve a tela de hoje. Se o portal passar a escrever
    'Ordem crescente', a palavra inteira ainda casa, e 'decrescente' nao,
    porque ali nao ha fronteira de palavra antes de 'crescente'."""
    from justica_mcp.pje import escolher_por_rotulo

    class _So:
        def __init__(self, lista):
            self.lista = lista

        def query_selector(self, _s):
            return self.lista

    lista = _Lista([_Opcao("Ordem decrescente", "0"),
                    _Opcao("Ordem crescente", "1")])
    assert escolher_por_rotulo(_So(lista), "qualquer", "crescente") == "1"


# ==========================================================================
# PERCORRER A LINHA DO TEMPO INTEIRA
#
# A corrida de 23/10/2026 leu 53 eventos e avisou "pagina 1 de 3". A tela
# gravada mostrou COMO se chega as outras duas, e nao e botao: o conteiner tem
# a classe `scroll-y`, e entre os 109 clicaveis da tela nao ha controle de
# pagina nenhum. A linha do tempo carrega por ROLAGEM.
# ==========================================================================


class _PaginaQueRola:
    def __init__(self, levas):
        """`levas` e a sequencia que cada rolagem devolve, em ordem."""
        self.levas = list(levas)
        self.rolagens = 0
        self.esperas = 0

    def evaluate(self, _js):
        passo = self.levas[min(self.rolagens, len(self.levas) - 1)]
        self.rolagens += 1
        if isinstance(passo, Exception):
            raise passo
        return passo

    def wait_for_timeout(self, _ms):
        self.esperas += 1


def _leva(pagina, paginas, itens):
    return {"altura": 1000 * pagina, "itens": itens,
            "pagina": pagina, "paginas": paginas}


def test_rola_ate_a_ultima_pagina_e_para():
    from justica_mcp.pje import percorrer_a_linha_do_tempo

    pagina = _PaginaQueRola([_leva(1, 3, 20), _leva(2, 3, 45), _leva(3, 3, 70)])
    percurso = percorrer_a_linha_do_tempo(pagina, espera=0)
    assert percurso["completa"] is True
    assert percurso["pagina"] == 3 and percurso["paginas"] == 3
    assert percurso["rolagens"] == 3
    assert percurso["aviso"] == ""


def test_quando_nao_chega_ao_fim_ele_DIZ():
    """Ler so parte e achar que se leu o processo e o erro que este percurso
    existe para evitar."""
    from justica_mcp.pje import percorrer_a_linha_do_tempo

    pagina = _PaginaQueRola([_leva(1, 9, 20), _leva(2, 9, 45)])
    percurso = percorrer_a_linha_do_tempo(pagina, teto=2, espera=0)
    assert percurso["completa"] is False
    assert "NAO cobre o processo inteiro" in percurso["aviso"]


def test_para_quando_duas_rolagens_nao_trazem_item_novo():
    """`paginaAtual` pode nao subir num portal alterado. Sem esta condicao o
    laco rodaria o teto inteiro a cada consulta."""
    from justica_mcp.pje import percorrer_a_linha_do_tempo

    pagina = _PaginaQueRola([_leva(1, 5, 20), _leva(1, 5, 20), _leva(1, 5, 20)])
    percurso = percorrer_a_linha_do_tempo(pagina, teto=40, espera=0)
    assert percurso["rolagens"] == 3
    assert percurso["completa"] is False


def test_o_teto_de_rolagens_e_respeitado():
    """Teto existe porque a alternativa e um laco que nao termina quando o
    portal muda."""
    from justica_mcp.pje import percorrer_a_linha_do_tempo

    crescendo = [_leva(1, 99, 10 * i) for i in range(1, 30)]
    percurso = percorrer_a_linha_do_tempo(_PaginaQueRola(crescendo),
                                          teto=5, espera=0)
    assert percurso["rolagens"] == 5
    assert percurso["completa"] is False


def test_conteiner_ausente_na_rolagem_nao_vira_processo_sem_movimento():
    from justica_mcp.pje import percorrer_a_linha_do_tempo

    percurso = percorrer_a_linha_do_tempo(_PaginaQueRola([None]), espera=0)
    assert percurso["completa"] is False
    assert "NAO quer dizer" in percurso["aviso"]


def test_falha_na_rolagem_sai_como_aviso():
    from justica_mcp.pje import percorrer_a_linha_do_tempo

    percurso = percorrer_a_linha_do_tempo(
        _PaginaQueRola([RuntimeError("caiu")]), espera=0)
    assert percurso["completa"] is False
    assert "pode ser so parte" in percurso["aviso"]


def test_a_rolagem_nao_usa_identificador_gerado_pelo_jsf():
    from justica_mcp.pje import JS_DE_ROLAR_A_LINHA_DO_TEMPO

    assert "j_id" not in JS_DE_ROLAR_A_LINHA_DO_TEMPO
    assert "scrollHeight" in JS_DE_ROLAR_A_LINHA_DO_TEMPO


def test_a_consulta_rola_ANTES_de_ler():
    """Guarda de fonte. Ler sem rolar devolve so a primeira leva, e foi assim
    que a faixa de identificadores saiu cobrindo meio processo em 23/10/2026."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert fonte.index("percorrer_a_linha_do_tempo(aba)") < fonte.index(
        "ler_a_linha_do_tempo(aba)")


def test_o_arquivo_gravado_diz_se_a_leitura_e_completa():
    """Faixa sem essa marca e armadilha: quem ler o arquivo depois nao tem
    como saber se ele cobre o processo ou um pedaco dele."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert '"linha_do_tempo_completa"' in fonte


# ==========================================================================
# O DOWNLOAD LIGADO A CONSULTA
# ==========================================================================


def test_o_download_so_e_pedido_com_a_linha_do_tempo_COMPLETA():
    """Guarda de fonte, e e a recusa mais importante deste caminho.

    A faixa sai da linha do tempo. Linha incompleta da faixa incompleta, e o
    arquivo viria com um pedaco do processo sem que nada no PDF dissesse isso.
    Na corrida de 23/10/2026 a primeira pagina dava de 211055786 a 301359755;
    a leitura inteira deu de 116341641 a 301359755. Baixar pela primeira
    traria menos da metade."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    trecho = fonte.split("_baixar_autos_do_pje")[0][-2500:]
    assert 'not percurso["completa"]' in trecho
    assert "pela metade" in trecho


def test_sem_documento_na_linha_do_tempo_nada_e_pedido():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert "primeiro is None" in fonte


def test_o_download_do_pje_e_opcional():
    """Baixar os autos sozinho seria decidir pelo advogado: a geracao demora e
    o arquivo e grande."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert "--documentos integra" in fonte


def test_o_resgate_do_pje_reaproveita_as_tres_redeas():
    """Guarda de fonte: ouvir o evento, procurar na pasta do navegador, e
    dizer da Area de Download. As duas primeiras foram escritas a duras penas
    no Portal de Servicos; reescreve-las aqui seria repetir o aprendizado."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_autos_do_pje)
    assert "expect_download" in fonte
    assert "resgatar_descarga" in fonte
    assert "AreaDeDownload" in fonte


def test_a_permissao_de_download_e_desligada_sempre():
    """`finally`, e nao depois do `if`: uma excecao no meio deixaria a trava
    autorizando download em qualquer tela seguinte."""
    import ast
    import inspect
    import textwrap

    from justica_mcp import portal

    arvore = ast.parse(textwrap.dedent(
        inspect.getsource(portal._baixar_autos_do_pje)))
    tentativas = [no for no in ast.walk(arvore) if isinstance(no, ast.Try)]
    finais = "\n".join(ast.unparse(no) for t in tentativas for no in t.finalbody)
    assert "permitir_download = False" in finais


def test_copia_repetida_nao_e_indexada_de_novo():
    """Indexar de novo diria que o processo tem o dobro de folhas que tem."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_autos_do_pje)
    assert "REPETIDA_NO_TEXTO" in fonte
    assert "O indice NAO foi alterado" in fonte


def test_o_rotulo_e_lido_de_aria_label_OU_de_title():
    """A corrida de 23/10/2026 parou porque o seletor olhava so `aria-label`,
    e naquele botao o rotulo vinha de `title`. O gravador de telas sempre
    consultou as duas fontes; a busca e que olhava uma."""
    from justica_mcp.pje import rotulo_acessivel

    por_aria = _BotaoDeMentira(rotulo_acessivel="Download autos do processo")
    por_title = _BotaoDeMentira(rotulo_acessivel="Download autos do processo",
                                onde_fica_o_rotulo="title")
    sem_rotulo = _BotaoDeMentira()
    assert rotulo_acessivel(por_aria) == "download autos do processo"
    assert rotulo_acessivel(por_title) == "download autos do processo"
    assert rotulo_acessivel(sem_rotulo) == ""


def test_entre_tres_icones_de_download_escolhe_o_dos_AUTOS():
    """A tela real tem 'Download autos do processo', 'Download do documento' e
    'Download favoritos'. Casar por "download" traria uma peca onde o advogado
    espera o processo inteiro."""
    from justica_mcp.pje import achar_o_abridor_do_painel

    pagina = _PaginaDoDownload()
    achado = achar_o_abridor_do_painel(pagina)
    assert achado is pagina.abridor
    pedir = __import__("justica_mcp.pje", fromlist=["x"]).pedir_o_download_dos_autos
    pedir(pagina, _GuardaDeMentira(), de=1, ate=2)
    assert "download-errado" not in pagina.cliques


def test_sem_nenhum_download_de_autos_nada_e_clicado():
    """So os irmaos na tela: nao se clica no que baixaria a coisa errada."""
    import pytest

    from justica_mcp.pje import (DownloadDoPJeIndisponivel,
                                 pedir_o_download_dos_autos)

    pagina = _PaginaDoDownload(abridor=False)
    with pytest.raises(DownloadDoPJeIndisponivel) as erro:
        pedir_o_download_dos_autos(pagina, _GuardaDeMentira(), de=1, ate=2)
    assert "aria-label" in str(erro.value) and "title" in str(erro.value)
    assert pagina.cliques == []


# ==========================================================================
# A AREA DE DOWNLOAD
#
# Corrida de 23/10/2026: o pedido foi feito inteiro. O relato da trava mostra
# o painel aberto (`a:abrir-painel-de-download`), a faixa preenchida
# (`navbar:idDe`, `navbar:idAte`) e o botao clicado (`navbar:j_id246`). E
# nenhum arquivo chegou pelo navegador em 45 segundos.
#
# Isso NAO e falha: o PJe gera o arquivo e o deixa na Area de Download, uma
# tela propria do portal, cujo caminho a tela dos autos declarou entre os de
# navegacao. Buscar o arquivo la nao vai ser escrito as cegas.
# ==========================================================================


def test_o_caminho_da_area_de_download_nao_e_adivinhado():
    """Ele veio dos CAMINHOS DE NAVEGACAO que a tela dos autos declarou."""
    from justica_mcp.portal import CAMINHO_DA_AREA_DE_DOWNLOAD

    assert CAMINHO_DA_AREA_DE_DOWNLOAD == "/1g/AreaDeDownload/listView.seam"


def test_sem_arquivo_o_programa_vai_relatar_a_area_e_nao_desiste_calado():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_autos_do_pje)
    assert "_relatar_area_de_download" in fonte
    assert "O PEDIDO FOI FEITO" in fonte


def test_na_area_de_download_nada_e_clicado():
    """Guarda de fonte. Clicar numa tela que eu nunca vi e exatamente o erro
    que custou quatro corridas em outubro."""
    import ast
    import inspect
    import textwrap

    from justica_mcp import portal

    arvore = ast.parse(textwrap.dedent(
        inspect.getsource(portal._relatar_area_de_download)))
    chamadas = [ast.unparse(no) for no in ast.walk(arvore)
                if isinstance(no, ast.Call)]
    assert not [c for c in chamadas if ".click(" in c], chamadas
    # A unica acao autorizada e NAVEGAR.
    fonte = inspect.getsource(portal._relatar_area_de_download)
    assert "Acao.NAVEGAR" in fonte
    assert "Acao.CLICAR" not in fonte


# --------------------------------------------------------------------------
# A quarta redea: pedir de novo pelo endereco que o navegador viu passar
# --------------------------------------------------------------------------


class _GuardaDoFaro:
    def __init__(self, recusar=()):
        self.permissoes: list = []
        self.permitir_download = False
        self.recusadas = set(recusar)

    def pode_executar(self, acao, destino, url=None):
        if (url or destino) in self.recusadas:
            raise PermissionError("recusado")
        return True


class _ContextoDePedido:
    def __init__(self):
        self.pedidos: list = []

    @property
    def request(self):
        return self


class _AbaDeMentira:
    def __init__(self, url, contexto=None):
        self.url = url
        self.context = contexto or _ContextoDePedido()


class _FaroDeMentira:
    def __init__(self, enderecos):
        self._enderecos = list(enderecos)
        self.relatou = False

    def enderecos(self):
        return list(self._enderecos)

    def relatar(self, recuo="    "):
        self.relatou = True


def test_o_resgate_pelo_faro_pede_de_novo_o_que_passou(monkeypatch, tmp_path):
    from justica_mcp import portal

    pedidos = []

    def _falso(contexto, url, destino, nome, sugerido=None, recuo="      "):
        pedidos.append(url)
        alvo = tmp_path / f"{nome}-{sugerido}"
        alvo.write_bytes(b"%PDF-1.4")
        return str(alvo)

    monkeypatch.setattr("justica_mcp.dcp.baixar_pelo_endereco", _falso)
    numero = type("N", (), {"apenas_digitos": "1" * 20})()
    trazido = portal._resgatar_pelo_faro(
        _FaroDeMentira(["https://docs.tjrj.jus.br/a/autos.pdf"]),
        _AbaDeMentira("https://tjrj.pje.jus.br/1g/x.seam"),
        _GuardaDoFaro(), tmp_path, numero)
    assert pedidos == ["https://docs.tjrj.jus.br/a/autos.pdf"]
    assert trazido is not None and trazido.is_file()


def test_o_resgate_pelo_faro_nao_pede_arquivo_de_fora_da_justica(monkeypatch,
                                                                 tmp_path):
    """Endereco que nao e do mesmo tribunal nao e dos autos, e esta funcao nao
    e porta para buscar arquivo em servidor qualquer."""
    from justica_mcp import portal

    pedidos = []
    monkeypatch.setattr(
        "justica_mcp.dcp.baixar_pelo_endereco",
        lambda *a, **k: pedidos.append(a[1]))
    numero = type("N", (), {"apenas_digitos": "1" * 20})()
    trazido = portal._resgatar_pelo_faro(
        _FaroDeMentira(["https://cdn.exemplo.com/autos.pdf"]),
        _AbaDeMentira("https://tjrj.pje.jus.br/1g/x.seam"),
        _GuardaDoFaro(), tmp_path, numero)
    assert pedidos == []
    assert trazido is None


def test_o_resgate_pelo_faro_respeita_a_recusa_da_guarda(monkeypatch, tmp_path):
    from justica_mcp import portal

    pedidos = []
    monkeypatch.setattr(
        "justica_mcp.dcp.baixar_pelo_endereco",
        lambda *a, **k: pedidos.append(a[1]))
    endereco = "https://docs.tjrj.jus.br/a/autos.pdf"
    numero = type("N", (), {"apenas_digitos": "1" * 20})()
    trazido = portal._resgatar_pelo_faro(
        _FaroDeMentira([endereco]),
        _AbaDeMentira("https://tjrj.pje.jus.br/1g/x.seam"),
        _GuardaDoFaro(recusar=[endereco]), tmp_path, numero)
    assert pedidos == []
    assert trazido is None


def test_o_resgate_pelo_faro_sem_endereco_nenhum_diz_isso(capsys, tmp_path):
    from justica_mcp import portal

    numero = type("N", (), {"apenas_digitos": "1" * 20})()
    assert portal._resgatar_pelo_faro(
        _FaroDeMentira([]), _AbaDeMentira("https://tjrj.pje.jus.br/x"),
        _GuardaDoFaro(), tmp_path, numero) is None
    assert "nao viu endereco" in capsys.readouterr().out


def test_o_resgate_pelo_faro_nao_solta_o_endereco_inteiro(monkeypatch, capsys,
                                                          tmp_path):
    from justica_mcp import portal

    monkeypatch.setattr("justica_mcp.dcp.baixar_pelo_endereco",
                        lambda *a, **k: None)
    numero = type("N", (), {"apenas_digitos": "1" * 20})()
    portal._resgatar_pelo_faro(
        _FaroDeMentira(
            ["https://docs.tjrj.jus.br/a/08090908820238190001/autos.pdf?t=x"]),
        _AbaDeMentira("https://tjrj.pje.jus.br/1g/x.seam"),
        _GuardaDoFaro(), tmp_path, numero)
    saida = capsys.readouterr().out
    assert "0809090" not in saida
    assert "autos.pdf" in saida


def test_o_faro_e_ligado_antes_do_pedido_e_desligado_depois():
    """Guarda de fonte: ligado DEPOIS do clique nao ve o endereco passar, e o
    endereco passa uma vez so."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_autos_do_pje)
    assert fonte.index("farejador.ligar()") < fonte.index("expect_download")
    assert "farejador.desligar()" in fonte


def test_o_faro_e_consultado_antes_e_depois_da_area_de_download():
    """Duas colheitas: a tela da Area de Download pode fazer o endereco passar."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_autos_do_pje)
    assert fonte.count("_resgatar_pelo_faro") == 2
    primeiro = fonte.index("_resgatar_pelo_faro")
    area = fonte.index("_relatar_area_de_download")
    assert primeiro < area < fonte.rindex("_resgatar_pelo_faro")


def test_o_resgate_pelo_faro_nao_clica_em_nada():
    """Guarda de fonte: a quarta redea PEDE, nao clica."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._resgatar_pelo_faro)
    assert ".click(" not in fonte
    assert ".goto(" not in fonte


# --------------------------------------------------------------------------
# Prazo de tela e prazo de arquivo sao grandezas diferentes
# --------------------------------------------------------------------------


def test_o_download_dos_autos_usa_o_prazo_de_arquivo_e_nao_o_de_tela():
    """O defeito que fez as tres primeiras redeas falharem juntas.

    O caminho do PJe passava o prazo de TELA (45s por padrao) para esperar o
    ARQUIVO. Um PDF de 507 folhas nao fica pronto em 45s, e o programa
    desistia antes de o portal terminar de gera-lo. A licao ja estava escrita
    em `espera_do_arquivo` desde o Portal de Servicos; faltava aplica-la aqui.
    """
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_autos_do_pje)
    assert "espera_do_arquivo(" in fonte
    assert "expect_download(timeout=prazo * 1000)" in fonte
    assert "espera=prazo" in fonte
    # A tela continua com o prazo de tela: a Area de Download que nao monta em
    # 45s esta quebrada, e esperar 300s por ela so adiaria o relato.
    assert "_relatar_area_de_download(aba, guarda, segundos)" in fonte


def test_quem_chama_entrega_o_prazo_de_arquivo_pedido_na_linha_de_comando():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert "prazo_do_arquivo=segundos_download" in fonte


def test_o_prazo_de_arquivo_nunca_fica_abaixo_do_teto_proprio():
    """Sem `--segundos-download`, o prazo nao pode cair para o de tela."""
    from justica_mcp.dcp import TETO_DO_DOWNLOAD, espera_do_arquivo

    assert espera_do_arquivo(45) == TETO_DO_DOWNLOAD
    assert espera_do_arquivo(None) == TETO_DO_DOWNLOAD
    assert espera_do_arquivo(900) == 900
