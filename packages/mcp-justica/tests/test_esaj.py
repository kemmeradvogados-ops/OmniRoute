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


# --------------------------------------------------------------------------
# Extracao
#
# Identificadores conferidos em campo em 22/09/2026, na pagina do processo de
# primeiro grau. Cada um foi visto no relato de estrutura; nenhum foi suposto.
# --------------------------------------------------------------------------

from justica_mcp.esaj import (
    extrair, extrair_dados_principais, extrair_movimentacoes, extrair_partes,
    link_da_pasta_digital, lista_de_movimentacoes_esta_completa,
)


class _El:
    def __init__(self, texto="", filhos=None, atributos=None):
        self._texto = texto
        self._filhos = filhos or {}
        self._atributos = atributos or {}

    def inner_text(self):
        return self._texto

    def get_attribute(self, nome):
        return self._atributos.get(nome)

    def query_selector_all(self, seletor):
        return self._filhos.get(seletor, [])


class _Pagina:
    def __init__(self, mapa, tabelas=()):
        self._mapa = mapa
        self._tabelas = list(tabelas)

    def query_selector(self, seletor):
        return self._mapa.get(seletor)

    def query_selector_all(self, seletor):
        return self._tabelas if seletor == "table" else []


def _linha(*celulas):
    return _El(filhos={"td": [_El(c) for c in celulas]})


def test_le_os_dados_principais_pelos_identificadores():
    p = _Pagina({
        "#numeroProcesso": _El("1037850-62.2023.8.26.0100"),
        "#classeProcesso": _El("Execução Fiscal"),
        "#varaProcesso": _El(" 1ª  Vara  "),
    })
    d = extrair_dados_principais(p)
    assert d["numero"] == "1037850-62.2023.8.26.0100"
    assert d["classe"] == "Execução Fiscal"
    assert d["vara"] == "1ª Vara"      # espacos colapsados
    assert d["juiz"] is None           # ausente nao vira erro nem string vazia


def test_campo_ausente_nao_derruba_os_outros():
    """Processo sem juiz designado, ou de execucao fiscal sem os campos de
    conhecimento: faltar e normal, e nao pode custar o resto."""
    assert extrair_dados_principais(_Pagina({}))["numero"] is None


def test_partes_preferem_a_tabela_completa():
    """A tabela completa e superconjunto da de principais. Usar a de
    principais quando ha as duas perderia parte do polo passivo."""
    p = _Pagina({
        "#tablePartesPrincipais": _El(filhos={"tr": [_linha("Exeqte:", "FAZENDA")]}),
        "#tableTodasPartes": _El(filhos={"tr": [
            _linha("Exeqte:", "FAZENDA"),
            _linha("Exectdo:", "EMPRESA LTDA\nAdvogado Um\nAdvogado Dois"),
        ]}),
    })
    partes = extrair_partes(p)
    assert len(partes) == 2
    assert partes[1]["polo"] == "Exectdo"          # dois-pontos removidos
    assert partes[1]["nome"] == "EMPRESA LTDA"
    assert partes[1]["representantes"] == ["Advogado Um", "Advogado Dois"]


def test_sem_tabela_completa_cai_na_de_principais():
    p = _Pagina({
        "#tablePartesPrincipais": _El(filhos={"tr": [_linha("Exeqte:", "FAZENDA")]}),
    })
    assert len(extrair_partes(p)) == 1


def test_sem_tabela_alguma_devolve_lista_vazia():
    assert extrair_partes(_Pagina({})) == []


def test_movimentacoes_saem_do_container_e_nao_de_tabela_com_id():
    """A tabela nao tem identificador proprio: vive dentro do container.
    Ancorar no container e o que torna a leitura possivel sem inventar
    seletor."""
    p = _Pagina({
        "#containerMovimentacoes": _El(filhos={"tr": [
            _linha("21/07/2026", "", "", "Remetidos os autos"),
            _linha("16/07/2026", "", "", "Contrarrazões"),
        ]}),
    })
    m = extrair_movimentacoes(p)
    assert m == [
        {"data": "21/07/2026", "descricao": "Remetidos os autos"},
        {"data": "16/07/2026", "descricao": "Contrarrazões"},
    ]


def test_descricao_sai_da_ultima_celula_e_nao_de_indice_fixo():
    """Depender do indice 2 quebraria em tabela de tres colunas, e a pagina
    conferida tinha quatro."""
    p = _Pagina({
        "#containerMovimentacoes": _El(filhos={"tr": [_linha("01/01/2026", "Despacho")]}),
    })
    assert extrair_movimentacoes(p)[0]["descricao"] == "Despacho"


def test_linha_de_cabecalho_sem_celulas_de_dado_e_ignorada():
    p = _Pagina({
        "#containerMovimentacoes": _El(filhos={"tr": [
            _El(filhos={"td": []}),
            _linha("01/01/2026", "Despacho"),
        ]}),
    })
    assert len(extrair_movimentacoes(p)) == 1


def test_lista_parcial_e_sinalizada():
    """Entregar a lista parcial como completa faria o advogado concluir que
    nao ha andamento anterior, que e pior que nao entregar nada."""
    p = _Pagina({"#btnExibirMovimentacoes": _El("Exibir mais")})
    assert lista_de_movimentacoes_esta_completa(p) is False


def test_sem_link_de_expandir_a_lista_e_completa():
    assert lista_de_movimentacoes_esta_completa(_Pagina({})) is True


