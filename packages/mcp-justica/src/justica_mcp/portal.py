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
from datetime import timedelta
from typing import Any, Optional
from urllib.parse import urlparse

from .core.acesso import PortalNaoConfigurado, config_portal, portais_configurados
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


# Falhas de REDE, que nao sao defeito do programa nem do portal. O Chromium as
# devolve com estes nomes, e sem traducao elas sobem como traceback do
# Playwright no meio de uma autenticacao: trinta linhas de pilha para dizer
# "a internet caiu". Visto em campo em 30/09/2026, com ERR_NAME_NOT_RESOLVED
# num endereco que tinha resolvido normalmente minutos antes.
RECADOS_DE_REDE = {
    "ERR_NAME_NOT_RESOLVED": (
        "o seu computador nao conseguiu traduzir o endereco do portal. O "
        "navegador nem chegou a falar com o tribunal: e a rede ou o servidor de "
        "nomes, nao o portal."),
    "ERR_INTERNET_DISCONNECTED": "o computador esta sem conexao.",
    "ERR_CONNECTION_TIMED_OUT": (
        "o portal aceitou a conexao e nao respondeu no tempo. Costuma ser "
        "instabilidade do proprio tribunal."),
    "ERR_CONNECTION_REFUSED": "o servidor do portal recusou a conexao.",
    "ERR_CONNECTION_RESET": "a conexao com o portal caiu no meio.",
    "ERR_CERT_": "o certificado do portal nao foi aceito pelo navegador.",
    "ERR_PROXY_": "o proxy configurado no computador barrou a conexao.",
}


def _ir_para(pagina, url: str, segundos: int) -> None:
    """Navega ate o endereco e traduz falha de rede em recado legivel.

    Nada foi enviado ao portal quando isto falha, entao nenhuma tentativa do
    teto da conta foi gasta. Dizer isso importa: sem essa frase o operador fica
    sem saber se pode repetir o comando.
    """
    try:
        pagina.goto(url, timeout=segundos * 1000, wait_until="domcontentloaded")
    except Exception as exc:
        texto = str(exc)
        for marca, explicacao in RECADOS_DE_REDE.items():
            if marca in texto:
                raise PortalIndisponivel(
                    f"  [REDE] Nao foi possivel abrir {url}: {explicacao}\n"
                    "  Nada foi enviado ao portal e nenhuma tentativa foi gasta.\n"
                    "  Confira a conexao e repita o comando."
                ) from None
        if "Timeout" in texto and "exceeded" in texto:
            raise PortalIndisponivel(
                f"  [REDE] {url} nao terminou de carregar em {segundos}s.\n"
                "  Nada foi enviado ao portal e nenhuma tentativa foi gasta.\n"
                f"  Se o portal estiver lento, repita com --segundos {segundos * 2}."
            ) from None
        raise


# Tempo que o operador tem para marcar a caixa do desafio. Generoso de
# proposito: e uma pessoa indo ate a janela, nao uma espera de rede.
ESPERA_HUMANA_PADRAO = 180

VARIAVEL_PERFIL_EFEMERO = "JUSTICA_NAVEGADOR_EFEMERO"


def pasta_de_descargas() -> "Path":
    """Pasta fixa onde o navegador escreve os arquivos baixados.

    Sem ela, o Playwright usa um diretorio temporario que so ele conhece e que
    some quando o navegador fecha: se o canal morre, o arquivo ja baixado fica
    irrecuperavel. Com pasta conhecida, o arquivo continua no disco e pode ser
    copiado por caminho de sistema de arquivos, sem depender de janela viva.
    """
    from pathlib import Path as _P

    from .core.estado import diretorio_estado

    destino = _P(diretorio_estado()) / "descargas"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


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
    descargas = str(pasta_de_descargas())
    if _perfil_efemero():
        navegador = p.chromium.launch(
            headless=oculto, executable_path=executavel, downloads_path=descargas
        )
        return navegador, navegador.new_page()

    contexto = p.chromium.launch_persistent_context(
        str(pasta_do_navegador()),
        headless=oculto,
        executable_path=executavel,
        accept_downloads=True,
        downloads_path=descargas,
    )
    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    return contexto, pagina


# Palavras que nomeiam campo de senha. Comparadas sem acento e em minusculas,
# contra nome, identificador e rotulo do campo.
MARCAS_DE_CAMPO_DE_SENHA = ("senha", "password", "passwd", "contrasena", "clave")


def parece_campo_de_senha(tipo, nome, identificador, rotulo, autocomplete=None) -> bool:
    """Diz se o campo guarda senha, sem depender so do atributo `type`.

    Ate 02/10/2026 a regra era `tipo == "password"`, e o comentario dizia que o
    tipo nao muda. A tela do eproc do Rio desmentiu isso: ela traz um olhinho de
    mostrar a senha (`span#showHidePwd`) que TROCA o tipo do campo para `text`.
    Lido em campo no mapa de 02/10/2026, com `#pwdSenha tipo=text`.

    O estrago e duplo e silencioso. O relato deixava de marcar o campo como
    SENHA, que e o aviso de que ali passa segredo; e `_tem_formulario_de_login`
    passava a dizer que a tela de login nao tem formulario de login, o que faz a
    conferencia de sessao cair em INDEFINIDO numa tela que e inequivoca.
    """
    if (tipo or "").lower() == "password":
        return True
    # SO `current-password`, e nao qualquer `autocomplete` com "password".
    # A primeira versao desta funcao aceitava os dois, e a tela de cadastro do
    # eproc do Rio desmentiu isso no mesmo dia (02/10/2026): ela marca CPF, RG,
    # orgao emissor e data de emissao com `autocomplete=new-password`, que ali
    # nao descreve senha nenhuma, e sim o pedido para o navegador nao preencher
    # o campo sozinho. O relato passou a estampar ** SENHA ** em cima do CPF, e,
    # pior, `_tem_formulario_de_login` passaria a ver formulario de login numa
    # tela de cadastro: a conferencia de sessao diria FECHADA com a sessao
    # aberta. `current-password` nao tem esse uso desviado.
    if (autocomplete or "").strip().lower() == "current-password":
        return True
    texto = sem_acento(" ".join(p for p in (nome, identificador, rotulo) if p))
    return any(marca in texto for marca in MARCAS_DE_CAMPO_DE_SENHA)


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
            partes.append(f"rotulo={sem_dado_de_processo(self.rotulo)!r}")
        if self.texto_visivel:
            partes.append(f"texto={sem_dado_de_processo(self.texto_visivel)!r}")
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


def janela_de(pagina: Any) -> dict:
    """Tamanho da janela, tolerando QUADRO EMBUTIDO.

    Quadro embutido nao tem `viewport_size`: so a pagina tem. Ler a estrutura
    de dentro de um quadro quebrava com AttributeError, e o eproc do Rio abre a
    integra do processo justamente dentro de um quadro.
    """
    try:
        return pagina.viewport_size or {"width": 1280, "height": 720}
    except AttributeError:
        return {"width": 1280, "height": 720}


# Quantas opcoes de uma lista de escolha cabem no relato, o tamanho maximo de
# um valor, e a partir de quantos digitos uma sequencia so de numeros deixa de
# ser codigo e passa a cheirar a documento.
TETO_DE_OPCOES = 30
TAMANHO_DE_CODIGO = 24
DIGITOS_QUE_VIRAM_DOCUMENTO = 8


def parece_codigo(valor: str) -> bool:
    """Se o valor de uma opcao e vocabulario da pagina, e nao dado de alguem.

    Lista de escolha sem as opcoes e indocumentavel: o relato mostra que ha um
    `select` e nao diz o que escolher, e foi o que aconteceu com a tela de
    selecao de sistemas do Tribunal de Justica do Rio de Janeiro em 06/10/2026.
    Imprimir tudo tambem nao serve: a mesma etiqueta `select` serve para
    escolher o sistema e para escolher entre processos de clientes, e o relato
    e colado em conversa.

    A primeira versao cortava por tamanho, em doze caracteres, e escondeu
    justamente o que o operador procurava: `PORTALSERVICOS` tem quatorze. O
    tamanho era a medida errada. O que separa codigo de dado nao e o
    comprimento e sim a FORMA:

      - espaco ou pontuacao derrubam, e isso ja basta para nome de parte
        ("Fulano de Tal") e para numero de processo formatado
        ("0854091-62.2024.8.19.0001");
      - sequencia so de digitos com oito ou mais derruba tambem, e e esta
        linha que protege o que o tamanho nunca protegeu: numero de processo
        sem pontuacao tem vinte, cadastro de pessoa fisica tem onze, de pessoa
        juridica tem quatorze. Nenhum dos tres passa;
      - valor curto so de digitos ("1", "2") passa, porque e indice de lista e
        nao diz nada sobre ninguem.

    O que nao passa e CONTADO, nunca impresso.
    """
    limpo = (valor or "").strip()
    if not limpo or len(limpo) > TAMANHO_DE_CODIGO:
        return False
    if not limpo.replace("_", "").replace("-", "").isalnum():
        return False
    so_digitos = limpo.replace("_", "").replace("-", "")
    return not (so_digitos.isdigit() and len(so_digitos) >= DIGITOS_QUE_VIRAM_DOCUMENTO)


def opcoes_de_escolha(elemento) -> Optional[str]:
    """Resumo das opcoes de um `select`: os codigos, e a conta do resto."""
    try:
        valores = elemento.evaluate(
            "e => Array.from(e.options || []).map(o => o.value)")
    except Exception:
        return None
    if not valores:
        return None
    codigos = [v for v in valores if parece_codigo(v)]
    escondidos = len(valores) - len(codigos)
    partes = []
    if codigos:
        partes.append("|".join(codigos[:TETO_DE_OPCOES]))
        if len(codigos) > TETO_DE_OPCOES:
            partes.append(f"e mais {len(codigos) - TETO_DE_OPCOES}")
    if escondidos:
        # Contadas e nao impressas: valor que nao tem forma de codigo pode ser
        # numero de processo ou nome de parte.
        partes.append(f"{escondidos} sem forma de codigo, nao impressa(s)")
    return f"{len(valores)}: " + "; ".join(partes) if partes else str(len(valores))


def _coletar(pagina: Any) -> tuple[list[Campo], list[Campo]]:
    """Le a estrutura do formulario. Somente leitura do DOM."""
    janela = janela_de(pagina)
    largura, altura = janela["width"], janela["height"]
    campos: list[Campo] = []
    for elemento in pagina.query_selector_all("input, select, textarea"):
      # Um elemento que some no meio da leitura nao pode custar o relato
      # inteiro. Aplicacao de pagina unica remonta a tela sozinha, e o
      # identificador que ja tinha sido pego vira referencia morta: o
      # Playwright levanta erro no proximo toque. Em 06/10/2026 isso derrubou
      # a leitura do visualizador de processos do Tribunal de Justica do Rio
      # de Janeiro, que era justamente a tela que importava, e o relato saiu
      # com uma linha de erro no lugar de tudo.
      try:
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
        if marcador == "select":
            resumo = opcoes_de_escolha(elemento)
            if resumo:
                extras["opcoes"] = resumo

        campos.append(Campo(
            marcador=marcador,
            tipo=tipo,
            nome=elemento.get_attribute("name"),
            identificador=identificador,
            rotulo=rotulo or elemento.get_attribute("aria-label") or elemento.get_attribute("placeholder"),
            texto_visivel=None,
            e_senha=parece_campo_de_senha(
                tipo, elemento.get_attribute("name"), identificador,
                rotulo or elemento.get_attribute("aria-label")
                or elemento.get_attribute("placeholder"),
                extras.get("autocomplete"),
            ),
            visivel=elemento.is_visible(),
            na_tela=_na_tela(elemento, largura, altura),
            habilitado=elemento.is_enabled(),
            formulario=elemento.evaluate("e => e.form ? (e.form.id || e.form.name || 'sem-nome') : null"),
            extras=extras,
        ))
      except Exception:
        continue

    botoes: list[Campo] = []
    for elemento in pagina.query_selector_all(
        "button, input[type=submit], input[type=button], a[role=button]"
    ):
      try:
        texto = (elemento.inner_text() or elemento.get_attribute("value") or "").strip()
        # Botao de icone nao tem texto. Sem o rotulo acessivel, ele aparece no
        # relato como `(sem id)  ''` e nao serve para nada. Foi assim que a tela
        # do processo do eproc do Rio, em 05/10/2026, mostrou quatro botoes
        # mudos: podiam ser qualquer coisa, inclusive o de copiar os autos.
        rotulo_acessivel = None
        for atributo in ("aria-label", "title", "alt"):
            valor = (elemento.get_attribute(atributo) or "").strip()
            if valor:
                rotulo_acessivel = valor[:60]
                break
        botoes.append(Campo(
            marcador=elemento.evaluate("e => e.tagName.toLowerCase()"),
            tipo=(elemento.get_attribute("type") or "").lower(),
            nome=elemento.get_attribute("name"),
            identificador=elemento.get_attribute("id"),
            rotulo=rotulo_acessivel,
            texto_visivel=texto[:50] or None,
            e_senha=False,
            visivel=elemento.is_visible(),
            na_tela=_na_tela(elemento, largura, altura),
            habilitado=elemento.is_enabled(),
            formulario=elemento.evaluate("e => e.form ? (e.form.id || e.form.name || 'sem-nome') : null"),
            extras={},
        ))
      except Exception:
        continue
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
            _ir_para(pagina, url, segundos)
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
            # Fecha as abas antes do navegador. Uma aba aberta pela pagina de
            # passagem deixava o fechamento pendurado, e o operador precisou
            # interromper a execucao com o teclado. Erro ao fechar nao pode
            # custar o resultado: a consulta ja terminou aqui.
            try:
                for _aba in list(getattr(navegador, "pages", []) or []):
                    try:
                        _aba.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                navegador.close()
            except Exception:
                pass

    print("\n" + "=" * LARGURA)
    print("  Nada foi preenchido, clicado ou autenticado.")
    print("  Cole este relatorio para eu escrever o passo de autenticacao.")
    print("  Nenhum dado de processo aparece aqui: so a estrutura da pagina.")
    return 0




def _aba_em_foco(navegador, inicial):
    """A aba que o operador esta vendo, que nem sempre e a que o programa abriu.

    O IdServerJus do Tribunal de Justica do Rio de Janeiro abre o sistema
    escolhido em JANELA NOVA. Ler a aba inicial depois disso descreveria a tela
    de selecao, que o operador ja deixou para tras, e o relato diria que nada
    mudou enquanto ele olha para outra coisa.

    Prefere a ultima aba aberta e viva; se nao houver nenhuma, volta para a
    inicial, porque relatar a tela errada e melhor que nao relatar nada e
    sumir com um erro de atributo.
    """
    try:
        abas = [a for a in (getattr(navegador, "pages", None) or []) if not a.is_closed()]
    except Exception:
        abas = []
    return abas[-1] if abas else inicial


