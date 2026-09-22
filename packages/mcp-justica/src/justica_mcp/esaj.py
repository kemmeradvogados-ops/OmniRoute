"""Consulta de processo no e-SAJ do Tribunal de Justica de Sao Paulo.

Conferido em campo em 21 de setembro de 2026, com a sessao autenticada.

O e-SAJ nao tem a barra de busca rapida do eproc. Tem duas telas de consulta,
uma por grau, e elas pedem o numero PARTIDO em dois campos, como os proprios
rotulos dizem: "Informe os treze primeiros digitos" e "Informe os quatro
ultimos digitos". Os treze primeiros sao sequencial, digito verificador e ano;
os quatro ultimos sao a unidade de origem. O trecho `J.TR` fica num campo
desabilitado, porque o portal ja sabe que tribunal e.

Qual das duas telas usar sai do proprio numero, pelo grau (origem `0000` e
segundo grau). Consultar no grau errado devolve "nao encontrado", que se
confunde com processo inexistente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .core.cnj import NumeroCNJ


@dataclass(frozen=True)
class TelaConsulta:
    grau: int
    url: str
    campo_numero: str
    campo_origem: str
    radio_unificado: str
    botao_consultar: str
    formulario: str


# Os dois graus tem formulario e botao com nomes diferentes, e so isso: os
# campos do numero se chamam igual nos dois.
PRIMEIRO_GRAU = TelaConsulta(
    grau=1,
    url="https://esaj.tjsp.jus.br/cpopg/open.do",
    campo_numero="#numeroDigitoAnoUnificado",
    campo_origem="#foroNumeroUnificado",
    radio_unificado="#radioNumeroUnificado",
    botao_consultar="#botaoConsultarProcessos",
    formulario="formConsulta",
)

SEGUNDO_GRAU = TelaConsulta(
    grau=2,
    url="https://esaj.tjsp.jus.br/cposg/open.do",
    campo_numero="#numeroDigitoAnoUnificado",
    campo_origem="#foroNumeroUnificado",
    radio_unificado="#radioNumeroUnificado",
    botao_consultar="#pbConsultar",
    formulario="formularioConsulta",
)


def tela_para(numero: NumeroCNJ) -> TelaConsulta:
    """A tela sai do grau, e o grau sai do numero. Ninguem precisa informar."""
    return SEGUNDO_GRAU if numero.grau == 2 else PRIMEIRO_GRAU


def partes_do_numero(numero: NumeroCNJ) -> tuple[str, str]:
    """Devolve (treze primeiros, quatro ultimos), no formato que o campo mostra.

    O campo tem mascara. Preencher com digitos crus deixaria o valor sem os
    separadores que a mascara produziria, e o portal recusa ou busca errado.
    Por isso vai formatado, e quem chama confere o que ficou no campo.
    """
    treze = f"{numero.sequencial}-{numero.digito_verificador}.{numero.ano}"
    return treze, numero.origem


class ConsultaESAJIndisponivel(RuntimeError):
    pass


def buscar(pagina: Any, guarda: Any, numero: NumeroCNJ, segundos: int) -> TelaConsulta:
    """Abre a tela do grau certo, preenche o numero e consulta.

    Toda a autorizacao e estreita de proposito: vale para a tela de consulta
    daquele grau, libera os dois campos do numero e o botao Consultar, e nada
    mais. A tela tem links de peticionamento e de certidao ao lado; nenhum
    deles entra na lista.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (
        _assentar, elemento_visivel, permissao_de_origem, permissao_efemera,
    )

    tela = tela_para(numero)
    treze, quatro = partes_do_numero(numero)

    # A tela de consulta e outro caminho do MESMO portal onde a sessao foi
    # aberta. Sem esta autorizacao a trava barra a navegacao, e barra com razao:
    # o padrao e negar. A de origem libera navegar dentro do portal e NADA mais,
    # nenhum clique, nenhum preenchimento; esses vem da permissao estreita
    # acrescentada depois, ja na tela certa.
    guarda.permissoes.append(permissao_de_origem(
        pagina.url, "telas de consulta do mesmo portal"
    ))
    guarda.avaliar(Acao.NAVEGAR, tela.url, url=tela.url).exigir()
    pagina.goto(tela.url, timeout=segundos * 1000, wait_until="domcontentloaded")
    _assentar(pagina, segundos)

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao=f"consulta de processo no e-SAJ, {tela.grau}o grau",
        conferido_em="execucao atual",
        seletores_clicaveis=(tela.botao_consultar,),
        seletores_preenchiveis=(tela.campo_numero, tela.campo_origem),
    ))

    for seletor, valor, rotulo in (
        (tela.campo_numero, treze, "treze primeiros digitos"),
        (tela.campo_origem, quatro, "quatro ultimos digitos"),
    ):
        campo = elemento_visivel(pagina, seletor)
        if campo is None:
            raise ConsultaESAJIndisponivel(
                f"Campo de {rotulo} nao encontrado ({seletor}). A tela mudou; "
                "rode o reconhecimento de novo antes de insistir."
            )
        guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
        campo.click()
        campo.fill(valor)
        # O campo tem mascara: preencher nao garante que o valor ficou. Conferir
        # evita consultar numero diferente do pedido, que devolveria o processo
        # errado sem nada indicar o engano.
        ficou = campo.evaluate("e => e.value || ''")
        if ficou.replace(" ", "") != valor.replace(" ", ""):
            raise ConsultaESAJIndisponivel(
                f"O campo de {rotulo} ficou com {ficou!r} em vez de {valor!r}. "
                "Nada foi consultado, para nao buscar processo errado."
            )

    guarda.pode_executar(Acao.CLICAR, tela.botao_consultar, url=pagina.url)
    botao = elemento_visivel(pagina, tela.botao_consultar)
    if botao is None:
        raise ConsultaESAJIndisponivel(
            f"Botao Consultar nao encontrado ({tela.botao_consultar})."
        )
    botao.click()
    try:
        pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
    except Exception:
        pass
    _assentar(pagina, segundos)
    return tela


