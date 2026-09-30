"""Adaptador do PJe, comecando pela consulta publica.

Por que a consulta publica vem primeiro: ela NAO exige login. A sessao do PJe
nao sobrevive ao fechamento do navegador, ao contrario da do e-SAJ, entao cada
consulta autenticada custa uma tentativa do teto da conta e um codigo lido no
aplicativo. A consulta publica custa zero, e para processo que nao corre em
segredo ela responde a mesma pergunta: em que pe esta.

O que ela NAO responde: o que depende de habilitacao nos autos. Para isso ha a
consulta autenticada, na segunda metade deste arquivo.

PROVENIENCIA DOS SELETORES, que nesta casa vale mais que o codigo:

  Consulta publica. TODOS os seletores foram lidos da tela real do PJe do Rio,
  em 30/09/2026. Nenhum foi deduzido: identificador com dois pontos e sintaxe
  do JSF, e adivinhar um deles falha em silencio.

  Consulta autenticada. O operador fotografou o caminho inteiro em 30/09/2026 e
  dele vem o que esta afirmado aqui: o endereco da tela
  (`/1g/Processo/ConsultaProcesso/listView.seam`), o numero partido em SEIS
  campos, o aviso de responsabilidade em caixa do proprio navegador ao clicar
  no numero, e a abertura do processo em ABA NOVA. Os identificadores desses
  campos NAO apareceram nas fotos, entao nenhum foi escrito aqui: o codigo
  procura os campos pela forma e confere o que digitou antes de pesquisar. Se a
  forma nao bater, ele para e relata a tela, em vez de clicar as cegas.
"""

from __future__ import annotations

from typing import Any, Optional


class ConsultaPJeIndisponivel(RuntimeError):
    """A tela da consulta publica nao apareceu como esperado."""


# Os identificadores do PJe trazem dois pontos, que em CSS separam
# pseudoclasse. Por isso a busca e por atributo, e nao por `#`: escapar o
# caractere funciona, mas uma barra invertida perdida numa edicao futura viraria
# um seletor que nao casa com nada e falha sem dizer por que.
CAMPO_NUMERO = ('input[id="fPP:numProcesso-inputNumeroProcessoDecoration:'
                'numProcesso-inputNumeroProcesso"]')
BOTAO_PESQUISAR = 'input[id="fPP:searchProcessos"]'
TABELA_RESULTADOS = 'table[id="fPP:processosTable"]'

# Caminho da consulta publica dentro do portal. Derivado do endereco de login
# que ja esta no .env, e nao escrito a mao: um endereco fixo aqui apontaria
# para o Rio de Janeiro para sempre, e o mesmo PJe atende dezenas de tribunais.
SUFIXO_CONSULTA_PUBLICA = "/ConsultaPublica/listView.seam"


def endereco_da_consulta_publica(url_de_login: str) -> str:
    """Monta o endereco da consulta publica a partir do endereco de login.

    O de login termina em `/login.seam`; a consulta publica mora ao lado, na
    mesma instancia. Conferido em campo: `/1g/login.seam` leva a
    `/1g/ConsultaPublica/listView.seam`, que o proprio portal redireciona.
    """
    base = (url_de_login or "").split("?")[0].split("#")[0].rstrip("/")
    if base.endswith(".seam"):
        base = base.rsplit("/", 1)[0]
    if not base:
        raise ConsultaPJeIndisponivel(
            "Sem endereco de login configurado, nao da para achar a consulta publica.")
    return f"{base}{SUFIXO_CONSULTA_PUBLICA}"


def conferir_redirecionamento(partida: str, chegada: str,
                              sufixo: str = SUFIXO_CONSULTA_PUBLICA) -> None:
    """Aceita o redirecionamento do portal, e so ele.

    Duas condicoes, as duas necessarias: mesma origem, porque um portal que
    joga a consulta para outro dominio nao esta mais sob a autorizacao dada; e
    mesmo nome de tela, porque chegar a uma tela diferente da pedida e
    exatamente o caso em que preencher e clicar as cegas faria estrago.
    """
    from urllib.parse import urlparse

    de, para = urlparse(partida), urlparse(chegada)
    if de.netloc != para.netloc:
        raise ConsultaPJeIndisponivel(
            f"O portal levou a consulta para outro dominio ({para.netloc or chegada}). "
            "Nada foi preenchido.")
    if not para.path.endswith(sufixo):
        raise ConsultaPJeIndisponivel(
            f"O portal levou a outra tela ({para.path}), e nao a que foi pedida "
            f"({sufixo}). Nada foi preenchido.")


