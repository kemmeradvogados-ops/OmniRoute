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
    from .portal import endereco_sem_dado, permissao_efemera

    botao = achar_botao_de_download(pagina)
    if botao is None:
        raise DownloadIndisponivel(
            f"O botao {BOTAO_DE_DOWNLOAD!r} nao esta na barra desta tela "
            f"({endereco_sem_dado(pagina.url, 80)}). Nada foi clicado.")

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


# ---------------------------------------------------------------------------
# A consulta se alcanca pelo MENU, nunca por endereco
#
# Conferido em campo em 06/10/2026: navegar para `#/consproc/consultaportal`
# com a sessao aberta devolveu a pagina publica do tribunal. Rota `#/` nao e
# endereco novo para o navegador, e sim estado interno da aplicacao; mandar o
# navegador ir ate la RECARREGA a pagina inteira, a aplicacao perde o que
# tinha em memoria e o portal manda o visitante para fora.
#
# O caminho que funciona e o do operador: clicar "Consultas" no menu lateral e
# escolher "Consultas Processuais" na caixa que abre.
# ---------------------------------------------------------------------------

MENU_DE_CONSULTAS = "#CONSULTAS"
ITEM_DA_CONSULTA = "Consultas Processuais"
MARCA_DA_CONSULTA = "consproc"


def ja_esta_na_consulta(pagina: Any) -> bool:
    try:
        return MARCA_DA_CONSULTA in (pagina.url or "")
    except Exception:
        return False


def abrir_consulta_pelo_menu(pagina: Any, guarda: Any, segundos: int = 45) -> None:
    """Do painel ate a consulta processual, pelo menu lateral."""
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (PREFIXO_DE_TEXTO, endereco_sem_dado, esperar_elemento,
                         permissao_efemera)

    if ja_esta_na_consulta(pagina):
        return

    alvo_do_item = f"{PREFIXO_DE_TEXTO}{ITEM_DA_CONSULTA}"
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="abrir a consulta processual pelo menu",
        conferido_em="execucao atual",
        seletores_clicaveis=(MENU_DE_CONSULTAS, alvo_do_item),
    ))

    menu = esperar_elemento(pagina, MENU_DE_CONSULTAS, min(segundos, 20))
    if menu is None:
        # Conferido no acompanhamento de 06/10/2026: este menu so existe no
        # painel, DEPOIS de o tipo de usuario ser escolhido. Na tela que pede o
        # perfil ele nao esta, e procurar mais nao o faria aparecer. Dizer isso
        # aqui poupa a rodada inteira que custaria descobri-lo de novo.
        raise ConsultaIndisponivel(
            f"O menu {MENU_DE_CONSULTAS} nao esta na tela "
            f"({endereco_sem_dado(pagina.url, 80)}). "
            "Ele so existe no painel, depois de o TIPO DE USUARIO ser escolhido: "
            f"se o endereco ainda for {TELA_DE_PERFIL}, a escolha do perfil e "
            "que nao chegou ao fim. Nada foi clicado.")
    guarda.pode_executar(Acao.CLICAR, MENU_DE_CONSULTAS, url=pagina.url)
    menu.click()

    item = esperar_elemento(pagina, alvo_do_item, min(segundos, 15))
    if item is None:
        raise ConsultaIndisponivel(
            f"O item {ITEM_DA_CONSULTA!r} nao apareceu depois de o menu ser "
            "clicado. Nada mais foi clicado.")
    guarda.pode_executar(Acao.CLICAR, alvo_do_item, url=pagina.url)
    item.click()

    # Prova positiva de que o clique levou aonde devia, em vez de confiar nele.
    import time as _tempo

    limite = _tempo.monotonic() + min(segundos, 20)
    while not ja_esta_na_consulta(pagina):
        if _tempo.monotonic() >= limite:
            raise ConsultaIndisponivel(
                f"O item {ITEM_DA_CONSULTA!r} foi clicado e a tela nao chegou a "
                f"consulta. Endereco atual: {endereco_sem_dado(pagina.url, 80)}. "
                "Nada foi digitado.")
        try:
            pagina.wait_for_timeout(400)
        except Exception:
            _tempo.sleep(0.4)


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
    # Pelo MENU, nunca por endereco: rota `#/` nao e endereco novo para o
    # navegador, e sim estado interno da aplicacao. Mandar o navegador ir ate
    # la recarrega a pagina, a aplicacao perde o que tinha em memoria e o
    # portal manda o visitante para a pagina publica. Conferido em campo.
    abrir_consulta_pelo_menu(pagina, guarda, segundos)
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


