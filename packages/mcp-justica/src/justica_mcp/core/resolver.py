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
from datetime import datetime, timedelta, timezone
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



# Nomes de sistema conforme o campo `sistema.nome` do DataJud.
# CONFIRMADO em campo: "PJe" (codigo 1). Os demais nomes sao o rotulo esperado
# e AINDA NAO foram observados. Por isso o casamento e feito pelo NOME
# normalizado, nunca pelo `codigo`: so um codigo foi visto, e inventar uma
# tabela de codigos a partir de uma amostra seria chute com cara de mapeamento.
_NOMES_SISTEMA: dict[str, Sistema] = {
    "pje": Sistema.PJE,
    "eproc": Sistema.EPROC,
    "esaj": Sistema.ESAJ,
    "saj": Sistema.ESAJ,
    "dcp": Sistema.DCP,
    "cpe": Sistema.CPE,
}

# Janela em que a ficha da base nacional ainda e considerada recente.
# Valor de julgamento, nao numero verificado: serve para separar "informacao de
# poucos dias" de "informacao que pode ter perdido uma migracao".
DIAS_FICHA_RECENTE = 30


def _normalizar_nome(nome: str) -> str:
    import unicodedata

    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", nome) if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def sistema_de_documento(
    fonte: dict, tribunal: Tribunal
) -> Optional[SistemaResolvido]:
    """Extrai o sistema do documento do DataJud. Funcao pura, sem rede.

    Confianca deliberadamente limitada em dois casos:

    1. Tribunal com mais de um sistema candidato (Rio de Janeiro e Sao Paulo,
       ambos em migracao). E justamente onde a base nacional pode estar
       atrasada em relacao a uma migracao ja ocorrida, e onde errar custa caro.
    2. Ficha antiga ou sem data de atualizacao.
    """
    bruto = (fonte or {}).get("sistema")
    if not isinstance(bruto, dict) or not bruto.get("nome"):
        return None

    nome = str(bruto["nome"])
    sistema = _NOMES_SISTEMA.get(_normalizar_nome(nome))
    atualizado = fonte.get("dataHoraUltimaAtualizacao")

    recente = False
    if isinstance(atualizado, str):
        try:
            quando = datetime.fromisoformat(atualizado.replace("Z", "+00:00"))
            recente = (datetime.now(timezone.utc) - quando).days <= DIAS_FICHA_RECENTE
        except ValueError:
            recente = False

    ambiguo = len(tribunal.sistemas_candidatos) > 1
    if sistema is None:
        # Nome desconhecido nao vira chute: devolve indeterminado dizendo o que
        # a fonte respondeu, para o operador incluir o nome no mapa.
        return SistemaResolvido(
            sistema=Sistema.INDETERMINADO.value,
            origem_da_resolucao="datajud",
            candidatos=[s.value for s in tribunal.sistemas_candidatos],
            confianca=Confianca.BAIXA,
            motivo=(
                f"A base nacional informou o sistema {nome!r}, que nao consta do "
                f"mapa de nomes conhecidos. Acrescente-o a `_NOMES_SISTEMA` apos "
                f"conferir. Ficha atualizada em {atualizado}."
            ),
        )

    if ambiguo:
        confianca = Confianca.MEDIA
        ressalva = (
            f" {tribunal.codigo} opera mais de um sistema em migracao, e a base "
            f"nacional pode nao ter registrado uma migracao recente. Confirme no "
            f"portal antes de agir sobre prazo."
        )
    else:
        confianca = Confianca.ALTA if recente else Confianca.MEDIA
        ressalva = "" if recente else " Ficha nao atualizada recentemente."

    return SistemaResolvido(
        sistema=sistema.value,
        origem_da_resolucao="datajud",
        candidatos=[s.value for s in tribunal.sistemas_candidatos],
        confianca=confianca,
        motivo=(
            f"Declarado pela base nacional como {nome!r}. Ficha atualizada em "
            f"{atualizado}.{ressalva}"
        ),
    )


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
    documento_datajud: Optional[dict] = None,
    nota_da_base_nacional: Optional[str] = None,
) -> SistemaResolvido:
    """Resolve o sistema do processo.

    `documento_datajud` e o `_source` ja obtido da base nacional. Passa-lo
    evita uma segunda ida a rede quando quem chama ja consultou o processo.

    `nota_da_base_nacional` e o que QUEM CHAMOU sabe sobre essa consulta e o
    resolvedor nao tem como saber: se a chave esta configurada, se a chamada
    falhou, se nao ha ficha. Sem ela, um 'indeterminado' nao distingue "a base
    nacional nao sabe" de "a base nacional nem foi perguntada", e em
    25/10/2026 cinco processos voltaram indeterminados sem que desse para
    saber qual dos dois era. Diagnostico que nao distingue causa custa
    tentativa autenticada para descobrir o que era de graca.
    """
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

    # 1.5 historico da banca: sondagem que ALGUEM ja pagou, aqui ou noutra
    # maquina. Vem antes da sonda porque e de graca e a sonda custa tentativa
    # autenticada; vem depois do cache porque o cache e mais fresco. A data da
    # confirmacao entra na resposta e limita a confianca: migracao move
    # processo, e registro antigo pode estar apontando para o portal errado.
    if not ignorar_cache:
        from . import historico_sistemas

        guardado = historico_sistemas.consultar(numero.apenas_digitos)
        if guardado:
            dias = historico_sistemas.dias_desde(guardado)
            fresco = historico_sistemas.recente(guardado)
            quando = guardado.get("confirmado_em", "data nao registrada")
            idade = f"ha {dias} dia(s)" if dias is not None else "em data incerta"
            return SistemaResolvido(
                sistema=guardado["sistema"],
                origem_da_resolucao="historico_da_banca",
                candidatos=candidatos,
                confianca=Confianca.MEDIA if fresco else Confianca.BAIXA,
                motivo=(
                    f"O escritorio confirmou este processo em "
                    f"{guardado['sistema']} {idade} ({quando}), por "
                    f"{guardado.get('origem', 'origem nao registrada')}."
                    + ("" if fresco else
                       " Confirmacao antiga: o processo pode ter migrado desde"
                       " entao. Sonde de novo antes de agir sobre prazo.")
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

    # 3. base nacional: evidencia oficial, porem possivelmente atrasada
    nota = nota_da_base_nacional
    if documento_datajud is not None:
        do_datajud = sistema_de_documento(documento_datajud, tribunal)
        if do_datajud is not None and do_datajud.sistema != Sistema.INDETERMINADO.value:
            estado.gravar_cache(
                _chave_cache(numero), do_datajud.model_dump(), VALIDADE_RESOLUCAO
            )
            return do_datajud
        if do_datajud is None:
            nota = ("a base nacional tem ficha deste processo, mas ela nao traz "
                    "o campo do sistema")
        else:
            nota = do_datajud.motivo

    # 4. regra de migracao
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

    # 5. indeterminado
    indeterminado = SistemaResolvido(
        sistema=Sistema.INDETERMINADO.value,
        origem_da_resolucao="indeterminado",
        candidatos=candidatos,
        confianca=Confianca.BAIXA,
        base_nacional=nota or "sem informacao sobre a consulta a base nacional",
        motivo=(
            f"Sem sonda autenticada disponivel para {tribunal.codigo} e sem regra de "
            f"migracao aplicavel ao ano {ano}. Base nacional: "
            f"{nota or 'sem informacao sobre a consulta'}. Ordem de sondagem "
            f"sugerida: {', '.join(candidatos)}. {tribunal.observacao}"
        ),
    )
    estado.gravar_cache(_chave_cache(numero), indeterminado.model_dump(), VALIDADE_INDETERMINADO)
    return indeterminado
