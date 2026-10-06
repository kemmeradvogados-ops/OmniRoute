"""Comando `justica-credenciais`."""

import pytest

from justica_mcp.credenciais import _pares_esperados, _resolver


def test_pares_esperados_vem_do_registro_de_tribunais():
    """A banca declarou credencial para PJe, eproc e DCP no Rio, eproc e e-SAJ em
    Sao Paulo, PJe no Tribunal Regional do Trabalho, eproc na Justica Federal e,
    desde 05/10/2026, a Central do Processo Eletronico do Superior Tribunal de
    Justica."""
    chaves = {i.chave for i in _pares_esperados()}
    assert chaves == {
        "TJRJ:pje", "TJRJ:eproc", "TJRJ:dcp",
        "TJSP:eproc", "TJSP:esaj", "TRT1:pje", "TRF2:eproc", "STJ:cpe",
    }


def test_resolver_aceita_par_previsto():
    assert _resolver("tjrj", "EPROC").chave == "TJRJ:eproc"


def test_esaj_de_sao_paulo_entrou_no_escopo():
    """Credencial fornecida em 21 de setembro de 2026. Cobre o acervo do
    Tribunal de Justica do Estado de Sao Paulo ainda nao migrado para o eproc."""
    assert _resolver("TJSP", "esaj").chave == "TJSP:esaj"


def test_resolver_recusa_par_fora_do_escopo():
    with pytest.raises(SystemExit, match="nao consta do escopo"):
        _resolver("TRT1", "eproc")


def test_resolver_recusa_tribunal_desconhecido():
    with pytest.raises(SystemExit):
        _resolver("TJMG", "pje")


# ==========================================================================
# Semente repetida em dois pares
#
# Cada cadastro de autenticador gera a sua semente, entao duas contas nunca
# tem a mesma. Semente repetida no cofre quer dizer que a de um portal foi
# gravada no lugar da de outro, e o sintoma esconde a causa: o comando que
# confere diz que ela bate com o aplicativo, porque bate mesmo, so que com a
# entrada do OUTRO tribunal.
# ==========================================================================

from justica_mcp.core.cofre import Cofre, Identidade, SERVICO_SEMENTE  # noqa: E402


class _CofreDeMentira:
    def __init__(self, sementes):
        self.sementes = sementes

    def get_password(self, servico, chave):
        if servico != SERVICO_SEMENTE:
            return None
        return self.sementes.get(chave)

    def set_password(self, servico, chave, valor):
        self.sementes[chave] = valor

    def delete_password(self, servico, chave):
        self.sementes.pop(chave, None)


SEMENTE_A = "JBSWY3DPEHPK3PXP"
SEMENTE_B = "KRSXG5CTMVRXEZLU"


def _cofre(sementes):
    return Cofre(backend=_CofreDeMentira(dict(sementes)))


def test_semente_repetida_em_outro_par_e_apontada():
    cofre = _cofre({"TJRJ:pje": SEMENTE_A, "TJRJ:eproc": SEMENTE_A})
    iguais = cofre.onde_mais_esta_esta_semente(
        Identidade("TJRJ", "pje"), _pares_esperados())
    assert iguais == [Identidade("TJRJ", "eproc").rotulo]


def test_sementes_diferentes_nao_acusam_nada():
    cofre = _cofre({"TJRJ:pje": SEMENTE_A, "TJRJ:eproc": SEMENTE_B})
    assert cofre.onde_mais_esta_esta_semente(
        Identidade("TJRJ", "pje"), _pares_esperados()) == []


def test_par_sem_semente_nao_e_comparado_com_ninguem():
    cofre = _cofre({"TJRJ:eproc": SEMENTE_A})
    assert cofre.onde_mais_esta_esta_semente(
        Identidade("TJRJ", "pje"), _pares_esperados()) == []


def test_o_proprio_par_nunca_entra_na_lista():
    cofre = _cofre({"TJRJ:pje": SEMENTE_A})
    assert cofre.onde_mais_esta_esta_semente(
        Identidade("TJRJ", "pje"), _pares_esperados()) == []


def test_a_semente_nunca_sai_na_comparacao():
    """Compara por resumo criptografico, e nem o resumo sai da funcao: o que
    volta e a conclusao, nao o valor."""
    cofre = _cofre({"TJRJ:pje": SEMENTE_A, "TJRJ:eproc": SEMENTE_A})
    devolvido = cofre.onde_mais_esta_esta_semente(
        Identidade("TJRJ", "pje"), _pares_esperados())
    assert all(SEMENTE_A not in texto for texto in devolvido)


def test_a_janela_do_codigo_muda_a_cada_trinta_segundos(monkeypatch):
    """Dois comandos dentro dos mesmos 30s geram o MESMO codigo, e o segundo
    seria recusado por ja ter sido consumido, com a semente certa."""
    import time as relogio

    cofre = _cofre({})
    tempos = iter([990, 1019, 1020])
    monkeypatch.setattr(relogio, "time", lambda: next(tempos))
    primeira = cofre.janela_do_codigo()
    assert cofre.janela_do_codigo() == primeira
    assert cofre.janela_do_codigo() == primeira + 1
