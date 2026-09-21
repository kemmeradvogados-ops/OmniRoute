"""Resolucao do sistema pela declaracao da base nacional.

Estrutura confirmada em campo em 21 de setembro de 2026:
    sistema = {'codigo': 1, 'nome': 'PJe'}
    formato = {'codigo': 1, 'nome': 'Eletrônico'}

Apenas o codigo 1 foi observado. Por isso o casamento e feito pelo NOME
normalizado e nunca pelo codigo: montar uma tabela de codigos a partir de uma
unica amostra seria chute com aparencia de mapeamento.
"""

from datetime import datetime, timedelta, timezone

import pytest

from justica_mcp.core.resolver import sistema_de_documento
from justica_mcp.core.tribunais import identificar_tribunal


def _quando(dias_atras: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).isoformat().replace(
        "+00:00", "Z"
    )


def _doc(nome="PJe", dias_atras=1, codigo=1):
    return {
        "sistema": {"codigo": codigo, "nome": nome},
        "dataHoraUltimaAtualizacao": _quando(dias_atras),
    }


TJRJ = identificar_tribunal("8.19")   # PJe, eproc e DCP em migracao
TRT1 = identificar_tribunal("5.01")   # so PJe
TJSP = identificar_tribunal("8.26")   # e-SAJ e eproc em migracao


def test_le_o_sistema_declarado():
    r = sistema_de_documento(_doc(), TRT1)
    assert r.sistema == "pje"
    assert r.origem_da_resolucao == "datajud"


def test_tribunal_sem_ambiguidade_e_ficha_recente_da_confianca_alta():
    assert sistema_de_documento(_doc(dias_atras=1), TRT1).confianca.value == "alta"


def test_tribunal_em_migracao_nunca_recebe_confianca_alta():
    """Rio e Sao Paulo sao exatamente onde a base nacional pode estar atrasada
    em relacao a uma migracao ja ocorrida. E onde errar custa mais caro."""
    r = sistema_de_documento(_doc(dias_atras=0), TJRJ)
    assert r.confianca.value == "media"
    assert "migracao" in r.motivo
    assert sistema_de_documento(_doc(dias_atras=0), TJSP).confianca.value != "alta"


def test_ficha_antiga_rebaixa_a_confianca():
    assert sistema_de_documento(_doc(dias_atras=400), TRT1).confianca.value == "media"


def test_data_ausente_ou_invalida_nao_quebra():
    assert sistema_de_documento({"sistema": {"nome": "PJe"}}, TRT1).confianca.value == "media"
    doc = {"sistema": {"nome": "PJe"}, "dataHoraUltimaAtualizacao": "nao-e-data"}
    assert sistema_de_documento(doc, TRT1).sistema == "pje"


@pytest.mark.parametrize(
    "nome,esperado",
    [("PJe", "pje"), ("pje", "pje"), ("eproc", "eproc"), ("e-SAJ", "esaj"),
     ("SAJ", "esaj"), ("DCP", "dcp"), ("  PJe  ", "pje")],
)
def test_casa_por_nome_normalizado(nome, esperado):
    assert sistema_de_documento(_doc(nome=nome), TRT1).sistema == esperado


def test_nome_desconhecido_nao_vira_chute():
    """Sistema fora do mapa devolve indeterminado dizendo o que a fonte
    respondeu, para o operador conferir e incluir, em vez de forcar um palpite."""
    r = sistema_de_documento(_doc(nome="SistemaNovo"), TRT1)
    assert r.sistema == "indeterminado"
    assert "SistemaNovo" in r.motivo
    assert r.confianca.value == "baixa"


def test_documento_sem_campo_sistema_devolve_nada():
    assert sistema_de_documento({}, TRT1) is None
    assert sistema_de_documento({"sistema": {}}, TRT1) is None
    assert sistema_de_documento({"sistema": "PJe"}, TRT1) is None


def test_a_data_da_ficha_aparece_no_motivo():
    """O agente precisa poder dizer ao advogado o quao velha e a informacao."""
    r = sistema_de_documento(_doc(dias_atras=5), TRT1)
    assert "atualizada em" in r.motivo
