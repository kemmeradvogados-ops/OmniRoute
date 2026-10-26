"""A conferencia da sonda de era.

Em 26/10/2026 o aplicativo do Claude recusou a extensao nas sessoes do Cowork
e do Code. O primeiro diagnostico foi que faltava uma revisao de protocolo a
publicar, e estava ERRADO: a revisao atual da especificacao e a mesma que
este servidor serve, e o servidor responde a ela corretamente. O que falha e
o PRAZO: o aplicativo concede quatro segundos e, na maquina onde isso foi
investigado, so carregar a biblioteca levava de 2,6s a 4,5s.

Estes testes guardam o veredito contra o retorno daquele erro: ele fala de
tempo medido, nunca de versao publicada, e nunca afirma causa que ninguem
mediu.
"""

import json

from justica_mcp.core import protocolo


def test_a_revisao_servida_e_a_da_biblioteca():
    from mcp.types import LATEST_PROTOCOL_VERSION

    assert protocolo.revisao_servida() == str(LATEST_PROTOCOL_VERSION)


def test_moderna_e_aperto_de_mao_sao_conjuntos_separados():
    r = protocolo.revisoes_conhecidas()
    assert protocolo.revisao_servida() in r["modernas"]
    assert protocolo.revisao_servida() not in r["com_aperto_de_mao"]


def test_o_pedido_leva_as_duas_chaves_exigidas():
    # Sem `clientCapabilities` o servidor devolve -32602. Descoberto na marra
    # ao reproduzir a sonda pela primeira vez, e por isso tem teste.
    meta = json.loads(protocolo._pedido_de_sonda())["params"]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == protocolo.revisao_servida()
    assert "io.modelcontextprotocol/clientCapabilities" in meta


def _medida(segundos=None, respondeu=True, resposta=None):
    return {"respondeu": respondeu, "segundos": segundos, "resposta": resposta}


def _ok(versoes=("2026-07-28",)):
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"supportedVersions": list(versoes)}}


def test_rapido_com_folga_diz_que_deveria_funcionar(monkeypatch):
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(0.9, resposta=_ok()))
    r = protocolo.relatorio()
    assert "com folga" in r["veredito"]
    assert r["versoes_declaradas"] == ["2026-07-28"]


def test_dentro_do_limite_mas_na_linha_nao_declara_vitoria(monkeypatch):
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(3.6, resposta=_ok()))
    r = protocolo.relatorio()
    assert "SEM FOLGA" in r["veredito"]


def test_alem_do_limite_explica_que_o_atraso_e_a_causa(monkeypatch):
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(5.2, resposta=_ok()))
    r = protocolo.relatorio()
    assert "ALEM" in r["veredito"]
    assert "chega atrasado, nao fala errado" in r["veredito"]
    # As conversas comuns nao sao afetadas, e o veredito precisa dizer isso:
    # sem essa frase a equipe conclui que a extensao esta quebrada.
    assert "conversas comuns" in r["veredito"]


def test_sem_resposta_nao_e_tratado_como_lentidao(monkeypatch):
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(None, respondeu=False))
    r = protocolo.relatorio()
    assert "defeito de instalacao" in r["veredito"]
    assert r["segundos"] is None


def test_erro_do_servidor_nao_vira_sucesso(monkeypatch):
    erro = {"jsonrpc": "2.0", "id": 1,
            "error": {"code": -32602, "message": "faltou chave"}}
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(0.5, resposta=erro))
    r = protocolo.relatorio()
    assert "erro" in r["veredito"].lower()
    assert "com folga" not in r["veredito"]


def test_o_veredito_nunca_fala_de_versao_publicada(monkeypatch):
    # O erro que originou este arquivo. Se alguem reintroduzir a pergunta
    # errada, este teste cai.
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(5.2, resposta=_ok()))
    texto = protocolo.relatorio()["veredito"].lower()
    for proibido in ("versao mais nova", "atualizar", "publicad"):
        assert proibido not in texto


def test_mostrar_imprime_e_devolve_zero(capsys, monkeypatch):
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(0.9, resposta=_ok()))
    assert protocolo.mostrar() == 0
    saida = capsys.readouterr().out
    assert protocolo.revisao_servida() in saida
    assert "server/discover" in saida


def test_a_sonda_de_verdade_responde_e_declara_a_revisao():
    """Sem simulacao: sobe o servidor num processo novo e mede."""
    medida = protocolo.medir_sonda()
    assert medida["respondeu"], "o servidor nao respondeu a `server/discover`"
    corpo = medida["resposta"] or {}
    assert "error" not in corpo, corpo.get("error")
    versoes = corpo["result"]["supportedVersions"]
    assert protocolo.revisao_servida() in versoes