# A RAIZ do portal e a rota que ele assume depois de montar. A diferenca entre
# as duas decidiu a corrida de 06/10/2026: o `expect_page` entregou uma janela
# em `/portalservicos/`, sem rota nenhuma, e ela foi embora para o site publico
# do tribunal enquanto o portal de verdade assumia `#/usuarios/alterar-perfil`
# em OUTRA janela, que o advogado estava vendo. O endereco conferia no instante
# em que foi olhado, e nao conferia um segundo depois.
MARCA_DE_ROTA_DO_PORTAL = "/portalservicos/#/"


def tem_rota_do_portal(url: Any) -> bool:
    """Se o endereco e uma ROTA do portal, e nao a raiz que ainda vai mudar."""
    return MARCA_DE_ROTA_DO_PORTAL in (url or "")


def _aba_do_portal_agora(abas: Any, exigir_rota: bool) -> Optional[Any]:
    """A aba do portal entre as recebidas, de tras para frente.

    De tras para frente porque janela nova e acrescentada ao fim da lista, e a
    aba de ORIGEM pode exibir o endereco do portal por um instante durante a
    entrega, antes de voltar para a pagina publica. Pegando a primeira, o
    programa ficava com a aba que ia embora.
    """
    for aba in reversed(list(abas or [])):
        try:
            endereco = aba.url or ""
        except Exception:
            continue
        if tem_rota_do_portal(endereco) if exigir_rota else (
                MARCA_DO_PORTAL in endereco):
            return aba
    return None


