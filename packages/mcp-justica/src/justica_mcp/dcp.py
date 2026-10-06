"""Visualizador de Processos Eletronicos do Tribunal de Justica do Rio de Janeiro.

Fim do caminho do DCP, em `www3.tjrj.jus.br/visproc`. Lido em campo nos dias
05 e 06/10/2026, por acompanhamento conduzido pelo advogado e pelas fotos que
ele enviou das telas de download.

A barra de ferramentas nao da identificador a nenhum botao, e o texto visivel
de cada um e o nome do icone (`download_for_offline`). Quem diz o que o botao
faz e o rotulo acessivel, que no navegador e a dica ao passar o mouse. Por
isso tudo aqui mira em rotulo e em texto exato, nunca em identificador.
"""

from __future__ import annotations

from typing import Any, Optional

# Rotulo acessivel do botao da barra, lido na dica da tela em 06/10/2026.
BOTAO_DE_DOWNLOAD = "Baixar o processo atual em PDF"

# O que a caixa pergunta, para reconhece-la antes de clicar em qualquer coisa.
TITULO_DO_AVISO = "Download do Processo"

# As duas escolhas da caixa, com o texto exato dos botoes.
#
# A diferenca entre elas decide se o arquivo e o processo ou um pedaco dele, e
# nao ha nada no arquivo que denuncie a troca depois. "Carregados" traz o
# processo integral; "Selecionados" traz SO o que foi marcado na caixa de
# selecao, e com nada marcado nao traz nada.
ESCOLHA_INTEGRAL = "Salvar Documentos Carregados"
ESCOLHA_MARCADOS = "Salvar Documentos Selecionados"
ESCOLHA_CANCELAR = "Cancelar"

TETO_DO_DOWNLOAD = 180


class DownloadIndisponivel(RuntimeError):
    """O caminho do download parou, e nenhum arquivo foi gravado."""


def achar_botao_de_download(pagina: Any) -> Optional[Any]:
    """O botao da barra que abre a caixa de download."""
    from .portal import elemento_por_rotulo

    return elemento_por_rotulo(pagina, BOTAO_DE_DOWNLOAD)


def achar_escolha(pagina: Any, texto: str) -> Optional[Any]:
    """Um dos botoes da caixa de download, pelo texto exato."""
    from .portal import PREFIXO_DE_TEXTO, elemento_visivel

    return elemento_visivel(pagina, f"{PREFIXO_DE_TEXTO}{texto}")


def caixa_de_download_aberta(pagina: Any) -> bool:
    """Se a caixa que pergunta o que salvar esta na tela.

    Conferida pelas DUAS escolhas, e nao pelo titulo: titulo e texto solto na
    pagina e pode aparecer em outro lugar; os dois botoes juntos so existem
    nessa caixa.
    """
    return (achar_escolha(pagina, ESCOLHA_INTEGRAL) is not None
            and achar_escolha(pagina, ESCOLHA_MARCADOS) is not None)


