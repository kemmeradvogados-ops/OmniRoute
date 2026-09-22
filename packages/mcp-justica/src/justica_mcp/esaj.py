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
