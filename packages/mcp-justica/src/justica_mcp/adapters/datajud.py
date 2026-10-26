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
        # `None` significa "leia do ambiente"; `""` significa "sem chave, de
        # proposito". O encadeamento com `or` confundia os dois: quem passasse
        # uma configuracao vazia esperando ficar sem chave acabava usando
        # silenciosamente a chave que estivesse no ambiente.
        bruta = os.environ.get("DATAJUD_API_KEY", "") if chave is None else chave
        self._chave = bruta.strip()

    @property
    def configurado(self) -> bool:
        return bool(self._chave)

    def _cabecalhos(self) -> dict[str, str]:
        if not self._chave:
            raise ChaveDataJudAusente()
        return {"Authorization": f"APIKey {self._chave}", "Content-Type": "application/json"}

    def _diagnostico_do_401(self) -> str:
        """Diz POR QUE a chave foi recusada, sem mostrar a chave.

        Em 26/10/2026 o 401 custou uma noite. Tudo o que se podia medir dizia
        que estava certo: a mesma chave respondia 200 de duas maquinas
        diferentes, o valor no `.env` tinha os 60 caracteres exatos e sem
        caractere invisivel, e o campo da extensao estava vazio. O que faltava
        era saber QUAL valor o servidor estava usando, e de onde ele veio.
        O 401 cru nao dizia nada disso, e nem sequer tinha ramo proprio: caia
        no `raise_for_status` e virava um `HTTPStatusError` sem contexto.

        Nenhum valor aparece aqui: so comprimento e procedencia.
        """
        from ..core.config import (parece_molde_nao_substituido,
                                   sobrescritas_pelo_ambiente)

        partes = [
            "DataJud recusou a chave (401). A chave e publica e nao expira "
            "por uso, entao o problema costuma ser QUAL valor chegou ate aqui."
        ]
        partes.append(f"A chave em uso tem {len(self._chave)} caractere(s).")
        if parece_molde_nao_substituido(self._chave):
            partes.append(
                "E ela e um MOLDE nao substituido: o campo da extensao ficou "
                "vazio e o aplicativo mandou o texto do molde no lugar de nada. "
                "Esse texto vence o arquivo .env por precedencia de ambiente."
            )
        # A comparacao com o arquivo so e afirmada quando o arquivo pode ser
        # lido E tem a chave. "Nao achei diferenca" nao e "sao iguais": o
        # arquivo pode nem existir onde este processo esta rodando.
        try:
            from ..core.config import pares_do_arquivo

            no_arquivo = pares_do_arquivo().get("DATAJUD_API_KEY")
            vencidas = {c: (a, b) for c, a, b, _ in sobrescritas_pelo_ambiente()}
        except Exception:  # diagnostico nunca derruba a chamada
            no_arquivo, vencidas = None, {}

        if "DATAJUD_API_KEY" in vencidas:
            do_arquivo, do_ambiente = vencidas["DATAJUD_API_KEY"]
            partes.append(
                f"O arquivo .env traz um valor de {do_arquivo} caractere(s), "
                f"diferente do que esta em uso ({do_ambiente}). O programa usa "
                "o do AMBIENTE, nao o do arquivo: limpe o campo da extensao ou "
                "a variavel do sistema para o arquivo voltar a valer."
            )
        elif no_arquivo is not None:
            partes.append(
                "O valor em uso e o mesmo do arquivo .env, entao foi a chave "
                "gravada que o servico recusou: confira a vigente em "
                "https://datajud-wiki.cnj.jus.br/api-publica/acesso/."
            )
        else:
            partes.append(
                "Nao consegui ler a chave do arquivo .env deste processo para "
                "comparar, entao nao sei dizer se o valor em uso veio de la ou "
                "do ambiente. Rode o comando `ambiente` para ver os dois."
            )
        return " ".join(partes)

    async def _buscar(self, tribunal: Tribunal, consulta: dict[str, Any]) -> dict[str, Any]:
        url = f"{BASE}/{tribunal.alias_datajud}/_search"
        async with httpx.AsyncClient(timeout=30) as cliente:
            resposta = await self._requisitar(
                cliente, method="POST", url=url, headers=self._cabecalhos(), json=consulta
            )
        if resposta.status_code == 401:
            raise PermissionError(self._diagnostico_do_401())
        if resposta.status_code == 403:
            raise PermissionError(
                "DataJud recusou a requisicao (403). Duas causas comuns: chave "
                "invalida ou expirada, ou acesso a partir de endereco fora do Brasil "
                "(a infraestrutura do Conselho Nacional de Justica bloqueia por pais). "
                "Confirme que o servidor roda com saida brasileira."
            )
        resposta.raise_for_status()
        return resposta.json()

    async def buscar_documento(
        self, numero: NumeroCNJ, tribunal: Tribunal
    ) -> dict[str, Any]:
        """Devolve o `_source` cru do processo na base nacional.

        Separado de `montar_resposta` para que quem chama consulte UMA vez e
        reaproveite o documento tanto para a ficha quanto para resolver o
        sistema, em vez de ir duas vezes a rede pelo mesmo dado.
        """
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
        return acertos[0].get("_source", {})

    def montar_resposta(
        self,
        numero: NumeroCNJ,
        tribunal: Tribunal,
        sistema: SistemaResolvido,
        f: dict[str, Any],
    ) -> RespostaProcesso:
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
            id_datajud=f.get("id"),
            atualizado_em_na_fonte=f.get("dataHoraUltimaAtualizacao"),
            sistema_informado_pela_fonte=f.get("sistema"),
            formato=f.get("formato"),
            partes=None,
            advogados=None,
            documentos=None,
            indisponivel_nesta_fonte=[
                "partes", "advogados", "documentos", "valor_da_causa",
            ],
            proveniencia=self.proveniencia(
                endpoint=f"{BASE}/{tribunal.alias_datajud}/_search",
                observacao=(
                    f"{_OBS_FONTE} Ultima atualizacao desta ficha na base nacional: "
                    f"{f.get('dataHoraUltimaAtualizacao')}."
                    if f.get("dataHoraUltimaAtualizacao") else _OBS_FONTE
                ),
            ),
        )

    async def consultar_processo(
        self, numero: NumeroCNJ, tribunal: Tribunal, sistema: SistemaResolvido
    ) -> RespostaProcesso:
        """Caminho curto: uma chamada, sem reaproveitar o documento."""
        return self.montar_resposta(
            numero, tribunal, sistema, await self.buscar_documento(numero, tribunal)
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
                    "orgao_julgador": m.get("orgaoJulgador"),
                }
                for m in movimentos[:limite]
            ],
            "proveniencia": self.proveniencia(observacao=_OBS_FONTE).model_dump(),
        }
