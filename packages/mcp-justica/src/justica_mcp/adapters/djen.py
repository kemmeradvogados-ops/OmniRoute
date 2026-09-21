"""Adaptador do Diario de Justica Eletronico Nacional (Comunica PJe).

Endpoint publico: https://comunicaapi.pje.jus.br/api/v1/comunicacao
Sem autenticacao. Documentacao em Swagger publicada pelo Conselho Nacional de
Justica.

POR QUE ESTE ADAPTADOR E O CORACAO DA FASE 1

A lei nº. 11.419/06, artigo 5º, §3º, dispoe que a intimacao eletronica se
considera realizada no dia em que o intimado CONSULTA O TEOR da comunicacao, e,
nao havendo consulta em 10 dias corridos, considera-se automaticamente
realizada. O Superior Tribunal de Justica decidiu em outubro de 2025 que esses
10 dias corridos contam da data do ENVIO da intimacao.

Consequencia de engenharia: abrir o expediente no portal CONSOME o prazo. Este
adaptador le a publicacao no Diario, que e canal publico e ja publicado, e
portanto NAO dispara ciencia. E o caminho seguro para o requisito de "checar
intimacao sem abrir".

Ressalva honesta, registrada tambem na matriz de capacidades: nem toda
comunicacao dirigida ao advogado transita pelo Diario. Expediente no painel do
portal e Domicilio Judicial Eletronico sao canais distintos. A cobertura
precisa ser conferida tribunal a tribunal antes de o escritorio confiar o
monitoramento a esta fonte isoladamente.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import httpx

from ..core.capabilities import Capacidade
from ..core.cnj import NumeroCNJ
from ..core.resiliencia import LimitadorTaxa, Portal
from ..core.schemas import Confianca, Metodo
from ..core.tribunais import Tribunal
from .base import AdaptadorBase

BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"

# Teto pratico relatado: acima de 50 a resposta pode voltar vazia sem erro.
# [Nao verificado em documentacao oficial]
MAX_POR_PAGINA = 50

AVISO_SEM_CIENCIA = (
    "Leitura de publicacao no Diario de Justica Eletronico Nacional. Canal "
    "publico: NAO dispara ciencia nem inicia prazo processual. Nao confundir "
    "com abrir expediente no painel do portal, que dispara."
)


class AdaptadorDJEN(AdaptadorBase):
    nome = "djen"
    metodo = Metodo.API_OFICIAL
    confianca_padrao = Confianca.ALTA

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("portal", Portal(nome="djen", limitador=LimitadorTaxa(intervalo_minimo=0.5)))
        super().__init__(**kw)

    async def _consultar(self, parametros: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as cliente:
            resposta = await self._requisitar(
                cliente, method="GET", url=BASE, params=parametros,
                headers={"Accept": "application/json"},
            )
        if resposta.status_code == 403:
            raise PermissionError(
                "Diario recusou a requisicao (403). A infraestrutura que serve esta "
                "API bloqueia acesso por pais de origem; confirmado empiricamente que "
                "chamadas de fora do Brasil retornam 403 do CloudFront. Rode o "
                "servidor em maquina com saida brasileira."
            )
        resposta.raise_for_status()
        return resposta.json()

    @staticmethod
    def _normalizar(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "numero_processo": item.get("numero_processo") or item.get("numeroprocessocommascara"),
            "tribunal": item.get("siglaTribunal"),
            "orgao": item.get("nomeOrgao"),
            "tipo_comunicacao": item.get("tipoComunicacao"),
            "tipo_documento": item.get("tipoDocumento"),
            "data_disponibilizacao": item.get("data_disponibilizacao"),
            "meio": item.get("meio"),
            "texto": item.get("texto"),
            "hash": item.get("hash"),
            "link_certidao": item.get("link"),
            "destinatarios": item.get("destinatarios") or [],
            "advogados": item.get("destinatarioadvogados") or [],
        }

    async def publicacoes_por_oab(
        self, numero_oab: str, uf_oab: str, *,
        data_inicio: Optional[date] = None, data_fim: Optional[date] = None,
        sigla_tribunal: Optional[str] = None, pagina: int = 1, itens: int = 50,
    ) -> dict[str, Any]:
        """Monitoramento por inscricao na Ordem. Base do acompanhamento diario."""
        self.exigir_capacidade(Capacidade.LISTAR_PUBLICACOES_POR_OAB)
        parametros: dict[str, Any] = {
            "numeroOab": numero_oab.strip(),
            "ufOab": uf_oab.strip().upper(),
            "pagina": max(pagina, 1),
            "itensPorPagina": min(itens, MAX_POR_PAGINA),
        }
        if data_inicio:
            parametros["dataDisponibilizacaoInicio"] = data_inicio.isoformat()
        if data_fim:
            parametros["dataDisponibilizacaoFim"] = data_fim.isoformat()
        if sigla_tribunal:
            parametros["siglaTribunal"] = sigla_tribunal
        dados = await self._consultar(parametros)
        itens_brutos = dados.get("items") or []
        return {
            "total": dados.get("count", len(itens_brutos)),
            "pagina": parametros["pagina"],
            "itens_por_pagina": parametros["itensPorPagina"],
            "publicacoes": [self._normalizar(i) for i in itens_brutos],
            "proveniencia": self.proveniencia(endpoint=BASE, observacao=AVISO_SEM_CIENCIA).model_dump(),
        }

    async def publicacoes_por_processo(
        self, numero: NumeroCNJ, tribunal: Tribunal, *,
        data_inicio: Optional[date] = None, data_fim: Optional[date] = None,
        pagina: int = 1, itens: int = 50,
    ) -> dict[str, Any]:
        self.exigir_capacidade(Capacidade.LISTAR_PUBLICACOES_POR_PROCESSO)
        parametros: dict[str, Any] = {
            "numeroProcesso": numero.apenas_digitos,
            "siglaTribunal": tribunal.sigla_djen,
            "pagina": max(pagina, 1),
            "itensPorPagina": min(itens, MAX_POR_PAGINA),
        }
        if data_inicio:
            parametros["dataDisponibilizacaoInicio"] = data_inicio.isoformat()
        if data_fim:
            parametros["dataDisponibilizacaoFim"] = data_fim.isoformat()
        dados = await self._consultar(parametros)
        itens_brutos = dados.get("items") or []
        return {
            "numero": numero.formatado,
            "tribunal": tribunal.codigo,
            "total": dados.get("count", len(itens_brutos)),
            "publicacoes": [self._normalizar(i) for i in itens_brutos],
            "proveniencia": self.proveniencia(endpoint=BASE, observacao=AVISO_SEM_CIENCIA).model_dump(),
        }
