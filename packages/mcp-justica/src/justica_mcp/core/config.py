"""Leitura do arquivo `.env`.

O README manda copiar `.env.example` para `.env`, mas nada lia esse arquivo:
o codigo consultava apenas as variaveis de ambiente do sistema. Quem seguisse
a instrucao ao pe da letra continuaria sem a chave, sem entender por que.

Regras: nunca sobrescreve variavel ja definida no ambiente, e nunca registra
o valor lido em log ou mensagem de erro.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def raiz_do_pacote() -> Path:
    return Path(__file__).resolve().parents[2].parent


def carregar_env(caminho: Optional[Path] = None) -> list[str]:
    """Carrega o `.env` e devolve os NOMES das chaves lidas, nunca os valores."""
    arquivo = caminho or (raiz_do_pacote() / ".env")
    if not arquivo.is_file():
        return []

    lidas: list[str] = []
    # utf-8-sig remove a marca de ordem de byte que o PowerShell grava com
    # `Out-File -Encoding utf8`. Sem isso a PRIMEIRA chave do arquivo viria
    # com um caractere invisivel no nome e nunca seria encontrada.
    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if not chave or not valor:
            continue
        # Ambiente explicito tem precedencia sobre arquivo.
        if chave not in os.environ:
            os.environ[chave] = valor
        lidas.append(chave)
    return lidas
