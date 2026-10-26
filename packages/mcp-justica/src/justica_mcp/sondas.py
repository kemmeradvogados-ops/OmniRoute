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
#
# PJE, conferida em 26/10/2026 na tela
# `20261026T021247509-sonda-pje-sem-resultado.json`: a pagina de resultado
# (`listView.seam`) montou, os seis campos do numero estavam preenchidos, a
# tabela `#fPP:processosTable` existia com os dez cabecalhos de coluna
# ("Acoes, Processo, Caracteristicas, ...") e nao havia link algum cujos
# digitos batessem com o procurado. Essa conjuncao e o "nada encontrado"
# daquele portal: a busca por numero exato que acha devolve a linha com o
# proprio numero, que e como `achar_link_do_processo` o encontra.
#
# EPROC e DCP continuam vazios: ver `procurar_no_eproc` e `procurar_no_dcp`.
ASSINATURAS_DE_AUSENCIA: dict[str, tuple] = {
    "dcp": (),
    "pje": ("tabela de resultado montada e nenhum link com o numero",),
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
    """Nao achou. Grava a tela e diz, COM BASE NO ARQUIVO, se gravou.

    Em 26/10/2026 esta funcao anunciou "A tela foi gravada para conferencia"
    cinco vezes numa corrida que nao gravou nada: `gravar_a_tela` devolve
    `None` em silencio quando a gravacao esta desligada, e aqui se tratava
    "nao levantou excecao" como "gravou". A corrida custou tres autenticacoes
    e a colheita veio vazia, sem que a saida dissesse isso.

    Agora o que decide e o CAMINHO devolvido, e nao a ausencia de erro. Um
    programa que afirma o que nao conferiu e pior do que um que falha.
    """
    caminho = None
    try:
        from .telas import gravar_a_tela

        caminho = gravar_a_tela(pagina, nome_da_tela(sistema, None))
    except Exception:
        # Falhar ao gravar a tela nao pode derrubar a varredura ja paga: o
        # resultado `None` continua valendo e a colheita perde um exemplar.
        caminho = None
    return Resposta(
        valor=None,
        detalhe=(f"{porque} A ausencia NAO foi confirmada: pode ser que o "
                 "processo nao esteja neste sistema, ou que a tela nao tenha "
                 "montado a tempo."
                 + (f" Tela gravada em {caminho}." if caminho else
                    " A TELA NAO FOI GRAVADA, entao nao ha o que conferir "
                    "depois.")),
        tela_gravada=bool(caminho),
    )


def procurar_no_dcp(pagina: Any, guarda: Any, numero: Any, url: str,
                    segundos: int, perfil: Optional[str] = None) -> Resposta:
    """Portal de Servicos: busca pelo menu e procura a linha cujo numero bate.

    A conferencia e digito por digito, feita por `processos_na_lista`: a busca
    por numero exato ja devolveu cinco linhas em campo, e abrir a linha errada
    e abrir o processo de outra pessoa.
    """
    from .dcp import (ESPERA_DA_LISTA, buscar, esperar_a_lista_de_resultado,
                      quadro_da_consulta, resumo_da_lista)

    # Chega aqui com a sessao JA dentro do portal: ver `preparar_dcp`. Sem
    # aquele preparo esta busca estoura, e foi o que aconteceu em 26/10/2026.
    #
    # `linha=0` e deliberado: `buscar` pesquisa e, em seguida, ABRE a linha do
    # resultado. Sondar nao precisa abrir nada. Pedir a linha zero, que nao
    # existe, faz a abertura devolver sem clicar, e a lista, que e a unica
    # coisa que a sonda le, ja esta montada nesse ponto. Menos acao, menos
    # superficie de falha, e nenhum processo de terceiro aberto a toa.
    from .dcp import ConsultaIndisponivel

    try:
        quadro = buscar(pagina, guarda, numero, url, segundos, linha=0)
    except ConsultaIndisponivel as exc:
        # A SESSAO PODE TER FICADO DENTRO DE UM PROCESSO. Conferido em
        # 26/10/2026 na tela `20261026T033403540-sonda-dcp-sem-resultado.json`:
        # depois de uma busca que devolveu UMA linha, o portal abriu o processo
        # sozinho, e o quadro embutido passou a ser `.../detalhes-processo`. Da
        # busca seguinte em diante nao havia formulario, porque nao se estava
        # mais nele, e a reabertura pelo menu nao volta de la: para o menu, a
        # tela de detalhe ja e "a consulta processual".
        #
        # Entao refaz-se a ENTRADA inteira, que e caminho provado, e tenta-se
        # uma vez. Uma, nao em laco: busca que falha duas vezes seguidas e
        # outro problema, e insistir esconderia qual.
        preparo = preparar_dcp(pagina, guarda, perfil, segundos)
        if not preparo.pronto:
            return _nao_confirmado(
                "dcp", pagina,
                f"A busca parou ({exc}) e a volta ao portal tambem: "
                f"{preparo.detalhe}.")
        pagina = preparo.pagina
        quadro = buscar(pagina, guarda, numero, url, segundos, linha=0)

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

    # AUSENCIA CONFIRMADA, e este e o unico lugar do programa que a afirma.
    # A tela de 26/10/2026 mostrou o que a confirma: pagina de resultado
    # montada, com a tabela e os cabecalhos de coluna, e nenhum link cujos
    # digitos batam com o procurado. Sem a tabela nao se afirma nada: tabela
    # ausente e tela que nao terminou de montar, que e coisa diferente de
    # processo que nao esta la.
    from .pje import TABELA_RESULTADOS

    try:
        montou = pagina.query_selector(TABELA_RESULTADOS) is not None
    except Exception:
        montou = False
    if montou:
        return Resposta(
            False,
            f"A tabela de resultado montada com {linhas_do_resultado(pagina)} "
            "linha(s) e nenhuma traz este processo. Ausencia confirmada.")
    return _nao_confirmado(
        "pje", pagina,
        "A tabela de resultado nao montou, entao nao da para dizer se a busca "
        "chegou a responder.")


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

    # A BUSCA PODE NEM TER ACONTECIDO. A tela gravada em 26/10/2026
    # (`20261026T020958092-sonda-eproc-sem-resultado.json`) mostrou que a
    # busca rapida, quando nao cai direto no processo, leva ao formulario de
    # Consulta Processual COM O NUMERO JA PREENCHIDO e o botao Consultar
    # esperando. Concluir "nao esta no eproc" ali seria afirmar a ausencia de
    # um processo que ninguem chegou a procurar.
    if _terminar_a_consulta_do_eproc(pagina, guarda, segundos):
        chegou = esperar_tela_do_processo(pagina, segundos)
        if chegou in ("eventos", "capa"):
            return Resposta(
                True, f"A tela do processo apareceu ({chegou}) depois de "
                      "completar a consulta no formulario.")
        return _nao_confirmado(
            "eproc", pagina,
            "A consulta foi completada no formulario e a tela do processo "
            "ainda assim nao apareceu.")
    return _nao_confirmado(
        "eproc", pagina, "A tela do processo nao apareceu no tempo dado.")


CAMPO_DA_CONSULTA_DO_EPROC = "#numNrProcesso"
BOTAO_DA_CONSULTA_DO_EPROC = "#sbmConsultar"


def _terminar_a_consulta_do_eproc(pagina: Any, guarda: Any,
                                  segundos: int) -> bool:
    """Clica em Consultar quando a busca rapida parou no formulario.

    Devolve se chegou a clicar. Nao e um clique a esmo: a tela de 26/10/2026
    trazia o numero ja escrito em `#numNrProcesso` e o botao `#sbmConsultar`
    ao lado, que e a propria busca do portal, no mesmo escopo de permissao da
    busca rapida.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import elemento_visivel, permissao_efemera

    campo = elemento_visivel(pagina, CAMPO_DA_CONSULTA_DO_EPROC)
    botao = elemento_visivel(pagina, BOTAO_DA_CONSULTA_DO_EPROC)
    if campo is None or botao is None:
        return False
    try:
        escrito = campo.evaluate("e => (e.value || '').length")
    except Exception:
        escrito = 0
    if not escrito:
        # Formulario vazio nao e a tela que se viu: ali o numero vinha
        # preenchido. Clicar num formulario vazio consultaria o que?
        return False

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="consulta processual do eproc, somente o botao Consultar",
        conferido_em="execucao atual",
        seletores_clicaveis=(BOTAO_DA_CONSULTA_DO_EPROC,),
        seletores_preenchiveis=(),
    ))
    guarda.pode_executar(Acao.CLICAR, BOTAO_DA_CONSULTA_DO_EPROC, url=pagina.url)
    botao.click()
    try:
        pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
    except Exception:
        pass
    return True


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


@dataclass(frozen=True)
class Preparo:
    """O que a sessao precisa ANTES de a primeira busca acontecer."""

    pagina: Any
    pronto: bool
    detalhe: str


def preparar_dcp(pagina: Any, guarda: Any, perfil: Optional[str],
                 segundos: int) -> Preparo:
    """Portal de Servicos: entra pela tela de selecao e escolhe o perfil.

    Isto NAO e etapa decorativa, e o comentario que esta em `_consultar_dcp`
    desde 06/10/2026 ja avisava: navegar direto para a consulta devolve a
    pagina publica do tribunal. A sessao do IdServerJus existe, mas o Portal
    de Servicos so e alcancado pela entrega que aquele formulario faz.

    Em 26/10/2026 a sonda pulou os tres passos e as quatro buscas estouraram
    com `ConsultaIndisponivel`, gastando uma autenticacao inteira. A pagina
    muda no caminho, e por isso a nova e DEVOLVIDA: seguir usando a antiga
    seria buscar na janela errada.

    Corre UMA vez por sessao. Repetir por processo seria entrar no portal
    quatro vezes para fazer quatro buscas.
    """
    from .dcp import (ConsultaIndisponivel, PerfilNaoInformado,
                      entrar_no_portal_de_servicos, escolher_perfil,
                      na_tela_de_perfil, reencontrar_o_portal)
    from .portal import _assentar

    try:
        pagina = entrar_no_portal_de_servicos(pagina, guarda, segundos)
    except ConsultaIndisponivel as exc:
        return Preparo(pagina, False, f"nao deu para entrar no portal: {exc}")
    _assentar(pagina, segundos)
    pagina = reencontrar_o_portal(pagina, min(segundos, 15))

    if na_tela_de_perfil(pagina):
        try:
            escolher_perfil(pagina, guarda, perfil, segundos)
        except PerfilNaoInformado as exc:
            return Preparo(pagina, False, f"o portal pediu o perfil: {exc}")
        except Exception as exc:
            return Preparo(pagina, False,
                           f"a escolha do perfil falhou ({type(exc).__name__})")
        _assentar(pagina, segundos)
        pagina = reencontrar_o_portal(pagina, min(segundos, 15))
    return Preparo(pagina, True, "portal aberto")


PREPARADORES: dict[str, Callable] = {"dcp": preparar_dcp}


def preparar(sistema: str, pagina: Any, guarda: Any,
             perfil: Optional[str], segundos: int) -> Preparo:
    """Prepara a sessao do sistema, quando ele precisar. Sistema sem preparo
    devolve a propria pagina e segue: o eproc e o PJe buscam direto da tela
    em que o login termina, e isso esta provado em campo."""
    preparador = PREPARADORES.get(sistema)
    if preparador is None:
        return Preparo(pagina, True, "este sistema busca direto")
    try:
        return preparador(pagina, guarda, perfil, segundos)
    except Exception as exc:
        return Preparo(pagina, False,
                       f"o preparo falhou ({type(exc).__name__})")


PROCURADORES: dict[str, Callable] = {
    "dcp": procurar_no_dcp,
    "pje": procurar_no_pje,
    "eproc": procurar_no_eproc,
    "esaj": procurar_no_esaj,
}


def procurar(sistema: str, pagina: Any, guarda: Any, numero: Any, url: str,
             segundos: int, perfil: Optional[str] = None) -> Resposta:
    """Despacha para a sonda do sistema. Sistema sem sonda nao vira `False`."""
    import inspect

    procurador = PROCURADORES.get(sistema)
    if procurador is None:
        return Resposta(
            None, f"Nao ha sonda escrita para o sistema {sistema!r}. A "
                  "ausencia nao foi confirmada porque ninguem olhou.")
    try:
        # So quem precisa do perfil o recebe: o Portal de Servicos o usa para
        # refazer a entrada; os outros nao tem o que fazer com ele.
        if "perfil" in inspect.signature(procurador).parameters:
            return procurador(pagina, guarda, numero, url, segundos, perfil)
        return procurador(pagina, guarda, numero, url, segundos)
    except Exception as exc:
        # Sonda quebrada em um processo nao pode derrubar a varredura inteira:
        # a autenticacao ja foi paga e os demais numeros ainda serao buscados.
        #
        # A MENSAGEM entra no relato, e nao so o tipo. Em 26/10/2026 as quatro
        # sondas do Portal de Servicos falharam com `ConsultaIndisponivel` e a
        # saida imprimiu so o nome da classe: as mensagens deste projeto dizem
        # o que a tela tinha de errado, e jogar fora a mensagem custou uma
        # corrida inteira de diagnostico. A tela tambem e gravada aqui, pelo
        # mesmo motivo: o caminho da excecao e justamente o que menos se sabe.
        primeira = str(exc).strip().splitlines()[:1]
        recado = primeira[0][:300] if primeira else "sem mensagem"
        return _nao_confirmado(
            sistema, pagina,
            f"A sonda falhou ({type(exc).__name__}): {recado}")
