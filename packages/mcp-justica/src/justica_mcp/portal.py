"""Reconhecimento de portal: descobre a estrutura da pagina sem tocar nela.

Primeiro passo do acesso autenticado, e deliberadamente o mais timido possivel.
Abre um endereco, LE a estrutura da pagina e relata. Nao preenche campo, nao
clica em botao, nao autentica, nao baixa nada.

Existe porque escrevi os adaptadores de API as cegas e o tribunal corrigiu
minhas suposicoes. Aqui o risco de supor e maior: um clique errado consome
prazo. Entao o codigo primeiro OLHA e relata, e so depois, com a estrutura
confirmada, ganha permissao de agir.

A trava de navegacao vale mesmo aqui. O endereco que o operador digita na linha
de comando e autorizado por ele, explicitamente, e vira uma permissao efemera,
valida so para aquela execucao. Se a pagina redirecionar para outro lugar, ou
se o endereco contiver termo de risco, a trava barra assim mesmo.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

from .core.guarda_navegacao import (
    Acao, GuardaNavegacao, Modo, NavegacaoBloqueada, Permissao,
)

LARGURA = 74

INSTRUCAO_INSTALACAO = (
    "O reconhecimento de portal exige o Playwright, que traz um navegador\n"
    "proprio. Instale com os dois comandos:\n\n"
    '    pip install -e ".[navegador]"\n'
    "    playwright install chromium\n\n"
    "O segundo baixa cerca de 150 MB e so precisa ser feito uma vez."
)


NAVEGADOR_AUSENTE = (
    "O Playwright esta instalado, mas o navegador dele nao. Rode:\n\n"
    "    playwright install chromium\n\n"
    "Baixa cerca de 150 MB, uma vez so. Se a maquina ja tem um Chromium ou\n"
    "Chrome que voce prefere usar, aponte para ele:\n\n"
    '    $env:JUSTICA_CHROMIUM = "C:\\caminho\\para\\chrome.exe"'
)


class PortalIndisponivel(RuntimeError):
    pass


@dataclass
class Campo:
    marcador: str
    tipo: str
    nome: Optional[str]
    identificador: Optional[str]
    rotulo: Optional[str]
    texto_visivel: Optional[str]
    e_senha: bool
    visivel: bool = True
    na_tela: bool = True
    habilitado: bool = True
    formulario: Optional[str] = None
    extras: dict[str, str] = None  # type: ignore[assignment]

    def linha(self) -> str:
        partes = [f"<{self.marcador}>", f"tipo={self.tipo or '-'}"]
        if self.nome:
            partes.append(f"name={self.nome}")
        if self.identificador:
            partes.append(f"id={self.identificador}")
        if self.rotulo:
            partes.append(f"rotulo={self.rotulo!r}")
        if self.texto_visivel:
            partes.append(f"texto={self.texto_visivel!r}")
        # Visibilidade e o que distingue campo real de campo espelho: dois
        # elementos com o mesmo nome, um visivel e outro nao, sao um par de
        # exibicao e armazenamento, e preencher o errado quebra em silencio.
        if not self.visivel:
            partes.append("OCULTO")
        elif not self.na_tela:
            # Campo com caixa, porem posicionado fora da area visivel. E o
            # padrao classico de campo espelho: o advogado digita num, o script
            # da pagina copia para o outro. Preencher o errado falha calado.
            partes.append("FORA DA TELA (provavel campo espelho)")
        else:
            partes.append("na tela")
        if not self.habilitado:
            partes.append("desabilitado")
        if self.formulario:
            partes.append(f"form={self.formulario}")
        if self.e_senha:
            partes.append("** SENHA **")
        for chave, valor in (self.extras or {}).items():
            partes.append(f"{chave}={valor}")
        return "  ".join(partes)


def permissao_efemera(url: str) -> Permissao:
    """Autoriza apenas o endereco que o operador digitou, nada alem dele.

    Ancorada no esquema, no dominio e no caminho exatos. Uma pagina vizinha do
    mesmo portal NAO fica autorizada por tabela.
    """
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise PortalIndisponivel(
            f"Endereco invalido: {url!r}. Cole o endereco completo da barra do "
            f"navegador, comecando em https://"
        )
    base = f"{partes.scheme}://{partes.netloc}{partes.path}"
    return Permissao(
        padrao_url=f"^{re.escape(base)}",
        descricao="endereco informado na linha de comando pelo operador",
        conferido_em="execucao atual",
    )


def _na_tela(elemento: Any, largura: int, altura: int) -> bool:
    """`is_visible` do Playwright aceita elemento jogado para fora da tela,
    porque so exige caixa nao vazia. Aqui a posicao importa: campo empurrado
    para `left:-9999px` e o padrao de campo espelho, e confundi-lo com o campo
    real faz o preenchimento falhar sem mensagem."""
    caixa = elemento.bounding_box()
    if caixa is None:
        return False
    return not (
        caixa["x"] + caixa["width"] <= 0
        or caixa["y"] + caixa["height"] <= 0
        or caixa["x"] >= largura
        or caixa["y"] >= altura
    )


def _coletar(pagina: Any) -> tuple[list[Campo], list[Campo]]:
    """Le a estrutura do formulario. Somente leitura do DOM."""
    janela = pagina.viewport_size or {"width": 1280, "height": 720}
    largura, altura = janela["width"], janela["height"]
    campos: list[Campo] = []
    for elemento in pagina.query_selector_all("input, select, textarea"):
        marcador = elemento.evaluate("e => e.tagName.toLowerCase()")
        tipo = (elemento.get_attribute("type") or marcador or "").lower()
        # Botoes aparecem na outra lista; repetir aqui so polui.
        if tipo in ("hidden", "button", "submit", "reset", "image"):
            continue

        identificador = elemento.get_attribute("id")
        rotulo = None
        if identificador:
            alvo = pagina.query_selector(f'label[for="{identificador}"]')
            if alvo:
                rotulo = (alvo.inner_text() or "").strip()[:60]

        extras: dict[str, str] = {}
        for atributo in ("maxlength", "autocomplete", "inputmode", "required"):
            valor = elemento.get_attribute(atributo)
            if valor is not None:
                extras[atributo] = valor or "sim"

        campos.append(Campo(
            marcador=marcador,
            tipo=tipo,
            nome=elemento.get_attribute("name"),
            identificador=identificador,
            rotulo=rotulo or elemento.get_attribute("aria-label") or elemento.get_attribute("placeholder"),
            texto_visivel=None,
            e_senha=tipo == "password",
            visivel=elemento.is_visible(),
            na_tela=_na_tela(elemento, largura, altura),
            habilitado=elemento.is_enabled(),
            formulario=elemento.evaluate("e => e.form ? (e.form.id || e.form.name || 'sem-nome') : null"),
            extras=extras,
        ))

    botoes: list[Campo] = []
    for elemento in pagina.query_selector_all(
        "button, input[type=submit], input[type=button], a[role=button]"
    ):
        texto = (elemento.inner_text() or elemento.get_attribute("value") or "").strip()
        botoes.append(Campo(
            marcador=elemento.evaluate("e => e.tagName.toLowerCase()"),
            tipo=(elemento.get_attribute("type") or "").lower(),
            nome=elemento.get_attribute("name"),
            identificador=elemento.get_attribute("id"),
            rotulo=None,
            texto_visivel=texto[:50] or None,
            e_senha=False,
            visivel=elemento.is_visible(),
            na_tela=_na_tela(elemento, largura, altura),
            habilitado=elemento.is_enabled(),
            formulario=elemento.evaluate("e => e.form ? (e.form.id || e.form.name || 'sem-nome') : null"),
            extras={},
        ))
    return campos, botoes


def _formularios(pagina: Any) -> list[str]:
    saida = []
    for f in pagina.query_selector_all("form"):
        saida.append(
            f"id={f.get_attribute('id') or '-'}  name={f.get_attribute('name') or '-'}  "
            f"action={(f.get_attribute('action') or '-')[:70]}  "
            f"method={(f.get_attribute('method') or 'get').lower()}"
        )
    return saida


def _sobreposicoes(pagina: Any) -> list[str]:
    """Janela sobreposta visivel ao carregar precisa ser fechada antes do
    login, e fechar e um clique, que a trava barra por padrao. Melhor saber
    que ela existe agora do que descobrir travando."""
    saida = []
    seletores = (
        "[role=dialog]", ".modal.show", ".modal.in", ".ui-dialog",
        "[aria-modal=true]", ".swal2-container",
    )
    for seletor in seletores:
        for elemento in pagina.query_selector_all(seletor):
            if not elemento.is_visible():
                continue
            texto = re.sub(r"\s+", " ", (elemento.inner_text() or "")).strip()
            saida.append(f"{seletor}: {texto[:110] or '(sem texto)'}")
    return saida


def reconhecer(url: str, *, oculto: bool = False, segundos: int = 30) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    guarda = GuardaNavegacao(modo=Modo.ENSAIO, permissoes=[permissao_efemera(url)])

    print("=" * LARGURA)
    print("RECONHECIMENTO DE PORTAL".center(LARGURA))
    print("=" * LARGURA)
    print(f"Endereco: {url}")
    print("Modo ensaio: le a estrutura e NAO preenche, NAO clica, NAO autentica.\n")

    try:
        guarda.avaliar(Acao.NAVEGAR, url).exigir()
    except NavegacaoBloqueada as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

    # Escape hatch para maquina que ja tem um navegador instalado, ou quando a
    # versao do Playwright nao casa com a do navegador baixado.
    executavel = os.environ.get("JUSTICA_CHROMIUM") or None

    with sync_playwright() as p:
        try:
            navegador = p.chromium.launch(headless=oculto, executable_path=executavel)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                print("\n" + NAVEGADOR_AUSENTE, file=sys.stderr)
                return 2
            raise
        pagina = navegador.new_page()
        try:
            pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")
            final = pagina.url

            if final != url:
                print(f"  A pagina redirecionou para: {final}")
                try:
                    # O destino do redirecionamento tambem passa pela trava.
                    guarda.avaliar(Acao.NAVEGAR, final).exigir()
                    print("  Destino dentro do endereco autorizado.\n")
                except NavegacaoBloqueada as exc:
                    print(f"\n  TRAVA ACIONADA NO REDIRECIONAMENTO: {exc}", file=sys.stderr)
                    print("  Nada foi lido. Informe este endereco de destino.", file=sys.stderr)
                    return 1

            print(f"  Titulo da pagina: {pagina.title()!r}\n")
            campos, botoes = _coletar(pagina)

            formularios = _formularios(pagina)
            print(f"  FORMULARIOS ({len(formularios)}):")
            for f in formularios:
                print(f"    {f}")

            sobreposicoes = _sobreposicoes(pagina)
            if sobreposicoes:
                print(f"\n  JANELAS SOBREPOSTAS VISIVEIS ({len(sobreposicoes)}):")
                for o in sobreposicoes:
                    print(f"    {o}")
                print("    Precisam ser fechadas antes do login, e fechar e um clique.")

            print(f"\n  CAMPOS DE FORMULARIO ({len(campos)}):")
            for c in campos:
                print(f"    {c.linha()}")
            if not campos:
                print("    (nenhum) A pagina talvez monte o formulario por script;")
                print("    tente de novo com --segundos maior.")

            print(f"\n  BOTOES E ACOES ({len(botoes)}):")
            for b in botoes:
                print(f"    {b.linha()}")

            print("\n  RELATO DA TRAVA:")
            for linha in guarda.relato():
                print(f"    {linha}")
        finally:
            navegador.close()

    print("\n" + "=" * LARGURA)
    print("  Nada foi preenchido, clicado ou autenticado.")
    print("  Cole este relatorio para eu escrever o passo de autenticacao.")
    print("  Nenhum dado de processo aparece aqui: so a estrutura da pagina.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="justica-portal",
        description="Le a estrutura de uma pagina de portal sem interagir com ela.",
    )
    sub = p.add_subparsers(dest="comando", required=True)
    r = sub.add_parser("reconhecer", help="abre um endereco e relata a estrutura")
    r.add_argument("--url", required=True, help="endereco completo, copiado da barra do navegador")
    r.add_argument("--oculto", action="store_true",
                   help="nao mostra a janela do navegador (o padrao e mostrar)")
    r.add_argument("--segundos", type=int, default=30, help="tempo limite de carregamento")
    args = p.parse_args(argv)

    try:
        if args.comando == "reconhecer":
            return reconhecer(args.url, oculto=args.oculto, segundos=args.segundos)
    except PortalIndisponivel as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
