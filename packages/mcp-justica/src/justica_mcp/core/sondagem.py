"""Sondagem em lote: descobrir em qual sistema cada processo corre.

O problema, medido em 25/10/2026: cinco processos do Tribunal de Justica do
Rio de Janeiro voltaram todos 'indeterminado'. Aquele tribunal opera tres
sistemas ao mesmo tempo (eproc, PJe e DCP) e o numero do processo nao diz em
qual deles o processo esta. Descobrir um por um custaria uma tentativa
autenticada por processo, de uma janela de dezoito por hora.

A saida e inverter a conta: a autenticacao e cara, a BUSCA dentro de uma
sessao ja aberta e barata. Entao autentica-se UMA vez por sistema e
procura-se a lista inteira ali dentro. Dez processos custam o mesmo que dois.

ORDEM DOS SISTEMAS, regra do operador em 25/10/2026:

    eproc  ->  PJe  ->  DCP

    1. O eproc e o sistema mais novo do tribunal. Processo achado nele esta
       onde vai ficar: nao ha para onde migrar depois.
    2. O PJe vem em seguida. Processo achado nele em primeiro grau, sem
       indicio de recurso, tem a integra ali mesmo.
    3. O DCP e o mais antigo e por isso vem POR ULTIMO. Comecar por ele seria
       o pior criterio: acharia a copia de processo ja migrado e a fixaria
       como resposta. Chegando por ultimo, os migrados ja sairam da fila.

    Quando a migracao ocorre, as copias vao junto (regra do operador, mesma
    data). Por isso achar num sistema encerra a busca daquele processo: nao
    ha pedaco dos autos deixado para tras no sistema antigo.

    A excecao e o recurso. Processo que subiu para a segunda instancia pode
    ter o primeiro grau num sistema e o segundo noutro, e ai os dois
    precisam ser varridos. O numero do processo nao revela se ha recurso, e
    a sonda so sabe responder achado ou nao achado, entao isto NAO e
    adivinhado: quem chama pede `conferir_segundo_grau` quando for o caso, e
    o relatorio avisa, em cada achado no PJe, que o segundo grau pode estar
    noutro sistema.

TRES VALORES, NUNCA DOIS. A sonda devolve True, False ou None. `None` e "nao
consegui ver", que NAO e "nao existe": pode ser tela que nao carregou, busca
que deu erro, sessao que caiu. Tratar os dois como a mesma coisa faria o
relatorio afirmar que um processo nao esta num sistema quando ninguem olhou,
e processo dado como inexistente e prazo perdido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from .cnj import NumeroCNJ
from .estado import Estado
from .schemas import Confianca, SistemaResolvido
from .tribunais import Sistema, Tribunal, identificar_tribunal

# Recebe o sistema e a lista de numeros pendentes; devolve, por numero em
# apenas digitos, True (o sistema reconheceu), False (nao reconheceu) ou None
# (nao deu para ver). Quem implementa autentica UMA vez e procura todos.
SondaEmLote = Callable[[Sistema, list[NumeroCNJ]], Awaitable[dict[str, Optional[bool]]]]


class ProcessosDeTribunaisDiferentes(ValueError):
    """Uma varredura, um tribunal. Misturar abriria portais diferentes na
    mesma corrida e gastaria autenticacao em sistema que nem e do processo."""


@dataclass
class LinhaDaSondagem:
    """O que se descobriu sobre UM processo."""

    numero: str
    por_sistema: dict = field(default_factory=dict)
    sistema: Optional[str] = None
    confianca: str = Confianca.BAIXA.value
    observacao: str = ""

    @property
    def achados(self) -> list:
        return [s for s, v in self.por_sistema.items() if v is True]

    @property
    def cegos(self) -> list:
        return [s for s, v in self.por_sistema.items() if v is None]


def _conclusao(linha: LinhaDaSondagem, ordem: list, conferiu_tudo: bool) -> None:
    """Preenche sistema, confianca e observacao. Nao escolhe por conta propria
    quando ha mais de um achado: avisa e devolve a decisao ao advogado."""
    achados = linha.achados
    cegos = linha.cegos

    if len(achados) == 1:
        linha.sistema = achados[0]
        linha.confianca = Confianca.ALTA.value
        linha.observacao = f"O sistema {achados[0]} reconheceu o processo."
        if achados[0] == Sistema.PJE.value and not conferiu_tudo:
            linha.observacao += (
                " Se este processo tiver recurso em segunda instancia, o"
                " segundo grau pode estar noutro sistema: rode de novo com"
                " conferir_segundo_grau para varrer os demais."
            )
        return

    if len(achados) > 1:
        # Nao escolher sozinho e deliberado. Processo que aparece em dois
        # sistemas e exatamente o caso em que errar custa caro, e o advogado
        # sabe qual grau esta onde.
        linha.sistema = None
        linha.confianca = Confianca.MEDIA.value
        linha.observacao = (
            f"ATENCAO: reconhecido em mais de um sistema ({', '.join(achados)}). "
            "Pode ser processo migrado cuja copia antiga continua visivel, ou "
            "primeiro e segundo grau em sistemas diferentes. Nao escolhi por "
            "voce: confira qual grau esta onde antes de agir sobre prazo."
        )
        return

    if cegos:
        linha.sistema = None
        linha.confianca = Confianca.BAIXA.value
        linha.observacao = (
            f"Nenhum sistema reconheceu, MAS {', '.join(cegos)} nao conseguiu "
            "responder. Nao achado aqui nao prova que o processo nao esta la: "
            "ninguem olhou. Sonde de novo antes de concluir."
        )
        return

    naos = [s for s in ordem if linha.por_sistema.get(s) is False]
    linha.sistema = None
    linha.confianca = Confianca.BAIXA.value
    linha.observacao = (
        f"Sondado em {', '.join(naos)} e nenhum reconheceu o processo. "
        "Confira a transcricao do numero e se o escritorio tem acesso a ele "
        "neste tribunal."
    ) if naos else "Nenhum sistema foi sondado."


async def sondar_em_lote(
    numeros: list,
    estado: Estado,
    sonda: SondaEmLote,
    *,
    conferir_segundo_grau: bool = False,
    gravar_cache: bool = True,
) -> dict:
    """Varre os sistemas do tribunal procurando cada processo da lista.

    Uma autenticacao por sistema, no maximo. Sistema cuja fila esvaziou NAO e
    aberto: se todos os processos forem achados no eproc, a varredura custa
    uma autenticacao e para ali.
    """
    if not numeros:
        return {"tribunal": None, "ordem": [], "linhas": [], "sistemas_abertos": []}

    tribunais = {n.chave_segmento_tribunal for n in numeros}
    if len(tribunais) > 1:
        raise ProcessosDeTribunaisDiferentes(
            "Uma varredura, um tribunal. Vieram processos de "
            f"{len(tribunais)} tribunais diferentes: {', '.join(sorted(tribunais))}. "
            "Separe por tribunal e rode uma varredura para cada."
        )

    tribunal: Tribunal = identificar_tribunal(numeros[0].chave_segmento_tribunal)
    ordem = [s.value for s in tribunal.sistemas_candidatos]
    linhas = {n.apenas_digitos: LinhaDaSondagem(numero=n.formatado) for n in numeros}
    por_digitos = {n.apenas_digitos: n for n in numeros}
    pendentes = list(por_digitos)
    abertos: list = []

    for posicao, sistema in enumerate(tribunal.sistemas_candidatos):
        if not pendentes:
            break
        abertos.append(sistema.value)
        respostas = await sonda(sistema, [por_digitos[d] for d in pendentes])
        ultimo = posicao == len(tribunal.sistemas_candidatos) - 1
        ainda: list = []
        for digitos in pendentes:
            resposta = respostas.get(digitos)
            linhas[digitos].por_sistema[sistema.value] = resposta
            # Achou: sai da fila, salvo quando o advogado pediu para conferir
            # o segundo grau e ainda ha sistema por varrer.
            if resposta is True and not (conferir_segundo_grau and not ultimo):
                continue
            ainda.append(digitos)
        pendentes = ainda

    for digitos, linha in linhas.items():
        _conclusao(linha, ordem, conferir_segundo_grau)
        if gravar_cache and linha.sistema:
            _gravar(estado, por_digitos[digitos], linha, ordem)

    estado.registrar(
        acao="sondagem_em_lote", tribunal=tribunal.codigo,
        resultado=f"{len(numeros)} processo(s), {len(abertos)} autenticacao(oes)")

    return {
        "tribunal": tribunal.codigo,
        "ordem": ordem,
        "sistemas_abertos": abertos,
        "autenticacoes": len(abertos),
        "linhas": [vars(linha) for linha in linhas.values()],
    }


def _gravar(estado: Estado, numero: NumeroCNJ, linha: LinhaDaSondagem, ordem: list) -> None:
    """Guarda o resultado confirmado para o processo nao ser sondado de novo.

    Usa a mesma chave e a mesma validade do resolvedor de proposito: sondagem
    e resolucao respondem a mesma pergunta, e dois caches com a mesma pergunta
    e prazos diferentes se contradizem em silencio.
    """
    from . import historico_sistemas
    from .resolver import VALIDADE_RESOLUCAO, _chave_cache

    # O historico fica na pasta compartilhada: esta sondagem economiza a
    # tentativa de todos os outros advogados da banca, nao so a de quem rodou.
    try:
        historico_sistemas.registrar(
            numero.apenas_digitos, numero.formatado, linha.sistema,
            origem="sondagem no portal")
    except OSError:
        # Pasta compartilhada indisponivel nao pode derrubar a sondagem que ja
        # foi paga: o resultado continua valendo nesta corrida e no cache local.
        pass

    resolvido = SistemaResolvido(
        sistema=linha.sistema,
        origem_da_resolucao="sondagem",
        candidatos=ordem,
        confianca=Confianca(linha.confianca),
        motivo=linha.observacao,
    )
    estado.gravar_cache(_chave_cache(numero), resolvido.model_dump(), VALIDADE_RESOLUCAO)
