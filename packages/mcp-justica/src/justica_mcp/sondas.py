"""Sondas de portal: "este processo esta NESTE sistema?"

A resposta tem TRES valores, e isso e o coracao do modulo:

    True   o sistema reconheceu o processo. Sinal positivo, nomeado, visto em
           campo nas corridas de 21 e 23/10/2026.
    None   nao deu para ver. Tela que nao montou, busca que deu erro, sessao
           que caiu, ou simplesmente processo que nao esta ali. Hoje nao da
           para separar esses casos, e por isso eles nao sao separados.
    False  o sistema declarou que nao tem este processo. HOJE NUNCA E
           DEVOLVIDO. Ver abaixo.

POR QUE `False` AINDA NAO EXISTE

Em todas as corridas de campo deste projeto o processo FOI achado. Ninguem
nunca buscou, num destes portais, um processo que nao estivesse la, e por
isso ninguem nunca viu a tela de "nada encontrado" de nenhum deles. Pode ser
faixa vermelha, tabela vazia, janela de aviso: nao se sabe.

Escrever esse reconhecimento de cabeca criaria o pior defeito possivel deste
programa: a tela demora a carregar, o programa nao acha o resultado, conclui
"nao esta neste sistema", e o advogado procura o processo em outro lugar ou
conclui que nao ha o que fazer. Processo dado como inexistente e prazo
perdido.

Entao a sonda NAO chuta: quando nao acha, devolve `None` e GRAVA A TELA. A
primeira varredura resolve os processos que forem achados, que e o objetivo,
e deixa no disco a prova que falta para escrever o reconhecimento do "nao
achado" contra telas reais. Decidido com o operador em 25/10/2026.

`ASSINATURAS_DE_AUSENCIA` nasce VAZIA, de proposito. Ela so e preenchida
depois que alguem olhar as telas gravadas. Enquanto estiver vazia, nenhum
sistema devolve `False`, e o relatorio diz, com todas as letras, que a
ausencia nao foi confirmada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

# Assinaturas confirmadas de "este sistema nao tem este processo", por
# sistema. Cada entrada so entra aqui depois de alguem ver a tela gravada por
# uma corrida real. Texto inventado nao entra.
ASSINATURAS_DE_AUSENCIA: dict[str, tuple] = {
    "dcp": (),
    "pje": (),
    "eproc": (),
    "esaj": (),
}

# Nome do arquivo de tela, por sistema. E por ele que se acha a colheita
# depois da varredura.
def nome_da_tela(sistema: str, numero: Any) -> str:
    return f"sonda-{sistema}-sem-resultado"


@dataclass(frozen=True)
class Resposta:
    """O que a sonda viu. `valor` e True, False ou None, nesta ordem de
    certeza; `detalhe` e o que vai para o relatorio, sem conteudo do
    processo."""

    valor: Optional[bool]
    detalhe: str
    tela_gravada: bool = False


def _nao_confirmado(sistema: str, pagina: Any, porque: str) -> Resposta:
    """Nao achou. Grava a tela e diz que NAO confirmou ausencia."""
    gravou = False
    try:
        from .telas import gravar_a_tela

        gravar_a_tela(pagina, nome_da_tela(sistema, None))
        gravou = True
    except Exception:
        # Falhar ao gravar a tela nao pode derrubar a varredura ja paga: o
        # resultado `None` continua valendo e a colheita perde um exemplar.
        gravou = False
    return Resposta(
        valor=None,
        detalhe=(f"{porque} A ausencia NAO foi confirmada: pode ser que o "
                 "processo nao esteja neste sistema, ou que a tela nao tenha "
                 "montado a tempo."
                 + (" A tela foi gravada para conferencia." if gravou else
                    " A tela NAO pode ser gravada.")),
        tela_gravada=gravou,
    )


def procurar_no_dcp(pagina: Any, guarda: Any, numero: Any, url: str,
                    segundos: int) -> Resposta:
    """Portal de Servicos: busca pelo menu e procura a linha cujo numero bate.

    A conferencia e digito por digito, feita por `processos_na_lista`: a busca
    por numero exato ja devolveu cinco linhas em campo, e abrir a linha errada
    e abrir o processo de outra pessoa.
    """
    from .dcp import (ESPERA_DA_LISTA, buscar, esperar_a_lista_de_resultado,
                      quadro_da_consulta, resumo_da_lista)

    # `buscar` abre a consulta, preenche e pesquisa. Ela tambem tenta abrir a
    # linha; aqui isso nao incomoda, porque abrir a tela do processo e sinal
    # positivo igualmente valido e nao baixa nada.
    quadro = buscar(pagina, guarda, numero, url, segundos)
    achados = esperar_a_lista_de_resultado(
        quadro or quadro_da_consulta(pagina), numero, ESPERA_DA_LISTA)
    if achados:
        return Resposta(True, f"{len(achados)} linha(s) da lista trazem este "
                              "numero, conferido digito por digito.")
    return _nao_confirmado(
        "dcp", pagina,
        f"Nenhuma linha da lista traz este numero. {resumo_da_lista(quadro)}")


def procurar_no_pje(pagina: Any, guarda: Any, numero: Any, url: str,
                    segundos: int) -> Resposta:
    """PJe: busca autenticada e procura o LINK do processo na lista.

    Nao clica. Clicar levantaria o aviso de responsabilidade da resolucao
    nº. 121 do Conselho Nacional de Justica, e aceita-lo e ato do advogado,
    nao de uma sondagem.
    """
    from .pje import (ConsultaPJeIndisponivel, achar_link_do_processo,
                      buscar_autenticado, linhas_do_resultado)

    try:
        buscar_autenticado(pagina, guarda, numero, url, segundos)
    except ConsultaPJeIndisponivel as exc:
        return _nao_confirmado("pje", pagina, f"A busca parou: {exc}")
    if achar_link_do_processo(pagina, numero) is not None:
        return Resposta(True, "A lista traz o link deste processo.")
    return _nao_confirmado(
        "pje", pagina,
        f"A lista voltou com {linhas_do_resultado(pagina)} linha(s) e nenhuma "
        "traz este processo.")


def procurar_no_eproc(pagina: Any, guarda: Any, numero: Any, url: str,
                      segundos: int) -> Resposta:
    """eproc: busca rapida e espera a tela do processo montar.

    `esperar_tela_do_processo` devolve 'eventos', 'capa' ou 'nada'. 'capa'
    tambem e achado: a tela do processo apareceu, so os eventos ainda nao
    tinham carregado, e o que se pergunta aqui e se o processo esta ali.
    """
    from .extracao import esperar_tela_do_processo
    from .portal import buscar_no_eproc

    enviada, porque = buscar_no_eproc(pagina, guarda, numero, segundos)
    if not enviada:
        return _nao_confirmado("eproc", pagina, porque)
    chegou = esperar_tela_do_processo(pagina, segundos)
    if chegou in ("eventos", "capa"):
        return Resposta(True, f"A tela do processo apareceu ({chegou}).")
    return _nao_confirmado(
        "eproc", pagina, "A tela do processo nao apareceu no tempo dado.")


def procurar_no_esaj(pagina: Any, guarda: Any, numero: Any, url: str,
                     segundos: int) -> Resposta:
    """e-SAJ: busca na tela do grau que o proprio numero indica."""
    from .esaj import ConsultaESAJIndisponivel, buscar
    from .esaj import extrair_movimentacoes

    try:
        buscar(pagina, guarda, numero, segundos)
    except ConsultaESAJIndisponivel as exc:
        return _nao_confirmado("esaj", pagina, f"A busca parou: {exc}")
    quantas = len(extrair_movimentacoes(pagina))
    if quantas:
        return Resposta(True, f"A tela trouxe {quantas} movimentacao(oes).")
    return _nao_confirmado(
        "esaj", pagina, "A tela nao trouxe movimentacao nenhuma.")


PROCURADORES: dict[str, Callable] = {
    "dcp": procurar_no_dcp,
    "pje": procurar_no_pje,
    "eproc": procurar_no_eproc,
    "esaj": procurar_no_esaj,
}


def procurar(sistema: str, pagina: Any, guarda: Any, numero: Any, url: str,
             segundos: int) -> Resposta:
    """Despacha para a sonda do sistema. Sistema sem sonda nao vira `False`."""
    procurador = PROCURADORES.get(sistema)
    if procurador is None:
        return Resposta(
            None, f"Nao ha sonda escrita para o sistema {sistema!r}. A "
                  "ausencia nao foi confirmada porque ninguem olhou.")
    try:
        return procurador(pagina, guarda, numero, url, segundos)
    except Exception as exc:
        # Sonda quebrada em um processo nao pode derrubar a varredura inteira:
        # a autenticacao ja foi paga e os demais numeros ainda serao buscados.
        return Resposta(
            None, f"A sonda falhou ({type(exc).__name__}). A ausencia nao foi "
                  "confirmada.")
