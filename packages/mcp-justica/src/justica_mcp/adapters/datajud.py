"""Adaptador da API publica do DataJud (Conselho Nacional de Justica).

Endpoint: https://api-publica.datajud.cnj.jus.br/api_publica_<tribunal>/_search
Autenticacao: cabecalho `Authorization: APIKey <chave publica do DPJ/CNJ>`.

Limite estrutural, verificado: o DataJud publica METADADOS e MOVIMENTOS. Nao
publica nomes de partes, advogados nem documentos, por politica do Conselho
Nacional de Justica amparada na Portaria nº. 160/2020. Por isso a busca por
nome de parte e por inscricao na Ordem NAO pode ser servida por aqui, e a
matriz de capacidades recusa essas chamadas antes de sair para a rede.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from ..core.capabilities import Capacidade
from ..core.cnj import NumeroCNJ
from ..core.schemas import Confianca, Metodo, RespostaProcesso, SistemaResolvido
from ..core.tribunais import Tribunal
from .base import AdaptadorBase

BASE = "https://api-publica.datajud.cnj.jus.br"

_OBS_FONTE = (
    "DataJud replica a base nacional e pode atrasar em relacao ao portal do "
    "tribunal. Nao substitui a consulta autenticada para fins de prazo."
)


class ChaveDataJudAusente(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Variavel DATAJUD_API_KEY nao definida. A chave e publica, emitida pelo "
            "Departamento de Pesquisas Judiciarias do Conselho Nacional de Justica; "
            "obtenha em https://datajud-wiki.cnj.jus.br/api-publica/acesso/ e "
            "grave no arquivo .env do servidor."
        )


class AdaptadorDataJud(AdaptadorBase):
    nome = "datajud"
    metodo = Metodo.API_OFICIAL
    confianca_padrao = Confianca.ALTA

    def __init__(self, chave: Optional[str] = None, **kw: Any) -> None:
        super().__init__(**kw)
        self._chave = chave or os.environ.get("DATAJUD_API_KEY") or ""

    @property
    def configurado(self) -> bool:
        return bool(self._chave)

    def _cabecalhos(self) -> dict[str, str]:
        if not self._chave:
            raise ChaveDataJudAusente()
        return {"Authorization": f"APIKey {self._chave}", "Content-Type": "application/json"}

    async def _buscar(self, tribunal: Tribunal, consulta: dict[str, Any]) -> dict[str, Any]:
        url = f"{BASE}/{tribunal.alias_datajud}/_search"
        async with httpx.AsyncClient(timeout=30) as cliente:
            resposta = await self._requisitar(
                cliente, method="POST", url=url, headers=self._cabecalhos(), json=consulta
            )
        if resposta.status_code == 403:
            raise PermissionError(
                "DataJud recusou a requisicao (403). Duas causas comuns: chave "
                "invalida ou expirada, ou acesso a partir de endereco fora do Brasil "
                "(a infraestrutura do Conselho Nacional de Justica bloqueia por pais). "
                "Confirme que o servidor roda com saida brasileira."
            )
        resposta.raise_for_status()
        return resposta.json()

    async def consultar_processo(
        self, numero: NumeroCNJ, tribunal: Tribunal, sistema: SistemaResolvido
    ) -> RespostaProcesso:
        self.exigir_capacidade(Capacidade.CONSULTAR_PROCESSO)
        dados = await self._buscar(
            tribunal,
            {"query": {"match": {"numeroProcesso": numero.apenas_digitos}}, "size": 1},
        )
        acertos = dados.get("hits", {}).get("hits", [])
        if not acertos:
            raise LookupError(
                f"Processo {numero.formatado} nao localizado no DataJud para "
                f"{tribunal.codigo}. Pode ser processo sigiloso, recem distribuido "
                f"(a base nacional atrasa) ou numero de outro tribunal."
            )
        f = acertos[0].get("_source", {})
        movimentos = sorted(
            f.get("movimentos", []) or [], key=lambda m: m.get("dataHora") or "", reverse=True
        )
        return RespostaProcesso(
            numero=numero.formatado,
            tribunal=tribunal.codigo,
            tribunal_nome=tribunal.nome,
            sistema_resolvido=sistema,
            classe=(f.get("classe") or {}).get("nome"),
            assuntos=[a.get("nome") for a in (f.get("assuntos") or []) if a.get("nome")],
            orgao_julgador=(f.get("orgaoJulgador") or {}).get("nome"),
            grau=f.get("grau"),
            data_ajuizamento=f.get("dataAjuizamento"),
            nivel_sigilo=f.get("nivelSigilo"),
            ultimo_andamento=movimentos[0] if movimentos else None,
            total_movimentos=len(movimentos),
            partes=None,
            advogados=None,
            documentos=None,
            indisponivel_nesta_fonte=[
                "partes", "advogados", "documentos", "valor_da_causa",
            ],
            proveniencia=self.proveniencia(
                endpoint=f"{BASE}/{tribunal.alias_datajud}/_search", observacao=_OBS_FONTE
            ),
        )

    async def listar_andamentos(
        self, numero: NumeroCNJ, tribunal: Tribunal, limite: int = 50
    ) -> dict[str, Any]:
        self.exigir_capacidade(Capacidade.LISTAR_ANDAMENTOS)
        dados = await self._buscar(
            tribunal,
            {"query": {"match": {"numeroProcesso": numero.apenas_digitos}}, "size": 1},
        )
        acertos = dados.get("hits", {}).get("hits", [])
        if not acertos:
            raise LookupError(f"Processo {numero.formatado} nao localizado no DataJud.")
        movimentos = sorted(
            acertos[0].get("_source", {}).get("movimentos", []) or [],
            key=lambda m: m.get("dataHora") or "", reverse=True,
        )
        return {
            "numero": numero.formatado,
            "tribunal": tribunal.codigo,
            "total": len(movimentos),
            "exibidos": min(limite, len(movimentos)),
            "movimentos": [
                {
                    "data_hora": m.get("dataHora"),
                    "codigo": m.get("codigo"),
                    "nome": m.get("nome"),
                    "complementos": m.get("complementosTabelados") or [],
                }
                for m in movimentos[:limite]
            ],
            "proveniencia": self.proveniencia(observacao=_OBS_FONTE).model_dump(),
        }
