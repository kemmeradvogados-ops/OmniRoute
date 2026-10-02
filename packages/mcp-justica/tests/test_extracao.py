"""Extracao das tabelas da tela de processo do eproc.

Estrutura reproduzida da observada em campo em 21 de setembro de 2026, na
Justica Federal do Rio: `tblEventos` com Evento, Data/Hora, Descricao, Usuario
e Documentos; `tblPartesERepresentantes` com os polos como CABECALHO; e a
tabela de assuntos sem identificador, achada pelos rotulos das colunas.

Os dubles dispensam navegador: a extracao e logica de leitura, e testa-la
contra um navegador real tornaria a suite lenta e dependente de rede.
"""

from justica_mcp.extracao import (
    extrair_assuntos, extrair_eventos, extrair_partes, extrair_processo, resumo,
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


def _celula(texto="", links=()):
    return _El(texto, {"a": list(links)})


def _link(rotulo, endereco):
    return _El(rotulo, atributos={"href": endereco})


def _linha(celulas):
    return _El(filhos={"td": celulas})


class _Tabela(_El):
    def __init__(self, titulos=(), linhas=(), identificador=None):
        super().__init__(
            filhos={"th": [_El(t) for t in titulos], "tr": list(linhas)},
            atributos={"id": identificador},
        )


class _Pagina:
    def __init__(self, tabelas):
        self._tabelas = tabelas
        self.url = "https://eproc.exemplo/processo"

    def title(self):
        return ":: eproc - Detalhes do Processo ::"

    def query_selector(self, seletor):
        alvo = seletor.lstrip("#")
        for t in self._tabelas:
            if t.get_attribute("id") == alvo:
                return t
        return None

    def query_selector_all(self, seletor):
        return list(self._tabelas) if seletor == "table" else []


EVENTOS = _Tabela(
    titulos=("Evento", "Data/Hora", "Descrição", "Usuário", "Documentos"),
    linhas=[
        _linha([_celula("69"), _celula("18/09/2026 14:02"),
                _celula("Conclusos para decisão"), _celula("SERVIDOR1"), _celula()]),
        _linha([_celula("68"), _celula("15/09/2026 09:31"),
                _celula("Juntada de petição"), _celula("ADVOGADO"),
                _celula(links=[_link("PET1", "/doc?id=1"), _link("ANEXO1", "/doc?id=2")])]),
    ],
    identificador="tblEventos",
)

PARTES = _Tabela(
    titulos=("AUTOR", "RÉU"),
    linhas=[_linha([_celula("FULANO DE TAL"), _celula("UNIAO FEDERAL")])],
    identificador="tblPartesERepresentantes",
)

ASSUNTOS = _Tabela(
    titulos=("Código", "Descrição", "Principal"),
    linhas=[_linha([_celula("10064"), _celula("Benefício Assistencial"), _celula("Sim")])],
)


def _pagina():
    return _Pagina([ASSUNTOS, PARTES, EVENTOS])


# ---------------- eventos ----------------

def test_extrai_eventos_com_as_cinco_colunas():
    eventos = extrair_eventos(_pagina())
    assert len(eventos) == 2
    assert eventos[0]["evento"] == "69"
    assert eventos[0]["data_hora"] == "18/09/2026 14:02"
    assert eventos[0]["descricao"] == "Conclusos para decisão"
    assert eventos[0]["usuario"] == "SERVIDOR1"


def test_lista_documentos_sem_abrir_nenhum():
    """A coluna Documentos traz os links dos arquivos. Aqui eles sao apenas
    listados, com rotulo e endereco: abrir e outro ato, e outra decisao."""
    eventos = extrair_eventos(_pagina())
    assert eventos[0]["documentos"] == []
    assert eventos[1]["documentos"] == [
        {"rotulo": "PET1", "endereco": "/doc?id=1"},
        {"rotulo": "ANEXO1", "endereco": "/doc?id=2"},
    ]


def test_pagina_sem_tabela_de_eventos_devolve_lista_vazia():
    assert extrair_eventos(_Pagina([PARTES])) == []


# ---------------- partes ----------------

def test_polo_vem_do_cabecalho_e_nao_de_uma_coluna():
    """A tabela usa AUTOR e REU como cabecalho das colunas, entao cada celula
    pertence ao polo da sua posicao. Ler como coluna de valor inverteria os
    polos, que e um erro grave num resumo processual."""
    partes = extrair_partes(_pagina())
    assert partes == [
        {"polo": "AUTOR", "conteudo": "FULANO DE TAL"},
        {"polo": "RÉU", "conteudo": "UNIAO FEDERAL"},
    ]


def test_celula_vazia_nao_vira_parte():
    tabela = _Tabela(titulos=("AUTOR", "RÉU"),
                     linhas=[_linha([_celula("SO O AUTOR"), _celula("  ")])],
                     identificador="tblPartesERepresentantes")
    assert extrair_partes(_Pagina([tabela])) == [
        {"polo": "AUTOR", "conteudo": "SO O AUTOR"},
    ]


# ---------------- assuntos ----------------

def test_acha_assuntos_pelos_rotulos_das_colunas():
    """Essa tabela nao tem identificador na tela real."""
    assert extrair_assuntos(_pagina()) == [
        {"codigo": "10064", "descricao": "Benefício Assistencial", "principal": "Sim"},
    ]


# ---------------- conjunto ----------------

def test_totais_somam_os_documentos_de_todos_os_eventos():
    dados = extrair_processo(_pagina(), "5068456-68.2025.4.02.5101")
    assert dados["totais"] == {
        "eventos": 2, "partes": 2, "assuntos": 1, "documentos_listados": 2,
    }


def test_resumo_mostra_contagens_e_os_mais_recentes():
    """O resumo e o que vai para o terminal. O conteudo completo fica em
    arquivo, porque despejar dezenas de eventos na tela convida a colar dado
    de cliente onde nao deve."""
    linhas = resumo(extrair_processo(_pagina(), "x"), ultimos=1)
    texto = "\n".join(linhas)
    assert "eventos: 2" in texto
    assert "Conclusos para decisão" in texto
    assert "Juntada de petição" not in texto, "o resumo respeita o limite pedido"


# ==========================================================================
# A tela do eproc monta depois da rede
#
# Visto em campo em 02/10/2026: a leitura devolveu "Tabelas na pagina: []" numa
# tela que, lida logo depois, tinha `#tblEventos` com 68 linhas de evento. O
# defeito nao estava na extracao; estava no instante da leitura.
# ==========================================================================

from justica_mcp.extracao import (  # noqa: E402
    ANCORAS_DA_TELA, LINHAS_DE_EVENTO, esperar_tela_do_processo,
)


class _TelaQueDemora:
    """Conta as esperas e responde conforme o que ja teria montado."""

    def __init__(self, tem_ancora=True, tem_eventos=True):
        self.tem_ancora, self.tem_eventos = tem_ancora, tem_eventos
        self.pedidos = []

    def wait_for_selector(self, seletor, timeout=None, state=None):
        self.pedidos.append((seletor, timeout))
        if seletor == ANCORAS_DA_TELA and not self.tem_ancora:
            raise TimeoutError("nao apareceu")
        if seletor == LINHAS_DE_EVENTO and not self.tem_eventos:
            raise TimeoutError("nao apareceu")
        return object()


def test_espera_a_capa_e_depois_as_linhas_de_evento():
    tela = _TelaQueDemora()
    assert esperar_tela_do_processo(tela, 40) == "eventos"
    assert [p[0] for p in tela.pedidos] == [ANCORAS_DA_TELA, LINHAS_DE_EVENTO]


def test_capa_sem_evento_e_dito_com_todas_as_letras():
    """Processo recem-autuado existe e nao tem evento. Chamar isso de 'nada'
    mandaria o operador procurar defeito onde ha so um processo novo."""
    tela = _TelaQueDemora(tem_eventos=False)
    assert esperar_tela_do_processo(tela, 40) == "capa"


def test_tela_que_nao_aparece_devolve_nada_e_nao_levanta_erro():
    """Quem chama precisa seguir para o relato da tela, que e o que permite
    escrever a leitura certa depois."""
    tela = _TelaQueDemora(tem_ancora=False)
    assert esperar_tela_do_processo(tela, 40) == "nada"
    assert len(tela.pedidos) == 1


def test_a_espera_das_linhas_e_menor_que_a_da_capa():
    """A capa ja esta na tela: esperar o mesmo tanto de novo dobraria a espera
    de uma tela que talvez nao tenha evento nenhum."""
    tela = _TelaQueDemora()
    esperar_tela_do_processo(tela, 40)
    capa, eventos = tela.pedidos[0][1], tela.pedidos[1][1]
    assert eventos < capa


def test_espera_curta_nao_vira_espera_de_zero():
    tela = _TelaQueDemora()
    esperar_tela_do_processo(tela, 2)
    assert tela.pedidos[1][1] >= 5000
