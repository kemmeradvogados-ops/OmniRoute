"""Cofre de credenciais da Fase 2.

A invariante que importa: o segredo nunca chega ao modelo. O adaptador le no
instante da chamada; nenhuma ferramenta, log ou relatorio devolve senha,
semente ou codigo de segundo fator.
"""

import json

import pytest

from justica_mcp.core.cofre import (
    Cofre, CofreIndisponivel, CredencialAusente, Identidade, SementeInvalida,
    normalizar_semente,
)

SENHA = "SenhaDoPortal!2026"
# 32 caracteres base32, no formato em que o portal exibe o QR Code.
SEMENTE = "ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567"


class BackendMemoria:
    def __init__(self, quebrado=False):
        self.d, self.quebrado = {}, quebrado

    def get_password(self, s, u):
        if self.quebrado:
            raise OSError("chaveiro indisponivel")
        return self.d.get((s, u))

    def set_password(self, s, u, p):
        if self.quebrado:
            raise OSError("chaveiro indisponivel")
        self.d[(s, u)] = p

    def delete_password(self, s, u):
        self.d.pop((s, u), None)


@pytest.fixture
def cofre():
    return Cofre(BackendMemoria())


@pytest.fixture
def tjrj():
    return Identidade("TJRJ", "eproc")


# ---------------- identidade ----------------

def test_identidade_normaliza_caixa():
    assert Identidade("tjrj", "EPROC").chave == "TJRJ:eproc"
    assert Identidade(" tjrj ", " eproc ").chave == "TJRJ:eproc"


# ---------------- a invariante ----------------

def test_situacao_nunca_devolve_o_segredo(cofre, tjrj):
    """`situacao` alimenta ferramenta e relatorio. Se vazasse, a credencial
    entraria no contexto do modelo, que e exatamente o que o projeto proibe."""
    cofre.guardar_login(tjrj, "11122233344")
    cofre.guardar_senha(tjrj, SENHA)
    cofre.guardar_semente(tjrj, SEMENTE)
    serializada = json.dumps(cofre.situacao(tjrj))
    assert SENHA not in serializada
    assert SEMENTE.replace(" ", "") not in serializada
    assert "11122233344" not in serializada, "o login tambem e dado pessoal"
    assert cofre.situacao(tjrj)["pronta_para_uso"] is True


def test_repr_do_cofre_nao_expoe_conteudo(cofre, tjrj):
    cofre.guardar_senha(tjrj, SENHA)
    assert SENHA not in repr(cofre)


def test_senha_e_semente_ficam_em_entradas_separadas(cofre, tjrj):
    """Juntas equivalem a conta inteira: o segundo fator deixa de ser segundo
    fator quando viaja ao lado da senha. Foi o defeito da planilha original."""
    cofre.guardar_senha(tjrj, SENHA)
    assert cofre.tem_senha(tjrj) is True
    assert cofre.tem_semente(tjrj) is False, "gravar a senha nao pode trazer a semente junto"


# ---------------- semente ----------------

def test_aceita_semente_no_formato_do_portal():
    """O QR Code e transcrito em grupos de quatro. Espaco e ruido, nao conteudo."""
    assert normalizar_semente(SEMENTE) == "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    assert normalizar_semente("abcd-efgh-ijkl-mnop-qrst-uvwx-yz23-4567") == (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    )


@pytest.mark.parametrize("ruim", ["", "   ", "ABC"])
def test_recusa_semente_vazia_ou_curta(ruim):
    with pytest.raises(SementeInvalida):
        normalizar_semente(ruim)


def test_recusa_caractere_fora_do_base32():
    """0, 1 e 8 nao existem em base32 e sao confusao comum com O, I e B."""
    with pytest.raises(SementeInvalida, match="base32"):
        normalizar_semente("ABCD0189 EFGH IJKL MNOP QRST UVWX YZ23 4567")


def test_gera_codigo_de_seis_digitos(cofre, tjrj):
    cofre.guardar_semente(tjrj, SEMENTE)
    codigo = cofre._codigo_segundo_fator(tjrj)
    assert len(codigo) == 6 and codigo.isdigit()


# ---------------- ausencia e falha ----------------

def test_credencial_ausente_ensina_o_comando(cofre, tjrj):
    with pytest.raises(CredencialAusente, match="justica-credenciais guardar"):
        cofre._senha(tjrj)
    with pytest.raises(CredencialAusente, match="Semente"):
        cofre._codigo_segundo_fator(tjrj)


def test_senha_vazia_nao_e_gravada(cofre, tjrj):
    with pytest.raises(ValueError):
        cofre.guardar_senha(tjrj, "   ")
    assert cofre.tem_senha(tjrj) is False


def test_cofre_quebrado_da_mensagem_util_em_vez_de_traceback(tjrj):
    """Sem isto a falha sobe como traceback bruto, inutil para quem opera."""
    quebrado = Cofre(BackendMemoria(quebrado=True))
    assert quebrado.disponivel() is False
    with pytest.raises(CofreIndisponivel, match="Gerenciador de Credenciais"):
        quebrado.tem_senha(tjrj)


def test_remover_apaga_tudo(cofre, tjrj):
    cofre.guardar_login(tjrj, "11122233344")
    cofre.guardar_senha(tjrj, SENHA)
    cofre.guardar_semente(tjrj, SEMENTE)
    assert sorted(cofre.remover(tjrj)) == ["login", "semente", "senha"]
    assert cofre.situacao(tjrj)["pronta_para_uso"] is False


def test_prontidao_nao_exige_segundo_fator(cofre, tjrj):
    """Nem todo portal usa segundo fator. Esta confirmado para o eproc, que o
    exige de usuario externo desde abril de 2024, mas para os demais nao ha
    confirmacao. Exigir de todos marcaria como incompleta uma credencial que
    funciona perfeitamente."""
    cofre.guardar_login(tjrj, "11122233344")
    cofre.guardar_senha(tjrj, SENHA)
    situacao = cofre.situacao(tjrj)
    assert situacao["pronta_para_uso"] is True
    assert situacao["semente_guardada"] is False


def test_codigo_espera_a_proxima_janela_quando_esta_acabando(cofre, tjrj, monkeypatch):
    """O codigo vale 30 segundos. Gerado a dois segundos do fim, expira entre o
    preenchimento e o envio, e o portal registra tentativa falha por um motivo
    que nao e culpa da credencial. Esperar custa segundos; a tentativa perdida
    custa mais."""
    import time as modulo_tempo

    cofre.guardar_semente(tjrj, SEMENTE)
    dormiu = []
    monkeypatch.setattr(modulo_tempo, "sleep", lambda s: dormiu.append(s))
    # Instante escolhido para cair no fim da janela: 1000000018 % 30 == 28,
    # logo restam 2 segundos dos 30.
    monkeypatch.setattr(modulo_tempo, "time", lambda: 1_000_000_018)

    cofre._codigo_segundo_fator(tjrj, minimo_segundos=8)
    assert dormiu, "deveria ter aguardado a proxima janela"


def test_codigo_nao_espera_com_janela_folgada(cofre, tjrj, monkeypatch):
    import time as modulo_tempo

    cofre.guardar_semente(tjrj, SEMENTE)
    dormiu = []
    monkeypatch.setattr(modulo_tempo, "sleep", lambda s: dormiu.append(s))
    # 1000000001 % 30 == 11, logo restam 19 segundos: folga suficiente.
    monkeypatch.setattr(modulo_tempo, "time", lambda: 1_000_000_001)

    cofre._codigo_segundo_fator(tjrj, minimo_segundos=8)
    assert not dormiu
