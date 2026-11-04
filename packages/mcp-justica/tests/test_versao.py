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


# ==========================================================================
# Nenhum numero de versao digitado a mao
#
# 04/11/2026. O advogado perguntou a versao pela extensao durante dias e
# recebeu 0.1.0 de uma instalacao que era 0.9.9. Eram QUATRO fontes, e duas
# mentiam:
#
#   conector/manifest.json        0.9.9   (a que vale)
#   pyproject.toml                0.9.9
#   src/justica_mcp/__init__.py   0.1.0   <- literal parado
#   tools.py, justica_capacidades 0.1.0   <- literal parado, e o que ele lia
#
# Com isso nenhuma auditoria conseguia dizer qual codigo estava rodando, e eu
# cheguei a afirmar que a instalacao dele era a 0.9.5 apoiado nesse numero.
#
# Havia teste ligando manifesto e pyproject desde 26/10. Nao havia nenhum
# sobre os outros dois, que foram justamente os que mentiram.
# ==========================================================================


def _versao_do_manifesto() -> str:
    import json

    return json.loads(caminho_do_manifesto().read_text(encoding="utf-8"))["version"]


def test_a_versao_do_pacote_nao_e_um_literal():
    """`justica_mcp.__version__` vem do manifesto, como todo o resto."""
    import justica_mcp

    assert justica_mcp.__version__ == _versao_do_manifesto()


def test_a_ferramenta_de_capacidades_nao_tem_versao_digitada():
    """O que o advogado consulta precisa ser lido, e nao recitado.

    Este teste guarda a REGRA, nao a grafia: procura qualquer coisa com cara
    de numero de versao dentro da ferramenta. Literal novo, com outro numero,
    cai aqui do mesmo jeito.
    """
    import inspect
    import re

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    trecho = fonte.split("async def justica_capacidades")[1].split("@mcp.tool")[0]
    # Comentarios contam a historia e citam os numeros de proposito.
    codigo = "\n".join(l for l in trecho.splitlines()
                       if not l.strip().startswith("#"))
    digitados = re.findall(r'["\']\s*\d+\.\d+\.\d+', codigo)
    assert not digitados, (
        f"versao digitada na ferramenta de capacidades: {digitados}. "
        "Use versao_instalada(), que le o manifesto.")
    assert "versao_instalada()" in codigo


def test_as_capacidades_dizem_tambem_de_onde_o_codigo_roda():
    """O caminho separa "a versao esta velha" de "ha duas instalacoes e voce
    atualizou a outra", que foi o caso real de 26/10/2026."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    trecho = fonte.split("async def justica_capacidades")[1].split("@mcp.tool")[0]
    assert "onde_esta_o_codigo()" in trecho


def test_todo_modulo_com_main_ou_e_executavel_ou_nao_finge_ser():
    """04/11/2026: `python -m justica_mcp.cli ambiente` voltou VAZIO, com
    codigo de sucesso.

    Sem a guarda `__main__`, o modulo e importado, `main` e definida e nada a
    chama. Para quem roda, e indistinguivel de um comando que funcionou e nao
    tinha o que mostrar, e foi essa a leitura do advogado. Programa que cala
    onde devia falar e o defeito que a auditoria de 30/10/2026 apontou em
    outro canto do codigo.
    """
    import ast

    raiz = caminho_do_manifesto().parent.parent / "src" / "justica_mcp"
    mudos = []
    for caminho in sorted(raiz.rglob("*.py")):
        fonte = caminho.read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        tem_main = any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main"
            for n in arvore.body)
        if not tem_main:
            continue
        if "__main__" not in fonte:
            mudos.append(caminho.name)
    assert not mudos, (
        f"modulo(s) com main() e sem guarda __main__: {mudos}. "
        "`python -m` neles sai calado e com codigo de sucesso.")
