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

import re
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


def campos_de_texto_a_vista(pagina: Any, teto: int = 12) -> list[str]:
    """Descricao dos campos de texto visiveis: identificador, nome e tamanho.

    So a FORMA, nunca o conteudo. Numa tela de busca os campos estao vazios, e
    ainda assim a regra vale: o que se imprime daqui e estrutura.

    Existe porque `SELETOR_CANDIDATO_DO_NUMERO` foi escrito por deducao, e nao
    lido em tela real. Quando ele nao acha nada, a hipotese mais provavel e que
    o palpite errou, e nao que a tela mudou. Sem este relato cada tentativa
    frustrada gasta um login e nao ensina nada, e o proximo palpite sai tao no
    escuro quanto o primeiro.
    """
    saida: list[str] = []
    try:
        elementos = pagina.query_selector_all("input")
    except Exception:
        return saida
    for elemento in elementos:
        if len(saida) >= teto:
            break
        try:
            if (elemento.get_attribute("type") or "text").lower() in (
                    "hidden", "submit", "button", "image", "checkbox", "radio"):
                continue
            if not elemento.is_visible():
                continue
            pecas = []
            for atributo in ("id", "name", "maxlength"):
                valor = elemento.get_attribute(atributo)
                if valor:
                    pecas.append(f"{atributo}={valor}")
        except Exception:
            continue
        if pecas:
            saida.append(" ".join(pecas))
    return saida


def conferir_forma_dos_campos(campos: list, pagina: Any = None) -> None:
    """Recusa a tela que nao tem a forma fotografada. Antes de digitar nada.

    Duas conferencias. A contagem, porque digitar seis partes em cinco campos
    espalha o numero errado por uma busca que ninguem pediu. E o tamanho maximo
    de cada campo, quando a tela o declara, porque campo na ordem trocada aceita
    o que se digita e devolve "nada encontrado": o advogado leria isso como
    processo inexistente, que e o pior erro que esta consulta pode cometer.
    """
    if len(campos) != len(TAMANHOS_DAS_PARTES):
        recado = (
            f"A tela da consulta tem {len(campos)} campo(s) de numero achado(s) por "
            f"{SELETOR_CANDIDATO_DO_NUMERO}, e o caminho fotografado tem "
            f"{len(TAMANHOS_DAS_PARTES)}. Nada foi digitado.")
        if not campos:
            # Ordem das hipoteses pela probabilidade, nao pela gravidade: este
            # seletor foi DEDUZIDO, e e o suspeito numero um de nao achar nada.
            recado += (
                " Achar zero campo quer dizer, antes de tudo, que este seletor foi"
                " deduzido e errou o alvo; depois, que a autenticacao parou antes"
                " desta tela; por ultimo, que a tela mudou.")
        if pagina is not None:
            a_vista = campos_de_texto_a_vista(pagina)
            if a_vista:
                recado += " Campos de texto que a tela mostra: " + "; ".join(a_vista)
        raise ConsultaPJeIndisponivel(recado)
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
    from .portal import _assentar, permissao_efemera, preencher_conferindo

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
    conferir_forma_dos_campos(campos, pagina)

    # A autorizacao so e escrita DEPOIS de a forma bater, e nomeia os
    # identificadores que a propria tela declarou. Liberar antes seria liberar
    # o que ainda nao se sabe o que e.
    identificadores = tuple(
        f'input[id="{campo.get_attribute("id")}"]' for campo in campos)
    botao_pesquisar = achar_botao_pesquisar(pagina)
    if botao_pesquisar is None:
        raise ConsultaPJeIndisponivel(
            f"O botao de pesquisar nao esta na tela ({pagina.url}). Nada foi digitado.")
    seletor_do_botao = seletor_do_elemento(botao_pesquisar, "pesquisar")
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="consulta autenticada do PJe, somente a busca",
        conferido_em="execucao atual",
        seletores_clicaveis=(seletor_do_botao,),
        seletores_preenchiveis=identificadores,
    ))

    for posicao, (campo, seletor, parte) in enumerate(
            zip(campos, identificadores, partes_do_numero(numero)), 1):
        guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
        # `fill` sozinho desiste em silencio em campo controlado por framework,
        # e aqui desistir custa o login inteiro: a conferencia abaixo acusaria
        # o numero incompleto e o comando pararia, com a sessao ja gasta.
        preencher_conferindo(campo, parte, f"{posicao}ª parte do numero")

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


