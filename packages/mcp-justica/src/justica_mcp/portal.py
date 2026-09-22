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
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

from .core.acesso import PortalNaoConfigurado, config_portal
from .core.cofre import Cofre, CredencialAusente, Identidade
from .core.config import carregar_env
from .core.estado import Estado
from .core.limite_tentativas import (
    ACAO_SUCESSO, LimiteTentativas, TetoDeTentativasAtingido,
)
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


# Tempo que o operador tem para marcar a caixa do desafio. Generoso de
# proposito: e uma pessoa indo ate a janela, nao uma espera de rede.
ESPERA_HUMANA_PADRAO = 180

VARIAVEL_PERFIL_EFEMERO = "JUSTICA_NAVEGADOR_EFEMERO"


def pasta_do_navegador() -> "Path":
    """Perfil persistente do navegador, na pasta de estado.

    Guarda cookie de sessao do portal. Nao e pasta descartavel: quem apagar
    perde a liberacao do desafio e a sessao aberta, e volta a marcar a caixa.
    """
    from pathlib import Path as _P

    from .core.estado import diretorio_estado

    destino = _P(diretorio_estado()) / "navegador"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _perfil_efemero() -> bool:
    return os.environ.get(VARIAVEL_PERFIL_EFEMERO, "").strip().lower() in ("1", "true", "sim")


def abrir_navegador(p, oculto: bool, executavel):
    """Abre o navegador com PERFIL PERSISTENTE e devolve (contexto, pagina).

    Antes, cada execucao abria um navegador vazio: `launch()` mais `new_page()`.
    Para o Cloudflare isso e um visitante inedito toda vez, entao o desafio
    "Confirme que e humano" reaparecia em TODA execucao, e cada reaparicao
    custava uma tentativa do teto e a presenca do advogado.

    Guardar o perfil nao resolve, contorna nem disfarca o desafio: quem o
    responde continua sendo uma pessoa, uma vez. O que muda e que a liberacao
    obtida por ela deixa de ser jogada fora ao fechar o programa, que e o
    comportamento normal de qualquer navegador. Descartar o perfil nao tornava
    nada mais seguro; so obrigava a pessoa a repetir a prova ja dada.

    O preco e real e fica registrado: a pasta passa a conter cookie de sessao do
    portal. Quem tiver acesso a ela tem acesso a sessao enquanto ela valer. Por
    isso fica na pasta de estado, junto da auditoria, e nao em lugar temporario.
    `JUSTICA_NAVEGADOR_EFEMERO=1` volta ao descarte a cada execucao, para quem
    preferir pagar o desafio toda vez.
    """
    if _perfil_efemero():
        navegador = p.chromium.launch(headless=oculto, executable_path=executavel)
        return navegador, navegador.new_page()

    contexto = p.chromium.launch_persistent_context(
        str(pasta_do_navegador()), headless=oculto, executable_path=executavel
    )
    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    return contexto, pagina


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