def acompanhar(url: str, *, segundos: int = 30, teto: int = 20) -> int:
    """O OPERADOR navega e o programa so le a tela onde ele parar.

    Nasceu de uma pergunta do advogado em 06/10/2026: "eu posso mostrar o
    caminho clicando?". Pode, e e mais rapido que qualquer outra coisa. Ate
    aqui, descobrir um caminho de portal custava uma rodada inteira por tela:
    eu pedia um relato, ele colava, eu escrevia o passo seguinte as cegas, e
    quando o passo errava o preco as vezes era uma tentativa de login.

    A inversao e o ponto. Quem conhece o portal e quem clica; quem precisa dos
    identificadores e quem le. O programa nao navega, nao preenche e nao
    clica, e a trava fica em modo ensaio para que isso nao dependa da minha
    boa memoria: qualquer acao do programa seria barrada por ela.

    O que SAI no relato: endereco, titulo, campos, botoes, caminhos sem texto
    e sem parametro, e a estrutura das tabelas. O que NAO sai: texto de celula.
    Mesmo assim a escolha de qual tela registrar e do advogado, tela por tela,
    porque e ele quem sabe o que ha em cada uma.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    if not sys.stdin or not sys.stdin.isatty():
        print("  [PARADO] Este comando precisa de terminal: quem conduz e voce.",
              file=sys.stderr)
        return 1

    guarda = GuardaNavegacao(
        modo=Modo.ENSAIO,
        permissoes=[permissao_de_origem(url, "acompanhamento conduzido pelo operador")],
    )

    print("=" * LARGURA)
    print("ACOMPANHAR O CAMINHO".center(LARGURA))
    print("=" * LARGURA)
    print(f"Endereco de partida: {url}")
    print("Quem navega e VOCE. O programa nao clica, nao preenche e nao navega.")
    print("A sessao ja aberta neste perfil continua valendo, entao nenhuma")
    print("tentativa de login e gasta aqui.\n")
    print("  Como funciona:")
    print("    1. a janela abre no endereco acima;")
    print("    2. voce clica ate a tela que quer me mostrar;")
    print("    3. volta aqui e aperta Enter: eu leio e descrevo aquela tela;")
    print("    4. repete quantas vezes quiser, e escreve 'fim' para encerrar.\n")
    print("  O relato traz endereco, titulo, campos, botoes, caminhos sem texto")
    print("  nem parametro, e a forma das tabelas. NAO traz texto de celula.")
    print("  Ainda assim, quem decide qual tela registrar e voce.\n")

    executavel = os.environ.get("JUSTICA_CHROMIUM") or None
    registradas = 0
    with sync_playwright() as p:
        navegador, pagina = abrir_navegador(p, False, executavel)
        try:
            guarda.avaliar(Acao.NAVEGAR, url).exigir()
            _ir_para(pagina, url, segundos)
            _assentar(pagina, segundos)

            while registradas < teto:
                _esvaziar_teclado()
                try:
                    resposta = input(
                        f"  Enter para registrar a tela ({registradas}/{teto} ja "
                        "registradas), ou 'fim': ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n  Encerrado por voce.")
                    break
                if resposta in ("fim", "sair", "parar", "f"):
                    break

                alvo = _aba_em_foco(navegador, pagina)
                try:
                    _assentar(alvo, segundos)
                except Exception:
                    pass
                registradas += 1
                print()
                try:
                    _relatar_tela(alvo, f"TELA {registradas}")
                    _relatar_estrutura_de_dados(alvo)
                except Exception as exc:
                    # Janela fechada no meio da leitura e o caso comum, e nao
                    # pode derrubar o que ja foi registrado.
                    print(f"    Nao consegui ler esta tela: {type(exc).__name__}.")
                    print("    Se a janela fechou, abra de novo e aperte Enter.")
                print()
            if registradas >= teto:
                print(f"  Teto de {teto} telas atingido.")
        finally:
            try:
                for _aba in list(getattr(navegador, "pages", []) or []):
                    try:
                        _aba.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                navegador.close()
            except Exception:
                pass

    print("\n" + "=" * LARGURA)
    print(f"  {registradas} tela(s) registrada(s).")
    print("  O programa nao clicou, nao preencheu e nao navegou: tudo o que")
    print("  aconteceu na janela foi voce quem fez.")
    print("  RELATO DA TRAVA:")
    for linha in guarda.relato():
        print(f"    {linha}")
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
            _ir_para(pagina, url, segundos)

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
                el = achar_opcional(pagina, botao_entrar)
                if el is None:
                    return None
                return el.is_enabled()

            habilitado_antes = _estado_do_botao()

            for seletor, valor, rotulo in (
                (campo_usuario, login, "usuario"),
                (campo_senha, senha, "senha"),
            ):
                elemento = achar_opcional(pagina, seletor)
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
            oculto_el = achar_opcional(pagina, campo_senha_oculto)
            visivel_el = achar_opcional(pagina, campo_senha)
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
            # Fecha as abas antes do navegador. Uma aba aberta pela pagina de
            # passagem deixava o fechamento pendurado, e o operador precisou
            # interromper a execucao com o teclado. Erro ao fechar nao pode
            # custar o resultado: a consulta ja terminou aqui.
            try:
                for _aba in list(getattr(navegador, "pages", []) or []):
                    try:
                        _aba.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                navegador.close()
            except Exception:
                pass

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


# Recados que NAO sao recusa de credencial: a senha esta certa e venceu. A
# diferenca muda tudo o que se faz em seguida. Diante de "credencial recusada"
# o certo e parar e conferir o cofre; diante de senha vencida, conferir o cofre
# nao adianta nada, e insistir queima tentativas de uma conta cuja senha o
# portal ja nao aceita mais. Lido do PJe do Rio em 30/09/2026.
MARCAS_DE_SENHA_VENCIDA = (
    "senha expirada", "senha vencida", "senha esta vencida",
    "senha esta expirada", "senha e expirada",
    "expire", "solicite uma nova senha", "redefina sua senha",
    "alterar a senha", "trocar a senha", "password has expired",
)


def sem_acento(texto: str) -> str:
    """Minusculas e sem acento, para comparar rotulo de tela com marca fixa."""
    import unicodedata

    decomposto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


# Enderecos que o proprio navegador usa quando NAO conseguiu carregar a pagina.
# Nao sao telas do portal: sao a ausencia de tela.
MARCAS_DE_PAGINA_DE_ERRO = ("chrome-error://", "about:neterror", "edge-error://")


def clicar_tolerando_lentidao(elemento, alvo: str, segundos: int) -> None:
    """Clica e aceita que a navegacao seguinte demore mais que o teto.

    O Playwright espera, depois do clique, pelas navegacoes que o clique
    disparou. Se o portal demora, essa espera estoura e o erro sai como se o
    CLIQUE tivesse falhado. A diferenca e enorme: no login, um clique que falhou
    nao enviou nada e pode ser refeito; um clique que aconteceu ja gastou a
    tentativa, e refazer gasta outra.

    O proprio registro do Playwright separa os dois casos, e e nele que esta
    escrito o que de fato ocorreu. Visto em campo em 05/10/2026, no eproc do Rio,
    logo depois de o portal ter ficado fora do ar:

        - performing click action
        - click action done
        - waiting for scheduled navigations to finish   <- estourou AQUI

    Quando o registro diz que o clique foi feito, seguir em frente e o certo: a
    tela seguinte sera lida como sempre, e dira o que aconteceu. Quando nao diz,
    o erro sobe inteiro, porque ai o clique realmente nao saiu.
    """
    try:
        elemento.click(timeout=segundos * 1000)
    except Exception as exc:
        if "click action done" not in str(exc):
            raise
        print(f"    O clique em {alvo} ACONTECEU; o que estourou foi a espera pela")
        print("    navegacao seguinte. O portal esta lento. Nada foi repetido.")


# Onde portais costumam pendurar aviso que aparece por cima da tela. A lista e
# larga de proposito: cada aplicacao usa a sua, e aqui o custo de olhar num
# lugar a mais e zero, enquanto o custo de nao ver o recado e uma execucao
# inteira perdida.
MARCAS_DE_AVISO = (
    "[role=alert]", ".alert", ".toast", ".snackbar", ".notification",
    ".mensagem", ".message", ".v-alert", ".el-message", ".p-toast",
    ".swal2-html-container", ".modal-body",
)

# Texto dos botoes de fechar. Quando a aplicacao nao usa nenhuma classe
# conhecida, ELES sao a pista: um "x" que apareceu depois do envio da credencial
# quer dizer que algo foi aberto para ser lido e fechado. Visto na Central do
# Processo Eletronico do Superior Tribunal de Justica em 05/10/2026, onde o
# relato mostrou dois "x" novos e nenhuma mensagem.
MARCAS_DE_FECHAR = ("x", "✕", "×", "fechar", "close")


def avisos_na_tela(pagina, teto: int = 400) -> list[str]:
    """O que o portal escreveu em caixa de aviso, se houver.

    Serve para tela de SISTEMA, como a de login. Nao e para tela de processo: ali
    o texto da pagina e dado de cliente, e este projeto nao o imprime.
    """
    vistos, saida = set(), []

    def guardar(texto: str) -> None:
        limpo = " ".join((texto or "").split())[:teto]
        # Caixa cujo unico conteudo e o proprio botao de fechar nao tem recado
        # nenhum, e imprimi-la como "AVISO NA TELA: x" so atrapalha a leitura.
        if sem_acento(limpo) in MARCAS_DE_FECHAR:
            return
        if limpo and limpo not in vistos:
            vistos.add(limpo)
            saida.append(limpo)

    for marca in MARCAS_DE_AVISO:
        try:
            for alvo in pagina.query_selector_all(marca):
                if alvo.is_visible():
                    guardar(alvo.inner_text())
        except Exception:
            continue

    # O caminho do botao de fechar: sobe um nivel e le o que esta junto dele.
    try:
        for alvo in pagina.query_selector_all(ALVOS_CLICAVEIS):
            if not alvo.is_visible():
                continue
            texto = sem_acento(alvo.inner_text() or "").strip()
            if texto not in MARCAS_DE_FECHAR:
                continue
            guardar(alvo.evaluate(
                "e => e.parentElement ? e.parentElement.innerText : ''"))
    except Exception:
        pass
    return saida


# ==========================================================================
# De onde vem o codigo do segundo fator
#
# Duas telas parecidas pedem a mesma coisa e esperam codigos de origem
# diferente: a do aplicativo autenticador, que o cofre sabe gerar da semente,
# e a do codigo que o PROPRIO portal enviou por mensagem ou e-mail, que so a
# pessoa tem. Ter semente guardada decidia sozinho qual usar, e nas contas que
# bloqueiam por tentativa isso custa caro: a semente gera um numero que a tela
# nunca aceitaria, e a tentativa vai embora sem ninguem saber por que.
#
# Ler o que a tela ESCREVEU separa os dois de graca, antes do envio.
# ==========================================================================

MARCAS_DE_CODIGO_DO_APLICATIVO = (
    "aplicativo de autenticacao", "aplicativo autenticador",
    "aplicativo de autenticador", "autenticador", "authenticator",
    "aplicativo movel", "gerado pelo aplicativo", "codigo do aplicativo",
    "one-time", "otp",
)

MARCAS_DE_CODIGO_ENVIADO = (
    "enviamos", "foi enviado", "enviado para", "enviado ao",
    "reenviar codigo", "receber novo codigo", "reenviar o codigo",
    "sms", "mensagem de texto", "torpedo",
    "e-mail cadastrado", "email cadastrado", "caixa de entrada",
    "celular cadastrado", "telefone cadastrado",
)


def classificar_origem_do_codigo(texto: str) -> Optional[str]:
    """`aplicativo`, `enviado`, ou None quando a tela nao disse.

    O aplicativo ganha do envio quando as duas marcas aparecem. Motivo: a
    palavra "enviar" cabe no botao de qualquer uma das duas telas, enquanto
    "aplicativo de autenticacao" nao aparece por acaso numa tela que manda
    codigo por e-mail.

    Nenhuma marca encontrada devolve None, e None NAO e "enviado": na duvida o
    comando segue como seguia antes, porque chutar a origem errada e o defeito
    que esta funcao existe para evitar, e ele vale nos dois sentidos.
    """
    limpo = sem_acento(texto or "")
    if any(marca in limpo for marca in MARCAS_DE_CODIGO_DO_APLICATIVO):
        return "aplicativo"
    if any(marca in limpo for marca in MARCAS_DE_CODIGO_ENVIADO):
        return "enviado"
    return None


def texto_ao_redor(pagina, campo=None, teto: int = 1200) -> str:
    """O texto do formulario em volta do campo, ou o da tela inteira.

    Vale para tela de SISTEMA, como a de login e a do segundo fator. Nao e para
    tela de processo: ali o texto da pagina e dado de cliente, e este projeto
    nao o le.
    """
    if campo is not None:
        try:
            texto = campo.evaluate(
                "e => { const f = e.closest('form') || e.parentElement; "
                "return f ? f.innerText : ''; }")
            if texto and texto.strip():
                return " ".join(texto.split())[:teto]
        except Exception:
            pass
    try:
        return " ".join((pagina.inner_text("body") or "").split())[:teto]
    except Exception:
        return ""


def origem_do_codigo(pagina, campo=None) -> Optional[str]:
    """Le a tela do segundo fator e diz de onde o codigo deveria vir."""
    return classificar_origem_do_codigo(texto_ao_redor(pagina, campo))

def _valor_de(elemento) -> str:
    try:
        return elemento.evaluate("e => e.value || ''")
    except Exception:
        return ""


def mesmo_conteudo(escrito: str, pretendido: str) -> bool:
    """Se o que esta no campo e o mesmo valor, ainda que com outra aparencia.

    Mascara muda a APARENCIA, nao o conteudo: digita-se 13169898795 e o campo
    mostra 131.698.987-95. Comparar os dois textos letra a letra conclui que
    nada foi escrito, quando o campo esta certo.

    Foi o que aconteceu na Central do Processo Eletronico do Superior Tribunal
    de Justica em 05/10/2026: o comando abortou dizendo que o campo nao ficou
    com o valor, depois de duas tentativas de escrita que podem ter funcionado.

    A comparacao por digitos vale SO para valor que e todo digito, como CPF ou
    numero de processo. Para senha, onde nao ha mascara, a igualdade continua
    sendo exata, e tem de ser: afrouxar ali seria aceitar senha errada.
    """
    if escrito == pretendido:
        return True
    so_digitos = re.sub(r"\D", "", pretendido)
    if len(so_digitos) >= 5 and so_digitos == pretendido:
        return re.sub(r"\D", "", escrito or "") == so_digitos
    return False


def preencher_conferindo(elemento, valor: str, rotulo: str) -> bool:
    """Preenche e CONFERE que o valor ficou no campo. Devolve se ficou.

    Nasceu da Central do Processo Eletronico do Superior Tribunal de Justica,
    em 05/10/2026. O `fill` nao levantou erro nenhum, o botao foi clicado, a
    tentativa foi gasta, e o portal respondeu "O campo CPF deve ser preenchido".
    O campo chegou vazio do outro lado.

    Dois jeitos de escrever, nesta ordem. O `fill` resolve a maioria dos portais
    e e instantaneo. Quando ele nao pega, a digitacao tecla a tecla resolve o
    resto: campo controlado por framework de pagina unica, ou com mascara, as
    vezes so reconhece o que veio de teclado de verdade, porque e a sequencia de
    eventos de tecla que dispara a atualizacao interna.

    A conferencia importa mais que os dois: ela separa "nao consegui escrever"
    de "escrevi e o portal recusou", e essa diferenca decide se repetir o
    comando e util ou se so queima mais uma tentativa da conta.
    """
    elemento.click()
    elemento.fill(valor)
    if mesmo_conteudo(_valor_de(elemento), valor):
        return True

    print(f"    O campo de {rotulo} nao aceitou o preenchimento direto; "
          "digitando tecla a tecla.")
    try:
        elemento.fill("")
        elemento.type(valor, delay=30)
    except Exception as exc:
        print(f"    A digitacao falhou ({type(exc).__name__}).")
        return False
    final = _valor_de(elemento)
    if mesmo_conteudo(final, valor):
        return True
    # A FORMA do que sobrou, nunca o conteudo: o valor e dado pessoal. Saber se
    # o campo ficou vazio ou pela metade separa duas causas diferentes, e sem
    # isso a proxima tentativa seria no escuro.
    print(f"    O campo ficou com {len(final)} caractere(s) e esperava "
          f"{len(valor)}.")
    return False


def pagina_de_erro_do_navegador(endereco: str) -> bool:
    """Se o endereco atual e pagina de erro do navegador, e nao do portal."""
    baixo = (endereco or "").lower()
    return any(marca in baixo for marca in MARCAS_DE_PAGINA_DE_ERRO)


# Pagina de erro do SERVIDOR, que nao e a mesma coisa que pagina de erro do
# navegador. Ali o navegador nao chegou ao servidor; aqui o servidor respondeu,
# e o que ele respondeu foi um erro dele.
MARCAS_DE_ERRO_DO_SERVIDOR = (
    "service temporarily unavailable", "service unavailable",
    "temporarily unavailable", "bad gateway", "gateway time-out",
    "gateway timeout", "internal server error",
    "temporariamente indisponivel", "servico indisponivel",
    "servidor indisponivel", "em manutencao", "manutencao programada",
)

CODIGOS_DE_ERRO_DO_SERVIDOR = ("500", "502", "503", "504")


def erro_do_servidor(pagina) -> Optional[str]:
    """O titulo da pagina de erro do portal, quando e isso que esta na tela.

    Existe porque uma tela sem campo nenhum tinha uma explicacao so, e ela era
    a errada. Em 06/10/2026 o PJe do Rio respondeu "503 Service Temporarily
    Unavailable", e o comando anunciou que o campo de usuario nao foi
    encontrado. As duas frases sao verdadeiras e levam a lugares opostos: uma
    manda procurar seletor que mudou, a outra manda esperar o portal voltar.
    """
    try:
        titulo = " ".join((pagina.title() or "").split())
    except Exception:
        return None
    if not titulo:
        return None
    baixo = sem_acento(titulo)
    if any(marca in baixo for marca in MARCAS_DE_ERRO_DO_SERVIDOR):
        return titulo
    # Titulo que COMECA com o numero do erro, como "503 Service ...". Exigir o
    # comeco de proposito: um numero solto no meio de um titulo qualquer nao
    # transforma a tela em pagina de erro.
    primeiro = baixo.split(" ", 1)[0].strip(":-")
    if primeiro in CODIGOS_DE_ERRO_DO_SERVIDOR:
        return titulo
    return None


def senha_vencida(recados) -> bool:
    """Diz se algum recado da tela e de senha vencida.

    Compara sem acento de proposito: o mesmo aviso aparece escrito de varias
    formas ("senha expirada", "sua senha esta vencida"), e um acento a mais ou
    a menos nao pode decidir se o operador vai renovar a senha ou procurar
    defeito no cofre.
    """
    for recado in recados or []:
        limpo = sem_acento(recado)
        if any(sem_acento(marca) in limpo for marca in MARCAS_DE_SENHA_VENCIDA):
            return True
    return False


def _mensagens_de_erro(pagina: Any) -> list[str]:
    saida = []
    # O Keycloak, que atende o PJe, escreve o recado em classe propria: sem
    # ela, a recusa do codigo chegava ao operador como "nao passou", sem dizer
    # se o codigo estava errado, vencido ou se a conta e que foi bloqueada.
    # O PJe e feito em RichFaces, que escreve os recados em classes proprias.
    # Sem elas, a consulta publica voltava "0 resultados" sem dizer se nada foi
    # encontrado ou se o portal recusou o que foi digitado, que sao problemas
    # opostos: o primeiro e resposta, o segundo e defeito nosso.
    for seletor in (".alert", ".erro", ".error", "[role=alert]", ".infraAviso",
                    ".msgErro", ".kc-feedback-text", ".pf-c-alert__title",
                    "#input-error-otp-code", ".input-error",
                    ".rich-messages-label", ".rich-message-label", ".rf-msg-lbl",
                    ".rich-messages", ".msgError", ".msgInfo", ".msgWarn"):
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
            _ir_para(pagina, url, segundos)

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
                elemento = achar_opcional(pagina, seletor)
                if elemento is None:
                    print(f"  [FALHA] Campo de {rotulo} nao encontrado: {seletor}.")
                    print("          Nada foi enviado. Rode `reconhecer` de novo.")
                    return 1
                guarda.pode_executar(Acao.PREENCHER, seletor, url=url)
                elemento.click()
                elemento.fill(valor)

            # Conferencia ANTES de enviar: sem isso o clique viraria tentativa
            # falha por campo vazio, que e justamente o que bloqueia a conta.
            alvo = achar_opcional(pagina, campo_senha_oculto)
            if not alvo or alvo.evaluate("e => (e.value || '').length") != len(senha):
                print("  [ABORTADO] A senha nao chegou ao campo enviado.")
                print("             NADA foi enviado, para nao gerar tentativa falha.")
                return 1
            print("  Campos preenchidos e conferidos.")

            botao = achar_opcional(pagina, botao_entrar)
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
            # Fecha as abas antes do navegador. Uma aba aberta pela pagina de
            # passagem deixava o fechamento pendurado, e o operador precisou
            # interromper a execucao com o teclado. Erro ao fechar nao pode
            # custar o resultado: a consulta ja terminou aqui.
            try:
                for _aba in list(getattr(navegador, "pages", []) or []):
                    try:
                        _aba.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                navegador.close()
            except Exception:
                pass

    print("\n" + "=" * LARGURA)
    print("  Uma tentativa, e so uma. O comando nao repete em nenhuma hipotese.")
    print("  Nenhum codigo de segundo fator foi digitado. Nada foi baixado.")
    return 0




# Prefixo que faz o alvo ser procurado pelo TEXTO, e nao por seletor de CSS.
# Dois portais ja exigiram isso: a tela "Acesso a Integra do Processo" do eproc
# do Rio, cujos botoes sao "Confirmar" e "Cancelar" sem identificador nenhum, e
# a Central do Processo Eletronico do Superior Tribunal de Justica, cujo botao
# "Entrar" tambem nao tem identificador.
#
# A comparacao e por IGUALDADE, sem acento e sem caixa, e nunca por inicio de
# palavra. Na tela do Superior Tribunal de Justica convivem "Entrar" e "Entrar
# com gov.br": casar por inicio escolheria qualquer um dos dois, e entrar pelo
# gov.br e outro caminho de autenticacao, que ninguem pediu.
PREFIXO_DE_TEXTO = "texto="
ALVOS_CLICAVEIS = "button, input[type=submit], input[type=button], a"


def _por_texto_exato(pagina: Any, texto: str) -> Optional[Any]:
    alvo = sem_acento(texto).strip()
    janela = janela_de(pagina)
    for elemento in pagina.query_selector_all(ALVOS_CLICAVEIS):
        try:
            escrito = sem_acento(
                elemento.inner_text() or elemento.get_attribute("value") or "").strip()
            if escrito != alvo:
                continue
            if elemento.is_visible() and _na_tela(
                    elemento, janela["width"], janela["height"]):
                return elemento
        except Exception:
            continue
    return None


def elemento_visivel(pagina: Any, seletor: str) -> Optional[Any]:
    """Devolve a primeira ocorrencia do seletor que esteja de fato na tela.

    O eproc monta duas barras superiores, uma para tela grande e outra para
    telefone, com os MESMOS identificadores. `query_selector` devolve a
    primeira do documento, que pode ser a oculta, e preencher a oculta falha
    em silencio: nao levanta erro, so nao acontece nada.
    """
    if seletor.startswith(PREFIXO_DE_TEXTO):
        return _por_texto_exato(pagina, seletor[len(PREFIXO_DE_TEXTO):])
    janela = janela_de(pagina)
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


def _mapear_um(pagina, config, segundos: int) -> dict:
    """Le UMA tela de portal e devolve o resumo mais o relato inteiro."""
    import contextlib
    import io

    guarda = GuardaNavegacao(modo=Modo.ENSAIO,
                             permissoes=[permissao_efemera(config.url)])
    resultado = {"rotulo": config.rotulo, "url": config.url, "erro": None}
    try:
        guarda.avaliar(Acao.NAVEGAR, config.url).exigir()
        pagina.goto(config.url, timeout=segundos * 1000, wait_until="domcontentloaded")
        _assentar(pagina, segundos)
    except Exception as exc:
        resultado["erro"] = f"{type(exc).__name__}: {exc}"
        return resultado

    try:
        campos, botoes = _coletar(pagina)
        resultado["campos"], resultado["botoes"] = len(campos), len(botoes)
    except Exception:
        resultado["campos"] = resultado["botoes"] = 0
    resultado["formulario"] = _tem_formulario_de_login(pagina)
    resultado["desafio"] = _ha_desafio_humano(pagina)
    resultado["desafio_reprovado"] = _desafio_reprovado(pagina)

    relato = io.StringIO()
    with contextlib.redirect_stdout(relato):
        print(f"MAPA DE {config.rotulo}")
        print(f"Lido em modo ensaio: NAO preenche, NAO clica, NAO autentica.")
        _relatar_tela(pagina, config.rotulo)
        _relatar_estrutura_de_dados(pagina)
    resultado["relato"] = relato.getvalue()
    return resultado


def mapear(alvos=None, *, oculto: bool = False, segundos: int = 30) -> int:
    """Le a tela de entrada de cada portal do .env e grava um mapa por portal.

    Existe para separar o que custa do que nao custa. Escrever adaptador exige
    conhecer a tela, e conhecer a tela nao exige autenticar: a pagina de
    entrada e publica. Este comando le todas de uma vez, sem preencher, sem
    clicar e sem gastar tentativa nem codigo de portal nenhum, e deixa os
    relatos em arquivo para serem lidos com calma.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    from datetime import datetime, timezone

    try:
        escolhidos = alvos_escolhidos(portais_configurados(), alvos)
    except PortalNaoConfigurado as exc:
        print(f"Portal pedido que nao esta no .env: {exc}", file=sys.stderr)
        return 1
    if not escolhidos:
        print("Nenhum portal configurado no .env "
              "(JUSTICA_PORTAL_<TRIBUNAL>_<SISTEMA>_URL).", file=sys.stderr)
        return 1

    print("=" * LARGURA)
    print("MAPA DOS PORTAIS".center(LARGURA))
    print("=" * LARGURA)
    print(f"{len(escolhidos)} portal(is) do .env. Modo ensaio: nao preenche, nao")
    print("clica, nao autentica. Nao gasta tentativa de login nem codigo.\n")

    executavel = os.environ.get("JUSTICA_CHROMIUM") or None
    momento = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    falhas = 0
    with sync_playwright() as p:
        try:
            navegador, pagina = abrir_navegador(p, oculto, executavel)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                print("\n" + NAVEGADOR_AUSENTE, file=sys.stderr)
                return 2
            raise
        try:
            for config in escolhidos:
                print(f"  Lendo {config.rotulo}...")
                resultado = _mapear_um(pagina, config, segundos)
                print(f"    {linha_de_resumo(resultado)}")
                if resultado.get("erro"):
                    falhas += 1
                    continue
                arquivo = (pasta_dos_mapas()
                           / f"{config.tribunal}-{config.sistema}-{momento}.txt")
                # Com marca de ordem de byte: o `Get-Content` do PowerShell le
                # UTF-8 sem marca usando a pagina de codigo do sistema, e o mapa
                # chega ao operador com "usuArio" no lugar de "usuario". E o mesmo
                # motivo pelo qual o .env e lido como utf-8-sig.
                arquivo.write_text(resultado["relato"], encoding="utf-8-sig")
                print(f"    Mapa: {arquivo}")
        finally:
            try:
                for aberta in getattr(navegador, "pages", []):
                    try:
                        aberta.close()
                    except Exception:
                        pass
                navegador.close()
            except Exception:
                pass

    print(f"\n  Pronto. Os mapas estao em {pasta_dos_mapas()}")
    print("  Nenhuma tentativa de login foi gasta.")
    return 1 if falhas == len(escolhidos) else 0


