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
