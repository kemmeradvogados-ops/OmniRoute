"""Qual revisao de protocolo este servidor serve, e se ja ha outra publicada.

POR QUE ESTE MODULO EXISTE

Em 26/10/2026 o aplicativo do Claude passou a recusar a extensao nas sessoes
do Cowork e do Code, com esta linha no registro:

    connection is serving the 2026-07-28 protocol; the initialize handshake
    is not accepted

`2026-07-28` e exatamente o `LATEST_PROTOCOL_VERSION` da biblioteca `mcp`
instalada. Nao e defeito da instalacao de ninguem: falta uma revisao que a
biblioteca ainda nao publicou. A unica coisa que destrava e uma versao nova
da biblioteca.

O problema seguinte era de PROCESSO, nao de codigo: alguem teria de lembrar
de conferir o repositorio de pacotes de tempos em tempos. Promessa de
acompanhar nao e mecanismo, e sessao de conversa acaba. Entao a conferencia
virou comando: quem quiser saber, pergunta ao programa.

O QUE ESTE MODULO NAO FAZ

Nao afirma que atualizar RESOLVE. So a versao instalada diz qual revisao ela
serve, e isso so se sabe depois de instalar. O veredito honesto e "ha versao
mais nova, vale tentar" ou "ja esta na mais nova que existe", nunca "isto
conserta".
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

ENDERECO_DO_INDICE = "https://pypi.org/pypi/mcp/json"
SEGUNDOS = 15

# A revisao que o aplicativo recusava nas sessoes do Cowork e do Code, para
# que o relatorio possa dizer "e esta mesma" em vez de obrigar quem le a
# comparar strings de cabeca.
REVISAO_RECUSADA_EM_26_10_2026 = "2026-07-28"


def revisao_servida() -> str:
    """A revisao de protocolo que este servidor fala."""
    from mcp.types import LATEST_PROTOCOL_VERSION

    return str(LATEST_PROTOCOL_VERSION)


def versao_da_biblioteca() -> str:
    import importlib.metadata as meta

    try:
        return meta.version("mcp")
    except meta.PackageNotFoundError:
        return "nao determinada"


def versao_publicada(segundos: int = SEGUNDOS) -> Optional[str]:
    """A versao mais nova no repositorio publico, ou None se nao deu para ver.

    None e "nao consegui olhar", nunca "nao ha novidade": a maquina pode estar
    sem rede, atras de proxy ou com o indice fora do ar, e tratar isso como
    "esta tudo atualizado" seria afirmar o que ninguem verificou.
    """
    try:
        with urllib.request.urlopen(ENDERECO_DO_INDICE, timeout=segundos) as r:
            return str(json.load(r)["info"]["version"])
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        return None


def _ordenar(versao: str) -> tuple:
    """Compara 2.3.0 com 2.10.0 pelos numeros, nao pelas letras."""
    partes = []
    for pedaco in versao.split("."):
        digitos = ""
        for ch in pedaco:
            if not ch.isdigit():
                break
            digitos += ch
        partes.append(int(digitos) if digitos else 0)
    return tuple(partes)


def relatorio(segundos: int = SEGUNDOS) -> dict:
    instalada = versao_da_biblioteca()
    publicada = versao_publicada(segundos)
    revisao = revisao_servida()

    if publicada is None:
        veredito = ("Nao consegui consultar o repositorio de pacotes. Sem "
                    "rede, nao da para saber se ha versao mais nova.")
    elif instalada == "nao determinada":
        veredito = ("Nao sei qual versao esta instalada, entao nao posso "
                    f"comparar. A mais nova publicada e {publicada}.")
    elif _ordenar(publicada) > _ordenar(instalada):
        veredito = (
            f"Ha versao mais nova da biblioteca ({publicada}, contra "
            f"{instalada} instalada). VALE TENTAR: rode o instalador de novo "
            "e confira este comando outra vez. Nao garante que resolve, "
            "porque so depois de instalar da para ver qual revisao ela serve."
        )
    else:
        veredito = (
            f"A versao instalada ({instalada}) ja e a mais nova publicada. "
            "Nao ha o que atualizar hoje."
        )

    return {
        "revisao_servida": revisao,
        "versao_instalada": instalada,
        "versao_publicada": publicada,
        "e_a_revisao_recusada": revisao == REVISAO_RECUSADA_EM_26_10_2026,
        "veredito": veredito,
    }


def mostrar(segundos: int = SEGUNDOS) -> int:
    r = relatorio(segundos)
    print("Revisao de protocolo servida por este servidor:")
    print(f"  {r['revisao_servida']}")
    if r["e_a_revisao_recusada"]:
        print("  (e a revisao que as sessoes do Cowork e do Code recusaram")
        print("   em 26/10/2026; as conversas comuns aceitam normalmente)")
    print()
    print(f"Biblioteca mcp instalada:  {r['versao_instalada']}")
    publicada = r["versao_publicada"] or "nao consegui consultar"
    print(f"Mais nova publicada:       {publicada}")
    print()
    print(r["veredito"])
    return 0