def conferir_sessao(
    url: str, tribunal: str, sistema: str, *, oculto: bool = False, segundos: int = 30
) -> int:
    """Diz se a sessao guardada no perfil ainda vale, SEM gastar tentativa.

    Por que existe: cada execucao de `consultar` custa uma tentativa de login
    do teto da conta e um codigo lido no celular, e em 22/09/2026 foram seis
    execucoes num dia so para vencer degraus de UMA tela. Este comando nao
    preenche, nao clica e nao autentica: abre o portal com o perfil que ja
    esta no disco e relata o que aparece. Se a sessao ainda valer, a consulta
    seguinte pode aproveita-la; se nao valer, o relato mostra a tela real, que
    e o que permite escrever a prova de sessao aberta sem adivinhar.

    A conclusao vem rotulada: a AUSENCIA do formulario de login nao prova que
    a sessao esta aberta, so sugere. Prova positiva exige elemento que so
    exista depois da autenticacao, e e isso que o relato procura.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    guarda = GuardaNavegacao(modo=Modo.ENSAIO, permissoes=[permissao_efemera(url)])

    print("=" * LARGURA)
    print("CONFERENCIA DE SESSAO".center(LARGURA))
    print("=" * LARGURA)
    print(f"Portal: {tribunal.upper()} / {sistema}")
    print(f"Endereco: {url}")
    print("NAO preenche, NAO clica, NAO autentica. Nao gasta tentativa nem codigo.\n")

    try:
        guarda.avaliar(Acao.NAVEGAR, url).exigir()
    except NavegacaoBloqueada as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

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
            _ir_para(pagina, url, segundos)
            _assentar(pagina, segundos)
            final = pagina.url
            print(f"  Endereco final: {final}")
            try:
                print(f"  Titulo: {pagina.title()!r}")
            except Exception:
                pass

            formulario_de_login = _tem_formulario_de_login(pagina)
            prova_positiva = _ja_autenticado(pagina)
            if _desafio_reprovado(pagina):
                print("  VERIFICACAO HUMANA: presente e JA REPROVOU o navegador.")
            elif _ha_desafio_humano(pagina):
                print("  VERIFICACAO HUMANA: presente, aguardando resposta.")

            situacao, linhas = veredicto_da_sessao(prova_positiva, formulario_de_login)
            print()
            for linha in linhas:
                print(f"  {linha}")

            _relatar_tela(pagina, "TELA ENCONTRADA")
            return situacao
        finally:
            try:
                for aberta in getattr(navegador, "pages", []):
                    try:
                        aberta.close()
                    except Exception:
                        pass
                navegador.close()
            except Exception:
                pass


# Seletores de entrada de cada sistema. TODOS foram LIDOS de tela real, e a
# procedencia de cada bloco esta anotada: seletor adivinhado falha em silencio,
# e em portal que limita tentativa de login o silencio custa acesso.
SELETORES_POR_SISTEMA = {
    # Conferido em campo em 22/09/2026, na autenticacao que funcionou.
    "esaj": {
        "campo_usuario": "#usernameForm",
        "campo_senha": "#passwordForm",
        "campo_senha_oculto": "input[name=password]",
        "botao_entrar": "#pbEntrar",
        "campo_codigo": "#tokenInformado",
        "botao_validar": "#btnEnviarToken",
    },
    # Lido do mapa de 22/09/2026 (eproc.jfrj.jus.br): form#frmLogin com
    # input#txtUsuario, input#pwdSenha e button#sbmEntrar. O segundo fator NAO
    # aparece nesta tela (ha so o link a#lnk2fa), e por isso os campos dele
    # ficaram como palpite ate 02/10/2026, quando a autenticacao do TRF2 passou
    # ponta a ponta: o codigo foi preenchido pelo cofre e o portal respondeu com
    # a tela de selecao de perfil. Confirmados em campo, portanto, e nao mais
    # deduzidos.
    "eproc": {
        "campo_usuario": "#txtUsuario",
        "campo_senha": "#pwdSenha",
        "campo_senha_oculto": "input[name=pwdSenha]",
        "botao_entrar": "#sbmEntrar",
        "campo_codigo": "#txtAcessoCodigo",
        "botao_validar": "#btnValidar",
    },
    # Central do Processo Eletronico do Superior Tribunal de Justica, lida do
    # mapa de 05/10/2026 (cpe.web.stj.jus.br). Aplicacao de pagina unica: a
    # pagina inteira tem TRES identificadores, `div#app`, `input#cpf` e um
    # quadro de telemetria. O campo da senha so se identifica pelo nome, e o
    # botao de entrar nao se identifica de jeito nenhum, dai o alvo por texto.
    #
    # O usuario e o CPF, e nao um nome de usuario. Ha tambem entrada por gov.br
    # e por certificado digital; nenhuma das duas esta escrita aqui, e a de
    # gov.br e a razao de o alvo por texto comparar por igualdade: "Entrar" e
    # "Entrar com gov.br" convivem na mesma tela.
    #
    # Segundo fator: NAO SE SABE. A tela de entrada nao o mostra, como nao
    # mostrava no eproc nem no PJe. Fica vazio, e `achar_opcional` trata vazio
    # como "esta tela nao tem este campo neste portal", em vez de procurar por
    # nada e levantar erro depois de a credencial ja ter sido enviada.
    "cpe": {
        "campo_usuario": "#cpf",
        "campo_senha": "input[name=password]",
        "campo_senha_oculto": "input[name=password]",
        "botao_entrar": "texto=Entrar",
        "campo_codigo": "",
        "botao_validar": "",
    },
    # Lido do mapa de 22/09/2026 (sso.cloud.pje.jus.br, Keycloak do PJe):
    # form#loginForm com input#username, input#password e input#kc-login.
    # Lida em 06/10/2026 na tela de entrada do DCP do Tribunal de Justica do
    # Rio de Janeiro, em `www3.tjrj.jus.br/idserverjus-front/#/login`. Quem
    # autentica nao e o DCP: e o IdServerJus, o controle de acesso unico do
    # tribunal, e por isso esta tela nao se parece com nenhuma das outras.
    #
    # O botao "Entrar" NAO tem identificador, entao vai pelo texto. A
    # comparacao e exata, e aqui isso basta: os outros botoes da tela sao
    # "Esqueci Minha Senha", "Libras", "Voz" e "+ Acessibilidade", e nenhum
    # comeca por "Entrar".
    #
    # Sem segundo fator. O cofre confirma, a tela confirma, e por isso os dois
    # campos de codigo ficam vazios. Se um dia a tela passar a pedir, o
    # comando relata o campo que achou em vez de dizer que ela nao apareceu.
    "dcp": {
        "campo_usuario": "#usuario",
        "campo_senha": "#senha",
        "campo_senha_oculto": "#senha",
        "botao_entrar": "texto=Entrar",
        "campo_codigo": "",
        "botao_validar": "",
    },
    # O segundo fator nao aparece na tela de entrada.
    "pje": {
        "campo_usuario": "#username",
        "campo_senha": "#password",
        # [Inferencia] O mapa mostra o campo pelo id, nao pelo tipo. Este
        # seletor e so a rede de seguranca de quando o id falha, e por isso
        # fica preso ao formulario que o mapa mostrou.
        "campo_senha_oculto": "#loginForm input[type=password]",
        "botao_entrar": "#kc-login",
        # Lidos da tela de segundo fator do PJe do Rio em 22/09/2026, depois de
        # a credencial ser aceita: um campo so, `#otp`, com o rotulo "Entre no
        # seu aplicativo de autenticacao", e o mesmo `#kc-login` do login,
        # agora escrito "Validar". O identificador do botao se repete porque e
        # outra tela do mesmo Keycloak, e nao um engano.
        "campo_codigo": "#otp",
        "botao_validar": "#kc-login",
    },
}


# Familias de TELA DE LOGIN, que nao sao a mesma coisa que sistema.
#
# A tabela por sistema acima presumia que eproc tem a tela do eproc e PJe tem a
# do PJe. O eproc do Rio desmentiu isso em 05/10/2026: ele nao mostra a propria
# tela de login, redireciona para um Keycloak em `eproc-sso.tjrj.jus.br`, com
# `#username`, `#password` e `#kc-login`, os MESMOS identificadores do PJe. O
# endereco de retorno aponta para `sso.cloud.pje.jus.br`, o que explica a
# coincidencia: e a mesma infraestrutura de autenticacao do Conselho Nacional
# de Justica.
#
# Por isso a escolha final dos seletores nao pode sair so do nome do sistema.
# Ela sai da TELA, quando a tela desmente a configuracao.
FAMILIAS_DE_LOGIN = (
    {
        "nome": "eproc",
        "campo_usuario": "#txtUsuario",
        "campo_senha": "#pwdSenha",
        "campo_senha_oculto": "input[name=pwdSenha]",
        "botao_entrar": "#sbmEntrar",
        "campo_codigo": "#txtAcessoCodigo",
        "botao_validar": "#btnValidar",
    },
    {
        "nome": "stj-cpe",
        "campo_usuario": "#cpf",
        "campo_senha": "input[name=password]",
        "campo_senha_oculto": "input[name=password]",
        "botao_entrar": "texto=Entrar",
        "campo_codigo": "",
        "botao_validar": "",
    },
    {
        # Controle de acesso unico do Tribunal de Justica do Rio de Janeiro.
        # Entra nas familias porque o DCP nao e o unico servico atras dele: o
        # portal de servicos manda para ca com `sgSist` diferente, e a tela e
        # a mesma.
        "nome": "idserverjus",
        "campo_usuario": "#usuario",
        "campo_senha": "#senha",
        "campo_senha_oculto": "#senha",
        "botao_entrar": "texto=Entrar",
        "campo_codigo": "",
        "botao_validar": "",
    },
    {
        "nome": "keycloak",
        "campo_usuario": "#username",
        "campo_senha": "#password",
        # Aqui NAO ha campo espelho: o campo visivel e o que vai ser enviado.
        # E ele nao pode ser procurado por `input[type=password]`, porque a tela
        # traz o olhinho de mostrar a senha, que troca o tipo para `text`. Lido
        # assim na tela real do eproc do Rio em 05/10/2026.
        "campo_senha_oculto": "#password",
        "botao_entrar": "#kc-login",
        "campo_codigo": "#otp",
        "botao_validar": "#kc-login",
    },
)


def familia_da_tela(pagina) -> Optional[dict]:
    """Qual familia de tela de login esta na tela agora, se alguma.

    Decide pelo campo de usuario VISIVEL, e nao pela presenca no documento: a
    tela de um portal pode conter restos da outra, e e o que esta na frente da
    pessoa que vale.
    """
    for familia in FAMILIAS_DE_LOGIN:
        if elemento_visivel(pagina, familia["campo_usuario"]) is not None:
            return familia
    return None


def sistema_tem_seletores(sistema: str) -> bool:
    """Se a tela de entrada deste sistema ja foi lida e registrada aqui."""
    return (sistema or "").lower().strip() in SELETORES_POR_SISTEMA


def seletores_do_sistema(sistema: str) -> dict:
    """Seletores de entrada do sistema, ou os do eproc quando nao ha tabela.

    O eproc e o padrao historico do comando; manter esse desfecho evita que um
    sistema novo apareca sem seletor nenhum e o comando quebre por dentro.

    O desfecho e seguro e MENTE no relato, e por isso quem chama tem de avisar
    (ver `sistema_tem_seletores`). Procurar `#txtUsuario` num portal que nunca
    foi lido termina em "campo de usuario nao encontrado", que manda o operador
    procurar seletor que mudou quando nunca houve seletor nenhum.
    """
    return dict(SELETORES_POR_SISTEMA.get((sistema or "").lower().strip(),
                                          SELETORES_POR_SISTEMA["eproc"]))


def completar_seletores(args) -> None:
    """Preenche os seletores que o operador nao passou, pelo sistema.

    O que vem na linha de comando tem precedencia sempre: a tabela e
    conveniencia, nao autoridade. Portal muda de tela sem avisar, e o operador
    precisa poder corrigir na hora, sem esperar codigo novo.
    """
    padroes = seletores_do_sistema(getattr(args, "sistema", ""))
    for nome, valor in padroes.items():
        if getattr(args, nome, "ausente") is None and valor is not None:
            setattr(args, nome, valor)


def consulta_publica(tribunal: str, sistema: str, numero_processo: str, url: str,
                     *, oculto: bool = False, segundos: int = 30) -> int:
    """Consulta o processo na tela publica do portal, SEM autenticar.

    Existe por um motivo de custo, nao de conveniencia: a sessao do PJe nao
    sobrevive ao fechamento do navegador, entao toda consulta autenticada
    custa uma tentativa do teto da conta e um codigo lido no aplicativo. Para
    processo que nao corre em segredo, a tela publica responde a mesma
    pergunta por zero.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(INSTRUCAO_INSTALACAO, file=sys.stderr)
        return 2

    from .core.cnj import NumeroCNJInvalido, parse_numero
    from .pje import ConsultaPJeIndisponivel, buscar_publico, linhas_do_resultado

    if (sistema or "").lower().strip() != "pje":
        print(f"  [NAO IMPLEMENTADO] Consulta publica escrita so para o PJe, "
              f"nao para {sistema!r}.", file=sys.stderr)
        return 1
    try:
        numero = parse_numero(numero_processo)
    except NumeroCNJInvalido as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1

    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    print("=" * LARGURA)
    print("CONSULTA PUBLICA".center(LARGURA))
    print("=" * LARGURA)
    print(f"Portal: {tribunal.upper()} / {sistema}")
    print(f"Processo: {numero.formatado}")
    print("Sem login: nao gasta tentativa nem codigo. Somente leitura.\n")

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
            try:
                final = buscar_publico(pagina, guarda, numero, url, segundos)
            except ConsultaPJeIndisponivel as exc:
                print(f"  [PAROU] {exc}", file=sys.stderr)
                _relatar_tela(pagina, "TELA ONDE PAROU")
                return 1

            print(f"  Endereco: {final}")
            achadas = linhas_do_resultado(pagina)
            print(f"  Linhas na tabela de resultados: {achadas}")

            # O recado do portal separa duas coisas opostas: "nao encontrei" e
            # "nao entendi o que voce digitou". Sem ele, a consulta vazia parecia
            # sempre a primeira, e um defeito nosso passaria por resposta.
            recados = _mensagens_de_erro(pagina)
            if recados:
                print("  O portal disse:")
                for recado in recados:
                    print(f"    {recado}")
            if not achadas and not recados:
                print("  Nenhum resultado e nenhum recado na tela. Pode ser processo")
                print("  em segredo de justica, numero de outro tribunal, ou a busca")
                print("  nao ter chegado a rodar.")
            # O teor NAO vai para a tela: o relato mostra a forma, e o conteudo
            # sera gravado em arquivo quando a extracao for escrita a partir
            # desta estrutura, como se fez no e-SAJ.
            _relatar_tela(pagina, "TELA DE RESULTADO")
            _relatar_estrutura_de_dados(pagina)
            print("\n  RELATO DA TRAVA:")
            for linha in guarda.relato():
                print(f"    {linha}")
            return 0
        finally:
            try:
                for aberta in getattr(navegador, "pages", []):
                    try:
                        aberta.close()
                    except Exception:
                        pass
                navegador.close()
            except Exception:
                pass


def mostrar_ambiente() -> int:
    """Diz ONDE o programa procura a configuracao e O QUE encontrou la.

    Nasceu de uma perda de tempo evitavel em 22/09/2026: o comando de mapear
    listou cinco portais lidos do `.env` e, meia hora depois, o de autenticar
    disse que nao havia portal nenhum. Sem saber em que arquivo o programa
    estava olhando, nao havia como decidir entre arquivo errado, arquivo
    movido, codificacao ilegivel e nome de chave com caractere invisivel.

    Nao imprime valor nenhum: so nomes de chave, caminhos e contagens.
    """
    from .core.acesso import rotulos_no_ambiente
    from .core.config import carregar_env, codificacao_do_env, raiz_do_pacote

    arquivo = raiz_do_pacote() / ".env"
    print("=" * LARGURA)
    print("AMBIENTE DO PROGRAMA".center(LARGURA))
    print("=" * LARGURA)
    print("Nenhum valor e impresso aqui: so nomes de chave e caminhos.\n")
    print(f"  O programa procura a configuracao em:\n    {arquivo}")

    if not arquivo.is_file():
        print("\n  ESTE ARQUIVO NAO EXISTE.")
        vizinhos = sorted(
            a.name for a in arquivo.parent.iterdir()
            if a.is_file() and a.name.lower().startswith(".env")
        ) if arquivo.parent.is_dir() else []
        if vizinhos:
            print("  Ha, na mesma pasta, arquivos de nome parecido:")
            for vizinho in vizinhos:
                print(f"    {vizinho}")
            print("  Um deles pode ser o seu, com o nome trocado.")
        else:
            print("  E nao ha nenhum arquivo de nome parecido na pasta.")
    else:
        try:
            tamanho = arquivo.stat().st_size
        except OSError:
            tamanho = -1
        print(f"  Existe, com {tamanho} byte(s).")
        if tamanho == 0:
            print("  ESTA VAZIO. Foi o que aconteceu em 22/09/2026, quando uma")
            print("  edicao esvaziou o arquivo e o programa passou a nao enxergar")
            print("  portal nenhum, sem nada na tela explicando por que.")
        print(f"  Codificacao que serve para le-lo: {codificacao_do_env(arquivo)}")

    lidas = carregar_env()
    nossas = [c for c in lidas if c.startswith("JUSTICA_")]
    print(f"\n  CHAVES LIDAS DO ARQUIVO ({len(nossas)}):")
    for chave in sorted(nossas):
        print(f"    {chave}")
    if not nossas:
        print("    (nenhuma)")

    from .core.config import pasta_das_copias_do_env

    copias = sorted(pasta_das_copias_do_env().glob("env-*.txt"))
    if copias:
        print(f"\n  COPIAS DE SEGURANCA DA CONFIGURACAO ({len(copias)}), a mais nova primeiro:")
        for copia in reversed(copias[-3:]):
            print(f"    {copia}")
        print("  Para repor, copie o conteudo da mais recente para o .env.")

    rotulos = rotulos_no_ambiente()
    print(f"\n  PORTAIS QUE O PROGRAMA ENXERGA ({len(rotulos)}):")
    for rotulo in rotulos:
        print(f"    {rotulo}")
    if not rotulos:
        print("    (nenhum)")
    return 0 if rotulos else 1


def reindexar(numero_bruto: str, *, confirmar: bool = False) -> int:
    """Refaz o indice de folhas de um processo a partir dos arquivos na pasta.

    Sem `--confirmar` nao toca em nada: mostra o que faria. A pasta e do
    escritorio e os arquivos sao copias de processo; apagar por engano ali e
    estrago que nao se desfaz com um comando.
    """
    from .core.acervo import (
        aplicar_reindexacao, carregar_indice, planejar_reindexacao,
    )
    from .core.cnj import parse_numero

    try:
        numero = parse_numero(numero_bruto)
    except ValueError as exc:
        print(f"Numero de processo invalido: {exc}", file=sys.stderr)
        return 1

    indice = carregar_indice(numero.apenas_digitos, numero.formatado)
    print("=" * LARGURA)
    print("REINDEXACAO DO ACERVO".center(LARGURA))
    print("=" * LARGURA)
    print(f"Processo: {numero.formatado}")
    print(f"Pasta: {indice.pasta}")
    if not indice.pasta.is_dir():
        print("\n  A pasta nao existe. Nada a fazer.", file=sys.stderr)
        return 1

    print(f"Indice atual: {len(indice.itens)} item(ns), {indice.ultima_folha} folha(s).\n")
    plano = planejar_reindexacao(indice)

    if plano["apagar"]:
        print("  REPETIDOS (mesmo conteudo, byte a byte):")
        for repetido in plano["apagar"]:
            print(f"    {repetido['arquivo'].name}")
            print(f"      identico a {repetido['igual_a'].name}, que fica")
    print("  COMO O INDICE VAI FICAR:")
    for item in plano["manter"]:
        faixa = (f"fls. {item['folha_inicial']}/{item['folha_final']}"
                 if item["folha_inicial"] else "folhas nao contadas")
        print(f"    {item['arquivo'].name}  {faixa}  [{item['tipo']}]")
    print(f"\n  Total: {plano['total']} folha(s).")

    if not confirmar:
        print("\n  ENSAIO: nada foi alterado. Para aplicar, repita com --confirmar.")
        return 0

    print()
    for linha in aplicar_reindexacao(indice, plano, apagar_repetidos=True):
        print(f"  {linha}")
    return 0


