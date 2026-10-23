"""O NAVEGADOR e a TELA: o que os cinco portais compartilham por baixo.

Saiu de `portal.py` em 22/10/2026, e a razao esta escrita num defeito concreto.

Em 15/10/2026 um commit meu trocou a area imposta da pagina por `no_viewport`,
para a gaveta do indice do Visualizador deixar de nascer em modo `over`. A
gaveta passou a aparecer e a CONSULTA quebrou: a 1280 de largura a busca
devolvia a tela do processo; a 1522 e depois a 1922 ela para na tela de
resultado. Uma linha de geometria, escrita pensando em UMA tela, atingiu os
cinco portais de uma vez, e custou quatro corridas do advogado para aparecer,
cada uma consumindo uma autenticacao.

O que esse episodio ensinou nao foi "tome cuidado": foi que a geometria estava
diluida em sete mil linhas junto de login, menu, busca e download, onde ninguem
a le inteira antes de mexer. Aqui ela cabe numa sentada, tem arquivo de teste
proprio (`tests/test_navegador.py`), e quem for alterar area de janela ve, na
linha de cima, o preco que a ultima alteracao teve.

Este modulo NAO IMPORTA NADA do pacote alem de `core.estado`, e e assim de
proposito: a dependencia corre num sentido so (`portal` -> `navegador`), entao
nada daqui pode voltar a se enroscar nas telas de um portal especifico. Ha um
teste que confere isso.

Uma advertencia para quem for escrever teste: `portal` reexporta estes nomes
por conveniencia, mas quem CHAMA um deles de dentro daqui enxerga o nome deste
modulo, nao o de `portal`. Trocar `portal.pasta_de_descargas` por um duble nao
muda o que `abrir_navegador` vai usar; troque `navegador.pasta_de_descargas`.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional


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


# A pasta de descargas CRESCE PARA SEMPRE, e isso e defeito desde o primeiro
# dia: nada nunca a limpou. Cada arquivo que o navegador escreve ali fica, e a
# corrida de 21/10/2026 passou por ela documentos de 24,7 MB, 11,5 MB duas
# vezes, 5,2 MB, 4,1 MB e dezenas de outros, alem de tudo o que os dias
# anteriores deixaram.
#
# Isto entrou na lista de suspeitos da queda do navegador junto com outra
# evidencia que eu vinha atribuindo ao Google Drive: as falhas de gravacao com
# `OSError`, que apareceram em quatro documentos. Disco cheio produz exatamente
# essas duas coisas. [Nao verificado] se foi essa a causa.
#
# Independente da causa da queda, pasta que cresce sem limite e defeito. Quem
# resgata um arquivo dali ja o copiou para o acervo: a copia do navegador e
# peso morto no instante seguinte.
def medida_das_descargas() -> tuple:
    """Quantos arquivos e quantos bytes a pasta de descargas guarda."""
    try:
        arquivos = [a for a in pasta_de_descargas().iterdir() if a.is_file()]
    except OSError:
        return (0, 0)
    total = 0
    for arquivo in arquivos:
        try:
            total += arquivo.stat().st_size
        except OSError:
            continue
    return (len(arquivos), total)


def limpar_descargas(antes_de: float) -> tuple:
    """Apaga da pasta de descargas o que e ANTERIOR a esta corrida.

    Devolve (quantos, bytes). Nunca levanta: pasta de cache nao pode derrubar
    um download.

    So o que e anterior, e isso nao e cautela de sobra: o resgate pela pasta do
    navegador compara contra uma lista tirada no instante do clique, entao
    arquivo mais novo que o inicio da corrida pode ser justamente o que a
    proxima redea vai procurar. Arquivo anterior, nao: ele ja foi resgatado ou
    ja se perdeu, e nos dois casos nao serve mais.
    """
    apagados = 0
    bytes_livres = 0
    try:
        arquivos = [a for a in pasta_de_descargas().iterdir() if a.is_file()]
    except OSError:
        return (0, 0)
    for arquivo in arquivos:
        try:
            dados = arquivo.stat()
            if dados.st_mtime >= antes_de:
                continue
            tamanho = dados.st_size
            arquivo.unlink()
        except OSError:
            continue
        apagados += 1
        bytes_livres += tamanho
    return (apagados, bytes_livres)


def nome_do_perfil() -> str:
    """Um perfil por NAVEGADOR, nunca um perfil para todos.

    O perfil guarda sessao e liberacao do desafio, e e escrito pelo navegador
    que o abriu. Abrir com o Microsoft Edge um perfil criado pelo Chromium do
    Playwright, ou o contrario, e pedir defeito silencioso: as duas coisas sao
    Chromium, mas nao sao a mesma compilacao.

    Trocar de navegador passa a significar sessao nova, e isso tem preco
    honesto: login de novo, e possivelmente o desafio de verificacao humana de
    novo. O que nao acontece e a sessao antiga ser corrompida pelo teste.
    """
    executavel = (os.environ.get("JUSTICA_CHROMIUM") or "").strip()
    if not executavel:
        return "navegador"
    # A barra e separada na mao, nos dois sentidos: o programa roda no Windows
    # e os testes rodam fora dele, e `Path` de uma plataforma nao reconhece o
    # separador da outra. Lido num teste que passou um caminho do Windows e
    # recebeu o caminho inteiro como nome de pasta.
    ultimo = executavel.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    marca = "".join(c for c in ultimo.rsplit(".", 1)[0].lower() if c.isalnum())
    return f"navegador-{marca or 'outro'}"


def pasta_do_navegador() -> "Path":
    """Perfil persistente do navegador, na pasta de estado.

    Guarda cookie de sessao do portal. Nao e pasta descartavel: quem apagar
    perde a liberacao do desafio e a sessao aberta, e volta a marcar a caixa.
    """
    from pathlib import Path as _P

    from .core.estado import diretorio_estado

    destino = _P(diretorio_estado()) / nome_do_perfil()
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _perfil_efemero() -> bool:
    return os.environ.get(VARIAVEL_PERFIL_EFEMERO, "").strip().lower() in ("1", "true", "sim")


def bandeiras_do_navegador() -> list[str]:
    """Bandeiras extras para o Chromium, vindas de `JUSTICA_NAVEGADOR_ARGS`.

    Saida de emergencia da mesma familia do `JUSTICA_CHROMIUM`, e existe pelo
    mesmo motivo: a maquina do operador as vezes precisa de um detalhe que o
    programa nao tem como adivinhar.

    O caso que a motivou, relatado em 06/10/2026: a janela abre e fica em
    branco, com a pagina carregada por tras. Em Windows isso costuma ser a
    composicao por placa de video, e a providencia conhecida e `--disable-gpu`.
    Ligar isso por conta propria seria piorar o desempenho de todo mundo por
    causa de uma maquina, entao fica na mao de quem precisa:

        JUSTICA_NAVEGADOR_ARGS=--disable-gpu

    Separadas por espaco. Vazio nao vira bandeira, para `ARGS=` nao mandar uma
    string vazia ao navegador.
    """
    bruto = (os.environ.get("JUSTICA_NAVEGADOR_ARGS") or "").strip()
    escolhidas = [pedaco for pedaco in bruto.split(" ") if pedaco]
    if not any(p.startswith("--window-size") for p in escolhidas):
        escolhidas.append(f"--window-size={JANELA_LARGA}")
    # A escala NAO entra sozinha. Ela foi acrescentada em 16/10/2026 para
    # encolher o desenho e fazer caber uma tela larga numa janela que a escala
    # do Windows tinha estreitado. Com area imposta esse problema nao existe
    # mais: a pagina mede o que o programa mandar, em qualquer maquina. Fica
    # como saida de emergencia, para quem precisar.
    escala = (os.environ.get("JUSTICA_ESCALA") or "").strip()
    if escala and not any(
            p.startswith("--force-device-scale-factor") for p in escolhidas):
        escolhidas.append(f"--force-device-scale-factor={escala_da_janela()}")
    return escolhidas


# Quanto a janela encolhe o desenho para caber mais tela dentro dela.
#
# `--window-size` fala em pixel de APARELHO; a pagina e desenhada em pixel de
# CSS, e a conta entre os dois e a escala do sistema. Em 16/10/2026, com
# `--window-size=1920,1080`, a janela mediu 1522x744: o Windows do advogado
# esta a 125%, entao 1920/1,25 da 1536, menos a barra de rolagem da 1522, e
# 1080/1,25 da 864, menos a moldura do navegador da 744. A conta fecha nos dois
# eixos, e nao sobra duvida sobre a causa.
#
# A consulta do Portal de Servicos do Tribunal de Justica do Rio de Janeiro
# desenha o formulario em mais de 2140 de largura: os campos ficam a esquerda e
# o botao `Pesquisar` em 1921, fora de uma janela de 1522. Aumentar
# `--window-size` nao resolve, porque a tela do operador acaba: janela nao
# cresce alem do monitor. O que resolve e encolher o desenho, que e o que esta
# escala faz. A 0,8 uma janela de 1920 de aparelho vira 2400 de CSS, e o
# formulario inteiro cabe.
#
# Fica ajustavel porque monitor e escala do sistema mudam de maquina para
# maquina: `JUSTICA_ESCALA=1` desliga o encolhimento, e valor menor cabe mais.
ESCALA_PADRAO = "0.8"


def escala_da_janela() -> str:
    """A escala pedida pelo operador, ou a padrao. Valor invalido nao passa."""
    bruto = (os.environ.get("JUSTICA_ESCALA") or "").strip()
    if not bruto:
        return ESCALA_PADRAO
    try:
        valor = float(bruto.replace(",", "."))
    except ValueError:
        print(f"JUSTICA_ESCALA={bruto!r} nao e um numero; usando "
              f"{ESCALA_PADRAO}.", file=sys.stderr)
        return ESCALA_PADRAO
    if not 0.3 <= valor <= 3:
        print(f"JUSTICA_ESCALA={bruto!r} esta fora de 0,3 a 3; usando "
              f"{ESCALA_PADRAO}.", file=sys.stderr)
        return ESCALA_PADRAO
    return f"{valor:g}"


# Tamanho da janela, e ele NAO e cosmetico.
#
# O Visualizador de Processos poe o indice de documentos numa gaveta do Angular
# Material. Em tela estreita a gaveta vira modo `over` e o conteudo dela nao e
# desenhado; em tela larga ela fica ao lado e o indice existe.
#
# Em 14/10/2026 o acompanhamento conduzido pelo advogado, na janela de verdade,
# mostrou `div#node-<n> x530` e 543 botoes. A corrida automatica, na mesma tela
# e no mesmo processo, mostrou 12 botoes e nenhum item, e o relato trazia
# `mat-drawer-backdrop`, que e a marca do modo `over`. Quatro tentativas de
# autenticacao foram gastas procurando isso em outro lugar.
JANELA_LARGA = "1920,1080"

# A AREA DA PAGINA, imposta pelo programa, e por que ela voltou a ser imposta.
#
# Ate 14/10/2026 o Playwright impunha 1280x720 e ninguem tinha reparado. Em
# 15/10, para o indice do Visualizador aparecer, troquei isso por `no_viewport`,
# que faz a pagina valer o tamanho real da janela. O indice e gaveta do Angular
# Material: em tela estreita ela vira modo `over` e o conteudo nao e desenhado.
#
# A troca consertou a gaveta e quebrou a consulta. Em 13/10, a 1280 de largura,
# a busca devolvia a tela do processo e a leitura saiu com 207 movimentacoes em
# 21 paginas. Em 16/10, a 1522 e depois a 1922, a mesma busca para na tela de
# resultado e o botao do Visualizador nunca aparece. [Inferencia] A correlacao
# e exata com a largura; nao tenho como provar daqui que o portal desenha outra
# tela a partir de certa largura, mas e a unica coisa que mudou entre as duas
# corridas, e mudou por minha mao.
#
# Entao a area volta a ser imposta, e por DUAS razoes alem dessa. Primeira: com
# area imposta a corrida nao depende mais do monitor do operador nem da escala
# do Windows, que foi o que fez 1920 virar 1522 e custou tres corridas.
# Segunda: area imposta se TROCA em tempo de execucao, e e isso que resolve o
# conflito de verdade. A consulta roda estreita, como no dia em que funcionou,
# e a janela do Visualizador e alargada no momento em que abre, que e a unica
# tela que precisa de largura.
AREA_DA_CONSULTA = {"width": 1280, "height": 720}
AREA_DO_VISUALIZADOR = {"width": 1920, "height": 1080}


def alargar_a_area(pagina: Any, area: Optional[dict] = None) -> bool:
    """Impoe outra area a esta pagina, e diz se conseguiu.

    So funciona com area imposta no lancamento; com `no_viewport` o Playwright
    recusa, e e por isso que o programa voltou a impor. Falhar aqui nao derruba
    nada: a tela so continua do tamanho em que estava, e quem chama relata.
    """
    alvo = dict(area or AREA_DO_VISUALIZADOR)
    try:
        pagina.set_viewport_size(alvo)
        return True
    except Exception:
        return False


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
    bandeiras = bandeiras_do_navegador()
    # Dito em voz alta: o operador precisa saber que nao esta no navegador
    # padrao, porque a sessao e outra e o comportamento pode ser outro.
    if executavel:
        from pathlib import Path as _P

        print(f"  Navegador: {_P(executavel).name} (JUSTICA_CHROMIUM), "
              f"perfil proprio '{nome_do_perfil()}'.")
    if _perfil_efemero():
        navegador = p.chromium.launch(
            headless=oculto, executable_path=executavel,
            downloads_path=descargas, args=bandeiras,
        )
        return navegador, navegador.new_page(viewport=dict(AREA_DA_CONSULTA))

    contexto = p.chromium.launch_persistent_context(
        str(pasta_do_navegador()),
        headless=oculto,
        executable_path=executavel,
        accept_downloads=True,
        downloads_path=descargas,
        args=bandeiras,
        # Area IMPOSTA, e a mesma em toda maquina. Quem precisa de largura e a
        # gaveta do indice do Visualizador, e ela e alargada quando a janela
        # dela abre, por `alargar_a_area`. Ver AREA_DA_CONSULTA.
        viewport=dict(AREA_DA_CONSULTA),
    )
    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    return contexto, pagina


def caixa_de(elemento: Any) -> Optional[dict]:
    """A caixa do elemento, ou None quando ele nao ocupa lugar nenhum."""
    try:
        return elemento.bounding_box()
    except Exception:
        return None


def caixa_na_tela(caixa: Optional[dict], largura: int, altura: int) -> bool:
    """Decide pela MEDIDA ja lida, sem tocar na pagina de novo."""
    if caixa is None:
        return False
    return not (
        caixa["x"] + caixa["width"] <= 0
        or caixa["y"] + caixa["height"] <= 0
        or caixa["x"] >= largura
        or caixa["y"] >= altura
    )


def descrever_caixa(caixa: Optional[dict]) -> str:
    """Onde o elemento esta, em palavras, para o relato dizer POR QUE recusou."""
    if caixa is None:
        return "sem caixa"
    return (f"x={caixa['x']:.0f} y={caixa['y']:.0f} "
            f"largura={caixa['width']:.0f} altura={caixa['height']:.0f}")


def _na_tela(elemento: Any, largura: int, altura: int) -> bool:
    """`is_visible` do Playwright aceita elemento jogado para fora da tela,
    porque so exige caixa nao vazia. Aqui a posicao importa: campo empurrado
    para `left:-9999px` e o padrao de campo espelho, e confundi-lo com o campo
    real faz o preenchimento falhar sem mensagem."""
    return caixa_na_tela(caixa_de(elemento), largura, altura)


# Quanto tempo esperar a pagina rolar ate o elemento, em milissegundos.
ROLAGEM_ATE_O_ELEMENTO = 2000


def _rolar_ate(elemento: Any) -> bool:
    """Pede a pagina para trazer o elemento, e diz se o pedido passou."""
    try:
        elemento.scroll_into_view_if_needed(timeout=ROLAGEM_ATE_O_ELEMENTO)
        return True
    except Exception:
        return False


def na_tela_ou_rolar(elemento: Any, largura: int, altura: int) -> bool:
    """Igual a `_na_tela`, mas ROLA antes de recusar por posicao.

    Abaixo da dobra nao e escondido. O botao `Pesquisar` da consulta do Portal
    de Servicos do Tribunal de Justica do Rio de Janeiro fica depois dos campos,
    e numa tela cujo conteudo mora em quadro embutido a caixa que o Playwright
    devolve e contada a partir da janela de fora: basta o quadro ser mais alto
    que a janela para o botao medir `y` maior que a altura. A recusa saia como
    "o botao nao esta na tela", que e verdade e nao e o problema: ele esta na
    pagina, a um rolar de distancia. Em 09/10/2026 isso parou a corrida com
    oito botoes `Pesquisar` presentes no quadro.

    A protecao contra campo espelho continua de pe, e e por isso que a medida e
    lida DE NOVO depois de rolar: pagina nao rola para coordenada negativa,
    entao o campo em `left:-9999px` volta da rolagem com a mesma caixa negativa
    e segue recusado. Ja o que estava so abaixo da dobra volta com caixa
    dentro da janela.
    """
    if caixa_na_tela(caixa_de(elemento), largura, altura):
        return True
    if not _rolar_ate(elemento):
        return False
    return caixa_na_tela(caixa_de(elemento), largura, altura)


def passou_da_borda(caixa: Optional[dict], largura: int, altura: int) -> bool:
    """Caixa inteira em coordenada POSITIVA, so que adiante da borda direita ou
    da de baixo.

    E a diferenca entre as duas coisas que a conferencia de posicao trata como
    uma so. Campo espelho e empurrado para coordenada NEGATIVA, tipicamente
    `left:-9999px`, e nenhuma rolagem o traz. Conteudo adiante da borda esta no
    lugar certo de um desenho mais largo que a janela: no Portal de Servicos do
    Tribunal de Justica do Rio de Janeiro, em 16/10/2026, o unico botao
    `Pesquisar` visivel media `x=1921` e o botao `Voltar` media `x=2062`, numa
    janela de 1522 de largura. Os campos do mesmo formulario, mais a esquerda,
    estavam dentro. O desenho da tela passa dos 2140, e a janela nao tem onde
    crescer: a tela do operador acaba antes.

    Coordenada negativa nunca passa por aqui. E isso que mantem de pe a
    protecao que a conferencia existe para dar.
    """
    if caixa is None:
        return False
    if caixa["x"] < 0 or caixa["y"] < 0:
        return False
    return caixa["x"] >= largura or caixa["y"] >= altura


def os_que_cabem_na_janela(candidatos: list, largura: int, altura: int) -> list:
    """Dos candidatos, os que estao na janela; so se NENHUM estiver, os que a
    rolagem traz.

    A ordem das duas passagens importa. Rolar e mexer na tela, e quando ja ha
    um alvo a vista nao ha o que ganhar mexendo: o eproc monta duas barras
    superiores com os MESMOS identificadores, e o criterio que separa a boa da
    inutil e justamente estar na janela. Se a rolagem entrasse na primeira
    passagem, a escolha passaria a depender da ordem do documento, que e a
    ordem errada. Assim, onde algo ja aparecia, nada muda; a rolagem so entra
    onde antes a resposta era "nao esta na tela".
    """
    dentro = [e for e in candidatos
              if caixa_na_tela(caixa_de(e), largura, altura)]
    if dentro:
        return dentro
    rolados = [e for e in candidatos if na_tela_ou_rolar(e, largura, altura)]
    if rolados:
        return rolados
    # Terceira passagem: nem dentro, nem alcancavel rolando, e ainda assim em
    # coordenada positiva. E tela desenhada mais larga do que a janela pode
    # ficar, e recusar aqui seria recusar conteudo legitimo por um motivo que
    # o operador nao tem como consertar. O clique do Playwright ainda confere
    # por conta propria se alcanca o alvo, e reclama alto quando nao alcanca:
    # errar para o lado de tentar devolve uma mensagem util; errar para o lado
    # de recusar devolve "nao esta na tela", que foi a frase que parou quatro
    # corridas.
    return [e for e in candidatos
            if passou_da_borda(caixa_de(e), largura, altura)]


JANELA_SUPOSTA = {"width": 1280, "height": 720}

# O que o desenho da tela ocupa, contra o que a janela mostra. Sem isso o
# relato diz que um elemento esta fora da janela e nao diz se ha para onde
# rolar, que e a pergunta seguinte e a que decide o conserto.
JS_DA_MEDIDA_DO_CONTEUDO = (
    "() => ({desenhoL: document.documentElement.scrollWidth,"
    " desenhoA: document.documentElement.scrollHeight,"
    " visivelL: document.documentElement.clientWidth,"
    " visivelA: document.documentElement.clientHeight,"
    " rolagemX: Math.round(window.scrollX),"
    " rolagemY: Math.round(window.scrollY)})")


def medida_do_conteudo(pagina: Any) -> Optional[dict]:
    try:
        lido = pagina.evaluate(JS_DA_MEDIDA_DO_CONTEUDO)
    except Exception:
        return None
    return lido if isinstance(lido, dict) else None


def relatar_a_medida_do_conteudo(pagina: Any) -> str:
    """Uma linha dizendo se o desenho cabe na janela e onde a rolagem esta."""
    medida = medida_do_conteudo(pagina)
    if not medida:
        return "DESENHO DA TELA: nao foi possivel medir"
    desenho = f"{int(medida.get('desenhoL') or 0)}x{int(medida.get('desenhoA') or 0)}"
    visivel = f"{int(medida.get('visivelL') or 0)}x{int(medida.get('visivelA') or 0)}"
    rolagem = (f"{int(medida.get('rolagemX') or 0)},"
               f"{int(medida.get('rolagemY') or 0)}")
    sobra_lado = int(medida.get("desenhoL") or 0) - int(medida.get("visivelL") or 0)
    veredicto = ("cabe na largura" if sobra_lado <= 0
                 else f"passa {sobra_lado} de largura")
    return (f"DESENHO DA TELA: {desenho}, visivel {visivel}, rolagem em "
            f"{rolagem} ({veredicto})")


def _pagina_dona(pagina: Any) -> Any:
    """A pagina de um quadro embutido, ou o proprio objeto quando ja e pagina."""
    return getattr(pagina, "page", None) or pagina


def _medida_perguntada(pagina: Any) -> Optional[dict]:
    """Pergunta o tamanho a PROPRIA pagina, que e quem sabe."""
    try:
        lido = _pagina_dona(pagina).evaluate(
            "() => ({width: window.innerWidth, height: window.innerHeight})")
    except Exception:
        return None
    try:
        largura, altura = int(lido["width"]), int(lido["height"])
    except (TypeError, KeyError, ValueError):
        return None
    if largura > 0 and altura > 0:
        return {"width": largura, "height": altura}
    return None


def janela_de(pagina: Any) -> dict:
    """Tamanho da janela, tolerando QUADRO EMBUTIDO e janela sem area imposta.

    Quadro embutido nao tem `viewport_size`: so a pagina tem. Ler a estrutura
    de dentro de um quadro quebrava com AttributeError, e o eproc do Rio abre a
    integra do processo justamente dentro de um quadro.

    E desde 14/10/2026 ha um segundo caso. Com `no_viewport`, que existe para a
    pagina valer o tamanho real da janela, o Playwright nao impoe area nenhuma
    e `viewport_size` devolve nada. O chute de 1280x720 passava a valer numa
    janela de 1920x1080, e TUDO que estivesse alem dessa dobra era lido como
    "fora da tela": o relato de 16/10/2026 mostrou "0 de 29" botoes, com a
    pagina inteira desenhada. Quem sabe o tamanho e a propria pagina, e agora
    ela e perguntada antes de qualquer chute.
    """
    try:
        medida = pagina.viewport_size
    except AttributeError:
        medida = None
    if medida:
        return medida
    dona = _pagina_dona(pagina)
    if dona is not pagina:
        try:
            medida = dona.viewport_size
        except AttributeError:
            medida = None
        if medida:
            return medida
    return _medida_perguntada(pagina) or dict(JANELA_SUPOSTA)


# --------------------------------------------------------------------------
# Faro de arquivos
#
# Por que isto existe. Em 23/10/2026 o pedido dos autos do PJe foi feito
# inteiro: o painel abriu, a faixa de identificadores entrou conferida e o
# botao DOWNLOAD foi clicado. Nenhum arquivo chegou pelo navegador, e a Area
# de Download, que e a tela propria do portal para isso, voltou sem conteudo
# depois de 45s de espera: um unico botao, nenhum campo, nenhuma tabela. O
# arquivo EXISTE, e de 507 folhas, e foi visto aberto no leitor de PDF do
# proprio navegador.
#
# O que falta, entao, nao e o arquivo: e o ENDERECO dele. Clicar no icone de
# baixar do leitor de PDF resolveria para quem esta na frente da tela, mas
# aquele leitor e um visualizador do navegador, com barra propria fora do
# documento, e nao uma pagina que se possa ler e clicar por seletor.
#
# O faro nao clica em nada e nao navega. Ele apenas ANOTA o que o navegador ja
# viu passar: toda resposta com cara de arquivo e toda aba que se abriu. Se o
# endereco passou, ele fica anotado, e ai o arquivo se pede de novo pela
# sessao, que e o caminho que o Portal de Servicos ja usa desde outubro.
# --------------------------------------------------------------------------

TIPOS_DE_ARQUIVO = (
    "application/pdf",
    "application/octet-stream",
    "application/zip",
    "application/x-zip",
)

FINAIS_DE_ARQUIVO = (".pdf", ".zip")


def parece_arquivo(url: str, cabecalhos: dict) -> bool:
    """A resposta tem cara de arquivo para guardar, e nao de pagina?

    Tres sinais, e qualquer um basta. O tipo declarado, que e o mais confiavel
    quando vem; a disposicao `attachment`, que e o portal dizendo "isto se
    baixa"; e a terminacao do caminho, que e o unico sinal quando o servidor
    nao declara tipo nenhum.
    """
    tipo = (cabecalhos.get("content-type") or "").split(";")[0].strip().lower()
    if tipo in TIPOS_DE_ARQUIVO:
        return True
    disposicao = (cabecalhos.get("content-disposition") or "").lower()
    if "attachment" in disposicao:
        return True
    caminho = (url or "").split("?")[0].split("#")[0].lower()
    return caminho.endswith(FINAIS_DE_ARQUIVO)


def resumo_do_endereco(url: str) -> str:
    """O endereco sem os numeros longos, para poder ser dito em voz alta.

    O numero do processo viaja no caminho e na busca de quase todo endereco de
    portal, e o relato desta casa vai parar em conversa. Entao o que se imprime
    e a FORMA do endereco, nao o endereco: o servidor, o caminho, e no lugar de
    cada corrida de sete ou mais digitos, reticencias. O endereco inteiro fica
    na memoria, que e onde ele serve.
    """
    import re as _re
    from urllib.parse import urlparse

    try:
        partes = urlparse(url or "")
    except Exception:
        return "(endereco ilegivel)"
    if not partes.netloc:
        return "(endereco sem servidor)"
    caminho = _re.sub(r"\d{7,}", "...", partes.path or "/")
    busca = " ?..." if partes.query else ""
    return f"{partes.scheme}://{partes.netloc}{caminho}{busca}"


class FarejadorDeArquivos:
    """Anota os enderecos de arquivo que o navegador viu passar.

    Nao clica, nao navega, nao le corpo de resposta. Ler o corpo aqui seria
    gastar a resposta que o navegador ainda vai usar; o que se anota e so o
    endereco, e o arquivo se pede de novo depois, pela sessao.
    """

    def __init__(self, contexto: Any) -> None:
        self.contexto = contexto
        self.achados: list[dict] = []
        self._vistos: set[str] = set()
        self._paginas: list[Any] = []
        self._ligado = False

    # ---- ligar e desligar -------------------------------------------------

    def ligar(self) -> bool:
        if self._ligado or self.contexto is None:
            return self._ligado
        try:
            self.contexto.on("response", self._anotar_resposta)
            self.contexto.on("page", self._anotar_pagina)
        except Exception:
            return False
        for pagina in self._abertas():
            self._paginas.append(pagina)
        self._ligado = True
        return True

    def desligar(self) -> None:
        if not self._ligado:
            return
        for evento, tratador in (("response", self._anotar_resposta),
                                 ("page", self._anotar_pagina)):
            try:
                self.contexto.remove_listener(evento, tratador)
            except Exception:
                pass
        self._ligado = False

    def _abertas(self) -> list:
        try:
            return list(self.contexto.pages)
        except Exception:
            return []

    # ---- o que se anota ---------------------------------------------------

    def _guardar(self, url: str, origem: str, tipo: str = "") -> None:
        if not url or url in self._vistos:
            return
        if url.lower().startswith(("about:", "chrome:", "data:")):
            return
        self._vistos.add(url)
        self.achados.append({"url": url, "origem": origem, "tipo": tipo})

    def _anotar_resposta(self, resposta: Any) -> None:
        try:
            url = resposta.url
            cabecalhos = resposta.headers or {}
        except Exception:
            return
        try:
            if not parece_arquivo(url, cabecalhos):
                return
        except Exception:
            return
        tipo = (cabecalhos.get("content-type") or "").split(";")[0].strip()
        self._guardar(url, "resposta", tipo)

    def _anotar_pagina(self, pagina: Any) -> None:
        self._paginas.append(pagina)

    def _colher_das_abas(self) -> None:
        """Uma aba parada num PDF tem o endereco dele na barra.

        Quando o navegador abre o arquivo no leitor embutido em vez de baixar,
        nao ha evento de download nenhum, mas a aba fica com o endereco do
        arquivo. E so perguntar a ela, e por isso isto e perguntado tarde: no
        instante em que a aba nasce o endereco dela ainda e `about:blank`.
        """
        for pagina in list(self._paginas) + self._abertas():
            try:
                url = pagina.url
            except Exception:
                continue
            caminho = (url or "").split("?")[0].lower()
            if caminho.endswith(FINAIS_DE_ARQUIVO):
                self._guardar(url, "aba aberta")

    # ---- o que se colhe ---------------------------------------------------

    def enderecos(self) -> list[str]:
        self._colher_das_abas()
        return [achado["url"] for achado in self.achados]

    def relatar(self, recuo: str = "    ") -> None:
        self._colher_das_abas()
        achados = self.achados
        if not achados:
            print(f"{recuo}O navegador nao viu endereco de arquivo nenhum "
                  "passar.")
            return
        print(f"{recuo}Enderecos de arquivo que o navegador viu passar "
              f"({len(achados)}):")
        for achado in achados:
            tipo = f" [{achado['tipo']}]" if achado.get("tipo") else ""
            print(f"{recuo}  ({achado['origem']}){tipo} "
                  f"{resumo_do_endereco(achado['url'])}")
