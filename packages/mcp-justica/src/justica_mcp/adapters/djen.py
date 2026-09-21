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

# Teto de saturacao do campo `count`, observado em campo em 2026-09-21.
TETO_CONTAGEM = 10000

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
    def _cancelada(item: dict[str, Any]) -> bool:
        """Publicacao cancelada nao gera prazo.

        Derivado apenas de sinais explicitos. O campo `status` traz codigos de
        uma letra cujo significado NAO foi confirmado em documentacao oficial,
        entao ele e repassado cru e nunca interpretado aqui.
        """
        return (
            item.get("ativo") is False
            or bool(item.get("motivo_cancelamento"))
            or bool(item.get("data_cancelamento"))
        )

    @staticmethod
    def _normalizar_advogados(item: dict[str, Any]) -> list[dict[str, Any]]:
        """Achata `destinatarioadvogados[].advogado`.

        Estrutura confirmada em campo em 21 de setembro de 2026:
        cada vinculo traz um objeto `advogado` com `id`, `nome`, `numero_oab`
        e `uf_oab`.
        """
        saida = []
        for vinculo in item.get("destinatarioadvogados") or []:
            adv = vinculo.get("advogado") if isinstance(vinculo, dict) else None
            if not isinstance(adv, dict):
                continue
            saida.append({
                "nome": adv.get("nome"),
                "numero_oab": str(adv.get("numero_oab")) if adv.get("numero_oab") is not None else None,
                "uf_oab": adv.get("uf_oab"),
            })
        return saida

    @staticmethod
    def _normalizar_destinatarios(item: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"nome": d.get("nome"), "polo": d.get("polo")}
            for d in (item.get("destinatarios") or [])
            if isinstance(d, dict)
        ]

    @staticmethod
    def _cita_inscricao(publicacao: dict[str, Any], numero_oab: str, uf_oab: str) -> bool:
        """A publicacao realmente nomeia a inscricao consultada?

        Conferido em campo: o servidor filtra por numero E seccional
        corretamente. Esta verificacao existe como guarda de regressao, nao por
        desconfianca do momento: se o filtro mudar de comportamento, a falha
        seria SILENCIOSA, e a banca passaria a monitorar processo de terceiro
        sem nenhum sinal. O custo de conferir e desprezivel; o de nao conferir,
        nao e.
        """
        alvo = numero_oab.strip().lstrip("0")
        uf = uf_oab.strip().upper()
        return any(
            (a["numero_oab"] or "").lstrip("0") == alvo and (a["uf_oab"] or "").upper() == uf
            for a in publicacao["advogados"]
        )

    @classmethod
    def _normalizar(cls, item: dict[str, Any]) -> dict[str, Any]:
        cancelada = cls._cancelada(item)
        return {
            # `id` e a chave estavel de deduplicacao entre consultas.
            "id": item.get("id"),
            "numero_comunicacao": item.get("numeroComunicacao"),
            "numero_processo": item.get("numero_processo"),
            "numero_processo_formatado": item.get("numeroprocessocommascara"),
            "tribunal": item.get("siglaTribunal"),
            "orgao": item.get("nomeOrgao"),
            "classe": item.get("nomeClasse"),
            "codigo_classe": item.get("codigoClasse"),
            "tipo_comunicacao": item.get("tipoComunicacao"),
            "tipo_documento": item.get("tipoDocumento"),
            "data_disponibilizacao": item.get("data_disponibilizacao"),
            "meio": item.get("meio"),
            "meio_completo": item.get("meiocompleto"),
            "texto": item.get("texto"),
            "hash": item.get("hash"),
            "link_certidao": item.get("link"),
            "destinatarios": cls._normalizar_destinatarios(item),
            "advogados": cls._normalizar_advogados(item),
            # Sinais de cancelamento: uma publicacao cancelada NAO gera prazo,
            # e tratar como viva produziria prazo fantasma no monitoramento.
            "cancelada": cancelada,
            "ativo": item.get("ativo"),
            "status_bruto": item.get("status"),
            "motivo_cancelamento": item.get("motivo_cancelamento"),
            "data_cancelamento": item.get("data_cancelamento"),
            "alerta": (
                "PUBLICACAO CANCELADA: nao gera prazo. Confira antes de considerar."
                if cancelada else None
            ),
        }

    @staticmethod
    def _resumo_total(dados: dict[str, Any], itens: list[Any]) -> dict[str, Any]:
        """O campo `count` da API satura em 10.000.

        Observado em campo: consultas por tribunal devolvem exatamente 10000,
        valor identico para tribunais de portes muito diferentes. Reportar isso
        como total faria o agente afirmar um numero falso e paginar ate um fim
        que nao existe.
        """
        bruto = dados.get("count", len(itens)) if isinstance(dados, dict) else len(itens)
        saturado = isinstance(bruto, int) and bruto >= TETO_CONTAGEM
        return {
            "total_informado": bruto,
            "total_e_estimativa": saturado,
            "observacao_total": (
                f"A API satura a contagem em {TETO_CONTAGEM}. O total real e "
                f"MAIOR OU IGUAL a esse valor, e nao deve ser citado como exato. "
                f"Refine por tribunal, processo ou janela de datas."
                if saturado else None
            ),
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
        publicacoes = [self._normalizar(i) for i in itens_brutos]
        for pub in publicacoes:
            pub["inscricao_consultada_confere"] = self._cita_inscricao(
                pub, parametros["numeroOab"], parametros["ufOab"]
            )
        divergentes = [p for p in publicacoes if not p["inscricao_consultada_confere"]]
        return {
            **self._resumo_total(dados, itens_brutos),
            "pagina": parametros["pagina"],
            "itens_por_pagina": parametros["itensPorPagina"],
            "canceladas_nesta_pagina": sum(1 for p in publicacoes if p["cancelada"]),
            "divergentes_nesta_pagina": len(divergentes),
            "alerta_divergencia": (
                f"{len(divergentes)} publicacao(oes) nao nomeiam a inscricao "
                f"{parametros['numeroOab']}/{parametros['ufOab']}. Podem ser de outro "
                f"advogado com o mesmo numero em outra seccional. NAO trate como "
                f"processo da banca sem conferir."
                if divergentes else None
            ),
            "publicacoes": publicacoes,
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
        publicacoes = [self._normalizar(i) for i in itens_brutos]
        return {
            "numero": numero.formatado,
            "tribunal": tribunal.codigo,
            **self._resumo_total(dados, itens_brutos),
            "canceladas_nesta_pagina": sum(1 for p in publicacoes if p["cancelada"]),
            "publicacoes": publicacoes,
            "proveniencia": self.proveniencia(endpoint=BASE, observacao=AVISO_SEM_CIENCIA).model_dump(),
        }
