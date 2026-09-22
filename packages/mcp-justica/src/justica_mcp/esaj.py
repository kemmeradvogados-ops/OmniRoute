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

import re
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

# O operador informou em 22 de setembro de 2026: na secao de andamentos e
# preciso clicar na palavra "mais". O identificador conhecido some depois de uma
# expansao e o historico continuava parando em cinco linhas, entao ele nao e o
# unico controle. A palavra e o que o operador ve; o identificador e o que a
# pagina declara. Tentar os dois, nesta ordem, cobre os dois mundos sem supor
# qual deles o portal usa em cada tela.
CANDIDATOS_EXPANDIR = (
    LINK_EXPANDIR_MOVIMENTACOES,
    'text="mais"',
    'text="Mais"',
)
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


DATA_BRASILEIRA = re.compile(r"^\s*\d{2}/\d{2}/\d{4}\s*$")


def _linhas_com_cara_de_movimentacao(elemento: Any) -> list[dict[str, str]]:
    """Le as linhas cuja PRIMEIRA celula e uma data no formato brasileiro.

    Reconhecer pelo formato do dado, e nao por identificador, e o que permite
    achar a tabela de movimentacoes do e-SAJ sem inventar seletor: ela nao tem
    identificador proprio, e o container que tem esta vazio ate alguem acionar
    "exibir mais". Uma data na primeira celula e evidencia; um seletor
    adivinhado nao e.
    """
    achadas: list[dict[str, str]] = []
    try:
        linhas = elemento.query_selector_all("tr")
    except Exception:
        return achadas
    for linha in linhas:
        try:
            celulas = linha.query_selector_all("td")
        except Exception:
            continue
        if len(celulas) < 2:
            continue
        data = " ".join((celulas[0].inner_text() or "").split())
        if not DATA_BRASILEIRA.match(data):
            continue
        descricao = " ".join((celulas[-1].inner_text() or "").split())
        if not descricao:
            continue
        achadas.append({"data": data, "descricao": descricao})
    return achadas


def extrair_movimentacoes_com_origem(pagina: Any) -> tuple[list[dict[str, str]], str]:
    """Devolve o MAIOR conjunto de linhas com data, e de onde ele veio.

    Pegar o primeiro conjunto que aparecesse era instavel, e a instabilidade
    apareceu em campo: a mesma consulta trouxe 50, depois 48, depois 5. O
    `div#containerMovimentacoes` guarda so as ultimas, e a lista completa nasce
    noutra tabela quando a pessoa expande. Parando no primeiro, o laco de
    expansao via o numero travado em cinco e concluia "parou de crescer" com
    quarenta e tantas linhas ja na tela.

    O maior conjunto e o historico: a pagina tem outras tabelas com data
    (peticoes, incidentes, audiencias) e todas sao pequenas. A origem continua
    sendo relatada, porque "o maior" e uma boa aposta e nao uma declaracao da
    pagina.
    """
    candidatos: list[tuple[list[dict[str, str]], str]] = []

    try:
        container = pagina.query_selector(CONTAINER_MOVIMENTACOES)
    except Exception:
        container = None
    if container is not None:
        do_container = _linhas_com_cara_de_movimentacao(container)
        if do_container:
            candidatos.append((do_container, "container"))

    try:
        tabelas = pagina.query_selector_all("table")
    except Exception:
        tabelas = []
    for tabela in tabelas:
        achadas = _linhas_com_cara_de_movimentacao(tabela)
        if achadas:
            candidatos.append((achadas, "varredura"))

    if not candidatos:
        return [], "nenhuma"
    # Empate fica com o container, que e o lugar declarado.
    candidatos.sort(key=lambda par: (len(par[0]), par[1] == "container"), reverse=True)
    return candidatos[0]