def seletor_do_elemento(elemento: Any, apelido: str) -> str:
    """O seletor que NOMEIA este elemento para a trava de navegacao.

    Montava-se `input[id="..."]` com o identificador do elemento, o que
    assumia duas coisas: que ele e um `input` e que ele tem identificador. A
    primeira deixou de valer quando a busca passou a aceitar quatro tipos de
    botao; a segunda nunca valeu para `<button>` sem id, e ali o seletor saia
    como `input[id="None"]`, que a trava autorizaria sem nomear nada.

    A trava precisa de um nome que case com o elemento de verdade: autorizacao
    que nao casa e autorizacao que nao protege.
    """
    try:
        etiqueta = (elemento.evaluate("e => e.tagName") or "").lower() or "*"
        identificador = elemento.get_attribute("id")
    except Exception:
        return f'texto={apelido}'
    if identificador:
        return f'{etiqueta}[id="{identificador}"]'
    return f'{etiqueta}:{apelido}'


# Lido da tela real em 23/10/2026, na corrida que autenticou no PJe do Rio de
# Janeiro. Ate entao este identificador nao era conhecido, e por isso a busca
# era so por texto. Agora ele esta conferido, e entra como primeiro caminho.
BOTAO_PESQUISAR_AUTENTICADO = 'input[id="fPP:searchProcessos"]'

# Os quatro tipos, e nao dois. O RichFaces, que desenha o PJe, renderiza botao
# de comando como `input[type=button]`, que a versao anterior desta funcao NAO
# procurava: ela olhava so `input[type=submit], button`. O proprio projeto ja
# tem a lista certa em `portal.ALVOS_CLICAVEIS`, e esta funcao nao a usava.
TIPOS_DE_BOTAO = "button, input[type=submit], input[type=button], input[type=image]"


def achar_botao_pesquisar(pagina: Any) -> Optional[Any]:
    """O botao de pesquisar: pelo identificador conferido, depois pelo texto.

    A corrida de 23/10/2026 autenticou no PJe do Rio de Janeiro e parou aqui,
    dizendo que o botao nao estava na tela. Ele estava: o relato da propria
    tela trazia `input#fPP:searchProcessos`, e a captura mostrou "PESQUISAR" no
    fim do painel da esquerda, abaixo da dobra.

    Duas coisas mudaram, e as duas vieram daquela tela:

    O IDENTIFICADOR agora e conhecido. A versao anterior procurava so por
    texto, e o comentario dizia por que: o identificador do JSF nunca tinha
    sido lido em tela real. Agora foi, entao ele vira o primeiro caminho. A
    busca por texto continua como segunda, porque identificador de JSF muda com
    a versao do portal e a palavra no botao e mais estavel.

    OS TIPOS DE BOTAO passaram de dois para quatro. RichFaces renderiza botao
    de comando como `input[type=button]`, que nao estava na lista.

    A posicao NAO entra aqui. Abaixo da dobra nao e escondido, e quem decide se
    da para clicar e o proprio Playwright, que rola sozinho e reclama alto se
    nao alcancar. Recusar por posicao foi o que parou quatro corridas no Portal
    de Servicos em outubro.
    """
    direto = pagina.query_selector(BOTAO_PESQUISAR_AUTENTICADO)
    if direto is not None:
        return direto
    for candidato in pagina.query_selector_all(TIPOS_DE_BOTAO):
        try:
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


