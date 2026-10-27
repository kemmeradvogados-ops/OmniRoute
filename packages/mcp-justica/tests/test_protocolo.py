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


def _sem_lancador(monkeypatch):
    """Nenhum lancador a medir: o veredito cai no tempo do Python.

    Imita a maquina em que o `node` nao esta no caminho, que e situacao real
    e precisa continuar produzindo relato util.
    """
    monkeypatch.setattr(
        protocolo, "medir_pelo_lancador",
        lambda *a, **k: {"respondeu": None, "segundos": None,
                         "motivo": "nao ha lancador"})


def _lancador(monkeypatch, segundos):
    monkeypatch.setattr(
        protocolo, "medir_pelo_lancador",
        lambda *a, **k: {"respondeu": True, "segundos": segundos, "motivo": ""})


def _ok(versoes=("2026-07-28",)):
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"supportedVersions": list(versoes)}}


def test_rapido_pelo_lancador_diz_que_deveria_funcionar(monkeypatch):
    _lancador(monkeypatch, 0.09)
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(8.5, resposta=_ok()))
    r = protocolo.relatorio()
    # O ponto da mudanca de 27/10/2026: o Python lento NAO condena mais a
    # extensao, porque quem responde a sonda e o lancador.
    assert "com folga" in r["veredito"]
    assert "8.50s para subir" in r["veredito"]
    assert r["versoes_declaradas"] == ["2026-07-28"]


def test_sem_lancador_o_relato_usa_o_tempo_do_python(monkeypatch):
    _sem_lancador(monkeypatch)
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(3.6, resposta=_ok()))
    r = protocolo.relatorio()
    assert "nao ha lancador" in r["veredito"]
    assert "3.60s" in r["veredito"]


def test_lento_nos_dois_caminhos_explica_e_da_o_contorno(monkeypatch):
    _lancador(monkeypatch, 9.0)
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(5.2, resposta=_ok()))
    r = protocolo.relatorio()
    assert "ALEM" in r["veredito"]
    # Sem o contorno a equipe conclui que a extensao esta quebrada.
    assert "noutra conversa" in r["veredito"]
    # E NAO nomeia Cowork nem Code: em 26/10/2026 uma conversa comum tambem
    # falhou, entao atribuir a falha a essas sessoes era afirmar o que nao
    # se verificou.
    assert "Cowork" not in r["veredito"]


def test_sem_resposta_nao_e_tratado_como_lentidao(monkeypatch):
    _sem_lancador(monkeypatch)
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(None, respondeu=False))
    r = protocolo.relatorio()
    assert "defeito de instalacao" in r["veredito"]
    assert r["segundos"] is None


def test_erro_do_servidor_nao_vira_sucesso(monkeypatch):
    erro = {"jsonrpc": "2.0", "id": 1,
            "error": {"code": -32602, "message": "faltou chave"}}
    _sem_lancador(monkeypatch)
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(0.5, resposta=erro))
    r = protocolo.relatorio()
    assert "erro" in r["veredito"].lower()
    assert "com folga" not in r["veredito"]


def test_o_veredito_nunca_fala_de_versao_publicada(monkeypatch):
    # O erro que originou este arquivo. Se alguem reintroduzir a pergunta
    # errada, este teste cai.
    _lancador(monkeypatch, 9.0)
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(5.2, resposta=_ok()))
    texto = protocolo.relatorio()["veredito"].lower()
    for proibido in ("versao mais nova", "atualizar", "publicad"):
        assert proibido not in texto


def test_mostrar_imprime_e_devolve_zero(capsys, monkeypatch):
    _lancador(monkeypatch, 0.09)
    monkeypatch.setattr(protocolo, "medir_sonda",
                        lambda *a, **k: _medida(0.9, resposta=_ok()))
    assert protocolo.mostrar() == 0
    saida = capsys.readouterr().out
    assert protocolo.revisao_servida() in saida
    # Os DOIS caminhos aparecem, e nomeados: quem le precisa saber que o
    # tempo do Python e o do lancador medem coisas diferentes.
    assert "Servidor Python responde em" in saida
    assert "Pelo lancador" in saida


def test_a_sonda_de_verdade_responde_e_declara_a_revisao():
    """Sem simulacao: sobe o servidor num processo novo e mede."""
    medida = protocolo.medir_sonda()
    assert medida["respondeu"], "o servidor nao respondeu a `server/discover`"
    corpo = medida["resposta"] or {}
    assert "error" not in corpo, corpo.get("error")
    versoes = corpo["result"]["supportedVersions"]
    assert protocolo.revisao_servida() in versoes


def test_a_sonda_pelo_lancador_responde_de_verdade():
    """Sem simulacao: sobe o lancador e mede. Pulado onde nao ha `node`."""
    import pytest

    medida = protocolo.medir_pelo_lancador()
    if medida.get("respondeu") is None:
        pytest.skip(medida.get("motivo") or "lancador indisponivel")
    assert medida["respondeu"], "o lancador nao respondeu a sonda"
    assert medida["segundos"] < protocolo.JANELA_DA_SONDA_S
