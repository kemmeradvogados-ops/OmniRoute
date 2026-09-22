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
# Qual "Mais" clicar
#
# Fotografado pelo operador em 22/09/2026: a pagina tem VARIOS "Mais". Um no
# cabecalho, um em PARTES DO PROCESSO, e o de MOVIMENTACOES, que so aparece
# abaixo da lista. Pegar o primeiro que casasse clicava em qualquer um deles, e
# por isso a mesma consulta trouxe 50, 48, 20 e 5.
#
# A condicao de parada tambem estava errada: nao e o botao sumir, e a palavra
# virar "Recolher".
# --------------------------------------------------------------------------

from justica_mcp.esaj import (
    CONTAINER_MOVIMENTACOES, TEXTO_MAIS, TEXTO_RECOLHER, _abaixo_da_secao,
    movimentacoes_totalmente_expandidas,
)


class _Posicionado:
    def __init__(self, y, rotulo="", visivel=True):
        self.y = y
        self.rotulo = rotulo
        self.visivel = visivel
        self.cliques = 0

    def is_visible(self):
        return self.visivel

    def bounding_box(self):
        return {"x": 0, "y": self.y, "width": 50, "height": 15}

    def click(self):
        self.cliques += 1


class _PaginaPosicional:
    """Pagina com varios "Mais" em alturas diferentes, como a real."""

    def __init__(self, container_y=500, mais=(), recolher=()):
        self.url = "https://esaj.tjsp.jus.br/cpopg/show.do"
        self._container = _Posicionado(container_y, "container")
        self._mais = list(mais)
        self._recolher = list(recolher)
        self.viewport_size = {"width": 1280, "height": 720}

    def query_selector_all(self, seletor):
        if seletor == TEXTO_MAIS:
            return self._mais
        if seletor == TEXTO_RECOLHER:
            return self._recolher
        if seletor == CONTAINER_MOVIMENTACOES:
            return [self._container]
        return []

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

    def wait_for_load_state(self, *a, **kw):
        pass

    def wait_for_selector(self, *a, **kw):
        pass

    def wait_for_timeout(self, ms):
        pass


def test_escolhe_o_mais_que_esta_abaixo_das_movimentacoes():
    """O do cabecalho e o das partes ficam ACIMA. Clicar neles expandia outra
    coisa e deixava o historico truncado."""
    cabecalho = _Posicionado(100, "cabecalho")
    partes = _Posicionado(300, "partes")
    movimentacoes = _Posicionado(800, "movimentacoes")
    p = _PaginaPosicional(container_y=500, mais=[cabecalho, partes, movimentacoes])
    achado = _abaixo_da_secao(p, TEXTO_MAIS, CONTAINER_MOVIMENTACOES)
    assert achado is movimentacoes


def test_escolhe_o_mais_PROXIMO_abaixo():
    """Secoes seguintes, como PETICOES DIVERSAS, tem os seus proprios "Mais", e
    ficam ainda mais abaixo."""
    das_movimentacoes = _Posicionado(800)
    das_peticoes = _Posicionado(1500)
    p = _PaginaPosicional(container_y=500, mais=[das_peticoes, das_movimentacoes])
    assert _abaixo_da_secao(p, TEXTO_MAIS, CONTAINER_MOVIMENTACOES) is das_movimentacoes


def test_mais_invisivel_nao_conta():
    escondido = _Posicionado(800, visivel=False)
    p = _PaginaPosicional(container_y=500, mais=[escondido])
    assert _abaixo_da_secao(p, TEXTO_MAIS, CONTAINER_MOVIMENTACOES) is None


def test_recolher_abaixo_das_movimentacoes_significa_expandido():
    """Condicao de parada informada pelo operador e visivel na terceira foto:
    a palavra troca, o botao nao some."""
    p = _PaginaPosicional(container_y=500, recolher=[_Posicionado(900)])
    assert movimentacoes_totalmente_expandidas(p) is True


def test_recolher_de_outra_secao_nao_encerra_a_expansao():
    """Um "Recolher" acima das movimentacoes e de outra secao, e tomá-lo como
    fim deixaria o historico truncado sem aviso."""
    p = _PaginaPosicional(container_y=500, recolher=[_Posicionado(200)])
    assert movimentacoes_totalmente_expandidas(p) is False


def test_sem_recolher_a_expansao_continua():
    assert movimentacoes_totalmente_expandidas(_PaginaPosicional()) is False