def buscar_publico(pagina: Any, guarda: Any, numero: Any, url_de_login: str,
                   segundos: int = 30) -> str:
    """Abre a consulta publica, preenche o numero e pesquisa. Somente leitura.

    Devolve o endereco em que parou. Nao abre documento, nao baixa nada e nao
    encosta em expediente: a tela tem um formulario de busca e nada mais.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import _assentar, elemento_visivel, permissao_efemera

    destino = endereco_da_consulta_publica(url_de_login)

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(destino).padrao_url,
        descricao="consulta publica do PJe, somente leitura",
        conferido_em="execucao atual",
        seletores_clicaveis=(BOTAO_PESQUISAR,),
        seletores_preenchiveis=(CAMPO_NUMERO,),
    ))
    guarda.pode_executar(Acao.NAVEGAR, destino, url=destino)
    pagina.goto(destino, timeout=segundos * 1000, wait_until="domcontentloaded")
    _assentar(pagina, segundos)

    # O PJe redireciona `/1g/ConsultaPublica/...` para `/pje/ConsultaPublica/...`,
    # conferido em campo em 30/09/2026. A trava barrou o preenchimento, e estava
    # CERTA: a permissao valia para a tela de partida, e quem chega a outro
    # endereco nao tem autorizacao nenhuma ali. A correcao nao e afrouxar a
    # trava; e conferir que o destino ainda e a mesma tela do mesmo portal, e so
    # entao autoriza-la nominalmente.
    final = pagina.url
    if final != destino:
        conferir_redirecionamento(destino, final)
        guarda.permissoes.append(Permissao(
            padrao_url=permissao_efemera(final).padrao_url,
            descricao="consulta publica do PJe apos redirecionamento do portal",
            conferido_em="execucao atual",
            seletores_clicaveis=(BOTAO_PESQUISAR,),
            seletores_preenchiveis=(CAMPO_NUMERO,),
        ))

    campo = elemento_visivel(pagina, CAMPO_NUMERO)
    if campo is None:
        raise ConsultaPJeIndisponivel(
            f"O campo do numero nao apareceu em {pagina.url}. A tela mudou, ou o "
            "portal esta fora do ar.")

    guarda.pode_executar(Acao.PREENCHER, CAMPO_NUMERO, url=pagina.url)
    campo.click()
    campo.fill(numero.formatado)
    # Confere o que entrou ANTES de pesquisar. O campo do PJe tem mascara, e
    # mascara que rejeita o formato deixa o campo vazio sem reclamar: a busca
    # entao volta "nada encontrado", e o operador conclui que o processo nao
    # existe quando o que falhou foi a digitacao.
    entrou = campo.evaluate("e => (e.value || '').replace(/\\D/g, '').length")
    if entrou < 20:
        raise ConsultaPJeIndisponivel(
            f"O numero nao entrou inteiro no campo ({entrou} de 20 digitos). "
            "Nada foi pesquisado.")

    botao = elemento_visivel(pagina, BOTAO_PESQUISAR)
    if botao is None:
        raise ConsultaPJeIndisponivel("O botao Pesquisar nao esta na tela.")
    guarda.pode_executar(Acao.CLICAR, BOTAO_PESQUISAR, url=pagina.url)
    botao.click()
    _assentar(pagina, segundos)
    return pagina.url


def linhas_do_resultado(pagina: Any) -> int:
    """Quantas linhas a tabela de resultados traz. Conta, nao le conteudo.

    A contagem serve para o programa dizer se achou algo sem imprimir dado de
    processo: o teor sai para arquivo, como no e-SAJ, e nunca para a tela.
    """
    try:
        tabela = pagina.query_selector(TABELA_RESULTADOS)
        if tabela is None:
            return 0
        return len(tabela.query_selector_all("tbody tr"))
    except Exception:
        return 0


# ===========================================================================
# Consulta autenticada
# ===========================================================================
#
# Tres coisas separam esta tela da consulta publica, e as tres foram vistas nas
# fotos de 30/09/2026. Nenhuma delas se resolve reaproveitando o codigo de cima:
#
#   1. o numero nao vai num campo so. Vai em SEIS, um por parte da numeracao da
#      resolucao nº. 65/2008 (NNNNNNN, DD, AAAA, J, TR, OOOO);
#   2. clicar no numero do processo levanta uma caixa do PROPRIO NAVEGADOR, com
#      o aviso de responsabilidade da resolucao nº. 121 do Conselho Nacional de
#      Justica. O Playwright dispensa essas caixas sozinho, por padrao, sem
#      contar a ninguem: quem nao a trata explicitamente ve o clique "nao
#      funcionar" e nunca fica sabendo que houve um aviso;
#   3. o processo abre em ABA NOVA, e nao na mesma.


SUFIXO_CONSULTA_AUTENTICADA = "/Processo/ConsultaProcesso/listView.seam"

# Os seis campos, na ordem em que aparecem na tela, com o tamanho de cada parte.
TAMANHOS_DAS_PARTES = (7, 2, 4, 1, 2, 4)

# Procura pela FORMA, nao pelo identificador. O identificador do JSF muda de
# versao para versao e nao foi lido em tela real; o trecho "umeroProcesso"
# aparece nos dois jeitos de escrever (`numeroProcesso` e `NumeroProcesso`) e
# nao depende de casar maiuscula.
SELETOR_CANDIDATO_DO_NUMERO = 'input[id*="umeroProcesso"]'

# O aviso da resolucao nº. 121 fala em responsabilizacao civil, administrativa e
# criminal de quem acessa autos de processo em que nao atua. Estas marcas servem
# para RECONHECE-LO, nunca para aceita-lo: aceitar e ato do advogado.
MARCAS_DO_AVISO = ("responsabiliza", "121", "sigilo", "acesso")


class AvisoDeResponsabilidade(RuntimeError):
    """O portal pediu aceite de responsabilidade e ninguem o deu."""


def endereco_da_consulta_autenticada(url_de_login: str) -> str:
    """Endereco da consulta autenticada, derivado do endereco de login.

    Mesma razao da consulta publica: escrever o endereco do Rio aqui o fixaria
    para sempre, e o mesmo PJe atende dezenas de tribunais.
    """
    base = (url_de_login or "").split("?")[0].split("#")[0].rstrip("/")
    if base.endswith(".seam"):
        base = base.rsplit("/", 1)[0]
    if not base:
        raise ConsultaPJeIndisponivel(
            "Sem endereco de login configurado, nao da para achar a consulta.")
    return f"{base}{SUFIXO_CONSULTA_AUTENTICADA}"


def partes_do_numero(numero: Any) -> tuple[str, ...]:
    """As seis partes do numero, na ordem dos seis campos da tela."""
    return (numero.sequencial, numero.digito_verificador, numero.ano,
            str(numero.segmento), numero.tribunal, numero.origem)


def campos_do_numero(pagina: Any) -> list:
    """Os campos do numero que estao de fato na tela, na ordem do documento.

    Devolve o que achou, sem julgar quantos sao: quem julga e
    `conferir_forma_dos_campos`, que separa "achei seis" de "achei outra coisa"
    com uma mensagem que diz o que achou.
    """
    achados = []
    for elemento in pagina.query_selector_all(SELETOR_CANDIDATO_DO_NUMERO):
        try:
            if (elemento.get_attribute("type") or "text").lower() == "hidden":
                continue
            if elemento.get_attribute("readonly") is not None:
                continue
            if elemento.get_attribute("disabled") is not None:
                continue
            if not elemento.is_visible():
                continue
        except Exception:
            continue
        achados.append(elemento)
    return achados


def conferir_forma_dos_campos(campos: list) -> None:
    """Recusa a tela que nao tem a forma fotografada. Antes de digitar nada.

    Duas conferencias. A contagem, porque digitar seis partes em cinco campos
    espalha o numero errado por uma busca que ninguem pediu. E o tamanho maximo
    de cada campo, quando a tela o declara, porque campo na ordem trocada aceita
    o que se digita e devolve "nada encontrado": o advogado leria isso como
    processo inexistente, que e o pior erro que esta consulta pode cometer.
    """
    if len(campos) != len(TAMANHOS_DAS_PARTES):
        raise ConsultaPJeIndisponivel(
            f"A tela da consulta tem {len(campos)} campo(s) de numero, e o caminho "
            f"conferido em campo tem {len(TAMANHOS_DAS_PARTES)}. Nada foi digitado. "
            "A tela mudou, ou a autenticacao parou antes dela.")
    for posicao, (campo, tamanho) in enumerate(zip(campos, TAMANHOS_DAS_PARTES), 1):
        try:
            declarado = campo.get_attribute("maxlength")
        except Exception:
            declarado = None
        if declarado and declarado.isdigit() and int(declarado) != tamanho:
            raise ConsultaPJeIndisponivel(
                f"O {posicao}º campo do numero aceita {declarado} digito(s), e a "
                f"{posicao}ª parte da numeracao tem {tamanho}. A ordem dos campos "
                "nao e a conferida em campo. Nada foi digitado.")


def buscar_autenticado(pagina: Any, guarda: Any, numero: Any, url_de_login: str,
                       segundos: int = 45) -> str:
    """Abre a consulta autenticada, preenche as seis partes e pesquisa.

    Somente leitura: preenche busca e clica em pesquisar. Nao abre processo,
    nao aceita aviso nenhum e nao baixa nada. Abrir o processo e um segundo
    passo, deliberadamente separado, porque ele esbarra no aviso de
    responsabilidade.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import _assentar, permissao_efemera

    destino = endereco_da_consulta_autenticada(url_de_login)
    # A tela da consulta nao e a mesma do login, e a trava nega por padrao. A
    # autorizacao e nominal e vale so para este endereco: navegar ate ela e
    # tudo o que ela concede, e os campos so entram depois de a forma bater.
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(destino).padrao_url,
        descricao="consulta autenticada do PJe, tela de busca",
        conferido_em="execucao atual",
    ))
    guarda.pode_executar(Acao.NAVEGAR, destino, url=destino)
    pagina.goto(destino, timeout=segundos * 1000, wait_until="domcontentloaded")
    _assentar(pagina, segundos)

    final = pagina.url
    if final != destino:
        conferir_redirecionamento(destino, final, SUFIXO_CONSULTA_AUTENTICADA)

    campos = campos_do_numero(pagina)
    conferir_forma_dos_campos(campos)

    # A autorizacao so e escrita DEPOIS de a forma bater, e nomeia os
    # identificadores que a propria tela declarou. Liberar antes seria liberar
    # o que ainda nao se sabe o que e.
    identificadores = tuple(
        f'input[id="{campo.get_attribute("id")}"]' for campo in campos)
    botao_pesquisar = achar_botao_pesquisar(pagina)
    if botao_pesquisar is None:
        raise ConsultaPJeIndisponivel(
            f"O botao de pesquisar nao esta na tela ({pagina.url}). Nada foi digitado.")
    seletor_do_botao = f'input[id="{botao_pesquisar.get_attribute("id")}"]'
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="consulta autenticada do PJe, somente a busca",
        conferido_em="execucao atual",
        seletores_clicaveis=(seletor_do_botao,),
        seletores_preenchiveis=identificadores,
    ))

    for campo, seletor, parte in zip(campos, identificadores, partes_do_numero(numero)):
        guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
        campo.click()
        campo.fill(parte)

    # Confere o que entrou ANTES de pesquisar, remontando o numero a partir da
    # tela. Campo com mascara que rejeita o formato fica vazio sem reclamar, e a
    # busca volta "nada encontrado" por defeito nosso, nao por falta do processo.
    digitado = "".join(
        campo.evaluate("e => (e.value || '').replace(/\\D/g, '')") for campo in campos)
    if digitado != numero.apenas_digitos:
        raise ConsultaPJeIndisponivel(
            f"O numero na tela ficou com {len(digitado)} digito(s) e nao confere com "
            "o pedido. Nada foi pesquisado.")

    guarda.pode_executar(Acao.CLICAR, seletor_do_botao, url=pagina.url)
    botao_pesquisar.click()
    _assentar(pagina, segundos)
    return pagina.url


