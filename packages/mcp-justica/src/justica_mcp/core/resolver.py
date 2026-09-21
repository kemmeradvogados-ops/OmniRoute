"""Resolucao de sistema: empirica, cacheada e com validade curta.

Este modulo existe porque `tribunal -> sistema` nao e tabelavel. No Tribunal de
Justica do Estado do Rio de Janeiro convivem PJe, eproc e DCP; no Tribunal de
Justica do Estado de Sao Paulo convivem e-SAJ e eproc. Um mapa fixo erraria em
massa e, pior, erraria em silencio.

Ordem de decisao:

  1. Cache valido        -> devolve, confianca media, origem 'cache'.
  2. Sondagem            -> pergunta a adaptadores registrados quem reconhece o
                            processo. Unica fonte de confianca alta.
  3. Regra de migracao   -> pista do arquivo `dados/migracao.yaml`, confianca
                            no maximo media, origem 'regra_migracao'.
  4. Indeterminado       -> devolve a ordem de candidatos e diz por que nao sabe.

O passo 2 depende de adaptadores autenticados e entra na Fase 2. Ate la o
resolvedor responde honestamente 'indeterminado' em vez de chutar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable, Optional

import yaml

from .cnj import NumeroCNJ
from .estado import Estado
from .schemas import Confianca, SistemaResolvido, agora_iso
from .tribunais import Sistema, Tribunal, identificar_tribunal

# Validade curta de proposito: a migracao reposiciona processos, e um cache
# longo levaria o agente ao adaptador errado sem sinal nenhum.
VALIDADE_RESOLUCAO = timedelta(hours=12)
VALIDADE_INDETERMINADO = timedelta(minutes=30)

# Sonda: recebe o numero e devolve True se o sistema reconhece o processo.
Sonda = Callable[[NumeroCNJ], Awaitable[bool]]
_SONDAS: dict[tuple[str, Sistema], Sonda] = {}


def registrar_sonda(codigo_tribunal: str, sistema: Sistema, sonda: Sonda) -> None:
    """Fase 2 registra aqui as sondas de portal. Fase 1 nao registra nenhuma."""
    _SONDAS[(codigo_tribunal, sistema)] = sonda


@dataclass(frozen=True)
class RegraMigracao:
    descricao: str
    sistema_provavel: Optional[str]
    confianca: str
    vigencia_inicio: str
    fonte: str
    ano_ajuizamento_minimo: Optional[int] = None
    ano_ajuizamento_maximo: Optional[int] = None

    def aplica(self, ano: int) -> bool:
        if self.ano_ajuizamento_minimo is not None and ano < self.ano_ajuizamento_minimo:
            return False
        if self.ano_ajuizamento_maximo is not None and ano > self.ano_ajuizamento_maximo:
            return False
        return True


@lru_cache(maxsize=1)
def carregar_regras(caminho: Optional[str] = None) -> dict[str, list[RegraMigracao]]:
    arquivo = Path(caminho) if caminho else Path(__file__).parent.parent / "dados" / "migracao.yaml"
    if not arquivo.exists():
        return {}
    bruto = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
    return {
        tribunal: [RegraMigracao(**regra) for regra in regras]
        for tribunal, regras in bruto.items()
    }


def _chave_cache(numero: NumeroCNJ) -> str:
    return f"sistema:{numero.apenas_digitos}"


async def resolver_sistema(
    numero: NumeroCNJ,
    estado: Estado,
    *,
    ignorar_cache: bool = False,
) -> SistemaResolvido:
    tribunal: Tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
    candidatos = [s.value for s in tribunal.sistemas_candidatos]

    # 1. cache
    if not ignorar_cache:
        registro = estado.obter_cache(_chave_cache(numero))
        if registro and not registro["vencido"]:
            guardado = registro["valor"]
            return SistemaResolvido(
                sistema=guardado["sistema"],
                resolvido_em=guardado.get("resolvido_em", registro["gravado_em"]),
                valido_ate=registro["valido_ate"],
                origem_da_resolucao="cache",
                candidatos=guardado.get("candidatos", candidatos),
                confianca=Confianca.MEDIA,
                motivo=(
                    "Servido do cache local. Resolucao original: "
                    f"{guardado.get('origem_da_resolucao', 'desconhecida')}."
                ),
            )

    # 2. sondagem (Fase 2)
    for sistema in tribunal.sistemas_candidatos:
        sonda = _SONDAS.get((tribunal.codigo, sistema))
        if sonda is None:
            continue
        try:
            if await sonda(numero):
                resolvido = SistemaResolvido(
                    sistema=sistema.value,
                    origem_da_resolucao="sondagem",
                    candidatos=candidatos,
                    confianca=Confianca.ALTA,
                    motivo=f"O sistema {sistema.value} reconheceu o processo.",
                )
                estado.gravar_cache(
                    _chave_cache(numero), resolvido.model_dump(), VALIDADE_RESOLUCAO
                )
                return resolvido
        except Exception as exc:  # sonda quebrada nao pode derrubar a resolucao
            estado.registrar(
                acao="sondagem_falhou", tribunal=tribunal.codigo, sistema=sistema.value,
                numero=numero.formatado, resultado="erro", detalhe=type(exc).__name__,
            )

    # 3. regra de migracao
    ano = int(numero.ano)
    for regra in carregar_regras().get(tribunal.codigo, []):
        if not regra.aplica(ano) or regra.sistema_provavel is None:
            continue
        resolvido = SistemaResolvido(
            sistema=regra.sistema_provavel,
            origem_da_resolucao="regra_migracao",
            candidatos=candidatos,
            confianca=Confianca(regra.confianca),
            motivo=(
                f"Pista de migracao, nao confirmacao: {regra.descricao.strip()} "
                f"Vigencia desde {regra.vigencia_inicio}. Fonte: {regra.fonte}"
            ),
        )
        estado.gravar_cache(_chave_cache(numero), resolvido.model_dump(), VALIDADE_RESOLUCAO)
        return resolvido

    # 4. indeterminado
    indeterminado = SistemaResolvido(
        sistema=Sistema.INDETERMINADO.value,
        origem_da_resolucao="indeterminado",
        candidatos=candidatos,
        confianca=Confianca.BAIXA,
        motivo=(
            f"Sem sonda autenticada disponivel para {tribunal.codigo} e sem regra de "
            f"migracao aplicavel ao ano {ano}. Ordem de sondagem sugerida: "
            f"{', '.join(candidatos)}. {tribunal.observacao}"
        ),
    )
    estado.gravar_cache(_chave_cache(numero), indeterminado.model_dump(), VALIDADE_INDETERMINADO)
    return indeterminado