def baixar_integra(pagina: Any, guarda: Any, destino, chave: str,
                   segundos: int = TETO_DO_DOWNLOAD) -> str:
    """Clica em baixar, escolhe o processo INTEGRAL e grava o arquivo.

    Devolve o caminho do arquivo gravado.

    Duas recusas deliberadas, e as duas existem pelo mesmo motivo: um PDF
    parcial guardado como se fosse o processo e pior do que nenhum arquivo,
    porque ninguem volta a conferir o que ja esta na pasta.

    A primeira: se o botao "Salvar Documentos Carregados" nao estiver na caixa,
    este caminho PARA. Nao cai para "Salvar Documentos Selecionados", que traz
    so o que foi marcado e, com nada marcado, nao traz nada.

    A segunda: o arquivo gravado NAO e declarado completo aqui. O advogado
    informou em 06/10/2026 que processo grande as vezes nao baixa de uma vez.
    Quem confere a completude e o acervo, contra o indice, e esta funcao
    devolve so o que de fato gravou.
    """
    from pathlib import Path

    from .core.guarda_navegacao import Acao, Permissao
    from .portal import permissao_efemera

    botao = achar_botao_de_download(pagina)
    if botao is None:
        raise DownloadIndisponivel(
            f"O botao {BOTAO_DE_DOWNLOAD!r} nao esta na barra desta tela "
            f"({pagina.url[:80]}). Nada foi clicado.")

    alvo_do_botao = f'[aria-label="{BOTAO_DE_DOWNLOAD}"]'
    alvo_da_escolha = f"texto={ESCOLHA_INTEGRAL}"
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="download do processo no Visualizador de Processos",
        conferido_em="execucao atual",
        seletores_clicaveis=(alvo_do_botao, alvo_da_escolha),
    ))

    guarda.pode_executar(Acao.CLICAR, alvo_do_botao, url=pagina.url)
    botao.click()
    try:
        pagina.wait_for_timeout(1500)
    except Exception:
        pass

    escolha = achar_escolha(pagina, ESCOLHA_INTEGRAL)
    if escolha is None:
        marcados = achar_escolha(pagina, ESCOLHA_MARCADOS)
        recado = (
            f"A caixa {TITULO_DO_AVISO!r} nao mostrou {ESCOLHA_INTEGRAL!r}. "
            "Nada foi baixado.")
        if marcados is not None:
            recado += (
                f" Ha {ESCOLHA_MARCADOS!r} na tela, e este caminho NAO usa esse "
                "botao: ele traz so o que foi marcado na caixa de selecao, e com "
                "nada marcado nao traz nada. Um arquivo parcial guardado como "
                "integra e pior que arquivo nenhum.")
        raise DownloadIndisponivel(recado)

    guarda.pode_executar(Acao.CLICAR, alvo_da_escolha, url=pagina.url)
    try:
        with pagina.expect_download(timeout=segundos * 1000) as info:
            escolha.click()
    except Exception as exc:
        raise DownloadIndisponivel(
            f"A escolha {ESCOLHA_INTEGRAL!r} foi clicada e nenhum arquivo chegou "
            f"em {segundos}s ({type(exc).__name__}). Processo grande pode nao "
            "baixar de uma vez: confira na tela se o portal recusou e, se for o "
            "caso, use a caixa de selecao para baixar em partes."
        ) from None

    baixado = info.value
    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    sugerido = baixado.suggested_filename or f"{chave}-integra.pdf"
    arquivo = pasta / f"integra-{sugerido}"
    baixado.save_as(str(arquivo))
    return str(arquivo)


# ---------------------------------------------------------------------------
# Consulta processual do Portal de Servicos
#
# Telas fotografadas em 06/10/2026, versao 5.25.2 do portal. O formulario
# inteiro mora num QUADRO EMBUTIDO dentro da pagina do portal, e e por isso que
# o relato da pagina de fora dizia "0 campos": o que importa esta no quadro.
# ---------------------------------------------------------------------------

SUFIXO_DA_CONSULTA = "/portalservicos/#/consproc/consultaportal"

# O quadro onde o formulario vive, reconhecido pelo caminho.
MARCA_DO_QUADRO = "/consultaprocessual/"

# Tipo de numeracao. "Unica" ja vem marcada, e ainda assim e conferida: achar
# a tela com "Antiga" marcada e digitar o numero unico devolve "nada
# encontrado", que o advogado leria como processo inexistente.
OPCAO_NUMERACAO_UNICA = "#numeracaoUnica"
OPCAO_NUMERACAO_ANTIGA = "#numeracaoAntiga"

# Os DOIS campos do numero, com `.8.19.` escrito fixo na tela entre eles.
# Nao sao seis campos como no PJe: aqui o primeiro leva sequencial, digito e
# ano juntos, e o segundo leva so a origem.
CAMPO_INICIO = "input[name=numeroProcesso]"
CAMPO_ORIGEM = "#inputSufixoUnica3"

BOTAO_PESQUISAR = "Pesquisar"
BOTAO_VISUALIZADOR = "Processo Eletrônico - Visualizador"

# O `.8.19.` fixo entre os campos e o que amarra este formulario ao Tribunal
# de Justica do Estado do Rio de Janeiro.
SEGMENTO_DO_RIO = 8
TRIBUNAL_DO_RIO = "19"


class ConsultaIndisponivel(RuntimeError):
    """A consulta parou antes de pesquisar, e nada foi enviado."""


