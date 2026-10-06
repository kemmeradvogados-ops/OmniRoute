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


def conferir_forma_do_formulario(quadro: Any, segundos: int = 20) -> tuple:
    """Acha os dois campos e o botao, e recusa a tela que nao bate.

    Antes de digitar, nunca depois: campo que falta devolve busca vazia, e
    busca vazia e indistinguivel de processo inexistente para quem le o
    resultado.
    """
    from .portal import achar_opcional, elemento_visivel, esperar_elemento

    # Espera o primeiro campo, e so entao procura o resto: numa aplicacao de
    # pagina unica a tela chega vazia e se monta depois.
    inicio = esperar_elemento(quadro, CAMPO_INICIO, segundos)
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
    inicio, origem, pesquisar, unica = conferir_forma_do_formulario(
        quadro, segundos)

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


# ---------------------------------------------------------------------------
# Entrada no Portal de Servicos, pela tela de selecao de sistemas
#
# Conferido em campo em 06/10/2026: navegar DIRETO para a consulta nao
# funciona. O endereco `#/consproc/consultaportal` devolveu a pagina publica do
# tribunal, em `www.tjrj.jus.br`. A sessao do IdServerJus existe, e o Portal de
# Servicos so e alcancado pela entrega que este formulario faz.
# ---------------------------------------------------------------------------

TELA_DE_SELECAO = "/selecao-sistemas"
LISTA_DE_SISTEMAS = "#sistema"
ABRIR_EM_ABA = "#optionAba"
ABRIR_EM_JANELA = "#optionPopup"
BOTAO_ENVIAR = "Enviar"

# Como se reconhece que a sessao ja esta DENTRO do Portal de Servicos.
MARCA_DO_PORTAL = "/portalservicos"

SIGLA_DO_PORTAL = "PORTALSERVICOS"
NOME_DO_PORTAL = "portal de servicos"


def escolher_opcao_do_portal(lista: Any) -> Optional[str]:
    """O valor da opcao que leva ao Portal de Servicos, ou None.

    Casa primeiro pelo valor, que e a sigla, e so depois pelo texto. Exige
    UMA correspondencia: duas seriam escolha no escuro, e escolher o sistema
    errado leva a sessao para outro lugar sem dizer nada.
    """
    from .portal import sem_acento

    try:
        opcoes = lista.evaluate(
            "e => Array.from(e.options || []).map(o => [o.value, o.text])")
    except Exception:
        return None
    por_sigla = [v for v, _ in (opcoes or []) if (v or "").strip() == SIGLA_DO_PORTAL]
    if len(por_sigla) == 1:
        return por_sigla[0]
    por_nome = [v for v, t in (opcoes or [])
                if NOME_DO_PORTAL in sem_acento(t or "")]
    return por_nome[0] if len(por_nome) == 1 else None


def achar_aba_do_portal(pagina: Any, segundos: int = 20) -> Optional[Any]:
    """A aba ou janela onde o Portal de Servicos abriu, se houver.

    A entrada no portal abre uma JANELA PROPRIA, e a aba de origem volta para a
    pagina publica do tribunal. Conferido em campo em 06/10/2026: o comando
    anunciava "a lista nao esta nela" com o endereco em `www.tjrj.jus.br`,
    enquanto o portal estava aberto e pedindo o tipo de usuario em outra
    janela, que o advogado estava vendo na tela.

    Procura em TODAS as abas do mesmo navegador, e espera, porque a janela leva
    um instante para aparecer e outro para assumir o endereco.
    """
    import time as _tempo

    from .portal import pagina_de

    try:
        contexto = pagina_de(pagina).context
    except Exception:
        return None
    limite = _tempo.monotonic() + max(1, segundos)
    while True:
        try:
            abas = [a for a in (contexto.pages or []) if not a.is_closed()]
        except Exception:
            abas = []
        for aba in abas:
            try:
                if MARCA_DO_PORTAL in (aba.url or ""):
                    return aba
            except Exception:
                continue
        if _tempo.monotonic() >= limite:
            return None
        try:
            pagina.wait_for_timeout(400)
        except Exception:
            _tempo.sleep(0.4)


