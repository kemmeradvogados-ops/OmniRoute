"""A conferencia da revisao de protocolo.

Em 26/10/2026 o aplicativo do Claude recusou a extensao nas sessoes do Cowork
e do Code porque a biblioteca `mcp` so serve a revisao `2026-07-28`. O que
destrava e uma versao nova da biblioteca, e conferir isso virou comando para
nao depender de alguem lembrar.

O que estes testes guardam, sobretudo: SEM REDE, o programa diz que nao
conseguiu olhar. Dizer "esta tudo atualizado" quando ninguem conseguiu
consultar seria afirmar o que nao se verificou.
"""

from justica_mcp.core import protocolo


def test_a_revisao_servida_e_a_da_biblioteca():
    from mcp.types import LATEST_PROTOCOL_VERSION

    assert protocolo.revisao_servida() == str(LATEST_PROTOCOL_VERSION)


def test_versoes_sao_comparadas_por_numero_e_nao_por_letra():
    # "2.10.0" < "2.3.0" como texto, e e o contrario como versao.
    assert protocolo._ordenar("2.10.0") > protocolo._ordenar("2.3.0")
    assert protocolo._ordenar("2.3.0") == protocolo._ordenar("2.3.0")
    assert protocolo._ordenar("2.3.1") > protocolo._ordenar("2.3.0")


def test_sem_rede_nao_vira_esta_atualizado(monkeypatch):
    monkeypatch.setattr(protocolo, "versao_publicada", lambda segundos=15: None)
    r = protocolo.relatorio()
    assert r["versao_publicada"] is None
    assert "nao consegui" in r["veredito"].lower()
    assert "atualizad" not in r["veredito"].lower()


def test_versao_mais_nova_convida_a_tentar_sem_prometer(monkeypatch):
    monkeypatch.setattr(protocolo, "versao_da_biblioteca", lambda: "2.3.0")
    monkeypatch.setattr(protocolo, "versao_publicada", lambda segundos=15: "2.4.0")
    r = protocolo.relatorio()
    assert "VALE TENTAR" in r["veredito"]
    # Nao promete conserto: so depois de instalar da para ver a revisao.
    assert "garante que resolve" in r["veredito"]


def test_ja_na_mais_nova_diz_que_nao_ha_o_que_fazer(monkeypatch):
    monkeypatch.setattr(protocolo, "versao_da_biblioteca", lambda: "2.3.0")
    monkeypatch.setattr(protocolo, "versao_publicada", lambda segundos=15: "2.3.0")
    r = protocolo.relatorio()
    assert "ja e a mais nova" in r["veredito"]


def test_versao_instalada_desconhecida_nao_inventa_comparacao(monkeypatch):
    monkeypatch.setattr(protocolo, "versao_da_biblioteca",
                        lambda: "nao determinada")
    monkeypatch.setattr(protocolo, "versao_publicada", lambda segundos=15: "2.4.0")
    r = protocolo.relatorio()
    assert "nao posso comparar" in r["veredito"]


def test_mostrar_nao_explode_e_imprime(capsys, monkeypatch):
    monkeypatch.setattr(protocolo, "versao_publicada", lambda segundos=15: "2.3.0")
    assert protocolo.mostrar() == 0
    saida = capsys.readouterr().out
    assert "Revisao de protocolo servida" in saida
    assert protocolo.revisao_servida() in saida