def test_le_o_endereco_da_pasta_digital():
    """Ao contrario do eproc, a integra do e-SAJ tem endereco proprio, entao a
    copia nao vai precisar de clique."""
    p = _Pagina({"#linkPasta": _El(atributos={
        "href": "/cpopg/abrirPastaDigital.do?processo.codigo=2S001OE3V0000"
    })})
    assert link_da_pasta_digital(p).endswith("processo.codigo=2S001OE3V0000")


def test_sem_link_de_pasta_devolve_nada_em_vez_de_quebrar():
    assert link_da_pasta_digital(_Pagina({})) is None


def test_extracao_completa_traz_totais_e_sinalizacao():
    p = _Pagina({
        "#numeroProcesso": _El("1037850-62.2023.8.26.0100"),
        "#tableTodasPartes": _El(filhos={"tr": [_linha("Exeqte:", "FAZENDA")]}),
        "#containerMovimentacoes": _El(filhos={"tr": [_linha("01/01/2026", "Despacho")]}),
        "#btnExibirMovimentacoes": _El("Exibir mais"),
    })
    d = extrair(p)
    assert d["totais"] == {"partes": 1, "movimentacoes": 1}
    assert d["movimentacoes_completas"] is False


def test_pagina_que_explode_na_leitura_nao_derruba_a_extracao():
    class Explode:
        def query_selector(self, _):
            raise RuntimeError("pagina fechada")

    d = extrair(Explode())
    assert d["totais"] == {"partes": 0, "movimentacoes": 0}
    assert d["pasta_digital"] is None


def test_a_consulta_grava_o_arquivo_e_nao_despeja_na_tela():
    """Sao dezenas de movimentacoes por processo. Despeja-las no terminal
    convida a colar dado de cliente onde nao deve."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    ramo = fonte[fonte.index('identidade.sistema == "esaj"'):fonte.index("BUSCA_RAPIDA")]
    assert "_gravar_consulta" in ramo
    assert "Nao o cole em conversa nenhuma" in ramo
    assert 'dados["movimentacoes"][:5]' in ramo   # so as cinco mais recentes


def test_a_consulta_avisa_quando_a_lista_veio_parcial():
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert "e PARCIAL" in fonte
    assert "nao foi" in fonte and "conferido em campo" in fonte


def test_a_consulta_alimenta_a_comparacao_de_novidades():
    """Sem o instantaneo, Sao Paulo ficaria fora do monitoramento: a consulta
    traria os dados e `verificar_novos_andamentos` nunca saberia que eles
    existiram."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    ramo = fonte[fonte.index('identidade.sistema == "esaj"'):fonte.index("BUSCA_RAPIDA")]
    assert "gravar_snapshot" in ramo


# --------------------------------------------------------------------------
# A tabela de movimentacoes nao tem identificador
#
# Conferido em campo em 22/09/2026: `div#containerMovimentacoes` existe e vem
# VAZIO, porque o e-SAJ so o preenche quando alguem aciona "exibir mais". As
# movimentacoes visiveis vivem numa tabela sem identificador nenhum.
# --------------------------------------------------------------------------

def test_container_vazio_cai_na_varredura_por_formato_de_dado():
    """Reconhecer pela data na primeira celula e verificavel; chutar um
    identificador nao seria."""
    p = _Pagina(
        {"#containerMovimentacoes": _El(filhos={"tr": []})},
        tabelas=[_El(filhos={"tr": [
            _linha("21/07/2026", "", "", "Remetidos os autos"),
            _linha("16/07/2026", "", "", "Contrarrazoes"),
        ]})],
    )
    m = extrair_movimentacoes(p)
    assert [x["data"] for x in m] == ["21/07/2026", "16/07/2026"]


def test_container_preenchido_tem_precedencia_sobre_a_varredura():
    """O lugar declarado vem primeiro: quando ele responde, a varredura nem
    roda, e o resultado nao depende da ordem das tabelas na pagina."""
    p = _Pagina(
        {"#containerMovimentacoes": _El(filhos={"tr": [
            _linha("01/01/2026", "Do container"),
        ]})},
        tabelas=[_El(filhos={"tr": [_linha("02/02/2026", "De outra tabela")]})],
    )
    assert extrair_movimentacoes(p)[0]["descricao"] == "Do container"


def test_tabela_de_partes_nao_e_confundida_com_movimentacao():
    """A pagina tem varias tabelas. Sem a exigencia de data na primeira
    celula, a de partes viraria movimentacao e o relatorio mentiria."""
    p = _Pagina({}, tabelas=[
        _El(filhos={"tr": [_linha("Exeqte:", "FAZENDA DO ESTADO")]}),
        _El(filhos={"tr": [_linha("10/03/2026", "Juntada de peticao")]}),
    ])
    m = extrair_movimentacoes(p)
    assert len(m) == 1
    assert m[0]["descricao"] == "Juntada de peticao"


def test_data_em_formato_estranho_nao_conta():
    p = _Pagina({}, tabelas=[_El(filhos={"tr": [_linha("2026-03-10", "Algo")]})])
    assert extrair_movimentacoes(p) == []


def test_linha_com_data_mas_sem_descricao_e_descartada():
    p = _Pagina({}, tabelas=[_El(filhos={"tr": [_linha("10/03/2026", "")]})])
    assert extrair_movimentacoes(p) == []