def permissao_de_origem(url: str, descricao: str) -> Permissao:
    """Permissao para a ORIGEM do portal, nao para um caminho.

    Usada apenas durante a copia de documentos. Os arquivos de um processo
    ficam em caminhos proprios do mesmo portal, fora do endereco da tela, e a
    permissao ancorada no caminho exato os barrava: a trava estava certa e a
    suposicao e que era estreita demais.

    O alargamento e o minimo: mesma origem, e nada alem. Documento servido por
    outro dominio continua barrado, os termos de risco seguem valendo, e a
    autorizacao vale so enquanto `permitir_download` estiver ligado.
    """
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise PortalIndisponivel(f"Endereco invalido para origem: {url!r}")
    return Permissao(
        padrao_url=f"^{re.escape(f'{partes.scheme}://{partes.netloc}')}/",
        descricao=descricao,
        conferido_em="execucao atual",
    )


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
            navegador, pagina = abrir_navegador(p, oculto, executavel)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                print("\n" + NAVEGADOR_AUSENTE, file=sys.stderr)
                return 2
            raise
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

            # `domcontentloaded` dispara antes de o script montar a tela. Ler
            # ali devolvia zero campos e zero botoes em portal que monta o
            # formulario por script, e o relato dizia "a pagina talvez monte
            # por script" quando na verdade o comando e que leu cedo demais.
            # Verificado no e-SAJ de Sao Paulo em 21 de setembro de 2026.
            _assentar(pagina, segundos)

            print(f"  Titulo da pagina: {pagina.title()!r}")

            # Primeira pergunta do reconhecimento desde 21 de setembro de 2026,
            # quando o eproc reprovou o navegador automatizado: este portal tem
            # o mesmo controle? A resposta decide se vale escrever adaptador
            # autenticado para ele, e custa uma leitura de tela, nao uma
            # tentativa de login.
            if _desafio_reprovado(pagina):
                print("  VERIFICACAO HUMANA: presente e JA REPROVOU o navegador automatizado.")
                print("    Adaptador autenticado nao e viavel aqui enquanto isso valer.")
            elif _ha_desafio_humano(pagina):
                print("  VERIFICACAO HUMANA: presente, aguardando resposta.")
                print("    Pode ou nao reprovar o navegador automatizado; so tentando se sabe.")
            else:
                print("  VERIFICACAO HUMANA: nenhuma nesta tela.")
            print()
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
                # A mensagem antiga mandava aumentar o tempo, e isso passou a
                # ser conselho errado: a espera de assentamento ja rodou. Uma
                # pagina de verdade sem campo NENHUM costuma ser tela
                # intermediaria, nao a tela de login.
                print("    (nenhum) A espera de assentamento ja rodou, entao provavelmente")
                print("    esta nao e a tela de login: pode ser portal de servicos, aviso")
                print("    ou redirecionamento. Procure o link de entrar e use o endereco dele.")

            if not campos:
                try:
                    achados = []
                    for a in pagina.query_selector_all("a[href]"):
                        texto = (a.inner_text() or "").strip()
                        alvo = (a.get_attribute("href") or "")
                        if any(termo in (texto + alvo).lower() for termo in
                               ("login", "entrar", "acesso", "autentic", "identific", "senha")):
                            achados.append((texto[:45], alvo[:95]))
                    if achados:
                        print(f"\n  LINKS QUE PARECEM LEVAR AO LOGIN ({len(achados)}):")
                        for texto, alvo in achados[:15]:
                            print(f"    {texto!r}  ->  {alvo}")
                except Exception:
                    pass

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
    botao_entrar: str = "#sbmEntrar",
    oculto: bool = False,
    segundos: int = 30,
    espera_humana: int = ESPERA_HUMANA_PADRAO,
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
            navegador, pagina = abrir_navegador(p, oculto, executavel)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                print("\n" + NAVEGADOR_AUSENTE, file=sys.stderr)
                return 2
            raise
        try:
            guarda.pode_executar(Acao.NAVEGAR, url)
            pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")

            # O eproc passou a exibir o desafio "Confirme que e humano" do
            # Cloudflare antes do login. O programa nao o resolve: quem marca
            # a caixa e o operador, na janela aberta.
            if not _aguardar_desafio_humano(
                pagina, campo_usuario, espera_humana, oculto
            ):
                return 1

            botoes_antes = len(pagina.query_selector_all("button, input[type=button]"))

            # O e-SAJ de Sao Paulo entrega o botao Entrar DESABILITADO, e so o
            # habilita quando o formulario considera os campos preenchidos.
            # Sem conferir isso, o operador gastaria uma tentativa num clique
            # que nao faz nada, ou o clique esperaria ate o tempo esgotar.
            def _estado_do_botao():
                el = pagina.query_selector(botao_entrar)
                if el is None:
                    return None
                return el.is_enabled()

            habilitado_antes = _estado_do_botao()

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

            habilitado_depois = _estado_do_botao()
            print(f"  BOTAO DE ENVIO ({botao_entrar}):")
            if habilitado_antes is None:
                print("    nao encontrado nesta tela; confira o seletor com `reconhecer`.")
            elif habilitado_depois:
                print("    habilitado" + (" (ja estava)" if habilitado_antes
                                          else " apos o preenchimento"))
            else:
                print("    DESABILITADO mesmo com os campos preenchidos.")
                print("    Clicar nao surtiria efeito, e gastaria tentativa a toa.")
                print("    O formulario provavelmente exige algo mais: outra aba,")
                print("    um aceite, ou evento que o preenchimento nao disparou.")
            print()

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
    espera_humana: int = ESPERA_HUMANA_PADRAO,
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

    # `entrar` envia senha de verdade, entao consome tentativa como qualquer
    # outro envio. Ficava de fora da conferencia e do teto: quem alternasse
    # entre os dois comandos podia bloquear a conta sem nunca ver um aviso.
    try:
        LimiteTentativas.do_ambiente(estado).exigir_folga()
    except TetoDeTentativasAtingido as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

    print("=" * LARGURA)
    print("ENVIO UNICO DE LOGIN".center(LARGURA))
    print("=" * LARGURA)
    print(f"Endereco: {url}")
    print(f"Credencial: {identidade.rotulo} (lida do cofre, nunca impressa)")
    print("Clica UMA vez e le a tela seguinte. Sem repeticao, sem segundo fator.\n")

    executavel = os.environ.get("JUSTICA_CHROMIUM") or None
    with sync_playwright() as p:
        try:
            navegador, pagina = abrir_navegador(p, oculto, executavel)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                print("\n" + NAVEGADOR_AUSENTE, file=sys.stderr)
                return 2
            raise
        try:
            guarda.pode_executar(Acao.NAVEGAR, url)
            pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")

            # O eproc passou a exibir o desafio "Confirme que e humano" do
            # Cloudflare antes do login. O programa nao o resolve: quem marca
            # a caixa e o operador, na janela aberta.
            if not _aguardar_desafio_humano(
                pagina, campo_usuario, espera_humana, oculto
            ):
                return 1

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
                # Desfecho, nao um segundo envio: com o nome do envio, este
                # registro consumiria mais uma das seis tentativas por um ato
                # que nunca mandou senha nenhuma ao portal.
                estado.registrar(
                    acao="login_resultado_credencial", tribunal=identidade.tribunal,
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
                # A mensagem antiga presumia semente, porque o eproc foi o
                # primeiro portal implementado. O e-SAJ de Sao Paulo ENVIA o
                # codigo, e mandar o operador procurar no cofre um codigo que o
                # portal acabou de mandar por mensagem e desperdicar a validade
                # curta dele.
                if cofre.tem_semente(identidade):
                    print("  Ha semente guardada para esta credencial:")
                    print("  o proximo passo usa o codigo gerado pelo cofre.")
                else:
                    print("  NAO ha semente guardada para esta credencial, entao o codigo")
                    print("  provavelmente e ENVIADO pelo portal, por mensagem ou e-mail.")
                    print("  O proximo passo pede o codigo ao operador, na hora.")
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




def elemento_visivel(pagina: Any, seletor: str) -> Optional[Any]:
    """Devolve a primeira ocorrencia do seletor que esteja de fato na tela.

    O eproc monta duas barras superiores, uma para tela grande e outra para
    telefone, com os MESMOS identificadores. `query_selector` devolve a
    primeira do documento, que pode ser a oculta, e preencher a oculta falha
    em silencio: nao levanta erro, so nao acontece nada.
    """
    janela = pagina.viewport_size or {"width": 1280, "height": 720}
    for elemento in pagina.query_selector_all(seletor):
        try:
            if elemento.is_visible() and _na_tela(elemento, janela["width"], janela["height"]):
                return elemento
        except Exception:
            continue
    return None


def _perfis_disponiveis(botoes: list["Campo"]) -> list[tuple[str, str]]:
    """Botoes de escolha de inscricao na tela de selecao de perfil.

    No eproc eles vivem no formulario `frmEscolherUsuario` e trazem a inscricao
    e a qualificacao no texto, em linhas separadas.
    """
    saida = []
    for b in botoes:
        if not (b.na_tela and b.identificador and b.texto_visivel):
            continue
        if (b.formulario or "").lower().startswith("frmescolher"):
            saida.append((b.identificador, b.texto_visivel))
    return saida


def _casar_perfil(
    perfis: list[tuple[str, str]], desejado: str
) -> Optional[tuple[str, str]]:
    """Casa por trecho do rotulo, sem distinguir caixa nem espacos."""
    alvo = re.sub(r"\s+", "", desejado).lower()
    for identificador, rotulo in perfis:
        if alvo in re.sub(r"\s+", "", rotulo).lower():
            return identificador, rotulo
    return None


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
    perfil: Optional[str] = None,
    oculto: bool = False,
    segundos: int = 45,
    espera_humana: int = ESPERA_HUMANA_PADRAO,
    reenviar: bool = False,
    cofre: Optional[Cofre] = None,
    estado: Optional[Estado] = None,
    reconhecer_apos: Optional[str] = None,
    apos_autenticar: Optional[Any] = None,
) -> int:
    """Autenticacao completa: credencial, segundo fator, perfil, e para ali.

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
    # Falta de semente NAO impede autenticar. A conferencia nasceu quando o
    # eproc era o unico portal e todo segundo fator vinha de semente; no e-SAJ
    # de Sao Paulo o codigo e ENVIADO pelo portal, e exigir semente ali barrava
    # o comando antes de abrir o navegador, por uma falta que nao existe.
    #
    # O que ela ainda serve e avisar, porque sem semente o operador precisa
    # estar presente para digitar o codigo, e saber disso antes de comecar
    # evita comecar sem poder terminar.
    if not cofre.tem_semente(identidade):
        print(f"  Sem semente para {identidade.rotulo}: o codigo do segundo fator")
        print("  sera pedido a voce, se o portal exigir um. Tenha em maos o")
        print("  celular ou o e-mail que o recebe.")
        if oculto:
            print("\n  [PARADO] Sem semente e sem janela, nao ha a quem perguntar.",
                  file=sys.stderr)
            print("  Rode pela linha de comando, sem --oculto.", file=sys.stderr)
            return 1
        print()

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

    # Conferido antes de abrir o navegador: se o teto foi atingido, nem se
    # chega ao portal.
    try:
        LimiteTentativas.do_ambiente(estado).exigir_folga()
    except TetoDeTentativasAtingido as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

    print("=" * LARGURA)
    print("AUTENTICACAO COMPLETA".center(LARGURA))
    print("=" * LARGURA)
    print(f"Endereco: {url}")
    print(f"Credencial: {identidade.rotulo} (lida do cofre, nunca impressa)")
    print("Uma tentativa de credencial e uma de codigo. Nao marca dispositivo confiavel.\n")

    executavel = os.environ.get("JUSTICA_CHROMIUM") or None
    with sync_playwright() as p:
        try:
            navegador, pagina = abrir_navegador(p, oculto, executavel)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                print("\n" + NAVEGADOR_AUSENTE, file=sys.stderr)
                return 2
            raise
        try:
            guarda.pode_executar(Acao.NAVEGAR, url)
            pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")

            # O eproc passou a exibir o desafio "Confirme que e humano" do
            # Cloudflare antes do login. O programa nao o resolve: quem marca
            # a caixa e o operador, na janela aberta.
            if not _aguardar_desafio_humano(
                pagina, campo_usuario, espera_humana, oculto
            ):
                return 1

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

            # O desafio do Cloudflare tambem aparece DEPOIS do envio da
            # credencial, e nao so na abertura da pagina. Verificado em campo em
            # 21 de setembro de 2026: o portal devolveu
            # `acao=principal&acao_retorno=login` com o botao Enviar do desafio.
            # A espera so rodava na abertura, entao o comando desistia de um
            # login que apenas aguardava a pessoa, e gastava a tentativa a toa.
            if pagina.query_selector(campo_codigo) is None and _ha_desafio_humano(pagina):
                # Tres desfechos possiveis depois que a pessoa responde, e os
                # tres precisam ser reconhecidos. Reconhecer so o segundo fator
                # fazia o comando esperar os 180 segundos inteiros e desistir de
                # um desafio que ja tinha sido resolvido.
                def _passou(p):
                    alvo = p.query_selector(campo_codigo)
                    if alvo is not None and alvo.is_visible():
                        return True          # foi direto ao segundo fator
                    if _ja_autenticado(p):
                        return True          # foi direto a selecao de perfil
                    if _ha_desafio_humano(p):
                        return False         # ainda no desafio
                    usuario = p.query_selector(campo_usuario)
                    return usuario is not None and usuario.is_visible()

                _aguardar_desafio_humano(
                    pagina, campo_codigo, espera_humana, oculto, pronto=_passou
                )
                # Se o portal devolveu o formulario de login, a credencial
                # precisa ser reenviada. Este comando NAO reenvia sozinho: uma
                # credencial recusada tambem devolve o formulario, e reenviar as
                # cegas e como se bloqueia uma conta. O relato abaixo diz o que
                # apareceu, e a decisao de repetir fica com o operador.
                voltou = pagina.query_selector(campo_usuario)
                if (pagina.query_selector(campo_codigo) is None
                        and not _ha_desafio_humano(pagina)
                        and voltou is not None and voltou.is_visible()):
                    print("\n  O portal voltou ao formulario de login apos o desafio.")
                    erros_do_desafio = _mensagens_de_erro(pagina)
                    if erros_do_desafio:
                        print("  MAS ha mensagem na tela, entao a credencial pode ter sido")
                        print("  recusada. NAO foi reenviada:")
                        for e in erros_do_desafio:
                            print(f"    {e}")
                    elif not reenviar:
                        print("  A credencial precisa ser enviada de novo. Este comando nao")
                        print("  faz isso sozinho por padrao: credencial recusada devolve a")
                        print("  mesma tela, e reenviar as cegas e como se bloqueia conta.")
                        print("  Sem mensagem de erro acima, ha dois caminhos:")
                        print("    repetir o comando (a liberacao fica guardada no perfil), ou")
                        print("    acrescentar --reenviar-apos-desafio para o reenvio na hora.")
                    else:
                        # Autorizado pelo operador na linha de comando, e so
                        # quando NAO ha mensagem de erro. Nao e repetir uma
                        # tentativa recusada: a primeira nunca chegou a ser
                        # avaliada, foi desviada para o desafio.
                        print("  Sem mensagem de erro, e o reenvio foi autorizado no comando.")
                        if _reenviar_credencial(
                            pagina, guarda, url, login, senha, campo_usuario, campo_senha,
                            campo_senha_oculto, botao_entrar, segundos,
                        ):
                            estado.registrar(
                                acao="login_resultado_credencial",
                                tribunal=identidade.tribunal, sistema=identidade.sistema,
                                resultado="reenviada_apos_desafio",
                            )

            erros = _mensagens_de_erro(pagina)
            campo = pagina.query_selector(campo_codigo)
            if campo is None:
                # Duas situacoes muito diferentes chegavam aqui com a mesma
                # mensagem de uma linha: credencial recusada e portal que
                # simplesmente nao pediu o segundo fator porque a sessao
                # anterior continua valida. Sem distinguir, o operador nao
                # sabia se devia conferir a senha ou apenas rodar de novo, e a
                # orientacao errada custa tentativas de uma conta que bloqueia.
                if not _ja_autenticado(pagina):
                    print("\n  [PARADO] A tela do segundo fator nao apareceu.")
                    if erros:
                        print("  Mensagens na tela:")
                        for e in erros:
                            print(f"    {e}")
                    _relatar_tela(pagina, "TELA QUE APARECEU NO LUGAR")
                    print("\n  NAO repita o comando antes de conferir o que ha acima:")
                    print("  se for recusa de credencial, repetir queima tentativa da conta.")
                    # Nome proprio, de proposito: este e o DESFECHO da etapa,
                    # nao um segundo envio. Com o mesmo nome do envio, uma
                    # unica tentativa consumia duas das seis do teto, e o
                    # advogado ficava sem acesso na metade das tentativas que
                    # acreditava ter.
                    estado.registrar(acao="login_resultado_credencial",
                                     tribunal=identidade.tribunal,
                                     sistema=identidade.sistema, resultado="sem_tela_de_codigo")
                    return 1
                print("  Etapa 2: o portal nao pediu o segundo fator; "
                      "a sessao ja esta autenticada.")
                estado.registrar(acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                                 sistema=identidade.sistema, resultado="nao_solicitado")
            else:
                # ---------- etapa 2: segundo fator ----------
                # Dois tipos de segundo fator, e a diferenca nao e detalhe: com
                # semente o cofre GERA o codigo; sem semente quem o tem e a
                # pessoa, porque o portal o enviou. Presumir semente para todos
                # foi viavel enquanto so havia o eproc, e quebrou no e-SAJ.
                if cofre.tem_semente(identidade):
                    # Exige janela util: codigo gerado no fim da validade expira
                    # entre o preenchimento e o envio, e o portal registra falha
                    # por um motivo que nao e culpa da credencial.
                    restante = cofre.segundos_restantes_do_codigo()
                    if restante < 8:
                        print(f"  Codigo atual expira em {restante}s; aguardando a proxima janela.")
                    codigo = cofre._codigo_segundo_fator(identidade, minimo_segundos=8)
                    validade = f", valido por mais {cofre.segundos_restantes_do_codigo()}s"
                else:
                    tamanho = None
                    bruto = campo.get_attribute("maxlength")
                    if bruto and bruto.isdigit():
                        tamanho = int(bruto)
                    codigo = _codigo_do_operador(identidade.rotulo, tamanho, oculto)
                    if codigo is None:
                        estado.registrar(
                            acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                            sistema=identidade.sistema, resultado="codigo_nao_informado",
                        )
                        return 1
                    validade = " (informado pelo operador)"

                guarda.pode_executar(Acao.PREENCHER, campo_codigo, url=url)
                campo.click()
                campo.fill(codigo)
                conferido = campo.evaluate("e => (e.value || '').length")
                if conferido != len(codigo):
                    print(f"  [ABORTADO] O codigo nao entrou no campo ({conferido} de {len(codigo)}).")
                    print("             Nada foi enviado, para nao gastar tentativa.")
                    return 1
                print(f"  Etapa 2: codigo preenchido{validade}.")

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
                # Zera o teto: a sequencia de falhas que ele mede terminou aqui.
                estado.registrar(acao=ACAO_SUCESSO, tribunal=identidade.tribunal,
                                 sistema=identidade.sistema, resultado="autenticado")

            termo = guarda._termo_de_risco(final)
            if termo is not None:
                print(f"\n  TRAVA: o endereco final contem o termo de risco {termo!r}.")
                print("  A leitura da tela foi interrompida.")
                return 0

            campos, botoes = _coletar(pagina)
            # ---------- etapa 3: perfil ----------
            # O eproc pode ter mais de uma inscricao ligada ao mesmo acesso, e
            # o perfil escolhido determina QUAIS PROCESSOS o sistema mostra.
            # Escolher por conta propria daria uma visao incompleta sem aviso,
            # entao sem indicacao do operador o comando lista e para.
            perfis = _perfis_disponiveis(botoes)
            if perfis:
                print(f"\n  SELECAO DE PERFIL ({len(perfis)} disponivel(is)):")
                for identificador, rotulo in perfis:
                    print(f"    {rotulo}   (seletor #{identificador})")

                escolhido = _casar_perfil(perfis, perfil) if perfil else None
                if perfil and escolhido is None:
                    print(f"\n  Nenhum perfil corresponde a {perfil!r}. Nada foi selecionado.")
                    print("  Use um dos rotulos acima, ou parte dele.")
                    return 1
                if escolhido is None:
                    print("\n  Perfil nao indicado, entao nada foi selecionado.")
                    print("  O perfil determina quais processos aparecem, e escolher")
                    print("  por conta propria daria visao incompleta sem aviso.")
                    print("  Repita o comando acrescentando, por exemplo:")
                    print(f"    --perfil {perfis[0][1].split()[0]}")
                    return 0

                identificador, rotulo = escolhido
                seletor = f"#{identificador}"
                # A tela de perfil fica em endereco proprio, fora da permissao
                # do login, e a trava barrou o clique na primeira versao. Ela
                # estava certa. A autorizacao aqui e estreita de proposito:
                # vale so para esta tela e so para o botao do perfil escolhido,
                # em vez de liberar o endereco inteiro.
                guarda.permissoes.append(Permissao(
                    padrao_url=permissao_efemera(pagina.url).padrao_url,
                    descricao=f"selecao do perfil {rotulo.splitlines()[0]}",
                    conferido_em="execucao atual",
                    seletores_clicaveis=(seletor,),
                ))
                guarda.pode_executar(Acao.CLICAR, seletor, url=pagina.url)
                print(f"\n  Selecionando o perfil {rotulo.splitlines()[0]}...")
                pagina.query_selector(seletor).click()
                try:
                    pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
                except Exception:
                    pass
                estado.registrar(acao="login_etapa_perfil", tribunal=identidade.tribunal,
                                 sistema=identidade.sistema, resultado=rotulo.splitlines()[0])
                print(f"  Endereco: {pagina.url}")
                print(f"  Titulo: {pagina.title()!r}")
                campos, botoes = _coletar(pagina)

            if reconhecer_apos:
                # Varias telas numa autenticacao so. Cada login custa uma
                # tentativa do teto e um codigo que o operador precisa ler no
                # celular; reconhecer tela a tela multiplicava esse custo por
                # um motivo que era so de implementacao.
                destinos = ([reconhecer_apos] if isinstance(reconhecer_apos, str)
                            else list(reconhecer_apos))
                for i, destino in enumerate(destinos, 1):
                    print(f"\n  ===== TELA {i} de {len(destinos)} =====")
                    _reconhecer_dentro_da_sessao(pagina, guarda, destino, segundos)

            if apos_autenticar is not None:
                # Quem precisa continuar dentro da sessao recebe a pagina ja
                # autenticada. Evita duplicar o fluxo de login, que e a parte
                # mais delicada e ja validada em campo.
                resultado = apos_autenticar(pagina, guarda, estado, identidade)
                print("\n  RELATO DA TRAVA:")
                for linha in guarda.relato():
                    print(f"    {linha}")
                return resultado if isinstance(resultado, int) else 0

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




def _gravar_consulta(dados: dict, chave: str) -> "pathlib.Path":
    """Grava a consulta em arquivo local, no diretorio de estado do servidor."""
    import json
    import pathlib
    from datetime import datetime, timezone

    from .core.estado import diretorio_estado

    pasta = diretorio_estado() / "consultas"
    pasta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = pasta / f"{chave}-{marca}.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


BOTAO_INTEGRA = "#btnDownloadCompletoRS"


# Marcadores do desafio "Confirme que e humano" do Cloudflare, visto no eproc
# do Tribunal Regional Federal da 2a Regiao em 21 de setembro de 2026.
MARCAS_DESAFIO = (
    'iframe[src*="challenges.cloudflare.com"]',
    'input[name="cf-turnstile-response"]',
    ".cf-turnstile",
    "#cf-challenge-running",
)


# Texto que o Turnstile mostra quando REPROVA a verificacao. Visto em campo em
# 21 de setembro de 2026, no eproc do Tribunal Regional Federal da 2a Regiao.
MARCAS_DESAFIO_REPROVADO = (
    "falha na verificacao", "falha na verificação",
    "verification failed", "solucao de problemas", "solução de problemas",
)


def _desafio_reprovado(pagina) -> bool:
    """Diz se o desafio REPROVOU a verificacao, em vez de apenas aguardar.

    A diferenca importa muito para quem esta diante da tela. Aguardando, marcar
    a caixa resolve. Reprovado, marcar a caixa nao resolve nunca: o que foi
    recusado e o navegador automatizado, nao a pessoa. Sem distinguir, o
    operador fica clicando numa caixa que jamais vai passar.

    O texto vive dentro do quadro do proprio Cloudflare, entao a busca percorre
    os quadros da pagina, e nao so o documento principal.
    """
    alvos = [pagina]
    try:
        alvos.extend(pagina.frames)
    except Exception:
        pass
    for alvo in alvos:
        try:
            texto = (alvo.inner_text("body") or "").lower()
        except Exception:
            continue
        if any(marca in texto for marca in MARCAS_DESAFIO_REPROVADO):
            return True
    return False


def _assentar(pagina, segundos: int) -> None:
    """Espera a pagina assentar antes de ler a estrutura.

    Duas esperas, e a segunda existe porque a primeira nao basta: portais que
    montam a tela por script terminam a rede antes de terminar o desenho, e ler
    naquele instante devolve uma pagina vazia que parece um portal sem
    formulario. Sem isso o relato induz ao erro oposto do util: diz que nao ha
    nada onde ha tudo.
    """
    try:
        pagina.wait_for_load_state("networkidle", timeout=min(segundos, 20) * 1000)
    except Exception:
        pass
    try:
        # Um campo ou um botao ja indica tela montada. O tempo curto e de
        # proposito: e retoque, nao espera principal.
        pagina.wait_for_selector(
            "input, select, textarea, button, a[role=button]", timeout=5000
        )
    except Exception:
        pass


def _ha_desafio_humano(pagina) -> bool:
    for marca in MARCAS_DESAFIO:
        try:
            if pagina.query_selector(marca) is not None:
                return True
        except Exception:
            continue
    return False


def _aguardar_desafio_humano(
    pagina, seletor_esperado: str, segundos: int, oculto: bool, pronto=None
) -> bool:
    """Espera o OPERADOR resolver o desafio do Cloudflare, na janela aberta.

    Este projeto NAO resolve, contorna nem disfarca o desafio. Ele e um
    controle de seguranca do tribunal, e automatiza-lo seria contornar protecao
    de terceiro em nome do advogado, com o risco recaindo sobre ele. O caminho
    honesto e o unico oferecido: a pessoa marca a caixa, e o programa espera.

    Por isso tambem nao funciona com `--oculto`: sem janela visivel nao ha como
    um humano responder, e fingir que ha seria mentir para o operador.

    Devolve True quando o caminho esta livre, False quando o tempo acabou.
    """
    if not _ha_desafio_humano(pagina):
        return True

    print("\n  DESAFIO DO CLOUDFLARE NA TELA (\"Confirme que e humano\").")
    if oculto:
        print("  O navegador esta oculto, entao ninguem pode responder.")
        print("  Repita o comando SEM --oculto para resolver o desafio a mao.")
        return False
    print("  Este programa nao resolve o desafio: ele e protecao do tribunal, e")
    print("  automatiza-lo seria contorna-la em seu nome, com o risco sendo seu.")
    print(f"\n  >>> Va ate a janela do navegador, marque a caixa e, se houver botao,")
    print(f"  >>> clique em Enviar. Aguardando ate {segundos}s.")

    # Depois do desafio o portal nem sempre volta para a mesma tela: resolvido
    # no meio do login, ele pode ir direto ao segundo fator ou a selecao de
    # perfil. Esperar so por uma tela faria o comando desistir de um login que
    # deu certo.
    if pronto is None:
        def pronto(p):
            alvo = p.query_selector(seletor_esperado)
            return alvo is not None and alvo.is_visible()

    limite = time.monotonic() + segundos
    avisado = 0
    while time.monotonic() < limite:
        try:
            if pronto(pagina):
                print("  Desafio resolvido. Seguindo.")
                return True
        except Exception:
            pass
        if _desafio_reprovado(pagina):
            print("\n  O DESAFIO REPROVOU A VERIFICACAO (\"Falha na verificacao\").")
            print("  Marcar a caixa de novo nao resolve: o que foi recusado e o")
            print("  navegador automatizado, nao o senhor. O tribunal ligou um")
            print("  controle cuja finalidade e impedir acesso por programa.")
            print("\n  Este projeto nao disfarca a automacao para passar por ele.")
            print("  Caminhos que continuam valendo:")
            print("    - as fontes publicas (base nacional e Diario Eletronico),")
            print("      que nao tem desafio nem login;")
            print("    - o acesso pelo navegador do proprio advogado, a mao;")
            print("    - perguntar ao tribunal se ha via programatica autorizada.")
            return False
        restante = int(limite - time.monotonic())
        if restante // 30 != avisado // 30 and restante > 0:
            print(f"    aguardando... {restante}s")
        avisado = restante
        pagina.wait_for_timeout(1500)

    ainda = "sim" if _ha_desafio_humano(pagina) else "nao"
    print(f"  Tempo esgotado. Desafio ainda na tela: {ainda}.")
    if ainda == "nao":
        print("  O desafio saiu, mas a tela seguinte nao foi reconhecida.")
        print("  Veja o relato abaixo: pode ser que o portal tenha voltado ao login.")
    else:
        print("  A caixa continua por marcar, ou a resposta nao foi aceita.")
    return False


def _esvaziar_teclado() -> None:
    """Descarta o que foi digitado antes da pergunta.

    Best-effort e silencioso: falhar aqui nao pode atrapalhar a pergunta, que
    e o que importa.
    """
    try:
        import msvcrt

        while msvcrt.kbhit():
            msvcrt.getwch()
        return
    except Exception:
        pass
    try:
        import termios

        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def _reconhecer_dentro_da_sessao(pagina, guarda, destino: str, segundos: int) -> None:
    """Le a estrutura de uma tela DENTRO da sessao ja autenticada.

    O comando `reconhecer` abre sessao nova e por isso nunca enxerga o que so
    existe depois do login: a tela de consulta, a lista de intimacoes, o
    processo. Sem isto, escrever o adaptador de cada portal novo exigiria
    adivinhar seletores, que e o erro que este projeto existe para evitar.

    So LE. A autorizacao e de mesma origem do portal e nao libera clique nem
    preenchimento nenhum, e o destino passa pelos termos de risco como qualquer
    outro endereco.
    """
    print(f"\n  RECONHECENDO DENTRO DA SESSAO: {destino}")
    guarda.permissoes.append(permissao_de_origem(
        pagina.url, "reconhecimento de tela interna, somente leitura"
    ))
    try:
        guarda.avaliar(Acao.NAVEGAR, destino, url=destino).exigir()
    except NavegacaoBloqueada as exc:
        print(f"    TRAVA: {exc}")
        print("    Nada foi lido. O destino precisa ser do mesmo portal.")
        return
    try:
        pagina.goto(destino, timeout=segundos * 1000, wait_until="domcontentloaded")
    except Exception as exc:
        print(f"    Nao carregou: {type(exc).__name__}: {exc}")
        return
    _assentar(pagina, segundos)
    _relatar_tela(pagina, "TELA INTERNA")
    try:
        campos, _ = _coletar(pagina)
    except Exception as exc:
        print(f"    Estrutura ilegivel: {type(exc).__name__}: {exc}")
        return
    print(f"    CAMPOS ({len(campos)}):")
    for c in campos:
        print(f"      {c.linha()}")

    # Portais montam o menu como paineis sanfonados: os links existem no
    # documento mesmo com o painel fechado. Lista-los revela o endereco da tela
    # de consulta sem clicar em nada e sem eu adivinhar, que e o ponto todo do
    # reconhecimento. Visto no e-SAJ de Sao Paulo, 21 de setembro de 2026.
    _relatar_estrutura_de_dados(pagina)
    _listar_ligacoes(pagina)


def _relatar_estrutura_de_dados(pagina, teto: int = 40) -> None:
    """Descreve onde os dados moram, sem mostrar os dados.

    Partes, movimentacoes e documentos vivem em tabelas e em elementos com
    identificador, nao em campos de formulario, entao o relato de campos nao os
    enxerga. Sem isto, escrever a extracao de cada portal exigiria adivinhar
    seletor de tabela.

    Reporta identificador, classe e tamanho, e NAO reporta texto de celula. A
    promessa do reconhecimento e que nenhum dado de processo apareca no relato,
    porque ele e colado em conversa. Nome de parte e teor de movimentacao sao
    justamente o que nao pode sair dali.
    """
    try:
        tabelas = pagina.query_selector_all("table")
    except Exception as exc:
        print(f"    Tabelas ilegiveis: {type(exc).__name__}: {exc}")
        return

    print(f"    TABELAS ({len(tabelas)}), so estrutura, sem conteudo:")
    for i, tabela in enumerate(tabelas[:teto]):
        try:
            ident = tabela.get_attribute("id") or ""
            classe = (tabela.get_attribute("class") or "")[:45]
            linhas = len(tabela.query_selector_all("tr"))
            colunas = len(tabela.query_selector_all("tr:first-child > *"))
        except Exception:
            continue
        rotulo = f"#{ident}" if ident else (f".{classe}" if classe else "(sem id nem classe)")
        print(f"      {rotulo:46s} {linhas} linha(s) x {colunas} coluna(s)")

    try:
        marcados = pagina.query_selector_all("[id]")
    except Exception:
        return
    nomes: list[str] = []
    for el in marcados:
        try:
            ident = el.get_attribute("id") or ""
            marcador = el.evaluate("e => e.tagName.toLowerCase()")
        except Exception:
            continue
        if not ident or marcador in ("script", "style", "link", "meta"):
            continue
        nomes.append(f"{marcador}#{ident}")
    # Teto proprio, e alto: identificador e estrutura pura, nao dado de
    # processo, e cortar em 40 escondeu justamente o que faltava. O e-SAJ poe o
    # identificador da tabela de movimentacoes no `tbody`, nao na `table`, e
    # esses vinham depois do corte. Perder uma execucao autenticada por causa
    # de um teto de listagem e caro: custa uma tentativa e um codigo lido no
    # celular.
    teto_ids = 300
    if nomes:
        print(f"    ELEMENTOS COM IDENTIFICADOR ({len(nomes)}"
              + (f", mostrando {teto_ids}" if len(nomes) > teto_ids else "") + "):")
        for nome in nomes[:teto_ids]:
            print(f"      {nome}")


def _listar_ligacoes(pagina, teto: int = 60) -> None:
    try:
        ancoras = pagina.query_selector_all("a[href]")
    except Exception as exc:
        print(f"    Ligacoes ilegiveis: {type(exc).__name__}: {exc}")
        return
    vistos: set = set()
    linhas: list[tuple[str, str]] = []
    for a in ancoras:
        try:
            alvo = (a.get_attribute("href") or "").strip()
            texto = " ".join((a.inner_text() or "").split())[:50]
        except Exception:
            continue
        if not alvo or alvo.startswith(("#", "javascript:")) or alvo in vistos:
            continue
        vistos.add(alvo)
        linhas.append((texto, alvo))
    print(f"    LIGACOES ({len(linhas)}"
          + (f", mostrando {teto}" if len(linhas) > teto else "") + "):")
    for texto, alvo in linhas[:teto]:
        print(f"      {texto or '(sem texto)':42s} -> {alvo[:100]}")


def _codigo_do_operador(rotulo: str, tamanho: Optional[int], oculto: bool) -> Optional[str]:
    """Pede ao operador o codigo que o PORTAL enviou.

    Nem todo portal usa codigo gerado de semente. O e-SAJ de Sao Paulo envia um
    por mensagem ou e-mail, verificado em campo em 21 de setembro de 2026 pelo
    botao "Receber novo codigo" e pela ausencia de semente no cofre. Para esses,
    o cofre nao tem o que gerar: quem tem o codigo e a pessoa.

    Sem janela e sem terminal nao ha a quem perguntar, entao recusa em vez de
    ficar esperando uma resposta que nunca vem. Vale para a ferramenta do
    servidor, que roda sempre oculta.
    """
    if oculto:
        print("  [PARADO] O portal pede um codigo que ELE envia, e nao ha como")
        print("           perguntar a ninguem nesta execucao. Rode pela linha de")
        print("           comando, sem --oculto, com o codigo em maos.")
        return None
    if not sys.stdin or not sys.stdin.isatty():
        print("  [PARADO] O portal pede um codigo enviado por ele, e esta execucao")
        print("           nao tem terminal para perguntar. Rode direto no PowerShell.")
        return None

    # Teclas digitadas enquanto o navegador carregava ficam na fila e sao
    # consumidas pela primeira pergunta, que entao recusa um codigo que o
    # operador nem chegou a digitar. Visto em campo em 21 de setembro de 2026.
    _esvaziar_teclado()

    limite = f" ({tamanho} digitos)" if tamanho else ""
    print(f"\n  O portal enviou um codigo{limite}. Confira sua mensagem ou e-mail.")
    print("  Ele tem validade curta, entao digite assim que receber.")
    for tentativa in range(3):
        try:
            digitado = input(f"  Codigo para {rotulo} (vazio cancela): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelado pelo operador. Nada foi enviado.")
            return None
        if not digitado:
            print("  Cancelado. Nada foi enviado.")
            return None
        if not digitado.isdigit():
            print("  So digitos. Tente de novo.")
            continue
        if tamanho and len(digitado) != tamanho:
            print(f"  O campo aceita {tamanho} digitos e voce informou {len(digitado)}.")
            continue
        return digitado
    print("  Tres tentativas de digitacao sem acerto. Nada foi enviado.")
    return None


def _reenviar_credencial(
    pagina, guarda, url, login, senha, campo_usuario, campo_senha,
    campo_senha_oculto, botao_entrar, segundos,
) -> bool:
    """Reenvia a credencial UMA vez, apos o desafio ter sido resolvido.

    Nao e repetir uma tentativa recusada. A primeira nunca chegou a ser
    avaliada: foi desviada para o desafio do Cloudflare, e o portal devolveu o
    formulario em branco. Quem chama ja conferiu que nao ha mensagem de erro na
    tela e que o operador autorizou na linha de comando.

    Nao conta como nova tentativa no teto, pelo mesmo motivo: e a conclusao do
    envio que ja foi contado, nao um segundo envio.
    """
    for seletor, valor, rotulo in (
        (campo_usuario, login, "usuario"), (campo_senha, senha, "senha"),
    ):
        elemento = pagina.query_selector(seletor)
        if elemento is None:
            print(f"    [FALHA] Campo de {rotulo} sumiu. Nada reenviado.")
            return False
        guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
        elemento.click()
        elemento.fill(valor)

    alvo = pagina.query_selector(campo_senha_oculto)
    if not alvo or alvo.evaluate("e => (e.value || '').length") != len(senha):
        print("    [ABORTADO] A senha nao chegou ao campo enviado. Nada reenviado.")
        return False

    guarda.pode_executar(Acao.CLICAR, botao_entrar, url=pagina.url)
    botao = pagina.query_selector(botao_entrar)
    if botao is None:
        print("    [FALHA] Botao de entrar sumiu. Nada reenviado.")
        return False
    print("    Credencial reenviada (uma vez).")
    botao.click()
    try:
        pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
    except Exception:
        pass
    return True


def _ja_autenticado(pagina) -> bool:
    """Diz se a sessao ja esta aberta, por evidencia positiva na tela.

    So devolve verdadeiro quando a tela de selecao de perfil esta presente.
    Essa tela nao existe antes da autenticacao, entao serve de prova; deduzir
    do endereco ou da ausencia da tela de codigo seria concluir a partir de
    ausencia, e o preco de errar aqui e seguir como autenticado quando a
    credencial foi recusada.
    """
    try:
        _, botoes = _coletar(pagina)
    except Exception:
        return False
    return bool(_perfis_disponiveis(botoes))


def _relatar_tela(pagina, titulo: str) -> None:
    """Descreve a tela atual, sem tocar em nada.

    Existe porque o clique na copia integral NAO devolve arquivo: o eproc abre
    uma tela intermediaria pedindo que o arquivo seja gerado. Adivinhar o
    seletor dessa tela seria exatamente o erro que este projeto evita, entao o
    comando relata o que encontrou e para, para que o seletor real seja
    conferido em campo antes de virar codigo.
    """
    print(f"\n    ----- {titulo} -----")
    print(f"    Endereco: {pagina.url}")
    try:
        print(f"    Titulo: {pagina.title()!r}")
    except Exception:
        pass
    try:
        campos, botoes = _coletar(pagina)
    except Exception as exc:
        print(f"    Nao foi possivel ler a estrutura: {type(exc).__name__}: {exc}")
        return
    visiveis = [b for b in botoes if b.na_tela]
    print(f"    BOTOES NA TELA ({len(visiveis)} de {len(botoes)}):")
    for b in visiveis:
        alvo = b.identificador and f"#{b.identificador}" or (b.nome and f"[name={b.nome}]") or "(sem id)"
        print(f"      {alvo:40s} {(b.texto_visivel or '')[:50]!r}")
    if not visiveis:
        for b in botoes[:20]:
            alvo = b.identificador and f"#{b.identificador}" or (b.nome and f"[name={b.nome}]") or "(sem id)"
            print(f"      (fora da tela) {alvo:30s} {(b.texto_visivel or '')[:50]!r}")
    try:
        quadros = pagina.query_selector_all("iframe")
        if quadros:
            print(f"    QUADROS EMBUTIDOS ({len(quadros)}):")
            for q in quadros[:10]:
                print(f"      src={(q.get_attribute('src') or '(sem src)')[:90]}")
    except Exception:
        pass
    print(f"    Desafio de verificacao humana detectado: "
          f"{'sim' if _ha_desafio_humano(pagina) else 'nao'}")
    ligacoes = pagina.query_selector_all("a[href]")
    interessantes = []
    for a in ligacoes:
        texto = (a.inner_text() or "").strip()
        if any(t in texto.lower() for t in ("gerar", "download", "baixar", "completo", "integra")):
            interessantes.append((texto[:60], (a.get_attribute("href") or "")[:90]))
    if interessantes:
        print(f"    LIGACOES COM TERMO DE COPIA ({len(interessantes)}):")
        for texto, href in interessantes[:15]:
            print(f"      {texto!r}  ->  {href}")


def _baixar_integra(pagina, guarda, destino, chave: str, segundos: int) -> Optional[str]:
    """Copia integral pelo botao do proprio portal.

    Unico download que exige clique: o botao nao tem endereco proprio, o
    arquivo e montado pelo servidor sob demanda. Por isso o alvo e liberado
    nominalmente, e so nesta operacao.

    Em campo, em 21 de setembro de 2026, este clique NAO devolveu arquivo: o
    eproc abre uma tela intermediaria pedindo que a copia seja gerada. O
    comando nao adivinha o segundo clique. Ele relata a tela que apareceu, com
    os botoes e as ligacoes candidatas, para que o seletor real seja conferido
    antes de virar codigo. Adivinhar aqui e o erro que este projeto existe para
    evitar: um clique errado no portal custa caro.
    """
    from pathlib import Path

    botao = elemento_visivel(pagina, BOTAO_INTEGRA)
    if botao is None:
        return None
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="copia integral pelo botao do portal",
        conferido_em="execucao atual",
        seletores_clicaveis=(BOTAO_INTEGRA,),
    ))
    guarda.pode_executar(Acao.CLICAR, BOTAO_INTEGRA, url=pagina.url)

    # A tela intermediaria pode vir como aba nova. Sem capturar a aba, o
    # relato descreveria a pagina antiga e nao diria nada de util.
    nova: list = []
    try:
        pagina.context.on("page", lambda p: nova.append(p))
    except Exception:
        pass

    try:
        with pagina.expect_download(timeout=segundos * 1000) as info:
            botao.click()
    except Exception as exc:
        print(f"    O clique nao devolveu arquivo: {type(exc).__name__}.")
        print("    O eproc abre uma tela pedindo para gerar a copia. Segue o que ha nela,")
        print("    para o seletor ser conferido antes de virar codigo. Nada foi clicado.")
        _relatar_tela(pagina, "TELA APOS O CLIQUE")
        for i, p in enumerate(nova):
            try:
                p.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            _relatar_tela(p, f"ABA NOVA {i + 1}")
        raise

    baixado = info.value
    destino.mkdir(parents=True, exist_ok=True)
    sugerido = baixado.suggested_filename or f"{chave}-integra.zip"
    arquivo = Path(destino) / f"integra-{sugerido}"
    baixado.save_as(str(arquivo))
    return str(arquivo)


BUSCA_RAPIDA = "#txtNumProcessoPesquisaRapida"
BOTAO_BUSCA = "button[name=btnPesquisaRapidaSubmit]"


def consultar_processo_estruturado(
    tribunal: str,
    sistema: str,
    numero_processo: str,
    *,
    cofre: Optional[Cofre] = None,
    estado: Optional[Estado] = None,
) -> dict:
    """Consulta e devolve os dados, sem imprimir nada.

    Usada pela ferramenta do servidor. O endereco e o perfil vem do ambiente,
    e nao de parametro: o agente nao deve precisar saber o endereco do portal
    nem ter como apontar a autenticacao para outro lugar.
    """
    import io
    from contextlib import redirect_stdout

    from .core.acesso import autenticado_habilitado, config_portal

    if not autenticado_habilitado():
        raise PermissionError(
            "Acesso autenticado desligado. Ligar permite que o agente dispare "
            "autenticacao real no tribunal com a credencial do advogado, e isso "
            "e decisao do operador. Para habilitar, defina no .env: "
            "JUSTICA_ACESSO_AUTENTICADO=1"
        )

    config = config_portal(tribunal, sistema)
    guardado: dict = {}

    def capturar(pagina, guarda, estado_local, identidade):
        from .core.cnj import parse_numero
        from .extracao import extrair_processo

        numero = parse_numero(numero_processo)
        atual = pagina.url
        campo = elemento_visivel(pagina, BUSCA_RAPIDA)
        botao = elemento_visivel(pagina, BOTAO_BUSCA)
        if campo is None or botao is None:
            guardado["erro"] = "Busca rapida nao encontrada na tela."
            return 1
        guarda.permissoes.append(Permissao(
            padrao_url=permissao_efemera(atual).padrao_url,
            descricao="busca rapida de processo, somente leitura",
            conferido_em="execucao atual",
            seletores_clicaveis=(BOTAO_BUSCA,),
            seletores_preenchiveis=(BUSCA_RAPIDA,),
        ))
        guarda.pode_executar(Acao.PREENCHER, BUSCA_RAPIDA, url=atual)
        campo.click()
        campo.fill(numero.formatado)
        guarda.pode_executar(Acao.CLICAR, BOTAO_BUSCA, url=atual)
        botao.click()
        try:
            pagina.wait_for_load_state("networkidle", timeout=45000)
        except Exception:
            pass
        if guarda._termo_de_risco(pagina.url) is not None:
            guardado["erro"] = "Destino com termo de risco; leitura interrompida."
            return 1
        dados = extrair_processo(pagina, numero.formatado)
        dados["arquivo"] = str(_gravar_consulta(dados, numero.apenas_digitos))
        estado_local.gravar_snapshot(
            numero.apenas_digitos,
            [{"data_hora": e["data_hora"], "codigo": e["evento"], "nome": e["descricao"]}
             for e in dados["eventos"]],
        )
        estado_local.registrar(
            acao="consulta_processo_autenticada", tribunal=identidade.tribunal,
            sistema=identidade.sistema, numero=numero.formatado,
            resultado=f"{dados['totais']['eventos']} evento(s)",
        )
        guardado["dados"] = dados
        return 0

    # A saida do fluxo interativo nao interessa aqui; o que importa e o
    # dicionario. Capturar evita poluir o canal do servidor.
    with redirect_stdout(io.StringIO()):
        codigo = autenticar(
            config.url, tribunal, sistema, confirmado=True, perfil=config.perfil,
            oculto=True, cofre=cofre, estado=estado, apos_autenticar=capturar,
        )
    if "dados" not in guardado:
        raise RuntimeError(guardado.get("erro") or f"Consulta nao concluida (codigo {codigo}).")
    return guardado["dados"]


def consultar_processo(
    url: str,
    tribunal: str,
    sistema: str,
    numero_processo: str,
    *,
    campo_usuario: str = "#txtUsuario",
    campo_senha: str = "#pwdSenha",
    campo_senha_oculto: str = "input[name=pwdSenha]",
    botao_entrar: str = "#sbmEntrar",
    campo_codigo: str = "#txtAcessoCodigo",
    botao_validar: str = "#btnValidar",
    documentos: str = "auto",
    confirmado: bool = False,
    perfil: Optional[str] = None,
    oculto: bool = False,
    segundos: int = 45,
    espera_humana: int = ESPERA_HUMANA_PADRAO,
    reenviar: bool = False,
    cofre: Optional[Cofre] = None,
    estado: Optional[Estado] = None,
) -> int:
    """Autentica e consulta um processo pela busca rapida do portal.

    Usa a barra de busca que o eproc mantem em TODAS as telas. Isso contorna a
    tela de atualizacao cadastral em que a autenticacao desemboca quando o
    portal a exige: o campo de busca vive em `formPesquisaRapida`, formulario
    distinto do `frmPessoaAlteracao`, entao consultar nao encosta no cadastro.

    Somente leitura. Preenche o numero, envia a busca e relata a tela. Nao abre
    documento, nao baixa nada, nao toca em expediente.
    """
    from .core.cnj import NumeroCNJInvalido, parse_numero

    try:
        numero = parse_numero(numero_processo)
    except NumeroCNJInvalido as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

    def depois(pagina, guarda, estado_local, identidade):
        atual = pagina.url
        print(f"\n  CONSULTA DO PROCESSO {numero.formatado}")

        # Cada sistema tem a sua forma de chegar ao processo, e a diferenca nao
        # e cosmetica: o eproc tem barra de busca rapida em toda tela, o e-SAJ
        # tem duas telas de consulta, uma por grau, com o numero partido em dois
        # campos. Tratar tudo como eproc foi possivel enquanto so havia eproc.
        if identidade.sistema == "esaj":
            from .esaj import ConsultaESAJIndisponivel, buscar as buscar_esaj

            print(f"  e-SAJ, {numero.grau_nome} (deduzida do proprio numero).")
            try:
                buscar_esaj(pagina, guarda, numero, segundos)
            except ConsultaESAJIndisponivel as exc:
                print(f"  [FALHA] {exc}")
                return 1
            print(f"  Endereco: {pagina.url}")
            print(f"  Titulo: {pagina.title()!r}")
            # A extracao do e-SAJ ainda nao existe: a tela de resultado nunca
            # foi vista. Relatar a estrutura e o passo que gera o material para
            # escreve-la, e e o mesmo caminho que o eproc percorreu.
            _relatar_tela(pagina, "RESULTADO DA CONSULTA")
            _relatar_estrutura_de_dados(pagina)
            try:
                campos, _ = _coletar(pagina)
                print(f"    CAMPOS ({len(campos)}):")
                for c in campos[:30]:
                    print(f"      {c.linha()}")
            except Exception as exc:
                print(f"    Estrutura ilegivel: {type(exc).__name__}: {exc}")
            _listar_ligacoes(pagina, teto=40)
            estado_local.registrar(
                acao="consulta_processo_autenticada", tribunal=identidade.tribunal,
                sistema=identidade.sistema, numero=numero.formatado,
                resultado="estrutura relatada, extracao ainda nao escrita",
            )
            return 0

        campo = elemento_visivel(pagina, BUSCA_RAPIDA)
        if campo is None:
            print("  [FALHA] Campo de busca rapida nao encontrado na tela.")
            return 1
        botao = elemento_visivel(pagina, BOTAO_BUSCA)
        if botao is None:
            print("  [FALHA] Botao de busca nao encontrado na tela.")
            return 1

        # Autorizacao estreita: so a busca, so nesta tela. O formulario de
        # cadastro que divide a pagina continua inteiramente barrado.
        guarda.permissoes.append(Permissao(
            padrao_url=permissao_efemera(atual).padrao_url,
            descricao="busca rapida de processo, somente leitura",
            conferido_em="execucao atual",
            seletores_clicaveis=(BOTAO_BUSCA,),
            seletores_preenchiveis=(BUSCA_RAPIDA,),
        ))

        guarda.pode_executar(Acao.PREENCHER, BUSCA_RAPIDA, url=atual)
        campo.click()
        campo.fill(numero.formatado)
        conferido = campo.evaluate("e => (e.value || '').length")
        if not conferido:
            print("  [ABORTADO] O numero nao entrou no campo. Nada foi enviado.")
            return 1

        guarda.pode_executar(Acao.CLICAR, BOTAO_BUSCA, url=atual)
        estado_local.registrar(
            acao="consulta_processo_autenticada", tribunal=identidade.tribunal,
            sistema=identidade.sistema, numero=numero.formatado, resultado="enviada",
        )
        botao.click()
        try:
            pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
        except Exception:
            pass

        final = pagina.url
        print(f"  Endereco: {final}")
        print(f"  Titulo: {pagina.title()!r}")

        termo = guarda._termo_de_risco(final)
        if termo is not None:
            print(f"\n  TRAVA: o destino contem o termo de risco {termo!r}.")
            print("  A leitura foi interrompida. Informe este endereco.")
            return 1

        erros = _mensagens_de_erro(pagina)
        if erros:
            print("\n  MENSAGENS NA TELA:")
            for e in erros:
                print(f"    {e}")

        from .extracao import extrair_processo, resumo

        dados = extrair_processo(pagina, numero.formatado)
        if not dados["eventos"]:
            print("\n  [ATENCAO] Nenhum evento extraido. A tela pode ter outra")
            print("  estrutura, ou o processo pode estar em segredo de justica.")
            print(f"  Tabelas na pagina: "
                  f"{[t.get_attribute('id') or '-' for t in pagina.query_selector_all('table')]}")
            return 1

        # O conteudo vai para arquivo; o terminal recebe so o resumo. Despejar
        # dezenas de eventos na tela convida a colar dado de cliente onde nao
        # deve, e o arquivo e o que o restante do sistema vai consumir.
        destino = _gravar_consulta(dados, numero.apenas_digitos)
        print("\n  EXTRAIDO:")
        for linha in resumo(dados):
            print(f"    {linha}")

        # Alimenta o mesmo mecanismo de comparacao da Fase 1, de modo que
        # `verificar_novos_andamentos` passe a enxergar tambem o autenticado.
        registro = estado_local.gravar_snapshot(
            numero.apenas_digitos,
            [{"data_hora": e["data_hora"], "codigo": e["evento"], "nome": e["descricao"]}
             for e in dados["eventos"]],
        )
        if registro.get("primeiro"):
            print("\n    Referencia inicial gravada para comparacao futura.")
        elif registro["mudou"]:
            print(f"\n    Houve mudanca desde a consulta anterior "
                  f"({registro['coletado_em']}).")
        else:
            print("\n    Sem mudanca desde a consulta anterior.")

        # ---------- copias dos documentos ----------
        if documentos and documentos != "nenhum":
            from .core.acervo import (
                carregar_indice, decidir_estrategia, garantir_pasta,
                pdfs_fora_do_indice,
            )
            from .documentos import baixar_documentos_dos_eventos

            indice = carregar_indice(numero.apenas_digitos, numero.formatado)
            # A pasta nasce aqui, e nao no instante de gravar o primeiro
            # arquivo: ela e o endereco do processo no acervo, e precisa
            # existir mesmo que a consulta nao copie nada.
            pasta = garantir_pasta(numero.apenas_digitos)
            print(f"  Pasta do processo: {pasta}")
            avulsos = pdfs_fora_do_indice(indice)
            if avulsos:
                print(f"  ATENCAO: {len(avulsos)} arquivo(s) na pasta fora do indice, "
                      f"por exemplo {avulsos[0]}.")
                print("  Nao da para saber o que eles cobrem, entao nao contam como copia.")
            guarda.permissoes.insert(0, permissao_de_origem(
                pagina.url, "documentos do processo, mesma origem do portal"
            ))
            guarda.permitir_download = True
            print()

            if documentos == "auto":
                estrategia = decidir_estrategia(indice, dados["eventos"])
                print(f"  ACERVO: {estrategia['motivo']}")
            elif documentos == "integra":
                estrategia = {"acao": "integra", "motivo": "Integra pedida no comando."}
            else:
                quantos = 5
                if documentos.startswith("ultimos:"):
                    try:
                        quantos = max(int(documentos.split(":", 1)[1]), 1)
                    except ValueError:
                        quantos = 5
                estrategia = {"acao": "ultimos", "quantos": quantos}

            if estrategia["acao"] == "integra":
                print("  COPIA INTEGRAL (pelo botao do portal)...")
                falhou = False
                try:
                    arquivo = _baixar_integra(
                        pagina, guarda, pasta, numero.apenas_digitos, segundos
                    )
                except Exception as exc:
                    arquivo, falhou = None, True
                    # So o nome do erro: o relato da tela, impresso acima, e o
                    # que serve para decidir o proximo passo. O despejo do log
                    # do Playwright sepultava esse relato.
                    print(f"    Copia integral nao concluida ({type(exc).__name__}).")
                if arquivo:
                    from pathlib import Path as _P

                    from .core.acervo import maior_evento

                    item = indice.acrescentar(
                        _P(arquivo), "integra",
                        evento_ate=maior_evento(dados["eventos"]),
                    )
                    print(f"    gravada: {_P(arquivo).name}  ({item.faixa()}), "
                          f"cobrindo ate o evento {item.evento_ate}")
                    estado_local.registrar(
                        acao="copia_integral", tribunal=identidade.tribunal,
                        sistema=identidade.sistema, numero=numero.formatado,
                        documento=arquivo, resultado=item.faixa(),
                    )
                elif not falhou:
                    print("    botao de copia integral nao encontrado nesta tela.")

            elif estrategia["acao"] == "complemento":
                faltantes = estrategia["faltantes"]
                if not faltantes:
                    print("    Nada a complementar.")
                else:
                    # Um evento sintetico por documento faltante preserva o
                    # vinculo com o evento de origem no nome do arquivo.
                    pendentes = [
                        {**f["evento"], "documentos": [f["documento"]]} for f in faltantes
                    ]
                    copia = baixar_documentos_dos_eventos(
                        pagina, guarda, pendentes, pasta, quantos_eventos=len(pendentes)
                    )
                    print(f"  COMPLEMENTO: {len(copia.gravadas)} documento(s)")
                    from pathlib import Path as _P

                    for c in copia.gravadas:
                        item = indice.acrescentar(
                            _P(c.arquivo), "documento", evento=c.evento, rotulo=c.rotulo
                        )
                        print(f"    ev{c.evento} {c.rotulo}  ->  {item.faixa()}")
                        estado_local.registrar(
                            acao="copia_documento", tribunal=identidade.tribunal,
                            sistema=identidade.sistema, numero=numero.formatado,
                            documento=c.arquivo, resultado=item.faixa(),
                        )
                    for c in copia.falhas:
                        print(f"    falhou ev{c.evento} {c.rotulo}: {c.erro}")

            else:
                quantos = estrategia["quantos"]
                print(f"  COPIAS DOS {quantos} EVENTO(S) MAIS RECENTES...")
                copia = baixar_documentos_dos_eventos(
                    pagina, guarda, dados["eventos"], pasta, quantos_eventos=quantos
                )
                from pathlib import Path as _P

                for linha in copia.resumo():
                    print(f"    {linha}")
                for c in copia.gravadas:
                    item = indice.acrescentar(
                        _P(c.arquivo), "documento", evento=c.evento, rotulo=c.rotulo
                    )
                    estado_local.registrar(
                        acao="copia_documento", tribunal=identidade.tribunal,
                        sistema=identidade.sistema, numero=numero.formatado,
                        documento=c.arquivo, resultado=item.faixa(),
                    )

            guarda.permitir_download = False
            if not indice.vazio:
                indice.gravar()
                print(f"\n  Acervo: {indice.ultima_folha} folha(s) em {indice.pasta}")

        print(f"\n  Conteudo completo em: {destino}")
        print("  O arquivo contem dado de cliente. Nao o cole em conversa nenhuma.")
        estado_local.registrar(
            acao="consulta_processo_autenticada", tribunal=identidade.tribunal,
            sistema=identidade.sistema, numero=numero.formatado,
            resultado=f"{dados['totais']['eventos']} evento(s)",
        )
        return 0

    return autenticar(
        url, tribunal, sistema, confirmado=confirmado, perfil=perfil,
        campo_usuario=campo_usuario, campo_senha=campo_senha,
        campo_senha_oculto=campo_senha_oculto, botao_entrar=botao_entrar,
        campo_codigo=campo_codigo, botao_validar=botao_validar,
        oculto=oculto, segundos=segundos, espera_humana=espera_humana,
        reenviar=reenviar, cofre=cofre, estado=estado, apos_autenticar=depois,
    )


AJUDA_URL = ("endereco do portal; quando omitido, vem do .env "
             "(JUSTICA_PORTAL_<TRIBUNAL>_<SISTEMA>_URL)")


def _do_ambiente(args) -> None:
    """Completa endereco e perfil a partir do .env quando nao vieram no comando.

    O endereco ja morava no ambiente para o servidor, mas a linha de comando o
    exigia de novo a cada execucao. Repetir o endereco a mao convida a errar o
    destino da autenticacao, que e exatamente o que este projeto nao pode
    deixar acontecer. O que vier no comando continua tendo precedencia.
    """
    if (getattr(args, "url", None)
            and getattr(args, "perfil", "ausente") is not None
            and getattr(args, "processo", "ausente") is not None):
        return
    try:
        config = config_portal(args.tribunal, args.sistema)
    except PortalNaoConfigurado:
        if not getattr(args, "url", None):
            raise
        return
    if not args.url:
        args.url = config.url
        print(f"Endereco vindo do .env para {config.rotulo}.")
    if getattr(args, "perfil", "ausente") is None and config.perfil:
        args.perfil = config.perfil
    if getattr(args, "processo", "ausente") is None:
        # Quando o portal tem processo de teste dos dois graus, `--grau 2` diz
        # qual usar. Sem indicacao fica o de primeiro grau, que e o caso comum.
        grau = getattr(args, "grau", 1) or 1
        escolhido = config.processo_teste_2g if grau == 2 else config.processo_teste
        if escolhido is None and grau == 2:
            escolhido = config.processo_teste
        if escolhido:
            args.processo = escolhido
            print(f"Processo vindo do .env para {config.rotulo} "
                  f"({'2º' if grau == 2 else '1º'} grau).")


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
    e.add_argument("--url", default=None, help=AJUDA_URL)
    e.add_argument("--tribunal", required=True, help="por exemplo TRF2")
    e.add_argument("--sistema", required=True, help="por exemplo eproc")
    e.add_argument("--campo-usuario", default="#txtUsuario")
    e.add_argument("--campo-senha", default="#pwdSenha")
    e.add_argument("--campo-senha-oculto", default="input[name=pwdSenha]")
    e.add_argument("--botao-entrar", default="#sbmEntrar",
                   help="conferido, NUNCA clicado: o ensaio so relata se ele habilitou")
    e.add_argument("--oculto", action="store_true")
    e.add_argument("--segundos", type=int, default=30)
    e.add_argument("--espera-humana", type=int, default=ESPERA_HUMANA_PADRAO, dest="espera_humana",
                     help="segundos para o operador marcar a caixa do desafio do Cloudflare")

    t = sub.add_parser("entrar", help="envia o login UMA vez e le a tela seguinte")
    t.add_argument("--url", default=None, help=AJUDA_URL)
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
    t.add_argument("--espera-humana", type=int, default=ESPERA_HUMANA_PADRAO, dest="espera_humana",
                     help="segundos para o operador marcar a caixa do desafio do Cloudflare")

    a = sub.add_parser("autenticar", help="credencial e segundo fator, numa sessao so")
    a.add_argument("--url", default=None, help=AJUDA_URL)
    a.add_argument("--tribunal", required=True)
    a.add_argument("--sistema", required=True)
    a.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado")
    a.add_argument("--campo-usuario", default="#txtUsuario")
    a.add_argument("--campo-senha", default="#pwdSenha")
    a.add_argument("--campo-senha-oculto", default="input[name=pwdSenha]")
    a.add_argument("--botao-entrar", default="#sbmEntrar")
    a.add_argument("--campo-codigo", default="#txtAcessoCodigo")
    a.add_argument("--botao-validar", default="#btnValidar")
    a.add_argument("--reconhecer-apos", action="append", default=None,
                   dest="reconhecer_apos",
                   help="apos autenticar, LE a estrutura desta tela interna; pode ser "
                        "repetido para varias telas na mesma autenticacao. Nao clica "
                        "nem preenche nada em nenhuma delas")
    a.add_argument("--perfil", default=None,
                   help="inscricao a usar quando houver mais de um perfil, "
                        "por exemplo RJ168943")
    a.add_argument("--oculto", action="store_true")
    a.add_argument("--segundos", type=int, default=45)
    a.add_argument("--espera-humana", type=int, default=ESPERA_HUMANA_PADRAO, dest="espera_humana",
                     help="segundos para o operador marcar a caixa do desafio do Cloudflare")
    a.add_argument("--reenviar-apos-desafio", action="store_true",
                     dest="reenviar",
                     help="reenvia a credencial na hora se o portal voltar ao login apos o desafio, e so quando nao houver mensagem de erro")

    cp = sub.add_parser("consultar", help="autentica e consulta um processo pela busca rapida")
    cp.add_argument("--url", default=None, help=AJUDA_URL)
    cp.add_argument("--tribunal", required=True)
    cp.add_argument("--sistema", required=True)
    cp.add_argument("--grau", type=int, choices=(1, 2), default=1,
                    help="qual processo de teste usar quando --processo e omitido; "
                         "o grau do processo informado e deduzido do proprio numero")
    cp.add_argument("--processo", default=None,
                    help="numero no padrao da numeracao unica; quando omitido, vem do .env "
                         "(JUSTICA_PORTAL_<TRIBUNAL>_<SISTEMA>_PROCESSO_TESTE)")
    cp.add_argument("--campo-usuario", default="#txtUsuario")
    cp.add_argument("--campo-senha", default="#pwdSenha")
    cp.add_argument("--campo-senha-oculto", default="input[name=pwdSenha]")
    cp.add_argument("--botao-entrar", default="#sbmEntrar")
    cp.add_argument("--campo-codigo", default="#txtAcessoCodigo")
    cp.add_argument("--botao-validar", default="#btnValidar")
    cp.add_argument("--perfil", default=None)
    cp.add_argument("--documentos", default="auto",
                    help="'auto' (padrao: integra se nao ha copia, complemento se ha), "
                         "'integra', 'ultimos:N' ou 'nenhum'")
    cp.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado")
    cp.add_argument("--oculto", action="store_true")
    cp.add_argument("--segundos", type=int, default=45)
    cp.add_argument("--espera-humana", type=int, default=ESPERA_HUMANA_PADRAO, dest="espera_humana",
                      help="segundos para o operador marcar a caixa do desafio do Cloudflare")
    cp.add_argument("--reenviar-apos-desafio", action="store_true",
                      dest="reenviar",
                      help="reenvia a credencial na hora se o portal voltar ao login apos o desafio, e so quando nao houver mensagem de erro")

    args = p.parse_args(argv)

    # O .env nunca era lido aqui: so o servidor o carregava. Quem configurasse
    # a pasta de copias ou o endereco do portal no arquivo via a linha de
    # comando ignorar tudo, em silencio, e gravar no lugar antigo.
    carregar_env()

    try:
        if args.comando != "reconhecer":
            _do_ambiente(args)
        if args.comando == "reconhecer":
            return reconhecer(args.url, oculto=args.oculto, segundos=args.segundos)
        if args.comando == "consultar":
            if not args.processo:
                print(
                    "Nenhum processo informado. Passe --processo, ou defina no .env:\n"
                    f"    JUSTICA_PORTAL_{args.tribunal.upper()}_{args.sistema.upper()}"
                    "_PROCESSO_TESTE=<numero>",
                    file=sys.stderr,
                )
                return 1
            return consultar_processo(
                args.url, args.tribunal, args.sistema, args.processo,
                campo_usuario=args.campo_usuario, campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto, botao_entrar=args.botao_entrar,
                campo_codigo=args.campo_codigo, botao_validar=args.botao_validar,
                documentos=args.documentos, confirmado=args.confirmado,
                perfil=args.perfil, oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana, reenviar=args.reenviar,
            )
        if args.comando == "autenticar":
            return autenticar(
                args.url, args.tribunal, args.sistema, confirmado=args.confirmado,
                campo_usuario=args.campo_usuario, campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto, botao_entrar=args.botao_entrar,
                campo_codigo=args.campo_codigo, botao_validar=args.botao_validar,
                perfil=args.perfil, oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana, reenviar=args.reenviar,
                reconhecer_apos=args.reconhecer_apos,
            )
        if args.comando == "entrar":
            return entrar(
                args.url, args.tribunal, args.sistema, confirmado=args.confirmado,
                campo_usuario=args.campo_usuario, campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto, botao_entrar=args.botao_entrar,
                oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana,
            )
        if args.comando == "ensaiar-login":
            return ensaiar_login(
                args.url, args.tribunal, args.sistema,
                campo_usuario=args.campo_usuario,
                campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto,
                botao_entrar=args.botao_entrar,
                oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana,
            )
    except (PortalIndisponivel, PortalNaoConfigurado) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