def achar_botao_pesquisar(pagina: Any) -> Optional[Any]:
    """O botao de pesquisar, achado pelo que ESTA ESCRITO nele.

    Procurar pelo texto, e nao pelo identificador, e a escolha certa aqui: o
    identificador do JSF nao foi lido em tela real, mas a palavra no botao foi
    fotografada. Texto errado nao acha nada e o comando para; identificador
    adivinhado tambem nao acha nada, so que depois de ja ter digitado.
    """
    for candidato in pagina.query_selector_all("input[type=submit], button"):
        try:
            if not candidato.is_visible():
                continue
            rotulo = (candidato.get_attribute("value")
                      or candidato.inner_text() or "").strip().lower()
        except Exception:
            continue
        if rotulo.startswith("pesquisar"):
            return candidato
    return None


def achar_link_do_processo(pagina: Any, numero: Any) -> Optional[Any]:
    """O link do numero do processo na tabela de resultados.

    Casa pelos digitos do numero que se pediu, e nao pela posicao na tabela:
    clicar na primeira linha seria clicar no que a tela ofereceu, e nao no que
    se procurou.
    """
    alvo = numero.apenas_digitos
    for link in pagina.query_selector_all("a"):
        try:
            texto = "".join(c for c in (link.inner_text() or "") if c.isdigit())
        except Exception:
            continue
        if texto == alvo:
            return link
    return None