def extrair_movimentacoes(pagina: Any) -> list[dict[str, str]]:
    return extrair_movimentacoes_com_origem(pagina)[0]


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
    movimentacoes, origem = extrair_movimentacoes_com_origem(pagina)
    return {
        "principais": extrair_dados_principais(pagina),
        "partes": extrair_partes(pagina),
        "movimentacoes": movimentacoes,
        "movimentacoes_origem": origem,
        "movimentacoes_completas": lista_de_movimentacoes_esta_completa(pagina),
        "pasta_digital": link_da_pasta_digital(pagina),
        "totais": {
            "partes": len(extrair_partes(pagina)),
            "movimentacoes": len(movimentacoes),
        },
    }


# Teto do laco de expansao. Nao e desconfianca do portal: e a diferenca entre
# parar e ficar clicando para sempre se o botao nao sumir por algum motivo que
# nao previmos. Trinta cobre processo longo com folga.
MAXIMO_DE_EXPANSOES = 30


def expandir_movimentacoes_ate_o_fim(
    pagina: Any, guarda: Any, segundos: int, contar=None
) -> dict[str, Any]:
    """Aciona "exibir mais movimentacoes" ATE a opcao sumir.

    Uma expansao so trazia um pedaco: conferido em campo em 22 de setembro de
    2026, o processo tinha mais historico do que uma rodada revelava, e entregar
    o pedaco como se fosse o todo faria o advogado concluir que nao ha andamento
    anterior.

    Para por tres motivos, e os tres importam:

    - o botao sumiu, que e o fim normal;
    - o numero de linhas parou de crescer, o que significa que clicar de novo
      nao traz nada e so gasta tempo;
    - o teto foi atingido, que e a protecao contra um laco sem fim.
    """
    expansoes = 0
    antes_do_laco = contar(pagina) if contar else None
    while expansoes < MAXIMO_DE_EXPANSOES:
        if not expandir_movimentacoes(pagina, guarda, segundos):
            return {"expansoes": expansoes, "motivo": "botao sumiu"}
        expansoes += 1
        if contar is not None:
            # A pagina monta as linhas novas depois de a rede sossegar, entao
            # contar imediatamente via o numero antigo e o laco concluia "parou
            # de crescer" cedo demais. Em campo isso deixou o historico em cinco
            # linhas quando havia quase cinquenta.
            try:
                pagina.wait_for_timeout(1500)
            except Exception:
                pass
            agora = contar(pagina)
            if antes_do_laco is not None and agora <= antes_do_laco:
                # Uma rodada sem crescer pode ser lentidao. Duas seguidas e o
                # fim de verdade.
                try:
                    pagina.wait_for_timeout(2500)
                except Exception:
                    pass
                if contar(pagina) <= antes_do_laco:
                    return {"expansoes": expansoes, "motivo": "parou de crescer"}
            antes_do_laco = max(agora, contar(pagina))
    return {"expansoes": expansoes, "motivo": "teto de expansoes atingido"}