def pasta_dos_mapas() -> "Path":
    """Onde ficam os relatos de tela dos portais, um arquivo por leitura."""
    from pathlib import Path as _P

    from .core.estado import diretorio_estado

    destino = _P(diretorio_estado()) / "mapas"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def alvos_escolhidos(configs: list, alvos: Optional[list[str]]) -> list:
    """Filtra os portais pedidos na linha de comando, no formato TRIBUNAL/sistema.

    Sem `alvos`, devolve todos os configurados. Um alvo que nao existe no .env
    NAO e ignorado em silencio: quem digitou errado precisa saber, senao acha
    que o portal foi lido quando nao foi.
    """
    if not alvos:
        return list(configs)
    escolhidos, faltando = [], []
    for alvo in alvos:
        tribunal, _, sistema = alvo.partition("/")
        achado = [c for c in configs
                  if c.tribunal.upper() == tribunal.upper().strip()
                  and (not sistema or c.sistema.lower() == sistema.lower().strip())]
        if not achado:
            faltando.append(alvo)
            continue
        escolhidos.extend(a for a in achado if a not in escolhidos)
    if faltando:
        raise PortalNaoConfigurado(", ".join(faltando), "nao esta no .env")
    return escolhidos


def linha_de_resumo(resultado: dict) -> str:
    """Uma linha por portal, para o operador ver o essencial sem abrir arquivo."""
    if resultado.get("erro"):
        return f"{resultado['rotulo']}: NAO ABRIU ({resultado['erro']})"
    partes = [f"{resultado['rotulo']}:"]
    if resultado.get("desafio_reprovado"):
        partes.append("verificacao humana JA REPROVOU o navegador")
    elif resultado.get("desafio"):
        partes.append("verificacao humana presente")
    else:
        partes.append("sem verificacao humana")
    partes.append("com formulario de login" if resultado.get("formulario")
                  else "sem formulario de login")
    partes.append(f"{resultado.get('campos', 0)} campos, {resultado.get('botoes', 0)} botoes")
    return " ".join(partes)


SESSAO_ABERTA, SESSAO_FECHADA, SESSAO_INDEFINIDA = 0, 1, 3


def veredicto_da_sessao(
    prova_positiva: bool, formulario_de_login: bool
) -> tuple[int, list[str]]:
    """Traduz o que se viu na tela em veredicto, com o rotulo certo.

    A ausencia do formulario de login NAO prova sessao aberta: o portal pode
    ter devolvido uma tela de erro, de manutencao ou de escolha de perfil.
    Concluir por ausencia aqui levaria a consulta a seguir como autenticada
    quando nao esta, e o preco disso e uma tentativa do teto da conta.
    """
    if prova_positiva:
        return SESSAO_ABERTA, [
            "SESSAO ABERTA (prova positiva na tela).",
            "A consulta pode aproveitar esta sessao sem novo codigo.",
        ]
    if formulario_de_login:
        return SESSAO_FECHADA, [
            "SESSAO FECHADA: o portal mostrou o formulario de login.",
            "A proxima consulta vai pedir credencial e codigo.",
        ]
    return SESSAO_INDEFINIDA, [
        "INDEFINIDO: nao ha formulario de login, mas tambem nao ha prova",
        "positiva de sessao aberta. Ausencia de formulario NAO e prova: o",
        "relato abaixo mostra a tela real para que a prova seja escrita a",
        "partir dela, e nao adivinhada.",
    ]