def endereco_da_consulta(url_de_login: str) -> str:
    """Endereco da consulta processual, derivado do endereco de login."""
    partes = (url_de_login or "").split("://", 1)
    if len(partes) != 2 or not partes[1]:
        raise ConsultaIndisponivel(
            "Sem endereco de login configurado, nao da para achar a consulta.")
    esquema, resto = partes
    servidor = resto.split("/", 1)[0]
    if not servidor:
        raise ConsultaIndisponivel(
            "O endereco de login nao tem servidor; nao da para achar a consulta.")
    return f"{esquema}://{servidor}{SUFIXO_DA_CONSULTA}"


def conferir_tribunal(numero: Any) -> None:
    """Recusa numero que nao seja do Tribunal de Justica do Rio de Janeiro.

    O formulario traz `.8.19.` escrito fixo entre os dois campos: o portal nao
    pergunta segmento nem tribunal, ele os impoe. Mandar aqui um numero de
    outro tribunal montaria, silenciosamente, o numero de UM PROCESSO QUE NAO
    E O PEDIDO, e a tela que voltasse seria de outro feito ou de nenhum.
    """
    if int(numero.segmento) != SEGMENTO_DO_RIO or numero.tribunal != TRIBUNAL_DO_RIO:
        raise ConsultaIndisponivel(
            f"O numero {numero.formatado} e do segmento {numero.segmento} e do "
            f"tribunal {numero.tribunal}. Esta tela tem '.{SEGMENTO_DO_RIO}."
            f"{TRIBUNAL_DO_RIO}.' fixo entre os campos e so serve ao Tribunal de "
            "Justica do Estado do Rio de Janeiro. Nada foi digitado.")


def partes_do_numero(numero: Any) -> tuple[str, str]:
    """O numero como esta tela o divide: inicio e origem."""
    inicio = f"{numero.sequencial}-{numero.digito_verificador}.{numero.ano}"
    return inicio, numero.origem


def quadro_da_consulta(pagina: Any) -> Any:
    """O quadro embutido onde o formulario vive, ou a propria pagina.

    Devolver a pagina quando nao ha quadro nao e desistir: a conferencia
    seguinte procura os campos, e e ela quem para com uma mensagem que diz o
    que achou.
    """
    try:
        for quadro in list(pagina.frames or [])[1:]:
            if MARCA_DO_QUADRO in (quadro.url or ""):
                return quadro
    except Exception:
        pass
    return pagina


def conferir_forma_do_formulario(quadro: Any) -> tuple:
    """Acha os dois campos e o botao, e recusa a tela que nao bate.

    Antes de digitar, nunca depois: campo que falta devolve busca vazia, e
    busca vazia e indistinguivel de processo inexistente para quem le o
    resultado.
    """
    from .portal import achar_opcional, elemento_visivel

    inicio = elemento_visivel(quadro, CAMPO_INICIO)
    origem = elemento_visivel(quadro, CAMPO_ORIGEM)
    faltando = [nome for nome, alvo in
                ((CAMPO_INICIO, inicio), (CAMPO_ORIGEM, origem)) if alvo is None]
    if faltando:
        raise ConsultaIndisponivel(
            "A tela da consulta nao tem " + " nem ".join(faltando)
            + ". Nada foi digitado. Ou a autenticacao parou antes dela, ou a "
            "tela mudou desde 06/10/2026.")

    pesquisar = elemento_visivel(quadro, f"texto={BOTAO_PESQUISAR}")
    if pesquisar is None:
        raise ConsultaIndisponivel(
            f"O botao {BOTAO_PESQUISAR!r} nao esta na tela. Nada foi digitado.")

    unica = achar_opcional(quadro, OPCAO_NUMERACAO_UNICA)
    return inicio, origem, pesquisar, unica