# ==========================================================================
# A LINHA DO TEMPO DOS AUTOS
#
# PROVENIENCIA, que nesta casa vale mais que o codigo. Tudo abaixo vem da tela
# real dos autos do PJe do Rio de Janeiro, aberta em 23/10/2026 no endereco
# `/1g/Processo/ConsultaProcesso/Detalhe/listProcessoCompletoAdvogado.seam`.
#
# O QUE A TELA DECLAROU, e e o que esta escrito aqui:
#
#   form#divTimeLine                        o formulario da linha do tempo
#   div#divTimeLine:divEventosTimeLine      o conteiner dos eventos
#   div#divTimeLine:eventosTimeLineElement
#   input#totalPaginas  input#paginaAtual   a paginacao
#   input#divTimeLine:chkExibirDocumentos   mostrar documentos
#   input#divTimeLine:chkExibirMovimentos   mostrar movimentos
#   a#divTimeLine:btnPesquisar  a#divTimeLine:btnAtualizar
#
# O QUE NAO ENTRA AQUI, de proposito: os identificadores dos ITENS, que a tela
# traz na forma `divTimeLine:j_id410:0:j_id412:1:j_id423`. Esses `j_id` sao
# gerados pelo JavaServer Faces e mudam a cada versao do portal. Escrever
# contra eles e escrever contra areia: funcionaria hoje e falharia na proxima
# atualizacao, em silencio, devolvendo zero eventos como se o processo nao
# tivesse nenhum.
#
# Entao a leitura e ESTRUTURAL: parte do conteiner, que tem nome estavel, e
# desce pelos filhos.
# ==========================================================================

CONTEINER_DA_LINHA_DO_TEMPO = 'div[id="divTimeLine:divEventosTimeLine"]'
TOTAL_DE_PAGINAS = 'input[id="totalPaginas"]'
PAGINA_ATUAL = 'input[id="paginaAtual"]'

# O identificador do documento, como aparece no inicio do rotulo de cada item:
# "128507266 - Peticao Inicial", "312678280 - Notificacao". E por ele que o
# painel de download pede a faixa, entao e o dado que mais importa extrair.
_IDENTIFICADOR_DO_DOCUMENTO = re.compile(r"^\s*(\d{6,})\s*-\s*(.+?)\s*$")

# A data que encabeca cada grupo, na forma que a tela usa: "15 out 2026".
_DATA_DO_GRUPO = re.compile(
    r"^\s*(\d{1,2})\s+(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\w*\s+(\d{4})\s*$",
    re.IGNORECASE)

_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
          "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def data_do_grupo(texto: str) -> Optional[str]:
    """`15 out 2026` vira `2026-10-15`. Texto que nao for data devolve None."""
    casou = _DATA_DO_GRUPO.match(texto or "")
    if not casou:
        return None
    dia, mes, ano = casou.groups()
    numero_do_mes = _MESES.get(mes[:3].lower())
    if not numero_do_mes:
        return None
    return f"{ano}-{numero_do_mes:02d}-{int(dia):02d}"


def partir_o_rotulo(texto: str) -> tuple:
    """Devolve (identificador, descricao) de um item da linha do tempo.

    Item de DOCUMENTO comeca pelo identificador: "128507266 - Peticao Inicial".
    Item de MOVIMENTO nao tem identificador, so o texto do movimento, e sai
    como (None, texto). Distinguir os dois importa: so documento entra na faixa
    do download, e pedir o download de um movimento devolveria nada.
    """
    limpo = " ".join((texto or "").split())
    casou = _IDENTIFICADOR_DO_DOCUMENTO.match(limpo)
    if casou:
        return casou.group(1), casou.group(2)
    return None, limpo