def test_sem_tabela_alguma_devolve_lista_vazia_sem_quebrar():
    assert extrair_movimentacoes(_Pagina({})) == []


# --------------------------------------------------------------------------
# De onde as linhas vieram importa mais que as linhas
#
# Em campo em 22/09/2026 a varredura trouxe tres linhas com data, e elas
# pareciam peticoes, nao movimentacoes: um processo de execucao de 2023 nao tem
# tres andamentos, e as datas vinham em ordem crescente. A pagina do e-SAJ tem
# varias tabelas com data.
# --------------------------------------------------------------------------

from justica_mcp.esaj import extrair_movimentacoes_com_origem


def test_origem_container_quando_o_lugar_declarado_responde():
    p = _Pagina({"#containerMovimentacoes": _El(filhos={"tr": [
        _linha("01/01/2026", "Despacho"),
    ]})})
    assert extrair_movimentacoes_com_origem(p)[1] == "container"


def test_origem_varredura_quando_veio_de_tabela_sem_identificador():
    """A varredura acha ALGO com data, nao necessariamente o historico."""
    p = _Pagina({}, tabelas=[_El(filhos={"tr": [_linha("01/01/2026", "Peticao")]})])
    assert extrair_movimentacoes_com_origem(p)[1] == "varredura"


def test_origem_nenhuma_quando_nao_ha_linha_com_data():
    assert extrair_movimentacoes_com_origem(_Pagina({}))[1] == "nenhuma"