def buscar(pagina: Any, guarda: Any, numero: Any, url_de_login: str,
           segundos: int = 45) -> Any:
    """Abre a consulta, digita o numero e pesquisa. Devolve o quadro usado.

    Somente leitura: preenche e pesquisa. Nao abre o visualizador e nao baixa
    nada, porque abrir os autos e ato separado.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import _assentar, permissao_efemera, preencher_conferindo

    conferir_tribunal(numero)
    destino = endereco_da_consulta(url_de_login)
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(destino).padrao_url,
        descricao="consulta processual do Portal de Servicos",
        conferido_em="execucao atual",
    ))
    guarda.pode_executar(Acao.NAVEGAR, destino, url=destino)
    pagina.goto(destino, timeout=segundos * 1000, wait_until="domcontentloaded")
    _assentar(pagina, segundos)

    quadro = quadro_da_consulta(pagina)
    inicio, origem, pesquisar, unica = conferir_forma_do_formulario(quadro)

    # A autorizacao so e escrita DEPOIS de a forma bater, e nomeia o que a
    # propria tela mostrou. Liberar antes seria liberar o que ainda nao se sabe
    # o que e.
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="consulta processual, somente a busca",
        conferido_em="execucao atual",
        seletores_clicaveis=(OPCAO_NUMERACAO_UNICA, f"texto={BOTAO_PESQUISAR}"),
        seletores_preenchiveis=(CAMPO_INICIO, CAMPO_ORIGEM),
    ))

    # "Unica" ja vem marcada, e ainda assim e garantida: achar a tela com
    # "Antiga" marcada e digitar o numero unico devolve "nada encontrado", que
    # o advogado leria como processo inexistente.
    if unica is not None:
        try:
            ja_marcada = unica.evaluate("e => !!e.checked")
        except Exception:
            ja_marcada = False
        if not ja_marcada:
            guarda.pode_executar(Acao.CLICAR, OPCAO_NUMERACAO_UNICA, url=pagina.url)
            unica.click()

    texto_inicio, texto_origem = partes_do_numero(numero)
    for alvo, seletor, valor, rotulo in (
        (inicio, CAMPO_INICIO, texto_inicio, "inicio do numero"),
        (origem, CAMPO_ORIGEM, texto_origem, "origem do numero"),
    ):
        guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
        preencher_conferindo(alvo, valor, rotulo)

    # Remonta o numero a partir da TELA, com o `.8.19.` que o portal impoe, e
    # confere contra o pedido. Campo com mascara que recusa o formato fica
    # vazio sem reclamar, e a busca volta "nada encontrado" por defeito nosso.
    digitado = (_so_digitos(inicio) + str(SEGMENTO_DO_RIO) + TRIBUNAL_DO_RIO
                + _so_digitos(origem))
    if digitado != numero.apenas_digitos:
        raise ConsultaIndisponivel(
            f"O numero montado na tela ficou com {len(digitado)} digito(s) e nao "
            f"confere com {numero.formatado}. Nada foi pesquisado.")

    guarda.pode_executar(Acao.CLICAR, f"texto={BOTAO_PESQUISAR}", url=pagina.url)
    pesquisar.click()
    _assentar(pagina, segundos)
    return quadro


def _so_digitos(elemento: Any) -> str:
    try:
        return elemento.evaluate("e => (e.value || '').replace(/\\D/g, '')")
    except Exception:
        return ""


def abrir_visualizador(pagina: Any, guarda: Any, segundos: int = 45) -> Any:
    """Clica em "Processo Eletronico - Visualizador" e devolve a JANELA NOVA.

    O visualizador abre em janela propria, com um endereco cifrado que nao se
    monta a partir do numero do processo: ele e gerado por este clique. Nao ha
    como pular esta etapa.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import elemento_visivel, pagina_de, permissao_efemera

    quadro = quadro_da_consulta(pagina)
    botao = elemento_visivel(quadro, f"texto={BOTAO_VISUALIZADOR}")
    if botao is None:
        raise ConsultaIndisponivel(
            f"O botao {BOTAO_VISUALIZADOR!r} nao esta na tela do processo. "
            "Nada foi aberto.")

    alvo = f"texto={BOTAO_VISUALIZADOR}"
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="abrir o Visualizador de Processos",
        conferido_em="execucao atual",
        seletores_clicaveis=(alvo,),
    ))
    guarda.pode_executar(Acao.CLICAR, alvo, url=pagina.url)

    hospedeira = pagina_de(pagina)
    try:
        with hospedeira.context.expect_page(timeout=segundos * 1000) as nova:
            botao.click()
        janela = nova.value
    except Exception as exc:
        raise ConsultaIndisponivel(
            f"O visualizador nao abriu em {segundos}s ({type(exc).__name__}). "
            "Nada foi lido.") from None
    try:
        janela.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
    except Exception:
        pass
    return janela