def test_expande_pelo_mais_posicional_ate_virar_recolher():
    estado = {"cliques": 0}

    class Pagina(_PaginaPosicional):
        def query_selector_all(self, seletor):
            if seletor == TEXTO_RECOLHER:
                return [_Posicionado(900)] if estado["cliques"] >= 3 else []
            if seletor == TEXTO_MAIS:
                return [] if estado["cliques"] >= 3 else [_Marcador()]
            return super().query_selector_all(seletor)

    class _Marcador(_Posicionado):
        def __init__(self):
            super().__init__(800)

        def click(self):
            estado["cliques"] += 1

    p = Pagina(container_y=500)
    r = expandir_movimentacoes_ate_o_fim(p, _guarda(), 5, contar=lambda _: estado["cliques"] * 10)
    assert estado["cliques"] == 3


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
    """Pasta Digital que entrega o arquivo no clique, como o portal faz quando
    o PDF ja esta montado. Foi assim numa execucao de campo."""

    # Clicar aqui faz o navegador anunciar o download.
    ENTREGAM = ('text="Continuar"', "#btnContinuar", "#btnDownloadDocumento")

    def __init__(self, faltando=()):
        self.url = "https://esaj.tjsp.jus.br/pastadigital/abrirPastaProcessoDigital.do?t=1"
        self.faltando = set(faltando)
        self.clicados = []
        self.fechada = False
        self.viewport_size = {"width": 1280, "height": 720}
        self.ouvintes = {}
        self.baixado = _Baixado()

    def on(self, evento, funcao):
        self.ouvintes.setdefault(evento, []).append(funcao)

    def _apos_clique(self, seletor):
        if seletor in self.ENTREGAM and self.baixado is not None:
            for funcao in self.ouvintes.get("download", []):
                funcao(self.baixado)

    def query_selector_all(self, seletor):
        return [] if seletor in self.faltando else [_AlvoClicavel(self, seletor)]

    def query_selector(self, seletor):
        achados = self.query_selector_all(seletor)
        return achados[0] if achados else None

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
        apos = getattr(self._dono, "_apos_clique", None)
        if apos is not None:
            apos(self._seletor)


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


# --------------------------------------------------------------------------
# O maior conjunto e o historico
#
# Instabilidade vista em campo em 22/09/2026: a mesma consulta trouxe 50,
# depois 48, depois 5. O container guarda so as ultimas movimentacoes, e a
# lista completa nasce noutra tabela quando a pessoa expande. Parando no
# primeiro conjunto, o laco via o numero travado em cinco e concluia "parou de
# crescer" com quarenta e tantas linhas ja na tela.
# --------------------------------------------------------------------------

def test_prefere_o_maior_conjunto_ao_primeiro_encontrado():
    poucas = _El(filhos={"tr": [_linha("01/01/2026", "Recente")]})
    muitas = _El(filhos={"tr": [
        _linha(f"{d:02d}/01/2026", f"Andamento {d}") for d in range(1, 10)
    ]})
    p = _Pagina({"#containerMovimentacoes": poucas}, tabelas=[muitas])
    movs, origem = extrair_movimentacoes_com_origem(p)
    assert len(movs) == 9
    assert origem == "varredura"


def test_empate_fica_com_o_container():
    """O lugar declarado ganha quando os dois tem o mesmo tamanho: so se
    prefere a varredura quando ela traz MAIS."""
    iguais = lambda: _El(filhos={"tr": [_linha("01/01/2026", "Algo")]})
    p = _Pagina({"#containerMovimentacoes": iguais()}, tabelas=[iguais()])
    assert extrair_movimentacoes_com_origem(p)[1] == "container"


def test_container_maior_continua_vencendo():
    muitas = _El(filhos={"tr": [
        _linha(f"{d:02d}/01/2026", f"Andamento {d}") for d in range(1, 6)
    ]})
    poucas = _El(filhos={"tr": [_linha("01/01/2026", "Peticao")]})
    p = _Pagina({"#containerMovimentacoes": muitas}, tabelas=[poucas])
    movs, origem = extrair_movimentacoes_com_origem(p)
    assert len(movs) == 5
    assert origem == "container"