# Identificadores conferidos em campo em 22 de setembro de 2026, na pagina do
# processo do primeiro grau. Cada um foi visto no relato de estrutura, nenhum
# foi suposto.
DADOS_PRINCIPAIS = {
    "numero": "#numeroProcesso",
    "classe": "#classeProcesso",
    "assunto": "#assuntoProcesso",
    "foro": "#foroProcesso",
    "vara": "#varaProcesso",
    "juiz": "#juizProcesso",
    "distribuicao": "#dataHoraDistribuicaoProcesso",
    "controle": "#numeroControleProcesso",
    "area": "#areaProcesso",
    "valor_da_acao": "#valorAcaoProcesso",
}

TABELA_TODAS_PARTES = "#tableTodasPartes"
TABELA_PARTES_PRINCIPAIS = "#tablePartesPrincipais"
CONTAINER_MOVIMENTACOES = "#containerMovimentacoes"
LINK_EXPANDIR_MOVIMENTACOES = "#btnExibirMovimentacoes"
LINK_PASTA_DIGITAL = "#linkPasta"


def _texto(pagina: Any, seletor: str) -> Optional[str]:
    """Texto de um elemento, ou None. Nunca levanta: pagina de processo varia.

    Processo de execucao fiscal tem tabela de certidao de divida ativa que
    processo de conhecimento nao tem; processo sem juiz designado nao tem o
    campo do juiz. Faltar e normal, e faltar nao pode derrubar a extracao do
    resto.
    """
    try:
        el = pagina.query_selector(seletor)
        if el is None:
            return None
        return " ".join((el.inner_text() or "").split()) or None
    except Exception:
        return None


def extrair_dados_principais(pagina: Any) -> dict[str, Optional[str]]:
    return {nome: _texto(pagina, seletor) for nome, seletor in DADOS_PRINCIPAIS.items()}


