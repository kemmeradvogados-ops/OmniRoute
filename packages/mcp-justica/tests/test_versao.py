"""A versao instalada tem que ser visivel e unica.

Em 26/10/2026 a pasta de trabalho rodava a 0.9.3 enquanto a Area de Trabalho
ja tinha a 0.9.4. Descobrir isso exigiu um comando que inspecionava atributos
do codigo-fonte, porque nenhum comando do programa dizia a versao. E havia
dois numeros guardados, o do manifesto e o do `pyproject.toml`, que
discordavam: dois numeros que discordam sao pior do que nenhum, porque cada um
parece certo sozinho.
"""

import json
from pathlib import Path

from justica_mcp.core.versao import (
    NAO_SEI, caminho_do_manifesto, onde_esta_o_codigo, versao_instalada,
)

RAIZ = Path(__file__).resolve().parent.parent


def test_o_manifesto_e_o_pyproject_carregam_a_mesma_versao():
    manifesto = json.loads(
        (RAIZ / "conector" / "manifest.json").read_text(encoding="utf-8"))["version"]
    bruto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    for linha in bruto.splitlines():
        if linha.strip().startswith("version ="):
            do_projeto = linha.split("=", 1)[1].strip().strip('"')
            break
    else:
        raise AssertionError("pyproject.toml sem linha de versao")
    assert manifesto == do_projeto, (
        f"manifesto diz {manifesto} e pyproject diz {do_projeto}")


def test_a_versao_instalada_e_a_do_manifesto():
    esperada = json.loads(
        caminho_do_manifesto().read_text(encoding="utf-8"))["version"]
    assert versao_instalada() == esperada


def test_a_versao_nunca_e_inventada(monkeypatch, tmp_path):
    """Se a leitura falhar, o programa diz que nao sabe. Inventar um numero
    seria pior: o operador usaria a resposta para decidir se atualiza."""
    versao_instalada.cache_clear()
    monkeypatch.setattr("justica_mcp.core.versao.caminho_do_manifesto",
                        lambda: tmp_path / "nao-existe.json")

    def sem_pacote(nome):
        from importlib.metadata import PackageNotFoundError

        raise PackageNotFoundError(nome)

    monkeypatch.setattr("importlib.metadata.version", sem_pacote)
    try:
        assert versao_instalada() == NAO_SEI
    finally:
        versao_instalada.cache_clear()


def test_o_ambiente_mostra_versao_e_caminho():
    """Sem o caminho, "a versao esta velha" nao se distingue de "ha duas
    instalacoes e voce atualizou a outra", que foi o caso real."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.mostrar_ambiente)
    assert "versao_instalada" in fonte
    assert "onde_esta_o_codigo" in fonte


def test_onde_esta_o_codigo_aponta_para_o_pacote():
    assert onde_esta_o_codigo().name == "justica_mcp"