def test_a_tabela_de_partes_continua_fora_mesmo_sendo_grande():
    """Tamanho nao basta: a linha precisa comecar com data. Sem isso, uma
    tabela grande de partes viraria o historico."""
    partes = _El(filhos={"tr": [
        _linha("Exeqte:", f"PARTE {i}") for i in range(20)
    ]})
    movs = _El(filhos={"tr": [_linha("01/01/2026", "Despacho")]})
    p = _Pagina({}, tabelas=[partes, movs])
    achadas, _ = extrair_movimentacoes_com_origem(p)
    assert len(achadas) == 1
    assert achadas[0]["descricao"] == "Despacho"


# --------------------------------------------------------------------------
# A janela se fecha durante a gravacao
#
# Em campo em 22/09/2026: a copia comecou e `save_as` morreu com
# TargetClosedError. A Pasta Digital se fecha sozinha depois de entregar o
# arquivo, e fechar a janela mata o canal no meio da gravacao. Na execucao
# anterior ela sobreviveu: e corrida de tempo, nao erro de logica.
# --------------------------------------------------------------------------

class _BaixadoQueMorre:
    """`save_as` falha, mas o arquivo ja esta em disco, como de fato esta."""

    suggested_filename = "autos.pdf"

    def __init__(self, tmp_path, com_temporario=True):
        self._tmp = tmp_path / "temporario.pdf"
        if com_temporario:
            self._tmp.write_bytes(b"%PDF-1.4 conteudo")
        self._tem = com_temporario

    def save_as(self, caminho):
        raise RuntimeError("Target page, context or browser has been closed")

    def path(self):
        if not self._tem:
            return None
        return str(self._tmp)


class _JanelaQueMorre(_Janela):
    def __init__(self, baixado):
        super().__init__()
        self.baixado = baixado


def test_arquivo_e_salvo_do_temporario_quando_a_janela_morre(tmp_path):
    """Perder um arquivo ja baixado por causa da janela que o entregou seria o
    pior desperdicio: custou uma tentativa e um codigo lido no celular."""
    destino = tmp_path / "copias"
    janela = _JanelaQueMorre(_BaixadoQueMorre(tmp_path))
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), destino, "123", 10
    )
    assert r["situacao"] == "gravada"
    assert (destino / "integra-autos.pdf").read_bytes().startswith(b"%PDF")


def test_sem_temporario_o_erro_e_relatado_e_nada_e_inventado(tmp_path):
    destino = tmp_path / "copias"
    janela = _JanelaQueMorre(_BaixadoQueMorre(tmp_path, com_temporario=False))
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), destino, "123", 10
    )
    assert r["situacao"] == "download_perdido"
    assert not list(destino.iterdir())


def test_o_caminho_normal_continua_sendo_o_primeiro(tmp_path):
    """A copia do temporario e rede, nao o caminho principal: quando `save_as`
    funciona, e ele que grava."""
    janela = _Janela()
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), tmp_path, "123", 10
    )
    assert r["situacao"] == "gravada"


def test_falha_ao_localizar_o_temporario_tambem_e_relatada(tmp_path):
    """Nao pode explodir com erro meu: o operador precisa ler a causa do
    portal, nao um UnboundLocalError."""
    class SemCaminho(_BaixadoQueMorre):
        def path(self):
            raise RuntimeError("canal fechado")

    janela = _JanelaQueMorre(SemCaminho(tmp_path))
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), tmp_path / "c", "1", 10
    )
    assert r["situacao"] == "download_perdido"
    assert "canal fechado" in r["detalhe"]


# --------------------------------------------------------------------------
# O terceiro caminho: o disco
#
# `path()` tambem viaja pelo canal do navegador, entao morre junto com a
# janela, como `save_as`. Em campo em 22/09/2026 os dois falharam com
# TargetClosedError com o arquivo ja gravado em disco. A pasta de descargas
# nao depende de canal: e sistema de arquivos.
# --------------------------------------------------------------------------

class _BaixadoSemCanal:
    """Nem `save_as` nem `path()` respondem: o canal do navegador morreu."""

    suggested_filename = "autos.pdf"

    def save_as(self, caminho):
        raise RuntimeError("Target page, context or browser has been closed")

    def path(self):
        raise RuntimeError("Download.path: Target page, context or browser has been closed")