def _tem_formulario_de_login(pagina) -> bool:
    """Diz se ha campo de senha visivel na tela: e o formulario de login.

    Campo de senha e a marca mais estavel do formulario de login, porque o
    identificador muda de portal para portal e o tipo nao muda.
    """
    try:
        campos, _ = _coletar(pagina)
    except Exception:
        return False
    return any(c.e_senha and c.na_tela for c in campos)


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
        seletores_preenchiveis=tuple(
            s for s in (campo_usuario, campo_senha, campo_codigo) if s
        ),
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

    if not sistema_tem_seletores(identidade.sistema):
        print(f"  [PARADO] A tela de entrada do sistema {identidade.sistema!r} nunca")
        print("           foi lida, e nao ha seletor registrado para ela. Seguir")
        print("           daqui usaria os seletores de OUTRO sistema e terminaria")
        print("           em 'campo de usuario nao encontrado', que mandaria voce")
        print("           procurar seletor que mudou quando nunca houve seletor.")
        print("  Nada foi enviado e nenhuma tentativa foi gasta.")
        print("  Leia a tela primeiro, sem autenticar e sem gastar tentativa:")
        print(f"    justica-portal mapear --portal {identidade.tribunal}/"
              f"{identidade.sistema}")
        estado.registrar(acao="login_etapa_credencial", tribunal=identidade.tribunal,
                         sistema=identidade.sistema,
                         resultado="sistema_sem_seletor_registrado")
        return 1

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
            _ir_para(pagina, url, segundos)

            # O eproc passou a exibir o desafio "Confirme que e humano" do
            # Cloudflare antes do login. O programa nao o resolve: quem marca
            # a caixa e o operador, na janela aberta.
            if not _aguardar_desafio_humano(
                pagina, campo_usuario, espera_humana, oculto
            ):
                return 1

            # ---------- etapa 0: a sessao ja esta aberta? ----------
            # Ate 02/10/2026 esta pergunta nunca era feita ANTES. O comando
            # mandava credencial e codigo sempre, e so DEPOIS reparava que o
            # portal nao tinha pedido o segundo fator porque a sessao ja valia.
            # O preco disso aparecia inteiro em campo: o navegador roda com
            # perfil persistente, entao a sessao do eproc sobrevive entre
            # execucoes, e mesmo assim cada consulta gastava um login. Varios
            # logins seguidos do mesmo lugar foi o que acabou levantando o
            # desafio do Cloudflare no TRF2 em 02/10/2026.
            #
            # Nao se trata de contornar o desafio, e sim de parar de provoca-lo:
            # a autenticacao que nao precisava acontecer e a que nao deve
            # acontecer.
            sessao_aberta = _sessao_ja_aberta(pagina, identidade.sistema)
            if sessao_aberta:
                print("  SESSAO REAPROVEITADA: o portal ja reconhece este navegador.")
                print("  Nenhuma credencial foi enviada e nenhuma tentativa foi gasta.")
                estado.registrar(
                    acao="login_sessao_reaproveitada", tribunal=identidade.tribunal,
                    sistema=identidade.sistema, resultado="sessao_valida",
                )
                final = pagina.url

            if not sessao_aberta:
                # A tela manda mais que a configuracao. O eproc do Rio redireciona
                # para um Keycloak, e os seletores do eproc nao existem la: a
                # execucao anterior gastou trinta segundos clicando num campo
                # invisivel e parou antes de digitar. Trocar so quando o campo
                # configurado NAO esta visivel preserva o que o operador tenha
                # passado na linha de comando, que continua tendo a ultima palavra
                # quando funciona.
                if elemento_visivel(pagina, campo_usuario) is None:
                    familia = familia_da_tela(pagina)
                    if familia is not None:
                        print(f"  A tela de login e do tipo {familia['nome']!r}, e nao "
                              "a esperada para este sistema.")
                        print("  Os seletores desta execucao vem da tela, e nao da "
                              "configuracao.")
                        campo_usuario = familia["campo_usuario"]
                        campo_senha = familia["campo_senha"]
                        campo_senha_oculto = familia["campo_senha_oculto"]
                        botao_entrar = familia["botao_entrar"]
                        campo_codigo = familia["campo_codigo"]
                        botao_validar = familia["botao_validar"]
                        permissao = Permissao(
                            padrao_url=permissao_efemera(pagina.url).padrao_url,
                            descricao=f"tela de login {familia['nome']}, "
                                      "reconhecida na execucao atual",
                            conferido_em="execucao atual",
                            seletores_clicaveis=(botao_entrar, botao_validar),
                            seletores_preenchiveis=(campo_usuario, campo_senha,
                                                    campo_codigo),
                        )
                        guarda.permissoes.append(permissao)
                        url = pagina.url

                # ---------- etapa 1: credencial ----------
                for seletor, valor, rotulo in (
                    (campo_usuario, login, "usuario"), (campo_senha, senha, "senha"),
                ):
                    # `elemento_visivel`, e nao `query_selector`. O eproc monta a
                    # mesma tela duas vezes, uma para tela grande e outra para
                    # telefone, com os MESMOS identificadores, e `query_selector`
                    # devolve a primeira do documento, que pode ser a oculta.
                    # `elemento_visivel` existe no projeto desde setembro por causa
                    # disso, e a etapa de credencial era o unico lugar que ainda nao
                    # a usava. Conferido em campo em 05/10/2026 no eproc do Rio: o
                    # clique ficou 30 segundos tentando acertar um campo invisivel e
                    # terminou em traceback de Playwright.
                    elemento = elemento_visivel(pagina, seletor)
                    if elemento is None:
                        existe = achar_opcional(pagina, seletor) is not None
                        if existe:
                            print(f"  [FALHA] O campo de {rotulo} ({seletor}) existe na "
                                  "pagina, mas nenhuma copia dele esta visivel.")
                            print("  Insistir nele seria digitar onde ninguem ve. Nada "
                                  "foi enviado.")
                        else:
                            fora_do_ar = erro_do_servidor(pagina)
                            if fora_do_ar:
                                print(f"  [PARADO] O portal respondeu com pagina de erro: "
                                      f"{fora_do_ar!r}.")
                                print("  Nao e seletor mudado nem credencial recusada: o")
                                print("  portal esta fora do ar. Nada foi enviado e nenhuma")
                                print("  tentativa foi gasta. Nao ha o que conferir no cofre.")
                                print("  Repita o comando mais tarde.")
                                _relatar_tela(pagina, "TELA DE LOGIN")
                                estado.registrar(
                                    acao="login_etapa_credencial",
                                    tribunal=identidade.tribunal,
                                    sistema=identidade.sistema,
                                    resultado="portal_fora_do_ar")
                                return 1
                            print(f"  [FALHA] Campo de {rotulo} ({seletor}) nao "
                                  "encontrado. Nada enviado.")
                        _relatar_tela(pagina, "TELA DE LOGIN")
                        return 1
                    guarda.pode_executar(Acao.PREENCHER, seletor, url=url)
                    if not preencher_conferindo(elemento, valor, rotulo):
                        # Parar AQUI poupa a tentativa. Clicar em Entrar com o
                        # campo vazio gasta uma tentativa da conta para receber
                        # de volta "o campo deve ser preenchido", que e um
                        # problema nosso e nao do portal.
                        print(f"  [ABORTADO] O campo de {rotulo} ({seletor}) nao "
                              "ficou com o valor digitado.")
                        print("  Nada foi enviado, e nenhuma tentativa foi gasta.")
                        _relatar_tela(pagina, "TELA DE LOGIN")
                        return 1

                alvo = achar_opcional(pagina, campo_senha_oculto)
                if not alvo or alvo.evaluate("e => (e.value || '').length") != len(senha):
                    print("  [ABORTADO] A senha nao chegou ao campo enviado. Nada enviado.")
                    return 1

                entrar_visivel = elemento_visivel(pagina, botao_entrar)
                if entrar_visivel is None:
                    print(f"  [FALHA] O botao {botao_entrar} nao esta visivel na tela. "
                          "Nada foi enviado.")
                    _relatar_tela(pagina, "TELA DE LOGIN")
                    return 1
                guarda.pode_executar(Acao.CLICAR, botao_entrar, url=url)
                estado.registrar(acao="login_etapa_credencial", tribunal=identidade.tribunal,
                                 sistema=identidade.sistema, resultado="enviado")
                print("  Etapa 1: credencial enviada (uma vez).")
                clicar_tolerando_lentidao(entrar_visivel, botao_entrar, segundos)
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
                if achar_opcional(pagina, campo_codigo) is None and _ha_desafio_humano(pagina):
                    # Tres desfechos possiveis depois que a pessoa responde, e os
                    # tres precisam ser reconhecidos. Reconhecer so o segundo fator
                    # fazia o comando esperar os 180 segundos inteiros e desistir de
                    # um desafio que ja tinha sido resolvido.
                    def _passou(p):
                        alvo = achar_opcional(p, campo_codigo)
                        if alvo is not None and alvo.is_visible():
                            return True          # foi direto ao segundo fator
                        if _ja_autenticado(p):
                            return True          # foi direto a selecao de perfil
                        if _ha_desafio_humano(p):
                            return False         # ainda no desafio
                        usuario = achar_opcional(p, campo_usuario)
                        return usuario is not None and usuario.is_visible()

                    _aguardar_desafio_humano(
                        pagina, campo_codigo, espera_humana, oculto, pronto=_passou
                    )
                    # Se o portal devolveu o formulario de login, a credencial
                    # precisa ser reenviada. Este comando NAO reenvia sozinho: uma
                    # credencial recusada tambem devolve o formulario, e reenviar as
                    # cegas e como se bloqueia uma conta. O relato abaixo diz o que
                    # apareceu, e a decisao de repetir fica com o operador.
                    voltou = achar_opcional(pagina, campo_usuario)
                    if (achar_opcional(pagina, campo_codigo) is None
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
                campo = achar_opcional(pagina, campo_codigo)
                if campo is None and not campo_codigo:
                    a_vista = seletor_de_codigo_a_vista(pagina)
                    if a_vista:
                        print("\n  [PARADO] A tela PEDE um codigo de segundo fator, e este")
                        print("           portal ainda nao tem o campo registrado aqui.")
                        print(f"           Na tela ele aparece como  {a_vista}")
                        for aviso in avisos_na_tela(pagina):
                            print(f"  AVISO NA TELA: {aviso}")
                        origem = origem_do_codigo(pagina)
                        if origem == "aplicativo":
                            print("  A tela pede o codigo do APLICATIVO autenticador.")
                        elif origem == "enviado":
                            print("  A tela diz que o codigo foi ENVIADO pelo portal.")
                        print("  A credencial foi aceita: nao e caso de conferir a senha.")
                        print("  Para seguir, repita o comando acrescentando o campo acima")
                        print("  e o botao que a tela mostra, por exemplo:")
                        print(f"    --campo-codigo {a_vista} --botao-validar texto=Confirmar")
                        print("  Isso custa mais uma tentativa de login, e e de proposito:")
                        print("  preencher campo que eu mesmo descobri, sem o seu aval,")
                        print("  esvaziaria a guarda que impede agir em tela desconhecida.")
                        _relatar_tela(pagina, "TELA DO SEGUNDO FATOR")
                        estado.registrar(
                            acao="login_etapa_segundo_fator",
                            tribunal=identidade.tribunal, sistema=identidade.sistema,
                            resultado="campo_sem_seletor_registrado")
                        return 1

                    # Daqui para baixo: portal cuja tabela NAO declara campo de
                    # codigo, e cuja tela nao mostrou nenhum. Foi lido e nao tem
                    # segundo fator, como o DCP do Tribunal de Justica do Rio de
                    # Janeiro. Chegar aqui nele e o fim esperado do login, e nao
                    # "a tela do segundo fator nao apareceu": essa frase mandaria
                    # o operador desconfiar da credencial logo depois de ela ter
                    # funcionado, e o conselho que vem junto e nao repetir.
                    if pagina_de_erro_do_navegador(pagina.url):
                        print("\n  [PARADO] O navegador mostrou pagina de erro: o portal")
                        print("           nao respondeu. Nao e recusa de credencial, e")
                        print("           nao ha o que conferir no cofre.")
                        print("  Repita o comando.")
                        estado.registrar(acao="login_resultado_credencial",
                                         tribunal=identidade.tribunal,
                                         sistema=identidade.sistema,
                                         resultado="sem_resposta_do_portal")
                        return 1
                    fora_do_ar = erro_do_servidor(pagina)
                    if fora_do_ar:
                        print(f"\n  [PARADO] O portal respondeu com pagina de erro: "
                              f"{fora_do_ar!r}.")
                        print("  Esta fora do ar. Nao ha o que conferir no cofre.")
                        estado.registrar(acao="login_resultado_credencial",
                                         tribunal=identidade.tribunal,
                                         sistema=identidade.sistema,
                                         resultado="portal_fora_do_ar")
                        return 1
                    if _tem_formulario_de_login(pagina):
                        print("\n  [PARADO] O portal continua mostrando o formulario de login.")
                        for aviso in avisos_na_tela(pagina):
                            print(f"  AVISO NA TELA: {aviso}")
                        for recado in _mensagens_de_erro(pagina):
                            print(f"  MENSAGEM NA TELA: {recado}")
                        print("  Este portal nao tem segundo fator, entao nao e o codigo")
                        print("  que esta faltando: a credencial e que nao passou.")
                        print("  NAO repita antes de conferir o que ha acima: repetir uma")
                        print("  credencial recusada queima tentativa da conta.")
                        _relatar_tela(pagina, "TELA QUE APARECEU NO LUGAR")
                        estado.registrar(acao="login_resultado_credencial",
                                         tribunal=identidade.tribunal,
                                         sistema=identidade.sistema,
                                         resultado="formulario_de_login_de_volta")
                        return 1
                    print("  Etapa 2: este portal nao tem segundo fator, e a tela de")
                    print("  login ficou para tras.")
                    for aviso in avisos_na_tela(pagina):
                        print(f"  AVISO NA TELA: {aviso}")
                    estado.registrar(acao="login_etapa_segundo_fator",
                                     tribunal=identidade.tribunal,
                                     sistema=identidade.sistema,
                                     resultado="sem_segundo_fator")
                elif campo is None:
                    # Duas situacoes muito diferentes chegavam aqui com a mesma
                    # mensagem de uma linha: credencial recusada e portal que
                    # simplesmente nao pediu o segundo fator porque a sessao
                    # anterior continua valida. Sem distinguir, o operador nao
                    # sabia se devia conferir a senha ou apenas rodar de novo, e a
                    # orientacao errada custa tentativas de uma conta que bloqueia.
                    if not _ja_autenticado(pagina):
                        print("\n  [PARADO] A tela do segundo fator nao apareceu.")
                        # O que o portal ESCREVEU vale mais que a lista de
                        # campos. Na Central do Processo Eletronico do Superior
                        # Tribunal de Justica, em 05/10/2026, o relato mostrou
                        # dois botoes "x" novos e nenhuma mensagem: havia um
                        # aviso aberto na tela, e ninguem o leu.
                        for aviso in avisos_na_tela(pagina):
                            print(f"  AVISO NA TELA: {aviso}")
                        if pagina_de_erro_do_navegador(pagina.url):
                            # Distincao que muda o conselho por inteiro. O aviso
                            # padrao ("nao repita, pode ser recusa de credencial")
                            # existe para nao queimar tentativa de uma conta que
                            # bloqueia. Aqui ele seria o pior conselho possivel:
                            # nao houve resposta do portal, nao ha o que o portal
                            # tenha recusado, e repetir e justamente o certo.
                            # Visto em campo em 05/10/2026, com o servidor de
                            # autenticacao do Rio sem responder.
                            print("\n  ISTO NAO E RECUSA DE CREDENCIAL: o navegador "
                                  "mostrou pagina de erro.")
                            print("  O portal nao respondeu. Pode ser a rede daqui ou o "
                                  "proprio portal fora do ar.")
                            print("  Nao ha nada a conferir no cofre. Repita o comando "
                                  "daqui a pouco.")
                            estado.registrar(
                                acao="login_resultado_credencial",
                                tribunal=identidade.tribunal,
                                sistema=identidade.sistema,
                                resultado="portal_sem_resposta")
                            _relatar_tela(pagina, "TELA QUE APARECEU NO LUGAR")
                            return 1
                        if erros:
                            print("  Mensagens na tela:")
                            for e in erros:
                                print(f"    {e}")
                        if senha_vencida(erros):
                            # Sem esta distincao, o conselho impresso logo abaixo
                            # ("confira o cofre") manda o operador procurar defeito
                            # onde nao ha: a senha guardada esta certa, e o portal
                            # e que nao a aceita mais.
                            print("\n  ISTO NAO E RECUSA DE CREDENCIAL: a senha venceu.")
                            print("  Conferir o cofre nao resolve, e repetir o comando so")
                            print("  gasta tentativas de uma conta cuja senha o portal ja")
                            print("  nao aceita. O caminho e renovar a senha NO PORTAL, no")
                            print("  seu navegador comum, e depois grava-la aqui com:")
                            print(f"    justica-credenciais guardar --tribunal "
                                  f"{identidade.tribunal} --sistema {identidade.sistema} "
                                  "--so-senha --janela")
                            estado.registrar(
                                acao="login_resultado_credencial",
                                tribunal=identidade.tribunal,
                                sistema=identidade.sistema, resultado="senha_vencida")
                            _relatar_tela(pagina, "TELA QUE APARECEU NO LUGAR")
                            return 1
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
                    # A tela manda mais que o cofre. Ter semente guardada decidia
                    # sozinho gerar o codigo, e numa tela que ENVIOU o codigo isso
                    # queima uma tentativa com um numero que ela nunca aceitaria.
                    origem = origem_do_codigo(pagina, campo)
                    if origem == "enviado" and cofre.tem_semente(identidade):
                        print("  A tela diz que o codigo foi ENVIADO pelo portal, e nao")
                        print("  que vem do aplicativo autenticador. A semente guardada")
                        print("  NAO foi usada: ela geraria um numero que esta tela nao")
                        print("  espera, e a tentativa seria perdida.")
                    if cofre.tem_semente(identidade) and origem != "enviado":
                        # O segundo fator e de uso unico. O portal marca como
                        # consumido o codigo que recebeu, e o mesmo numero
                        # mandado de novo volta recusado com a mesma mensagem de
                        # codigo errado. Repetir o comando dentro dos mesmos 30s
                        # manda exatamente o mesmo numero, e o operador le
                        # "codigo invalido" sobre uma semente que esta certa.
                        chave_janela = f"segundo_fator:{identidade.chave}"
                        gasta = (estado.obter_cache(chave_janela) or {}).get("valor")
                        if gasta == cofre.janela_do_codigo():
                            espera = cofre.segundos_restantes_do_codigo() + 1
                            print(f"  O codigo desta janela de 30s ja foi enviado antes. "
                                  f"Aguardando {espera}s pelo proximo, porque reenviar o")
                            print("  mesmo seria recusado mesmo com a semente certa.")
                            time.sleep(espera)
                        # Exige janela util: codigo gerado no fim da validade expira
                        # entre o preenchimento e o envio, e o portal registra falha
                        # por um motivo que nao e culpa da credencial.
                        restante = cofre.segundos_restantes_do_codigo()
                        if restante < 8:
                            print(f"  Codigo atual expira em {restante}s; aguardando a proxima janela.")
                        codigo = cofre._codigo_segundo_fator(identidade, minimo_segundos=8)
                        # A janela, nunca o codigo: guardar o codigo seria guardar
                        # credencial de uso unico num banco que nao e cofre.
                        estado.gravar_cache(chave_janela, cofre.janela_do_codigo(),
                                            timedelta(minutes=5))
                        validade = f", valido por mais {cofre.segundos_restantes_do_codigo()}s"
                    else:
                        tamanho = None
                        bruto = campo.get_attribute("maxlength")
                        if bruto and bruto.isdigit():
                            tamanho = int(bruto)
                        try:
                            rotulo_do_campo = (campo.get_attribute("aria-label")
                                               or campo.get_attribute("placeholder") or "")
                            rotulo_do_campo = " ".join(rotulo_do_campo.split())[:120] or None
                        except Exception:
                            rotulo_do_campo = None
                        codigo = _codigo_do_operador(identidade.rotulo, tamanho, oculto,
                                                     rotulo_do_campo, origem)
                        if codigo is None:
                            estado.registrar(
                                acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                                sistema=identidade.sistema, resultado="codigo_nao_informado",
                            )
                            return 1
                        validade = " (informado pelo operador)"

                    guarda.pode_executar(Acao.PREENCHER, campo_codigo, url=url)
                    try:
                        campo.click()
                        campo.fill(codigo)
                        conferido = campo.evaluate("e => (e.value || '').length")
                    except Exception as exc:
                        # A janela pode ter sido fechada, ou a propria pessoa pode
                        # ter concluido o login nela enquanto o programa esperava o
                        # codigo no terminal. Conferido em campo em 30/09/2026: o
                        # erro subia como traceback de Playwright, o que parece
                        # defeito grave e nao e. Estes dois desfechos precisam ser
                        # ditos em portugues, porque a providencia e diferente em
                        # cada um e nenhuma delas e "conferir a senha".
                        print(f"\n  [PARADO] Nao consegui preencher o codigo: "
                              f"{type(exc).__name__}.")
                        if "closed" in str(exc).lower():
                            print("  A janela do navegador nao esta mais aberta.")
                            print("  Se foi voce que concluiu o login por la, esta tudo bem:")
                            print("  a sessao ficou no perfil. Confira sem gastar tentativa:")
                            print(f"    justica-portal sessao --tribunal {identidade.tribunal} "
                                  f"--sistema {identidade.sistema}")
                            print("  Se a janela fechou sozinha, repita o comando.")
                        estado.registrar(
                            acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                            sistema=identidade.sistema, resultado="janela_indisponivel")
                        return 1
                    if conferido != len(codigo):
                        print(f"  [ABORTADO] O codigo nao entrou no campo ({conferido} de {len(codigo)}).")
                        print("             Nada foi enviado, para nao gastar tentativa.")
                        return 1
                    print(f"  Etapa 2: codigo preenchido{validade}.")

                    guarda.pode_executar(Acao.CLICAR, botao_validar, url=url)
                    estado.registrar(acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                                     sistema=identidade.sistema, resultado="enviado")
                    validar_visivel = (elemento_visivel(pagina, botao_validar)
                                       or achar_opcional(pagina, botao_validar))
                    if validar_visivel is None:
                        print(f"  [FALHA] O botao {botao_validar} nao esta na tela. "
                              "O codigo foi digitado e NAO foi enviado.")
                        _relatar_tela(pagina, "TELA DO SEGUNDO FATOR")
                        return 1
                    clicar_tolerando_lentidao(validar_visivel, botao_validar, segundos)
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

                ainda_pede_codigo = achar_opcional(pagina, campo_codigo) is not None
                if ainda_pede_codigo:
                    print("  A tela ainda pede o codigo: a validacao NAO passou.")
                    # O recado do portal e o que separa codigo errado de codigo
                    # vencido, e um do outro muda o que se faz em seguida: o
                    # primeiro e semente errada no cofre, o segundo e so tempo.
                    recados = _mensagens_de_erro(pagina)
                    if recados:
                        print("  O portal disse:")
                        for recado in recados:
                            print(f"    {recado}")
                    else:
                        print("  O portal nao deixou mensagem nenhuma na tela.")
                    print("  NAO repita o comando. Confira a semente com:")
                    print("    justica-credenciais testar --tribunal "
                          f"{identidade.tribunal} --sistema {identidade.sistema}")
                    estado.registrar(acao="login_etapa_segundo_fator", tribunal=identidade.tribunal,
                                     sistema=identidade.sistema, resultado="recusado")
                    # PARA AQUI. Ate 30/09/2026 nao parava: o comando imprimia
                    # "a validacao NAO passou" e seguia para a selecao de perfil e
                    # para o `apos_autenticar` como se nada tivesse acontecido. Na
                    # pratica a consulta era disparada de dentro da tela de login,
                    # o portal a devolvia para o servidor de autenticacao, e a trava
                    # a barrava por dominio diferente. Ou seja: o operador via uma
                    # falha de navegacao no fim do relato e precisava subir vinte
                    # linhas para descobrir que o defeito de verdade era o codigo
                    # recusado. Sem autenticacao, nada do que vem depois faz sentido.
                    return 1
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

            # Campo e botao nao descrevem tela de escolha: ali o que leva
            # adiante sao ligacoes e blocos com identificador. O relato parava
            # nos dois primeiros e saia vazio justamente na tela que diz para
            # onde ir, e descobrir isso custava outra tentativa de login.
            try:
                caminhos = caminhos_de_navegacao(pagina.query_selector_all("a[href]"))
            except Exception:
                caminhos = []
            if caminhos:
                print(f"\n  CAMINHOS DE NAVEGACAO ({len(caminhos)}), sem texto "
                      "e sem parametros:")
                for caminho in caminhos[:40]:
                    print(f"    {caminho}")
            _relatar_estrutura_de_dados(pagina)

            print("\n  RELATO DA TRAVA:")
            for linha in guarda.relato():
                print(f"    {linha}")
        finally:
            # Fecha as abas antes do navegador. Uma aba aberta pela pagina de
            # passagem deixava o fechamento pendurado, e o operador precisou
            # interromper a execucao com o teclado. Erro ao fechar nao pode
            # custar o resultado: a consulta ja terminou aqui.
            try:
                for _aba in list(getattr(navegador, "pages", []) or []):
                    try:
                        _aba.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                navegador.close()
            except Exception:
                pass

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

# Palavras que denunciam um caminho de copia dos autos. Comparadas SEM ACENTO,
# contra o texto do link ou do botao.
TERMOS_DE_COPIA = ("gerar", "download", "baixar", "completo", "integra", "autos",
                   "copia")

# O eproc do Rio nao tem `#btnDownloadCompletoRS`. Ele tem, no quadro "Acoes" da
# tela do processo, um link escrito "Acesso integra do processo", conferido na
# tela real em 05/10/2026. O operador informou, na mesma data, que clicar nele
# dispara um SEGUNDO FATOR, como no login: acessar os autos inteiros exige mais
# que estar autenticado.
MARCA_DO_ACESSO_A_INTEGRA = "integra do processo"

# Campos de codigo ja vistos em tela real, nas duas familias de portal. A ordem
# importa pouco; o que importa e so aceitar o que esta VISIVEL.
CAMPOS_DE_CODIGO = ("#otp", "#txtAcessoCodigo")
BOTOES_DE_CODIGO = ("#kc-login", "#btnValidar")

# Nem todo botao de validar tem identificador. A tela "Acesso a Integra do
# Processo" do eproc do Rio, lida em 05/10/2026 dentro do quadro embutido, tem
# `#txtAcessoCodigo` e dois botoes SEM ID: "Confirmar" e "Cancelar". Quando o
# identificador falha, o texto e o que resta, e ele e bom o bastante desde que
# o que NAO deve ser clicado esteja nomeado tambem.
TEXTOS_DE_CONFIRMAR = ("confirmar", "validar", "enviar", "ok", "prosseguir")
TEXTOS_A_NUNCA_CLICAR = ("cancelar", "limpar", "voltar", "fechar", "sair")

# Segundo passo da copia integral no eproc, lido da tela real da Justica Federal
# do Rio em 02/10/2026. O primeiro clique nao devolve arquivo: leva a
# `acao=selecionar_processos_agendar_arquivo_completo`, cujo titulo e "Agenda
# geracao de arquivo completo do processo" e cujos unicos botoes proprios sao
# `#btnGerar` ("Gerar Arquivo Completo") e `#btnVoltar`.
#
# "Agenda" no titulo e no nome da acao e um aviso que vale levar a serio: o
# portal pode nao devolver o arquivo na hora, e sim enfileirar a geracao. Por
# isso o codigo abaixo nao afirma que o arquivo vem; ele clica, espera, e
# relata a tela quando nao vier.
# Quanto se espera pelo arquivo no PRIMEIRO clique, o do botao da tela do
# processo. Curto de proposito: em duas execucoes reais, 02 e 05/10/2026, esse
# clique NUNCA devolveu arquivo. O efeito dele e navegar para a tela de
# geracao, e so. Esperar os mesmos 45s da operacao inteira era jogar fora
# quarenta e cinco segundos em toda consulta, por um arquivo que ninguem nunca
# viu chegar por ali. O clique continua; o que encolheu foi a espera.
TETO_DO_DOWNLOAD_DIRETO = 8

BOTAO_GERAR_INTEGRA = "#btnGerar"
MARCA_DA_TELA_DE_GERACAO = "agendar_arquivo_completo"

# O que o portal escreve enquanto monta o arquivo. Lido da tela real do eproc do
# Rio em 05/10/2026: "Status do download: Em processamento: 31% (solicitacao foi
# feita em ...)" e "Dependendo do tamanho do processo, este procedimento pode
# demorar algumas horas". Isso NAO e falha: e a resposta certa a um pedido que
# acabou de ser aceito.
MARCAS_DE_GERACAO_EM_CURSO = ("em processamento", "sendo processado",
                              "aguarde", "em andamento")

# Devolvido quando a geracao foi PEDIDA e aceita, e o arquivo vira depois. Nao e
# arquivo, e tambem nao e falha; confundir os dois fazia o relato terminar em
# "copia nao concluida (TimeoutError)" depois de tudo ter dado certo.
GERACAO_PEDIDA = "geracao pedida"

# Terceiro e ultimo passo, lido da tela real da Justica Federal do Rio em
# 05/10/2026, numa execucao posterior ao pedido de geracao. A MESMA tela que
# antes trazia "Gerar Arquivo Completo" passa a trazer, quando o arquivo fica
# pronto:
#
#     'BAIXAR ARQUIVO PARTE 1'  -> https://eproc-down.jfrj.jus.br/...
#     'BAIXAR ARQUIVO PARTE 2'  -> https://eproc-down.jfrj.jus.br/...
#     'forcar nova geracao de download completo'
#
# Tres coisas que essa leitura ensinou e que nao dava para supor:
#   1. a copia vem PARTIDA, e o numero de partes depende do processo;
#   2. os arquivos moram em OUTRO endereco (`eproc-down`), e nao no portal;
#   3. a mesma tela serve para pedir a geracao e para buscar o resultado.
MARCA_DE_PARTE = "baixar arquivo parte"

# NUNCA clicado por conta propria. Este link descarta o arquivo que ja esta
# pronto e manda gerar tudo de novo: quem o aperta por engano joga fora o
# trabalho e volta para a fila. Esta aqui para ser RECONHECIDO e evitado.
MARCA_DE_NOVA_GERACAO = "nova geracao"


# Marcadores do desafio "Confirme que e humano" do Cloudflare, visto no eproc
# do Tribunal Regional Federal da 2a Regiao em 21 de setembro de 2026.
MARCAS_DESAFIO = (
    'iframe[src*="challenges.cloudflare.com"]',
    'input[name="cf-turnstile-response"]',
    ".cf-turnstile",
    "#cf-challenge-running",
)

# reCAPTCHA do Google NAO entra em MARCAS_DESAFIO, e a diferenca e de desenho.
# O Cloudflare so bota a marca na pagina quando esta cobrando o desafio, entao
# achar a marca e achar o desafio. O reCAPTCHA mora na pagina o tempo todo:
# pode estar vazio, invisivel, ou so ser acionado no envio. Tratar os dois
# igual faria o comando esperar o operador marcar uma caixa que talvez nunca
# apareca, em TODA execucao daquele portal.
#
# Ignora-lo tambem nao serve: o relato diria "desafio: nao" numa tela que
# carrega reCAPTCHA, e quando o portal recusasse o login ninguem saberia por
# que. Entao ele vira AVISO, e nao veredicto.
MARCAS_DE_RECAPTCHA = (
    "#recaptcha",
    ".g-recaptcha",
    'iframe[src*="recaptcha"]',
    'script[src*="recaptcha"]',
    "[data-sitekey]",
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


def recaptcha_na_pagina(pagina) -> Optional[str]:
    """A marca de reCAPTCHA que esta na pagina, se houver, ou None.

    Lido na tela de entrada do DCP do Tribunal de Justica do Rio de Janeiro em
    06/10/2026: `div#recaptcha` presente, e o relato anunciando "desafio de
    verificacao humana detectado: nao". As duas coisas eram verdadeiras ao
    mesmo tempo, e juntas enganavam.

    Devolve a marca para o relato, nunca para decidir esperar o operador: ver
    o comentario em MARCAS_DE_RECAPTCHA.
    """
    for marca in MARCAS_DE_RECAPTCHA:
        try:
            if pagina.query_selector(marca) is not None:
                return marca
        except Exception:
            continue
    return None


def seletor_de_codigo_a_vista(pagina) -> Optional[str]:
    """Campo de codigo visivel na tela, para portal sem seletor registrado.

    Seletor vazio na tabela quer dizer "ainda nao sei ONDE este portal pede o
    codigo", e nao "este portal nao pede". Com os dois tratados igual, a tela
    do segundo fator da Central do Processo Eletronico do Superior Tribunal de
    Justica seria anunciada como "a tela do segundo fator nao apareceu", que e
    o contrario do que estava acontecendo, e mandaria o operador conferir a
    senha quando a senha ja tinha sido aceita.

    Devolve o seletor APENAS para o relato. Quem autoriza preencher um campo
    descoberto assim e o operador, passando --campo-codigo na linha de comando:
    achar sozinho e depois dar permissao a si mesmo esvaziaria a guarda de
    navegacao, que existe justamente para nao agir em tela que nao se conhece.
    """
    try:
        campos, _ = _coletar(pagina)
    except Exception:
        return None
    for campo in campos:
        if not campo.visivel or campo.e_senha:
            continue
        if not _parece_segundo_fator(campo):
            continue
        if campo.identificador:
            return f"#{campo.identificador}"
        if campo.nome:
            return f"input[name={campo.nome}]"
    return None


def achar_opcional(pagina, seletor):
    """`query_selector` que entende seletor vazio e seletor por TEXTO.

    Porta unica para procurar seletor que veio da tabela de portais. O prefixo
    `texto=` e invencao deste projeto, para botao sem identificador, e o
    navegador nao o conhece: passar `texto=Entrar` direto ao `query_selector`
    levanta "Unknown engine". Aconteceu no primeiro ensaio do DCP do Tribunal
    de Justica do Rio de Janeiro, em 06/10/2026, porque so `elemento_visivel`
    sabia ler o prefixo e varios pontos chamavam o navegador sem passar por ela.

    Seletor vazio quer dizer "esta tela nao tem este campo NESTE portal", e nao
    "procure por nada". A diferenca importa porque passar vazio ao navegador
    levanta erro, e o erro cairia DEPOIS de a credencial ja ter sido enviada:
    a tentativa de login estaria gasta e o operador veria um erro de programa
    no lugar da tela do portal. Foi o que quase aconteceu ao levar o PJe para
    o comando de autenticacao, onde nenhuma tela mostrou segundo fator ainda.
    """
    if not seletor:
        return None
    if seletor.startswith(PREFIXO_DE_TEXTO):
        return _por_texto_exato(pagina, seletor[len(PREFIXO_DE_TEXTO):])
    try:
        return pagina.query_selector(seletor)
    except Exception:
        return None


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
            alvo = achar_opcional(p, seletor_esperado)
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
    teto_ids = 500
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


def _codigo_do_operador(rotulo: str, tamanho: Optional[int], oculto: bool,
                        rotulo_do_campo: Optional[str] = None,
                        origem: Optional[str] = None) -> Optional[str]:
    """Pede ao operador o codigo do segundo fator.

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
    # Nem todo codigo e ENVIADO pelo portal: o PJe pede o do aplicativo
    # autenticador, e dizer "confira sua mensagem ou e-mail" mandava o operador
    # esperar uma mensagem que nunca chegaria. Quando a tela traz o proprio
    # rotulo do campo, ele e repetido aqui: o portal explica melhor do que uma
    # suposicao minha sobre como cada tribunal manda o codigo.
    if rotulo_do_campo:
        print(f"\n  O portal pede um codigo{limite}. Ele diz: {rotulo_do_campo!r}")
    elif origem == "aplicativo":
        print(f"\n  O portal pede um codigo{limite} do seu APLICATIVO autenticador.")
        print("  Nao espere mensagem nem e-mail: este codigo nao e enviado.")
    elif origem == "enviado":
        print(f"\n  O portal ENVIOU um codigo{limite}, por mensagem ou e-mail.")
    else:
        print(f"\n  O portal pede um codigo{limite}. Pode vir por mensagem, por")
        print("  e-mail ou do seu aplicativo autenticador, conforme o tribunal.")
    print("  Ele tem validade curta, entao digite assim que o tiver.")
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
        elemento = achar_opcional(pagina, seletor)
        if elemento is None:
            print(f"    [FALHA] Campo de {rotulo} sumiu. Nada reenviado.")
            return False
        guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
        elemento.click()
        elemento.fill(valor)

    alvo = achar_opcional(pagina, campo_senha_oculto)
    if not alvo or alvo.evaluate("e => (e.value || '').length") != len(senha):
        print("    [ABORTADO] A senha nao chegou ao campo enviado. Nada reenviado.")
        return False

    guarda.pode_executar(Acao.CLICAR, botao_entrar, url=pagina.url)
    botao = achar_opcional(pagina, botao_entrar)
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


# Prova POSITIVA de sessao aberta, por sistema. Cada entrada e um seletor que
# so existe DEPOIS do login, conferido nos mapas das duas telas reais.
#
#   eproc  o mapa da tela de entrada (02/10/2026) tem `#txtUsuario`, `#pwdSenha`
#          e `#sidebar-searchbox`, e NAO tem a barra de busca de processo. O
#          mapa de dentro, do mesmo dia, tem `#txtNumProcessoPesquisaRapida` em
#          `form#formPesquisaRapida`. A presenca dela separa as duas telas.
#
# O PJe nao esta aqui de proposito: nenhuma tela interna dele foi lida ainda, e
# inventar uma prova faria o comando seguir como autenticado sem estar.
PROVA_DE_SESSAO_POR_SISTEMA = {
    "eproc": ("#txtNumProcessoPesquisaRapida",),
}


def _sessao_ja_aberta(pagina, sistema: str) -> bool:
    """Diz se a sessao ja vale, por PROVA POSITIVA e nunca por ausencia.

    Duas condicoes, as duas necessarias. Nao pode haver formulario de login na
    tela, e tem de haver algo que so existe depois do login. Concluir por
    ausencia aqui seria o pior erro possivel: o comando seguiria como
    autenticado numa tela de erro ou de manutencao, tentaria consultar, e o
    operador leria "processo nao encontrado" sobre um processo que existe.
    """
    if _tem_formulario_de_login(pagina):
        return False
    if _ja_autenticado(pagina):
        return True
    for prova in PROVA_DE_SESSAO_POR_SISTEMA.get((sistema or "").lower().strip(), ()):
        if elemento_visivel(pagina, prova) is not None:
            return True
    return False


def caminhos_de_navegacao(ligacoes) -> list[str]:
    """Caminhos distintos das ligacoes da tela, SEM texto e SEM parametros.

    Depois do login, a pergunta que importa e para onde ir: onde fica a
    consulta, onde ficam os autos. Isso esta nos enderecos do menu.

    O texto da ligacao NAO e impresso, e a parte depois da interrogacao
    tambem nao. Numa tela de painel, o texto de um item costuma ser o nome de
    uma parte ou o numero de um processo, e os parametros carregam
    identificador de cliente; o caminho, sozinho, diz o que precisa ser dito
    sem levar dado de ninguem para um relatorio que vai ser colado num chat.
    """
    from urllib.parse import urlparse

    vistos = []
    for ligacao in ligacoes:
        try:
            href = (ligacao.get_attribute("href") or "").strip()
        except Exception:
            continue
        if not href or href.startswith(("javascript:", "mailto:")):
            continue
        # `#` sozinho, ou `#secao`, e ancora na propria pagina e nao leva a
        # lugar nenhum. Mas `#/rota` e caminho de aplicacao de pagina unica, e
        # e ali que mora o menu inteiro desses portais. Descartar os dois
        # juntos fazia o relato do IdServerJus do Tribunal de Justica do Rio de
        # Janeiro, lido em 06/10/2026, sair sem um caminho sequer, bem na tela
        # de escolha do sistema. A regra de nao imprimir parametro continua
        # valendo: o que vem depois da interrogacao fica de fora.
        if href.startswith("#"):
            if not href.startswith("#/"):
                continue
            caminho = href.split("?", 1)[0]
            if caminho not in vistos:
                vistos.append(caminho)
            continue
        pedaco = urlparse(href)
        caminho = pedaco.path or "/"
        if pedaco.netloc:
            caminho = f"{pedaco.scheme}://{pedaco.netloc}{caminho}"
        if caminho not in vistos:
            vistos.append(caminho)
    return vistos


# Quantos botoes com o MESMO texto ainda contam como controle. Acima disso sao
# itens de uma lista, e o rotulo de cada um e conteudo, nao estrutura.
TETO_DE_BOTOES_IGUAIS = 2

_NUMERO_CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_SEQUENCIA_LONGA = re.compile(r"\b\d{8,}\b")


def sem_dado_de_processo(texto: str) -> str:
    """Troca por marca o que, num rotulo, e dado e nao estrutura."""
    limpo = texto or ""
    limpo = _NUMERO_CNJ.sub("<numero de processo>", limpo)
    limpo = _DATA.sub("<data>", limpo)
    limpo = _SEQUENCIA_LONGA.sub("<numero>", limpo)
    return limpo


def linhas_de_botoes(botoes, prefixo: str = "") -> list[str]:
    """Descreve os botoes SEM despejar o indice do processo junto.

    Lido no Visualizador de Processos do Tribunal de Justica do Rio de Janeiro
    em 06/10/2026: a arvore de documentos e feita de botoes, e o rotulo de cada
    um e o proprio andamento ("Alternar 45 - Juntada - Extrato da GRERJ - dia
    27/04/2018"). O relato prometia nao imprimir texto de celula e imprimiu os
    andamentos, porque ali eles nao estao em celula nenhuma: estao em rotulo de
    botao. A promessa estava certa e a regra que a sustentava era estreita
    demais, e o relato foi colado numa conversa.

    A regra nova separa controle de item de lista pela REPETICAO. Botao de
    barra de ferramentas e unico: "Baixar o processo atual em PDF" aparece uma
    vez. Item de arvore vem aos montes, todos com o mesmo texto visivel
    ("expand_more"), cada um com um rotulo diferente, e e o rotulo que carrega
    o dado. Grupo grande vira contagem, sem rotulo nenhum.

    O que ainda imprime passa por `sem_dado_de_processo`, como segunda rede.
    """
    from collections import OrderedDict

    grupos: "OrderedDict[str, list]" = OrderedDict()
    for botao in botoes:
        grupos.setdefault((botao.texto_visivel or "")[:50], []).append(botao)

    saida = []
    for texto, membros in grupos.items():
        if len(membros) > TETO_DE_BOTOES_IGUAIS:
            saida.append(
                f"{prefixo}{texto!r} x{len(membros)}  (itens de lista: rotulos "
                "omitidos, sao conteudo do processo)")
            continue
        for botao in membros:
            alvo = (botao.identificador and f"#{botao.identificador}") or (
                botao.nome and f"[name={botao.nome}]") or "(sem id)"
            marca = (f" rotulo={sem_dado_de_processo(botao.rotulo)!r}"
                     if botao.rotulo else "")
            saida.append(f"{prefixo}{alvo:40s} {sem_dado_de_processo(texto)!r}{marca}")
    return saida


def quadros_do_mesmo_portal(pagina, teto: int = 3) -> list:
    """Quadros embutidos que pertencem ao PROPRIO portal, nunca a terceiros.

    O Portal de Servicos do Tribunal de Justica do Rio de Janeiro poe a
    consulta processual inteira dentro de um `iframe`. Lido em 06/10/2026, o
    relato da tela dizia "0 campos de 10" e listava campos de um formulario de
    fale-conosco: o formulario que importa estava no quadro, e o relato nao
    descia ate la. Para quem le o relato, a tela parecia vazia.

    So quadro do mesmo servidor entra. A pagina inicial do tribunal embute um
    video do YouTube, e ler dentro dele nao diz nada sobre o portal e manda o
    programa a um lugar que nao e do tribunal.
    """
    from urllib.parse import urlparse

    try:
        casa = urlparse(pagina.url).netloc
        quadros = list(pagina.frames or [])[1:]
    except Exception:
        return []
    escolhidos = []
    for quadro in quadros:
        try:
            endereco = quadro.url or ""
        except Exception:
            continue
        if not endereco or endereco.startswith("about:"):
            continue
        if urlparse(endereco).netloc != casa:
            continue
        escolhidos.append(quadro)
        if len(escolhidos) >= teto:
            break
    return escolhidos


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
        primeira = " ".join(str(exc).split("\n")[0].split())[:160]
        print(f"    Nao foi possivel ler a estrutura: {type(exc).__name__}: {primeira}")
        return
    visiveis = [b for b in botoes if b.na_tela]
    # Os campos vinham sendo coletados e NUNCA impressos. O relato existe para
    # que um seletor seja escrito a partir da tela real, e sem os campos ele
    # servia so para metade do trabalho: no e-SAJ os campos foram achados por
    # acaso, na lista de elementos com identificador, e na tela de segundo
    # fator do PJe, em 22/09/2026, nao havia essa lista e o relato terminou
    # sem dizer onde se digita o codigo. Nenhum VALOR e impresso, so a forma.
    na_tela = [c for c in campos if c.na_tela]
    print(f"    CAMPOS NA TELA ({len(na_tela)} de {len(campos)}):")
    for c in na_tela:
        alvo = (c.identificador and f"#{c.identificador}") or (
            c.nome and f"[name={c.nome}]") or "(sem id)"
        marcas = [f"tipo={c.tipo or '?'}"]
        if c.e_senha:
            marcas.append("SENHA")
        if c.rotulo:
            marcas.append(f"rotulo={c.rotulo[:30]!r}")
        print(f"      {alvo:40s} {' '.join(marcas)}")
    if not na_tela:
        for c in campos[:20]:
            alvo = (c.identificador and f"#{c.identificador}") or (
                c.nome and f"[name={c.nome}]") or "(sem id)"
            print(f"      (fora da tela) {alvo:30s} tipo={c.tipo or '?'}")
        if not campos:
            print("      (nenhum)")

    print(f"    BOTOES NA TELA ({len(visiveis)} de {len(botoes)}):")
    for linha in linhas_de_botoes(visiveis, prefixo="      "):
        print(linha)
    if not visiveis:
        for linha in linhas_de_botoes(botoes[:20], prefixo="      (fora da tela) "):
            print(linha)
    try:
        quadros = pagina.query_selector_all("iframe")
        if quadros:
            print(f"    QUADROS EMBUTIDOS ({len(quadros)}):")
            for q in quadros[:10]:
                print(f"      src={(q.get_attribute('src') or '(sem src)')[:90]}")
    except Exception:
        pass
    # Antes do resto: numa tela cujo conteudo mora em quadro, o relato do
    # documento de fora descreve a moldura e nada mais.
    for quadro in quadros_do_mesmo_portal(pagina):
        try:
            dentro, acoes = _coletar(quadro)
        except Exception as exc:
            print(f"    QUADRO {quadro.url[:90]}: ilegivel "
                  f"({type(exc).__name__})")
            continue
        print(f"\n    ----- DENTRO DO QUADRO {quadro.url[:90]} -----")
        a_vista = [c for c in dentro if c.na_tela] or dentro[:20]
        print(f"    CAMPOS NO QUADRO ({len(a_vista)} de {len(dentro)}):")
        for c in a_vista:
            print(f"      {c.linha()}")
        if not dentro:
            print("      (nenhum)")
        visiveis_no_quadro = [b for b in acoes if b.na_tela] or acoes[:20]
        print(f"    BOTOES NO QUADRO ({len(visiveis_no_quadro)} de {len(acoes)}):")
        for linha in linhas_de_botoes(visiveis_no_quadro, prefixo="      "):
            print(linha)
        if not acoes:
            print("      (nenhum)")
        print(f"    ----- FIM DO QUADRO -----\n")

    print(f"    Desafio de verificacao humana detectado: "
          f"{'sim' if _ha_desafio_humano(pagina) else 'nao'}")
    marca_recaptcha = recaptcha_na_pagina(pagina)
    if marca_recaptcha and not _ha_desafio_humano(pagina):
        print(f"    A pagina carrega reCAPTCHA ({marca_recaptcha}), hoje sem desafio")
        print("    na tela. Pode ser invisivel ou acionado so no envio: se o portal")
        print("    recusar o login sem dizer por que, esta e a primeira suspeita.")
    ligacoes = pagina.query_selector_all("a[href]")
    interessantes = []
    for a in ligacoes:
        texto = (a.inner_text() or "").strip()
        # SEM ACENTO, e esta linha custou uma noite. O botao de copia do eproc do
        # Rio chama-se "Acesso integra do processo", com acento no i, e
        # `"integra" in "íntegra"` e falso. O relato jurou que a tela nao tinha
        # botao de copia enquanto ele estava ali, escrito em portugues correto.
        # Ja "Arrecadacao Integrada", que nao tem acento, passava e virava ruido.
        if any(t in sem_acento(texto) for t in TERMOS_DE_COPIA):
            interessantes.append((texto[:60], (a.get_attribute("href") or "")[:90]))
    if interessantes:
        print(f"    LIGACOES COM TERMO DE COPIA ({len(interessantes)}):")
        for texto, href in interessantes[:15]:
            print(f"      {texto!r}  ->  {href}")

    caminhos = caminhos_de_navegacao(ligacoes)
    if caminhos:
        print(f"    CAMINHOS DE NAVEGACAO ({len(caminhos)}), sem texto e sem parametros:")
        for caminho in caminhos[:25]:
            print(f"      {caminho}")


# Onde o eproc costuma escrever o recado da tela, em ordem do mais estreito
# para o mais largo. Lidos dos mapas reais de 02 e 05/10/2026.
AREAS_DE_RECADO = ("#divInfraAreaDados", "#divInfraAreaTelaD", "#divInfraAreaTela", "body")


def _recado_da_tela(pagina, limite: int = 800) -> str:
    """O texto que o portal escreveu nesta tela, encurtado.

    Existe por uma lacuna que custou uma execucao inteira: o relato desta casa
    imprime ESTRUTURA e nunca conteudo, por causa de dado de cliente. Isso esta
    certo para tela de processo. Para uma tela de sistema, como a que confirma
    o pedido de geracao de arquivo, vira um buraco: o portal explica ali o que
    vai acontecer e para onde ir buscar, e ninguem le.
    """
    for area in AREAS_DE_RECADO:
        try:
            alvo = pagina.query_selector(area)
            if alvo is None:
                continue
            texto = " ".join((alvo.inner_text() or "").split())
        except Exception:
            continue
        if texto:
            return texto[:limite]
    return ""


def _itens_do_menu(pagina, teto: int = 60) -> list[str]:
    """Os rotulos do menu lateral, sem endereco e sem repeticao.

    Rotulo de menu e texto do sistema, nao dado de processo: "Consultas",
    "Relatorios" e afins. Serve para achar por onde se chega a uma tela que
    ainda nao foi vista, como a dos arquivos ja gerados.
    """
    vistos, saida = set(), []
    try:
        for item in pagina.query_selector_all("#sidebar-wrapper a, #main-menu a"):
            texto = " ".join((item.inner_text() or "").split())[:40]
            if texto and texto not in vistos:
                vistos.add(texto)
                saida.append(texto)
    except Exception:
        return saida
    return saida[:teto]


def _gerar_integra_do_eproc(pagina, guarda, segundos: int):
    """Segundo clique da copia integral no eproc: a tela que pede para GERAR.

    Devolve o download, ou None quando esta nao e a tela de geracao ou quando o
    clique nao trouxe arquivo. None NAO quer dizer que deu errado para sempre:
    o nome da acao no portal fala em agendar, entao e possivel que o arquivo
    seja montado depois. Quem chama relata a tela nesse caso, que e o unico
    jeito honesto de descobrir o que vem a seguir.

    Nao tenta adivinhar nada alem disto. Em particular, nao procura o arquivo
    gerado em lista nenhuma do portal: essa tela ainda nao foi vista.
    """
    if MARCA_DA_TELA_DE_GERACAO not in (pagina.url or ""):
        # Outra tela. Clicar um botao chamado "Gerar" numa tela que nao e a
        # conferida seria exatamente o chute que este projeto evita.
        return None
    botao = elemento_visivel(pagina, BOTAO_GERAR_INTEGRA)
    if botao is None:
        return None

    print("    O portal abriu a tela de geracao do arquivo completo.")
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="gerar o arquivo completo do processo, tela do proprio portal",
        conferido_em="execucao atual",
        seletores_clicaveis=(BOTAO_GERAR_INTEGRA,),
    ))
    guarda.pode_executar(Acao.CLICAR, BOTAO_GERAR_INTEGRA, url=pagina.url)
    try:
        with pagina_de(pagina).expect_download(timeout=segundos * 1000) as info:
            botao.click()
    except Exception as exc:
        print(f"    A geracao foi pedida e o arquivo nao veio em {segundos}s "
              f"({type(exc).__name__}).")
        print("    O nome da acao no portal fala em AGENDAR, entao o arquivo pode estar")
        print("    sendo montado para depois. Nada foi perdido e nada foi clicado alem")
        print("    do botao de gerar.")
        recado = _recado_da_tela(pagina)
        if recado:
            print("\n    O QUE O PORTAL ESCREVEU NESTA TELA:")
            print(f"      {recado}")
        if any(m in sem_acento(recado) for m in MARCAS_DE_GERACAO_EM_CURSO):
            # Desfecho BOM, e precisa ser dito como tal. O portal aceitou o
            # pedido e esta montando o arquivo; ele avisa por e-mail quando
            # terminar, e pode demorar horas. Tratar isto como falha fazia o
            # relato pedir conferencia de seletor onde nao falta seletor nenhum.
            print("\n    O portal ACEITOU o pedido e esta montando o arquivo.")
            print("    Nao ha nada a corrigir aqui: rode o mesmo comando mais tarde")
            print("    e as partes prontas serao baixadas sozinhas.")
            return GERACAO_PEDIDA
        itens = _itens_do_menu(pagina)
        if itens:
            print(f"\n    MENU DO PORTAL ({len(itens)} item(ns)), para achar onde o")
            print("    arquivo gerado fica guardado:")
            for item in itens:
                print(f"      {item}")
        return None
    return info.value


# O eproc do Rio abre a integra DENTRO DA PROPRIA PAGINA, num quadro embutido,
# e nao em aba nova. Lido da tela real em 05/10/2026, depois do clique:
#
#     src=controlador.php?acao=processo_vista_sem_procuracao&txtNumProcesso=...
#
# O link, alias, e `javascript:void(0)`: nao ha endereco para seguir, so o
# efeito do script. Procurar o segundo fator e os arquivos no documento de cima
# nao acha nada, porque tudo esta dentro do quadro.
MARCA_DO_QUADRO_DA_INTEGRA = "processo_vista"


def pagina_de(janela):
    """A pagina a que a janela pertence, ou ela propria se ja for pagina.

    Quadro embutido nao tem contexto nem espera de download: quem tem e a
    pagina que o contem. Sem isto, operar dentro do quadro quebra com
    AttributeError no primeiro download.
    """
    return getattr(janela, "page", None) or janela


def quadro_da_integra(pagina):
    """O quadro embutido onde a integra do processo foi aberta, se houver."""
    try:
        quadros = list(pagina.frames)
    except Exception:
        return None
    for quadro in quadros:
        try:
            endereco = quadro.url or ""
        except Exception:
            continue
        if MARCA_DO_QUADRO_DA_INTEGRA in endereco:
            return quadro
    return None


def _acesso_a_integra(pagina):
    """O link "Acesso integra do processo" do quadro Acoes, se estiver na tela.

    Procura pelo TEXTO, sem acento, e nao pelo identificador: o link nao tem id
    na tela do Rio, e o texto e o unico sinal estavel que ele oferece.
    """
    for alvo in pagina.query_selector_all("a, button"):
        try:
            if not alvo.is_visible():
                continue
            texto = sem_acento(alvo.inner_text() or "")
        except Exception:
            continue
        if MARCA_DO_ACESSO_A_INTEGRA in texto:
            return alvo
    return None


def _botao_de_confirmar(pagina) -> tuple:
    """O botao que envia o codigo: por identificador, ou pelo texto.

    Devolve `(elemento, rotulo)`, ou `(None, None)`. O rotulo e o que aparece no
    relato da trava, e quando o botao nao tem identificador ele e o proprio
    texto, que e o unico sinal que a tela oferece.

    "Cancelar" e os seus irmaos sao nomeados para serem EVITADOS, e nao por
    excesso de zelo: naquela tela eles ficam lado a lado com "Confirmar", e
    clicar no errado fecha o acesso que acabou de ser pedido.
    """
    for candidato in BOTOES_DE_CODIGO:
        achado = elemento_visivel(pagina, candidato)
        if achado is not None:
            return achado, candidato
    for alvo in pagina.query_selector_all("button, input[type=submit], input[type=button], a"):
        try:
            if not alvo.is_visible():
                continue
            # `bruto` e o que esta escrito, e vai para o relato da trava; `texto`
            # e a versao sem acento e em minusculas, que serve para comparar.
            # Misturar os dois faria o relato dizer 'botao:"confirmar"' onde a
            # tela diz "Confirmar", e o operador confere o relato contra a tela.
            bruto = (alvo.inner_text() or alvo.get_attribute("value") or "").strip()
            texto = sem_acento(bruto)
        except Exception:
            continue
        if not texto or any(m in texto for m in TEXTOS_A_NUNCA_CLICAR):
            continue
        if any(texto.startswith(m) for m in TEXTOS_DE_CONFIRMAR):
            return alvo, f'botao:"{bruto[:30]}"'
    return None, None


def _responder_segundo_fator(pagina, guarda, identidade, segundos: int) -> bool:
    """Responde o segundo fator que o portal pede para abrir os autos.

    Devolve True quando respondeu, False quando NAO havia o que responder (a
    tela nao pediu codigo). Levanta quando pediu e nao foi possivel responder:
    seguir adiante sem o aceite daria a impressao de que a copia falhou por
    outro motivo.

    Por que isso existe: no eproc do Rio, estar autenticado nao basta para abrir
    os autos inteiros. O clique em "Acesso integra do processo" pede um segundo
    fator novo, como no login. Informado pelo operador em 05/10/2026.
    """
    campo = seletor = None
    for candidato in CAMPOS_DE_CODIGO:
        achado = elemento_visivel(pagina, candidato)
        if achado is not None:
            campo, seletor = achado, candidato
            break
    if campo is None:
        return False

    print("    O portal pede um segundo fator para abrir os autos.")
    cofre = Cofre()
    if not cofre.tem_semente(identidade):
        raise ConteudoInesperado(
            f"o portal pediu codigo para abrir os autos e nao ha semente para "
            f"{identidade.rotulo} no cofre. A consulta acima vale; so a copia parou.")

    restante = cofre.segundos_restantes_do_codigo()
    if restante < 8:
        print(f"    Codigo atual expira em {restante}s; aguardando a proxima janela.")
    codigo = cofre._codigo_segundo_fator(identidade, minimo_segundos=8)

    botao, botao_seletor = _botao_de_confirmar(pagina)
    if botao is None:
        raise ConteudoInesperado(
            "o campo do codigo apareceu, mas nenhum botao de confirmar, nem por "
            "identificador nem por texto. O codigo NAO foi digitado.")

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="segundo fator para abrir os autos",
        conferido_em="execucao atual",
        seletores_clicaveis=(botao_seletor,),
        seletores_preenchiveis=(seletor,),
    ))
    guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
    campo.click()
    campo.fill(codigo)
    guarda.pode_executar(Acao.CLICAR, botao_seletor, url=pagina.url)
    botao.click()
    _assentar(pagina, segundos)
    print("    Codigo do cofre enviado.")
    return True


def _links_das_partes(pagina) -> list:
    """Os links de BAIXAR ARQUIVO PARTE da tela, na ordem em que aparecem.

    Casa pelo texto do link, e nao pelo endereco: o endereco traz um ticket
    gerado na hora, que muda a cada geracao, enquanto o rotulo e estavel. O
    link de forcar nova geracao fica de fora por nome proprio, e nao por
    acidente de ordem.
    """
    achados = []
    for link in pagina.query_selector_all("a[href]"):
        try:
            texto = sem_acento(link.inner_text() or "")
            endereco = link.get_attribute("href") or ""
        except Exception:
            continue
        if MARCA_DE_NOVA_GERACAO in texto:
            continue
        if MARCA_DE_PARTE in texto and endereco:
            achados.append(link)
    return achados


def _gravar_pela_sessao(contexto, endereco: str, arquivo) -> str:
    """Busca o arquivo pelo endereco, usando a sessao que o navegador ja tem.

    Por que nao esperar o evento de download: os links de parte abrem em ABA
    NOVA, conferido em campo em 05/10/2026. O clique funcionava, as duas abas
    abriam com os PDFs, e a espera morria na aba velha, onde download nenhum
    acontece. Mesma armadilha ja vista no e-SAJ, e mesma saida: com o endereco
    em maos, buscar o arquivo pela sessao e mais simples e mais firme que
    perseguir o evento de uma aba que o navegador pode ate fechar sozinho.

    Recusa o que nao for arquivo. Uma pagina de erro do portal tem endereco de
    arquivo e corpo de HTML, e gravada com nome de PDF ela entra no acervo como
    se fossem autos: o advogado so descobre ao abrir, meses depois.
    """
    resposta = contexto.request.get(endereco)
    if not resposta.ok:
        raise ConteudoInesperado(f"o portal respondeu {resposta.status}")
    corpo = resposta.body()
    if corpo[:4] not in (b"%PDF", b"PK\x03\x04"):
        tipo = (resposta.headers or {}).get("content-type", "desconhecido")
        raise ConteudoInesperado(
            f"o que veio nao e PDF nem arquivo compactado (tipo {tipo}, "
            f"{len(corpo)} byte(s))")
    arquivo.write_bytes(corpo)
    return str(arquivo)


class ConteudoInesperado(RuntimeError):
    """O endereco respondeu, mas o que veio nao e arquivo."""


def _baixar_partes_do_eproc(pagina, guarda, destino, chave: str,
                            segundos: int) -> list:
    """Baixa as partes do arquivo completo que o portal ja gerou.

    Devolve a lista dos arquivos gravados, na ordem das partes. Lista vazia
    quer dizer que esta tela nao tem parte nenhuma pronta, que e o caso normal
    logo depois de pedir a geracao.

    Cada parte abre em aba nova. O endereco dessa aba e que vale, e nao o do
    link: ele e o que o navegador de fato resolveu, com ticket, sessao e tudo.
    O link serve para achar e para clicar; a aba, para saber o endereco certo.

    Uma parte que falha NAO cancela as outras: copia parcial e pior que copia
    nenhuma se passar por inteira, entao cada falha e dita em voz alta e quem
    chama decide. O que nao se faz aqui, em hipotese alguma, e clicar no link
    de forcar nova geracao para "tentar de novo": isso descartaria o arquivo
    pronto e devolveria o processo para a fila.
    """
    from pathlib import Path

    links = _links_das_partes(pagina)
    if not links:
        return []

    print(f"    O portal ja tem o arquivo pronto, em {len(links)} parte(s).")
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="baixar as partes do arquivo completo ja gerado",
        conferido_em="execucao atual",
    ))

    destino.mkdir(parents=True, exist_ok=True)
    gravados = []
    for ordem, link in enumerate(links, 1):
        rotulo = f"parte {ordem} de {len(links)}"
        aba = None
        try:
            with pagina_de(pagina).context.expect_page(timeout=segundos * 1000) as info:
                link.click()
            aba = info.value
            try:
                aba.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
            except Exception:
                # Aba que ja virou arquivo nao termina de "carregar", e isso nao
                # e erro: o endereco dela ja e o que interessa.
                pass
            endereco = aba.url
        except Exception:
            # Sem aba nova, resta o endereco do proprio link. Pode faltar o que
            # o portal acrescenta na hora, e por isso e a segunda opcao.
            endereco = link.get_attribute("href") or ""

        if not endereco:
            print(f"      {rotulo}: nao deu para saber o endereco do arquivo.")
            _fechar(aba)
            continue

        guarda.pode_executar(Acao.BAIXAR, endereco, url=pagina.url)
        nome = _nome_do_endereco(endereco) or f"{chave}-parte{ordem}.pdf"
        arquivo = Path(destino) / f"integra-parte{ordem}-{nome}"
        try:
            _gravar_pela_sessao(pagina_de(pagina).context, endereco, arquivo)
        except Exception as exc:
            print(f"      {rotulo}: nao gravou ({type(exc).__name__}: {exc}).")
            _fechar(aba)
            continue
        print(f"      {rotulo}: {arquivo.name} "
              f"({arquivo.stat().st_size // 1024} KB)")
        gravados.append(str(arquivo))
        _fechar(aba)

    if gravados and len(gravados) != len(links):
        # Dizer isto importa mais que o numero: um acervo com metade dos autos
        # que se apresenta como integra e uma armadilha para a proxima consulta,
        # que vai achar que ja tem tudo.
        print(f"      ATENCAO: {len(gravados)} de {len(links)} partes gravadas. "
              "A copia esta INCOMPLETA.")
    return gravados


def _fechar(aba) -> None:
    if aba is None:
        return
    try:
        aba.close()
    except Exception:
        pass


def _nome_do_endereco(endereco: str) -> str:
    """O nome do arquivo que o endereco carrega, quando carrega.

    O eproc poe o nome no parametro `file`, e ele ja vem com numero do processo
    e data da geracao, que e exatamente o que se quer no acervo.
    """
    from urllib.parse import parse_qs, urlparse

    try:
        campos = parse_qs(urlparse(endereco).query)
    except Exception:
        return ""
    for chave in ("file", "arquivo", "nome"):
        valores = campos.get(chave) or []
        if valores:
            return valores[0].rstrip("/").split("/")[-1][:120]
    return ""


# Rotulo do alvo no relato da trava. O link nao tem identificador na tela do
# Rio, entao o que o identifica e o proprio texto.
SELETOR_DO_ACESSO = 'a:"Acesso integra do processo"'


def _integra_pelo_acesso(pagina, guarda, acesso, destino, chave: str,
                         identidade, segundos: int) -> list:
    """Caminho da copia no eproc do Rio, pelo quadro "Acoes" da tela do processo.

    Tres diferencas em relacao ao do Tribunal Regional Federal da 2a Regiao, e
    as tres vieram da tela real e do operador, em 05/10/2026: o alvo e um link
    com texto, e nao um botao com identificador; o clique pede um SEGUNDO FATOR,
    porque estar autenticado nao basta para abrir os autos inteiros; e o
    resultado pode vir em aba nova.

    Do segundo fator em diante, o caminho volta a ser o mesmo do eproc ja
    conhecido: partes prontas, ou pedido de geracao. Se nao for, o relato da
    tela diz o que e, e nada e adivinhado.
    """
    print('    O portal do Rio usa "Acesso integra do processo", e nao um botao.')
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="abrir a integra do processo pelo quadro Acoes",
        conferido_em="execucao atual",
        seletores_clicaveis=(SELETOR_DO_ACESSO,),
    ))
    guarda.pode_executar(Acao.CLICAR, SELETOR_DO_ACESSO, url=pagina.url)

    abertas: list = []
    try:
        pagina_de(pagina).context.on("page", lambda p: abertas.append(p))
    except Exception:
        pass
    acesso.click()
    _assentar(pagina, segundos)

    # A integra pode abrir em aba nova, como as partes do arquivo. Quando abre,
    # e nela que esta tudo o que interessa daqui para a frente.
    janela = pagina
    if abertas:
        janela = abertas[-1]
        try:
            janela.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
        except Exception:
            pass
        _assentar(janela, segundos)
        print("    Os autos abriram em aba nova.")
    else:
        # Caminho do Rio: nao ha aba nova, ha quadro embutido na mesma pagina.
        quadro = quadro_da_integra(pagina)
        if quadro is not None:
            janela = quadro
            print("    Os autos abriram num quadro embutido na propria pagina.")

    try:
        respondeu = _responder_segundo_fator(janela, guarda, identidade, segundos)
    except ConteudoInesperado as exc:
        print(f"    [PAROU] {exc}")
        _relatar_tela(janela, "TELA DO SEGUNDO FATOR DA INTEGRA")
        return []

    if respondeu:
        # O quadro de antes NAO serve mais. Ao aceitar o codigo, o portal troca
        # o conteudo do quadro, e o objeto antigo fica solto: qualquer leitura
        # nele levanta erro do Playwright sem mensagem util. Foi o que aconteceu
        # em campo em 05/10/2026, com a execucao terminando em "(Error)" seco,
        # depois de o codigo ter sido aceito.
        _assentar(pagina, segundos)
        renovado = quadro_da_integra(pagina)
        janela = renovado if renovado is not None else pagina

    try:
        recados = _mensagens_de_erro(janela)
    except Exception:
        recados = []
    for recado in recados:
        print(f"    O portal disse: {recado}")

    # O ACHADO de 05/10/2026: liberado o acesso, a PAGINA DE CIMA ganha
    # `#btnDownloadCompletoRS`, que antes nao existia nela. E o mesmo botao do
    # Tribunal Regional Federal da 2a Regiao. Daqui em diante os dois tribunais
    # sao o mesmo portal, e seria desperdicio escrever um caminho so para o Rio.
    botao = elemento_visivel(pagina, BOTAO_INTEGRA)
    if botao is not None:
        print("    Liberado o acesso, o botao de Download Completo apareceu.")
        return _fluxo_do_botao_de_copia(pagina, guarda, botao, destino, chave,
                                        segundos)

    # Daqui para a frente a janela pode ser um quadro que o portal troca sob os
    # pes. Qualquer erro vira relato, e nao traceback: a consulta ja terminou, e
    # o que falta e descobrir como e a tela dos autos no Rio.
    try:
        partes = _baixar_partes_do_eproc(janela, guarda, destino, chave, segundos)
    except Exception as exc:
        print(f"    A leitura da tela dos autos falhou ({type(exc).__name__}: "
              f"{str(exc).strip().splitlines()[0][:120]}).")
        _relatar_tela(pagina, "PAGINA DE CIMA")
        return []
    if partes:
        return partes

    baixado = _gerar_integra_do_eproc(janela, guarda, segundos)
    if baixado is GERACAO_PEDIDA:
        return []
    if baixado is not None:
        from pathlib import Path

        destino.mkdir(parents=True, exist_ok=True)
        sugerido = baixado.suggested_filename or f"{chave}-integra.pdf"
        arquivo = Path(destino) / f"integra-{sugerido}"
        baixado.save_as(str(arquivo))
        return [str(arquivo)]

    print("    A tela dos autos nao tem parte pronta nem botao de gerar conhecido.")
    _relatar_tela(janela, "TELA DOS AUTOS")
    return []


def _baixar_integra(pagina, guarda, destino, chave: str, identidade,
                    segundos: int) -> list:
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
    from pathlib import Path  # noqa: F401  (usado no fluxo do botao)

    botao = elemento_visivel(pagina, BOTAO_INTEGRA)
    if botao is None:
        # Beco, se parar aqui calado. Conferido em campo em 05/10/2026: o eproc
        # do Rio nao tem `#btnDownloadCompletoRS` na tela do processo, e o
        # comando dizia so "botao de copia integral nao encontrado nesta tela",
        # sem entregar nada com que descobrir qual e o botao de la. O relato
        # lista os botoes e as ligacoes com termo de copia, que e exatamente o
        # material para escrever o seletor certo sem adivinhar.
        # Antes de desistir, o caminho do Rio: o quadro "Acoes" da tela do
        # processo traz "Acesso integra do processo", que nao e botao com
        # identificador, e sim um link com texto.
        acesso = _acesso_a_integra(pagina)
        if acesso is not None:
            return _integra_pelo_acesso(pagina, guarda, acesso, destino, chave,
                                        identidade, segundos)
        print(f"    O botao {BOTAO_INTEGRA} nao esta nesta tela, e tambem nao ha")
        print('    link de "acesso a integra do processo".')
        _relatar_tela(pagina, "TELA DO PROCESSO")
        itens = _itens_do_menu(pagina)
        if itens:
            print(f"\n    MENU DO PORTAL ({len(itens)} item(ns)), caso a copia dos")
            print("    autos more no menu e nao na tela do processo:")
            for item in itens:
                print(f"      {item}")
        return []
    return _fluxo_do_botao_de_copia(pagina, guarda, botao, destino, chave, segundos)


def _fluxo_do_botao_de_copia(pagina, guarda, botao, destino, chave: str,
                             segundos: int) -> list:
    """Do botao `#btnDownloadCompletoRS` em diante: gerar e baixar as partes.

    Separado de `_baixar_integra` porque o Rio chega a este mesmo botao por
    outro caminho. Conferido em campo em 05/10/2026: no eproc do Rio o botao NAO
    existe na tela do processo e PASSA A EXISTIR depois que o acesso a integra e
    liberado pelo segundo fator. Daquele ponto em diante, os dois tribunais sao
    o mesmo portal.
    """
    from pathlib import Path

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
        with pagina.expect_download(timeout=TETO_DO_DOWNLOAD_DIRETO * 1000) as info:
            botao.click()
    except Exception:
        # Caminho NORMAL, e nao falha. Dizer "nao devolveu arquivo" aqui fazia
        # o relato comecar por um erro que nao existe, e quem lesse so o comeco
        # concluiria que a copia tinha dado errado quando ela mal tinha
        # comecado.
        print("    O botao leva a tela de geracao, e nao devolve arquivo direto.")
        _assentar(pagina, segundos)
        # Ordem deliberada. Primeiro procura o que JA ESTA PRONTO: pedir
        # geracao nova por cima de um arquivo pronto descartaria o arquivo e
        # devolveria o processo para a fila. So quando nao ha parte nenhuma e
        # que se pede a geracao.
        partes = _baixar_partes_do_eproc(pagina, guarda, destino, chave, segundos)
        if partes:
            return partes
        baixado = _gerar_integra_do_eproc(pagina, guarda, segundos)
        if baixado is GERACAO_PEDIDA:
            return []
        if baixado is None:
            print("    Segue o que ha na tela, para o seletor ser conferido antes de")
            print("    virar codigo. Nada mais foi clicado.")
            _relatar_tela(pagina, "TELA APOS O CLIQUE")
            for i, p in enumerate(nova):
                try:
                    p.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                _relatar_tela(p, f"ABA NOVA {i + 1}")
            raise
        destino.mkdir(parents=True, exist_ok=True)
        sugerido = baixado.suggested_filename or f"{chave}-integra.zip"
        arquivo = Path(destino) / f"integra-{sugerido}"
        baixado.save_as(str(arquivo))
        return [str(arquivo)]

    baixado = info.value
    destino.mkdir(parents=True, exist_ok=True)
    sugerido = baixado.suggested_filename or f"{chave}-integra.zip"
    arquivo = Path(destino) / f"integra-{sugerido}"
    baixado.save_as(str(arquivo))
    return [str(arquivo)]


# Sistemas que TEM caminho de consulta escrito e conferido em tela real. O que
# nao esta aqui e recusado antes de autenticar, em vez de gastar uma tentativa
# do teto da conta para descobrir no meio do caminho.
#
#   esaj   conferido em campo em 22/09/2026, ponta a ponta, ate a integra.
#   eproc  busca rapida em toda tela; a autenticacao segue barrada pelo
#          Cloudflare, mas a consulta em si esta escrita.
#   pje    caminho fotografado pelo operador em 30/09/2026, do menu ate os autos
#          em aba nova. Os identificadores dos campos nao apareceram nas fotos,
#          entao o adaptador procura os campos pela forma e confere o que
#          digitou antes de pesquisar; se a forma nao bater, ele para.
SISTEMAS_COM_CONSULTA = frozenset({"esaj", "eproc", "pje"})

# Conferidos na tela real do TRF2 em 02/10/2026, depois da selecao de perfil:
# `input#txtNumProcessoPesquisaRapida` com rotulo "Número do processo", e
# `button[name=btnPesquisaRapidaSubmit]`, os dois em `form=formPesquisaRapida`.
# A mesma leitura confirmou as duas coisas que justificam usar a busca rapida
# aqui: o portal desemboca na tela de cadastro (`frmPessoaAlteracao`), e a busca
# vive em formulario separado dela, entao consultar nao encosta no cadastro. E
# confirmou tambem o par visivel/oculto de cada campo, que e o motivo de
# `elemento_visivel` existir.
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
        from .extracao import esperar_tela_do_processo, extrair_processo

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
        esperar_tela_do_processo(pagina, 45)
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
    aceitar_termo: bool = False,
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

    # A recusa vem ANTES de autenticar, e essa ordem e o ponto. Ate aqui, pedir
    # consulta num sistema sem adaptador autenticava primeiro, gastava uma
    # tentativa do teto da conta e so entao falhava, com uma mensagem que ainda
    # por cima acusava a tela errada ("campo de busca rapida nao encontrado"),
    # como se o portal tivesse mudado. Gastar credencial para descobrir que o
    # programa nao sabe fazer aquilo e o pior desperdicio possivel: ele ja sabia
    # disso antes de abrir o navegador.
    if (sistema or "").lower().strip() not in SISTEMAS_COM_CONSULTA:
        print(f"  [NAO IMPLEMENTADO] A consulta de processo ainda nao existe "
              f"para o sistema {sistema!r}.", file=sys.stderr)
        print(f"  Hoje ha consulta para: {', '.join(sorted(SISTEMAS_COM_CONSULTA))}.",
              file=sys.stderr)
        print("  Nada foi enviado ao portal e nenhuma tentativa de login foi "
              "gasta.", file=sys.stderr)
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

            from .esaj import expandir_movimentacoes_ate_o_fim
            from .esaj import extrair as extrair_esaj
            from .esaj import extrair_movimentacoes as _contar_movs

            # O historico verdadeiro so existe depois deste clique, e uma
            # expansao so trazia um pedaco. Autorizado pelo operador em 22 de
            # setembro de 2026: clicar ate a opcao sumir.
            expansao = expandir_movimentacoes_ate_o_fim(
                pagina, guarda, segundos, contar=lambda p: len(_contar_movs(p))
            )
            if expansao["expansoes"]:
                print(f"  Movimentacoes expandidas {expansao['expansoes']}x "
                      f"({expansao['motivo']}).")
                estado_local.registrar(
                    acao="expandir_movimentacoes", tribunal=identidade.tribunal,
                    sistema=identidade.sistema, numero=numero.formatado,
                    resultado=f"{expansao['expansoes']}x, {expansao['motivo']}",
                )
                if expansao["motivo"] == "teto de expansoes atingido":
                    print("    ATENCAO: o teto foi atingido e o botao ainda estava la.")
                    print("    A lista pode continuar incompleta.")

            dados = extrair_esaj(pagina)
            dados["numero"] = numero.formatado
            dados["tribunal"] = identidade.tribunal
            dados["sistema"] = identidade.sistema
            dados["grau"] = numero.grau
            dados["endereco"] = pagina.url

            principais = dados["principais"]
            print("\n  EXTRAIDO:")
            for rotulo in ("classe", "assunto", "foro", "vara", "juiz"):
                if principais.get(rotulo):
                    print(f"    {rotulo}: {principais[rotulo]}")
            print(f"    partes: {dados['totais']['partes']}   "
                  f"movimentacoes: {dados['totais']['movimentacoes']}")
            if dados["movimentacoes_origem"] == "varredura":
                # Vindas de tabela sem identificador. A pagina do e-SAJ tem
                # varias com data: peticoes diversas, incidentes, audiencias.
                # Chama-las de movimentacoes seria afirmar o que nao se sabe, e
                # o advogado leria um historico que talvez nao seja o historico.
                print("    ATENCAO: estas linhas vieram de uma tabela SEM identificador,")
                print("    achada por ter datas. A pagina tem outras tabelas com data")
                print("    (peticoes, incidentes, audiencias). CONFIRA no portal se e")
                print("    mesmo o historico de movimentacoes antes de confiar nelas.")
            if not dados["movimentacoes_completas"]:
                # Entregar a lista parcial como completa faria o advogado
                # concluir que nao ha andamento anterior, que e pior que nao
                # entregar nada. O clique que expande ainda nao foi conferido
                # em campo, e nao vai ser adivinhado.
                print("    ATENCAO: a pagina ainda oferece \"exibir mais movimentacoes\".")
                print("    A lista acima e PARCIAL. O clique que expande ainda nao foi")
                print("    conferido em campo, entao nao e dado por este comando.")
            if dados["pasta_digital"]:
                print(f"    integra disponivel em: {dados['pasta_digital'][:70]}")
            for m in dados["movimentacoes"][:5]:
                print(f"      {m['data']}  {m['descricao'][:70]}")

            if documentos and documentos != "nenhum":
                from .core.acervo import (
                    AcervoIndisponivel, carregar_indice, garantir_pasta,
                )
                from .esaj import copiar_pasta_digital

                try:
                    indice = carregar_indice(numero.apenas_digitos, numero.formatado)
                    pasta = garantir_pasta(numero.apenas_digitos)
                    print(f"\n  Pasta do processo: {pasta}")
                    guarda.permitir_download = True
                    # O caminho que funciona e o que o operador descreveu e
                    # fotografou: clicar em "Visualizar autos", marcar "Todas",
                    # "Baixar PDF", "Arquivo unico" e "Continuar". Buscar pelo
                    # endereco falhou por tres caminhos conferidos em campo, porque
                    # o ticket da Pasta Digital so e montado no instante do clique.
                    from .esaj import copiar_autos_pelo_visualizador

                    resultado = copiar_autos_pelo_visualizador(
                        pagina, guarda, pasta, numero.apenas_digitos, segundos
                    )
                    janela = resultado.pop("janela", None)
                    if resultado["situacao"] != "gravada" and janela is not None:
                        # Parou no meio: relatar a tela e o que permite escrever o
                        # passo que faltou, sem adivinhar seletor.
                        if resultado["situacao"] == "download_perdido":
                            print(f"    O arquivo foi baixado mas nao pode ser gravado: "
                                  f"{resultado.get('detalhe', '')}")
                        else:
                            print(f"    Nao concluiu no passo {resultado.get('passo', '?')}.")
                        _relatar_tela(janela, "PASTA DIGITAL")
                        _relatar_estrutura_de_dados(janela)
                    if janela is not None:
                        try:
                            janela.close()
                        except Exception:
                            pass
                    guarda.permitir_download = False
                    if resultado["situacao"] == "gravada":
                        from pathlib import Path as _P

                        from .core.acervo import REPETIDA_IGUAL, REPETIDA_SUSPEITA

                        baixado = _P(resultado["arquivo"])
                        veredicto, gemeo = indice.avaliar_repeticao(baixado)
                        if veredicto == REPETIDA_IGUAL:
                            # Indexar de novo diria que o processo tem o dobro de
                            # folhas que tem. Folha errada em citacao e o pior
                            # defeito possivel neste indice.
                            print(f"    COPIA REPETIDA: identica a "
                                  f"{_P(gemeo.arquivo).name} ({gemeo.faixa()}), ja no acervo.")
                            print("    O indice NAO foi alterado, para nao renumerar folhas.")
                            if baixado != _P(gemeo.arquivo) and _P(gemeo.arquivo).is_file():
                                try:
                                    baixado.unlink()
                                    print("    O arquivo repetido foi removido da pasta.")
                                except OSError as exc:
                                    print(f"    Nao consegui remover o repetido: {exc}")
                            estado_local.registrar(
                                acao="copia_repetida", tribunal=identidade.tribunal,
                                sistema=identidade.sistema, numero=numero.formatado,
                                documento=str(baixado), resultado=gemeo.faixa(),
                            )
                        elif veredicto == REPETIDA_SUSPEITA:
                            print(f"    ATENCAO: esta copia tem o mesmo numero de paginas de "
                                  f"{_P(gemeo.arquivo).name} ({gemeo.faixa()}), mas o "
                                  "conteudo difere.")
                            print("    Pode ser a MESMA copia com data de geracao diferente,")
                            print("    que o proprio portal escreve dentro do PDF. NAO indexei:")
                            print("    numerar folha errada e pior que nao numerar. O arquivo")
                            print(f"    esta em {baixado}. Confira e me diga o que fazer.")
                            estado_local.registrar(
                                acao="copia_suspeita_de_repeticao",
                                tribunal=identidade.tribunal, sistema=identidade.sistema,
                                numero=numero.formatado, documento=str(baixado),
                                resultado=gemeo.faixa(),
                            )
                        else:
                            item = indice.acrescentar(baixado, "integra")
                            indice.gravar()
                            print(f"    COPIA INTEGRAL gravada: {baixado.name} "
                                  f"({item.faixa()})")
                            estado_local.registrar(
                                acao="copia_integral", tribunal=identidade.tribunal,
                                sistema=identidade.sistema, numero=numero.formatado,
                                documento=resultado["arquivo"], resultado=item.faixa(),
                            )
                    else:
                        print(f"    COPIA NAO CONCLUIDA ({resultado['situacao']}): "
                              f"{resultado.get('detalhe', '')}")
                        for pista in resultado.get("pistas") or []:
                            print(f"      {pista}")
                        print("    Nada foi inventado: o download real sera escrito depois")
                        print("    de conferido o que a pasta digital devolve.")
                except AcervoIndisponivel as exc:
                    # A consulta ja terminou e ja foi gravada. Derrubar tudo por causa da
                    # pasta de copias seria jogar fora o trabalho que deu certo por causa
                    # do que deu errado depois.
                    guarda.permitir_download = False
                    print(f"\n  [ACERVO] {exc}")
                    print("  A consulta acima vale e ja esta no arquivo indicado abaixo.")
                    print("  Repita o comando mais tarde para a parte de copia, ou confira")
                    print("  se o Google Drive esta sincronizando.")

            dados["arquivo"] = str(_gravar_consulta(dados, numero.apenas_digitos))
            # Alimenta a comparacao de novidades, igual ao eproc. Sem isto, Sao
            # Paulo ficaria fora do monitoramento: a consulta traria os dados e
            # o `verificar_novos_andamentos` nunca saberia que eles existiram.
            # A movimentacao do e-SAJ nao tem numero de evento, so data e
            # descricao, entao a data faz as vezes de codigo; comparar por
            # (data, descricao) e o que a pagina permite.
            estado_local.gravar_snapshot(
                numero.apenas_digitos,
                [{"data_hora": m["data"], "codigo": m["data"], "nome": m["descricao"]}
                 for m in dados["movimentacoes"]],
            )
            print(f"\n  Conteudo completo em: {dados['arquivo']}")
            print("  O arquivo contem dado de cliente. Nao o cole em conversa nenhuma.")
            estado_local.registrar(
                acao="consulta_processo_autenticada", tribunal=identidade.tribunal,
                sistema=identidade.sistema, numero=numero.formatado,
                resultado=f"{dados['totais']['movimentacoes']} movimentacao(oes)",
            )
            return 0

        if identidade.sistema == "pje":
            from .pje import (ConsultaPJeIndisponivel, abrir_processo,
                              buscar_autenticado, parece_aviso_de_responsabilidade)

            print("  PJe, consulta autenticada (caminho fotografado em 30/09/2026).")
            try:
                final = buscar_autenticado(pagina, guarda, numero, url, segundos)
            except ConsultaPJeIndisponivel as exc:
                print(f"  [PAROU] {exc}")
                _relatar_tela(pagina, "TELA ONDE PAROU")
                _relatar_estrutura_de_dados(pagina)
                return 1
            print(f"  Endereco: {final}")

            recados = _mensagens_de_erro(pagina)
            for recado in recados:
                print(f"    O portal disse: {recado}")

            estado_local.registrar(
                acao="consulta_processo_autenticada", tribunal=identidade.tribunal,
                sistema=identidade.sistema, numero=numero.formatado,
                resultado="busca enviada",
            )

            # Abrir os autos e um SEGUNDO passo, separado de proposito: o clique
            # no numero levanta o aviso de responsabilidade da resolucao nº. 121
            # do Conselho Nacional de Justica, e aceita-lo e ato do advogado, nao
            # do programa. Sem o aceite explicito o comando mostra o texto do
            # aviso e para.
            try:
                aba, avisos = abrir_processo(
                    pagina, guarda, numero, aceitar_termo=aceitar_termo,
                    segundos=segundos)
            except ConsultaPJeIndisponivel as exc:
                print(f"  [PAROU] {exc}")
                _relatar_tela(pagina, "TELA DO RESULTADO")
                return 1

            for aviso in avisos:
                print("\n  O PORTAL PEDIU UM ACEITE, E ELE NAO FOI DADO:")
                for pedaco in aviso.splitlines():
                    if pedaco.strip():
                        print(f"    {pedaco.strip()}")
                if parece_aviso_de_responsabilidade(aviso):
                    print("    Este e o aviso de responsabilizacao civil, "
                          "administrativa e criminal.")

            if aba is None:
                if avisos:
                    print("\n  Nada foi aberto. Leia o aviso acima; se for o caso de")
                    print("  aceita-lo, repita o comando com --aceito-o-termo.")
                else:
                    print("\n  O clique no numero nao abriu aba nova nem mostrou aviso.")
                    print("  Nada foi aberto.")
                _relatar_tela(pagina, "TELA DO RESULTADO")
                return 1

            print("\n  O aceite foi dado pelo operador e os autos abriram em aba nova.")
            estado_local.registrar(
                acao="aceite_do_termo_de_responsabilidade",
                tribunal=identidade.tribunal, sistema=identidade.sistema,
                numero=numero.formatado, resultado="autos abertos",
            )
            # A leitura da linha do tempo do PJe ainda NAO esta escrita: a
            # estrutura dela nao foi lida de tela real. O que sai aqui e a forma
            # da pagina, sem conteudo, que e o que permite escreve-la depois.
            _relatar_tela(aba, "AUTOS DO PROCESSO (ABA NOVA)")
            _relatar_estrutura_de_dados(aba)
            print("\n  A extracao da linha do tempo do PJe ainda nao foi escrita.")
            print("  O relato acima e a forma da pagina, sem conteudo, e e dele que")
            print("  ela sera escrita. Nada foi inventado.")
            try:
                aba.close()
            except Exception:
                pass
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

        from .extracao import esperar_tela_do_processo, extrair_processo, resumo

        # Esperar o CONTEUDO, e nao so a rede. O eproc chega nesta tela com
        # `autocarregar=true`, navega no meio do caminho e traz os eventos
        # depois do desenho: ler naquele instante devolve zero tabela, que e
        # indistinguivel de processo inexistente.
        _assentar(pagina, segundos)
        chegou = esperar_tela_do_processo(pagina, segundos)
        if chegou == "nada":
            print("  A tela do processo nao apareceu no tempo dado.")
        elif chegou == "capa":
            print("  A capa do processo apareceu, mas nenhuma linha de evento.")
        dados = extrair_processo(pagina, numero.formatado)
        if not dados["eventos"]:
            print("\n  [ATENCAO] Nenhum evento extraido. A tela pode ter outra")
            print("  estrutura, ou o processo pode estar em segredo de justica.")
            print(f"  Tabelas na pagina: "
                  f"{[t.get_attribute('id') or '-' for t in pagina.query_selector_all('table')]}")
            # Conteudo dentro de quadro embutido e a explicacao mais comum para
            # "zero tabelas" numa tela que visivelmente tem tabelas: a leitura
            # de cima nao atravessa o quadro. Contar por quadro separa isso de
            # processo que realmente nao existe ali.
            try:
                for quadro in pagina.frames[1:]:
                    quantas = len(quadro.query_selector_all("table"))
                    print(f"    quadro embutido {quadro.name or '(sem nome)'}: "
                          f"{quantas} tabela(s)")
            except Exception as exc:
                print(f"    Quadros embutidos ilegiveis: {type(exc).__name__}")
            # O relato inteiro, e nao so a contagem. Sem ele este ponto vira um
            # beco: o comando diz que nao achou e nao entrega nada com que
            # escrever a leitura certa. E o mesmo que o e-SAJ e o PJe ja fazem
            # quando param no meio.
            _relatar_tela(pagina, "TELA DA CONSULTA")
            _relatar_estrutura_de_dados(pagina)
            print("\n  RELATO DA TRAVA:")
            for linha in guarda.relato():
                print(f"    {linha}")
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
                AcervoIndisponivel, carregar_indice, decidir_estrategia,
                garantir_pasta, pdfs_fora_do_indice,
            )
            from .documentos import baixar_documentos_dos_eventos

            try:
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
                        # A copia do eproc vem PARTIDA: conferido em campo em
                        # 05/10/2026, com duas partes. O numero depende do
                        # processo, entao aqui se recebe uma lista.
                        arquivos = _baixar_integra(
                            pagina, guarda, pasta, numero.apenas_digitos,
                            identidade, segundos
                        )
                    except Exception as exc:
                        arquivos, falhou = [], True
                        # O nome da classe sozinho nao diz nada: o Playwright chama
                        # tudo de `Error`, e a execucao de 05/10/2026 terminou num
                        # "(Error)" seco que nao permitia decidir nada. A PRIMEIRA
                        # linha da mensagem diz o essencial; o resto e o despejo do
                        # log, que sepultava o relato da tela impresso acima.
                        primeira = str(exc).strip().splitlines()[:1]
                        detalhe = primeira[0][:160] if primeira else "sem mensagem"
                        print(f"    Copia integral nao concluida "
                              f"({type(exc).__name__}: {detalhe}).")
                    if arquivos:
                        from pathlib import Path as _P

                        from .core.acervo import maior_evento

                        ate = maior_evento(dados["eventos"])
                        # Cada parte entra como um item, e a numeracao de folhas
                        # segue continua de uma para a outra. Juntar as partes num
                        # arquivo so seria mais bonito e exigiria supor o formato
                        # delas, que ainda nao foi visto.
                        for ordem, arquivo in enumerate(arquivos, 1):
                            item = indice.acrescentar(
                                _P(arquivo), "integra", evento_ate=ate,
                                rotulo=(f"parte {ordem} de {len(arquivos)}"
                                        if len(arquivos) > 1 else None),
                            )
                            print(f"    gravada: {_P(arquivo).name}  ({item.faixa()})")
                            estado_local.registrar(
                                acao="copia_integral", tribunal=identidade.tribunal,
                                sistema=identidade.sistema, numero=numero.formatado,
                                documento=arquivo, resultado=item.faixa(),
                            )
                        print(f"    cobrindo ate o evento {ate}")
                    elif not falhou:
                        # Mensagem NEUTRA de proposito. Ela dizia "botao de copia
                        # integral nao encontrado nesta tela", o que passou a ser
                        # falso no dia em que o pedido de geracao passou a ser
                        # aceito: o botao foi encontrado, clicado, e o portal
                        # respondeu que esta montando o arquivo. Quem le so o fim
                        # da saida concluiria o contrario do que aconteceu. O
                        # motivo verdadeiro, qualquer que seja, ja foi impresso
                        # pelas funcoes acima, que sabem qual e.
                        print("    Nenhum arquivo gravado nesta execucao; o motivo "
                              "esta logo acima.")

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
            except AcervoIndisponivel as exc:
                # A consulta ja terminou e ja foi gravada. Derrubar tudo por causa da
                # pasta de copias seria jogar fora o trabalho que deu certo por causa
                # do que deu errado depois.
                guarda.permitir_download = False
                print(f"\n  [ACERVO] {exc}")
                print("  A consulta acima vale e ja esta no arquivo indicado abaixo.")
                print("  Repita o comando mais tarde para a parte de copia, ou confira")
                print("  se o Google Drive esta sincronizando.")

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

    ac = sub.add_parser(
        "acompanhar",
        help="VOCE navega e o programa le a tela onde voce parar",
    )
    ac.add_argument("--url", default=None,
                    help="endereco de partida; sem isto, o do portal no .env")
    ac.add_argument("--tribunal", default=None, help="por exemplo TJRJ")
    ac.add_argument("--sistema", default=None, help="por exemplo dcp")
    ac.add_argument("--segundos", type=int, default=30)
    ac.add_argument("--teto", type=int, default=20,
                    help="quantas telas, no maximo, podem ser registradas")

    cpu = sub.add_parser(
        "consulta-publica",
        help="consulta o processo na tela publica do portal, sem login",
    )
    cpu.add_argument("--url", default=None, help=AJUDA_URL)
    cpu.add_argument("--tribunal", required=True)
    cpu.add_argument("--sistema", required=True)
    cpu.add_argument("--processo", default=None)
    cpu.add_argument("--grau", type=int, default=1)
    cpu.add_argument("--oculto", action="store_true")
    cpu.add_argument("--segundos", type=int, default=30)

    sub.add_parser(
        "ambiente",
        help="diz onde o programa procura a configuracao e o que encontrou la",
    )

    ri = sub.add_parser(
        "reindexar",
        help="refaz o indice de folhas de um processo a partir dos arquivos na pasta",
    )
    ri.add_argument("--processo", required=True)
    ri.add_argument("--confirmar", action="store_true",
                    help="sem isto e ensaio: mostra o que faria e nao altera nada")

    m = sub.add_parser(
        "mapear",
        help="le a tela de entrada de cada portal do .env e grava um mapa por portal",
    )
    m.add_argument("--portal", action="append", dest="alvos", default=None,
                   help="TRIBUNAL/sistema, repetivel; sem isto, todos os do .env")
    m.add_argument("--oculto", action="store_true")
    m.add_argument("--segundos", type=int, default=30)

    s = sub.add_parser(
        "sessao",
        help="diz se a sessao guardada ainda vale, sem gastar tentativa nem codigo",
    )
    s.add_argument("--url", default=None, help=AJUDA_URL)
    s.add_argument("--tribunal", required=True)
    s.add_argument("--sistema", required=True)
    s.add_argument("--oculto", action="store_true")
    s.add_argument("--segundos", type=int, default=30)

    e = sub.add_parser(
        "ensaiar-login",
        help="preenche o formulario e confere o efeito, SEM clicar em Entrar",
    )
    e.add_argument("--url", default=None, help=AJUDA_URL)
    e.add_argument("--tribunal", required=True, help="por exemplo TRF2")
    e.add_argument("--sistema", required=True, help="por exemplo eproc")
    e.add_argument("--campo-usuario", default=None)
    e.add_argument("--campo-senha", default=None)
    e.add_argument("--campo-senha-oculto", default=None)
    e.add_argument("--botao-entrar", default=None,
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
    t.add_argument("--campo-usuario", default=None)
    t.add_argument("--campo-senha", default=None)
    t.add_argument("--campo-senha-oculto", default=None)
    t.add_argument("--botao-entrar", default=None)
    t.add_argument("--oculto", action="store_true")
    t.add_argument("--segundos", type=int, default=45)
    t.add_argument("--espera-humana", type=int, default=ESPERA_HUMANA_PADRAO, dest="espera_humana",
                     help="segundos para o operador marcar a caixa do desafio do Cloudflare")

    a = sub.add_parser("autenticar", help="credencial e segundo fator, numa sessao so")
    a.add_argument("--url", default=None, help=AJUDA_URL)
    a.add_argument("--tribunal", required=True)
    a.add_argument("--sistema", required=True)
    a.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado")
    a.add_argument("--campo-usuario", default=None)
    a.add_argument("--campo-senha", default=None)
    a.add_argument("--campo-senha-oculto", default=None)
    a.add_argument("--botao-entrar", default=None)
    a.add_argument("--campo-codigo", default=None)
    a.add_argument("--botao-validar", default=None)
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
    cp.add_argument("--campo-usuario", default=None)
    cp.add_argument("--campo-senha", default=None)
    cp.add_argument("--campo-senha-oculto", default=None)
    cp.add_argument("--botao-entrar", default=None)
    cp.add_argument("--campo-codigo", default=None)
    cp.add_argument("--botao-validar", default=None)
    cp.add_argument("--perfil", default=None)
    cp.add_argument("--documentos", default="auto",
                    help="'auto' (padrao: integra se nao ha copia, complemento se ha), "
                         "'integra', 'ultimos:N' ou 'nenhum'")
    cp.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado")
    cp.add_argument("--aceito-o-termo", action="store_true", dest="aceitar_termo",
                    help="aceita o aviso de responsabilidade que o PJe levanta ao abrir "
                         "os autos (resolucao nº. 121 do Conselho Nacional de Justica). "
                         "Sem esta opcao o comando mostra o texto do aviso e para: o "
                         "aceite e ato do advogado, nao do programa")
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
        if args.comando not in ("reconhecer", "mapear", "reindexar", "ambiente"):
            _do_ambiente(args)
            completar_seletores(args)
        if args.comando == "reconhecer":
            return reconhecer(args.url, oculto=args.oculto, segundos=args.segundos)
        if args.comando == "acompanhar":
            if not args.url:
                if not (args.tribunal and args.sistema):
                    print("Informe --url, ou --tribunal e --sistema para usar o "
                          "endereco do .env.", file=sys.stderr)
                    return 1
                _do_ambiente(args)
            return acompanhar(args.url, segundos=args.segundos, teto=args.teto)
        if args.comando == "consulta-publica":
            if not args.processo:
                print("Nenhum processo informado. Passe --processo, ou defina "
                      "o de teste no .env.", file=sys.stderr)
                return 1
            return consulta_publica(args.tribunal, args.sistema, args.processo,
                                    args.url, oculto=args.oculto,
                                    segundos=args.segundos)
        if args.comando == "ambiente":
            return mostrar_ambiente()
        if args.comando == "reindexar":
            return reindexar(args.processo, confirmar=args.confirmar)
        if args.comando == "mapear":
            return mapear(args.alvos, oculto=args.oculto, segundos=args.segundos)
        if args.comando == "sessao":
            return conferir_sessao(args.url, args.tribunal, args.sistema,
                                   oculto=args.oculto, segundos=args.segundos)
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
                aceitar_termo=args.aceitar_termo,
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
    except Exception as exc:
        # Rede de seguranca so para UM caso, e nao para erro em geral: a janela
        # do navegador fechada. Ela e fechada pelo operador, e em 30/09/2026
        # isso subiu como traceback de Playwright no meio de uma autenticacao
        # que tinha dado certo, o que parece defeito grave e nao e. Qualquer
        # outro erro continua subindo inteiro: esconde-lo seria pior.
        if "has been closed" not in str(exc):
            raise
        print("\n  [PARADO] A janela do navegador nao esta mais aberta.", file=sys.stderr)
        print("  Se foi voce que a fechou, ou que concluiu o login por la, nada",
              file=sys.stderr)
        print("  se perdeu: a sessao fica guardada no perfil do navegador.",
              file=sys.stderr)
        print("  Confira sem gastar tentativa nenhuma com o comando 'sessao'.",
              file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
