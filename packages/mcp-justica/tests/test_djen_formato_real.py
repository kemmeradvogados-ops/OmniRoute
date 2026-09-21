"""Normalizacao do Diario contra o formato REAL da API.

O item abaixo reproduz a estrutura observada em campo em 21 de setembro de
2026, numa consulta feita da maquina do escritorio. Os valores foram
substituidos por conteudo neutro; os NOMES DOS CAMPOS sao os verdadeiros.
Antes disso o adaptador tinha sido escrito a partir de documentacao de
terceiro, e deixava de fora campos que importam.
"""

from justica_mcp.adapters.djen import TETO_CONTAGEM, AdaptadorDJEN

ITEM_REAL = {
    "id": 731754063,
    "data_disponibilizacao": "2026-09-21",
    "siglaTribunal": "TJRR",
    "tipoComunicacao": "Intimação",
    "nomeOrgao": "Vice Presidência",
    "idOrgao": 69503,
    "texto": "conteudo da publicacao",
    "numero_processo": "90040295020258230000",
    "meio": "D",
    "link": None,
    "tipoDocumento": "Decisão",
    "nomeClasse": "AGRAVO INTERNO CíVEL",
    "codigoClasse": "1208",
    "numeroComunicacao": 1892,
    "ativo": True,
    "hash": "2nqe4VJbYaLCaaqCzTn1d2PZKk7AgO",
    "status": "P",
    "motivo_cancelamento": None,
    "data_cancelamento": None,
    "datadisponibilizacao": "21/09/2026",
    "meiocompleto": "Diário de Justiça Eletrônico Nacional",
    "numeroprocessocommascara": "9004029-50.2025.8.23.0000",
    "destinatarios": [{"nome": "Fulano"}],
    # ATENCAO: a estrutura interna de `advogado` ainda NAO foi confirmada em
    # campo. Os nomes abaixo sao provisorios e o adaptador nao depende deles.
    # A confirmacao vem na proxima execucao do diagnostico.
    "destinatarioadvogados": [{"advogado": {"numero_oab": "218174", "uf_oab": "RJ"}}],
}


def test_captura_o_id_para_deduplicacao():
    """Sem identificador estavel nao da para dizer o que ja foi visto."""
    n = AdaptadorDJEN._normalizar(ITEM_REAL)
    assert n["id"] == 731754063
    assert n["numero_comunicacao"] == 1892


def test_captura_numero_cru_e_formatado():
    n = AdaptadorDJEN._normalizar(ITEM_REAL)
    assert n["numero_processo"] == "90040295020258230000"
    assert n["numero_processo_formatado"] == "9004029-50.2025.8.23.0000"


def test_captura_classe_e_orgao():
    n = AdaptadorDJEN._normalizar(ITEM_REAL)
    assert n["classe"] == "AGRAVO INTERNO CíVEL"
    assert n["codigo_classe"] == "1208"
    assert n["orgao"] == "Vice Presidência"


def test_publicacao_viva_nao_e_marcada_como_cancelada():
    n = AdaptadorDJEN._normalizar(ITEM_REAL)
    assert n["cancelada"] is False
    assert n["alerta"] is None


def test_publicacao_inativa_e_marcada_e_alerta():
    """Publicacao cancelada nao gera prazo. Trata-la como viva produz prazo
    fantasma no monitoramento, que e o pior erro possivel neste sistema."""
    n = AdaptadorDJEN._normalizar({**ITEM_REAL, "ativo": False})
    assert n["cancelada"] is True
    assert "CANCELADA" in n["alerta"]


def test_cancelamento_por_motivo_ou_data():
    assert AdaptadorDJEN._normalizar({**ITEM_REAL, "motivo_cancelamento": "erro"})["cancelada"]
    assert AdaptadorDJEN._normalizar({**ITEM_REAL, "data_cancelamento": "2026-09-20"})["cancelada"]


def test_status_bruto_e_repassado_sem_interpretacao():
    """O significado dos codigos de uma letra nao foi confirmado em fonte
    oficial, entao o campo viaja cru em vez de virar conclusao inventada."""
    n = AdaptadorDJEN._normalizar(ITEM_REAL)
    assert n["status_bruto"] == "P"


def test_contagem_saturada_e_declarada_como_estimativa():
    """A API satura `count` em 10000. Reportar isso como total exato faria o
    agente afirmar um numero falso e paginar ate um fim inexistente."""
    r = AdaptadorDJEN._resumo_total({"count": TETO_CONTAGEM}, [])
    assert r["total_e_estimativa"] is True
    assert "MAIOR OU IGUAL" in r["observacao_total"]


def test_contagem_pequena_e_tratada_como_exata():
    r = AdaptadorDJEN._resumo_total({"count": 35}, [])
    assert r["total_informado"] == 35
    assert r["total_e_estimativa"] is False
    assert r["observacao_total"] is None