def ler_aviso(pagina: Any, aceitar: bool, registro: list) -> None:
    """Trata a caixa de aviso do navegador, e por padrao NAO a aceita.

    O Playwright dispensa dialogo sozinho quando ninguem escuta, em silencio. O
    efeito pratico e o pior possivel para esta tela: o aviso da resolucao nº. 121
    do Conselho Nacional de Justica some sem ninguem ler, o clique parece ter
    falhado, e o programa teria acabado de decidir, sozinho, uma questao de
    responsabilizacao civil, administrativa e criminal do advogado.

    Por isso o padrao aqui e dispensar E GUARDAR O TEXTO, para mostra-lo a quem
    de direito. Aceitar so acontece com `aceitar=True`, que vem de um pedido
    explicito do operador, nunca de uma decisao do codigo.
    """

    def tratar(dialogo):
        try:
            registro.append(dialogo.message)
        except Exception:
            registro.append("(aviso sem texto legivel)")
        try:
            dialogo.accept() if aceitar else dialogo.dismiss()
        except Exception:
            pass

    pagina.on("dialog", tratar)


def parece_aviso_de_responsabilidade(texto: str) -> bool:
    """Se o texto guardado tem cara do aviso da resolucao nº. 121."""
    baixo = (texto or "").lower()
    return any(marca in baixo for marca in MARCAS_DO_AVISO)


