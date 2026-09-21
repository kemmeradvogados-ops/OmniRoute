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

from .core.cofre import Cofre, CredencialAusente, Identidade
from .core.estado import Estado
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




def ensaiar_login(
    url: str,
    tribunal: str,
    sistema: str,
    *,
    campo_usuario: str = "#txtUsuario",
    campo_senha: str = "#pwdSenha",
    campo_senha_oculto: str = "input[name=pwdSenha]",
    oculto: bool = False,
    segundos: int = 30,
    cofre: Optional[Cofre] = None,
) -> int:
    """Preenche o formulario de login e CONFERE o efeito, sem enviar.

    Por que nao envia: se o preenchimento programatico nao funcionar e o codigo
    clicar em Entrar assim mesmo, isso conta como tentativa de login falha, e
    tentativas repetidas bloqueiam a conta do advogado. O risco nao e uma
    mensagem de erro, e sim perder o acesso.

    O motivo da duvida esta na propria pagina: o campo visivel do eproc traz
    `inputmode=none`, que suprime o teclado do dispositivo. E a assinatura de
    portal com teclado virtual, onde o valor talvez so se forme a partir de
    cliques na tela. Se for esse o caso, preencher nao surte efeito, e este
    ensaio revela isso sem custo nenhum.

    A conferencia e feita lendo de volta o campo OCULTO, que e o efetivamente
    enviado. Nenhum valor de credencial e impresso: so o comprimento.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    identidade = Identidade(tribunal, sistema)
    cofre = cofre or Cofre()
    try:
        login = cofre._login(identidade)
        senha = cofre._senha(identidade)
    except CredencialAusente as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

    # A tela recebe permissao de PREENCHIMENTO nos dois campos, e nenhuma
    # permissao de clique. Assim, mesmo que o codigo tentasse enviar por
    # engano, a trava barraria: a impossibilidade nao depende de eu lembrar.
    permissao = permissao_efemera(url)
    permissao = Permissao(
        padrao_url=permissao.padrao_url,
        descricao="tela de login, ensaio de preenchimento sem envio",
        conferido_em="execucao atual",
        seletores_clicaveis=(),
        seletores_preenchiveis=(campo_usuario, campo_senha),
    )
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[permissao])

    print("=" * LARGURA)
    print("ENSAIO DE LOGIN".center(LARGURA))
    print("=" * LARGURA)
    print(f"Endereco: {url}")
    print(f"Credencial: {identidade.rotulo} (lida do cofre, nunca impressa)")
    print("Preenche e CONFERE o efeito. NAO clica em Entrar, NAO autentica.\n")

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
            guarda.pode_executar(Acao.NAVEGAR, url)
            pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")

            botoes_antes = len(pagina.query_selector_all("button, input[type=button]"))

            for seletor, valor, rotulo in (
                (campo_usuario, login, "usuario"),
                (campo_senha, senha, "senha"),
            ):
                elemento = pagina.query_selector(seletor)
                if elemento is None:
                    print(f"  [FALHA] Campo de {rotulo} nao encontrado: {seletor}")
                    print("          A pagina mudou. Rode `reconhecer` de novo.")
                    return 1
                guarda.pode_executar(Acao.PREENCHER, seletor, url=url)
                elemento.click()          # foco, dentro da tela autorizada
                elemento.fill(valor)
                print(f"  Preenchido o campo de {rotulo} ({seletor}).")

            print()
            # Conferencia: o campo oculto e o que viaja no envio.
            oculto_el = pagina.query_selector(campo_senha_oculto)
            visivel_el = pagina.query_selector(campo_senha)
            tam_oculto = oculto_el.evaluate("e => (e.value || '').length") if oculto_el else None
            tam_visivel = visivel_el.evaluate("e => (e.value || '').length") if visivel_el else None
            esperado = len(senha)

            print("  CONFERENCIA (comprimentos, nunca o conteudo):")
            print(f"    senha no cofre           : {esperado} caracteres")
            print(f"    campo visivel  ({campo_senha}) : {tam_visivel}")
            print(f"    campo oculto   (enviado) : {tam_oculto}")

            if tam_oculto == esperado:
                veredito = "O valor CHEGOU ao campo enviado. O login programatico deve funcionar."
                proximo = "Proximo passo: clicar em Entrar e reconhecer a tela seguinte."
            elif tam_visivel == esperado and not tam_oculto:
                veredito = (
                    "O valor ficou SO no campo visivel e nao passou para o enviado. "
                    "E o comportamento esperado quando a pagina monta o valor a partir "
                    "de teclado virtual, ou quando o espelhamento depende de eventos "
                    "de digitacao que o preenchimento direto nao dispara."
                )
                proximo = (
                    "Proximo passo: digitar tecla a tecla em vez de preencher de uma "
                    "vez, e conferir de novo. NAO clicar em Entrar ate o valor chegar."
                )
            else:
                veredito = "Resultado inesperado; nao da para concluir."
                proximo = "Nao clicar em Entrar. Me mande este relatorio."

            print(f"\n  VEREDITO: {veredito}")
            print(f"  {proximo}")

            botoes_depois = len(pagina.query_selector_all("button, input[type=button]"))
            if botoes_depois > botoes_antes:
                print(f"\n  ATENCAO: apareceram {botoes_depois - botoes_antes} botoes novos apos")
                print("  o foco no campo. Indicio forte de teclado virtual na tela.")

            print("\n  RELATO DA TRAVA:")
            for linha in guarda.relato():
                print(f"    {linha}")
        finally:
            navegador.close()

    print("\n" + "=" * LARGURA)
    print("  NADA foi enviado. Nenhuma tentativa de login foi registrada no portal.")
    print("  Cole este relatorio para eu decidir o passo seguinte.")
    return 0




# Pistas de que um campo pede o codigo de seis digitos do autenticador.
_PISTAS_SEGUNDO_FATOR = ("one-time-code", "otp", "token", "codigo", "código", "2fa", "duplo")


def _parece_segundo_fator(campo: "Campo") -> bool:
    # Caixa de selecao e botao de opcao nunca sao campo de codigo. Sem esta
    # linha, a caixa "Nao usar o 2FA neste dispositivo" do eproc era apontada
    # como campo do autenticador, que e o oposto do que ela faz.
    if campo.tipo in ("checkbox", "radio"):
        return False
    texto = " ".join(
        str(v).lower() for v in
        (campo.nome, campo.identificador, campo.rotulo, (campo.extras or {}).get("autocomplete"))
        if v
    )
    if any(p in texto for p in _PISTAS_SEGUNDO_FATOR):
        return True
    tamanho = (campo.extras or {}).get("maxlength")
    return tamanho in ("4", "6", "8")


def _mensagens_de_erro(pagina: Any) -> list[str]:
    saida = []
    for seletor in (".alert", ".erro", ".error", "[role=alert]", ".infraAviso", ".msgErro"):
        for elemento in pagina.query_selector_all(seletor):
            if not elemento.is_visible():
                continue
            texto = re.sub(r"\s+", " ", (elemento.inner_text() or "")).strip()
            if texto:
                saida.append(texto[:160])
    return saida


def entrar(
    url: str,
    tribunal: str,
    sistema: str,
    *,
    confirmado: bool = False,
    campo_usuario: str = "#txtUsuario",
    campo_senha: str = "#pwdSenha",
    campo_senha_oculto: str = "input[name=pwdSenha]",
    botao_entrar: str = "#sbmEntrar",
    oculto: bool = False,
    segundos: int = 45,
    cofre: Optional[Cofre] = None,
    estado: Optional[Estado] = None,
) -> int:
    """Envia o login UMA vez e relata a tela seguinte. Nao passa disso.

    Primeiro comando do projeto que pratica um ato no portal. Duas travas, pelo
    mesmo motivo: tentativa de login falha repetida bloqueia a conta do
    advogado.

    1. Exige confirmacao explicita do operador na linha de comando.
    2. Clica UMA vez. Nao ha repeticao, nem em caso de falha. Se falhar, para e
       relata; a decisao de tentar de novo e do advogado, nunca do codigo.

    Depois do envio apenas LE a tela seguinte. Nao preenche o codigo do segundo
    fator, nao navega para lugar nenhum, nao baixa nada.
    """
    if not confirmado:
        print(
            "Este comando ENVIA uma tentativa de login real ao portal.\n\n"
            "Tentativas falhas repetidas bloqueiam a conta do advogado, entao ele\n"
            "so roda com confirmacao expressa, e clica uma unica vez:\n\n"
            "    --confirmo-tentativa-unica\n",
            file=sys.stderr,
        )
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    identidade = Identidade(tribunal, sistema)
    cofre = cofre or Cofre()
    estado = estado or Estado()
    try:
        login = cofre._login(identidade)
        senha = cofre._senha(identidade)
    except CredencialAusente as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

    base = permissao_efemera(url)
    permissao = Permissao(
        padrao_url=base.padrao_url,
        descricao="tela de login, envio unico autorizado pelo operador",
        conferido_em="execucao atual",
        seletores_clicaveis=(botao_entrar,),
        seletores_preenchiveis=(campo_usuario, campo_senha),
    )
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[permissao])

    print("=" * LARGURA)
    print("ENVIO UNICO DE LOGIN".center(LARGURA))
    print("=" * LARGURA)
    print(f"Endereco: {url}")
    print(f"Credencial: {identidade.rotulo} (lida do cofre, nunca impressa)")
    print("Clica UMA vez e le a tela seguinte. Sem repeticao, sem segundo fator.\n")

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
            guarda.pode_executar(Acao.NAVEGAR, url)
            pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")

            for seletor, valor, rotulo in (
                (campo_usuario, login, "usuario"), (campo_senha, senha, "senha"),
            ):
                elemento = pagina.query_selector(seletor)
                if elemento is None:
                    print(f"  [FALHA] Campo de {rotulo} nao encontrado: {seletor}.")
                    print("          Nada foi enviado. Rode `reconhecer` de novo.")
                    return 1
                guarda.pode_executar(Acao.PREENCHER, seletor, url=url)
                elemento.click()
                elemento.fill(valor)

            # Conferencia ANTES de enviar: sem isso o clique viraria tentativa
            # falha por campo vazio, que e justamente o que bloqueia a conta.
            alvo = pagina.query_selector(campo_senha_oculto)
            if not alvo or alvo.evaluate("e => (e.value || '').length") != len(senha):
                print("  [ABORTADO] A senha nao chegou ao campo enviado.")
                print("             NADA foi enviado, para nao gerar tentativa falha.")
                return 1
            print("  Campos preenchidos e conferidos.")

            botao = pagina.query_selector(botao_entrar)
            if botao is None:
                print(f"  [FALHA] Botao {botao_entrar} nao encontrado. Nada enviado.")
                return 1

            guarda.pode_executar(Acao.CLICAR, botao_entrar, url=url)
            estado.registrar(
                acao="login_tentativa_unica", tribunal=identidade.tribunal,
                sistema=identidade.sistema, resultado="enviado",
                detalhe="clique unico autorizado pelo operador",
            )
            print("  >>> ENVIANDO (uma unica vez) <<<\n")
            botao.click()
            try:
                pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
            except Exception:
                pass

            final = pagina.url
            print(f"  Endereco apos o envio: {final}")
            print(f"  Titulo: {pagina.title()!r}\n")

            erros = _mensagens_de_erro(pagina)
            if erros:
                print("  MENSAGENS NA TELA:")
                for e in erros:
                    print(f"    {e}")
                print("\n  Se indicar credencial invalida, NAO repita o comando.")
                print("  Confira a senha no cofre antes de qualquer nova tentativa.\n")

            termo = guarda._termo_de_risco(final)
            if termo is not None:
                print(f"  TRAVA: o destino contem o termo de risco {termo!r}.")
                print("  A leitura foi interrompida. Informe este endereco.")
                estado.registrar(
                    acao="login_tentativa_unica", tribunal=identidade.tribunal,
                    sistema=identidade.sistema, resultado="destino_bloqueado", detalhe=termo,
                )
                return 1

            campos, botoes = _coletar(pagina)
            print(f"  CAMPOS NA TELA SEGUINTE ({len(campos)}):")
            for c in campos:
                marca = "  <-- PARECE SER O CODIGO DO AUTENTICADOR" if _parece_segundo_fator(c) else ""
                print(f"    {c.linha()}{marca}")

            print(f"\n  BOTOES ({len(botoes)}):")
            for b in botoes:
                print(f"    {b.linha()}")

            candidatos = [c for c in campos if _parece_segundo_fator(c) and c.na_tela]
            print()
            if candidatos:
                print(f"  Encontrado(s) {len(candidatos)} campo(s) com cara de segundo fator.")
                print("  Proximo passo: preencher o codigo gerado pelo cofre.")
            elif erros:
                print("  Nenhum campo de segundo fator, e ha mensagem de erro na tela:")
                print("  o envio provavelmente nao passou da autenticacao.")
            else:
                print("  Nenhum campo com cara de segundo fator. Ou o portal nao pediu")
                print("  nesta sessao, ou a tela seguinte e outra. Veja o titulo acima.")

            print("\n  RELATO DA TRAVA:")
            for linha in guarda.relato():
                print(f"    {linha}")
        finally:
            navegador.close()

    print("\n" + "=" * LARGURA)
    print("  Uma tentativa, e so uma. O comando nao repete em nenhuma hipotese.")
    print("  Nenhum codigo de segundo fator foi digitado. Nada foi baixado.")
    return 0




def autenticar(
    url: str,
    tribunal: str,
    sistema: str,
    *,
    confirmado: bool = False,
    campo_usuario: str = "#txtUsuario",
    campo_senha: str = "#pwdSenha",
    campo_senha_oculto: str = "input[name=pwdSenha]",
    botao_entrar: str = "#sbmEntrar",
    campo_codigo: str = "#txtAcessoCodigo",
    botao_validar: str = "#btnValidar",
    oculto: bool = False,
    segundos: int = 45,
    cofre: Optional[Cofre] = None,
    estado: Optional[Estado] = None,
) -> int:
    """Autenticacao completa: credencial, segundo fator, e para por ali.

    A tela do segundo fator so existe dentro da sessao aberta pelo login, entao
    os dois passos ocorrem numa execucao so.

    Mesma disciplina do envio unico, agora em dois pontos: UMA tentativa de
    credencial e UMA de codigo. Codigo errado tambem conta como tentativa falha.

    Nunca marca a caixa "Nao usar o 2FA neste dispositivo". Marca-la facilitaria
    as proximas execucoes, e e exatamente por isso que nao se marca: o cofre ja
    gera o codigo sozinho, entao nao ha ganho, so perda de protecao da conta.
    Os botoes "Desativar 2FA" e "Cancelar Dispositivos Liberados", que dividem a
    mesma tela, ficam barrados pela lista de permissao e pelos termos de risco.

    Ao final apenas LE a tela onde parou. Nao navega, nao baixa, nao abre nada.
    """
    if not confirmado:
        print(
            "Este comando AUTENTICA de verdade no portal: envia a credencial e o\n"
            "codigo do segundo fator.\n\n"
            "Tentativas falhas repetidas bloqueiam a conta do advogado, entao ele\n"
            "so roda com confirmacao expressa, e tenta uma unica vez em cada etapa:\n\n"
            "    --confirmo-tentativa-unica\n",
            file=sys.stderr,
        )
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    identidade = Identidade(tribunal, sistema)
    cofre = cofre or Cofre()
    estado = estado or Estado()
    try:
        login = cofre._login(identidade)
        senha = cofre._senha(identidade)
    except CredencialAusente as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1
    if not cofre.tem_semente(identidade):
        print(f"  Sem semente de segundo fator para {identidade.rotulo}.", file=sys.stderr)
        print("  Grave com: justica-credenciais guardar --so-semente", file=sys.stderr)
        return 1

    base = permissao_efemera(url)
    permissao = Permissao(
        padrao_url=base.padrao_url,
        descricao="autenticacao completa autorizada pelo operador",
        conferido_em="execucao atual",
        # Apenas o necessario. A caixa de liberar dispositivo e os botoes de
        # desativar ficam de fora de proposito.
        seletores_clicaveis=(botao_entrar, botao_validar),
        seletores_preenchiveis=(campo_usuario, campo_senha, campo_codigo),
    )
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[permissao])

    print("=" * LARGURA)
    print("AUTENTICACAO COMPLETA".center(LARGURA))
    print("=" * LARGURA)
    print(f"Endereco: {url}")
    print(f"Credencial: {identidade.rotulo} (lida do cofre, nunca impressa)")
    print("Uma tentativa de credencial e uma de codigo. Nao marca dispositivo confiavel.\n")

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
            guarda.pode_executar(Acao.NAVEGAR, url)
            pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")

            # ---------- etapa 1: credencial ----------
            for seletor, valor, rotulo in (
                (campo_usuario, login, "usuario"), (campo_senha, senha, "senha"),
            ):
                elemento = pagina.query_selector(seletor)
                if elemento is None:
                    print(f"  [FALHA] Campo de {rotulo} nao encontrado. Nada enviado.")
                    return 1
                guarda.pode_executar(Acao.PREENCHER, seletor, url=url)
                elemento.click()
                elemento.fill(valor)

            alvo = pagina.query_selector(campo_senha_oculto)
            if not alvo or alvo.evaluate("e => (e.value || '').length") != len(senha):
                print("  [ABORTADO] A senha nao chegou ao campo enviado. Nada enviado.")
                return 1

            guarda.pode_executar(Acao.CLICAR, botao_entrar, url=url)
            estado.registrar(acao="login_etapa_credencial", tribunal=identidade.tribunal,
                             sistema=identidade.sistema, resultado="enviado")
            print("  Etapa 1: credencial enviada (uma vez).")
            pagina.query_selector(botao_entrar).click()
            try:
                pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
            except Exception:
                pass

            erros = _mensagens_de_erro(pagina)
            campo = pagina.query_selector(campo_codigo)
            if campo is None:
                print("\n  [PARADO] A tela do segundo fator nao apareceu.")
                if erros:
                    print("  Mensagens na tela:")
                    for e in erros:
                        print(f"    {e}")
                    print("\n  NAO repita o comando. Confira a credencial no cofre.")
                estado.registrar(acao="login_etapa_credencial", tribunal=identidade.tribunal,
                                 sistema=identidade.sistema, resultado="sem_tela_de_codigo")
                return 1

            # ---------- etapa 2: segundo fator ----------
            # Exige janela util: codigo gerado no fim da validade expira entre o
            # preenchimento e o envio, e o portal registra falha por um motivo
            # que nao e culpa da credencial.
            restante = cofre.segundos_restantes_do_codigo()
            if restante < 8:
                print(f"  Codigo atual expira em {restante}s; aguardando a proxima janela.")
            codigo = cofre._codigo_segundo_fator(identidade, minimo_segundos=8)

            guarda.pode_executar(Acao.PREENCHER, campo_codigo, url=url)
            campo.click()
            campo.fill(codigo)
            conferido = campo.evaluate("e => (e.value || '').length")
            if conferido != len(codigo):
                print(f"  [ABORTADO] O codigo nao entrou no campo ({conferido} de {len(codigo)}).")
                print("             Nada foi enviado, para nao gastar tentativa.")
                return 1
            print(f"  Etapa 2: codigo preenchido, valido por mais "
                  f"{cofre.segundos_restantes_do_codigo()}s.")

            guarda.pode_executar(Acao.CLICAR, botao_validar, url=url)
            estado.registrar(acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                             sistema=identidade.sistema, resultado="enviado")
            pagina.query_selector(botao_validar).click()
            try:
                pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
            except Exception:
                pass

            # ---------- resultado ----------
            final = pagina.url
            print(f"\n  Endereco final: {final}")
            print(f"  Titulo: {pagina.title()!r}\n")

            erros = _mensagens_de_erro(pagina)
            if erros:
                print("  MENSAGENS NA TELA:")
                for e in erros:
                    print(f"    {e}")
                print()

            ainda_pede_codigo = pagina.query_selector(campo_codigo) is not None
            if ainda_pede_codigo:
                print("  A tela ainda pede o codigo: a validacao NAO passou.")
                print("  NAO repita o comando. Confira a semente com:")
                print("    justica-credenciais testar --tribunal "
                      f"{identidade.tribunal} --sistema {identidade.sistema}")
                estado.registrar(acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                                 sistema=identidade.sistema, resultado="recusado")
            else:
                print("  AUTENTICADO. A sessao esta aberta neste navegador.")
                estado.registrar(acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                                 sistema=identidade.sistema, resultado="autenticado")

            termo = guarda._termo_de_risco(final)
            if termo is not None:
                print(f"\n  TRAVA: o endereco final contem o termo de risco {termo!r}.")
                print("  A leitura da tela foi interrompida.")
                return 0

            campos, botoes = _coletar(pagina)
            print(f"\n  ESTRUTURA DA TELA ONDE PAROU ({len(campos)} campos, {len(botoes)} botoes):")
            for c in campos[:15]:
                print(f"    {c.linha()}")
            for b in botoes[:20]:
                print(f"    {b.linha()}")

            print("\n  RELATO DA TRAVA:")
            for linha in guarda.relato():
                print(f"    {linha}")
        finally:
            navegador.close()

    print("\n" + "=" * LARGURA)
    print("  Uma tentativa em cada etapa. Nada foi repetido.")
    print("  A caixa de dispositivo confiavel NAO foi marcada.")
    print("  Nada foi navegado, aberto ou baixado alem da tela de chegada.")
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

    e = sub.add_parser(
        "ensaiar-login",
        help="preenche o formulario e confere o efeito, SEM clicar em Entrar",
    )
    e.add_argument("--url", required=True, help="endereco da tela de login")
    e.add_argument("--tribunal", required=True, help="por exemplo TRF2")
    e.add_argument("--sistema", required=True, help="por exemplo eproc")
    e.add_argument("--campo-usuario", default="#txtUsuario")
    e.add_argument("--campo-senha", default="#pwdSenha")
    e.add_argument("--campo-senha-oculto", default="input[name=pwdSenha]")
    e.add_argument("--oculto", action="store_true")
    e.add_argument("--segundos", type=int, default=30)

    t = sub.add_parser("entrar", help="envia o login UMA vez e le a tela seguinte")
    t.add_argument("--url", required=True)
    t.add_argument("--tribunal", required=True)
    t.add_argument("--sistema", required=True)
    t.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado",
                   help="confirma que autoriza UMA tentativa de login real")
    t.add_argument("--campo-usuario", default="#txtUsuario")
    t.add_argument("--campo-senha", default="#pwdSenha")
    t.add_argument("--campo-senha-oculto", default="input[name=pwdSenha]")
    t.add_argument("--botao-entrar", default="#sbmEntrar")
    t.add_argument("--oculto", action="store_true")
    t.add_argument("--segundos", type=int, default=45)

    a = sub.add_parser("autenticar", help="credencial e segundo fator, numa sessao so")
    a.add_argument("--url", required=True)
    a.add_argument("--tribunal", required=True)
    a.add_argument("--sistema", required=True)
    a.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado")
    a.add_argument("--campo-codigo", default="#txtAcessoCodigo")
    a.add_argument("--botao-validar", default="#btnValidar")
    a.add_argument("--oculto", action="store_true")
    a.add_argument("--segundos", type=int, default=45)

    args = p.parse_args(argv)

    try:
        if args.comando == "reconhecer":
            return reconhecer(args.url, oculto=args.oculto, segundos=args.segundos)
        if args.comando == "autenticar":
            return autenticar(
                args.url, args.tribunal, args.sistema, confirmado=args.confirmado,
                campo_codigo=args.campo_codigo, botao_validar=args.botao_validar,
                oculto=args.oculto, segundos=args.segundos,
            )
        if args.comando == "entrar":
            return entrar(
                args.url, args.tribunal, args.sistema, confirmado=args.confirmado,
                campo_usuario=args.campo_usuario, campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto, botao_entrar=args.botao_entrar,
                oculto=args.oculto, segundos=args.segundos,
            )
        if args.comando == "ensaiar-login":
            return ensaiar_login(
                args.url, args.tribunal, args.sistema,
                campo_usuario=args.campo_usuario,
                campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto,
                oculto=args.oculto, segundos=args.segundos,
            )
    except PortalIndisponivel as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
