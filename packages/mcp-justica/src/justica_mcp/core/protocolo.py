"""Mede o que o aplicativo mede antes de aceitar a extensao nas sessoes
compartilhadas: o servidor responde a revisao moderna, e responde A TEMPO?

O QUE ESTE MODULO JA FOI, E POR QUE MUDOU

Nasceu em 26/10/2026 perguntando "ja saiu versao mais nova da biblioteca
`mcp`?", porque o diagnostico daquele momento era que faltava uma revisao de
protocolo a publicar. Esse diagnostico estava ERRADO, e a correcao veio de
medicao:

  1. A revisao atual da especificacao e a `2026-07-28`, a MESMA que este
     servidor serve. Nao ha revisao a esperar.
  2. A `2026-07-28` removeu o aperto de mao `initialize`. No lugar dele
     entrou `server/discover`, alcancavel sem aperto de mao nenhum.
  3. Este servidor responde a `server/discover` corretamente, declarando
     `supportedVersions: ["2026-07-28"]`, em cerca de 0,7s em Linux.
  4. O aplicativo sonda a era com um limite de QUATRO SEGUNDOS, medido em
     quatro ocorrencias do registro: 4,001s, 4,001s, 4,010s, 4,004s. Quando
     ninguem responde nesse prazo, ele anota "legacy (sibling did not
     complete the exchange)" e recusa a extensao nas sessoes do Cowork e do
     Code.
  5. Numa maquina Windows do escritorio, so carregar a biblioteca levou de
     2,6s a 4,5s em medicoes repetidas, contra 0,74s em Linux. O servidor
     chega atrasado, nao fala errado.

Entao a pergunta certa nao e sobre versao publicada: e sobre TEMPO ATE A
PRIMEIRA RESPOSTA, na maquina de quem pergunta. E o que este modulo mede.

O QUE ELE NAO FAZ

Nao afirma a causa da lentidao quando ela aparece. Na maquina onde isso foi
investigado, o Windows Defender estava desligado e quem varria era outro
antivirus; trocar de suspeito sem medir seria repetir o erro que originou
este arquivo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# O limite que o aplicativo concede, medido no registro dele. Nao e numero
# documentado: e o intervalo observado, sempre o mesmo, entre o nascimento do
# processo sonda e o veredito "legacy".
JANELA_DA_SONDA_S = 4.0

# Margem para nao declarar vitoria em cima da linha. Uma medicao que da 3,9s
# numa maquina da 4,2s na proxima.
FOLGA_S = 1.0

ESPERA_MAXIMA_S = 20.0


def revisao_servida() -> str:
    from mcp.types import LATEST_PROTOCOL_VERSION

    return str(LATEST_PROTOCOL_VERSION)


def revisoes_conhecidas() -> dict:
    from mcp_types import version as v

    return {
        "modernas": list(v.MODERN_PROTOCOL_VERSIONS),
        "com_aperto_de_mao": list(v.HANDSHAKE_PROTOCOL_VERSIONS),
    }


def _pedido_de_sonda() -> str:
    """O mesmo `server/discover` que a sonda do aplicativo faz.

    As duas chaves de `_meta` sao exigidas pela revisao: sem
    `clientCapabilities` o servidor responde erro -32602, o que foi
    descoberto na marra ao reproduzir a sonda pela primeira vez.
    """
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "server/discover",
        "params": {"_meta": {
            "io.modelcontextprotocol/protocolVersion": revisao_servida(),
            "io.modelcontextprotocol/clientCapabilities": {},
        }},
    })


def medir_sonda(python: Optional[str] = None, pacote: Optional[str] = None) -> dict:
    """Sobe o servidor num processo novo e cronometra a primeira resposta.

    Processo NOVO de proposito: o que interessa e o custo frio, que e o que o
    aplicativo paga. Medir dentro deste processo, com tudo ja carregado,
    responderia outra pergunta e daria um numero bonito e inutil.
    """
    python = python or sys.executable
    pacote = pacote or str(Path(__file__).resolve().parents[3])

    inicio = time.monotonic()
    filho = subprocess.Popen(
        [python, "-m", "justica_mcp.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=pacote, text=True, bufsize=1,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    recebido: list = []

    def ler() -> None:
        linha = filho.stdout.readline() if filho.stdout else ""
        if linha:
            recebido.append((time.monotonic() - inicio, linha.strip()))

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    try:
        if filho.stdin:
            filho.stdin.write(_pedido_de_sonda() + "\n")
            filho.stdin.flush()
        leitor.join(timeout=ESPERA_MAXIMA_S)
    finally:
        filho.kill()

    if not recebido:
        return {"respondeu": False, "segundos": None, "resposta": None}

    segundos, linha = recebido[0]
    try:
        corpo = json.loads(linha)
    except ValueError:
        corpo = None
    return {"respondeu": True, "segundos": segundos, "resposta": corpo}


def relatorio(python: Optional[str] = None, pacote: Optional[str] = None) -> dict:
    medida = medir_sonda(python, pacote)
    revisao = revisao_servida()
    corpo = medida.get("resposta") or {}
    declaradas = (corpo.get("result") or {}).get("supportedVersions")
    erro = corpo.get("error")

    if not medida["respondeu"]:
        veredito = (
            "O servidor NAO respondeu a sonda. Isso e defeito de instalacao, "
            "nao de desempenho: rode o comando `ambiente` e mande a saida ao "
            "responsavel."
        )
    elif erro:
        veredito = (
            f"O servidor respondeu com erro: {erro.get('message', erro)}. "
            "A sonda espera um resultado, nao um erro."
        )
    elif medida["segundos"] <= JANELA_DA_SONDA_S - FOLGA_S:
        veredito = (
            f"Respondeu em {medida['segundos']:.2f}s, dentro dos "
            f"{JANELA_DA_SONDA_S:.0f}s que o aplicativo concede, com folga. "
            "As sessoes do Cowork e do Code deveriam aceitar a extensao."
        )
    elif medida["segundos"] <= JANELA_DA_SONDA_S:
        veredito = (
            f"Respondeu em {medida['segundos']:.2f}s, dentro dos "
            f"{JANELA_DA_SONDA_S:.0f}s mas SEM FOLGA. Medicoes repetidas "
            "variam o bastante para que isso falhe parte das vezes."
        )
    else:
        veredito = (
            f"Respondeu em {medida['segundos']:.2f}s, ALEM dos "
            f"{JANELA_DA_SONDA_S:.0f}s que o aplicativo concede. E por isso "
            "que as sessoes do Cowork e do Code recusam a extensao: o "
            "servidor chega atrasado, nao fala errado. As conversas comuns "
            "nao tem esse limite e seguem funcionando."
        )

    return {
        "revisao_servida": revisao,
        "revisoes": revisoes_conhecidas(),
        "respondeu": medida["respondeu"],
        "segundos": medida["segundos"],
        "versoes_declaradas": declaradas,
        "janela_da_sonda_s": JANELA_DA_SONDA_S,
        "veredito": veredito,
    }


def mostrar(python: Optional[str] = None, pacote: Optional[str] = None) -> int:
    r = relatorio(python, pacote)
    print(f"Revisao de protocolo servida:  {r['revisao_servida']}")
    print(f"Revisoes modernas conhecidas:  {', '.join(r['revisoes']['modernas'])}")
    print()
    if r["respondeu"]:
        print(f"Resposta a `server/discover`:   {r['segundos']:.2f}s "
              f"(limite do aplicativo: {r['janela_da_sonda_s']:.0f}s)")
        if r["versoes_declaradas"]:
            print(f"Versoes declaradas na resposta: {', '.join(r['versoes_declaradas'])}")
    else:
        print("Resposta a `server/discover`:   NENHUMA")
    print()
    print(r["veredito"])
    return 0