def extrair_partes(pagina: Any) -> list[dict[str, str]]:
    """Partes do processo, da tabela completa quando ela existe.

    O e-SAJ mostra duas: as principais e todas. A completa e superconjunto da
    outra, entao usa-la evita perder o polo passivo de processo com varias
    partes. Sem ela, cai na de principais em vez de devolver nada.

    Cada linha tem duas colunas: o polo e o nome, e o nome vem com os
    advogados no mesmo bloco, separados por quebra de linha.
    """
    for seletor in (TABELA_TODAS_PARTES, TABELA_PARTES_PRINCIPAIS):
        try:
            tabela = pagina.query_selector(seletor)
        except Exception:
            tabela = None
        if tabela is None:
            continue
        partes: list[dict[str, str]] = []
        try:
            linhas = tabela.query_selector_all("tr")
        except Exception:
            continue
        for linha in linhas:
            try:
                celulas = linha.query_selector_all("td")
            except Exception:
                continue
            if len(celulas) < 2:
                continue
            polo = " ".join((celulas[0].inner_text() or "").split()).rstrip(":")
            bruto = (celulas[1].inner_text() or "").strip()
            if not bruto:
                continue
            pedacos = [p.strip() for p in bruto.splitlines() if p.strip()]
            partes.append({
                "polo": polo,
                "nome": pedacos[0] if pedacos else "",
                # Advogados vem no mesmo bloco, depois do nome. Guardar cru
                # evita inventar estrutura que a pagina nao declara.
                "representantes": pedacos[1:],
            })
        if partes:
            return partes
    return []


def extrair_movimentacoes(pagina: Any) -> list[dict[str, str]]:
    """Movimentacoes, na ordem em que a pagina as mostra.

    A tabela nao tem identificador proprio: vive dentro de
    `div#containerMovimentacoes`. Ancorar no container, e nao na tabela, e o que
    torna a leitura possivel sem inventar seletor.
    """
    try:
        container = pagina.query_selector(CONTAINER_MOVIMENTACOES)
    except Exception:
        return []
    if container is None:
        return []
    movimentacoes: list[dict[str, str]] = []
    try:
        linhas = container.query_selector_all("tr")
    except Exception:
        return []
    for linha in linhas:
        try:
            celulas = linha.query_selector_all("td")
        except Exception:
            continue
        if len(celulas) < 2:
            continue
        data = " ".join((celulas[0].inner_text() or "").split())
        # A ultima celula e a descricao; as do meio sao vazias ou decorativas na
        # pagina conferida, e depender do indice 2 quebraria em tabela de tres
        # colunas.
        descricao = " ".join((celulas[-1].inner_text() or "").split())
        if not data and not descricao:
            continue
        movimentacoes.append({"data": data, "descricao": descricao})
    return movimentacoes


def lista_de_movimentacoes_esta_completa(pagina: Any) -> bool:
    """Falso quando a pagina ainda oferece "exibir mais movimentacoes".

    O e-SAJ mostra so as ultimas e guarda o resto atras de um link. Entregar a
    lista parcial como se fosse completa faria o advogado concluir que nao ha
    andamento anterior, que e pior que nao entregar nada.
    """
    try:
        return pagina.query_selector(LINK_EXPANDIR_MOVIMENTACOES) is None
    except Exception:
        return True


def link_da_pasta_digital(pagina: Any) -> Optional[str]:
    """Endereco da integra. Ao contrario do eproc, aqui ela tem endereco
    proprio, entao a copia nao precisa de clique."""
    try:
        el = pagina.query_selector(LINK_PASTA_DIGITAL)
        return el.get_attribute("href") if el is not None else None
    except Exception:
        return None


def extrair(pagina: Any) -> dict[str, Any]:
    movimentacoes = extrair_movimentacoes(pagina)
    return {
        "principais": extrair_dados_principais(pagina),
        "partes": extrair_partes(pagina),
        "movimentacoes": movimentacoes,
        "movimentacoes_completas": lista_de_movimentacoes_esta_completa(pagina),
        "pasta_digital": link_da_pasta_digital(pagina),
        "totais": {
            "partes": len(extrair_partes(pagina)),
            "movimentacoes": len(movimentacoes),
        },
    }
