"""Nenhum nome usado sem estar definido, em nenhum modulo do pacote.

POR QUE ESTE ARQUIVO EXISTE

Em 27/10/2026 a consulta autenticada, depois de finalmente passar do login,
morreu com `NameError: name 'agora_iso' is not defined`. A funcao era usada
em `tools.py` e nunca importada ali.

O defeito estava no codigo havia semanas e nenhum teste o via, porque aquele
ramo so executa DEPOIS de uma autenticacao de verdade num portal de
tribunal, que nenhum teste faz nem deve fazer. Ficou escondido atras de
outro defeito, o dos seletores de login, que impedia a execucao de chegar
ate la.

Nao da para testar executando o que exige credencial e portal. Da para
conferir, sem executar, que todo nome usado existe. E o que isto faz.

Nao substitui um analisador estatico de verdade; cobre a classe de defeito
que custou o dia.
"""

from __future__ import annotations

import ast
import builtins
import pathlib

PACOTE = pathlib.Path(__file__).resolve().parent.parent / "src" / "justica_mcp"

# Nomes que o interpretador poe em todo modulo e que nao aparecem em
# `dir(builtins)`.
DO_MODULO = {"__file__", "__name__", "__doc__", "__package__", "__spec__",
             "__loader__", "__builtins__", "__path__", "__annotations__"}


def _nomes_soltos(caminho: pathlib.Path) -> list:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), str(caminho))
    definidos = set(dir(builtins)) | DO_MODULO

    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definidos.add(no.name)
            a = no.args
            for lista in (a.posonlyargs, a.args, a.kwonlyargs):
                definidos.update(x.arg for x in lista)
            for extra in (a.vararg, a.kwarg):
                if extra:
                    definidos.add(extra.arg)
        elif isinstance(no, ast.ClassDef):
            definidos.add(no.name)
        elif isinstance(no, ast.Lambda):
            a = no.args
            for lista in (a.posonlyargs, a.args, a.kwonlyargs):
                definidos.update(x.arg for x in lista)
        elif isinstance(no, (ast.Import, ast.ImportFrom)):
            for alias in no.names:
                definidos.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(no, ast.Name) and isinstance(no.ctx, (ast.Store, ast.Del)):
            definidos.add(no.id)
        elif isinstance(no, ast.ExceptHandler) and no.name:
            definidos.add(no.name)
        elif isinstance(no, (ast.Global, ast.Nonlocal)):
            definidos.update(no.names)

    return sorted({
        no.id for no in ast.walk(arvore)
        if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Load)
        and no.id not in definidos
    })


def test_nenhum_nome_usado_sem_definicao():
    faltando = {}
    for caminho in sorted(PACOTE.rglob("*.py")):
        soltos = _nomes_soltos(caminho)
        if soltos:
            faltando[caminho.relative_to(PACOTE).as_posix()] = soltos
    assert not faltando, (
        "nome usado e nunca definido nem importado, que so apareceria como "
        f"NameError ao executar aquele ramo: {faltando}"
    )


def test_a_conferencia_reconhece_o_defeito_que_a_originou():
    """Guarda da guarda: sem isto, um erro meu aqui passaria despercebido."""
    import tempfile

    with tempfile.TemporaryDirectory() as pasta:
        alvo = pathlib.Path(pasta) / "exemplo.py"
        alvo.write_text(
            "def f():\n"
            "    return agora_iso()\n", encoding="utf-8")
        assert _nomes_soltos(alvo) == ["agora_iso"]

        alvo.write_text(
            "from x import agora_iso\n\n"
            "def f():\n"
            "    return agora_iso()\n", encoding="utf-8")
        assert _nomes_soltos(alvo) == []
