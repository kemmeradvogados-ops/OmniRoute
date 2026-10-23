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
# DETECTAR a repeticao e util, e o sintoma esconde a causa: o comando que
# confere diz que a semente bate com o aplicativo, porque bate mesmo, sem
# dizer com a entrada de QUAL tribunal.
#
# CONCLUIR a partir dela era erro, e o advogado o corrigiu em 22/10/2026. O
# aviso dizia "cada cadastro de autenticador gera a sua, entao duas contas
# nunca tem a mesma" e afirmava que uma fora gravada por cima da outra. Nao e
# verdade como regra: sistema nacional atende instalacoes de varios tribunais
# com UMA identidade, e ai a semente e a mesma de propósito. Foi o caso do PJe
# do Rio de Janeiro e do PJe do Tribunal Regional do Trabalho da 1a Regiao.
#
# O alarme falso teve preco: levou a regravar uma semente que funcionava. O
# aviso passa a relatar o fato e oferecer as duas leituras.
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


def test_o_aviso_de_semente_repetida_nao_acusa_defeito():
    """Guarda de fonte, e ela protege contra um dano concreto.

    Ate 22/10/2026 este aviso afirmava que duas contas nunca tem a mesma
    semente e que uma fora gravada por cima da outra. O advogado leu, acreditou
    e REGRAVOU uma semente que funcionava, porque o PJe do Rio de Janeiro e o
    do Tribunal Regional do Trabalho da 1a Regiao compartilham o cadastro.

    O programa nao tem como saber se dois portais compartilham identidade.
    Quem tem e o advogado, e o aviso precisa deixar a conclusao com ele.
    """
    import inspect

    from justica_mcp import credenciais

    fonte = inspect.getsource(credenciais)
    trecho = fonte.split("onde_mais_esta_esta_semente(identidade")[1][:2000]
    sem_comentario = "\n".join(
        linha for linha in trecho.splitlines()
        if not linha.strip().startswith("#"))
    assert "duas contas nunca" not in sem_comentario
    assert "ATENCAO" not in sem_comentario
    assert "NORMAL" in sem_comentario
    assert "DEFEITO" in sem_comentario


def test_a_senha_diz_QUAL_senha_antes_de_pedir():
    """Guarda de fonte. Em 22/10/2026 o advogado colou a semente no lugar da
    senha, e o motivo estava na tela: o trecho da semente explicava o que era
    ("o codigo longo do QR Code, com 32 caracteres, e nao o codigo de 6
    digitos") e o da senha nao dizia nada. Silencio de um lado, ao lado da
    explicacao do outro, sugere que os dois sao a mesma coisa.

    O engano custa caro: senha errada so se descobre TENTANDO o login, que
    gasta tentativa do teto, e tentativas erradas seguidas bloqueiam a conta.
    """
    import inspect

    from justica_mcp import credenciais

    fonte = inspect.getsource(credenciais)
    trecho = fonte.split('pedir_segredo("Senha do portal"')[0][-1200:]
    sem_comentario = "\n".join(
        linha for linha in trecho.splitlines()
        if not linha.strip().startswith("#"))
    assert "NAO e a semente" in sem_comentario
    assert "6 digitos" in sem_comentario
