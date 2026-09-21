"""A fronteira de somente leitura precisa ser estrutural, nao uma promessa."""

import pytest

from justica_mcp.core.capabilities import (
    MATRIZ, Capacidade, Declaracao, Situacao, adaptadores_para,
)
from justica_mcp.core.seguranca import FronteiraViolada, verificar_somente_leitura


def test_versao_1_sobe_somente_leitura():
    verificar_somente_leitura()


def test_habilitar_ciencia_por_engano_aborta_a_inicializacao(monkeypatch):
    """Dar ciencia consome prazo (lei nº. 11.419/06, artigo 5º, §3º).
    Se algum dia isso for declarado disponivel sem decisao expressa, o servidor
    deve se recusar a subir em vez de expor a ferramenta."""
    monkeypatch.setitem(
        MATRIZ["eproc"], Capacidade.DAR_CIENCIA_INTIMACAO,
        Declaracao(Situacao.DISPONIVEL, ""),
    )
    with pytest.raises(FronteiraViolada, match="somente leitura"):
        verificar_somente_leitura()


def test_nenhum_adaptador_da_ciencia_hoje():
    assert adaptadores_para(Capacidade.DAR_CIENCIA_INTIMACAO) == []


def test_busca_por_parte_nao_e_prometida_por_ninguem():
    """DataJud nao publica partes. Declarar isso evita que o agente invente
    uma explicacao quando a busca voltar vazia."""
    assert adaptadores_para(Capacidade.BUSCAR_POR_PARTE) == []


def test_integra_nao_e_prometida_na_fase_1():
    assert adaptadores_para(Capacidade.BAIXAR_INTEGRA) == []


def test_ferramenta_de_credenciais_nao_pode_devolver_segredo():
    """A ferramenta de situacao do cofre alimenta o contexto do modelo.
    Se algum dia passar a devolver valor, a credencial vaza para o chat.
    Este teste trava o formato: apenas presenca."""
    import json

    from justica_mcp.core.cofre import Cofre, Identidade

    class Memoria:
        def __init__(self):
            self.d = {}

        def get_password(self, s, u):
            return self.d.get((s, u))

        def set_password(self, s, u, p):
            self.d[(s, u)] = p

        def delete_password(self, s, u):
            self.d.pop((s, u), None)

    cofre = Cofre(Memoria())
    identidade = Identidade("TJRJ", "eproc")
    cofre.guardar_senha(identidade, "SenhaSecreta123!")
    cofre.guardar_semente(identidade, "ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567")

    saida = json.dumps([cofre.situacao(identidade)])
    assert "SenhaSecreta123!" not in saida
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" not in saida
    # E so pode conter estas chaves.
    assert set(cofre.situacao(identidade)) == {
        "identidade", "senha_guardada", "semente_guardada", "pronta_para_uso",
    }
