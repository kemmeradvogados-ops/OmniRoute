"""Configuracao do acesso autenticado aos portais.

Desligado por padrao. Ligar significa permitir que o agente dispare
autenticacao real no tribunal com a credencial do advogado, e isso e decisao
do operador, nao um comportamento herdado da instalacao.

O endereco e o perfil de cada portal ficam no ambiente, e nao como parametro de
ferramenta: o agente nao deve precisar saber o endereco do portal, nem ter como
apontar a autenticacao para outro lugar.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

VARIAVEL_LIGA = "JUSTICA_ACESSO_AUTENTICADO"


def autenticado_habilitado() -> bool:
    return os.environ.get(VARIAVEL_LIGA, "").strip().lower() in ("1", "true", "sim")


@dataclass(frozen=True)
class ConfigPortal:
    tribunal: str
    sistema: str
    url: str
    perfil: Optional[str]
    # Processo usado para exercitar este portal em campo. Fica no ambiente, e
    # nao no codigo, porque e numero de processo de cliente: o repositorio e
    # compartilhado, e numero em codigo versionado nao se apaga do historico.
    processo_teste: Optional[str] = None
    # Portais separam as telas de primeiro e de segundo grau, entao exercitar
    # um portal exige um processo de cada. O e-SAJ e o caso confirmado.
    processo_teste_2g: Optional[str] = None

    @property
    def rotulo(self) -> str:
        return f"{self.tribunal} / {self.sistema}"


def _chave(tribunal: str, sistema: str, sufixo: str) -> str:
    return f"JUSTICA_PORTAL_{tribunal.upper()}_{sistema.upper()}_{sufixo}"


def rotulos_no_ambiente() -> list[str]:
    """Portais que o ambiente declara, lidos SO pelo nome da chave.

    Nao passa por `config_portal` de proposito: ele e quem levanta o erro que
    chama esta funcao, e chama-lo daqui seria recursao. Serve para a mensagem
    de erro mostrar o que o programa enxerga, que foi o que faltou em
    22/09/2026, quando a listagem mostrava o portal e a busca nao o achava.
    """
    achados = []
    for chave in os.environ:
        if chave.startswith("JUSTICA_PORTAL_") and chave.endswith("_URL"):
            miolo = chave[len("JUSTICA_PORTAL_"):-len("_URL")]
            if "_" not in miolo:
                continue
            tribunal, _, sistema = miolo.rpartition("_")
            achados.append(f"{tribunal} / {sistema.lower()}")
    return sorted(achados)


class PortalNaoConfigurado(LookupError):
    def __init__(self, tribunal: str, sistema: str) -> None:
        # A lista do que o programa ENXERGA entra na mensagem porque, em
        # 22/09/2026, o portal aparecia na listagem e a busca dizia que ele nao
        # existia: um caractere invisivel no nome da chave. Ver os dois lados
        # lado a lado e o que transforma um misterio num erro de digitacao.
        conhecidos = rotulos_no_ambiente()
        visao = (
            "\n\n  O programa enxerga estes portais no ambiente:\n    "
            + "\n    ".join(conhecidos)
            + "\n  Se o que voce procura ESTA nessa lista, o nome da chave tem"
              "\n  algum caractere invisivel: reescreva a linha inteira no .env."
            if conhecidos else
            "\n\n  O programa nao enxerga portal nenhum no ambiente: o .env pode"
            "\n  estar em outro lugar ou vazio."
        )
        super().__init__(
            f"Portal {tribunal}/{sistema} sem endereco configurado. Defina no .env:\n"
            f"    {_chave(tribunal, sistema, 'URL')}=https://...\n"
            f"    {_chave(tribunal, sistema, 'PERFIL')}=<inscricao, se o portal pedir>"
            f"{visao}"
        )


def config_portal(tribunal: str, sistema: str) -> ConfigPortal:
    url = os.environ.get(_chave(tribunal, sistema, "URL"), "").strip()
    if not url:
        raise PortalNaoConfigurado(tribunal, sistema)
    return ConfigPortal(
        tribunal=tribunal.upper(),
        sistema=sistema.lower(),
        url=url,
        perfil=os.environ.get(_chave(tribunal, sistema, "PERFIL"), "").strip() or None,
        processo_teste=os.environ.get(
            _chave(tribunal, sistema, "PROCESSO_TESTE"), ""
        ).strip() or None,
        processo_teste_2g=os.environ.get(
            _chave(tribunal, sistema, "PROCESSO_TESTE_2G"), ""
        ).strip() or None,
    )


def portais_configurados() -> list[ConfigPortal]:
    """Varre o ambiente atras de portais declarados, sem expor valor algum."""
    saida = []
    for chave in os.environ:
        if chave.startswith("JUSTICA_PORTAL_") and chave.endswith("_URL"):
            miolo = chave[len("JUSTICA_PORTAL_"):-len("_URL")]
            if "_" not in miolo:
                continue
            tribunal, _, sistema = miolo.rpartition("_")
            try:
                saida.append(config_portal(tribunal, sistema))
            except PortalNaoConfigurado:
                continue
    return sorted(saida, key=lambda c: c.rotulo)
