"""Contrato comum dos adaptadores."""

from __future__ import annotations

import abc
from typing import Any, Optional

import httpx

from ..core.capabilities import Capacidade, Situacao, consultar
from ..core.resiliencia import Portal
from ..core.schemas import Confianca, Metodo, Proveniencia


class CapacidadeIndisponivel(RuntimeError):
    """Recusa declarada, com motivo, antes de gastar chamada de rede."""

    def __init__(self, adaptador: str, capacidade: Capacidade, motivo: str, alternativas: list[str]) -> None:
        sugestao = (
            f" Adaptador(es) que atendem hoje: {', '.join(alternativas)}."
            if alternativas
            else " Nenhum adaptador atende a isso no momento."
        )
        super().__init__(f"{adaptador} nao atende {capacidade.value}: {motivo}{sugestao}")
        self.adaptador = adaptador
        self.capacidade = capacidade
        self.motivo = motivo
        self.alternativas = alternativas


class AdaptadorBase(abc.ABC):
    nome: str
    metodo: Metodo
    confianca_padrao: Confianca

    def __init__(self, portal: Optional[Portal] = None) -> None:
        self.portal = portal or Portal(nome=self.nome)

    def exigir_capacidade(self, capacidade: Capacidade) -> None:
        """Falha cedo e com motivo, em vez de devolver vazio ambiguo."""
        from ..core.capabilities import adaptadores_para

        declaracao = consultar(self.nome, capacidade)
        if declaracao.situacao is not Situacao.DISPONIVEL:
            raise CapacidadeIndisponivel(
                self.nome, capacidade, declaracao.motivo or declaracao.situacao.value,
                [a for a in adaptadores_para(capacidade) if a != self.nome],
            )

    def proveniencia(
        self, *, endpoint: Optional[str] = None, observacao: Optional[str] = None,
        confianca: Optional[Confianca] = None,
    ) -> Proveniencia:
        return Proveniencia(
            fonte=self.nome, metodo=self.metodo,
            confianca=confianca or self.confianca_padrao,
            endpoint=endpoint, observacao=observacao,
        )

    async def _requisitar(self, cliente: httpx.AsyncClient, **kwargs: Any) -> httpx.Response:
        """Toda saida de rede passa por limitador e disjuntor."""
        await self.portal.entrar()
        try:
            resposta = await cliente.request(**kwargs)
        except httpx.HTTPError:
            self.portal.disjuntor.registrar_falha()
            raise
        if resposta.status_code >= 500 or resposta.status_code in (403, 429):
            self.portal.disjuntor.registrar_falha()
        else:
            self.portal.disjuntor.registrar_sucesso()
        return resposta