def test_arquivo_e_recuperado_da_pasta_de_descargas(tmp_path, monkeypatch):
    """O arquivo ja esta no disco; perde-lo custaria uma tentativa do teto e um
    codigo lido no celular."""
    from justica_mcp import portal as portal_mod

    descargas = tmp_path / "descargas"
    descargas.mkdir()
    (descargas / "a1b2c3").write_bytes(b"%PDF-1.4 integra")
    monkeypatch.setattr(portal_mod, "pasta_de_descargas", lambda: descargas)

    destino = tmp_path / "copias"
    janela = _JanelaQueMorre(_BaixadoSemCanal())
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), destino, "123", 10
    )
    assert r["situacao"] == "gravada"
    assert (destino / "integra-autos.pdf").read_bytes() == b"%PDF-1.4 integra"


def test_arquivo_de_execucao_anterior_nao_e_entregue_como_a_integra(
    tmp_path, monkeypatch
):
    """Entregar a copia de outro processo seria inventar prova: o pior erro
    possivel neste projeto."""
    import os
    import time

    from justica_mcp import portal as portal_mod

    descargas = tmp_path / "descargas"
    descargas.mkdir()
    velho = descargas / "de-ontem"
    velho.write_bytes(b"%PDF-1.4 outro processo")
    antigo = time.time() - 86400
    os.utime(velho, (antigo, antigo))
    monkeypatch.setattr(portal_mod, "pasta_de_descargas", lambda: descargas)

    destino = tmp_path / "copias"
    janela = _JanelaQueMorre(_BaixadoSemCanal())
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), destino, "123", 10
    )
    assert r["situacao"] == "download_perdido"
    assert not destino.exists() or not list(destino.iterdir())


def test_arquivo_vazio_nao_e_gravado_como_copia(tmp_path, monkeypatch):
    """Um PDF de zero byte abre como arquivo corrompido e faria o advogado
    acreditar que a copia existe."""
    from justica_mcp import portal as portal_mod

    descargas = tmp_path / "descargas"
    descargas.mkdir()
    (descargas / "vazio").write_bytes(b"")
    monkeypatch.setattr(portal_mod, "pasta_de_descargas", lambda: descargas)

    destino = tmp_path / "copias"
    janela = _JanelaQueMorre(_BaixadoSemCanal())
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), destino, "123", 10
    )
    assert r["situacao"] == "download_perdido"
    assert "vazio" in r["detalhe"]


def test_parcial_do_chromium_e_ignorado(tmp_path, monkeypatch):
    """`.crdownload` e escrita em andamento: copiar dali daria um PDF truncado,
    que abre, parece a integra e esconde as ultimas folhas."""
    from justica_mcp import portal as portal_mod

    descargas = tmp_path / "descargas"
    descargas.mkdir()
    (descargas / "parcial.crdownload").write_bytes(b"%PDF pela metade")
    monkeypatch.setattr(portal_mod, "pasta_de_descargas", lambda: descargas)

    destino = tmp_path / "copias"
    janela = _JanelaQueMorre(_BaixadoSemCanal())
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), destino, "123", 10
    )
    assert r["situacao"] == "download_perdido"


def test_esperar_parar_de_crescer_devolve_o_tamanho_estavel(tmp_path):
    from justica_mcp.esaj import _esperar_arquivo_parar_de_crescer

    arquivo = tmp_path / "x.pdf"
    arquivo.write_bytes(b"1234567890")
    assert _esperar_arquivo_parar_de_crescer(arquivo, segundos=2) == 10


def test_o_caminho_do_navegador_continua_vindo_antes_do_disco(tmp_path, monkeypatch):
    """O disco e rede de seguranca, nao o caminho principal: quando `save_as`
    responde, e ele que grava."""
    from justica_mcp import portal as portal_mod

    descargas = tmp_path / "descargas"
    descargas.mkdir()
    (descargas / "nao-usar").write_bytes(b"%PDF nao deveria ser lido")
    monkeypatch.setattr(portal_mod, "pasta_de_descargas", lambda: descargas)

    destino = tmp_path / "copias"
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(_Janela()), _guarda(), destino, "123", 10
    )
    assert r["situacao"] == "gravada"


# --------------------------------------------------------------------------
# O portal MONTA o documento antes de entrega-lo
#
# Em campo em 22/09/2026: depois do "Continuar" a espera de 120s terminou em
# TimeoutError sem arquivo nenhum. O relato da tela explicou: o portal tinha
# aberto #popupGerarDocumento e estava montando o PDF dos 115 documentos. O
# arquivo nao vem do "Continuar": vem de "Salvar o documento", que so nasce
# quando a montagem termina.
# --------------------------------------------------------------------------

