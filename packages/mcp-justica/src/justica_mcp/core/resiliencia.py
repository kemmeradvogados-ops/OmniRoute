"""Limitacao de taxa e disjuntor por portal.

Motivo pratico: tribunal bloqueia origem que faz rajada, e o bloqueio costuma
atingir a credencial do advogado, nao apenas o processo. Aqui o custo de errar
nao e uma requisicao perdida, e sim perder o acesso.

Desenho espelhado do disjuntor ja usado em `src/shared/utils/circuitBreaker.ts`
neste repositorio: recuperacao preguicosa, sem tarefa de fundo, com o proprio
`pode_executar()` promovendo ABERTO para MEIO_ABERTO quando a espera vence.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EstadoDisjuntor(str, Enum):
    FECHADO = "fechado"        # trafego normal
    ABERTO = "aberto"          # portal bloqueado temporariamente
    MEIO_ABERTO = "meio_aberto"  # deixa passar uma sonda


class PortalIndisponivel(RuntimeError):
    def __init__(self, portal: str, segundos: float) -> None:
        super().__init__(
            f"Disjuntor aberto para {portal!r}: falhas seguidas recentes. "
            f"Nova tentativa em {segundos:.0f}s. Nao insista; repetir agora aumenta "
            f"o risco de bloqueio da credencial."
        )
        self.portal = portal
        self.segundos_restantes = segundos


class LimiteDeTaxa(PortalIndisponivel):
    """A fonte recusou por excesso de chamadas, e nao por falha nossa.

    AUDITORIA DE 03/11/2026. O DataJud devolveu `429 Too Many Requests`
    durante a verificacao em lote, e isso chegava ao advogado como "Falha
    inesperada: HTTPStatusError", que e falso em duas frentes: nao foi
    inesperada, e nao foi falha. A fonte estava no ar e disse, com todas as
    letras, para esperar.

    Herda de `PortalIndisponivel` porque a conduta e a mesma, aguardar a
    janela antes de repetir, e `_tratar` ja a traduz assim. O que muda e a
    FRASE: dizer "disjuntor aberto, falhas seguidas recentes" sobre um limite
    de taxa mandaria o leitor procurar defeito que nao existe.
    """

    def __init__(self, fonte: str, segundos: float, *, pedido_pela_fonte: bool) -> None:
        de_onde = ("a propria fonte pediu esta espera"
                   if pedido_pela_fonte
                   else "a fonte nao disse quanto, entao este e o nosso padrao")
        RuntimeError.__init__(
            self,
            f"{fonte} recusou por excesso de chamadas (429). Ja esperei e "
            f"tentei de novo, e continuou recusando. Aguarde cerca de "
            f"{segundos:.0f}s antes de repetir ({de_onde}). A consulta NAO "
            f"falhou por defeito nosso nem gasta tentativa de autenticacao: "
            f"pedir em rajada e que atinge o limite, entao prefira espacar as "
            f"chamadas a repetir esta agora."
        )
        self.portal = fonte
        self.segundos_restantes = segundos


@dataclass
class LimitadorTaxa:
    """Espacamento minimo entre chamadas ao mesmo portal.

    O padrao de 500 ms segue a recomendacao publicada para a API de comunicacoes
    do Conselho Nacional de Justica. [Nao verificado em documentacao oficial]
    """

    intervalo_minimo: float = 0.5
    _ultimo: float = field(default=0.0, repr=False)
    _trava: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def aguardar(self) -> None:
        async with self._trava:
            espera = self.intervalo_minimo - (time.monotonic() - self._ultimo)
            if espera > 0:
                await asyncio.sleep(espera)
            self._ultimo = time.monotonic()


@dataclass
class Disjuntor:
    portal: str
    limite_falhas: int = 5
    espera_segundos: float = 60.0
    _falhas: int = field(default=0, repr=False)
    _aberto_em: Optional[float] = field(default=None, repr=False)

    @property
    def estado(self) -> EstadoDisjuntor:
        if self._aberto_em is None:
            return EstadoDisjuntor.FECHADO
        if (time.monotonic() - self._aberto_em) >= self.espera_segundos:
            return EstadoDisjuntor.MEIO_ABERTO
        return EstadoDisjuntor.ABERTO

    def pode_executar(self) -> bool:
        return self.estado is not EstadoDisjuntor.ABERTO

    def exigir_passagem(self) -> None:
        if not self.pode_executar():
            restante = self.espera_segundos - (time.monotonic() - (self._aberto_em or 0.0))
            raise PortalIndisponivel(self.portal, max(restante, 0.0))

    def registrar_sucesso(self) -> None:
        self._falhas = 0
        self._aberto_em = None

    def registrar_falha(self) -> None:
        self._falhas += 1
        if self._falhas >= self.limite_falhas:
            self._aberto_em = time.monotonic()


@dataclass
class Portal:
    """Par limitador mais disjuntor, um por origem de dados."""

    nome: str
    limitador: LimitadorTaxa = field(default_factory=LimitadorTaxa)
    disjuntor: Disjuntor = field(init=False)

    def __post_init__(self) -> None:
        self.disjuntor = Disjuntor(portal=self.nome)

    async def entrar(self) -> None:
        self.disjuntor.exigir_passagem()
        await self.limitador.aguardar()