def achar_aba_do_portal(pagina: Any, segundos: int = 20) -> Optional[Any]:
    """A aba ou janela onde o Portal de Servicos abriu, se houver.

    A entrada no portal abre uma JANELA PROPRIA, e a aba de origem volta para a
    pagina publica do tribunal. Conferido em campo em 06/10/2026: o comando
    anunciava "a lista nao esta nela" com o endereco em `www.tjrj.jus.br`,
    enquanto o portal estava aberto e pedindo o tipo de usuario em outra
    janela, que o advogado estava vendo na tela.

    Procura em TODAS as abas do mesmo navegador, e espera, porque a janela leva
    um instante para aparecer e outro para assumir o endereco.

    Prefere a aba que ja ASSUMIU UMA ROTA, e so aceita a raiz quando o prazo
    acaba sem nenhuma rota aparecer. A raiz e endereco de passagem: na corrida
    de 06/10/2026 o programa ficou com uma janela que estava nela e que, um
    segundo depois, era o site publico do tribunal. Esperar a rota custa o
    tempo de a tela montar, que o passo seguinte gastaria de qualquer jeito.
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
        achada = _aba_do_portal_agora(abas, exigir_rota=True)
        if achada is not None:
            return achada
        if _tempo.monotonic() >= limite:
            # Ultima chance, e so agora: a raiz pode ser o portal que demorou
            # mais que o prazo para rotear, e devolver nada seria pior.
            crua = _aba_do_portal_agora(abas, exigir_rota=False)
            if crua is not None:
                return crua
            return None
        try:
            pagina.wait_for_timeout(400)
        except Exception:
            _tempo.sleep(0.4)


def abas_do_navegador(pagina: Any, teto: int = 10) -> list[str]:
    """Endereco de cada aba viva, sem parametros, para a recusa dizer onde esta.

    Sem parametros, pela regra de sempre: e neles que viajam identificador de
    cliente e numero de processo.
    """
    from .portal import enderecos_das_abas, pagina_de

    try:
        contexto = pagina_de(pagina).context
        abas = [a for a in (contexto.pages or []) if not a.is_closed()]
    except Exception:
        return []
    return enderecos_das_abas(abas, teto)


def trazer_para_a_frente(aba: Any) -> Any:
    """Poe a aba na frente antes de o programa agir nela, e devolve a aba.

    O advogado observou em 06/10/2026, com a janela do portal aberta na tela:
    "e voce nao consegue clicar nessa aba". Em navegador com janela visivel, o
    Chromium nao desenha nem calcula posicao de aba que esta atras, e o clique
    do Playwright depende das duas coisas: ele espera o elemento ficar estavel
    e visivel, e numa aba de fundo isso pode nunca acontecer.

    Falhar aqui nao e motivo para parar: se o navegador recusar, o clique ainda
    pode dar certo, e perder a consulta por causa do foco seria desproporcional.
    """
    try:
        aba.bring_to_front()
    except Exception:
        pass
    return aba


def conferir_janela_do_portal(candidata: Any, pagina: Any, segundos: int = 20) -> Any:
    """Devolve a janela que E o Portal de Servicos, ou recusa dizendo onde esta.

    Ate 06/10/2026 o caminho terminava em `return pagina` quando a janela nova
    nao vinha: devolvia a aba de ORIGEM, que o acompanhamento conduzido pelo
    advogado mostrou voltar para `www.tjrj.jus.br`. O comando entao procurava o
    menu do portal na pagina publica do tribunal e parava anunciando que o menu
    nao existe, que e verdade e nao ajuda em nada.

    Devolver a aba errada e pior que parar: a consulta seguiria em cima de uma
    tela que nao e a do processo. Entao, quando o portal nao esta em aba
    nenhuma, isto recusa e diz quais abas existem.
    """
    # Primeiro quem JA assumiu uma rota. A raiz nao serve aqui: foi aceitando a
    # raiz que o programa ficou, em 06/10/2026, com uma janela de passagem que
    # um segundo depois era o site publico do tribunal.
    for alvo in (candidata, pagina):
        try:
            if alvo is not None and tem_rota_do_portal(alvo.url):
                return trazer_para_a_frente(alvo)
        except Exception:
            continue

    achada = achar_aba_do_portal(pagina, segundos)
    if achada is not None:
        return trazer_para_a_frente(achada)

    # Nenhuma rota apareceu no prazo. A raiz ainda e melhor que recusar, porque
    # o portal pode so estar demorando a montar, e o passo seguinte espera.
    for alvo in (candidata, pagina):
        try:
            if alvo is not None and MARCA_DO_PORTAL in (alvo.url or ""):
                return trazer_para_a_frente(alvo)
        except Exception:
            continue

    abertas = abas_do_navegador(pagina)
    raise ConsultaIndisponivel(
        f"O Portal de Servicos ({MARCA_DO_PORTAL}) nao esta em nenhuma aba "
        "aberta. Ele abre em janela propria, e a aba de origem volta para a "
        "pagina publica do tribunal: seguir pela aba de origem procuraria o "
        "processo numa tela que nao e a do portal. "
        + ("Abas abertas, sem parametros: " + "; ".join(abertas) + ". "
           if abertas else "Nenhuma aba pode ser lida. ")
        + "Nada foi consultado.")


def entrar_no_portal_de_servicos(pagina: Any, guarda: Any, segundos: int = 45) -> Any:
    """Da tela de selecao de sistemas ate o Portal de Servicos aberto.

    Devolve a JANELA onde o portal abriu. Pede a abertura em ABA, e nao em
    janela destacada: aba e o que o navegador entrega de forma previsivel, e
    janela destacada pode ser barrada sem aviso nenhum.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (PREFIXO_DE_TEXTO, achar_opcional, elemento_visivel,
                         endereco_sem_dado, esperar_elemento, esperar_tela_montar,
                         pagina_de, permissao_efemera)

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
            f"Endereco atual: {endereco_sem_dado(pagina.url, 80)}. "
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
        # aberto numa janela que o evento nao entregou a tempo, ou na propria
        # aba. A conferencia recusa se nao estiver em nenhuma delas.
        return conferir_janela_do_portal(None, pagina, min(segundos, 10))
    try:
        janela.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
    except Exception:
        pass
    # `expect_page` entrega QUALQUER janela nova, e nao necessariamente o
    # portal. Conferir o endereco custa nada e evita seguir numa janela de
    # aviso ou de propaganda como se fosse a do processo.
    return conferir_janela_do_portal(janela, pagina, min(segundos, 10))


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


# Identificadores reais da tela do tipo de usuario, lidos no acompanhamento
# conduzido pelo advogado em 06/10/2026. Ate aqui eu so alcancava esta lista
# por texto, o que e adivinhacao com outro nome: o texto prova que ACHEI algo
# com aquele nome, nunca que a lista chegou a abrir. Com o identificador da
# lista eu separo as duas perguntas, e a recusa passa a dizer qual das duas
# falhou em vez de deixar o operador tentar de novo as cegas.
CAIXA_DO_PERFIL = "app-dropdown#dropdownPerfil"
LISTA_DE_RESULTADOS = "ul#resultados"
ITEM_DA_LISTA = "li[id^=itemAutocomplete]"


# Onde uma opcao de lista pode morar, da forma mais especifica para a mais
# frouxa. Lista montada por script nem sempre usa `option`: usa `li`, `div` com
# papel de opcao, ou `div` puro e sem nada que a identifique alem do texto.
LUGARES_DE_OPCAO = (
    ITEM_DA_LISTA,
    "[role=option]",
    "li",
    "option",
    "button, input[type=submit], input[type=button], a",
    "span",
    "div",
)