def abrir_processo(pagina: Any, guarda: Any, numero: Any, *, aceitar_termo: bool,
                   segundos: int = 45) -> tuple[Optional[Any], list]:
    """Clica no numero do processo e devolve a ABA NOVA que o portal abre.

    Devolve `(aba, avisos)`. Sem aceite, `aba` e `None` e `avisos` traz o texto
    que o portal mostrou: e o que o advogado precisa ler antes de decidir.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import permissao_efemera

    link = achar_link_do_processo(pagina, numero)
    if link is None:
        raise ConsultaPJeIndisponivel(
            f"O numero {numero.formatado} nao aparece como link na tabela de "
            "resultados. Nada foi aberto.")

    seletor = f'a[href*="{numero.apenas_digitos[:7]}"]'
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="abrir os autos a partir do resultado da consulta",
        conferido_em="execucao atual",
        seletores_clicaveis=(seletor,),
    ))
    guarda.pode_executar(Acao.CLICAR, seletor, url=pagina.url)

    avisos: list = []
    ler_aviso(pagina, aceitar_termo, avisos)

    if not aceitar_termo:
        # Clica mesmo assim, de proposito: e o clique que faz o aviso aparecer,
        # e sem o texto do aviso o advogado nao tem o que decidir. A caixa e
        # dispensada, entao nada e aberto.
        link.click()
        pagina.wait_for_timeout(1500)
        return None, avisos

    try:
        with pagina.context.expect_page(timeout=segundos * 1000) as nova:
            link.click()
        aba = nova.value
    except Exception as exc:
        raise ConsultaPJeIndisponivel(
            f"O aceite foi dado e a aba do processo nao abriu em {segundos}s "
            f"({type(exc).__name__}). Nada foi lido.") from None
    try:
        aba.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
    except Exception:
        pass
    return aba, avisos
