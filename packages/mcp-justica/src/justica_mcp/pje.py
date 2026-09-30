"""Adaptador do PJe, comecando pela consulta publica.

Por que a consulta publica vem primeiro: ela NAO exige login. A sessao do PJe
nao sobrevive ao fechamento do navegador, ao contrario da do e-SAJ, entao cada
consulta autenticada custa uma tentativa do teto da conta e um codigo lido no
aplicativo. A consulta publica custa zero, e para processo que nao corre em
segredo ela responde a mesma pergunta: em que pe esta.

O que ela NAO responde: o que depende de habilitacao nos autos. Para isso
continua sendo necessario o acesso autenticado, cujo caminho o painel do
advogado revelou em 30/09/2026 (`/1g/Processo/ConsultaProcesso/listView.seam`)
e que sera escrito quando uma tela real dele for lida.

TODOS os seletores daqui foram lidos da tela real da consulta publica do PJe
do Rio, em 30/09/2026. Nenhum foi deduzido: identificador com dois pontos e
sintaxe do JSF, e adivinhar um deles falha em silencio.
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


def conferir_redirecionamento(partida: str, chegada: str) -> None:
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
    if not para.path.endswith(SUFIXO_CONSULTA_PUBLICA):
        raise ConsultaPJeIndisponivel(
            f"O portal levou a outra tela ({para.path}), e nao a consulta publica. "
            "Nada foi preenchido.")


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
