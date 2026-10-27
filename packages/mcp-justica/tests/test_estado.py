"""Cache, snapshots e auditoria."""

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

from justica_mcp.core.estado import Estado
from justica_mcp.core.resiliencia import (
    Disjuntor, EstadoDisjuntor, PortalIndisponivel,
)


@pytest.fixture
def estado():
    return Estado(Path(tempfile.mkdtemp()) / "estado.sqlite3")


def test_cache_vencido_volta_marcado_em_vez_de_sumir(estado):
    """Sumir em silencio faria o agente tratar dado velho como ausente."""
    estado.gravar_cache("k", {"a": 1}, timedelta(seconds=-1))
    registro = estado.obter_cache("k")
    assert registro is not None and registro["vencido"] is True


def test_snapshot_nao_duplica_quando_nada_mudou(estado):
    assert estado.gravar_snapshot("P", [{"m": 1}])["mudou"] is True
    assert estado.gravar_snapshot("P", [{"m": 1}])["mudou"] is False
    assert estado.gravar_snapshot("P", [{"m": 1}, {"m": 2}])["mudou"] is True


def test_diferenca_identifica_movimento_novo(estado):
    estado.gravar_snapshot("P", [{"data_hora": "2026-09-01", "codigo": 1, "nome": "a"}])
    anterior = estado.ultimo_snapshot("P")
    atuais = [
        {"data_hora": "2026-09-10", "codigo": 2, "nome": "b"},
        {"data_hora": "2026-09-01", "codigo": 1, "nome": "a"},
    ]
    vistos = {(m["data_hora"], m["codigo"], m["nome"]) for m in anterior["conteudo"]}
    novos = [m for m in atuais if (m["data_hora"], m["codigo"], m["nome"]) not in vistos]
    assert len(novos) == 1 and novos[0]["codigo"] == 2


def test_auditoria_registra_chamada(estado):
    estado.registrar(acao="consultar_processo", tribunal="TJRJ", numero="X", resultado="ok")
    registros = estado.auditoria_recente()
    assert len(registros) == 1 and registros[0]["acao"] == "consultar_processo"


def test_disjuntor_abre_e_recupera_sozinho():
    """Recuperacao preguicosa: ler o estado promove ABERTO para MEIO_ABERTO."""
    d = Disjuntor("portal", limite_falhas=2, espera_segundos=0.0)
    d.registrar_falha()
    d.registrar_falha()
    assert d.estado is EstadoDisjuntor.MEIO_ABERTO
    d.registrar_sucesso()
    assert d.estado is EstadoDisjuntor.FECHADO


def test_disjuntor_bloqueia_insistencia():
    d = Disjuntor("portal", limite_falhas=1, espera_segundos=60.0)
    d.registrar_falha()
    with pytest.raises(PortalIndisponivel, match="Nao insista"):
        d.exigir_passagem()


# --------------------------------------------------------------------------
# A auditoria precisa guardar a MENSAGEM, nao so o tipo.
#
# Em 26/10/2026 a consulta autenticada falhou tres vezes e o registro dizia
# apenas "RuntimeError". Esse e o tipo que o proprio codigo levanta em tres
# situacoes diferentes, entao o registro nao distinguia nenhuma delas e o
# diagnostico ficou parado esperando o operador colar a mensagem de volta.

from justica_mcp.core.estado import LIMITE_DO_DETALHE, detalhe_do_erro


def test_o_detalhe_traz_tipo_e_mensagem():
    d = detalhe_do_erro(RuntimeError("Consulta nao concluida (codigo 1)."))
    assert d.startswith("RuntimeError: ")
    assert "codigo 1" in d


def test_runtime_errors_diferentes_viram_detalhes_diferentes():
    # O ponto todo: antes os tres eram gravados como "RuntimeError".
    a = detalhe_do_erro(RuntimeError("Portal nao abriu"))
    b = detalhe_do_erro(RuntimeError("Consulta nao concluida (codigo 2)."))
    c = detalhe_do_erro(RuntimeError("Destino com termo de risco"))
    assert len({a, b, c}) == 3


def test_so_a_primeira_linha_entra():
    d = detalhe_do_erro(RuntimeError("primeira linha\nrastro de pilha\nmais"))
    assert "rastro" not in d
    assert d.endswith("primeira linha")


def test_sem_mensagem_devolve_o_tipo_sozinho():
    assert detalhe_do_erro(ValueError()) == "ValueError"


def test_mensagem_enorme_e_cortada():
    d = detalhe_do_erro(RuntimeError("x" * 5000))
    assert len(d) <= LIMITE_DO_DETALHE


# --------------------------------------------------------------------------
# "Nunca observei" nao e "nao pede".
#
# Sem semente e com janela oculta, `autenticar` recusava antes do login
# presumindo que haveria codigo a digitar. Para o eproc a presuncao vale; para
# o Portal de Servicos do Rio de Janeiro e falsa, e a recusa barrava uma
# consulta que teria funcionado. Quem decide passa a ser a auditoria.

def _estado_limpo(tmp_path):
    from justica_mcp.core.estado import Estado

    return Estado(tmp_path / "estado.sqlite3")


def test_sem_historico_a_resposta_e_nao_sei(tmp_path):
    e = _estado_limpo(tmp_path)
    assert e.portal_pede_segundo_fator("TJRJ", "dcp") is None


def test_portal_que_nao_pediu_codigo_e_reconhecido(tmp_path):
    e = _estado_limpo(tmp_path)
    e.registrar(acao="login_etapa_segundo_fator", tribunal="TJRJ",
                sistema="dcp", resultado="sem_segundo_fator")
    assert e.portal_pede_segundo_fator("TJRJ", "dcp") is False


def test_nao_solicitado_tambem_conta_como_nao_pede(tmp_path):
    e = _estado_limpo(tmp_path)
    e.registrar(acao="login_etapa_segundo_fator", tribunal="TJRJ",
                sistema="dcp", resultado="nao_solicitado")
    assert e.portal_pede_segundo_fator("TJRJ", "dcp") is False


def test_portal_que_pediu_codigo_e_reconhecido(tmp_path):
    e = _estado_limpo(tmp_path)
    e.registrar(acao="login_etapa_segundo_fator", tribunal="TJRJ",
                sistema="eproc", resultado="codigo_aceito")
    assert e.portal_pede_segundo_fator("TJRJ", "eproc") is True


def test_vale_a_observacao_mais_recente(tmp_path):
    # Portal que passa a exigir codigo precisa voltar a ser tratado assim.
    e = _estado_limpo(tmp_path)
    e.registrar(acao="login_etapa_segundo_fator", tribunal="TJRJ",
                sistema="dcp", resultado="sem_segundo_fator")
    e.registrar(acao="login_etapa_segundo_fator", tribunal="TJRJ",
                sistema="dcp", resultado="codigo_aceito")
    assert e.portal_pede_segundo_fator("TJRJ", "dcp") is True


def test_um_sistema_nao_responde_pelo_outro(tmp_path):
    e = _estado_limpo(tmp_path)
    e.registrar(acao="login_etapa_segundo_fator", tribunal="TJRJ",
                sistema="dcp", resultado="sem_segundo_fator")
    assert e.portal_pede_segundo_fator("TJRJ", "eproc") is None