def expandir_movimentacoes(pagina: Any, guarda: Any, segundos: int) -> bool:
    """Aciona "exibir mais movimentacoes". Autorizado pelo operador em 22/09/2026.

    O historico verdadeiro do e-SAJ so existe depois deste clique: o container
    nomeado vem vazio e o portal so o preenche aqui. Sem isso a consulta entrega
    o que achar numa tabela anonima, e o advogado le como historico o que talvez
    nao seja.

    A autorizacao e nominal e efemera, do mesmo feitio da copia integral do
    eproc: vale para ESTE seletor, nesta tela, nesta execucao. Nao alarga nada,
    e em especial nao alcanca `#botaoConfirmarRebebimentoIntimacao`, que mora na
    mesma pagina e continua barrado pelo termo de risco, que e conferido antes
    de qualquer lista.

    Devolve True quando clicou.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import _assentar, elemento_visivel, permissao_efemera

    seletor = None
    botao = None
    for candidato in CANDIDATOS_EXPANDIR:
        botao = elemento_visivel(pagina, candidato)
        if botao is not None:
            seletor = candidato
            break
    if botao is None:
        return False
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao=f"exibir mais movimentacoes ({seletor}), autorizado pelo operador",
        conferido_em="execucao atual",
        seletores_clicaveis=(seletor,),
    ))
    guarda.pode_executar(Acao.CLICAR, seletor, url=pagina.url)
    botao.click()
    try:
        pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
    except Exception:
        pass
    _assentar(pagina, segundos)
    return True


def _pistas_do_visualizador(corpo: bytes, teto: int = 14) -> list[str]:
    """Enderecos e nomes de formulario achados numa pagina de passagem.

    O padrao mais util e o ultimo: QUALQUER endereco entre aspas. A primeira
    versao procurava `action`, `src`, `href` e `location`, e nao achou nada na
    pagina real do e-SAJ, porque ela usa `window.open`, que nao casa com nenhum
    deles. Procurar pela forma do endereco, e nao pelo nome do atributo que o
    carrega, cobre `window.open`, `document.location`, `top.location` e o que
    mais o portal inventar.

    So estrutura: endereco, nome de campo, nome de formulario. Nao devolve
    texto livre, porque o relato e colado em conversa e a promessa do projeto e
    que nenhum dado de processo apareca nele.
    """
    try:
        texto = corpo.decode("utf-8", errors="replace")
    except Exception:
        return []
    achados: list[str] = []
    padroes = (
        (r'action=["\']([^"\']+)', "action"),
        (r'name=["\']([^"\']+)', "campo"),
        (r'["\']((?:https?://|/)[^"\'\s]{1,200})["\']', "endereco"),
    )
    for padrao, rotulo in padroes:
        try:
            encontrados = re.findall(padrao, texto)
        except Exception:
            continue
        for achado in encontrados[:teto]:
            linha = f"{rotulo}: {achado[:130]}"
            if linha not in achados:
                achados.append(linha)
    return achados[:teto * 2]


def copiar_pasta_digital(pagina: Any, guarda: Any, destino: Any, chave: str,
                         segundos: int) -> dict[str, Any]:
    """Tenta copiar a integra pelo endereco da pasta digital.

    Diferenca importante em relacao ao eproc: aqui a integra TEM endereco
    proprio (`/cpopg/abrirPastaDigital.do?processo.codigo=...`), entao a copia
    nao precisa de clique. Buscar pelo endereco nao clica, nao navega e nao muda
    a pagina, que e o padrao deste projeto desde a Fase 2.

    A pasta digital e outra aplicacao do portal (`/pastadigital/`), e o que ela
    devolve nunca foi visto. Por isso este passo tem dois desfechos honestos:
    ou vem arquivo e ele e gravado, ou nao vem e o comando RELATA o que
    encontrou, para o download real ser escrito depois de conferido. Nao ha
    terceiro desfecho em que se finge que deu certo.
    """
    from pathlib import Path

    from .core.guarda_navegacao import Acao
    from .portal import permissao_de_origem

    endereco = link_da_pasta_digital(pagina)
    if not endereco:
        return {"situacao": "sem_link", "detalhe": "A pagina nao traz link de pasta digital."}

    absoluto = endereco if endereco.startswith("http") else (
        f"{pagina.url.split('/cpopg')[0]}{endereco}"
        if endereco.startswith("/") else endereco
    )

    guarda.permissoes.append(permissao_de_origem(
        pagina.url, "pasta digital, mesma origem do portal"
    ))
    decisao = guarda.avaliar(Acao.BAIXAR, absoluto, url=absoluto)
    if not decisao.permitido:
        return {"situacao": "barrado", "detalhe": decisao.motivo}

    try:
        resposta = pagina.context.request.get(absoluto, timeout=segundos * 1000)
    except Exception as exc:
        return {"situacao": "falhou", "detalhe": f"{type(exc).__name__}: {exc}"}

    try:
        tipo = (resposta.headers or {}).get("content-type", "")
        corpo = resposta.body()
    except Exception as exc:
        return {"situacao": "falhou", "detalhe": f"{type(exc).__name__}: {exc}"}

    if "pdf" not in tipo.lower():
        # Nao e arquivo: e a tela do visualizador. Conferido em campo em 22 de
        # setembro de 2026: `text/html`, 948 bytes. Esse tamanho nao comporta
        # uma tela de verdade, entao e pagina de passagem, que redireciona ou
        # monta o visualizador por script.
        #
        # O corpo e pequeno e NAO contem dado de processo: e andaime. Relatar
        # os enderecos que ele carrega e o que permite escrever o download real
        # sem adivinhar, e e a mesma disciplina do resto do projeto.
        return {
            "situacao": "nao_e_arquivo",
            "detalhe": f"content-type {tipo!r}, {len(corpo)} bytes. "
                       "Tela de passagem, nao o PDF.",
            "endereco": absoluto,
            "pistas": _pistas_do_visualizador(corpo),
        }

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"integra-{chave}.pdf"
    arquivo.write_bytes(corpo)
    return {"situacao": "gravada", "arquivo": str(arquivo), "bytes": len(corpo)}


# A pagina de passagem carrega o endereco real da pasta, com um `ticket` que so
# o portal emite, por sessao e por processo. Montar esse endereco e impossivel
# por definicao, e por isso ele e LIDO de onde o portal o pos.
CAMINHO_DA_PASTA = "/pastadigital/"


def endereco_real_da_pasta(corpo: bytes) -> Optional[str]:
    """Extrai, da pagina de passagem, o endereco que ela abriria.

    O operador perguntou em 22 de setembro de 2026 como resolver o endereco
    variar por processo. Nao se resolve construindo: ele traz um `ticket` de
    sessao que so o portal emite. Resolve-se LENDO, porque a pagina de passagem
    existe exatamente para carrega-lo.
    """
    for pista in _pistas_do_visualizador(corpo, teto=40):
        rotulo, _, valor = pista.partition(": ")
        if rotulo == "endereco" and CAMINHO_DA_PASTA in valor:
            return valor
    return None


def abrir_pasta_digital(pagina: Any, guarda: Any, segundos: int) -> list[Any]:
    """Abre a janela dos autos e devolve TODAS as abas que sobraram abertas.

    Conferido em campo em 22 de setembro de 2026: a aba que eu abro MORRE. O
    endereco da pasta digital devolve 954 bytes de `text/html`, que e pagina de
    passagem: ela abre outra janela e se encerra. Ler a aba que eu abri dava
    `TargetClosedError`, e o relato vinha vazio.

    Por isso o que interessa nao e a aba aberta aqui, e sim as que existirem
    depois. Sao coletadas por diferenca com as de antes, e as fechadas ficam de
    fora. Devolver lista, e nao uma aba, evita supor que ela abre exatamente
    uma.
    """
    from .core.guarda_navegacao import Acao
    from .portal import _assentar, permissao_de_origem

    endereco = link_da_pasta_digital(pagina)
    if not endereco:
        return []
    absoluto = endereco if endereco.startswith("http") else (
        f"{pagina.url.split('/cpopg')[0]}{endereco}"
        if endereco.startswith("/") else endereco
    )
    guarda.permissoes.append(permissao_de_origem(
        pagina.url, "janela dos autos, mesma origem do portal"
    ))
    guarda.avaliar(Acao.NAVEGAR, absoluto, url=absoluto).exigir()

    contexto = pagina.context
    try:
        antes = set(contexto.pages)
    except Exception:
        antes = {pagina}

    # Le a pagina de passagem e pega dela o endereco real, com o ticket. Abrir
    # a de passagem e torcer para o script rodar deixava a aba vazia: conferido
    # em campo, titulo vazio e zero elementos.
    destino = absoluto
    try:
        resposta = contexto.request.get(absoluto, timeout=segundos * 1000)
        # O endereco real aparece de dois jeitos, e o primeiro so foi percebido
        # em campo em 22 de setembro de 2026: a pagina de passagem REDIRECIONA,
        # e a requisicao segue o redirecionamento sozinha. O corpo que chega ja
        # e o do destino, e por isso procurar o endereco dentro dele nao achava
        # nada. Quem sabe onde parou e a RESPOSTA.
        achado = None
        try:
            parou_em = getattr(resposta, "url", "") or ""
            if CAMINHO_DA_PASTA in parou_em:
                achado = parou_em
        except Exception:
            pass
        if achado is None:
            achado = endereco_real_da_pasta(resposta.body())
        if achado:
            destino = achado if achado.startswith("http") else (
                f"{pagina.url.split('/cpopg')[0]}{achado}"
            )
            guarda.avaliar(Acao.NAVEGAR, destino, url=destino).exigir()
    except Exception:
        # Sem o endereco real, segue com o de passagem: e pior, mas nao e nada.
        pass

    aba = contexto.new_page()
    try:
        aba.goto(destino, timeout=segundos * 1000, wait_until="domcontentloaded")
    except Exception:
        # A propria navegacao pode morrer se a pagina se encerrar durante ela.
        pass
    # A janela filha nao nasce instantaneamente: sem esta pausa a coleta
    # acontece antes de ela existir e o relato volta vazio de novo.
    try:
        pagina.wait_for_timeout(3000)
    except Exception:
        pass

    novas: list[Any] = []
    try:
        for p in contexto.pages:
            if p in antes or p is pagina:
                continue
            try:
                if p.is_closed():
                    continue
            except Exception:
                continue
            novas.append(p)
    except Exception:
        return []

    for p in novas:
        try:
            _assentar(p, segundos)
        except Exception:
            continue
    return novas


# Sequencia descrita pelo operador em 22 de setembro de 2026, com as telas
# fotografadas: "Visualizar autos" abre a Pasta Digital; la se marca "Todas",
# clica em "Baixar PDF", escolhe "Arquivo unico" e confirma em "Continuar".
#
# Os alvos sao TEXTOS, e nao identificadores, porque foi o texto que o operador
# viu e informou. O mesmo caminho resolveu a palavra "Mais" nas movimentacoes,
# depois de o identificador conhecido falhar.
BOTAO_VISUALIZAR_AUTOS = "#linkPasta"

# Conferido em campo em 22 de setembro de 2026, no relato da propria Pasta
# Digital. Os botoes da barra inferior NAO tem texto: sao icones, e o relato os
# mostrou com `texto=''`. Por isso os seletores por texto nao achavam nada,
# embora o operador visse as palavras na tela: o que ele le e a legenda ao lado
# do icone, nao o conteudo do botao.
#
# Cada passo aceita varios candidatos, com o identificador primeiro. E o mesmo
# arranjo que resolveu a palavra "Mais": o declarado tem precedencia, e o texto
# fica como rede, para o caso de o portal mudar os identificadores.
MARCAR_TODAS = ("#selecionarButton", 'text="Todas"')
BAIXAR_PDF = ("#salvarButton", 'text="Baixar PDF"')
ARQUIVO_UNICO = ('text="Arquivo único"', 'text="Arquivo unico"')
CONFIRMAR_DOWNLOAD = ('text="Continuar"', "#btnContinuar")


def _primeiro_visivel(janela: Any, candidatos) -> Optional[tuple[Any, str]]:
    from .portal import elemento_visivel

    for candidato in candidatos:
        alvo = elemento_visivel(janela, candidato)
        if alvo is not None:
            return alvo, candidato
    return None


def _clicar_na_pasta(janela: Any, guarda: Any, candidatos, rotulo: str) -> bool:
    """Clica um alvo da Pasta Digital, sob autorizacao nominal.

    Cada alvo entra na lista de permissao por si, no momento de usa-lo. Uma
    permissao ampla para a janela inteira seria mais simples e e justamente o
    que nao se faz aqui: a lista estreita e o que impede um clique fora do
    previsto quando a tela mudar.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import permissao_efemera

    achado = _primeiro_visivel(janela, candidatos)
    if achado is None:
        print(f"    [PAROU] Nao encontrei {rotulo} na Pasta Digital.")
        print(f"            Tentados: {', '.join(candidatos)}")
        return False
    alvo, seletor = achado
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(janela.url).padrao_url,
        descricao=f"Pasta Digital: {rotulo}, autorizado pelo operador",
        conferido_em="execucao atual",
        seletores_clicaveis=(seletor,),
    ))
    guarda.pode_executar(Acao.CLICAR, seletor, url=janela.url)
    alvo.click()
    print(f"    {rotulo}: clicado.")
    return True