def entrar_no_portal_de_servicos(pagina: Any, guarda: Any, segundos: int = 45) -> Any:
    """Da tela de selecao de sistemas ate o Portal de Servicos aberto.

    Devolve a JANELA onde o portal abriu. Pede a abertura em ABA, e nao em
    janela destacada: aba e o que o navegador entrega de forma previsivel, e
    janela destacada pode ser barrada sem aviso nenhum.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (PREFIXO_DE_TEXTO, achar_opcional, elemento_visivel,
                         esperar_elemento, esperar_tela_montar, pagina_de,
                         permissao_efemera)

    # O endereco de login carrega `sgSist=PORTALSERVICOS`, e o portal as vezes
    # entra sozinho naquele sistema, sem passar pela escolha. Conferido em
    # campo em 06/10/2026: uma corrida parou ja dentro de `/portalservicos/`
    # sem nada ter sido selecionado. Quando a sessao ja esta la, insistir na
    # tela de selecao e procurar uma tela que nao existe mais.
    if MARCA_DO_PORTAL in (pagina.url or ""):
        return pagina

    # O portal abre em JANELA PROPRIA, e a aba de origem volta para a pagina
    # publica do tribunal. Procurar so na aba de origem fazia o comando
    # anunciar "a lista nao esta nela" com o portal aberto do lado, pedindo o
    # tipo de usuario, visivel na tela do operador.
    ja_aberta = achar_aba_do_portal(pagina, min(segundos, 10))
    if ja_aberta is not None:
        return ja_aberta

    lista = esperar_elemento(pagina, LISTA_DE_SISTEMAS, segundos)
    if lista is None and MARCA_DO_PORTAL in (pagina.url or ""):
        # Entrou enquanto se esperava.
        return pagina
    if lista is None:
        # Ultima chance: a janela pode ter aparecido durante a espera.
        tardia = achar_aba_do_portal(pagina, min(segundos, 5))
        if tardia is not None:
            return tardia
        montou = esperar_tela_montar(pagina, min(segundos, 5))
        raise ConsultaIndisponivel(
            f"A tela de selecao de sistemas nao tem {LISTA_DE_SISTEMAS}. "
            f"Endereco atual: {pagina.url[:80]}. "
            + ("A tela montou e a lista nao esta nela."
               if montou else "A tela nao chegou a montar: nenhum campo e nenhum "
                              "botao apareceram no prazo.")
            + " Nada foi escolhido.")

    valor = escolher_opcao_do_portal(lista)
    if valor is None:
        raise ConsultaIndisponivel(
            f"Nao achei UMA opcao do {SIGLA_DO_PORTAL} na lista de sistemas. "
            "Escolher no escuro levaria a sessao para outro sistema sem dizer "
            "nada. Nada foi escolhido.")

    enviar = elemento_visivel(pagina, f"{PREFIXO_DE_TEXTO}{BOTAO_ENVIAR}")
    if enviar is None:
        raise ConsultaIndisponivel(
            f"O botao {BOTAO_ENVIAR!r} nao esta na tela de selecao. "
            "Nada foi escolhido.")

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="entrada no Portal de Servicos pela selecao de sistemas",
        conferido_em="execucao atual",
        seletores_clicaveis=(ABRIR_EM_ABA, f"{PREFIXO_DE_TEXTO}{BOTAO_ENVIAR}"),
        seletores_preenchiveis=(LISTA_DE_SISTEMAS,),
    ))

    guarda.pode_executar(Acao.PREENCHER, LISTA_DE_SISTEMAS, url=pagina.url)
    lista.select_option(valor)

    # Aba, nunca janela destacada: aba e o que o navegador entrega de forma
    # previsivel, e janela destacada pode ser barrada sem aviso nenhum.
    aba = achar_opcional(pagina, ABRIR_EM_ABA)
    if aba is not None:
        guarda.pode_executar(Acao.CLICAR, ABRIR_EM_ABA, url=pagina.url)
        aba.click()

    guarda.pode_executar(Acao.CLICAR, f"{PREFIXO_DE_TEXTO}{BOTAO_ENVIAR}",
                         url=pagina.url)
    hospedeira = pagina_de(pagina)
    try:
        with hospedeira.context.expect_page(timeout=segundos * 1000) as nova:
            enviar.click()
        janela = nova.value
    except Exception:
        # Sem janela nova pelo evento, procura entre as abas: o portal pode ter
        # aberto numa janela que o evento nao entregou a tempo.
        tardia = achar_aba_do_portal(pagina, min(segundos, 10))
        if tardia is not None:
            return tardia
        # Pode ter aberto na propria aba. Quem julga e a conferencia do
        # formulario da consulta, que diz o que achou.
        return pagina
    try:
        janela.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
    except Exception:
        pass
    return janela


# ---------------------------------------------------------------------------
# Tipo de usuario, em `#/usuarios/alterar-perfil`
#
# Tela fotografada em 06/10/2026, logo depois de o Portal de Servicos abrir.
# Duas opcoes, "Usuario Comum" e "Advogado", e o botao "Entrar" so habilita
# depois da escolha. O perfil decide o que a sessao enxerga, exatamente como a
# inscricao no eproc, e por isso quem o nomeia e o operador.
# ---------------------------------------------------------------------------

TELA_DE_PERFIL = "/usuarios/alterar-perfil"
TITULO_DO_PERFIL = "Alterar Perfil"
ROTULO_DA_LISTA_DE_PERFIL = "Selecione perfil do usuário"
SELETOR_DA_CAIXA_DE_PERFIL = f'[placeholder="{ROTULO_DA_LISTA_DE_PERFIL}"]'
BOTAO_ENTRAR_NO_PERFIL = "Entrar"


class PerfilNaoInformado(RuntimeError):
    """A tela pediu o tipo de usuario e ninguem disse qual."""


def na_tela_de_perfil(pagina: Any, segundos: int = 8) -> bool:
    """Se a tela que pede o tipo de usuario esta aberta.

    O endereco basta e e imediato. Sem ele, espera o titulo aparecer: a tela
    chega vazia e se monta depois, e olhar uma vez so responderia "nao" a uma
    tela que esta chegando.
    """
    from .portal import PREFIXO_DE_TEXTO, esperar_elemento

    try:
        if TELA_DE_PERFIL in (pagina.url or ""):
            return True
    except Exception:
        pass
    return esperar_elemento(
        pagina, f"{PREFIXO_DE_TEXTO}{TITULO_DO_PERFIL}", segundos) is not None


def _lista_de_perfil(pagina: Any) -> Optional[Any]:
    """O `select` do tipo de usuario, quando a tela o monta como `select`."""
    from .portal import elemento_visivel

    for seletor in ("select[name=perfil]", "select#perfil", "select"):
        achado = elemento_visivel(pagina, seletor)
        if achado is not None:
            return achado
    return None


def perfis_oferecidos(pagina: Any) -> list[str]:
    """Os tipos de usuario que a tela oferece, para o relato da recusa.

    Sao nomes de PERFIL, nao dado de processo: "Usuario Comum", "Advogado".
    """
    lista = _lista_de_perfil(pagina)
    if lista is None:
        return []
    try:
        textos = lista.evaluate(
            "e => Array.from(e.options || []).map(o => o.text)")
    except Exception:
        return []
    return [" ".join((t or "").split()) for t in (textos or []) if (t or "").strip()]


# Onde uma opcao de lista pode morar, da forma mais especifica para a mais
# frouxa. Lista montada por script nem sempre usa `option`: usa `li`, `div` com
# papel de opcao, ou `div` puro e sem nada que a identifique alem do texto.
LUGARES_DE_OPCAO = (
    "[role=option]",
    "li",
    "option",
    "button, input[type=submit], input[type=button], a",
    "span",
    "div",
)


def achar_opcao_na_lista(pagina: Any, texto: str) -> Optional[Any]:
    """A opcao da lista cujo texto e EXATAMENTE este, onde quer que ela esteja.

    `_por_texto_exato` procura so em elemento clicavel, porque foi escrito para
    botao. Lista montada por script costuma empilhar `li` ou `div`, que nao
    entram naquela busca, e a opcao fica invisivel para ela.

    A ordem dos lugares vai do mais especifico ao mais frouxo, e para no
    primeiro que achar: comecar por `div` casaria com qualquer caixa que
    contivesse so aquela opcao, e clicar na caixa nao e clicar na opcao.

    Comparacao exata e sem acento. Exata porque "Advogado" e "Advogado
    (suspenso)" sao escolhas diferentes, e aceitar prefixo escolheria a errada.
    """
    from .portal import _na_tela, janela_de, sem_acento

    alvo = sem_acento(texto).strip()
    janela = janela_de(pagina)
    for lugar in LUGARES_DE_OPCAO:
        try:
            achados = pagina.query_selector_all(lugar)
        except Exception:
            continue
        for elemento in achados:
            try:
                if sem_acento(elemento.inner_text() or "").strip() != alvo:
                    continue
                if elemento.is_visible() and _na_tela(
                        elemento, janela["width"], janela["height"]):
                    return elemento
            except Exception:
                continue
    return None


def escolher_perfil(pagina: Any, guarda: Any, perfil: Optional[str],
                    segundos: int = 45) -> None:
    """Escolhe o tipo de usuario que o OPERADOR nomeou e entra.

    Nao escolhe por conta propria, nem quando ha so duas opcoes. O perfil
    decide o que a sessao enxerga: entrar como "Usuario Comum" devolveria uma
    visao reduzida sem avisar, e consulta que volta vazia e indistinguivel de
    processo inexistente para quem le o resultado.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (PREFIXO_DE_TEXTO, elemento_por_rotulo, elemento_visivel,
                         permissao_efemera, sem_acento)

    if not (perfil or "").strip():
        oferecidos = perfis_oferecidos(pagina)
        recado = ("A tela pediu o TIPO DE USUARIO e nenhum foi informado. "
                  "Repita o comando com --perfil.")
        if oferecidos:
            recado += " A tela oferece: " + "; ".join(oferecidos) + "."
        recado += (" Escolher por conta propria daria visao reduzida sem avisar, "
                   "e consulta que volta vazia e indistinguivel de processo "
                   "inexistente.")
        raise PerfilNaoInformado(recado)

    procurado = sem_acento(perfil).strip()
    alvo_da_opcao = f"{PREFIXO_DE_TEXTO}{perfil.strip()}"
    alvo_do_entrar = f"{PREFIXO_DE_TEXTO}{BOTAO_ENTRAR_NO_PERFIL}"
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao=f"escolha do tipo de usuario {perfil.strip()!r}",
        conferido_em="execucao atual",
        seletores_clicaveis=(alvo_da_opcao, alvo_do_entrar,
                             SELETOR_DA_CAIXA_DE_PERFIL),
        seletores_preenchiveis=("select",),
    ))

    from .portal import esperar_tela_montar

    esperar_tela_montar(pagina, segundos=min(segundos, 8))
    lista = _lista_de_perfil(pagina)
    if lista is not None:
        casados = [t for t in perfis_oferecidos(pagina)
                   if sem_acento(t).strip() == procurado]
        if len(casados) != 1:
            raise PerfilNaoInformado(
                f"O perfil {perfil!r} nao casa com UMA opcao da tela. "
                f"Ela oferece: {'; '.join(perfis_oferecidos(pagina)) or '(nenhuma)'}. "
                "Nada foi escolhido.")
        guarda.pode_executar(Acao.PREENCHER, "select", url=pagina.url)
        lista.select_option(label=casados[0])
    else:
        # Lista montada por script, sem `select`. Abre pelo proprio rotulo que a
        # tela mostra e clica na opcao que o OPERADOR nomeou, por texto exato.
        # A caixa e `input[type=text]`, e nao botao: o unico rotulo dela e o
        # texto cinza que mostra. Procurar por texto de botao nao acha nada.
        caixa = elemento_por_rotulo(pagina, ROTULO_DA_LISTA_DE_PERFIL)
        if caixa is None:
            raise PerfilNaoInformado(
                f"A tela do tipo de usuario nao tem lista nem "
                f"{ROTULO_DA_LISTA_DE_PERFIL!r}. Nada foi escolhido.")
        guarda.pode_executar(Acao.CLICAR, SELETOR_DA_CAIXA_DE_PERFIL,
                             url=pagina.url)
        caixa.click()
        try:
            pagina.wait_for_timeout(500)
        except Exception:
            pass
        opcao = achar_opcao_na_lista(pagina, perfil.strip())
        if opcao is None:
            raise PerfilNaoInformado(
                f"A opcao {perfil!r} nao apareceu na lista de tipos de usuario. "
                "Nada foi escolhido.")
        guarda.pode_executar(Acao.CLICAR, alvo_da_opcao, url=pagina.url)
        opcao.click()

    entrar = elemento_visivel(pagina, alvo_do_entrar)
    if entrar is None:
        raise PerfilNaoInformado(
            f"O botao {BOTAO_ENTRAR_NO_PERFIL!r} nao esta na tela do tipo de "
            "usuario. O perfil foi escolhido e NAO foi enviado.")
    guarda.pode_executar(Acao.CLICAR, alvo_do_entrar, url=pagina.url)
    entrar.click()
    try:
        pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
    except Exception:
        pass
