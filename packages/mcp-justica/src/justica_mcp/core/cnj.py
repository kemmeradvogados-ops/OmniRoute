"""Parser da numeracao unica de processos judiciais.

Base normativa: Resolucao nº. 65/2008 do Conselho Nacional de Justica.
Formato: NNNNNNN-DD.AAAA.J.TR.OOOO

Este modulo e deterministico: nao faz rede, nao consulta cache e nao decide
sistema. Identificar o tribunal se resolve pelo proprio numero; identificar o
SISTEMA (PJe, eproc, e-SAJ, DCP) nao, e por isso vive em `resolver.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Segmentos do Poder Judiciario, digito J da numeracao unica.
SEGMENTOS = {
    1: "Supremo Tribunal Federal",
    2: "Conselho Nacional de Justica",
    3: "Superior Tribunal de Justica",
    4: "Justica Federal",
    5: "Justica do Trabalho",
    6: "Justica Eleitoral",
    7: "Justica Militar da Uniao",
    8: "Justica dos Estados e do Distrito Federal e Territorios",
    9: "Justica Militar Estadual",
}

_RE_NUMERO = re.compile(
    r"^(?P<seq>\d{7})-?(?P<dv>\d{2})\.?(?P<ano>\d{4})\.?(?P<seg>\d)\.?(?P<trib>\d{2})\.?(?P<origem>\d{4})$"
)


class NumeroCNJInvalido(ValueError):
    """Numero fora do formato da Resolucao nº. 65/2008 ou com digito incorreto."""


@dataclass(frozen=True)
class NumeroCNJ:
    sequencial: str
    digito_verificador: str
    ano: str
    segmento: int
    tribunal: str
    origem: str

    @property
    def formatado(self) -> str:
        return (
            f"{self.sequencial}-{self.digito_verificador}.{self.ano}"
            f".{self.segmento}.{self.tribunal}.{self.origem}"
        )

    @property
    def apenas_digitos(self) -> str:
        return (
            f"{self.sequencial}{self.digito_verificador}{self.ano}"
            f"{self.segmento}{self.tribunal}{self.origem}"
        )

    @property
    def segmento_nome(self) -> str:
        return SEGMENTOS.get(self.segmento, "segmento desconhecido")

    @property
    def chave_segmento_tribunal(self) -> str:
        """Chave `J.TR`, usada para resolver o tribunal."""
        return f"{self.segmento}.{self.tribunal}"


def calcular_digito_verificador(
    sequencial: str, ano: str, segmento: str, tribunal: str, origem: str
) -> str:
    """Digito verificador por ISO 7064 MOD 97-10.

    Regra da Resolucao nº. 65/2008: concatena-se
    NNNNNNN + AAAA + J + TR + OOOO, acrescenta-se "00" ao final e calcula-se
    98 menos o resto da divisao por 97.
    """
    base = f"{sequencial}{ano}{segmento}{tribunal}{origem}00"
    return f"{98 - (int(base) % 97):02d}"


def parse_numero(numero: str, *, validar_digito: bool = True) -> NumeroCNJ:
    """Converte texto livre em `NumeroCNJ`, validando o digito verificador.

    Aceita com ou sem mascara. `validar_digito=False` serve para diagnostico de
    numero recebido de terceiro, jamais para consulta silenciosa: um digito
    errado normalmente significa erro de transcricao, e consultar assim mesmo
    produz "processo nao encontrado" que o agente interpretaria como inexistente.
    """
    if not numero or not numero.strip():
        raise NumeroCNJInvalido("Numero do processo vazio.")

    limpo = re.sub(r"[^0-9]", "", numero)
    if len(limpo) != 20:
        raise NumeroCNJInvalido(
            f"Numero deve ter 20 digitos no padrao NNNNNNN-DD.AAAA.J.TR.OOOO; "
            f"recebido {len(limpo)} digito(s) em {numero!r}."
        )

    m = _RE_NUMERO.match(limpo)
    if not m:  # pragma: no cover - 20 digitos sempre casam
        raise NumeroCNJInvalido(f"Numero fora do padrao: {numero!r}")

    g = m.groupdict()
    if validar_digito:
        esperado = calcular_digito_verificador(
            g["seq"], g["ano"], g["seg"], g["trib"], g["origem"]
        )
        if esperado != g["dv"]:
            raise NumeroCNJInvalido(
                f"Digito verificador invalido em {numero!r}: informado {g['dv']}, "
                f"esperado {esperado}. Confira a transcricao antes de consultar."
            )

    return NumeroCNJ(
        sequencial=g["seq"],
        digito_verificador=g["dv"],
        ano=g["ano"],
        segmento=int(g["seg"]),
        tribunal=g["trib"],
        origem=g["origem"],
    )