# O JavaScript que LE a linha do tempo. Roda no navegador porque a travessia
# elemento a elemento pelo canal do Playwright custa uma viagem por no, e esta
# tela tem centenas: a corrida de 23/10/2026 contou 472 elementos com
# identificador so na pagina, antes de abrir grupo nenhum.
#
# Ele devolve a FORMA, nao o conteudo dos autos: rotulo de item e data de
# grupo. Rotulo de documento no PJe e tipo de peca ("Peticao Inicial",
# "Notificacao"), nao o texto dela.
JS_DA_LINHA_DO_TEMPO = r"""() => {
  const conteiner = document.querySelector(
    'div[id="divTimeLine:divEventosTimeLine"]');
  if (!conteiner) return null;

  // O texto PROPRIO do no: o dos filhos nao entra. Sem isto o primeiro no
  // devolveria a linha do tempo inteira numa string so, que foi exatamente o
  // defeito que o indice do Visualizador teve em 21/10/2026.
  const textoProprio = (no) => {
    let saida = '';
    for (const filho of no.childNodes) {
      if (filho.nodeType === 3) saida += filho.nodeValue;
    }
    return saida.trim();
  };

  const itens = [];
  // Ancoras sao documentos e movimentos clicaveis; divs sem ancora dentro
  // costumam ser movimentos puros. Os dois entram, marcados.
  for (const no of conteiner.querySelectorAll('a, div, span')) {
    const proprio = textoProprio(no);
    if (!proprio) continue;
    // Um no cujo texto proprio repete o de um ancestral ja recolhido seria
    // item duplicado; a profundidade separa pai de filho na hora de montar.
    let profundidade = 0;
    for (let p = no.parentElement; p && p !== conteiner; p = p.parentElement) {
      profundidade += 1;
    }
    itens.push({
      etiqueta: no.tagName.toLowerCase(),
      texto: proprio.slice(0, 300),
      clicavel: no.tagName.toLowerCase() === 'a',
      endereco: (no.getAttribute && no.getAttribute('href')) || '',
      profundidade: profundidade,
    });
  }

  const numero = (seletor) => {
    const campo = document.querySelector(seletor);
    const bruto = campo ? (campo.value || '') : '';
    const lido = parseInt(bruto, 10);
    return Number.isNaN(lido) ? null : lido;
  };

  return {
    itens: itens,
    total_de_paginas: numero('input[id="totalPaginas"]'),
    pagina_atual: numero('input[id="paginaAtual"]'),
  };
}"""


def ler_a_linha_do_tempo(pagina: Any) -> dict:
    """A linha do tempo dos autos: eventos, documentos e a paginacao.

    Devolve `{"eventos": [...], "paginas": n, "pagina": n, "aviso": str}`.
    Cada evento traz `data`, `identificador` (do documento, ou None quando for
    movimento), `descricao` e `endereco`.

    NAO devolve conteudo de peca. O rotulo do PJe e o TIPO do documento, e e
    isso que vai no indice; o texto da peca sai do PDF, depois do download.

    Quando o conteiner nao existe, devolve o aviso em vez de lista vazia:
    "nenhum evento" e "nao achei a linha do tempo" sao conclusoes diferentes, e
    confundi-las faria o advogado achar que o processo nao tem movimento.
    """
    try:
        lido = pagina.evaluate(JS_DA_LINHA_DO_TEMPO)
    except Exception as erro:
        return {"eventos": [], "paginas": None, "pagina": None,
                "aviso": f"A leitura da linha do tempo falhou ({type(erro).__name__})."}
    if not isinstance(lido, dict):
        return {"eventos": [], "paginas": None, "pagina": None,
                "aviso": ("A linha do tempo nao foi encontrada nesta tela "
                          "(div[id=\"divTimeLine:divEventosTimeLine\"]). Isso NAO "
                          "quer dizer que o processo nao tem movimento.")}

    eventos: list = []
    data_corrente: Optional[str] = None
    vistos: set = set()
    for item in lido.get("itens") or []:
        texto = (item.get("texto") or "").strip()
        if not texto:
            continue
        virada = data_do_grupo(texto)
        if virada:
            data_corrente = virada
            continue
        identificador, descricao = partir_o_rotulo(texto)
        chave = (identificador, descricao)
        if chave in vistos:
            continue
        vistos.add(chave)
        eventos.append({
            "data": data_corrente,
            "identificador": identificador,
            "descricao": descricao,
            "e_documento": identificador is not None,
            "endereco": item.get("endereco") or "",
        })
    return {
        "eventos": eventos,
        "paginas": lido.get("total_de_paginas"),
        "pagina": lido.get("pagina_atual"),
        "aviso": "",
    }


def faixa_de_identificadores(eventos: list) -> tuple:
    """O menor e o maior identificador de documento, para o painel de download.

    O painel pede "ID a partir de" e "Ate", e o advogado explicou em
    23/10/2026 como ele e usado: cronologia crescente, do documento mais antigo
    ao mais novo. O menor identificador e o mais antigo porque o PJe os emite
    em ordem; `(None, None)` quando nao ha documento nenhum na lista.
    """
    numeros = [int(e["identificador"]) for e in eventos
               if e.get("identificador") and str(e["identificador"]).isdigit()]
    if not numeros:
        return (None, None)
    return (min(numeros), max(numeros))
