"""Numeracao unica: o digito verificador e a primeira barreira contra
consultar um numero transcrito errado e concluir que o processo nao existe."""

import pytest

from justica_mcp.core.cnj import (
    NumeroCNJInvalido, calcular_digito_verificador, parse_numero,
)


def test_digito_verificador_satisfaz_invariante_iso_7064():
    """MOD 97-10: NNNNNNN AAAA J TR OOOO DD deve deixar resto 1 na divisao por 97."""
    casos = [
        ("0000001", "2026", "8", "19", "0001"),
        ("1234567", "2019", "4", "02", "5101"),
        ("9999999", "2000", "5", "01", "0000"),
    ]
    for seq, ano, seg, trib, org in casos:
        dv = calcular_digito_verificador(seq, ano, seg, trib, org)
        assert int(f"{seq}{ano}{seg}{trib}{org}{dv}") % 97 == 1


def test_parse_aceita_com_e_sem_mascara():
    a = parse_numero("0000001-69.2026.8.19.0001")
    b = parse_numero("00000016920268190001")
    assert a == b
    assert a.formatado == "0000001-69.2026.8.19.0001"
    assert a.chave_segmento_tribunal == "8.19"


def test_digito_errado_e_recusado_em_vez_de_consultado():
    with pytest.raises(NumeroCNJInvalido, match="Digito verificador invalido"):
        parse_numero("0000001-99.2026.8.19.0001")


def test_numero_com_tamanho_errado_da_erro_explicito():
    with pytest.raises(NumeroCNJInvalido, match="20 digitos"):
        parse_numero("123456")


# --------------------------------------------------------------------------
# Grau de jurisdicao, deduzido do proprio numero
#
# Confirmado com dois processos reais do Tribunal de Justica de Sao Paulo em
# 21/09/2026. Portais separam as telas de primeiro e de segundo grau, e
# consultar no lugar errado devolve "nao encontrado", que se confunde com
# processo inexistente.
# --------------------------------------------------------------------------

def test_origem_zerada_e_segunda_instancia():
    n = parse_numero("2081722-17.2026.8.26.0000")
    assert n.grau == 2
    assert n.grau_nome == "segunda instancia"


def test_origem_com_unidade_e_primeira_instancia():
    n = parse_numero("1037850-62.2023.8.26.0100")
    assert n.grau == 1
    assert n.grau_nome == "primeira instancia"


def test_unidade_de_origem_diferente_continua_primeira_instancia():
    n = parse_numero("5068456-68.2025.4.02.5101")
    assert n.grau == 1


def test_o_grau_nao_depende_do_tribunal():
    """A regra e do numero, nao do tribunal: vale igual para qualquer
    segmento, e por isso nao precisa de tabela nenhuma."""
    for numero in ("0069900-31.1999.5.01.0009", "0998975-53.2025.8.19.0001"):
        assert parse_numero(numero).grau == 1
