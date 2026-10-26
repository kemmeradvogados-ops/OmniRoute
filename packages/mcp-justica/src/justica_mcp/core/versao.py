"""Qual versao do programa esta instalada AQUI.

Existe por causa de 26/10/2026: a pasta de trabalho rodava a 0.9.3 enquanto a
Area de Trabalho ja tinha a 0.9.4, e descobrir isso exigiu um comando de tres
linhas que lia atributos do codigo-fonte. O advogado nao deve precisar
inspecionar o programa para saber qual versao dele esta rodando.

A versao que vale e a do MANIFESTO do conector, porque e ela que acompanha
cada entrega. O `pyproject.toml` guarda a mesma, e um teste garante que as
duas nao se separem: dois numeros de versao que discordam sao pior do que
nenhum, porque cada um parece certo sozinho.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

NAO_SEI = "versao nao determinada"


def caminho_do_manifesto() -> Path:
    """`<raiz>/conector/manifest.json`, a partir deste arquivo."""
    return Path(__file__).resolve().parent.parent.parent.parent / "conector" / "manifest.json"


@lru_cache(maxsize=1)
def versao_instalada() -> str:
    """A versao desta instalacao, ou `NAO_SEI`. Nunca levanta erro.

    Saber a versao e conveniencia: se a leitura falhar, o programa segue. O
    que ele nao pode fazer e INVENTAR um numero, porque o operador usaria essa
    resposta para decidir se precisa atualizar.
    """
    try:
        bruto = json.loads(caminho_do_manifesto().read_text(encoding="utf-8"))
        achada = str(bruto.get("version") or "").strip()
        if achada:
            return achada
    except (OSError, ValueError):
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("justica-mcp")
        except PackageNotFoundError:
            return NAO_SEI
    except Exception:
        return NAO_SEI


def onde_esta_o_codigo() -> Optional[Path]:
    """A pasta de onde o programa esta rodando.

    Imprimir isto ao lado da versao e o que separa "a versao esta velha" de
    "ha duas instalacoes e voce atualizou a outra", que foi o caso real.
    """
    try:
        return Path(__file__).resolve().parent.parent
    except Exception:
        return None
