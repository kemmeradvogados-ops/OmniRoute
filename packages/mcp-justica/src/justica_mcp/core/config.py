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


def _ler(arquivo: Path) -> str:
    """Le o `.env` tolerando as codificacoes que o Windows produz.

    utf-8-sig remove a marca de ordem de byte que o PowerShell grava com
    `Out-File -Encoding utf8`. Sem isso a PRIMEIRA chave do arquivo viria com
    um caractere invisivel no nome e nunca seria encontrada.

    O Bloco de Notas do Windows 10 mais antigo salva em ANSI, e um caminho com
    acento (`G:\\Meu Drive\\4.Processos\\Copias`) vira byte invalido em UTF-8.
    Sem esta tolerancia o arquivo inteiro falharia, e a mensagem de erro
    apontaria para codificacao, nao para a configuracao que o usuario acabou de
    escrever. Um `.env` mal codificado nao pode derrubar a leitura das outras
    chaves.
    """
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return arquivo.read_text(encoding=codificacao)
        except (UnicodeDecodeError, LookupError):
            continue
    # latin-1 decodifica qualquer byte, entao so se chega aqui por erro de
    # leitura do disco, que nao e nosso para tratar.
    return arquivo.read_text(encoding="utf-8", errors="replace")


def limpar_invisiveis(chave: str) -> str:
    """Tira do NOME da chave os caracteres que nao se veem na tela.

    Conferido em campo em 22 de setembro de 2026: uma chave com um caractere
    invisivel no meio do nome produz a pior especie de defeito. A listagem de
    portais mostrava "TJRJ / pje", identico ao que se espera, e a busca pelo
    mesmo portal dizia que ele nao estava configurado. O arquivo parecia certo
    na tela, e o operador nao tinha como ver a diferenca.

    Esses caracteres entram sozinhos: `Add-Content -Encoding UTF8` do Windows
    PowerShell grava marca de ordem de byte, e copiar de pagina ou de documento
    traz espaco sem quebra e marcas de direcao de texto. Nenhum deles pode
    fazer parte de um nome de variavel, entao retira-los nao perde nada.
    """
    import unicodedata

    return "".join(
        c for c in chave
        if not (unicodedata.category(c) in ("Cf", "Cc") or c in "\ufeff\u00a0")
    )


def carregar_env(caminho: Optional[Path] = None) -> list[str]:
    """Carrega o `.env` e devolve os NOMES das chaves lidas, nunca os valores."""
    arquivo = caminho or (raiz_do_pacote() / ".env")
    if not arquivo.is_file():
        return []

    lidas: list[str] = []
    for linha in _ler(arquivo).splitlines():
        # A marca de ordem de byte e retirada linha a linha, nao so no inicio
        # do arquivo: `Add-Content -Encoding UTF8` do Windows PowerShell pode
        # grava-la de novo a cada acrescimo, no MEIO do arquivo, e ali o
        # utf-8-sig nao a remove. O efeito seria um caractere invisivel colado
        # no nome da chave recem-adicionada, que entao nunca seria encontrada,
        # com o arquivo parecendo correto na tela.
        linha = linha.strip().lstrip("\ufeff").strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = limpar_invisiveis(chave.strip())
        valor = valor.strip().strip('"').strip("'")
        if not chave or not valor:
            continue
        # Ambiente explicito tem precedencia sobre arquivo.
        if chave not in os.environ:
            os.environ[chave] = valor
        lidas.append(chave)
    return lidas