def lista_de_opcoes_aberta(pagina: Any) -> bool:
    """Se a lista do tipo de usuario chegou a ABRIR, independente do que tem.

    Separa as duas recusas que ate aqui saiam com a mesma frase: a lista nao
    abriu, e a lista abriu sem a opcao pedida. A primeira e defeito meu, de
    clique ou de espera; a segunda e informacao sobre o portal, e o operador
    so pode agir sobre a segunda.
    """
    from .portal import elemento_visivel

    return elemento_visivel(pagina, LISTA_DE_RESULTADOS) is not None


def achar_opcao_na_lista(pagina: Any, texto: str,
                        exigir_posicao: bool = True) -> Optional[Any]:
    """A opcao da lista cujo texto e EXATAMENTE este, onde quer que ela esteja.

    `_por_texto_exato` procura so em elemento clicavel, porque foi escrito para
    botao. Lista montada por script costuma empilhar `li` ou `div`, que nao
    entram naquela busca, e a opcao fica invisivel para ela.

    A ordem dos lugares vai do mais especifico ao mais frouxo, e para no
    primeiro que achar: comecar por `div` casaria com qualquer caixa que
    contivesse so aquela opcao, e clicar na caixa nao e clicar na opcao.

    Comparacao exata e sem acento. Exata porque "Advogado" e "Advogado
    (suspenso)" sao escolhas diferentes, e aceitar prefixo escolheria a errada.

    `exigir_posicao` controla a conferencia de que o elemento esta DENTRO da
    janela. Ela existe por um motivo real, o campo espelho empurrado para
    `left:-9999px`, e nao e dispensada de leve: sem ela, lista aberta abaixo da
    dobra tambem conta, e a diferenca entre as duas coisas e justamente o que o
    relato da recusa precisa dizer. Quem a desliga, diz que desligou.
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
                if not elemento.is_visible():
                    continue
                if exigir_posicao and not _na_tela(
                        elemento, janela["width"], janela["height"]):
                    continue
                return elemento
            except Exception:
                continue
    return None


# Onde a lista do tipo de usuario pode estar, com o nome que o relato usa.
PECAS_DA_LISTA = (
    (CAIXA_DO_PERFIL, "a caixa do perfil"),
    (LISTA_DE_RESULTADOS, "a lista"),
    (ITEM_DA_LISTA, "os itens da lista"),
    ("[role=option]", "as opcoes por papel"),
)


def _estado_do_elemento(elemento: Any, janela: dict) -> str:
    """Como este elemento esta: visivel, onde, e dentro ou fora da janela."""
    from .portal import _na_tela

    try:
        visivel = bool(elemento.is_visible())
    except Exception:
        return "ilegivel"
    try:
        caixa = elemento.bounding_box()
    except Exception:
        caixa = None
    if caixa is None:
        return "visivel, sem caixa" if visivel else "oculto, sem caixa"
    onde = (f"x={int(caixa['x'])} y={int(caixa['y'])} "
            f"l={int(caixa['width'])} a={int(caixa['height'])}")
    dentro = _na_tela(elemento, janela["width"], janela["height"])
    return (f"{'visivel' if visivel else 'oculto'}, {onde}, "
            f"{'dentro' if dentro else 'FORA'} da janela")


# O que perguntar a propria caixa. `aria-expanded` e o decisivo: lido antes e
# depois do clique, ele separa em um passo "o clique nao abriu o componente" de
# "abriu e o meu seletor da lista e que esta errado". Sao os dois consertos que
# ainda disputavam a mesma frase de recusa.
PERGUNTAS_A_CAIXA = (
    "aria-expanded",
    "aria-controls",
    "aria-owns",
    "aria-haspopup",
    "role",
    # `readonly` virou a pergunta mais importante depois da corrida de
    # 07/10/2026. Caixa de escolha costuma ser `input` somente de leitura, que
    # abre no clique e nao aceita digitacao: nela, `type()` NAO levanta erro e
    # NAO escreve nada. O relato dizia "preencher" e nada acontecia, e a prova
    # positiva recusava porque o valor nunca chegou a existir.
    "readonly",
    "disabled",
    "class",
)


def valor_da_caixa_frente_ao_pedido(caixa: Any, esperado: Optional[str]) -> str:
    """Se o que esta na caixa e o perfil pedido, outra coisa, ou nada.

    Diz o SUFICIENTE sem imprimir o valor. A mesma caixa, noutra tela, teria
    numero de processo ou nome de parte, e um relato que imprime valor nao
    serve para este programa. Aqui a pergunta nao e "o que esta escrito": e
    "o que foi digitado chegou a entrar", e isso se responde comparando.
    """
    from .portal import sem_acento

    escrito = None
    for ler in (lambda e: e.evaluate("e => e.value"),
                lambda e: e.inner_text()):
        try:
            lido = ler(caixa)
        except Exception:
            continue
        if lido is not None:
            escrito = str(lido)
            break
    if escrito is None:
        return "valor ilegivel"
    if not escrito.strip():
        return "valor VAZIO (nada entrou na caixa)"
    if esperado and sem_acento(escrito).strip() == sem_acento(esperado).strip():
        return "valor IGUAL ao perfil pedido"
    return f"valor diferente do pedido, com {len(escrito.strip())} caractere(s)"


def estado_da_caixa(caixa: Any, esperado: Optional[str] = None) -> str:
    """Como a caixa do perfil esta agora, numa linha.

    O valor digitado nao e impresso: so se ele e o pedido, outro, ou nenhum.
    Em tela de escolha de processo a mesma funcao leria dado de cliente.
    """
    if caixa is None:
        return "a caixa nao foi encontrada"
    partes = []
    try:
        partes.append(f"tag={caixa.evaluate('e => e.tagName')}")
    except Exception:
        pass
    for nome in PERGUNTAS_A_CAIXA:
        try:
            lido = caixa.get_attribute(nome)
        except Exception:
            continue
        if lido is not None:
            texto = " ".join(str(lido).split())
            partes.append(f"{nome}={texto[:60]!r}")
    # Tambem pela propriedade, e nao so pelo atributo: componente que monta a
    # caixa por script costuma marcar `readOnly` sem escrever o atributo, e
    # perguntar so pelo atributo devolveria "nao e somente leitura" para uma
    # caixa que e.
    for nome, codigo in (("readOnly", "e => e.readOnly"),
                         ("disabled", "e => e.disabled")):
        try:
            if caixa.evaluate(codigo):
                partes.append(f"{nome}=True (propriedade)")
        except Exception:
            continue
    partes.append(valor_da_caixa_frente_ao_pedido(caixa, esperado))
    return "; ".join(partes) if partes else "sem atributo legivel"


def relato_da_escolha(pagina: Any, caixa: Any, perfil: str,
                      antes: str) -> str:
    """O bloco de diagnostico, para TODA recusa da escolha de perfil.

    Ate 07/10/2026 ele saia so numa das recusas. Naquela corrida o caminho de
    teclado deu certo o bastante para pular aquele ramo, e a recusa que de fato
    aconteceu, a da prova positiva, nao trazia diagnostico nenhum: a corrida
    custou uma tentativa de login e contou menos que a anterior.

    Relato de recusa que depende de QUAL recusa foi nao e relato: e sorte.
    """
    linhas = relatar_a_lista_de_perfil(pagina)
    bloco = ""
    if linhas:
        bloco += ("\n    O QUE EXISTE NA TELA DO TIPO DE USUARIO:\n    "
                  + "\n    ".join(linhas))
    bloco += (f"\n    A CAIXA ANTES DO CLIQUE: {antes}"
              f"\n    A CAIXA AGORA:           {estado_da_caixa(caixa, perfil)}"
              f"\n    O COMPONENTE: {envoltorio_da_caixa(pagina)}")
    return bloco


def envoltorio_da_caixa(pagina: Any, teto: int = 300) -> str:
    """A marcacao do componente que contem a caixa, para identifica-lo.

    Qual biblioteca o portal usa decide onde a lista nasce: ha componente que a
    monta num `div` solto no fim do documento, e nesse caso procura-la perto da
    caixa nunca a acharia. A marcacao responde isso de uma vez, e o relato
    inteiro ate aqui nao respondia.
    """
    from .portal import sem_dado_de_processo

    try:
        envoltorio = pagina.query_selector(CAIXA_DO_PERFIL)
    except Exception:
        envoltorio = None
    if envoltorio is None:
        return f"{CAIXA_DO_PERFIL} nao esta no documento"
    try:
        marcacao = envoltorio.evaluate("e => e.outerHTML") or ""
    except Exception:
        return f"{CAIXA_DO_PERFIL} esta no documento e a marcacao nao pode ser lida"
    return sem_dado_de_processo(" ".join(marcacao.split()))[:teto]


def relatar_a_lista_de_perfil(pagina: Any, teto: int = 12) -> list[str]:
    """O que existe na tela do tipo de usuario, esteja a vista ou nao.

    O advogado perguntou em 06/10/2026, depois de a escolha falhar duas vezes:
    "e possivel listar as opcoes que aparecem?". E, e era o que faltava. As
    buscas desta familia exigem elemento VISIVEL e DENTRO da janela, e quando
    nao acham nada as duas exigencias ficam indistinguiveis de "nao existe".
    Sao tres respostas diferentes, com tres consertos diferentes, e ate aqui
    saiam todas com a mesma frase.

    Aqui nada e exigido: conta o que esta no documento e diz de cada um como
    esta. O teto e o corte por tamanho ficam, porque a mesma forma de lista
    serve para escolher processo, e ali o texto seria dado de cliente.
    """
    from .portal import janela_de

    janela = janela_de(pagina)
    linhas = []
    for seletor, nome in PECAS_DA_LISTA:
        try:
            achados = pagina.query_selector_all(seletor) or []
        except Exception:
            linhas.append(f"{nome} ({seletor}): ilegivel")
            continue
        if not achados:
            linhas.append(f"{nome} ({seletor}): nao esta no documento")
            continue
        linhas.append(f"{nome} ({seletor}): {len(achados)} no documento")
        for elemento in achados[:teto]:
            estado = _estado_do_elemento(elemento, janela)
            try:
                texto = " ".join((elemento.inner_text() or "").split())
            except Exception:
                texto = ""
            if len(texto) > 60:
                texto = ""
            linhas.append(f"  {texto!r}: {estado}" if texto else f"  {estado}")
    return linhas


# Quanto esperar a lista de opcoes aparecer depois do clique na caixa.
ESPERA_DA_LISTA = 8


def esperar_opcao_na_lista(pagina: Any, texto: str,
                           segundos: int = ESPERA_DA_LISTA,
                           exigir_posicao: bool = True) -> Optional[Any]:
    """Espera a opcao aparecer depois de a caixa ser aberta.

    Olhar meio segundo depois do clique nao basta: a lista e montada por
    script, com animacao, e meio segundo pegava a tela ainda sem ela. Foi o
    que aconteceu em 06/10/2026, com a caixa ja clicada, conforme o relato da
    trava, e a opcao anunciada como ausente.
    """
    import time as _tempo

    limite = _tempo.monotonic() + max(1, segundos)
    while True:
        achada = achar_opcao_na_lista(pagina, texto, exigir_posicao)
        if achada is not None:
            return achada
        if _tempo.monotonic() >= limite:
            return None
        try:
            pagina.wait_for_timeout(300)
        except Exception:
            _tempo.sleep(0.3)


def opcoes_a_vista(pagina: Any, teto: int = 12) -> list[str]:
    """Textos curtos das opcoes visiveis, para o relato de quando nao se acha.

    Vale para a tela do TIPO DE USUARIO, onde opcao e nome de perfil. O teto e
    o corte por tamanho existem porque a mesma forma de lista serve para
    escolher processo, e ali o texto seria dado de cliente.
    """
    vistos, saida = set(), []
    for lugar in (ITEM_DA_LISTA, "[role=option]", "li", "option"):
        try:
            achados = pagina.query_selector_all(lugar)
        except Exception:
            continue
        for elemento in achados:
            if len(saida) >= teto:
                return saida
            try:
                if not elemento.is_visible():
                    continue
                texto = " ".join((elemento.inner_text() or "").split())
            except Exception:
                continue
            if texto and len(texto) <= 60 and texto not in vistos:
                vistos.add(texto)
                saida.append(texto)
    return saida


def perfil_assumido_pelo_controle(pagina: Any, perfil: str) -> bool:
    """Se o controle passou a MOSTRAR o perfil escolhido.

    Prova positiva, no lugar de confiar no clique. Nas telas fotografadas em
    06/10/2026 o botao "Entrar" nasce desabilitado, em verde claro, e so fica
    verde forte depois de o controle assumir o perfil. Clicar nele antes disso
    nao faz nada, e sem esta conferencia o comando seguiria como se tivesse
    entrado.

    Vale para os dois jeitos de a tela montar a escolha, porque a pergunta e a
    mesma nos dois: o que o controle mostra agora.
    """
    from .portal import elemento_por_rotulo, sem_acento

    alvo = sem_acento(perfil).strip()

    lista = _lista_de_perfil(pagina)
    if lista is not None:
        for leitura in ("e => (e.selectedOptions && e.selectedOptions[0]) "
                        "? e.selectedOptions[0].text : (e.value || '')",
                        "e => e.value || ''"):
            try:
                escrito = lista.evaluate(leitura) or ""
            except Exception:
                continue
            if sem_acento(str(escrito)).strip() == alvo:
                return True

    caixa = elemento_por_rotulo(pagina, ROTULO_DA_LISTA_DE_PERFIL)
    if caixa is not None:
        for ler in (lambda e: e.evaluate("e => e.value || ''"),
                    lambda e: e.inner_text()):
            try:
                escrito = ler(caixa) or ""
            except Exception:
                continue
            if sem_acento(str(escrito)).strip() == alvo:
                return True
    return False


def escolher_pelo_teclado(caixa: Any, pagina: Any) -> bool:
    """Seta para baixo e Enter, o caminho de teclado do combobox.

    Padrao comum de caixa de completar: a lista existe para o teclado antes de
    existir para o mouse, e ha componente que nem chega a desenha-la quando a
    navegacao e por tecla.

    Isto seria temerario em qualquer outro lugar deste programa, porque a seta
    escolhe por POSICAO e nao por nome, e aqui ha duas opcoes: "Usuario Comum"
    e "Advogado". Escolher a errada daria visao reduzida sem avisar, que e
    exatamente o que `escolher_perfil` existe para impedir.

    O que torna aceitavel e a conferencia que ja vem depois:
    `perfil_assumido_pelo_controle` exige que o controle MOSTRE o perfil que o
    operador nomeou, e recusa quando nao mostra. A seta nao decide nada: ela so
    propoe, e quem decide e a prova positiva. Sem aquela conferencia no lugar,
    este caminho nao poderia existir.
    """
    for tecla in ("ArrowDown", "Enter"):
        try:
            caixa.press(tecla)
        except Exception:
            return False
        try:
            pagina.wait_for_timeout(300)
        except Exception:
            pass
    return True


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
        # A caixa entra nos DOIS: ela e clicada para abrir a lista e, quando a
        # lista nao abre, recebe o nome digitado. Liberar so `select` deixava o
        # caminho de digitar barrado pela propria trava, e o comando terminava
        # em traceback no meio da escolha do perfil.
        seletores_preenchiveis=("select", SELETOR_DA_CAIXA_DE_PERFIL),
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
        # A caixa pode estar abaixo da dobra: o clique do Playwright rola ate
        # ela sozinho, mas a lista que ela abre fica onde a caixa estiver, e e
        # a posicao da LISTA que decide se as buscas a enxergam. Rolar antes
        # deixa as duas na janela, em vez de so a caixa.
        try:
            caixa.scroll_into_view_if_needed()
        except Exception:
            pass
        antes_do_clique = estado_da_caixa(caixa)
        caixa.click()
        opcao = esperar_opcao_na_lista(pagina, perfil.strip(),
                                       min(segundos, ESPERA_DA_LISTA))

        if opcao is None:
            # A caixa e `input[type=text]`: pode ser de digitar e filtrar, e
            # nesse caso o clique sozinho nao abre lista nenhuma. Digitar o
            # que o OPERADOR nomeou nao e escolher por conta propria: e o
            # mesmo valor, por outro caminho.
            guarda.pode_executar(Acao.PREENCHER, SELETOR_DA_CAIXA_DE_PERFIL,
                                 url=pagina.url)
            try:
                caixa.click()
                caixa.type(perfil.strip(), delay=40)
            except Exception as exc:
                raise PerfilNaoInformado(
                    f"A opcao {perfil!r} nao apareceu, e digitar na caixa falhou "
                    f"({type(exc).__name__}). Nada foi escolhido.") from None
            opcao = esperar_opcao_na_lista(pagina, perfil.strip(),
                                           min(segundos, ESPERA_DA_LISTA))

        if opcao is None:
            # Ultima tentativa antes de desistir: a MESMA busca, sem exigir que
            # o elemento esteja dentro da janela. Lista que abre abaixo da
            # dobra e indistinguivel de lista que nao abriu para quem exige
            # posicao, e as duas pedem consertos diferentes. Quando e isto, o
            # comando segue E DIZ que seguiu assim: achado que depende de uma
            # regra afrouxada nao pode passar por achado comum.
            opcao = achar_opcao_na_lista(pagina, perfil.strip(),
                                         exigir_posicao=False)
            if opcao is not None:
                print(f"    [FORA DA JANELA] A opcao {perfil.strip()!r} estava "
                      "na lista, porem fora da area visivel da janela.")
                print("    O comando seguiu. Avise-me: a regra de posicao e que "
                      "precisa ser corrigida, e nao a escolha do perfil.")

        pelo_teclado = False
        if opcao is None:
            # Ultimo caminho antes de desistir. A conferencia positiva logo
            # abaixo e que o torna aceitavel: a seta propoe, ela decide.
            guarda.pode_executar(Acao.PREENCHER, SELETOR_DA_CAIXA_DE_PERFIL,
                                 url=pagina.url)
            pelo_teclado = escolher_pelo_teclado(caixa, pagina)
            if pelo_teclado:
                print("    [TECLADO] A lista nao apareceu para o mouse. Tentei "
                      "seta para baixo e Enter.")
                print("    Se o perfil certo nao for assumido, o comando para "
                      "aqui mesmo: a seta escolhe por posicao, nao por nome.")

        if opcao is None and not pelo_teclado:
            a_vista = opcoes_a_vista(pagina)
            abriu = lista_de_opcoes_aberta(pagina)
            recado = (f"A opcao {perfil!r} nao apareceu na lista de tipos de "
                      "usuario, nem depois de a caixa ser clicada e o nome ser "
                      "digitado nela.")
            if a_vista:
                recado += " A lista mostra: " + "; ".join(a_vista) + "."
            elif abriu:
                recado += (f" A lista ({LISTA_DE_RESULTADOS}) ESTA aberta e "
                           "vazia: o portal nao ofereceu nenhum tipo de usuario.")
            else:
                recado += (f" A lista ({LISTA_DE_RESULTADOS}) nao chegou a abrir.")
            # O que existe no documento, visivel ou nao, dentro da janela ou
            # nao. Sem isto, "nao achei" cobre tres defeitos diferentes e nao
            # distingue nenhum, e cada rodada as cegas custa uma tentativa de
            # login ao advogado.
            recado += relato_da_escolha(pagina, caixa, perfil.strip(),
                                        antes_do_clique)
            raise PerfilNaoInformado(recado + "\n    Nada foi escolhido.")
        if opcao is not None:
            guarda.pode_executar(Acao.CLICAR, alvo_da_opcao, url=pagina.url)
            opcao.click()

    # Prova positiva antes de enviar. O botao "Entrar" nasce desabilitado e so
    # habilita depois de a caixa assumir o perfil: clicar nele antes nao faz
    # nada, e sem esta conferencia o comando seguiria como se tivesse entrado.
    try:
        pagina.wait_for_timeout(400)
    except Exception:
        pass
    if not perfil_assumido_pelo_controle(pagina, perfil.strip()):
        recado = (f"A opcao {perfil.strip()!r} foi escolhida e o controle nao "
                  "passou a mostra-la. O botao de entrar so habilita depois "
                  "disso, entao clicar nele nao faria nada. Nada foi enviado.")
        # O MESMO bloco das outras recusas. Em 07/10/2026 esta aqui era a unica
        # sem diagnostico, e foi exatamente ela que aconteceu: o caminho de
        # teclado deu certo o bastante para pular o ramo que relatava, e a
        # corrida custou uma tentativa de login para contar menos que a
        # anterior. Relato que depende de QUAL recusa foi nao e relato.
        try:
            caixa_agora = elemento_por_rotulo(pagina, ROTULO_DA_LISTA_DE_PERFIL)
        except Exception:
            caixa_agora = None
        recado += relato_da_escolha(pagina, caixa_agora, perfil.strip(),
                                    "(a escolha nao passou pelo caminho da caixa)")
        raise PerfilNaoInformado(recado)

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


def reencontrar_o_portal(pagina: Any, segundos: int = 15) -> Any:
    """A aba do portal AGORA, porque a que o programa segura pode ter mudado.

    A licao de 06/10/2026 nao foi "o portal abre em janela nova": foi que a
    pagina que o programa segura NAO e estavel. A janela aceita como portal
    saiu de `/portalservicos/` para `www.tjrj.jus.br` entre um passo e o
    seguinte, e o comando levou a pagina publica do tribunal ate o fim, tres
    passos adiante, anunciando a cada parada um defeito que nao existia.

    Entao, a cada fronteira, o portal e reencontrado em vez de carregado. Nao
    recusa quando nao acha: quem recusa e o passo seguinte, que sabe o que
    procurava. Aqui so se devolve a melhor aba disponivel.
    """
    achada = achar_aba_do_portal(pagina, segundos)
    return trazer_para_a_frente(achada if achada is not None else pagina)
