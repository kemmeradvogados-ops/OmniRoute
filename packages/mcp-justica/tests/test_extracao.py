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