def copiar_autos_pelo_visualizador(
    pagina: Any, guarda: Any, destino: Any, chave: str, segundos: int
) -> dict[str, Any]:
    """Copia a integra pelo caminho que o operador descreveu e fotografou.

    Por que o clique, se este projeto prefere o endereco: a Pasta Digital SO
    nasce do clique. Conferido em campo por tres caminhos, todos falhos: buscar
    o endereco devolve pagina de passagem de menos de mil bytes; segui-la por
    requisicao nao redireciona; abrir essa pagina numa aba deixa a aba vazia. O
    endereco real traz um `ticket` que o portal monta no instante do clique.

    O clique aqui e aceitavel porque o alvo e conhecido, nominalmente
    autorizado, e a Pasta Digital nao contem o botao de ciencia, que mora na
    pagina do processo e continua barrado pelo termo de risco.
    """
    from pathlib import Path

    from .portal import _assentar, elemento_visivel

    botao = elemento_visivel(pagina, BOTAO_VISUALIZAR_AUTOS)
    if botao is None:
        return {"situacao": "sem_botao",
                "detalhe": f"Nao ha {BOTAO_VISUALIZAR_AUTOS} na pagina do processo."}

    from .core.guarda_navegacao import Acao, Permissao
    from .portal import permissao_efemera

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="Visualizar autos, autorizado pelo operador",
        conferido_em="execucao atual",
        seletores_clicaveis=(BOTAO_VISUALIZAR_AUTOS,),
    ))
    guarda.pode_executar(Acao.CLICAR, BOTAO_VISUALIZAR_AUTOS, url=pagina.url)

    print("    Visualizar autos: clicando e aguardando a janela...")
    try:
        with pagina.expect_popup(timeout=segundos * 1000) as info:
            botao.click()
        janela = info.value
    except Exception as exc:
        return {"situacao": "sem_janela",
                "detalhe": f"A janela nao apareceu: {type(exc).__name__}: {exc}"}

    try:
        janela.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
    except Exception:
        pass
    _assentar(janela, segundos)
    print(f"    Pasta Digital aberta: {janela.url[:90]}")

    passos = (
        (MARCAR_TODAS, "Todas"),
        (BAIXAR_PDF, "Baixar PDF"),
    )
    for seletor, rotulo in passos:
        if not _clicar_na_pasta(janela, guarda, seletor, rotulo):
            return {"situacao": "parou_no_passo", "passo": rotulo, "janela": janela}
        _assentar(janela, segundos)

    # "Arquivo unico" ja vem marcado na tela fotografada. Clicar assim mesmo e
    # barato e protege do caso de o portal mudar o padrao; nao achar nao e erro.
    _clicar_na_pasta(janela, guarda, ARQUIVO_UNICO, "Arquivo unico")

    achado = _primeiro_visivel(janela, CONFIRMAR_DOWNLOAD)
    if achado is None:
        return {"situacao": "parou_no_passo", "passo": "Continuar", "janela": janela}
    alvo, seletor = achado

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(janela.url).padrao_url,
        descricao="Pasta Digital: Continuar, autorizado pelo operador",
        conferido_em="execucao atual",
        seletores_clicaveis=(seletor,),
    ))
    guarda.pode_executar(Acao.CLICAR, seletor, url=janela.url)
    print("    Continuar: clicado, aguardando o arquivo...")
    try:
        with janela.expect_download(timeout=max(segundos, 120) * 1000) as baixa:
            alvo.click()
        baixado = baixa.value
    except Exception as exc:
        return {"situacao": "sem_arquivo",
                "detalhe": f"{type(exc).__name__}: {exc}", "janela": janela}

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    sugerido = baixado.suggested_filename or f"{chave}-integra.pdf"
    arquivo = destino / f"integra-{sugerido}"
    baixado.save_as(str(arquivo))
    return {"situacao": "gravada", "arquivo": str(arquivo), "janela": janela}
