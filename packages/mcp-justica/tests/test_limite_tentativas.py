"""Teto de tentativas de autenticacao.

Ate a Fase 2 a protecao contra bloqueio de conta era a confirmacao na linha de
comando: um humano digitava a opcao a cada execucao. Expor a autenticacao como
ferramenta do servidor quebra essa premissa, porque um agente que tente de novo
diante de erro queima as tentativas da conta em segundos, sem ninguem no meio.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from justica_mcp.core.estado import Estado
from justica_mcp.core.limite_tentativas import (
    LimiteTentativas, TetoDeTentativasAtingido,
)


@pytest.fixture
def estado():
    return Estado(Path(tempfile.mkdtemp()) / "estado.sqlite3")


def _tentar(estado, quantas=1):
    for _ in range(quantas):
        estado.registrar(acao="login_etapa_credencial", resultado="enviado")


def test_permite_ate_o_teto(estado):
    limite = LimiteTentativas(estado, teto=3)
    for _ in range(3):
        limite.exigir_folga()
        _tentar(estado)
    assert limite.situacao()["restantes"] == 0


def test_bloqueia_ao_passar_do_teto(estado):
    limite = LimiteTentativas(estado, teto=2)
    _tentar(estado, 2)
    with pytest.raises(TetoDeTentativasAtingido, match="Teto de tentativas"):
        limite.exigir_folga()


def test_mensagem_orienta_a_conferir_a_credencial(estado):
    """Insistir com credencial errada e o caminho mais curto para o bloqueio."""
    limite = LimiteTentativas(estado, teto=1)
    _tentar(estado)
    with pytest.raises(TetoDeTentativasAtingido, match="corrija o cofre"):
        limite.exigir_folga()


def test_tentativa_fora_da_janela_nao_conta(estado):
    limite = LimiteTentativas(estado, teto=1, janela_minutos=30)
    antiga = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    with estado._conectar() as cx:
        cx.execute(
            "INSERT INTO auditoria (ocorrido_em, acao, resultado) VALUES (?,?,?)",
            (antiga, "login_etapa_credencial", "enviado"),
        )
    limite.exigir_folga()
    assert limite.situacao()["tentativas_na_janela"] == 0


def test_conta_tentativas_de_qualquer_tribunal(estado):
    """O bloqueio costuma ser por credencial, nao por sistema, e varias
    identidades podem compartilhar o mesmo cadastro."""
    limite = LimiteTentativas(estado, teto=2)
    estado.registrar(acao="login_etapa_credencial", tribunal="TRF2", resultado="enviado")
    estado.registrar(acao="login_etapa_credencial", tribunal="TJRJ", resultado="enviado")
    with pytest.raises(TetoDeTentativasAtingido):
        limite.exigir_folga()


def test_outras_acoes_nao_contam(estado):
    limite = LimiteTentativas(estado, teto=1)
    estado.registrar(acao="consulta_processo_autenticada", resultado="ok")
    estado.registrar(acao="resolver_sistema", resultado="cache")
    limite.exigir_folga()


def test_teto_vem_do_ambiente(estado, monkeypatch):
    monkeypatch.setenv("JUSTICA_TETO_TENTATIVAS", "2")
    monkeypatch.setenv("JUSTICA_JANELA_TENTATIVAS_MIN", "15")
    limite = LimiteTentativas.do_ambiente(estado)
    assert (limite.teto, limite.janela_minutos) == (2, 15)


def test_valor_invalido_no_ambiente_cai_no_padrao(estado, monkeypatch):
    monkeypatch.setenv("JUSTICA_TETO_TENTATIVAS", "zero")
    assert LimiteTentativas.do_ambiente(estado).teto == 6


# --------------------------------------------------------------------------
# O que conta como tentativa
#
# Dois defeitos encontrados em 21/09/2026, quando o teto barrou o operador
# depois de poucas execucoes. Os dois distorciam a contagem, em sentidos
# opostos, e os dois podiam terminar em conta bloqueada.
# --------------------------------------------------------------------------

def test_desfecho_da_etapa_nao_conta_como_segunda_tentativa(estado):
    """Uma unica tentativa gravava DOIS registros com o mesmo nome de acao, o
    envio e o desfecho, e consumia duas das seis. O advogado ficava sem acesso
    na metade das tentativas que acreditava ter."""
    estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    estado.registrar(acao="login_resultado_credencial", resultado="sem_tela_de_codigo")
    assert LimiteTentativas(estado=estado).situacao()["tentativas_na_janela"] == 1


def test_envio_unico_pelo_comando_entrar_tambem_conta(estado):
    """`entrar` envia senha de verdade ao portal. Ficava fora da contagem, e o
    bloqueio da conta nao distingue por qual comando a senha foi enviada."""
    estado.registrar(acao="login_tentativa_unica", resultado="enviado")
    assert LimiteTentativas(estado=estado).situacao()["tentativas_na_janela"] == 1


def test_os_dois_comandos_somam_no_mesmo_teto(estado):
    for _ in range(3):
        estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    for _ in range(3):
        estado.registrar(acao="login_tentativa_unica", resultado="enviado")
    with pytest.raises(TetoDeTentativasAtingido):
        LimiteTentativas(estado=estado).exigir_folga()


def test_destino_bloqueado_nao_conta_como_novo_envio(estado):
    """Envio e desfecho sao o mesmo ato: uma senha enviada. Contar o desfecho
    tiraria do advogado uma tentativa por algo que nao mandou senha nenhuma."""
    estado.registrar(acao="login_tentativa_unica", resultado="enviado")
    estado.registrar(acao="login_resultado_credencial", resultado="destino_bloqueado")
    assert LimiteTentativas(estado=estado).situacao()["tentativas_na_janela"] == 1


# --------------------------------------------------------------------------
# Sucesso zera o contador
#
# Decidido pelo operador em 22/09/2026, depois de o teto barra-lo duas vezes
# por trabalho legitimo. Bloqueio de conta vem de falhas CONSECUTIVAS, nao de
# login que deu certo: seis autenticacoes bem sucedidas numa hora nao ameacam
# conta nenhuma.
# --------------------------------------------------------------------------

def test_sucesso_zera_o_contador(estado):
    for _ in range(5):
        estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    estado.registrar(acao="login_sucesso", resultado="autenticado")
    assert LimiteTentativas(estado=estado).situacao()["tentativas_na_janela"] == 0


def test_tentativas_depois_do_sucesso_voltam_a_contar(estado):
    estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    estado.registrar(acao="login_sucesso", resultado="autenticado")
    estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    assert LimiteTentativas(estado=estado).situacao()["tentativas_na_janela"] == 2


def test_falhas_consecutivas_sem_sucesso_continuam_barrando(estado):
    """O teto existe contra o laco descontrolado. Zerar no sucesso nao pode
    enfraquecer isso: sem sucesso nenhum, seis falhas seguidas barram."""
    for _ in range(6):
        estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    with pytest.raises(TetoDeTentativasAtingido):
        LimiteTentativas(estado=estado).exigir_folga()


def test_sucesso_antigo_nao_apaga_falhas_recentes(estado):
    """Um sucesso de ontem nao pode absolver uma sequencia de falhas de agora:
    o corte e o mais recente entre o inicio da janela e o ultimo sucesso."""
    estado.registrar(acao="login_sucesso", resultado="autenticado")
    for _ in range(6):
        estado.registrar(acao="login_etapa_credencial", resultado="enviado")
    with pytest.raises(TetoDeTentativasAtingido):
        LimiteTentativas(estado=estado).exigir_folga()