class _JanelaQueGera(_Janela):
    """Pasta Digital que monta o PDF: tela de espera, depois o botao de salvar,
    e so entao o arquivo."""

    def __init__(self, com_espera=True, aviso=None):
        super().__init__()
        self.visiveis = {
            "#selecionarButton", "#salvarButton", 'text="Arquivo único"',
            'text="Continuar"',
        }
        self.com_espera = com_espera
        self.aviso = aviso

    def query_selector_all(self, seletor):
        return [_AlvoClicavel(self, seletor)] if seletor in self.visiveis else []

    def _apos_clique(self, seletor):
        if seletor == 'text="Continuar"':
            self.visiveis.discard('text="Continuar"')
            if self.aviso:
                self.visiveis.add(self.aviso)
            elif self.com_espera:
                self.visiveis |= {"#radioAguardar", "#btnAguardarProcessamento"}
            else:
                self.visiveis.add("#btnDownloadDocumento")
        elif seletor == "#btnAguardarProcessamento":
            self.visiveis -= {"#radioAguardar", "#btnAguardarProcessamento"}
            self.visiveis.add("#btnDownloadDocumento")
        elif seletor == "#btnDownloadDocumento":
            for funcao in self.ouvintes.get("download", []):
                funcao(self.baixado)


def test_espera_o_portal_montar_o_pdf_e_clica_em_salvar_o_documento(tmp_path):
    janela = _JanelaQueGera()
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), tmp_path, "123", 1
    )
    assert r["situacao"] == "gravada"
    assert "#btnDownloadDocumento" in janela.clicados


def test_a_espera_e_escolhida_e_o_envio_por_email_nunca_e_clicado(tmp_path):
    """Mandar os autos do cliente por e-mail e ato externo: ninguem autorizou."""
    janela = _JanelaQueGera()
    copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), tmp_path, "123", 1
    )
    assert "#radioAguardar" in janela.clicados
    assert "#btnAguardarProcessamento" in janela.clicados
    for proibido in ("#radioEmail", "#btnConfirmarEnvioEmail",
                     "#btnCancelarProcessamento"):
        assert proibido not in janela.clicados


def test_arquivo_que_vem_direto_continua_sendo_aceito(tmp_path):
    """Numa execucao de campo o portal entregou na hora, porque ja tinha o PDF
    montado. Os dois casos precisam funcionar."""
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(_Janela()), _guarda(), tmp_path, "123", 1
    )
    assert r["situacao"] == "gravada"


def test_aviso_de_intimacao_pendente_para_tudo_e_chama_o_operador(tmp_path):
    """Confirmar esse aviso fica a um passo de dar ciencia, e ciencia abre
    prazo. Prazo aberto por engano e dano que automatismo nenhum repara."""
    janela = _JanelaQueGera(aviso="#divMensagemIntimacaoPendente")
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), tmp_path, "123", 1
    )
    assert r["situacao"] == "aviso_de_intimacao"
    assert "ciencia" in r["detalhe"]
    assert "#buttonOk" not in janela.clicados


def test_o_aviso_de_somente_pendente_tambem_para(tmp_path):
    janela = _JanelaQueGera(aviso="#divMensagemIntimacaoSomentePendente")
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), tmp_path, "123", 1
    )
    assert r["situacao"] == "aviso_de_intimacao"


def test_tempo_esgotado_na_geracao_explica_o_que_aconteceu(tmp_path, monkeypatch):
    """'Timeout waiting for event download' mandava procurar no lugar errado: o
    portal nao estava parado, estava montando o PDF."""
    from justica_mcp import esaj as esaj_mod

    monkeypatch.setattr(esaj_mod, "TETO_DE_GERACAO", 0)
    janela = _JanelaQueGera()
    r = copiar_autos_pelo_visualizador(
        _PaginaComAutos(janela), _guarda(), tmp_path, "123", 0
    )
    assert r["situacao"] == "sem_arquivo"
    assert "montando o PDF" in r["detalhe"]
    assert "--segundos" in r["detalhe"]


def test_lista_de_alvos_proibidos_nao_pode_ser_clicada_nem_por_engano(tmp_path):
    """Trava de bancada: uma lista montada errado nao pode virar um e-mail com
    os autos do cliente."""
    import pytest

    from justica_mcp.esaj import NUNCA_CLICAR, _clicar_na_pasta

    for proibido in NUNCA_CLICAR:
        with pytest.raises(AssertionError):
            _clicar_na_pasta(_Janela(), _guarda(), (proibido,), "proibido")