def test_a_consulta_avisa_quando_a_origem_e_incerta():
    """Chamar de movimentacoes o que veio de tabela anonima seria afirmar o que
    nao se sabe, e o advogado leria um historico que talvez nao seja."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert 'movimentacoes_origem"] == "varredura"' in fonte
    assert "CONFIRA no portal" in fonte


# --------------------------------------------------------------------------
# Expandir movimentacoes
#
# Autorizado pelo operador em 22/09/2026. O historico verdadeiro so existe
# depois deste clique: o container nomeado vem vazio e o portal so o preenche
# aqui.
# --------------------------------------------------------------------------

from justica_mcp.esaj import LINK_EXPANDIR_MOVIMENTACOES, expandir_movimentacoes


class _PaginaExpansivel:
    def __init__(self, tem_botao=True):
        self.url = "https://esaj.tjsp.jus.br/cpopg/show.do"
        self.cliques = 0
        self.tem_botao = tem_botao
        self.viewport_size = {"width": 1280, "height": 720}

    def query_selector_all(self, seletor):
        if seletor == LINK_EXPANDIR_MOVIMENTACOES and self.tem_botao:
            return [self]
        return []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 10, "y": 10, "width": 80, "height": 20}

    def click(self):
        self.cliques += 1

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


def test_expande_quando_o_botao_existe():
    p = _PaginaExpansivel()
    assert expandir_movimentacoes(p, _guarda(), 5) is True
    assert p.cliques == 1


def test_sem_botao_nao_clica_e_avisa_pelo_retorno():
    """Processo sem movimentacao escondida nao tem o botao, e isso nao e erro."""
    p = _PaginaExpansivel(tem_botao=False)
    assert expandir_movimentacoes(p, _guarda(), 5) is False
    assert p.cliques == 0


def test_a_autorizacao_do_clique_alcanca_so_esse_seletor():
    p = _PaginaExpansivel()
    guarda = _guarda()
    expandir_movimentacoes(p, guarda, 5)
    liberados = set()
    for perm in guarda.permissoes:
        liberados.update(perm.seletores_clicaveis)
        liberados.update(perm.seletores_preenchiveis)
    assert liberados == {LINK_EXPANDIR_MOVIMENTACOES}


def test_o_botao_de_ciencia_continua_barrado_depois_da_expansao():
    """Ele mora na MESMA pagina. A autorizacao do clique de expandir nao pode
    respingar nele, e o termo de risco garante isso antes de qualquer lista."""
    p = _PaginaExpansivel()
    guarda = _guarda()
    expandir_movimentacoes(p, guarda, 5)
    d = guarda.avaliar(
        Acao.CLICAR, "#botaoConfirmarRebebimentoIntimacao", url=p.url
    )
    assert d.permitido is False
    assert "ciencia" in d.motivo


# --------------------------------------------------------------------------
# Copia da integra
#
# Diferenca em relacao ao eproc: aqui a integra TEM endereco proprio, entao a
# copia nao precisa de clique. A pasta digital e outra aplicacao do portal e o
# que ela devolve nunca foi visto.
# --------------------------------------------------------------------------

from justica_mcp.esaj import copiar_pasta_digital


class _Resposta:
    def __init__(self, tipo, corpo, url=""):
        self.headers = {"content-type": tipo}
        self._corpo = corpo
        # Onde a requisicao PAROU, depois de seguir redirecionamentos. E aqui
        # que o endereco real da pasta aparece.
        self.url = url

    def body(self):
        return self._corpo


class _Requisicao:
    def __init__(self, resposta):
        self._resposta = resposta
        self.pedido = None

    def get(self, endereco, **kw):
        self.pedido = endereco
        if isinstance(self._resposta, Exception):
            raise self._resposta
        return self._resposta


class _Contexto:
    def __init__(self, resposta):
        self.request = _Requisicao(resposta)


class _PaginaComPasta:
    def __init__(self, href, resposta=None):
        self.url = "https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=X"
        self._href = href
        self.context = _Contexto(resposta)

    def query_selector(self, seletor):
        if seletor == "#linkPasta" and self._href:
            return _El(atributos={"href": self._href})
        return None


def test_pdf_e_gravado_na_pasta_do_processo(tmp_path):
    p = _PaginaComPasta("/cpopg/abrirPastaDigital.do?processo.codigo=X",
                        _Resposta("application/pdf", b"%PDF-1.4 conteudo"))
    r = copiar_pasta_digital(p, _guarda_com_download(), tmp_path, "123", 10)
    assert r["situacao"] == "gravada"
    assert (tmp_path / "integra-123.pdf").read_bytes().startswith(b"%PDF")


def test_endereco_relativo_vira_absoluto():
    """O link vem relativo na pagina. Buscar sem completar daria 404 e
    pareceria processo sem autos."""
    p = _PaginaComPasta("/cpopg/abrirPastaDigital.do?processo.codigo=X",
                        _Resposta("application/pdf", b"%PDF"))
    copiar_pasta_digital(p, _guarda_com_download(), "/tmp", "123", 10)
    assert p.context.request.pedido.startswith("https://esaj.tjsp.jus.br/")


def test_resposta_que_nao_e_pdf_e_relatada_e_nao_gravada(tmp_path):
    """A pasta digital e um visualizador: provavelmente devolve tela, nao
    arquivo. Gravar HTML como se fosse a integra seria pior que nao gravar."""
    p = _PaginaComPasta("/cpopg/abrirPastaDigital.do?processo.codigo=X",
                        _Resposta("text/html; charset=utf-8", b"<html>visualizador"))
    r = copiar_pasta_digital(p, _guarda_com_download(), tmp_path, "123", 10)
    assert r["situacao"] == "nao_e_arquivo"
    assert "text/html" in r["detalhe"]
    assert not list(tmp_path.iterdir())


def test_sem_link_de_pasta_diz_isso_em_vez_de_quebrar(tmp_path):
    r = copiar_pasta_digital(_PaginaComPasta(None), _guarda_com_download(), tmp_path, "123", 10)
    assert r["situacao"] == "sem_link"


def test_falha_de_rede_e_relatada(tmp_path):
    p = _PaginaComPasta("/cpopg/abrirPastaDigital.do?processo.codigo=X",
                        RuntimeError("sem rede"))
    r = copiar_pasta_digital(p, _guarda_com_download(), tmp_path, "123", 10)
    assert r["situacao"] == "falhou"
    assert "sem rede" in r["detalhe"]


def _guarda_com_download():
    """A copia exige autorizacao explicita: `permitir_download` e falso por
    padrao, e e o comando que o liga, so durante a copia."""
    g = _guarda()
    g.permitir_download = True
    return g


def test_sem_autorizacao_de_download_a_copia_e_barrada(tmp_path):
    """A garantia central: baixar autos e negado por padrao, e listar a
    permissao de origem nao basta."""
    p = _PaginaComPasta("/cpopg/abrirPastaDigital.do?processo.codigo=X",
                        _Resposta("application/pdf", b"%PDF"))
    r = copiar_pasta_digital(p, _guarda(), tmp_path, "123", 10)
    assert r["situacao"] == "barrado"
    assert not list(tmp_path.iterdir())


# --------------------------------------------------------------------------
# Pistas da tela de passagem da pasta digital
#
# Conferido em campo em 22/09/2026: a pasta digital devolveu `text/html` com
# 948 bytes. Esse tamanho nao comporta uma tela de verdade: e pagina de
# passagem, que redireciona ou monta o visualizador por script.
# --------------------------------------------------------------------------

from justica_mcp.esaj import _pistas_do_visualizador


def test_acha_o_endereco_para_onde_a_pagina_redireciona():
    corpo = b"<html><script>location.href='/pastadigital/pg/abrirDocumento.do?x=1'</script>"
    pistas = _pistas_do_visualizador(corpo)
    assert any("abrirDocumento.do" in p for p in pistas)


def test_acha_formulario_que_a_pagina_envia_sozinha():
    corpo = b'<form action="/pastadigital/pg/abrir.do" name="frm"><input name="codigo"></form>'
    pistas = _pistas_do_visualizador(corpo)
    assert any("action: /pastadigital/pg/abrir.do" in p for p in pistas)
    assert any("campo: codigo" in p for p in pistas)


def test_nao_repete_o_mesmo_endereco():
    corpo = b'<a href="/x"></a><a href="/x"></a>'
    assert sum(1 for p in _pistas_do_visualizador(corpo) if p.endswith(": /x")) == 1


def test_acha_endereco_dentro_de_window_open():
    """A pagina real do e-SAJ usa `window.open`, que nao casa com `action`,
    `src`, `href` nem `location`. Procurar pela FORMA do endereco, e nao pelo
    nome do atributo que o carrega, foi o que a fez aparecer."""
    corpo = b'<script>window.open("/pastadigital/pg/abrirPasta.do?x=1");window.close()</script>'
    pistas = _pistas_do_visualizador(corpo)
    assert any("abrirPasta.do" in p for p in pistas)


def test_acha_endereco_em_document_location():
    corpo = b'<script>document.location = "/pastadigital/outro.do"</script>'
    assert any("outro.do" in p for p in _pistas_do_visualizador(corpo))


def test_texto_comum_nao_vira_pista():
    """So endereco: texto entre aspas que nao parece caminho ficaria como
    ruido e poderia carregar dado de processo."""
    corpo = b'<script>var nome = "FULANO DE TAL"</script>'
    assert _pistas_do_visualizador(corpo) == []


def test_corpo_ilegivel_nao_quebra():
    assert _pistas_do_visualizador(b"\\xff\\xfe\\x00binario") == []


def test_a_copia_devolve_as_pistas_quando_nao_e_pdf(tmp_path):
    p = _PaginaComPasta(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X",
        _Resposta("text/html;charset=UTF-8",
                  b'<form action="/pastadigital/pg/abrir.do"></form>'),
    )
    r = copiar_pasta_digital(p, _guarda_com_download(), tmp_path, "123", 10)
    assert r["situacao"] == "nao_e_arquivo"
    assert any("pastadigital" in pista for pista in r["pistas"])


# --------------------------------------------------------------------------
# Expandir ate o fim, e abrir a janela dos autos
#
# Instrucoes do operador em 22/09/2026: clicar em "exibir movimentacoes" ate a
# opcao sumir; e, para as copias, abrir a janela dos autos, selecionar todos os
# documentos e baixar os selecionados.
# --------------------------------------------------------------------------

from justica_mcp.esaj import (
    MAXIMO_DE_EXPANSOES, abrir_pasta_digital, expandir_movimentacoes_ate_o_fim,
)


class _PaginaQueExpande:
    """Some com o botao depois de N expansoes, crescendo a cada uma."""

    def __init__(self, ate=3, cresce=True):
        self.url = "https://esaj.tjsp.jus.br/cpopg/show.do"
        self.cliques = 0
        self.ate = ate
        self.cresce = cresce
        self.viewport_size = {"width": 1280, "height": 720}

    def query_selector_all(self, seletor):
        if seletor == LINK_EXPANDIR_MOVIMENTACOES and self.cliques < self.ate:
            return [self]
        return []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def click(self):
        self.cliques += 1

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


def test_expande_ate_o_botao_sumir():
    """Uma expansao so trazia um pedaco, e entregar o pedaco como o todo faria
    o advogado concluir que nao ha andamento anterior."""
    p = _PaginaQueExpande(ate=4)
    r = expandir_movimentacoes_ate_o_fim(
        p, _guarda(), 5, contar=lambda _: p.cliques * 10
    )
    assert p.cliques == 4
    assert r == {"expansoes": 4, "motivo": "botao sumiu"}


def test_para_quando_a_lista_deixa_de_crescer():
    """Botao que nao some e lista que nao cresce e clique inutil repetido."""
    p = _PaginaQueExpande(ate=99)
    r = expandir_movimentacoes_ate_o_fim(p, _guarda(), 5, contar=lambda _: 7)
    assert r["motivo"] == "parou de crescer"
    assert p.cliques < MAXIMO_DE_EXPANSOES


def test_o_teto_impede_laco_sem_fim():
    """Protecao contra o botao nunca sumir por motivo que nao previmos."""
    p = _PaginaQueExpande(ate=9999)
    r = expandir_movimentacoes_ate_o_fim(
        p, _guarda(), 5, contar=lambda _: p.cliques * 10
    )
    assert r == {"expansoes": MAXIMO_DE_EXPANSOES, "motivo": "teto de expansoes atingido"}


def test_pagina_sem_botao_nao_expande_nada():
    p = _PaginaQueExpande(ate=0)
    assert expandir_movimentacoes_ate_o_fim(p, _guarda(), 5)["expansoes"] == 0


class _ContextoComAbas:
    """Simula o comportamento visto em campo: a aba aberta morre e uma janela
    filha aparece no contexto."""

    def __init__(self, aba, filhas=(), mata_a_aba=False, resposta=None):
        self._aba = aba
        self.abriu = False
        self.pages = []
        self._filhas = list(filhas)
        self._mata = mata_a_aba
        self.request = _Requisicao(resposta) if resposta is not None else None

    def new_page(self):
        self.abriu = True
        if not self._mata:
            self.pages = self.pages + [self._aba]
        self.pages = self.pages + self._filhas
        return self._aba


class _AbaNova:
    def __init__(self, fechada=False):
        self.url = ""
        self.viewport_size = {"width": 1280, "height": 720}
        self._fechada = fechada

    def goto(self, destino, **kw):
        self.url = destino

    def is_closed(self):
        return self._fechada

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


class _PaginaDoProcesso:
    def __init__(self, href, aba=None, filhas=(), mata_a_aba=False, resposta=None):
        self.url = "https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=X"
        self._href = href
        self.context = _ContextoComAbas(
            aba or _AbaNova(), filhas=filhas, mata_a_aba=mata_a_aba,
            resposta=resposta,
        )

    def query_selector(self, seletor):
        return _El(atributos={"href": self._href}) if (
            seletor == "#linkPasta" and self._href) else None

    def wait_for_timeout(self, ms):
        pass


def test_abre_os_autos_em_aba_nova_sem_clicar():
    """Abrir pelo endereco nao pode cair em elemento vizinho, e a aba original
    continua na pagina do processo, com os dados ja lidos."""
    aba = _AbaNova()
    p = _PaginaDoProcesso("/cpopg/abrirPastaDigital.do?processo.codigo=X", aba=aba)
    abas = abrir_pasta_digital(p, _guarda(), 5)
    assert p.context.abriu is True
    assert aba.url.startswith("https://esaj.tjsp.jus.br/cpopg/abrirPastaDigital.do")
    assert abas == [aba]


def test_devolve_a_janela_FILHA_quando_a_aba_aberta_morre():
    """Conferido em campo: a pagina de passagem abre outra janela e se encerra.
    Ler a aba que abrimos dava TargetClosedError e o relato vinha vazio."""
    filha = _AbaNova()
    p = _PaginaDoProcesso(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X",
        filhas=[filha], mata_a_aba=True,
    )
    assert abrir_pasta_digital(p, _guarda(), 5) == [filha]


def test_aba_fechada_fica_de_fora_da_lista():
    p = _PaginaDoProcesso(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X",
        aba=_AbaNova(fechada=True),
    )
    assert abrir_pasta_digital(p, _guarda(), 5) == []


def test_devolve_lista_e_nao_supoe_uma_janela_so():
    """Supor exatamente uma janela seria adivinhar o comportamento do portal."""
    duas = [_AbaNova(), _AbaNova()]
    p = _PaginaDoProcesso(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X",
        filhas=duas, mata_a_aba=True,
    )
    assert len(abrir_pasta_digital(p, _guarda(), 5)) == 2


def test_sem_link_nao_abre_aba_alguma():
    p = _PaginaDoProcesso(None)
    assert abrir_pasta_digital(p, _guarda(), 5) == []
    assert p.context.abriu is False


# --------------------------------------------------------------------------
# A palavra "mais"
#
# O operador informou em 22/09/2026: na secao de andamentos e preciso clicar na
# palavra "mais". O identificador conhecido some depois de uma expansao e o
# historico continuava em cinco linhas, entao ele nao e o unico controle.
# --------------------------------------------------------------------------

from justica_mcp.esaj import CANDIDATOS_EXPANDIR


class _PaginaComPalavraMais:
    """So responde ao seletor de texto, nunca ao identificador."""

    def __init__(self):
        self.url = "https://esaj.tjsp.jus.br/cpopg/show.do"
        self.cliques = 0
        self.viewport_size = {"width": 1280, "height": 720}

    def query_selector_all(self, seletor):
        return [self] if seletor == 'text="mais"' else []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def click(self):
        self.cliques += 1

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass


def test_clica_na_palavra_mais_quando_nao_ha_identificador():
    p = _PaginaComPalavraMais()
    assert expandir_movimentacoes(p, _guarda(), 5) is True
    assert p.cliques == 1


def test_o_identificador_tem_precedencia_sobre_a_palavra():
    """O que a pagina declara vem antes do que o olho ve: assim o resultado nao
    depende de haver outra palavra "mais" em algum canto da tela."""
    assert CANDIDATOS_EXPANDIR[0] == LINK_EXPANDIR_MOVIMENTACOES


def test_a_autorizacao_nomeia_o_seletor_que_foi_de_fato_usado():
    """Auditoria com o seletor errado nao prova o que aconteceu."""
    p = _PaginaComPalavraMais()
    guarda = _guarda()
    expandir_movimentacoes(p, guarda, 5)
    descricoes = [perm.descricao for perm in guarda.permissoes]
    assert any('text="mais"' in d for d in descricoes)


def test_expande_pela_palavra_ate_o_fim():
    """Cada expansao revela outra palavra "mais"; o laco para quando ela some."""
    class Ate3(_PaginaComPalavraMais):
        def query_selector_all(self, seletor):
            if seletor == 'text="mais"' and self.cliques < 3:
                return [self]
            return []

    p = Ate3()
    r = expandir_movimentacoes_ate_o_fim(p, _guarda(), 5, contar=lambda _: p.cliques * 10)
    assert p.cliques == 3
    assert r["motivo"] == "botao sumiu"


# --------------------------------------------------------------------------
# O endereco da pasta varia por processo, e nao se constroi
#
# Pergunta do operador em 22/09/2026. A resposta e que ele traz um `ticket` de
# sessao que so o portal emite, por sessao e por processo: montar e impossivel
# por definicao. A pagina de passagem existe exatamente para carrega-lo, entao
# o caminho e LER de onde o portal o pos.
# --------------------------------------------------------------------------

from justica_mcp.esaj import endereco_real_da_pasta


def test_le_o_endereco_real_de_dentro_de_window_open():
    corpo = (b'<script>window.open("https://esaj.tjsp.jus.br/pastadigital/'
             b'abrirPastaProcessoDigital.do?nuProcesso=X&ticket=ABC%2FDEF");</script>')
    achado = endereco_real_da_pasta(corpo)
    assert achado.startswith("https://esaj.tjsp.jus.br/pastadigital/")
    assert "ticket=ABC%2FDEF" in achado


def test_o_ticket_e_preservado_inteiro():
    """O ticket vem com caracteres escapados. Mexer nele o invalida, e o portal
    responderia como se o advogado nao tivesse acesso ao processo."""
    ticket = "b4G7VsPqAr4M%2BUajgpmj58o7DbaRQP0c%2FYfy%2F"
    corpo = f'<script>window.open("/pastadigital/abrirPasta.do?ticket={ticket}")</script>'
    assert ticket in endereco_real_da_pasta(corpo.encode())


def test_endereco_relativo_tambem_e_aceito():
    corpo = b'<script>window.open("/pastadigital/abrirPastaProcessoDigital.do?x=1")</script>'
    assert endereco_real_da_pasta(corpo) == "/pastadigital/abrirPastaProcessoDigital.do?x=1"


def test_outro_endereco_da_pagina_nao_e_confundido_com_a_pasta():
    """A pagina pode carregar folha de estilo, script e icone. So o caminho da
    pasta digital interessa."""
    corpo = (b'<link href="/estilo/tema.css"><script src="/js/app.js"></script>'
             b'<script>window.open("/pastadigital/abrirPasta.do?x=1")</script>')
    assert endereco_real_da_pasta(corpo) == "/pastadigital/abrirPasta.do?x=1"


def test_pagina_sem_endereco_de_pasta_devolve_nada():
    assert endereco_real_da_pasta(b"<html>sem nada</html>") is None


def test_corpo_vazio_nao_quebra():
    assert endereco_real_da_pasta(b"") is None


# --------------------------------------------------------------------------
# A pagina de passagem REDIRECIONA
#
# Percebido em campo em 22/09/2026: procurar o endereco dentro do corpo nao
# achava nada, porque a requisicao ja seguia o redirecionamento sozinha e o
# corpo que chegava era o do destino. Quem sabe onde a requisicao parou e a
# RESPOSTA, nao o corpo.
# --------------------------------------------------------------------------

def test_usa_o_endereco_onde_a_requisicao_parou():
    real = ("https://esaj.tjsp.jus.br/pastadigital/abrirPastaProcessoDigital.do"
            "?nuProcesso=X&ticket=ABC%2FDEF")
    aba = _AbaNova()
    p = _PaginaDoProcesso(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X", aba=aba,
        resposta=_Resposta("text/html", b"<html>destino</html>", url=real),
    )
    abrir_pasta_digital(p, _guarda(), 5)
    assert aba.url == real


def test_o_ticket_do_redirecionamento_chega_inteiro():
    ticket = "b4G7VsPqAr4M%2BUajgpmj58o7DbaRQP0c%2FYfy%2F"
    real = f"https://esaj.tjsp.jus.br/pastadigital/abrirPasta.do?ticket={ticket}"
    aba = _AbaNova()
    p = _PaginaDoProcesso(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X", aba=aba,
        resposta=_Resposta("text/html", b"", url=real),
    )
    abrir_pasta_digital(p, _guarda(), 5)
    assert ticket in aba.url


def test_resposta_que_nao_parou_na_pasta_cai_na_leitura_do_corpo():
    """Nem todo portal redireciona. Se a resposta parou noutro lugar, o corpo
    ainda pode carregar o endereco, e os dois caminhos continuam valendo."""
    aba = _AbaNova()
    p = _PaginaDoProcesso(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X", aba=aba,
        resposta=_Resposta(
            "text/html",
            b'<script>window.open("/pastadigital/doCorpo.do?x=1")</script>',
            url="https://esaj.tjsp.jus.br/cpopg/abrirPastaDigital.do",
        ),
    )
    abrir_pasta_digital(p, _guarda(), 5)
    assert aba.url.endswith("/pastadigital/doCorpo.do?x=1")


def test_sem_endereco_real_segue_com_o_de_passagem():
    """Pior que o certo, melhor que nada: o relato continua dizendo o que
    encontrou, e o operador decide."""
    aba = _AbaNova()
    p = _PaginaDoProcesso(
        "/cpopg/abrirPastaDigital.do?processo.codigo=X", aba=aba,
        resposta=_Resposta("text/html", b"<html>nada</html>", url="https://x/y"),
    )
    abrir_pasta_digital(p, _guarda(), 5)
    assert aba.url.endswith("/cpopg/abrirPastaDigital.do?processo.codigo=X")


# --------------------------------------------------------------------------
# Copia pelo visualizador, como o operador descreveu e fotografou
#
# 22/09/2026: "Visualizar autos" abre a Pasta Digital; la se marca "Todas",
# clica em "Baixar PDF", escolhe "Arquivo unico" e confirma em "Continuar".
#
# Por que o clique, se este projeto prefere o endereco: a Pasta Digital SO nasce
# do clique. Tres caminhos falharam em campo, e o ultimo relato mostrou por que:
# o ticket e montado no instante do clique.
# --------------------------------------------------------------------------

from justica_mcp.esaj import (
    ARQUIVO_UNICO, BAIXAR_PDF, BOTAO_VISUALIZAR_AUTOS, CONFIRMAR_DOWNLOAD,
    MARCAR_TODAS, copiar_autos_pelo_visualizador,
)


class _Baixado:
    suggested_filename = "autos.pdf"

    def __init__(self, destino=None):
        self.salvo_em = None

    def save_as(self, caminho):
        self.salvo_em = caminho
        from pathlib import Path

        Path(caminho).write_bytes(b"%PDF-1.4")


class _Espera:
    def __init__(self, valor):
        self.value = valor

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Janela:
    def __init__(self, faltando=()):
        self.url = "https://esaj.tjsp.jus.br/pastadigital/abrirPastaProcessoDigital.do?t=1"
        self.faltando = set(faltando)
        self.clicados = []
        self.fechada = False
        self.viewport_size = {"width": 1280, "height": 720}

    def query_selector_all(self, seletor):
        return [] if seletor in self.faltando else [_AlvoClicavel(self, seletor)]

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def expect_download(self, timeout=None):
        return _Espera(_Baixado())

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass

    def close(self):
        self.fechada = True


class _AlvoClicavel:
    def __init__(self, dono, seletor):
        self._dono, self._seletor = dono, seletor

    def is_visible(self):
        return True

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 9, "height": 9}

    def click(self):
        self._dono.clicados.append(self._seletor)


class _PaginaComAutos:
    def __init__(self, janela, sem_botao=False):
        self.url = "https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=X"
        self._janela = janela
        self.sem_botao = sem_botao
        self.clicados = []
        self.viewport_size = {"width": 1280, "height": 720}

    def query_selector_all(self, seletor):
        if seletor == BOTAO_VISUALIZAR_AUTOS and not self.sem_botao:
            return [_AlvoClicavel(self, seletor)]
        return []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def expect_popup(self, timeout=None):
        return _Espera(self._janela)


def test_a_sequencia_inteira_grava_o_pdf(tmp_path):
    janela = _Janela()
    p = _PaginaComAutos(janela)
    r = copiar_autos_pelo_visualizador(p, _guarda(), tmp_path, "123", 10)
    assert r["situacao"] == "gravada"
    assert (tmp_path / "integra-autos.pdf").read_bytes().startswith(b"%PDF")
    assert "#selecionarButton" in janela.clicados
    assert "#salvarButton" in janela.clicados
    assert 'text="Continuar"' in janela.clicados


def test_a_ordem_dos_passos_e_a_que_o_operador_descreveu(tmp_path):
    """Marcar depois de baixar nao selecionaria nada, e o PDF viria vazio."""
    janela = _Janela()
    copiar_autos_pelo_visualizador(_PaginaComAutos(janela), _guarda(), tmp_path, "1", 10)
    assert janela.clicados.index("#selecionarButton") < janela.clicados.index("#salvarButton")
    assert janela.clicados.index("#salvarButton") < janela.clicados.index('text="Continuar"')


def test_para_e_relata_quando_um_passo_some(tmp_path):
    """A tela pode mudar. Continuar sem o passo baixaria outra coisa, ou nada,
    e gravaria como se fosse a integra."""
    janela = _Janela(faltando=set(BAIXAR_PDF))
    r = copiar_autos_pelo_visualizador(_PaginaComAutos(janela), _guarda(), tmp_path, "1", 10)
    assert r["situacao"] == "parou_no_passo"
    assert r["passo"] == "Baixar PDF"
    assert 'text="Continuar"' not in janela.clicados


def test_sem_o_botao_de_visualizar_autos_nao_clica_nada(tmp_path):
    janela = _Janela()
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela, sem_botao=True), _guarda(), tmp_path, "1", 10
    )
    assert r["situacao"] == "sem_botao"
    assert janela.clicados == []


def test_arquivo_unico_ausente_nao_interrompe(tmp_path):
    """Ele ja vem marcado na tela fotografada: clicar e so protecao contra o
    portal mudar o padrao, e nao achar nao pode custar o download."""
    janela = _Janela(faltando=set(ARQUIVO_UNICO))
    r = copiar_autos_pelo_visualizador(_PaginaComAutos(janela), _guarda(), tmp_path, "1", 10)
    assert r["situacao"] == "gravada"


def test_cada_alvo_entra_na_permissao_por_si(tmp_path):
    """Uma permissao ampla para a janela inteira seria mais simples, e e o que
    nao se faz: a lista estreita impede clique fora do previsto se a tela
    mudar."""
    janela = _Janela()
    guarda = _guarda()
    copiar_autos_pelo_visualizador(_PaginaComAutos(janela), guarda, tmp_path, "1", 10)
    liberados = set()
    for perm in guarda.permissoes:
        liberados.update(perm.seletores_clicaveis)
    permitidos = {BOTAO_VISUALIZAR_AUTOS}
    for grupo in (MARCAR_TODAS, BAIXAR_PDF, ARQUIVO_UNICO, CONFIRMAR_DOWNLOAD):
        permitidos.update(grupo)
    assert liberados <= permitidos


def test_o_botao_de_ciencia_continua_barrado_durante_a_copia(tmp_path):
    janela = _Janela()
    guarda = _guarda()
    copiar_autos_pelo_visualizador(_PaginaComAutos(janela), guarda, tmp_path, "1", 10)
    d = guarda.avaliar(
        Acao.CLICAR, "#botaoConfirmarRebebimentoIntimacao",
        url="https://esaj.tjsp.jus.br/cpopg/show.do",
    )
    assert d.permitido is False


def test_uma_rodada_sem_crescer_nao_encerra_a_expansao():
    """A pagina monta as linhas depois de a rede sossegar. Concluir "parou de
    crescer" na primeira rodada lenta deixou o historico em cinco linhas quando
    havia quase cinquenta."""
    class Lenta(_PaginaQueExpande):
        def __init__(self):
            super().__init__(ate=99)
            self.leituras = 0

        def wait_for_timeout(self, ms):
            pass

    p = Lenta()
    # Cresce, finge estagnar numa leitura, e volta a crescer na seguinte.
    leituras = iter([10, 10, 20, 20, 30, 30, 30, 30, 30, 30])

    def contar(_):
        try:
            return next(leituras)
        except StopIteration:
            return 30

    r = expandir_movimentacoes_ate_o_fim(p, _guarda(), 5, contar=contar)
    assert p.cliques >= 2, "desistiu na primeira rodada sem crescimento"
