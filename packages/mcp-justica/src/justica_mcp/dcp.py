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

# Quanto esperar pelo ARQUIVO, que e coisa diferente de esperar por tela.
#
# O portal nao tem o PDF pronto: ele o GERA quando se pede, e um lote de 300
# paginas leva o tempo que leva. Em 08/10/2026 os quatro lotes foram marcados
# certos, 45 de 45, 32 de 32, 53 de 53 e 34 de 34, e os quatro morreram em 45
# segundos de espera. O numero 45 vem de `--segundos`, que e prazo de tela, e
# estava passando por cima deste teto, que existe exatamente para isto.
TETO_DO_DOWNLOAD = 300

# De quanto em quanto tempo a espera pelo arquivo fala, e de quanto em quanto
# tempo ela confere se a janela continua aberta.
#
# Em 09/10/2026 o lote 1 foi marcado certo, 45 de 45, a espera de 300s comecou
# e o terminal ficou mudo. No fim a janela nao estava mais aberta, e nao ha
# como saber se foi o operador que a fechou achando que tinha travado ou se ela
# morreu sozinha. Espera muda de cinco minutos e um convite para fechar a
# janela, e e isso que estes dois numeros desfazem.
INTERVALO_DO_AVISO = 20
PASSO_DA_ESPERA = 500


def espera_do_arquivo(segundos: Any) -> int:
    """O prazo do DOWNLOAD, que nunca e menor que o teto proprio dele.

    Prazo de tela e prazo de arquivo sao grandezas diferentes: a tela que nao
    monta em 45s esta quebrada; o PDF de 300 paginas que nao chega em 45s
    esta so sendo gerado.
    """
    try:
        pedido = int(segundos)
    except (TypeError, ValueError):
        pedido = 0
    return max(pedido, TETO_DO_DOWNLOAD)


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


# A caixa de selecao, e o indice de documentos atras dela.
#
# O advogado explicou em 06/10/2026: "o exibir caixa de selecao lhe permite
# selecionar um documento especifico para download", e em 08/10/2026, depois
# de a integra nao baixar: "nessas situacoes colocar duas opcoes, baixar
# alguma peca especifica ou baixar de 300 em 300 paginas".
#
# As duas precisam marcar itens do indice, e o indice NUNCA foi lido com a
# caixa de selecao aberta. O que se sabe dele veio do acompanhamento de
# 06/10/2026: e feito de botoes cujo rotulo acessivel comeca por "Alternar ",
# seguido do numero do documento e do proprio andamento. O numero e sequencia;
# o resto e conteudo do processo e nao sai em relato nenhum.
BOTAO_CAIXA_DE_SELECAO = "Exibir caixa de seleção"
# O MESMO botao, depois que a caixa abre. Ele troca de rotulo, e foi assim que
# a corrida de 08/10/2026 desistiu de uma coisa que ja estava pronta: o
# reconhecimento do indice, que roda quando a integra falha, ABRIU a caixa; o
# download em lotes, logo depois, procurou "Exibir" e nao achou.
BOTAO_OCULTAR_SELECAO = "Ocultar caixa de seleção"
MARCA_DO_ITEM_DO_INDICE = "alternar "
# Onde a marca de selecao costuma morar, do mais especifico ao mais frouxo.
LUGARES_DE_MARCA = (
    "input[type=checkbox]",
    "[role=checkbox]",
    "mat-checkbox",
    "mat-pseudo-checkbox",
)


def pagina_inicial_do_item(rotulo: str) -> Optional[int]:
    """A PAGINA em que o documento comeca, lida do rotulo do item do indice.

    Correcao de 08/10/2026, do proprio advogado: "ao lado do nome do documento
    vem o numero da pagina que inicia o documento". Eu vinha lendo aquele
    numero como SEQUENCIA do documento, e nao e.

    A tela que ele mandou confirma, porque os numeros saltam:

        3 - Peticao Inicial
       12 - CPF
       13 - CPF
       ...
       92 - Extrato da GRERJ
       93 - Juntada - Certidao

    Sequencia nao salta de 16 para 23; pagina inicial, sim. A diferenca decide
    tudo o que vem depois: com ela, "de 300 em 300 paginas" e conta exata, e
    nao chute por quantidade de documentos.

    O resto do rotulo nao e aproveitado em lugar nenhum: e o proprio andamento
    do processo, e foi o que vazou para uma conversa em 06/10/2026.
    """
    from .portal import sem_acento

    limpo = sem_acento(rotulo or "").strip()
    if not limpo.startswith(MARCA_DO_ITEM_DO_INDICE):
        return None
    resto = limpo[len(MARCA_DO_ITEM_DO_INDICE):].strip()
    numero = resto.split(" ")[0].split("-")[0].strip()
    return int(numero) if numero.isdigit() else None


# De quantas em quantas paginas baixar, quando a integra nao vem de uma vez.
# Numero dado pelo advogado em 08/10/2026: "baixar de 300 em 300 paginas".
PAGINAS_POR_LOTE = 300


def lotes_por_pagina(inicios: Any, tamanho: int = PAGINAS_POR_LOTE) -> list:
    """Agrupa documentos em lotes de ate `tamanho` paginas.

    Recebe as paginas iniciais, na ordem do indice, e devolve listas de
    POSICOES. Um documento entra no lote enquanto a distancia entre a pagina
    em que ele comeca e a do primeiro do lote for MENOR que o tamanho.

    Um documento sozinho que ja passe do tamanho vai num lote so dele, em vez
    de ser deixado de fora: documento que nao cabe em lote nenhum nunca seria
    baixado, e um acervo com buraco silencioso e pior que um download que
    falha na cara do operador.

    O ULTIMO lote nao tem como ser medido: a pagina final do processo nao
    aparece no indice, so a inicial de cada documento. Quem chama trata esse
    lote como os outros e confere o arquivo que chegar.
    """
    posicoes = [(i, p) for i, p in enumerate(inicios or [])
                if isinstance(p, int)]
    if not posicoes:
        return []
    teto = max(1, int(tamanho))
    lotes, atual, base = [], [], None
    for posicao, pagina in posicoes:
        if base is None:
            base, atual = pagina, [posicao]
            continue
        if pagina - base < teto:
            atual.append(posicao)
            continue
        lotes.append(atual)
        base, atual = pagina, [posicao]
    if atual:
        lotes.append(atual)
    return lotes


def itens_do_indice(pagina: Any) -> list:
    """Os botoes do indice de documentos, na ordem da tela."""
    saida = []
    try:
        candidatos = pagina.query_selector_all("[aria-label]") or []
    except Exception:
        return saida
    for elemento in candidatos:
        try:
            rotulo = elemento.get_attribute("aria-label") or ""
        except Exception:
            continue
        if pagina_inicial_do_item(rotulo) is not None:
            saida.append(elemento)
    return saida


def caixa_de_selecao_aberta(pagina: Any) -> bool:
    """Se as marcas de selecao ja estao ligadas.

    Pelo rotulo do botao, que e o que o portal troca: com a caixa aberta ele
    passa a ser "Ocultar caixa de selecao". Perguntar isso antes de clicar e o
    que impede o programa de FECHAR a caixa achando que a estava abrindo.
    """
    from .portal import elemento_por_rotulo

    return elemento_por_rotulo(pagina, BOTAO_OCULTAR_SELECAO) is not None


# A TELA DO VISUALIZADOR SE MONTA DEPOIS DE ABRIR, e esta e a oitava vez que
# esta mesma classe de defeito aparece neste portal. Em 16/10/2026 a janela do
# Visualizador abriu, foi lida no mesmo instante e o relato saiu com
# "CAMPOS NA TELA (0 de 0)" e "BOTOES NA TELA (0 de 0)": nao e tela sem botao,
# e tela que ainda nao existe. A recusa dizia que o botao da caixa de selecao
# nao estava na barra, o que era verdade e nao era o problema.
#
# Entao a janela e ESPERADA ate parar de crescer, e so entao lida. Mesma regra
# do indice, em `esperar_o_indice`, pelo mesmo motivo.
JS_DO_VISUALIZADOR_MONTADO = r"""() => {
  const controles = document.querySelectorAll(
    'button, a, [role=button], [aria-label], input, mat-checkbox');
  return {
    controles: controles.length,
    nos: document.querySelectorAll('*').length,
    comRotulo: document.querySelectorAll('[aria-label]').length,
  };
}"""

# Quanto esperar a janela do Visualizador se montar.
ESPERA_DO_VISUALIZADOR = 30


def medida_do_visualizador(pagina: Any) -> dict:
    """Quantos controles e quantos nos a tela tem AGORA."""
    try:
        lido = pagina.evaluate(JS_DO_VISUALIZADOR_MONTADO)
    except Exception:
        return {"controles": 0, "nos": 0, "comRotulo": 0}
    if not isinstance(lido, dict):
        return {"controles": 0, "nos": 0, "comRotulo": 0}
    # NORMALIZADA, sempre com as tres chaves. Quem le a medida le por chave, e
    # uma tela que devolva outra coisa nao pode derrubar a espera com KeyError:
    # a espera existe justamente para telas que ainda nao sao o que deveriam.
    return {chave: int(lido.get(chave) or 0)
            for chave in ("controles", "nos", "comRotulo")}


def esperar_o_visualizador_montar(pagina: Any,
                                  segundos: int = ESPERA_DO_VISUALIZADOR) -> dict:
    """Espera a tela do Visualizador PARAR de crescer, e devolve a medida.

    Parar de crescer, e nao so comecar: a barra de ferramentas aparece antes
    do indice, e desistir no primeiro controle visto leva a procurar botao
    numa barra pela metade.
    """
    import time as _tempo

    limite = _tempo.monotonic() + max(1, segundos)
    anterior, estaveis = -1, 0
    medida = medida_do_visualizador(pagina)
    while True:
        medida = medida_do_visualizador(pagina)
        if medida["controles"] > 0 and medida["controles"] == anterior:
            estaveis += 1
            if estaveis >= LEITURAS_ESTAVEIS:
                return medida
        else:
            estaveis = 0
        anterior = medida["controles"]
        if _tempo.monotonic() >= limite:
            return medida
        try:
            pagina.wait_for_timeout(500)
        except Exception:
            _tempo.sleep(0.5)


def abrir_caixa_de_selecao(pagina: Any, guarda: Any) -> bool:
    """Liga as marcas de selecao do indice, se ja nao estiverem ligadas.

    Chamar isto duas vezes nao pode desfazer o que a primeira fez, e e
    exatamente o que acontecia ate 08/10/2026: o reconhecimento do indice
    abria a caixa, e o download em lotes, logo depois, procurava o botao de
    ABRIR, que ja tinha virado o de fechar.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import elemento_por_rotulo, permissao_efemera

    if caixa_de_selecao_aberta(pagina):
        return True

    # Procura PRIMEIRO, espera depois. A barra pode ainda nao existir, e por
    # isso a espera esta aqui tambem, e nao so no assentamento da janela: esta
    # funcao e chamada de quatro lugares e nem todos passam por la. Mas quem ja
    # tem a barra pronta nao paga espera nenhuma.
    botao = elemento_por_rotulo(pagina, BOTAO_CAIXA_DE_SELECAO)
    medida = {"controles": 0, "comRotulo": 0}
    if botao is None:
        medida = esperar_o_visualizador_montar(pagina)
        botao = elemento_por_rotulo(pagina, BOTAO_CAIXA_DE_SELECAO)
    if botao is None:
        print(f"      A tela do Visualizador tem {medida['controles']} "
              f"controle(s) e {medida['comRotulo']} com rotulo acessivel, e "
              f"nenhum deles e {BOTAO_CAIXA_DE_SELECAO!r}.")
        return False
    alvo = f'[aria-label="{BOTAO_CAIXA_DE_SELECAO}"]'
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="abrir a caixa de selecao do indice de documentos",
        conferido_em="execucao atual",
        seletores_clicaveis=(alvo,),
    ))
    guarda.pode_executar(Acao.CLICAR, alvo, url=pagina.url)
    clicar_com_jeito(botao)
    try:
        pagina.wait_for_timeout(1200)
    except Exception:
        pass
    # Prova positiva, como em todo clique deste programa: o botao tem de ter
    # virado o de fechar. Sem isso, "abri a caixa" e so uma suposicao sobre o
    # que o clique fez, e marcar documento numa caixa fechada nao marca nada.
    return caixa_de_selecao_aberta(pagina)


def relatar_o_indice(pagina: Any, teto: int = 8) -> list[str]:
    """A FORMA do indice de documentos, sem o conteudo dele.

    Sai: quantos itens ha, o numero de cada um dos primeiros, e onde esta a
    marca de selecao de cada um, com a etiqueta e o identificador.
    NAO sai: o rotulo dos itens. Ele e o proprio andamento do processo, e foi
    o que vazou para uma conversa em 06/10/2026.
    """
    itens = itens_do_indice(pagina)
    if not itens:
        return ["o indice nao tem item nenhum com rotulo 'Alternar <numero>'"]

    paginas = []
    for elemento in itens:
        try:
            paginas.append(pagina_inicial_do_item(
                elemento.get_attribute("aria-label") or ""))
        except Exception:
            paginas.append(None)

    mostradas = [str(p) if p is not None else "?" for p in paginas[:teto]]
    linhas = [f"{len(itens)} item(ns) no indice; os {len(mostradas)} primeiros "
              "comecam nas paginas: " + ", ".join(mostradas)]

    # Os lotes que sairiam deste indice, ja calculados. E o que o advogado
    # pediu em 08/10/2026, e agora e conta exata: a pagina inicial de cada
    # documento esta no proprio rotulo.
    lotes = lotes_por_pagina([p for p in paginas if p is not None])
    if lotes:
        resumo = []
        for lote in lotes[:6]:
            primeira = [p for p in paginas if p is not None][lote[0]]
            ultima = [p for p in paginas if p is not None][lote[-1]]
            resumo.append(f"paginas {primeira} a {ultima} ({len(lote)} doc.)")
        linhas.append(
            f"em lotes de {PAGINAS_POR_LOTE} paginas dariam {len(lotes)} "
            "download(s): " + "; ".join(resumo)
            + ("; ..." if len(lotes) > 6 else ""))

    # Onde esta a marca de selecao de cada item, que e o que falta saber para
    # marcar um documento especifico.
    for elemento in itens[:3]:
        numero = None
        try:
            numero = pagina_inicial_do_item(elemento.get_attribute("aria-label") or "")
        except Exception:
            pass
        achou = []
        for lugar in LUGARES_DE_MARCA:
            for onde, alvo in (("dentro", elemento),
                               ("no pai", _pai_de(elemento)),
                               ("no avo", _pai_de(_pai_de(elemento)))):
                if alvo is None:
                    continue
                try:
                    marcas = alvo.query_selector_all(lugar) or []
                except Exception:
                    continue
                if marcas:
                    achou.append(f"{lugar} x{len(marcas)} {onde}")
                    break
            if achou:
                break
        linhas.append(
            f"documento da pagina {numero if numero is not None else '?'}: "
            + ("; ".join(achou) if achou
               else "nenhuma marca de selecao perto dele, "
                    f"nos lugares {', '.join(LUGARES_DE_MARCA)}"))
    return linhas


def _pai_de(elemento: Any) -> Optional[Any]:
    """O elemento acima deste, ou None."""
    if elemento is None:
        return None
    try:
        return elemento.evaluate_handle("e => e.parentElement").as_element()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Baixar em PARTES, quando a integra nao vem de uma vez
#
# Conferido em campo em 08/10/2026, com o Visualizador aberto no processo do
# advogado: 164 documentos, ultima pagina 1541, e a marca de selecao de cada
# item e um `input[type=checkbox]` que fica no elemento PAI dele. Em lotes de
# 300 paginas o processo dava 4 downloads.
#
# As duas formas que ele pediu nascem do mesmo mecanismo: marcar itens e usar
# "Salvar Documentos Selecionados". A diferenca e so quais itens se marca.
# ---------------------------------------------------------------------------


def marca_do_item(elemento: Any) -> Optional[Any]:
    """A caixa de marcacao do item, que fica no PAI dele, nao dentro.

    Conferido em 08/10/2026: `input[type=checkbox] x1 no pai` para os tres
    itens examinados. Procura tambem dentro e no avo, porque um item pode ser
    montado com um nivel a mais sem que isso mude o que ele e.
    """
    for alvo in (_pai_de(elemento), elemento, _pai_de(_pai_de(elemento))):
        if alvo is None:
            continue
        for lugar in LUGARES_DE_MARCA:
            try:
                achados = alvo.query_selector_all(lugar) or []
            except Exception:
                continue
            if achados:
                return achados[0]
    return None


def esta_marcado(marca: Any) -> Optional[bool]:
    """Se a caixa esta marcada agora, ou None quando nao da para saber."""
    for codigo in ("e => e.checked",
                   "e => e.getAttribute('aria-checked') === 'true'"):
        try:
            return bool(marca.evaluate(codigo))
        except Exception:
            continue
    return None


def marcar_item(marca: Any, pagina: Any) -> bool:
    """Marca a caixa e CONFERE que ela ficou marcada.

    A caixa do Angular Material e um `input` escondido atras de um desenho, e
    o clique de mouse nela costuma falhar por nao ter area visivel. O clique
    do documento resolve, e a conferencia depois e o que impede o programa de
    seguir achando que marcou quando nao marcou: um lote com documento de
    menos vira um PDF incompleto que ninguem volta a conferir.
    """
    if esta_marcado(marca) is True:
        return True
    for tentativa in (lambda: clicar_com_jeito(marca),
                      lambda: clicar_pelo_documento(_pai_de(marca))):
        try:
            tentativa()
        except Exception:
            continue
        try:
            pagina.wait_for_timeout(120)
        except Exception:
            pass
        if esta_marcado(marca) is not False:
            return esta_marcado(marca) is True
    return False


def desmarcar_tudo(marcas: Any, pagina: Any) -> int:
    """Desfaz a selecao do lote anterior. Devolve quantas ficaram desmarcadas.

    Entre um lote e outro isto nao e opcional: marca que sobra do lote
    anterior entra no PDF seguinte, e dois arquivos com o mesmo documento
    dentro nao se denunciam sozinhos.
    """
    desfeitas = 0
    for marca in marcas or []:
        if esta_marcado(marca) is not True:
            desfeitas += 1
            continue
        try:
            clicar_com_jeito(marca)
            pagina.wait_for_timeout(80)
        except Exception:
            pass
        if esta_marcado(marca) is not True:
            desfeitas += 1
    return desfeitas


def indice_com_paginas(pagina: Any) -> list:
    """Cada item do indice com a pagina em que ele comeca e a marca dele.

    Devolve uma lista de (pagina_inicial, elemento, marca), na ordem da tela.
    Item sem pagina legivel ou sem marca fica de fora da conta, e quem chama
    diz quantos ficaram: documento que some em silencio e o defeito que esta
    funcao existe para nao ter.
    """
    saida = []
    for elemento in itens_do_indice(pagina):
        try:
            inicio = pagina_inicial_do_item(
                elemento.get_attribute("aria-label") or "")
        except Exception:
            inicio = None
        if inicio is None:
            continue
        saida.append((inicio, elemento, marca_do_item(elemento)))
    return saida


# A FORMA do Visualizador, para quando o indice nao aparece.
#
# Em 13/10/2026 o indice nao chegou em 45s e o relato da tela mostrou 12
# botoes, contra os 543 das corridas em que ele existia. Isso ja nao parece
# demora: parece arvore que nao esta no documento. Descobrir onde ela esta
# custava outra tentativa de autenticacao, entao a propria falha passa a
# trazer o reconhecimento.
#
# Sai so ESTRUTURA: marcador e classe por nivel, contagem de elementos com
# rotulo acessivel, e a PRIMEIRA PALAVRA de cada rotulo, que e verbo de tela
# ("Alternar", "Baixar", "Ocultar") e nao conteudo do processo.
JS_DA_FORMA_DO_VISUALIZADOR = r"""
() => {
  const corta = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const assinatura = (e) => {
    const classe = (typeof e.className === 'string' ? e.className : '');
    const partes = corta(classe, 60).split(' ').filter(Boolean).slice(0, 2);
    return e.tagName.toLowerCase() + (partes.length ? '.' + partes.join('.') : '');
  };

  const niveis = [];
  let nivel = [document.body];
  for (let d = 0; d < 6 && nivel.length; d++) {
    const grupos = {};
    const proximo = [];
    for (const no of nivel) {
      for (const filho of Array.from(no.children)) {
        const a = assinatura(filho);
        grupos[a] = (grupos[a] || 0) + 1;
        proximo.push(filho);
      }
    }
    if (Object.keys(grupos).length === 0) break;
    niveis.push(grupos);
    nivel = proximo.slice(0, 400);
  }

  const verbos = {};
  let comRotulo = 0;
  for (const e of document.querySelectorAll('[aria-label]')) {
    const rotulo = corta(e.getAttribute('aria-label'), 60);
    if (!rotulo) continue;
    comRotulo += 1;
    const verbo = rotulo.split(' ')[0];
    verbos[verbo] = (verbos[verbo] || 0) + 1;
  }

  return {
    niveis: niveis,
    com_rotulo_acessivel: comRotulo,
    primeira_palavra_do_rotulo: verbos,
    elementos: document.querySelectorAll('*').length,
    caixas_de_marcacao: document.querySelectorAll(
      'input[type=checkbox], mat-checkbox, [role=checkbox]').length,
  };
}
"""


def forma_do_visualizador(pagina: Any) -> dict:
    """A estrutura do Visualizador, sem nenhum texto dele."""
    try:
        bruto = pagina.evaluate(JS_DA_FORMA_DO_VISUALIZADOR)
    except Exception as exc:
        return {"falha": f"{type(exc).__name__}: {exc}"}
    return bruto if isinstance(bruto, dict) else {"falha": "leitura invalida"}


def relatar_a_forma_do_visualizador(pagina: Any, teto: int = 10) -> list:
    """A forma em linhas, para entrar numa recusa sem despejar conteudo."""
    forma = forma_do_visualizador(pagina)
    if forma.get("falha"):
        return [f"a forma da tela nao pode ser lida: {forma['falha']}"]

    linhas = [
        f"{forma.get('elementos', 0)} elemento(s) na tela, "
        f"{forma.get('com_rotulo_acessivel', 0)} com rotulo acessivel, "
        f"{forma.get('caixas_de_marcacao', 0)} caixa(s) de marcacao",
    ]
    verbos = forma.get("primeira_palavra_do_rotulo") or {}
    if verbos:
        maiores = sorted(verbos.items(), key=lambda par: -par[1])[:teto]
        linhas.append("primeira palavra dos rotulos: " + ", ".join(
            f"{_sem_dado(palavra)} x{quantas}" for palavra, quantas in maiores))
    for profundidade, grupos in enumerate(forma.get("niveis") or []):
        maiores = sorted((grupos or {}).items(), key=lambda par: -par[1])[:teto]
        linhas.append(f"nivel {profundidade}: " + ", ".join(
            f"{_sem_dado(nome)} x{quantas}" for nome, quantas in maiores))
    return linhas


# Quanto esperar o INDICE montar. Prazo de tela, nao de arquivo.
SEGUNDOS_DO_INDICE = 45


def esperar_o_indice(pagina: Any, segundos: int = SEGUNDOS_DO_INDICE) -> list:
    """Espera o indice de documentos montar, e para quando ele para de crescer.

    Em 13/10/2026 a leitura do indice rodou com o Visualizador recem-aberto e
    devolveu lista vazia: o relato da tela mostrou 12 botoes, contra os 543 das
    corridas em que o indice existia. O comando parou dizendo "o indice nao foi
    lido", que e verdade e nao ajuda, porque o indice ia aparecer um segundo
    depois.

    E o mesmo defeito que ja apareceu na tela de login, na de selecao de
    sistemas, no menu, no botao de enviar o perfil e na tela do processo: ler a
    tela antes de ela terminar de montar. Aqui ele custou uma tentativa de
    autenticacao inteira.
    """
    import time as _tempo

    limite = _tempo.monotonic() + max(1, segundos)
    quantos = 0
    estaveis = 0
    while _tempo.monotonic() < limite:
        agora = len(indice_com_paginas(pagina))
        if agora > quantos:
            quantos = agora
            estaveis = 0
        elif quantos:
            estaveis += 1
            if estaveis >= LEITURAS_ESTAVEIS:
                break
        try:
            pagina.wait_for_timeout(1000)
        except Exception:
            _tempo.sleep(1)
    # Relido agora: os elementos guardados nas voltas anteriores podem ter sido
    # trocados pela propria montagem da tela.
    return indice_com_paginas(pagina)


def _gravar(baixado: Any, destino: Any, nome: str) -> str:
    from pathlib import Path

    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    sugerido = baixado.suggested_filename or "processo.pdf"
    arquivo = pasta / f"{nome}-{sugerido}"
    baixado.save_as(str(arquivo))
    return str(arquivo)


# Uma so ida ao navegador por volta de aviso. O relato completo da tela faz
# uma chamada por atributo de cada elemento, e nesta tela sao 543 botoes: ficar
# repetindo isso durante a espera custaria mais tempo do que a propria espera.
JS_DOS_CONTROLES = """
() => {
  const vis = (e) => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const saida = [];
  const alvos = document.querySelectorAll(
    'button, a[role=button], input[type=submit], input[type=button], ' +
    '[role=dialog], [role=alertdialog], mat-dialog-container');
  for (const e of alvos) {
    if (!vis(e)) continue;
    saida.push([
      (e.innerText || e.value || '').trim().slice(0, 60),
      (e.getAttribute('aria-label') || e.getAttribute('title') || '').trim().slice(0, 60)
    ]);
    if (saida.length >= 400) break;
  }
  return saida;
}
"""

# Quantas novidades cabem num aviso. O que interessa e o controle que APARECEU,
# e se aparecerem dezenas de uma vez isso ja e a resposta.
TETO_DE_NOVIDADES = 8


def controles_da_tela(pagina: Any) -> list:
    """Texto visivel e rotulo de cada controle visivel, como pares."""
    try:
        bruto = pagina.evaluate(JS_DOS_CONTROLES)
    except Exception:
        # Tela navegando, fechada, ou sem o metodo (falso de teste antigo).
        return []
    pares = []
    for item in bruto or []:
        try:
            pares.append((str(item[0] or ""), str(item[1] or "")))
        except Exception:
            continue
    return pares


def novidades_na_tela(antes: list, agora: list) -> list[str]:
    """O que apareceu na tela depois do clique, SEM o conteudo do processo.

    A mesma regra do relato de tela: controle que se repete aos montes e item
    de lista, e o rotulo dele e o andamento do processo. Vira contagem, sem
    rotulo nenhum. O que sobra ainda passa por `sem_dado_de_processo`.
    """
    from collections import Counter, OrderedDict

    from .portal import TETO_DE_BOTOES_IGUAIS, sem_dado_de_processo

    sobra = Counter(agora) - Counter(antes)
    grupos: "OrderedDict[str, list]" = OrderedDict()
    for (visivel, rotulo), quantas in sobra.items():
        grupos.setdefault(visivel, []).extend([rotulo] * quantas)

    linhas = []
    for visivel, rotulos in grupos.items():
        if len(rotulos) > TETO_DE_BOTOES_IGUAIS:
            linhas.append(f"{sem_dado_de_processo(visivel)!r} x{len(rotulos)} "
                          "(itens de lista: rotulos omitidos, sao conteudo do "
                          "processo)")
            continue
        for rotulo in rotulos:
            marca = (f" rotulo={sem_dado_de_processo(rotulo)!r}" if rotulo else "")
            linhas.append(f"{sem_dado_de_processo(visivel)!r}{marca}")
    return linhas


def janela_fechada(pagina: Any) -> bool:
    """A janela ainda esta aberta? Erro ao perguntar ja e resposta: nao."""
    try:
        return bool(pagina.is_closed())
    except Exception:
        return True


def escutar_descargas(pagina: Any, capturados: list, gravar: Any) -> Any:
    """Ouve os downloads da janela e das abas que ela abrir, e GRAVA na hora.

    O ouvinte entra ANTES do clique, e grava dentro do proprio aviso, por duas
    razoes que ja custaram copia em campo. A primeira e do e-SAJ, em
    22/09/2026: a janela se fechou entre o aviso de download e a gravacao, e
    meio segundo de atraso levou o arquivo junto. A segunda e deste portal, em
    09/10/2026: com `expect_download` o arquivo so e gravado depois que a
    espera termina, entao janela que morre no meio da geracao do PDF nao deixa
    nada no disco, nem quando o portal ja tinha entregue.
    """

    def guardar(baixado: Any) -> None:
        registro: dict[str, Any] = {"baixado": baixado, "arquivo": None,
                                    "erro": None, "sugerido": None}
        capturados.append(registro)
        # O nome ANTES de gravar: se a janela morrer no meio da gravacao, o
        # resgate pela pasta do navegador ainda precisa saber como chamar o
        # arquivo, e ali os nomes sao sequencias sem significado.
        try:
            registro["sugerido"] = baixado.suggested_filename
        except Exception:
            pass
        try:
            registro["arquivo"] = gravar(baixado)
        except Exception as exc:
            registro["erro"] = f"{type(exc).__name__}: {exc}"

    def ouvir_a_aba_nova(outra: Any) -> None:
        outra.on("download", guardar)

    pagina.on("download", guardar)
    ouvindo_o_contexto = False
    try:
        pagina.context.on("page", ouvir_a_aba_nova)
        ouvindo_o_contexto = True
    except Exception:
        # Sem acesso ao contexto, a janela principal continua sendo ouvida: e
        # menos cobertura, nao um erro que justifique nao esperar o arquivo.
        pass

    def parar_de_ouvir() -> None:
        """Tira o ouvinte da janela quando a espera acaba.

        Sem isto, o lote 2 e ouvido tambem pelo ouvinte que o lote 1 deixou
        para tras, e cada arquivo seguinte e gravado uma vez a mais do que o
        anterior, por cima do caminho do lote errado.
        """
        try:
            pagina.remove_listener("download", guardar)
        except Exception:
            pass
        if ouvindo_o_contexto:
            try:
                pagina.context.remove_listener("page", ouvir_a_aba_nova)
            except Exception:
                pass

    return parar_de_ouvir


def gravacao_terminou(capturados: list) -> bool:
    """Todo aviso recebido ja terminou de gravar, com arquivo ou com erro.

    ANUNCIAR NAO E TER GRAVADO, e confundir os dois custou a corrida de
    19/10/2026, a primeira em que o portal chegou a entregar o arquivo.

    O que acontece por baixo: o ouvinte do download grava DENTRO do proprio
    aviso, e `save_as` e uma chamada que bloqueia. O Playwright sincrono roda
    sobre greenlets, entao uma chamada que bloqueia dentro de um ouvinte
    devolve o controle para o laco principal enquanto a gravacao ainda esta em
    curso. O laco via a lista de avisos cheia, dava a espera por encerrada,
    nao achava arquivo nenhum porque a gravacao nao tinha terminado, e
    derrubava a corrida inteira levando junto a gravacao em andamento.

    O relato disso foi "o navegador anunciou o download e nada ficou no
    disco", sem erro de gravacao nenhum, que e precisamente a assinatura de
    uma gravacao interrompida no meio.
    """
    if not capturados:
        return False
    return all(r.get("arquivo") or r.get("erro") for r in capturados)


def esperar_a_descarga(pagina: Any, capturados: list, espera: int,
                       recuo: str = "      ") -> Optional[str]:
    """Acompanha a geracao do PDF. None quando o arquivo chegou.

    Devolve, quando nao chegou, a frase que diz o que aconteceu: o portal
    demorou mais que o prazo, ou a janela se fechou no meio. Sao coisas
    diferentes e o operador precisa saber qual das duas foi.

    A espera tambem OLHA a tela. Em 09/10/2026 o clique saiu, a janela ficou
    viva os 300s inteiros e nenhum arquivo foi anunciado; o relato de depois
    mostrou a tela do Visualizador normal, e nada do que aconteceu no meio.
    No e-SAJ, a licao de 22/09/2026 foi justamente esta: o portal NAO entrega
    no primeiro botao, ele monta o arquivo e so entao mostra o segundo. So da
    para saber se e esse o caso aqui olhando enquanto espera.
    """
    import time

    antes = controles_da_tela(pagina)
    comeco = time.time()
    limite = comeco + espera
    proximo_aviso = comeco + INTERVALO_DO_AVISO
    # Duas redeas, nao uma. O relogio e quem manda no navegador de verdade; a
    # conta de voltas existe porque cada volta dorme `PASSO_DA_ESPERA`, entao
    # passar desse numero significa que a espera nao esta dormindo coisa
    # nenhuma, e ficar rodando a vazio por cinco minutos nao ajuda ninguem.
    voltas = 0
    voltas_maximas = int(espera * 1000 / PASSO_DA_ESPERA) + 2
    while time.time() < limite and voltas < voltas_maximas:
        voltas += 1
        # Primeiro o arquivo. Depois, a gravacao que terminou em erro. Nunca
        # o simples aviso: ver `gravacao_terminou`.
        if arquivo_capturado(capturados):
            return None
        if gravacao_terminou(capturados):
            return "O navegador anunciou o download e a gravacao falhou."
        # A janela fechada so encerra a espera se NAO houver gravacao em
        # curso: o aviso ja chegou, o arquivo pode estar a caminho do disco, e
        # desistir aqui joga fora justamente o que se esperou cinco minutos.
        if not capturados and janela_fechada(pagina):
            return (f"A janela se fechou {int(time.time() - comeco)}s depois do "
                    f"pedido, antes de o arquivo chegar. O prazo era de {espera}s.")
        agora = time.time()
        if agora >= proximo_aviso:
            proximo_aviso = agora + INTERVALO_DO_AVISO
            print(f"{recuo}... {int(agora - comeco)}s de {espera}s. O portal ainda "
                  "esta gerando o PDF. Nao feche a janela.")
            novas = novidades_na_tela(antes, controles_da_tela(pagina))
            for linha in novas[:TETO_DE_NOVIDADES]:
                print(f"{recuo}    [APARECEU NA TELA] {linha}")
            if len(novas) > TETO_DE_NOVIDADES:
                print(f"{recuo}    [APARECEU NA TELA] e mais "
                      f"{len(novas) - TETO_DE_NOVIDADES} controle(s).")
        try:
            pagina.wait_for_timeout(PASSO_DA_ESPERA)
        except Exception:
            if arquivo_capturado(capturados):
                return None
            if capturados:
                return ("A janela parou de responder com a gravacao em curso, "
                        f"{int(time.time() - comeco)}s depois do pedido.")
            return (f"A janela parou de responder {int(time.time() - comeco)}s "
                    "depois do pedido, antes de o arquivo chegar.")
    if arquivo_capturado(capturados):
        return None
    if capturados:
        return (f"O navegador anunciou o download, e a gravacao nao terminou "
                f"em {espera}s.")
    return f"Nenhum arquivo chegou em {espera}s depois do pedido."


def arquivo_capturado(capturados: list) -> Optional[str]:
    """O caminho do primeiro arquivo que chegou ao disco, se chegou."""
    for registro in capturados:
        if registro.get("arquivo"):
            return registro["arquivo"]
    return None


def recado_de_gravacao(capturados: list) -> str:
    """O que deu errado ao gravar, quando o aviso veio e o arquivo nao ficou."""
    erros = [r["erro"] for r in capturados if r.get("erro")]
    if not erros:
        return ""
    return (" O navegador anunciou o download e a gravacao falhou: "
            + "; ".join(erros) + ".")


# O RESGATE PELA PASTA DO NAVEGADOR.
#
# 19/10/2026, com a espera ja consertada para nao abandonar a gravacao:
#
#   A janela parou de responder com a gravacao em curso, 4s depois do pedido.
#   TargetClosedError: Download.save_as: Target page, context ou browser has
#   been closed.
#
# A janela do Visualizador se FECHA sozinha quatro segundos depois do pedido. E
# comportamento do proprio Chromium: janela aberta por `window.open` que navega
# para um endereco que vira download fica sem conteudo, e o navegador a fecha.
# Com ela vai embora o canal pelo qual `save_as` grava, e o arquivo que o portal
# ja estava entregando se perde.
#
# O conserto nao e manter a janela viva, porque quem a fecha nao e este
# programa. E parar de depender dela. `pasta_de_descargas` existe desde o comeco
# exatamente para isto, e a propria explicacao dela ja dizia: "o arquivo
# continua no disco e pode ser copiado por caminho de sistema de arquivos, sem
# depender de janela viva". Faltava alguem copiar.
#
# Entao, quando a gravacao pelo canal falha, o arquivo e procurado na pasta onde
# o navegador escreve, por diferenca com o que havia la antes do pedido.

# Sufixos que o navegador usa enquanto ainda esta escrevendo. Copiar um desses
# traz PDF cortado, e PDF cortado guardado como peca e pior que peca nenhuma.
SUFIXOS_INCOMPLETOS = (".crdownload", ".part", ".tmp", ".partial")


def instantaneo_da_pasta(pasta: Any) -> dict:
    """Nome e tamanho do que ja esta na pasta. Chave para achar o que e novo."""
    from pathlib import Path

    try:
        return {p.name: p.stat().st_size for p in Path(pasta).iterdir()
                if p.is_file()}
    except Exception:
        return {}


def _completo(caminho: Any) -> bool:
    return not str(caminho).lower().endswith(SUFIXOS_INCOMPLETOS)


def arquivos_novos(pasta: Any, antes: dict) -> list:
    """Os arquivos COMPLETOS que apareceram depois do instantaneo."""
    from pathlib import Path

    try:
        atuais = [p for p in Path(pasta).iterdir() if p.is_file()]
    except Exception:
        return []
    novos = []
    for p in atuais:
        if not _completo(p):
            continue
        if p.name in antes and p.stat().st_size == antes[p.name]:
            continue
        novos.append(p)
    return sorted(novos, key=lambda p: p.stat().st_mtime, reverse=True)


def resgatar_descarga(pasta: Any, antes: dict, destino: Any, nome: str,
                      sugerido: Optional[str] = None,
                      espera: int = 20, recuo: str = "      ") -> Optional[str]:
    """Procura na pasta do navegador o arquivo novo e o copia para o destino.

    Espera o tamanho PARAR de crescer antes de copiar: o navegador escreve aos
    poucos, e copiar no meio traz PDF cortado.
    """
    import shutil
    import time as _tempo
    from pathlib import Path

    limite = _tempo.monotonic() + max(1, espera)
    anterior, estaveis, escolhido = -1, 0, None
    while _tempo.monotonic() < limite:
        novos = arquivos_novos(pasta, antes)
        if novos:
            escolhido = novos[0]
            tamanho = escolhido.stat().st_size
            if tamanho > 0 and tamanho == anterior:
                estaveis += 1
                if estaveis >= LEITURAS_ESTAVEIS:
                    break
            else:
                estaveis = 0
            anterior = tamanho
        _tempo.sleep(0.5)
    if escolhido is None or not escolhido.exists():
        return None
    if escolhido.stat().st_size <= 0:
        return None

    pasta_destino = Path(destino)
    pasta_destino.mkdir(parents=True, exist_ok=True)
    final = pasta_destino / f"{nome}-{sugerido or escolhido.name}"
    try:
        shutil.copy2(str(escolhido), str(final))
    except Exception as erro:
        print(f"{recuo}[ATENCAO] O arquivo foi achado na pasta do navegador e "
              f"a copia falhou: {type(erro).__name__}.")
        return None
    print(f"{recuo}Arquivo resgatado da pasta do navegador "
          f"({escolhido.stat().st_size} byte(s)).")
    return str(final)


def nome_sugerido(capturados: list) -> Optional[str]:
    """O nome que o portal deu ao arquivo, quando o aviso chegou a traze-lo."""
    for registro in capturados:
        if registro.get("sugerido"):
            return registro["sugerido"]
    return None


def baixar_marcados(pagina: Any, guarda: Any, destino: Any, nome: str,
                    segundos: int = TETO_DO_DOWNLOAD) -> str:
    """Abre a caixa de download e salva SO o que esta marcado."""
    from .core.guarda_navegacao import Acao

    botao = achar_botao_de_download(pagina)
    if botao is None:
        raise DownloadIndisponivel(
            f"O botao {BOTAO_DE_DOWNLOAD!r} sumiu da barra. Nada foi baixado.")
    alvo_do_botao = f'[aria-label="{BOTAO_DE_DOWNLOAD}"]'
    guarda.pode_executar(Acao.CLICAR, alvo_do_botao, url=pagina.url)
    clicar_com_jeito(botao)
    try:
        pagina.wait_for_timeout(1500)
    except Exception:
        pass

    escolha = achar_escolha(pagina, ESCOLHA_MARCADOS)
    if escolha is None:
        raise DownloadIndisponivel(
            f"A caixa de download nao mostrou {ESCOLHA_MARCADOS!r}. "
            "Nada foi baixado.")
    alvo_da_escolha = f"texto={ESCOLHA_MARCADOS}"
    guarda.pode_executar(Acao.CLICAR, alvo_da_escolha, url=pagina.url)
    espera = espera_do_arquivo(segundos)
    print(f"      Esperando ate {espera}s pelo arquivo. O portal gera o PDF "
          "agora, e isso demora. Nao feche a janela.")
    from .portal import pasta_de_descargas

    pasta_do_navegador = pasta_de_descargas()
    antes_do_pedido = instantaneo_da_pasta(pasta_do_navegador)
    capturados: list = []
    parar_de_ouvir = escutar_descargas(
        pagina, capturados, lambda baixado: _gravar(baixado, destino, nome))
    try:
        clicar_com_jeito(escolha)
        parada = esperar_a_descarga(pagina, capturados, espera)
    finally:
        parar_de_ouvir()
    arquivo = arquivo_capturado(capturados)
    if arquivo:
        return arquivo

    # A janela pode ter fechado com a gravacao em curso. O arquivo pode estar
    # na pasta do navegador assim mesmo. Ver o bloco em `resgatar_descarga`.
    resgatado = resgatar_descarga(
        pasta_do_navegador, antes_do_pedido, destino, nome,
        nome_sugerido(capturados))
    if resgatado:
        return resgatado

    if parada is None:
        parada = "O navegador anunciou o download e nada ficou no disco."
    raise DownloadIndisponivel(
        f"{ESCOLHA_MARCADOS!r} foi clicado e nenhum arquivo foi gravado. "
        + parada + recado_de_gravacao(capturados))


def permitir_o_download_marcado(pagina: Any, guarda: Any) -> None:
    """Autoriza, de uma vez, os cliques do caminho da selecao."""
    from .core.guarda_navegacao import Permissao
    from .portal import permissao_efemera

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="download por selecao no Visualizador de Processos",
        conferido_em="execucao atual",
        seletores_clicaveis=(
            f'[aria-label="{BOTAO_DE_DOWNLOAD}"]',
            f'[aria-label="{BOTAO_CAIXA_DE_SELECAO}"]',
            f"texto={ESCOLHA_MARCADOS}",
            "input[type=checkbox]",
        ),
    ))


def baixar_uma_peca(pagina: Any, guarda: Any, destino: Any, chave: str,
                    pagina_inicial: int,
                    segundos: int = TETO_DO_DOWNLOAD,
                    segundos_do_indice: int = SEGUNDOS_DO_INDICE) -> str:
    """Baixa UM documento, o que comeca na pagina indicada pelo operador.

    A pagina e a que aparece ao lado do nome no indice, como o advogado
    explicou em 08/10/2026. E ela que identifica o documento para quem olha a
    tela, entao e por ela que ele se pede.
    """
    permitir_o_download_marcado(pagina, guarda)
    if not abrir_caixa_de_selecao(pagina, guarda):
        raise DownloadIndisponivel(
            f"O botao {BOTAO_CAIXA_DE_SELECAO!r} nao esta na barra. "
            "Sem a caixa de selecao nao da para escolher um documento.")

    indice = esperar_o_indice(pagina, segundos_do_indice)
    if not indice:
        raise DownloadIndisponivel(
            f"O indice de documentos nao apareceu em {segundos_do_indice}s. "
            "Nada foi baixado."
            + "\n    A FORMA DA TELA, para achar onde o indice esta:\n    "
            + "\n    ".join(relatar_a_forma_do_visualizador(pagina)))

    escolhidos = [t for t in indice if t[0] == pagina_inicial]
    if not escolhidos:
        disponiveis = sorted({t[0] for t in indice})[:20]
        raise DownloadIndisponivel(
            f"Nenhum documento comeca na pagina {pagina_inicial}. "
            f"O indice tem {len(indice)} documento(s); os primeiros comecam "
            "nas paginas: " + ", ".join(str(p) for p in disponiveis) + ".")
    if len(escolhidos) > 1:
        raise DownloadIndisponivel(
            f"{len(escolhidos)} documentos comecam na pagina {pagina_inicial}. "
            "Baixar o errado seria pior que nao baixar. Nada foi marcado.")

    inicio, _elemento, marca = escolhidos[0]
    if marca is None:
        raise DownloadIndisponivel(
            f"O documento da pagina {inicio} nao tem caixa de marcacao. "
            "Nada foi baixado.")
    desmarcar_tudo([t[2] for t in indice if t[2] is not None], pagina)
    if not marcar_item(marca, pagina):
        raise DownloadIndisponivel(
            f"A caixa do documento da pagina {inicio} nao ficou marcada. "
            "Baixar agora traria o processo errado. Nada foi baixado.")
    print(f"    Marcado 1 documento, o que comeca na pagina {inicio}.")
    return baixar_marcados(pagina, guarda, destino,
                           f"{chave}-pagina{inicio}", segundos)


def baixar_em_lotes(pagina: Any, guarda: Any, destino: Any, chave: str,
                    tamanho: int = PAGINAS_POR_LOTE,
                    segundos: int = TETO_DO_DOWNLOAD,
                    apenas: Optional[int] = None,
                    segundos_do_indice: int = SEGUNDOS_DO_INDICE) -> list:
    """Baixa o processo, de `tamanho` em `tamanho` paginas.

    Com `apenas`, baixa SO aquele lote, contado a partir de 1. A divisao nao
    muda: o lote 2 de quatro continua sendo o mesmo lote 2, com as mesmas
    paginas, baixado sozinho ou no meio dos outros. Sem isso, "repita o
    comando para os que faltam", que a propria recusa diz, nao tinha como ser
    obedecido, e conferir o caminho custava o processo inteiro.

    Devolve a lista de arquivos gravados, na ordem. Um lote que falha NAO
    derruba os anteriores: eles ja estao em disco e valem. O que falhou e
    dito, com a faixa de paginas, para que possa ser repetido sozinho.
    """
    permitir_o_download_marcado(pagina, guarda)
    if not abrir_caixa_de_selecao(pagina, guarda):
        raise DownloadIndisponivel(
            f"O botao {BOTAO_CAIXA_DE_SELECAO!r} nao esta na barra. "
            "Sem a caixa de selecao nao da para baixar em partes.")

    indice = esperar_o_indice(pagina, segundos_do_indice)
    if not indice:
        raise DownloadIndisponivel(
            f"O indice de documentos nao apareceu em {segundos_do_indice}s. "
            "Nada foi baixado."
            + "\n    A FORMA DA TELA, para achar onde o indice esta:\n    "
            + "\n    ".join(relatar_a_forma_do_visualizador(pagina)))

    sem_marca = [t[0] for t in indice if t[2] is None]
    if sem_marca:
        print(f"    [ATENCAO] {len(sem_marca)} documento(s) do indice nao tem "
              "caixa de marcacao e NAO entrarao em lote nenhum.")
        print("    Paginas iniciais: "
              + ", ".join(str(p) for p in sem_marca[:20])
              + ("; ..." if len(sem_marca) > 20 else ""))

    uteis = [t for t in indice if t[2] is not None]
    lotes = lotes_por_pagina([t[0] for t in uteis], tamanho)
    todas = [t[2] for t in uteis]
    print(f"    {len(uteis)} documento(s) em {len(lotes)} lote(s) de ate "
          f"{tamanho} paginas.")

    numerados = list(enumerate(lotes, 1))
    if apenas is not None:
        if not 1 <= apenas <= len(lotes):
            raise DownloadIndisponivel(
                f"Este processo tem {len(lotes)} lote(s) de {tamanho} paginas, "
                f"e foi pedido o lote {apenas}. Nada foi baixado.")
        numerados = [numerados[apenas - 1]]
        primeira, ultima = uteis[lotes[apenas - 1][0]][0], \
            uteis[lotes[apenas - 1][-1]][0]
        print(f"    Baixando APENAS o lote {apenas} de {len(lotes)}: paginas "
              f"{primeira} a {ultima}.")

    arquivos, falhas = [], []
    for numero, lote in numerados:
        primeira, ultima = uteis[lote[0]][0], uteis[lote[-1]][0]
        desmarcar_tudo(todas, pagina)
        marcados = 0
        for posicao in lote:
            if marcar_item(uteis[posicao][2], pagina):
                marcados += 1
        print(f"    Lote {numero}/{len(lotes)}: paginas {primeira} a {ultima}, "
              f"{marcados} de {len(lote)} documento(s) marcado(s).")
        if marcados != len(lote):
            falhas.append(
                f"lote {numero} (paginas {primeira} a {ultima}): so "
                f"{marcados} de {len(lote)} documentos foram marcados")
            continue
        try:
            arquivo = baixar_marcados(
                pagina, guarda, destino,
                f"{chave}-lote{numero}-paginas{primeira}a{ultima}", segundos)
        except DownloadIndisponivel as exc:
            falhas.append(f"lote {numero} (paginas {primeira} a {ultima}): {exc}")
            # Com a janela fechada nao ha o que tentar: marcar e clicar numa
            # tela que nao existe mais so troca o recado certo, "a janela se
            # fechou", por uma fila de erros de leitura que escondem a causa.
            if janela_fechada(pagina):
                falhas.append("a janela se fechou, e os lotes seguintes nem "
                              "chegaram a ser tentados")
                break
            continue
        arquivos.append(arquivo)
        print(f"    Lote {numero} gravado em {arquivo}")

    if falhas:
        print(f"    [INCOMPLETO] {len(falhas)} lote(s) nao foram gravados:")
        for falha in falhas:
            print(f"      {falha}")
        print("    Os lotes que deram certo estao em disco e valem. Repita o "
              "comando para os que faltam.")
    if not arquivos:
        raise DownloadIndisponivel(
            "Nenhum lote foi gravado. " + "; ".join(falhas[:3]))
    return arquivos


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
    from .portal import endereco_sem_dado, permissao_efemera

    botao = achar_botao_de_download(pagina)
    if botao is None:
        raise DownloadIndisponivel(
            f"O botao {BOTAO_DE_DOWNLOAD!r} nao esta na barra desta tela "
            f"({endereco_sem_dado(pagina.url, 80)}). Nada foi clicado.")

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
    espera = espera_do_arquivo(segundos)
    print(f"    Esperando ate {espera}s pelo arquivo da integra. O portal gera "
          "o PDF agora, e processo grande demora. Nao feche a janela.")
    from .portal import pasta_de_descargas

    pasta_do_navegador = pasta_de_descargas()
    antes_do_pedido = instantaneo_da_pasta(pasta_do_navegador)

    def gravar_a_integra(baixado: Any) -> str:
        pasta = Path(destino)
        pasta.mkdir(parents=True, exist_ok=True)
        sugerido = baixado.suggested_filename or f"{chave}-integra.pdf"
        arquivo = pasta / f"integra-{sugerido}"
        baixado.save_as(str(arquivo))
        return str(arquivo)

    capturados: list = []
    parar_de_ouvir = escutar_descargas(pagina, capturados, gravar_a_integra)
    try:
        escolha.click()
        parada = esperar_a_descarga(pagina, capturados, espera, recuo="    ")
    finally:
        parar_de_ouvir()
    arquivo = arquivo_capturado(capturados)
    if arquivo:
        return arquivo

    resgatado = resgatar_descarga(
        pasta_do_navegador, antes_do_pedido, destino, f"integra-{chave}",
        nome_sugerido(capturados), recuo="    ")
    if resgatado:
        return resgatado

    if parada is None:
        parada = "O navegador anunciou o download e nada ficou no disco."
    parada += recado_de_gravacao(capturados)

    # Em vez de so falhar, LE o indice. O advogado pediu em 08/10/2026 duas
    # formas de baixar em partes, e as duas precisam marcar itens do indice,
    # que nunca foi lido com a caixa de selecao aberta. Fazer essa leitura aqui
    # aproveita a corrida que ja foi gasta. Com a janela fechada nao ha indice
    # para ler, e tentar so troca o recado certo por um erro de leitura.
    mapa = []
    if janela_fechada(pagina):
        mapa = ["a janela se fechou antes de o indice poder ser lido"]
    else:
        try:
            if abrir_caixa_de_selecao(pagina, guarda):
                mapa = relatar_o_indice(pagina)
            else:
                mapa = [f"o botao {BOTAO_CAIXA_DE_SELECAO!r} nao esta na barra"]
        except Exception as outra:
            mapa = [f"nao foi possivel ler o indice ({type(outra).__name__})"]
    raise DownloadIndisponivel(
        f"A escolha {ESCOLHA_INTEGRAL!r} foi clicada e nenhum arquivo foi "
        f"gravado. {parada} Processo grande nao baixa de uma vez, como o "
        "advogado ja havia informado em 06/10/2026."
        + "\n    O INDICE DE DOCUMENTOS, para baixar em partes:\n    "
        + "\n    ".join(mapa)
    ) from None


# ---------------------------------------------------------------------------
# Consulta processual do Portal de Servicos
#
# Telas fotografadas em 06/10/2026, versao 5.25.2 do portal. O formulario
# inteiro mora num QUADRO EMBUTIDO dentro da pagina do portal, e e por isso que
# o relato da pagina de fora dizia "0 campos": o que importa esta no quadro.
# ---------------------------------------------------------------------------

SUFIXO_DA_CONSULTA = "/portalservicos/#/consproc/consultaportal"

# O quadro onde o formulario vive, reconhecido pelo caminho.
MARCA_DO_QUADRO = "/consultaprocessual/"

# Tipo de numeracao. "Unica" ja vem marcada, e ainda assim e conferida: achar
# a tela com "Antiga" marcada e digitar o numero unico devolve "nada
# encontrado", que o advogado leria como processo inexistente.
OPCAO_NUMERACAO_UNICA = "#numeracaoUnica"
OPCAO_NUMERACAO_ANTIGA = "#numeracaoAntiga"

# Os DOIS campos do numero, com `.8.19.` escrito fixo na tela entre eles.
# Nao sao seis campos como no PJe: aqui o primeiro leva sequencial, digito e
# ano juntos, e o segundo leva so a origem.
CAMPO_INICIO = "input[name=numeroProcesso]"
CAMPO_ORIGEM = "#inputSufixoUnica3"

BOTAO_PESQUISAR = "Pesquisar"
BOTAO_VISUALIZADOR = "Processo Eletrônico - Visualizador"

# O `.8.19.` fixo entre os campos e o que amarra este formulario ao Tribunal
# de Justica do Estado do Rio de Janeiro.
SEGMENTO_DO_RIO = 8
TRIBUNAL_DO_RIO = "19"


class ConsultaIndisponivel(RuntimeError):
    """A consulta parou antes de pesquisar, e nada foi enviado."""


def endereco_da_consulta(url_de_login: str) -> str:
    """Endereco da consulta processual, derivado do endereco de login."""
    partes = (url_de_login or "").split("://", 1)
    if len(partes) != 2 or not partes[1]:
        raise ConsultaIndisponivel(
            "Sem endereco de login configurado, nao da para achar a consulta.")
    esquema, resto = partes
    servidor = resto.split("/", 1)[0]
    if not servidor:
        raise ConsultaIndisponivel(
            "O endereco de login nao tem servidor; nao da para achar a consulta.")
    return f"{esquema}://{servidor}{SUFIXO_DA_CONSULTA}"


def conferir_tribunal(numero: Any) -> None:
    """Recusa numero que nao seja do Tribunal de Justica do Rio de Janeiro.

    O formulario traz `.8.19.` escrito fixo entre os dois campos: o portal nao
    pergunta segmento nem tribunal, ele os impoe. Mandar aqui um numero de
    outro tribunal montaria, silenciosamente, o numero de UM PROCESSO QUE NAO
    E O PEDIDO, e a tela que voltasse seria de outro feito ou de nenhum.
    """
    if int(numero.segmento) != SEGMENTO_DO_RIO or numero.tribunal != TRIBUNAL_DO_RIO:
        raise ConsultaIndisponivel(
            f"O numero {numero.formatado} e do segmento {numero.segmento} e do "
            f"tribunal {numero.tribunal}. Esta tela tem '.{SEGMENTO_DO_RIO}."
            f"{TRIBUNAL_DO_RIO}.' fixo entre os campos e so serve ao Tribunal de "
            "Justica do Estado do Rio de Janeiro. Nada foi digitado.")


def partes_do_numero(numero: Any) -> tuple[str, str]:
    """O numero como esta tela o divide: inicio e origem."""
    inicio = f"{numero.sequencial}-{numero.digito_verificador}.{numero.ano}"
    return inicio, numero.origem


def quadro_da_consulta(pagina: Any) -> Any:
    """O quadro embutido onde o formulario vive, ou a propria pagina.

    Devolver a pagina quando nao ha quadro nao e desistir: a conferencia
    seguinte procura os campos, e e ela quem para com uma mensagem que diz o
    que achou.
    """
    try:
        for quadro in list(pagina.frames or [])[1:]:
            if MARCA_DO_QUADRO in (quadro.url or ""):
                return quadro
    except Exception:
        pass
    return pagina


# ---------------------------------------------------------------------------
# A consulta se alcanca pelo MENU, nunca por endereco
#
# Conferido em campo em 06/10/2026: navegar para `#/consproc/consultaportal`
# com a sessao aberta devolveu a pagina publica do tribunal. Rota `#/` nao e
# endereco novo para o navegador, e sim estado interno da aplicacao; mandar o
# navegador ir ate la RECARREGA a pagina inteira, a aplicacao perde o que
# tinha em memoria e o portal manda o visitante para fora.
#
# O caminho que funciona e o do operador: clicar "Consultas" no menu lateral e
# escolher "Consultas Processuais" na caixa que abre.
# ---------------------------------------------------------------------------

MENU_DE_CONSULTAS = "#CONSULTAS"
ITEM_DA_CONSULTA = "Consultas Processuais"
MARCA_DA_CONSULTA = "consproc"


def ja_esta_na_consulta(pagina: Any) -> bool:
    try:
        return MARCA_DA_CONSULTA in (pagina.url or "")
    except Exception:
        return False


# Classe que o portal poe no submenu fechado. Lida na marcacao em 08/10/2026:
#
#   <li class="collapse submenu ng-star-inserted">Consultas Processuais</li>
#
# `collapse` sem `show` quer dizer `display: none`, e por isso `bounding_box`
# devolveu `nenhuma` em vez de uma caixa de zero por zero. Sao duas coisas
# diferentes: o 'Entrar' da tela de perfil OCUPA lugar e nao tem tamanho; este
# item nao esta sendo desenhado. O primeiro so precisa de outro jeito de
# clique; este precisa que o grupo seja ABERTO.
MARCA_DE_RECOLHIDO = "collapse"
MARCAS_DE_ABERTO = ("show", "in")


def esta_recolhido(elemento: Any) -> bool:
    """Se o elemento esta dentro de um grupo fechado, e nao apenas invisivel."""
    try:
        classes = (elemento.get_attribute("class") or "").split()
    except Exception:
        return False
    if MARCA_DE_RECOLHIDO not in classes:
        return False
    return not any(marca in classes for marca in MARCAS_DE_ABERTO)


def abrir_o_grupo_do_menu(pagina: Any, guarda: Any, tentativas: int = 2,
                          segundos: int = 8) -> bool:
    """Clica no cabecalho do grupo ate o item ficar visivel.

    O primeiro clique em `#CONSULTAS` LEVOU a `#/tela-menu`, e nessa tela o
    grupo continua fechado. Abrir e o que o operador faz com o mouse, e e o
    passo que faltava: ate aqui o programa procurava o item de um grupo que
    nunca tinha sido aberto.
    """
    from .core.guarda_navegacao import Acao
    from .portal import elemento_visivel

    for _ in range(max(1, tentativas)):
        cabecalho = elemento_visivel(pagina, MENU_DE_CONSULTAS)
        if cabecalho is None:
            return False
        guarda.pode_executar(Acao.CLICAR, MENU_DE_CONSULTAS, url=pagina.url)
        clicar_com_jeito(cabecalho)
        try:
            pagina.wait_for_timeout(600)
        except Exception:
            pass
        achado = achar_por_texto_em_qualquer_lugar(
            pagina, ITEM_DA_CONSULTA, exigir_posicao=False)
        if achado is not None:
            return True
    return False


def abrir_consulta_pelo_menu(pagina: Any, guarda: Any, segundos: int = 45) -> None:
    """Do painel ate a consulta processual, pelo menu lateral."""
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (PREFIXO_DE_TEXTO, endereco_sem_dado, esperar_elemento,
                         permissao_efemera)

    if ja_esta_na_consulta(pagina):
        return

    alvo_do_item = f"{PREFIXO_DE_TEXTO}{ITEM_DA_CONSULTA}"
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="abrir a consulta processual pelo menu",
        conferido_em="execucao atual",
        seletores_clicaveis=(MENU_DE_CONSULTAS, alvo_do_item),
    ))

    menu = esperar_elemento(pagina, MENU_DE_CONSULTAS, min(segundos, 20))
    if menu is None:
        # Conferido no acompanhamento de 06/10/2026: este menu so existe no
        # painel, DEPOIS de o tipo de usuario ser escolhido. Na tela que pede o
        # perfil ele nao esta, e procurar mais nao o faria aparecer. Dizer isso
        # aqui poupa a rodada inteira que custaria descobri-lo de novo.
        raise ConsultaIndisponivel(
            f"O menu {MENU_DE_CONSULTAS} nao esta na tela "
            f"({endereco_sem_dado(pagina.url, 80)}). "
            "Ele so existe no painel, depois de o TIPO DE USUARIO ser escolhido: "
            f"se o endereco ainda for {TELA_DE_PERFIL}, a escolha do perfil e "
            "que nao chegou ao fim. Nada foi clicado.")
    guarda.pode_executar(Acao.CLICAR, MENU_DE_CONSULTAS, url=pagina.url)
    clicar_com_jeito(menu)

    # Pela busca geral, e nao por uma olhada estrita. Conferido em campo em
    # 07/10/2026: o menu levou a `#/tela-menu`, e dos 30 clicaveis dela
    # apenas 4 estavam DENTRO da janela. O item existia e estava abaixo da
    # dobra, que e a terceira forma do mesmo defeito neste portal.
    item = achar_clicavel(pagina, ITEM_DA_CONSULTA, min(segundos, 15))

    # O item pode existir e estar dentro de um grupo FECHADO. Abrir o grupo e
    # o que o operador faz com o mouse, e e diferente de insistir no clique:
    # ate 08/10/2026 o programa procurava o item de um grupo que nunca tinha
    # sido aberto, e por isso o achava `display: none`.
    if item is not None and esta_recolhido(item):
        print(f"    [RECOLHIDO] O item {ITEM_DA_CONSULTA!r} esta num grupo "
              "fechado. Abrindo o grupo antes de clicar nele.")
        if abrir_o_grupo_do_menu(pagina, guarda, segundos=min(segundos, 8)):
            item = achar_clicavel(pagina, ITEM_DA_CONSULTA, min(segundos, 10))

    if item is None:
        raise ConsultaIndisponivel(
            f"O item {ITEM_DA_CONSULTA!r} nao apareceu depois de o menu ser "
            f"clicado, por via nenhuma. Endereco atual: "
            f"{endereco_sem_dado(pagina.url, 80)}. Nada mais foi clicado."
            + "\n    CANDIDATOS AO ITEM:\n    "
            + "\n    ".join(relato_dos_candidatos(pagina, ITEM_DA_CONSULTA)))
    guarda.pode_executar(Acao.CLICAR, alvo_do_item, url=pagina.url)
    jeito = clicar_com_jeito(item)
    if jeito == "documento":
        print(f"    [SEM TAMANHO] O item {ITEM_DA_CONSULTA!r} nao tem caixa "
              "clicavel. O clique foi disparado no proprio elemento.")
    elif jeito == "nenhum":
        raise ConsultaIndisponivel(
            f"O item {ITEM_DA_CONSULTA!r} foi encontrado e nao aceitou clique "
            "de forma nenhuma. Nada mais foi clicado.")

    # Prova positiva de que o clique levou aonde devia, em vez de confiar nele.
    import time as _tempo

    limite = _tempo.monotonic() + min(segundos, 20)
    while not ja_esta_na_consulta(pagina):
        if _tempo.monotonic() >= limite:
            raise ConsultaIndisponivel(
                f"O item {ITEM_DA_CONSULTA!r} foi clicado e a tela nao chegou a "
                f"consulta. Endereco atual: {endereco_sem_dado(pagina.url, 80)}. "
                "Nada foi digitado.")
        try:
            pagina.wait_for_timeout(400)
        except Exception:
            _tempo.sleep(0.4)


def onde_estao_os_botoes(quadro: Any, texto: str) -> str:
    """O que a tela tem com este texto, e onde cada um esta.

    A recusa "o botao nao esta na tela" e verdadeira em quatro situacoes
    diferentes: o botao nao existe, existe oculto, existe com outro texto, ou
    existe visivel e fora da janela. Sem distinguir as quatro, cada corrida
    gasta uma tentativa do advogado para descartar uma delas. Em 09/10/2026
    foram tres corridas ate chegar na quarta, que era o caso.

    Nenhum rotulo de item e impresso: em grupo grande, rotulo de botao e
    conteudo do processo.
    """
    from .portal import (caixa_na_tela, janela_de,
                         relatar_a_medida_do_conteudo, sem_acento)

    alvo = sem_acento(texto).strip()
    janela = janela_de(quadro)
    try:
        achados = quadro.query_selector_all(
            "button, input[type=submit], input[type=button], a")
    except Exception as erro:
        return f" Nao foi possivel reconhecer a tela: {type(erro).__name__}."

    iguais, visiveis, na_janela, posicoes = 0, 0, 0, []
    for elemento in achados:
        try:
            escrito = sem_acento(
                elemento.inner_text() or elemento.get_attribute("value") or ""
            ).strip()
            if escrito != alvo:
                continue
            iguais += 1
            if not elemento.is_visible():
                continue
            visiveis += 1
            caixa = elemento.bounding_box()
            if caixa_na_tela(caixa, janela["width"], janela["height"]):
                na_janela += 1
            elif caixa is not None and len(posicoes) < 3:
                posicoes.append(f"x={int(caixa['x'])} y={int(caixa['y'])}")
        except Exception:
            continue

    partes = [
        f" Na tela: {len(achados)} elemento(s) clicavel(is), {iguais} com este "
        f"texto, {visiveis} visivel(is), {na_janela} dentro da janela de "
        f"{janela['width']}x{janela['height']}."
    ]
    if posicoes:
        partes.append(" Fora da janela em: " + "; ".join(posicoes) + ".")
        # Se ha para onde rolar, o conserto e rolar; se o desenho esta cortado,
        # rolar nao alcanca e o conserto e encolher a tela (JUSTICA_ESCALA).
        # Sao dois consertos diferentes para a mesma frase de recusa.
        partes.append(" " + relatar_a_medida_do_conteudo(quadro) + ".")
    if iguais == 0:
        partes.append(" Nenhum elemento tem este texto: ou a tela mudou, ou a "
                      "consulta nao chegou a se montar.")
    return "".join(partes)


def conferir_forma_do_formulario(quadro: Any, segundos: int = 20) -> tuple:
    """Acha os dois campos e o botao, e recusa a tela que nao bate.

    Antes de digitar, nunca depois: campo que falta devolve busca vazia, e
    busca vazia e indistinguivel de processo inexistente para quem le o
    resultado.
    """
    from .portal import achar_opcional, elemento_visivel, esperar_elemento

    # Espera o primeiro campo, e so entao procura o resto: numa aplicacao de
    # pagina unica a tela chega vazia e se monta depois.
    inicio = esperar_elemento(quadro, CAMPO_INICIO, segundos)
    origem = elemento_visivel(quadro, CAMPO_ORIGEM)
    faltando = [nome for nome, alvo in
                ((CAMPO_INICIO, inicio), (CAMPO_ORIGEM, origem)) if alvo is None]
    if faltando:
        raise ConsultaIndisponivel(
            "A tela da consulta nao tem " + " nem ".join(faltando)
            + ". Nada foi digitado. Ou a autenticacao parou antes dela, ou a "
            "tela mudou desde 06/10/2026.")

    pesquisar = elemento_visivel(quadro, f"texto={BOTAO_PESQUISAR}")
    if pesquisar is None:
        from .telas import gravar_a_tela

        gravar_a_tela(quadro, "recusa-botao-pesquisar")
        raise ConsultaIndisponivel(
            f"O botao {BOTAO_PESQUISAR!r} nao esta na tela. Nada foi digitado."
            + onde_estao_os_botoes(quadro, BOTAO_PESQUISAR))

    unica = achar_opcional(quadro, OPCAO_NUMERACAO_UNICA)
    return inicio, origem, pesquisar, unica


def buscar(pagina: Any, guarda: Any, numero: Any, url_de_login: str,
           segundos: int = 45) -> Any:
    """Abre a consulta, digita o numero e pesquisa. Devolve o quadro usado.

    Somente leitura: preenche e pesquisa. Nao abre o visualizador e nao baixa
    nada, porque abrir os autos e ato separado.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import _assentar, permissao_efemera, preencher_conferindo

    conferir_tribunal(numero)
    # Pelo MENU, nunca por endereco: rota `#/` nao e endereco novo para o
    # navegador, e sim estado interno da aplicacao. Mandar o navegador ir ate
    # la recarrega a pagina, a aplicacao perde o que tinha em memoria e o
    # portal manda o visitante para a pagina publica. Conferido em campo.
    abrir_consulta_pelo_menu(pagina, guarda, segundos)
    _assentar(pagina, segundos)

    quadro = quadro_da_consulta(pagina)
    inicio, origem, pesquisar, unica = conferir_forma_do_formulario(
        quadro, segundos)

    # A autorizacao so e escrita DEPOIS de a forma bater, e nomeia o que a
    # propria tela mostrou. Liberar antes seria liberar o que ainda nao se sabe
    # o que e.
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="consulta processual, somente a busca",
        conferido_em="execucao atual",
        # A linha do resultado entra aqui porque abrir o processo na lista e
        # parte de CHEGAR nele, e nao de abrir os autos, que e ato separado e
        # tem permissao propria.
        seletores_clicaveis=(OPCAO_NUMERACAO_UNICA, f"texto={BOTAO_PESQUISAR}",
                             ALVO_DO_RESULTADO),
        seletores_preenchiveis=(CAMPO_INICIO, CAMPO_ORIGEM),
    ))

    # "Unica" ja vem marcada, e ainda assim e garantida: achar a tela com
    # "Antiga" marcada e digitar o numero unico devolve "nada encontrado", que
    # o advogado leria como processo inexistente.
    if unica is not None:
        try:
            ja_marcada = unica.evaluate("e => !!e.checked")
        except Exception:
            ja_marcada = False
        if not ja_marcada:
            guarda.pode_executar(Acao.CLICAR, OPCAO_NUMERACAO_UNICA, url=pagina.url)
            unica.click()

    texto_inicio, texto_origem = partes_do_numero(numero)
    for alvo, seletor, valor, rotulo in (
        (inicio, CAMPO_INICIO, texto_inicio, "inicio do numero"),
        (origem, CAMPO_ORIGEM, texto_origem, "origem do numero"),
    ):
        guarda.pode_executar(Acao.PREENCHER, seletor, url=pagina.url)
        preencher_conferindo(alvo, valor, rotulo)

    # Remonta o numero a partir da TELA, com o `.8.19.` que o portal impoe, e
    # confere contra o pedido. Campo com mascara que recusa o formato fica
    # vazio sem reclamar, e a busca volta "nada encontrado" por defeito nosso.
    digitado = (_so_digitos(inicio) + str(SEGMENTO_DO_RIO) + TRIBUNAL_DO_RIO
                + _so_digitos(origem))
    if digitado != numero.apenas_digitos:
        raise ConsultaIndisponivel(
            f"O numero montado na tela ficou com {len(digitado)} digito(s) e nao "
            f"confere com {numero.formatado}. Nada foi pesquisado.")

    from .telas import gravar_a_tela

    gravar_a_tela(quadro, "consulta-preenchida-antes-de-pesquisar")
    guarda.pode_executar(Acao.CLICAR, f"texto={BOTAO_PESQUISAR}", url=pagina.url)
    pesquisar.click()
    _assentar(pagina, segundos)
    # A TELA QUE FALTAVA. Em 16/10/2026 a pesquisa foi enviada com o numero
    # certo, conferido na tela, e as seis tabelas de "Resultado da Pesquisa"
    # voltaram com uma linha cada, que e so o cabecalho. Nao havia como saber
    # dali se o portal disse "nenhum registro encontrado", se pediu mais um
    # filtro ou se devolveu a tela do processo noutro lugar: o relato nao lia
    # mensagem dentro de quadro. Agora esta tela fica gravada SEMPRE, deu certo
    # ou nao, e a proxima pergunta sobre ela nao custa outra autenticacao.
    atual = quadro_da_consulta(pagina) or quadro
    gravar_a_tela(atual, "consulta-depois-de-pesquisar")

    # A busca devolve uma LISTA, e a tela do processo mora atras de um clique
    # nela. Ver o bloco em `abrir_o_processo_da_lista`.
    aberto = abrir_o_processo_da_lista(atual, guarda, numero, pagina.url,
                                       segundos)
    print(f"  Lista de resultado: {aberto['situacao']}.")
    if aberto["clicado"]:
        _assentar(pagina, segundos)
    return quadro_da_consulta(pagina) or atual


# O PASSO QUE FALTAVA, e como ele foi descoberto.
#
# Ate 16/10/2026 o programa preenchia o numero, clicava em `Pesquisar` e ja
# esperava o botao do Visualizador aparecer. Ele nunca aparecia, e a recusa
# dizia "a pesquisa nao chegou a devolver o processo", que era falso.
#
# A tela gravada depois da pesquisa mostrou o que havia ali: uma
# `p-datatable` com cabecalhos "Codigo CNJ, Nome Comarca, Descricao Serventia,
# Classe, Assunto, ultimo Movimento", um `p-paginator` embaixo, e CINCO
# clicaveis cujo texto visivel e um numero de processo, em x=50, um a cada
# 190 de altura. O filtro de privacidade imprimiu os cinco como
# `<numero de processo>`, que e a prova de que sao numero de processo.
#
# Ou seja: a busca SEMPRE funcionou. O que faltava era abrir o processo na
# lista de resultado. A tela do processo mora atras desse clique.
#
# Por que o numero e CONFERIDO antes de clicar, e nao se clica na primeira
# linha: a busca devolveu cinco linhas para um numero exato. Abrir o processo
# errado e abrir o processo de outra pessoa, e isso nao se desfaz. So e
# clicado o que confere digito por digito.
ALVO_DO_RESULTADO = "linha-do-resultado-com-o-numero-pesquisado"

# Quanto esperar a lista de resultado montar. Aplicacao de pagina unica
# devolve a tela vazia e preenche depois, e esta ja foi a causa de seis
# defeitos diferentes neste mesmo portal.
ESPERA_DA_LISTA = 20


# Como a linha da lista e encontrada, e por que nao e pela lista de clicaveis.
#
# `ALVOS_CLICAVEIS` cobre `button`, `input` de botao e `a`. A lista de
# resultado deste portal e uma `p-datatable` do PrimeNG, e nela a celula que
# leva ao processo pode ser `td`, `span` ou `div` com tratador de clique, sem
# ser nenhuma daquelas quatro etiquetas. Procurar so entre elas pode nao achar
# linha nenhuma numa tela que tem cinco.
#
# Entao a procura e pelo TEXTO PROPRIO de qualquer elemento: os algarismos dos
# nos de texto FILHOS DIRETOS, e nao `textContent`, que soma os descendentes.
# A diferenca e o que separa a celula do numero da tabela inteira que a contem:
# com `textContent`, `<table>`, `<tbody>`, `<tr>` e `<td>` casariam todos, e o
# clique iria parar na tabela.
#
# A marca `data-justica-linha` e posta e retirada pelo proprio script, a cada
# chamada. E a unica escrita que este programa faz na pagina, e existe porque
# devolver elementos de dentro do navegador exige um seletor: sem a marca
# seriam mil e duzentas idas e vindas para perguntar o texto de cada no, uma
# por vez.
JS_DAS_LINHAS_DO_RESULTADO = r"""(alvo) => {
  const so = (s) => (s || '').replace(/\D/g, '');
  let achados = 0;
  for (const e of document.querySelectorAll('[data-justica-linha]')) {
    e.removeAttribute('data-justica-linha');
  }
  for (const e of document.querySelectorAll('*')) {
    let proprio = '';
    for (const f of e.childNodes) {
      if (f.nodeType === 3) proprio += f.nodeValue;
    }
    if (so(proprio) !== alvo) continue;
    const r = e.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) continue;
    e.setAttribute('data-justica-linha', String(achados));
    achados += 1;
  }
  return achados;
}"""


def _digitos_do_texto(elemento: Any) -> str:
    """So os algarismos do texto VISIVEL do elemento."""
    try:
        texto = elemento.inner_text() or ""
    except Exception:
        return ""
    return "".join(c for c in texto if c.isdigit())


def processos_na_lista(quadro: Any, numero: Any) -> list:
    """Os elementos da lista cujo numero CONFERE com o pesquisado.

    Comparacao por algarismo, e nao por texto: a lista escreve o numero
    formatado e o pedido pode vir de qualquer jeito. Exata, e nunca por
    conter: um numero pode ser pedaco de outro.
    """
    alvo = numero.apenas_digitos
    try:
        quantas = quadro.evaluate(JS_DAS_LINHAS_DO_RESULTADO, alvo)
    except Exception:
        quantas = 0
    if quantas:
        try:
            achados = quadro.query_selector_all("[data-justica-linha]") or []
        except Exception:
            achados = []
        if achados:
            return achados

    # Caminho de reserva, para a tela que o script nao conseguiu varrer.
    from .portal import ALVOS_CLICAVEIS

    try:
        candidatos = quadro.query_selector_all(ALVOS_CLICAVEIS) or []
    except Exception:
        return []
    achados = []
    for elemento in candidatos:
        try:
            if _digitos_do_texto(elemento) != alvo:
                continue
            if not elemento.is_visible():
                continue
        except Exception:
            continue
        achados.append(elemento)
    return achados


def esperar_a_lista_de_resultado(quadro: Any, numero: Any,
                                 segundos: int = ESPERA_DA_LISTA) -> list:
    """Espera a lista montar e devolve as linhas que conferem."""
    import time as _tempo

    limite = _tempo.monotonic() + max(1, segundos)
    while True:
        achados = processos_na_lista(quadro, numero)
        if achados:
            return achados
        if _tempo.monotonic() >= limite:
            return []
        try:
            quadro.wait_for_timeout(500)
        except Exception:
            _tempo.sleep(0.5)


def resumo_da_lista(quadro: Any) -> str:
    """Quantas linhas a lista tem, sem imprimir nenhuma delas.

    "Nao achei o numero" cobre duas coisas muito diferentes: lista vazia, que e
    busca sem resultado, e lista cheia em que o numero nao bate, que e defeito
    da comparacao ou processo que nao e o pedido. Contar separa as duas sem
    mostrar conteudo.
    """
    try:
        contagem = quadro.evaluate(
            "() => ({tabelas: document.querySelectorAll('table').length,"
            " linhas: document.querySelectorAll('tbody tr').length,"
            " paginadores: document.querySelectorAll('p-paginator').length})")
    except Exception:
        return "Nao foi possivel contar a lista."
    if not isinstance(contagem, dict):
        return "Nao foi possivel contar a lista."
    return (f"Na tela ha {contagem.get('tabelas', 0)} tabela(s), "
            f"{contagem.get('linhas', 0)} linha(s) de corpo e "
            f"{contagem.get('paginadores', 0)} paginador(es).")


def abrir_o_processo_da_lista(quadro: Any, guarda: Any, numero: Any,
                              endereco_da_tela: str,
                              segundos: int = ESPERA_DA_LISTA) -> dict:
    """Clica, na lista de resultado, no processo cujo numero confere.

    `endereco_da_tela` e o endereco da PAGINA, e nunca o do quadro. A permissao
    desta tela foi escrita a partir de `pagina.url`, e o quadro embutido mora em
    outro caminho do mesmo dominio: `/consultaprocessual/` contra
    `/portalservicos/`. Pedir autorizacao com o endereco do quadro faz a trava
    nao achar permissao nenhuma e barrar o clique, que foi o que aconteceu em
    16/10/2026, depois de a procura pela linha finalmente funcionar. Os outros
    cliques desta mesma tela ja usavam o da pagina; este nasceu diferente.

    Devolve o que aconteceu, para o relato dizer. NAO levanta erro quando nao
    acha a lista: ha telas em que a busca por numero unico ja cai direto no
    processo, e nesse caso nao ha lista nenhuma e o passo seguinte e que vai
    dizer se chegou.
    """
    from .core.guarda_navegacao import Acao
    from .telas import gravar_a_tela

    achados = esperar_a_lista_de_resultado(quadro, numero, segundos)
    if not achados:
        gravar_a_tela(quadro, "sem-linha-com-o-numero-na-lista")
        return {"situacao": "nenhuma linha com este numero na lista. "
                            + resumo_da_lista(quadro),
                "linhas": 0, "clicado": False}

    if len(achados) > 1:
        # Mesmo numero em mais de uma linha acontece quando o processo aparece
        # em graus ou serventias diferentes. Abre a primeira e DIZ que havia
        # mais de uma, para o advogado conferir se era a que ele queria.
        print(f"      [ATENCAO] {len(achados)} linhas trazem este mesmo numero. "
              "Abrindo a primeira.")

    guarda.pode_executar(Acao.CLICAR, ALVO_DO_RESULTADO, url=endereco_da_tela)
    try:
        achados[0].scroll_into_view_if_needed(timeout=2000)
    except Exception:
        pass
    try:
        achados[0].click()
    except Exception as erro:
        return {"situacao": f"a linha nao aceitou o clique ({type(erro).__name__})",
                "linhas": len(achados), "clicado": False}
    gravar_a_tela(quadro, "depois-de-abrir-o-processo-da-lista")
    return {"situacao": f"aberta a linha que confere, de {len(achados)}",
            "linhas": len(achados), "clicado": True}


def _so_digitos(elemento: Any) -> str:
    try:
        return elemento.evaluate("e => (e.value || '').replace(/\\D/g, '')")
    except Exception:
        return ""


# A tela de justificativa, lida em campo em 08/10/2026. Clicar em
# "Processo Eletronico - Visualizador" NAO abre janela: abre este formulario,
# dentro do mesmo quadro, em `#/consultar/detalhes-processo`.
#
#   <input  type=password id=senhaProvisoria
#           rotulo='Senha para visualizar o processo eletronico*'>
#   <textarea id=motivo rotulo='Motivo*' maxlength=499>
#   botao 'Visualizar Processo'
#
# A senha NAO e preenchida por este programa, e nem sequer entra na lista de
# seletores preenchiveis da trava: ela e credencial de acesso a autos, dada ao
# titular, e inventa-la seria exatamente o que este projeto nao faz. Se o
# portal a exigir, o comando para e diz.
CAMPO_DO_MOTIVO = "#motivo"
CAMPO_DA_SENHA_PROVISORIA = "#senhaProvisoria"
BOTAO_VISUALIZAR_PROCESSO = "Visualizar Processo"
# Instrucao do advogado em 08/10/2026, por escrito. Fica como PADRAO, e nao
# como texto fixo: declarar o motivo do acesso aos autos e ato dele, e o
# comando imprime o que digitou para que haja registro do que foi declarado.
MOTIVO_PADRAO = "consulta"


class MotivoNaoInformado(RuntimeError):
    """O portal pediu o motivo do acesso e nenhum foi informado."""


def _janela_do_clique(hospedeira: Any, elemento: Any, segundos: int) -> Optional[Any]:
    """Clica e devolve a janela nova, ou None se nenhuma abrir no prazo."""
    try:
        with hospedeira.context.expect_page(timeout=max(1, segundos) * 1000) as nova:
            clicar_com_jeito(elemento)
        return nova.value
    except Exception:
        return None


def tela_de_justificativa(quadro: Any) -> Optional[Any]:
    """O campo do motivo, quando o portal pede justificativa para abrir."""
    from .portal import elemento_visivel

    return elemento_visivel(quadro, CAMPO_DO_MOTIVO)


# A tela do processo tem DOIS botoes chamados "Visualizar Processo", lidos no
# relato de 08/10/2026. A busca por nome devolve o primeiro do documento, e o
# que vale e o do dialogo da justificativa. O advogado disse qual: "o botao
# visualizar processo a ser clicado e o abaixo da caixa motivo".
#
# Duas formas de achar o mesmo botao, e a primeira nao depende de posicao:
# subir do campo do motivo ate o PRIMEIRO antepassado que contenha exatamente
# UM botao com aquele nome. Esse e o botao daquele dialogo, por estrutura.
# A regra do advogado entra como reserva, quando a estrutura nao desempata.
_JS_BOTAO_DO_DIALOGO = """
(campo, alvo) => {
  const normal = (t) => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const seletor = 'button, a, input[type=submit], input[type=button]';
  let no = campo.parentElement;
  while (no) {
    const achados = Array.from(no.querySelectorAll(seletor)).filter(
      (b) => normal(b.innerText || b.value) === alvo);
    if (achados.length === 1) return achados[0];
    if (achados.length > 1) return null;
    no = no.parentElement;
  }
  return null;
}
"""


def botao_do_mesmo_dialogo(campo: Any, nome: str) -> Optional[Any]:
    """O botao com este nome que esta no MESMO dialogo do campo.

    Por estrutura, e nao por posicao: sobe do campo ate o primeiro
    antepassado que contenha exatamente um botao com aquele nome. Se o
    primeiro antepassado que contem algum ja contiver dois, nao desempata e
    devolve nada, porque chutar entre dois seria escolher no escuro.
    """
    try:
        punho = campo.evaluate_handle(_JS_BOTAO_DO_DIALOGO, nome.strip().lower())
    except Exception:
        return None
    try:
        return punho.as_element()
    except Exception:
        return None


def botao_abaixo_do_campo(pagina: Any, campo: Any, nome: str) -> Optional[Any]:
    """O botao com este nome que fica LOGO ABAIXO do campo.

    A regra e do advogado, dita em 08/10/2026: "o botao visualizar processo a
    ser clicado e o abaixo da caixa motivo". Entra como reserva da busca por
    estrutura, e nao antes dela: posicao e a ultima coisa em que confio para
    desempatar, porque muda com o tamanho da janela.

    "Logo abaixo" e o de menor distancia entre os que comecam abaixo do campo,
    e nao qualquer um que esteja mais para baixo.
    """
    from .portal import ALVOS_CLICAVEIS, sem_acento

    try:
        caixa = campo.bounding_box()
    except Exception:
        caixa = None
    if not caixa:
        return None
    base = caixa["y"]
    alvo = sem_acento(nome).strip()

    melhor, menor = None, None
    try:
        candidatos = pagina.query_selector_all(ALVOS_CLICAVEIS) or []
    except Exception:
        return None
    for elemento in candidatos:
        try:
            escrito = sem_acento(
                elemento.inner_text() or elemento.get_attribute("value") or "")
            if escrito.strip() != alvo:
                continue
            dele = elemento.bounding_box()
        except Exception:
            continue
        if not dele or dele["y"] < base:
            continue
        distancia = dele["y"] - base
        if menor is None or distancia < menor:
            melhor, menor = elemento, distancia
    return melhor


def achar_o_visualizar_processo(pagina: Any, campo: Any,
                                segundos: int = 15) -> tuple:
    """O botao certo entre os homonimos, e COMO ele foi escolhido.

    Devolve (elemento, criterio). O criterio vai para o relato: escolher entre
    homonimos nunca pode acontecer calado.
    """
    pelo_dialogo = botao_do_mesmo_dialogo(campo, BOTAO_VISUALIZAR_PROCESSO)
    if pelo_dialogo is not None:
        return pelo_dialogo, "pelo dialogo do campo do motivo"

    abaixo = botao_abaixo_do_campo(pagina, campo, BOTAO_VISUALIZAR_PROCESSO)
    if abaixo is not None:
        return abaixo, "por ser o primeiro abaixo da caixa do motivo"

    return achar_clicavel(pagina, BOTAO_VISUALIZAR_PROCESSO, segundos), \
        "pelo nome, SEM desempate entre homonimos"


# Marca da tela do processo, depois que a busca devolve. Enquanto o quadro
# estiver em `#/consultaportal` ele ainda e o FORMULARIO de busca.
MARCA_DA_TELA_DO_PROCESSO = "detalhes-processo"


def esperar_a_tela_do_processo(pagina: Any, segundos: int = 45) -> tuple:
    """Espera a busca devolver o processo, e devolve (quadro, botao).

    Reconsulta o QUADRO a cada volta, e nao so o botao: quando a aplicacao
    troca de rota, o quadro que se tinha em maos pode nao ser mais o que esta
    na tela, e procurar nele e procurar no lugar certo de um instante que ja
    passou.

    Devolve o botao do Visualizador quando ele aparece. Devolve (quadro, None)
    quando o prazo acaba, para que quem chama possa dizer EM QUE TELA parou.
    """
    import time as _tempo

    from .portal import elemento_visivel

    limite = _tempo.monotonic() + max(1, min(segundos, 30))
    quadro = quadro_da_consulta(pagina)
    while True:
        quadro = quadro_da_consulta(pagina) or quadro
        botao = elemento_visivel(quadro, f"texto={BOTAO_VISUALIZADOR}")
        if botao is not None:
            return quadro, botao
        if _tempo.monotonic() >= limite:
            return quadro, None
        try:
            pagina.wait_for_timeout(500)
        except Exception:
            _tempo.sleep(0.5)


# ---------------------------------------------------------------------------
# Leitura da tela do processo
#
# ATENCAO, e isto nao e formalidade: esta leitura e GENERICA. A tela do
# processo do Portal de Servicos nunca foi vista por este programa. Todo o
# resto deste arquivo foi escrito a partir de tela real, lida em campo nos
# dias 05, 06 e 08/10/2026; esta parte, nao.
#
# Por isso nada aqui procura identificador do portal. O que ela procura e
# ESTRUTURA que existe em qualquer pagina:
#
#   - lista de definicao, `<dt>` seguido de `<dd>`;
#   - linha de tabela com exatamente duas celulas, rotulo e valor;
#   - folha de texto no formato "Rotulo: valor";
#   - rotulo que termina em dois pontos, com o valor na folha seguinte;
#   - linha que comeca por data, que e como movimentacao se apresenta.
#
# O que ela devolve vem marcado como leitura nao conferida, e o relatorio
# junto traz a estrutura da tela (tabelas e familias de identificador, sem
# conteudo nenhum) justamente para que a leitura possa ser apertada depois,
# contra a tela de verdade, em vez de continuar generica para sempre.
# ---------------------------------------------------------------------------

AVISO_DA_LEITURA = (
    "Leitura GENERICA. Os rotulos e as linhas foram achados pela estrutura da "
    "pagina (lista de definicao, linha de duas celulas, texto no formato "
    "'Rotulo: valor' e linha que comeca por data), e NAO por seletor lido da "
    "tela real do Portal de Servicos, que este programa nunca viu. Confira "
    "contra a tela antes de usar como fonte."
)

JS_DA_TELA_DO_PROCESSO = r"""
() => {
  const corta = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const visivel = (e) => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const semAcento = (s) => (s || '').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

  // Os rotulos de MOVIMENTO, lidos na tela real em 13/10/2026 depois do
  // clique em "Todos Os Movimentos". Eles aparecem uma vez por movimento, e
  // por isso NAO sao campos da capa: deixa-los entrar ali fazia o ultimo
  // movimento ocupar o lugar do processo, e os outros nove sumirem.
  const ROTULOS_DE_DATA = ['data', 'data da juntada', 'data do expediente',
                           'data da digitacao'];
  const ROTULOS_DE_DESCRICAO = ['descricao', 'descricao da juntada'];
  const ROTULOS_DE_MOVIMENTO = ROTULOS_DE_DATA
    .concat(ROTULOS_DE_DESCRICAO).concat(['tipo do movimento']);

  const pares = [];
  const vistos = new Set();
  // Rotulo e nome de campo, nao linha de movimentacao. Sem esta regra, a
  // tabela de movimentos entrava inteira na capa do processo, cada data virando
  // um "rotulo", e a hora "14:22" ainda virava o par "03/05/2018 14" -> "22".
  const ehRotulo = (r) => (
    /[A-Za-zÀ-ÿ]/.test(r) &&
    !/^\d{1,2}\/\d{1,2}\/\d{2,4}/.test(r) &&
    !/^\d/.test(r) &&
    r.length <= 60
  );
  const guardar = (rotulo, valor) => {
    rotulo = corta(rotulo, 120).replace(/:\s*$/, '');
    valor = corta(valor, 300);
    if (!rotulo || !valor || rotulo === valor) return;
    if (!ehRotulo(rotulo)) return;
    if (ROTULOS_DE_MOVIMENTO.indexOf(semAcento(rotulo)) >= 0) return;
    const chave = rotulo.toLowerCase() + '\u0000' + valor;
    if (vistos.has(chave)) return;
    vistos.add(chave);
    pares.push([rotulo, valor]);
  };

  for (const dl of document.querySelectorAll('dl')) {
    const filhos = Array.from(dl.children);
    for (let i = 0; i < filhos.length - 1; i++) {
      if (filhos[i].tagName === 'DT' && filhos[i + 1].tagName === 'DD') {
        guardar(filhos[i].innerText, filhos[i + 1].innerText);
      }
    }
  }

  // Tabela COM cabecalho proprio guarda dados em linha, nao rotulo e valor.
  // Lido na tela real em 13/10/2026: a tabela "Tipo / Personagem" fez
  // "Autor", "Reu", "Advogado" e "Representante Legal" entrarem na capa do
  // processo como se fossem campos dela. Sao partes, e tem lugar proprio.
  const temCabecalho = (tabela) => {
    if (!tabela) return false;
    const topo = tabela.querySelector('tr');
    const celulas = topo ? Array.from(topo.children) : [];
    return celulas.length > 0 && celulas.every(c => c.tagName === 'TH');
  };

  for (const tr of document.querySelectorAll('tr')) {
    const celulas = Array.from(tr.children);
    if (celulas.length !== 2) continue;
    // Linha de cabecalho e titulo de coluna, nao rotulo e valor: "Data" nao
    // vale "Movimento". As duas celulas serem TH e o que a distingue.
    if (celulas[0].tagName === 'TH' && celulas[1].tagName === 'TH') continue;
    if (temCabecalho(tr.closest('table'))) continue;
    guardar(celulas[0].innerText, celulas[1].innerText);
  }

  // As PARTES, da tabela que a tela real nomeia "Tipo" e "Personagem". Este e
  // o primeiro trecho desta leitura que nao e generico: o cabecalho foi lido
  // da tela de verdade em 13/10/2026. Quando ele nao bate, nada sai daqui.
  const partes = [];
  const partesVistas = new Set();
  for (const tabela of document.querySelectorAll('table')) {
    const topo = tabela.querySelector('tr');
    const cabecalho = topo
      ? Array.from(topo.children).map(c => semAcento(corta(c.innerText, 40)))
      : [];
    if (cabecalho.length !== 2) continue;
    if (cabecalho[0] !== 'tipo' || cabecalho[1] !== 'personagem') continue;
    for (const linha of Array.from(tabela.querySelectorAll('tr')).slice(1)) {
      const celulas = Array.from(linha.children);
      if (celulas.length !== 2) continue;
      const tipo = corta(celulas[0].innerText, 60);
      const nome = corta(celulas[1].innerText, 200);
      if (!tipo || !nome) continue;
      const chave = tipo + '\u0000' + nome;
      if (partesVistas.has(chave)) continue;
      partesVistas.add(chave);
      partes.push([tipo, nome]);
    }
  }

  const folhas = document.querySelectorAll(
    'span, div, p, li, label, strong, b, td, h1, h2, h3, h4, h5');
  for (const e of folhas) {
    if (e.children.length > 0) continue;
    if (!visivel(e)) continue;
    const texto = corta(e.innerText, 360);
    if (!texto) continue;
    const m = texto.match(/^([^:]{2,60}):\s*(.+)$/);
    if (m) { guardar(m[1], m[2]); continue; }
    if (/:$/.test(texto)) {
      const vizinho = e.nextElementSibling;
      if (vizinho && vizinho.children.length === 0 && visivel(vizinho)) {
        guardar(texto, corta(vizinho.innerText, 300));
      }
    }
  }

  const movimentacoes = [];
  const jaVistas = new Set();
  const comecaPorData = /^(\d{2}\/\d{2}\/\d{4})(?:[\s,]+(\d{2}:\d{2}(?::\d{2})?))?/;
  const soData = /^(\d{2}\/\d{2}\/\d{4})(?:[\s,]+(\d{2}:\d{2}(?::\d{2})?))?$/;
  // A CONTA do que foi descartado. Em 13/10/2026 onze blocos se formaram,
  // todos com valor lido, e sairam tres movimentacoes. Oito sumiram em
  // silencio, e o terminal nao tinha como dizer se foi por falta de descricao
  // ou por repeticao. Sao dois motivos com dois consertos diferentes.
  const descartes = {sem_data: 0, sem_descricao: 0, repetidas: 0};
  const guardarMovimento = (data, hora, descricao, origem) => {
    descricao = corta(descricao, 300);
    if (!data) { descartes.sem_data += 1; return; }
    if (!descricao) { descartes.sem_descricao += 1; return; }
    const chave = data + '\u0000' + descricao;
    if (jaVistas.has(chave)) { descartes.repetidas += 1; return; }
    jaVistas.add(chave);
    movimentacoes.push([data, hora || '', descricao, origem]);
  };

  // Primeira passada: a linha COMECA por data.
  for (const linha of document.querySelectorAll('tr, [role=row], li')) {
    if (linha.querySelector('tr, [role=row]')) continue;
    const texto = corta(linha.innerText, 400);
    const m = texto.match(comecaPorData);
    if (!m) continue;
    guardarMovimento(m[1], m[2],
                     texto.slice(m[0].length).replace(/^[\s\-|]+/, ''),
                     'linha que comeca por data');
  }

  // Segunda passada: a data esta em ALGUMA celula, nao necessariamente na
  // primeira. Em 13/10/2026 a tela do processo do Portal de Servicos devolveu
  // quatro tabelas e nenhuma movimentacao pela primeira regra, e coluna de
  // sequencia antes da data e arranjo comum. A origem fica gravada em cada
  // movimento para que ninguem precise adivinhar de onde ele veio.
  for (const linha of document.querySelectorAll('tr')) {
    if (linha.querySelector('tr')) continue;
    const celulas = Array.from(linha.children);
    if (celulas.length < 2) continue;
    let data = '', hora = '', posicao = -1;
    for (let i = 0; i < celulas.length; i++) {
      const m = corta(celulas[i].innerText, 40).match(soData);
      if (m) { data = m[1]; hora = m[2] || ''; posicao = i; break; }
    }
    if (!data) continue;
    let descricao = '';
    for (let i = 0; i < celulas.length; i++) {
      if (i === posicao) continue;
      const t = corta(celulas[i].innerText, 300);
      if (t.length > descricao.length) descricao = t;
    }
    const dona = linha.closest('table');
    const nome = dona ? (dona.id || corta(dona.className, 30) || 'sem id') : 'sem tabela';
    // O cabecalho vai junto porque e ele que denuncia a tabela errada. Em
    // 13/10/2026 esta segunda passada achou UMA "movimentacao" que vinha, na
    // verdade, do Historico de Mandados, e sem o cabecalho na origem isso
    // passaria por andamento do processo.
    let cabecalho = '';
    if (dona) {
      const topo = dona.querySelector('tr');
      const celulas = topo ? Array.from(topo.children) : [];
      if (celulas.length > 0 && celulas.every(c => c.tagName === 'TH')) {
        cabecalho = ' [' + celulas.map(c => corta(c.innerText, 30)).join(' | ') + ']';
      }
    }
    guardarMovimento(data, hora, descricao,
                     'celula de data na tabela ' + nome + cabecalho);
  }

  // Terceira passada: o movimento desta tela NAO e linha de tabela, e sim um
  // BLOCO DE ROTULOS. Lido na estrutura real em 13/10/2026, depois do clique
  // em "Todos Os Movimentos": "Data da juntada:" e "Descricao da Juntada:"
  // passaram de 1 para 4 ocorrencias, "Data:" e "Descricao:" apareceram 3
  // vezes cada, e os titulos "Descricao Detalhada" passaram de 2 para 11.
  //
  // Os rotulos sao lidos NA ORDEM DO DOCUMENTO, e um movimento termina quando
  // um rotulo que ele ja tem reaparece. Isso nao depende de saber como a tela
  // agrupa os blocos, que e justamente o que eu nao sei.
  // Onde comeca o PROXIMO rotulo de movimento dentro de um texto. Serve para
  // nao entregar, como valor de um rotulo, o rotulo seguinte e o valor dele
  // junto: no texto do bloco inteiro eles vem colados.
  const PROXIMO_ROTULO =
    /(data(?:\s+d[ao]\s+[a-z]+)?|descricao(?:\s+da\s+juntada)?|tipo\s+do\s+movimento)\s*:/;
  const ateOProximoRotulo = (valor) => {
    const achado = PROXIMO_ROTULO.exec(semAcento(valor));
    if (!achado || achado.index <= 0) return valor;
    // `semAcento` nao muda o comprimento dos acentos latinos, entao a posicao
    // achada na copia sem acento vale na original.
    return corta(valor.slice(0, achado.index), 300);
  };

  // O valor de um rotulo, por quatro caminhos. A primeira versao tinha so os
  // dois primeiros e devolvia vazio na tela real: o valor nao era elemento
  // irmao, e o texto do pai nao COMECA pelo rotulo, porque o titulo
  // "Descricao Detalhada" vem antes dele dentro do mesmo bloco.
  const textoApos = (no, parar) => {
    let seguinte = no.nextSibling;
    while (seguinte) {
      if (seguinte.nodeType === 1) {
        if (parar && seguinte.tagName === 'LABEL') break;
        const t = corta(seguinte.innerText || seguinte.textContent, 300);
        if (t) return t;
      } else if (seguinte.nodeType === 3) {
        const t = corta(seguinte.textContent, 300);
        if (t) return t;
      }
      seguinte = seguinte.nextSibling;
    }
    return '';
  };

  const valorDoRotulo = (rot) => {
    // 1. O que vem logo depois do rotulo, inclusive texto solto.
    const direto = textoApos(rot, true);
    if (direto) return ateOProximoRotulo(direto);

    // 2. O campo que o rotulo aponta com `for`.
    const para = rot.getAttribute('for');
    if (para) {
      try {
        const campo = document.getElementById(para);
        if (campo && campo !== rot) {
          const t = corta(campo.value || campo.innerText || '', 300);
          if (t) return ateOProximoRotulo(t);
        }
      } catch (e) { /* identificador invalido como seletor */ }
    }

    const pai = rot.parentElement;
    if (!pai) return '';

    // 3. O texto do pai DEPOIS do rotulo, onde quer que ele esteja.
    const todo = corta(pai.innerText, 600);
    const so = corta(rot.innerText, 60);
    const onde = todo.indexOf(so);
    if (onde >= 0) {
      const resto = corta(todo.slice(onde + so.length), 300);
      if (resto) return ateOProximoRotulo(resto);
    }

    // 4. O rotulo sozinho numa caixa, com o valor na caixa seguinte.
    const tio = textoApos(pai, false);
    return tio ? ateOProximoRotulo(tio) : '';
  };

  const chaveDoRotulo = (rot) =>
    semAcento(corta(rot.innerText, 60)).replace(/:$/, '').trim();
  // O bloco de um rotulo e o MENOR ancestral que contem data E descricao.
  //
  // Pedir so a descricao nao servia, e o defeito era silencioso: numa tela que
  // poe cada rotulo na sua propria caixa, a caixa da descricao ja basta por si
  // e a da data nao, entao data e descricao do MESMO movimento caiam em blocos
  // diferentes e nenhum dos dois virava movimentacao. Exigir os dois torna o
  // bloco o mesmo para os dois rotulos.
  const temRotuloDe = (no, chaves) => Array.from(no.querySelectorAll('label'))
    .some(l => chaves.indexOf(chaveDoRotulo(l)) >= 0);
  const blocoDe = (rot) => {
    let no = rot.parentElement;
    for (let i = 0; i < 10 && no; i++) {
      if (temRotuloDe(no, ROTULOS_DE_DATA) && temRotuloDe(no, ROTULOS_DE_DESCRICAO)) {
        return no;
      }
      no = no.parentElement;
    }
    return null;
  };

  const blocos = [];
  let rotulosDeMovimento = 0;
  let atual = null;
  let donoAtual = null;
  for (const rot of document.querySelectorAll('label')) {
    const chave = chaveDoRotulo(rot);
    if (ROTULOS_DE_MOVIMENTO.indexOf(chave) < 0) continue;
    rotulosDeMovimento += 1;
    const dono = blocoDe(rot);
    const ehDescricao = ROTULOS_DE_DESCRICAO.indexOf(chave) >= 0;
    const jaTemDescricao = atual !== null &&
      ROTULOS_DE_DESCRICAO.some(c => atual[c] !== undefined);
    // Tres motivos para comecar outro movimento, e qualquer um basta: mudou o
    // bloco na tela, o rotulo repetiu, ou chegou a segunda descricao. Os dois
    // ultimos cobrem a tela que poe tudo num container so, onde o primeiro
    // nao separaria nada.
    if (atual === null || dono !== donoAtual || atual[chave] !== undefined ||
        (ehDescricao && jaTemDescricao)) {
      atual = {};
      donoAtual = dono;
      blocos.push(atual);
    }
    atual[chave] = valorDoRotulo(rot);
  }

  for (const bloco of blocos) {
    let data = '', hora = '';
    for (const chave of ROTULOS_DE_DATA) {
      const m = (bloco[chave] || '').match(comecaPorData);
      if (m) { data = m[1]; hora = m[2] || ''; break; }
    }
    let descricao = '';
    for (const chave of ROTULOS_DE_DESCRICAO) {
      if (bloco[chave]) { descricao = bloco[chave]; break; }
    }
    if (!descricao && bloco['tipo do movimento']) {
      descricao = bloco['tipo do movimento'];
    }
    guardarMovimento(data, hora, descricao, 'bloco de rotulos da tela');
  }

  // O DIAGNOSTICO da leitura dos blocos. Em 13/10/2026 a leitura devolveu uma
  // movimentacao so e o terminal nao sabia dizer onde ela tinha parado: se nao
  // achou rotulo, se nao formou bloco, ou se formou bloco com valor vazio. Sao
  // tres defeitos diferentes com tres consertos diferentes.
  //
  // Vai so a CHAVE de cada rotulo, que e vocabulario da tela, e se o valor
  // ficou vazio, que e um sim ou nao. O valor em si nao entra aqui.
  const diagnostico = {
    rotulos_de_movimento_na_tela: rotulosDeMovimento,
    blocos_formados: blocos.length,
    descartadas_sem_data: descartes.sem_data,
    descartadas_sem_descricao: descartes.sem_descricao,
    descartadas_por_repetir: descartes.repetidas,
    chaves_por_bloco: blocos.slice(0, 8).map(b => Object.keys(b)),
    chaves_sem_valor_por_bloco: blocos.slice(0, 8)
      .map(b => Object.keys(b).filter(k => !b[k])),
  };

  // O MOVIMENTO desta tela e um `<app-movimento>`.
  //
  // Lido na estrutura real em 13/10/2026, dentro de `div#movimentacaoProcessoC`:
  //
  //   div.row.mt-4                     x10
  //     div.col-12.ng-tns-...          x10
  //       app-movimento.ng-tns-...     x10
  //   p-paginator.p-element            x1
  //   folhas que comecam por data      10
  //
  // Dez componentes, dez folhas com data, e um paginador. Este e o primeiro
  // trecho da leitura de movimento que nao e generico: o nome do componente
  // veio da tela de verdade, e nao de suposicao sobre como ela seria.
  //
  // Quando ha `app-movimento` na tela, SO ele vale. As tres passadas genericas
  // continuam para a tela que nao tiver nenhum, mas aqui elas so trariam de
  // volta o que ja esta nos componentes, em pedacos e fora de ordem.
  const componentes = document.querySelectorAll('app-movimento');
  const movimentosDoComponente = [];
  for (const item of componentes) {
    let data = '', hora = '', descricao = '';
    const folhasDoItem = [];
    for (const no of item.querySelectorAll('*')) {
      if (no.children.length > 0) continue;
      const t = corta(no.innerText || no.textContent, 300);
      if (t) folhasDoItem.push(t);
    }
    for (const t of folhasDoItem) {
      const m = t.match(comecaPorData);
      if (m && !data) { data = m[1]; hora = m[2] || ''; continue; }
      // A descricao e a folha mais longa que nao e a data nem um rotulo.
      if (/:$/.test(t)) continue;
      if (t.length > descricao.length) descricao = t;
    }
    movimentosDoComponente.push([data, hora, descricao, 'app-movimento']);
  }

  // O ESQUELETO das caixas de movimentacao.
  //
  // Em 13/10/2026 o clique em "Todos Os Movimentos" fez surgir
  // `div#movimentacaoProcessoC` e `input#buscarMovimentacaoN`, e a leitura
  // continuou achando tres movimentacoes. Onze blocos se formaram, nenhum sem
  // valor, e oito foram descartados. A lista de verdade esta nessa caixa, numa
  // forma que esta leitura nao reconhece: nem tabela, nem linha que comeca por
  // data, nem bloco de rotulo.
  //
  // Isto aqui nao le a lista: descreve a FORMA dela. Marcador e classe, com
  // contagem por nivel, e quantas folhas tem texto comecando por data. Nenhum
  // texto sai daqui.
  const assinatura = (e) => {
    const classe = (typeof e.className === 'string' ? e.className : '');
    const partes = corta(classe, 60).split(' ').filter(Boolean).slice(0, 2);
    return e.tagName.toLowerCase() + (partes.length ? '.' + partes.join('.') : '');
  };

  const caixasDeMovimentacao = [];
  for (const e of document.querySelectorAll('[id]')) {
    if (semAcento(e.id).indexOf('movimentacao') < 0) continue;
    if (caixasDeMovimentacao.length >= 3) break;

    const niveis = [];
    let nivel = [e];
    for (let d = 0; d < 4 && nivel.length; d++) {
      const grupos = {};
      const proximo = [];
      for (const no of nivel) {
        for (const filho of Array.from(no.children)) {
          const a = assinatura(filho);
          grupos[a] = (grupos[a] || 0) + 1;
          proximo.push(filho);
        }
      }
      if (Object.keys(grupos).length === 0) break;
      niveis.push(grupos);
      nivel = proximo.slice(0, 300);
    }

    let folhasComData = 0;
    let folhasComTexto = 0;
    for (const no of Array.from(e.querySelectorAll('*')).slice(0, 2000)) {
      if (no.children.length > 0) continue;
      const t = corta(no.innerText || no.textContent, 60);
      if (!t) continue;
      folhasComTexto += 1;
      if (comecaPorData.test(t)) folhasComData += 1;
    }

    caixasDeMovimentacao.push([
      e.id.replace(/\d+/g, 'N'), assinatura(e), niveis,
      folhasComTexto, folhasComData,
    ]);
  }

  // A ESTRUTURA das tabelas, para apertar esta leitura contra a tela real. Vai
  // junto o cabecalho de cada uma, que e vocabulario da TELA e nao dado de
  // processo, e a contagem de linhas com data por coluna, que e so numero.
  const tabelas = [];
  for (const t of Array.from(document.querySelectorAll('table')).slice(0, 40)) {
    const linhas = Array.from(t.querySelectorAll('tr'));
    const primeira = linhas[0];
    // So e cabecalho quando TODAS as celulas da primeira linha sao TH. A
    // mesma regra que impede "Data" -> "Movimento" de virar rotulo e valor,
    // ao contrario. Sem ela, numa tabela de capa cuja primeira linha e
    // "Comarca:" / "Niteroi", o VALOR entrava no bloco de estrutura, que e
    // justamente o bloco feito para poder ser mostrado a terceiros.
    const celulasDaPrimeira = primeira ? Array.from(primeira.children) : [];
    const soCabecalho = celulasDaPrimeira.length > 0 &&
      celulasDaPrimeira.every(c => c.tagName === 'TH');
    const cabecalhos = soCabecalho
      ? celulasDaPrimeira.map(c => corta(c.innerText, 40))
      : [];
    const datasPorColuna = {};
    for (const linha of linhas) {
      const celulas = Array.from(linha.children);
      for (let i = 0; i < celulas.length; i++) {
        if (soData.test(corta(celulas[i].innerText, 40))) {
          datasPorColuna[i] = (datasPorColuna[i] || 0) + 1;
        }
      }
    }
    tabelas.push([t.id || '', corta(t.className, 45), linhas.length,
                  celulasDaPrimeira.length, cabecalhos, datasPorColuna]);
  }

  // O vocabulario de rotulos da tela: folha de texto terminada em dois pontos.
  // Rotulo e nome de campo, da TELA; o valor fica do lado de fora disto.
  const rotulosCandidatos = [];
  const rotulosVistos = new Set();
  for (const e of folhas) {
    if (e.children.length > 0) continue;
    if (!visivel(e)) continue;
    const t = corta(e.innerText, 60);
    if (!/:$/.test(t)) continue;
    if (rotulosVistos.has(t)) continue;
    rotulosVistos.add(t);
    rotulosCandidatos.push(t);
    if (rotulosCandidatos.length >= 80) break;
  }

  // As SECOES da tela, pelos titulos. Lido na estrutura real em 13/10/2026:
  // esta tela tem "Descricao Detalhada", "Todos os Personagens", "Historico de
  // Mandados" e "Peticoes Pendentes", e NENHUMA tabela de andamentos. Saber em
  // que secao o que se procura mora, ou que ele nao esta ali, vale mais do que
  // qualquer regra nova de leitura.
  const secoes = [];
  for (const e of document.querySelectorAll('h1, h2, h3, h4, h5, h6')) {
    const t = corta(e.innerText, 60);
    if (!t) continue;
    secoes.push([e.tagName.toLowerCase(), t]);
    if (secoes.length >= 40) break;
  }

  // Os BOTOES da tela, agrupados pelo texto visivel. A mesma regra do relato de
  // tela: controle que se repete aos montes e item de lista, e o rotulo dele e
  // conteudo do processo, entao vira contagem sem rotulo nenhum.
  const porTexto = {};
  for (const e of document.querySelectorAll(
      'button, a[role=button], input[type=submit], input[type=button], [role=tab]')) {
    if (!visivel(e)) continue;
    const t = corta(e.innerText || e.value || '', 50);
    const rotulo = corta(e.getAttribute('aria-label') || e.getAttribute('title') || '', 50);
    if (!porTexto[t]) porTexto[t] = [];
    porTexto[t].push(rotulo);
  }
  const botoes = [];
  for (const t of Object.keys(porTexto)) {
    const rotulos = porTexto[t];
    botoes.push(rotulos.length > 2 ? [t, rotulos.length, []]
                                   : [t, rotulos.length, rotulos]);
    if (botoes.length >= 60) break;
  }

  const familias = {};
  for (const e of document.querySelectorAll('[id]')) {
    const marcador = e.tagName.toLowerCase();
    if (['script', 'style', 'link', 'meta'].indexOf(marcador) >= 0) continue;
    const nome = marcador + '#' + e.id.replace(/\d+/g, 'N');
    familias[nome] = (familias[nome] || 0) + 1;
  }

  return {pares: pares, partes: partes, movimentacoes: movimentacoes,
          tabelas: tabelas, familias: familias,
          rotulosCandidatos: rotulosCandidatos,
          secoes: secoes, botoes: botoes, diagnostico: diagnostico,
          caixasDeMovimentacao: caixasDeMovimentacao,
          movimentosDoComponente: movimentosDoComponente};
}
"""


def _sem_dado(texto: Any) -> str:
    """Segunda rede sobre tudo que entra no bloco de ESTRUTURA.

    O bloco existe para poder ser mostrado a terceiros, e por isso nao pode
    carregar dado de processo. Nao basta escolher bem o que entra: na tela real
    do Portal de Servicos, lida em 13/10/2026, o titulo de secao e "Processo n.
    <numero>", entao o proprio vocabulario da tela traz o numero do processo
    dentro dele.
    """
    from .portal import sem_dado_de_processo

    return sem_dado_de_processo(str(texto or ""))


def _caixas(bruto: Any) -> list:
    """A FORMA das caixas de movimentacao, sem nenhum texto delas.

    Marcador e classe, com contagem por nivel, e quantas folhas tem texto
    comecando por data. E por aqui que se descobre em que forma a lista esta,
    quando ela nao e tabela nem linha nem bloco de rotulo.
    """
    saida = []
    for item in bruto or []:
        try:
            saida.append({
                "id": _sem_dado(item[0]),
                "assinatura": _sem_dado(item[1]),
                "por_nivel": [{str(k): int(v) for k, v in (nivel or {}).items()}
                              for nivel in (item[2] or [])],
                "folhas_com_texto": int(item[3]),
                "folhas_que_comecam_por_data": int(item[4]),
            })
        except Exception:
            continue
    return saida


def _diagnostico(bruto: Any) -> dict:
    """Onde a leitura dos blocos de movimento parou, em numeros e em chaves.

    Nao achar rotulo, nao formar bloco e formar bloco com valor vazio sao tres
    defeitos diferentes, com tres consertos diferentes. Sem isto o terminal
    dizia so "uma movimentacao" e nao dava para saber qual dos tres era.
    """
    if not isinstance(bruto, dict):
        return {"rotulos_de_movimento_na_tela": 0, "blocos_formados": 0,
                "descartadas_sem_data": 0, "descartadas_sem_descricao": 0,
                "descartadas_por_repetir": 0,
                "chaves_por_bloco": [], "chaves_sem_valor_por_bloco": []}
    return {
        "rotulos_de_movimento_na_tela":
            int(bruto.get("rotulos_de_movimento_na_tela") or 0),
        "blocos_formados": int(bruto.get("blocos_formados") or 0),
        "descartadas_sem_data": int(bruto.get("descartadas_sem_data") or 0),
        "descartadas_sem_descricao":
            int(bruto.get("descartadas_sem_descricao") or 0),
        "descartadas_por_repetir": int(bruto.get("descartadas_por_repetir") or 0),
        "chaves_por_bloco": [[_sem_dado(c) for c in bloco]
                             for bloco in (bruto.get("chaves_por_bloco") or [])],
        "chaves_sem_valor_por_bloco":
            [[_sem_dado(c) for c in bloco]
             for bloco in (bruto.get("chaves_sem_valor_por_bloco") or [])],
    }


def _leitura_vazia(falha: Optional[str] = None) -> dict:
    """O mesmo formato, quando nao houve o que ler. Nunca um dicionario torto.

    Quem consome nao pode ter de descobrir se a leitura falhou olhando se a
    chave existe: a forma e sempre a mesma, e a falha vem dita.
    """
    return {
        "principais": {},
        "partes": [],
        "movimentacoes": [],
        "estrutura": {"tabelas": [], "familias": {}, "rotulos_candidatos": [],
                      "secoes": [], "botoes": [], "rotulos_lidos": [],
                      "diagnostico_dos_blocos": _diagnostico(None),
                      "caixas_de_movimentacao": [],
                      "componentes_de_movimento": 0},
        "leitura": {
            "metodo": "generica",
            "confirmada_em_tela_real": False,
            # Coisa diferente da linha acima, e as duas precisam existir. A de
            # cima diz que a REGRA de leitura nunca foi conferida contra a tela
            # real. Esta diz se a tela lida era mesmo a do processo, e nao o
            # formulario de busca que fica no mesmo lugar.
            "tela_do_processo_confirmada": None,
            "endereco_do_quadro": None,
            "aviso": AVISO_DA_LEITURA,
            "falha": falha,
        },
        "totais": {"principais": 0, "partes": 0, "movimentacoes": 0},
    }


def extrair(quadro: Any) -> dict:
    """Le a tela do processo do Portal de Servicos, pela estrutura da pagina.

    Devolve o mesmo formato do e-SAJ no que da para comparar (`principais`,
    `movimentacoes`, `totais`), mais a `estrutura` da tela, que nao tem
    conteudo nenhum e serve para apertar esta leitura depois.

    O campo `leitura` diz, dentro do proprio arquivo, que isto nao foi
    conferido em tela real. Quem abrir o arquivo daqui a seis meses nao tem
    como saber disso de outro jeito.
    """
    try:
        bruto = quadro.evaluate(JS_DA_TELA_DO_PROCESSO)
    except Exception as exc:
        return _leitura_vazia(f"{type(exc).__name__}: {exc}")
    if not isinstance(bruto, dict):
        return _leitura_vazia("a tela devolveu algo que nao e leitura")

    principais: dict = {}
    for item in bruto.get("pares") or []:
        try:
            rotulo, valor = str(item[0]), str(item[1])
        except Exception:
            continue
        # O primeiro valor de cada rotulo ganha: numa tela montada por script,
        # o mesmo rotulo costuma reaparecer em rodape e em caixa escondida.
        principais.setdefault(rotulo, valor)

    # Quando a tela traz `<app-movimento>`, e ele que manda: cada componente e
    # um movimento, na ordem da tela, sem juntar nem descartar repetido. Dois
    # andamentos do mesmo dia com a mesma descricao existem, e a deduplicacao
    # das passadas genericas apagaria o segundo.
    do_componente = bruto.get("movimentosDoComponente") or []
    fonte = do_componente if do_componente else (bruto.get("movimentacoes") or [])

    movimentacoes = []
    for item in fonte:
        try:
            movimentacoes.append({
                "data": str(item[0]), "hora": str(item[1]),
                "descricao": str(item[2]),
                # De onde o movimento veio. Duas regras diferentes acham
                # linhas diferentes, e quem conferir o arquivo nao pode ter de
                # adivinhar qual delas achou cada uma.
                "origem": str(item[3]) if len(item) > 3 else "",
            })
        except Exception:
            continue

    tabelas = []
    for item in bruto.get("tabelas") or []:
        try:
            tabelas.append({
                "id": str(item[0]), "classe": str(item[1]),
                "linhas": int(item[2]), "colunas": int(item[3]),
                "cabecalhos": [str(c) for c in (item[4] if len(item) > 4 else [])],
                "linhas_com_data_por_coluna": {
                    str(k): int(v) for k, v in
                    (item[5] if len(item) > 5 else {}).items()},
            })
        except Exception:
            continue

    partes = []
    for item in bruto.get("partes") or []:
        try:
            partes.append({"tipo": str(item[0]), "nome": str(item[1])})
        except Exception:
            continue

    saida = _leitura_vazia()
    saida["principais"] = principais
    saida["partes"] = partes
    saida["movimentacoes"] = movimentacoes
    saida["estrutura"] = {
        "tabelas": tabelas,
        "familias": dict(bruto.get("familias") or {}),
        # Vocabulario de rotulos da TELA, nao valor de campo: folha de texto
        # terminada em dois pontos. E por ele que se ve como a capa esta
        # montada quando a leitura generica acha pouco.
        "rotulos_candidatos": [_sem_dado(r) for r in
                               (bruto.get("rotulosCandidatos") or [])],
        "secoes": [{"nivel": str(s[0]), "titulo": _sem_dado(s[1])}
                   for s in (bruto.get("secoes") or []) if len(s) > 1],
        "botoes": [{"texto": _sem_dado(b[0]), "quantas": int(b[1]),
                    "rotulos": [_sem_dado(r) for r in (b[2] if len(b) > 2 else [])]}
                   for b in (bruto.get("botoes") or []) if len(b) > 1],
        # So as CHAVES do que foi lido. O valor e dado de processo e fica fora
        # deste bloco, que existe para poder ser mostrado.
        "rotulos_lidos": sorted(_sem_dado(r) for r in principais),
        "diagnostico_dos_blocos": _diagnostico(bruto.get("diagnostico")),
        "caixas_de_movimentacao": _caixas(bruto.get("caixasDeMovimentacao")),
        "componentes_de_movimento": len(do_componente),
    }
    saida["totais"] = {"principais": len(principais),
                       "partes": len(partes),
                       "movimentacoes": len(movimentacoes)}
    return saida


# O botao que carrega o historico, lido na tela real em 13/10/2026.
#
# A tela do processo mostra UM movimento, o ultimo, com os rotulos "Data da
# juntada:", "Descricao da Juntada:" e "Tipo do Movimento". Por isso a leitura
# achava uma movimentacao so, e a que achava vinha, na verdade, do Historico de
# Mandados. O resto do historico esta atras deste botao.
BOTAO_TODOS_OS_MOVIMENTOS = "Todos Os Movimentos"

# Quantas leituras seguidas sem crescer bastam para dizer que a tela parou de
# montar. Tres segundos parados, com leitura a cada segundo.
LEITURAS_ESTAVEIS = 3


def mostrar_todos_os_movimentos(quadro: Any, guarda: Any,
                                segundos: int = 45) -> dict:
    """Clica em "Todos Os Movimentos" e espera o historico chegar.

    Somente leitura: o botao troca o que a tela MOSTRA, nao toca em nada do
    processo. E o mesmo ato que o e-SAJ ja fazia desde 22/09/2026 com "exibir
    mais movimentacoes", e pela mesma razao: entregar o pedaco como se fosse o
    todo faria o advogado concluir que nao ha andamento anterior.

    A prova de que funcionou nao e o clique, e sim a CONTAGEM crescer. Devolve
    o que aconteceu, para ir ao arquivo e ao terminal.
    """
    import time as _tempo

    from .core.guarda_navegacao import Acao, Permissao
    from .portal import elemento_visivel, permissao_efemera

    antes = len(extrair(quadro).get("movimentacoes") or [])
    alvo = f"texto={BOTAO_TODOS_OS_MOVIMENTOS}"
    botao = elemento_visivel(quadro, alvo)
    if botao is None:
        return {"situacao": f"o botao {BOTAO_TODOS_OS_MOVIMENTOS!r} nao esta na "
                            "tela; o historico pode estar incompleto",
                "antes": antes, "depois": antes}

    endereco = getattr(quadro, "url", "") or ""
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(endereco).padrao_url,
        descricao="mostrar todos os movimentos do processo, somente leitura",
        conferido_em="execucao atual",
        seletores_clicaveis=(alvo,),
    ))
    guarda.pode_executar(Acao.CLICAR, alvo, url=endereco)
    clicar_com_jeito(botao)

    # Esperar ate PARAR de crescer, e nao ate crescer pela primeira vez.
    #
    # Em 13/10/2026 esta espera devolveu "clicado, 2 -> 3" e saiu. A tela ainda
    # estava montando: o portal escreve os movimentos um apos o outro, e sair
    # na primeira mudanca entrega tres de um historico que tem muito mais.
    # Parar cedo demais aqui e o mesmo erro de entregar o pedaco como se fosse
    # o todo, so que disfarcado de sucesso.
    limite = _tempo.monotonic() + max(1, segundos)
    depois = antes
    estaveis = 0
    while _tempo.monotonic() < limite:
        try:
            quadro.wait_for_timeout(1000)
        except Exception:
            _tempo.sleep(1)
        agora = len(extrair(quadro).get("movimentacoes") or [])
        if agora > depois:
            depois = agora
            estaveis = 0
            continue
        if depois > antes:
            estaveis += 1
            if estaveis >= LEITURAS_ESTAVEIS:
                break

    if depois > antes:
        parou = ("a contagem parou de crescer" if estaveis >= LEITURAS_ESTAVEIS
                 else f"o prazo de {segundos}s acabou com ela ainda crescendo")
        return {"situacao": f"clicado, {antes} -> {depois} movimentacao(oes), "
                            f"{parou}",
                "antes": antes, "depois": depois}
    return {"situacao": f"clicado, e a contagem nao mudou ({antes}). O "
                        "historico pode estar incompleto",
            "antes": antes, "depois": depois}


# A paginacao dos movimentos, lida na estrutura real em 13/10/2026.
#
# Dentro de `div#movimentacaoProcessoC` ha dez `app-movimento` e um
# `p-paginator.p-element`. Os botoes "1", "2" e "3" que apareciam no relato
# eram isso, e agora e leitura de tela, nao suposicao.
SELETOR_DA_PAGINA = ".p-paginator-page"
TETO_DE_PAGINAS = 60


def _paginas_na_tela(quadro: Any) -> list:
    """Os botoes de pagina, como pares (numero, elemento), na ordem."""
    saida = []
    try:
        botoes = quadro.query_selector_all(SELETOR_DA_PAGINA) or []
    except Exception:
        return []
    for botao in botoes:
        try:
            escrito = (botao.inner_text() or "").strip()
        except Exception:
            continue
        if escrito.isdigit():
            saida.append((int(escrito), botao))
    return sorted(saida, key=lambda par: par[0])


def _assinatura_da_pagina(movimentos: list) -> tuple:
    """O que identifica a PAGINA, para saber se ela trocou.

    Serve so para isso. Nao serve para descartar movimento: dois andamentos do
    mesmo dia com a mesma descricao existem, e em 13/10/2026 este programa
    leu 207 componentes e gravou 201, porque usava a mesma chave para as duas
    coisas. Seis andamentos foram perdidos em silencio.
    """
    return tuple((m.get("data"), m.get("hora"), m.get("descricao"))
                 for m in movimentos or [])


def percorrer_as_paginas_de_movimentos(quadro: Any, guarda: Any,
                                       segundos: int = 45,
                                       teto: int = TETO_DE_PAGINAS) -> dict:
    """Visita cada pagina de movimentos e junta TUDO, na ordem.

    Somente leitura: paginar troca o que a tela MOSTRA. A prova de que a
    pagina virou e a lista inteira ficar DIFERENTE da anterior e parar de
    mudar; a partir dai tudo o que esta nela entra, repetido ou nao, porque
    repetido aqui e andamento de verdade.

    Devolve a lista acumulada e o que aconteceu, para ir ao arquivo e ao
    terminal. Pagina que nao chega e pior do que pagina que falta: o advogado
    precisa saber que o historico pode estar incompleto.
    """
    import time as _tempo

    from .core.guarda_navegacao import Acao, Permissao
    from .portal import permissao_efemera

    def ler() -> list:
        return list(extrair(quadro).get("movimentacoes") or [])

    pagina_atual = ler()
    acumulado: list = list(pagina_atual)
    assinatura = _assinatura_da_pagina(pagina_atual)

    paginas = _paginas_na_tela(quadro)
    if not paginas:
        return {"situacao": "a tela nao tem paginacao de movimentos",
                "paginas": 1, "movimentacoes": acumulado}

    endereco = getattr(quadro, "url", "") or ""
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(endereco).padrao_url,
        descricao="percorrer as paginas de movimentacao, somente leitura",
        conferido_em="execucao atual",
        seletores_clicaveis=(SELETOR_DA_PAGINA,),
    ))

    visitadas = {paginas[0][0]}
    percorridas = 1
    parou_por = "nao havia mais pagina"
    while percorridas < teto:
        alvo = None
        for numero, botao in _paginas_na_tela(quadro):
            if numero not in visitadas:
                alvo = (numero, botao)
                break
        if alvo is None:
            break
        numero, botao = alvo
        visitadas.add(numero)
        guarda.pode_executar(Acao.CLICAR, SELETOR_DA_PAGINA, url=endereco)
        try:
            clicar_com_jeito(botao)
        except Exception:
            parou_por = f"a pagina {numero} nao aceitou o clique"
            break

        # Esperar a pagina VIRAR, e depois parar de mudar. Aceitar a primeira
        # leitura diferente pegaria a tela no meio da troca.
        limite = _tempo.monotonic() + max(1, segundos)
        ultima: Optional[list] = None
        estaveis = 0
        nova: Optional[list] = None
        while _tempo.monotonic() < limite:
            try:
                quadro.wait_for_timeout(1000)
            except Exception:
                _tempo.sleep(1)
            lida = ler()
            marca = _assinatura_da_pagina(lida)
            if marca == assinatura:
                continue
            if ultima is not None and marca == _assinatura_da_pagina(ultima):
                estaveis += 1
                if estaveis >= LEITURAS_ESTAVEIS:
                    nova = lida
                    break
            else:
                ultima = lida
                estaveis = 0
        if nova is None:
            parou_por = (f"a pagina {numero} nao chegou em {segundos}s; o "
                         "historico pode estar incompleto")
            break

        acumulado.extend(nova)
        assinatura = _assinatura_da_pagina(nova)
        percorridas += 1

    if percorridas >= teto:
        parou_por = f"o teto de {teto} paginas foi atingido"

    # VOLTAR para a primeira pagina, e subir a tela.
    #
    # Em 13/10/2026 esta funcao deixou a tela na pagina 21 e a etapa seguinte,
    # que abre o Visualizador, nao achou mais o botao dela: o relato mostrou so
    # os botoes '19', '20' e '21'. Quem pagina tem de devolver a tela como a
    # encontrou, senao conserta a leitura e quebra o download.
    volta = _voltar_ao_comeco(quadro, guarda, endereco, paginas[0][0], segundos)
    return {"situacao": f"{percorridas} pagina(s), {parou_por}; {volta}",
            "paginas": percorridas, "movimentacoes": acumulado}


def _voltar_ao_comeco(quadro: Any, guarda: Any, endereco: str, primeira: int,
                      segundos: int) -> str:
    """Devolve a tela a primeira pagina e ao topo. Diz o que conseguiu."""
    import time as _tempo

    from .core.guarda_navegacao import Acao

    recado = "a tela continuou onde a paginacao parou"
    for numero, botao in _paginas_na_tela(quadro):
        if numero != primeira:
            continue
        try:
            guarda.pode_executar(Acao.CLICAR, SELETOR_DA_PAGINA, url=endereco)
            clicar_com_jeito(botao)
            recado = f"a tela voltou para a pagina {primeira}"
        except Exception:
            recado = f"a tela nao voltou para a pagina {primeira}"
        break

    limite = _tempo.monotonic() + max(1, min(segundos, 10))
    while _tempo.monotonic() < limite:
        try:
            quadro.wait_for_timeout(500)
        except Exception:
            _tempo.sleep(0.5)
        break
    try:
        quadro.evaluate("() => window.scrollTo(0, 0)")
    except Exception:
        pass
    return recado


def resumo_seguro(dados: dict) -> list:
    """O resumo que PODE ir ao terminal: contagem, e nada de conteudo.

    O e-SAJ imprime classe, assunto, foro e vara. Aqui nao. Esta tela e tela de
    processo, e a regra do advogado para ela e clara: resultado com dado de
    cliente vai para arquivo, nunca para o terminal nem para conversa. Contagem
    nao e dado de cliente; classe e assunto sao.
    """
    totais = dados.get("totais") or {}
    estrutura = dados.get("estrutura") or {}
    linhas = [
        f"rotulos lidos: {totais.get('principais', 0)}   "
        f"partes: {totais.get('partes', 0)}   "
        f"movimentacoes: {totais.get('movimentacoes', 0)}",
        f"componentes app-movimento: "
        f"{estrutura.get('componentes_de_movimento', 0)}   "
        f"tabelas na tela: {len(estrutura.get('tabelas') or [])}   "
        f"familias de identificador: {len(estrutura.get('familias') or {})}   "
        f"rotulos que a tela oferece: "
        f"{len(estrutura.get('rotulos_candidatos') or [])}",
    ]
    leitura = dados.get("leitura") or {}
    if leitura.get("tela_do_processo_confirmada") is False:
        linhas.append(
            "ATENCAO: a tela lida NAO foi confirmada como a do processo. O "
            "formulario de busca mora no mesmo quadro, e o que esta no arquivo "
            "pode ser ele. Endereco do quadro: "
            f"{leitura.get('endereco_do_quadro') or '(nao lido)'}")
    falha = leitura.get("falha")
    if falha:
        linhas.append(f"a leitura falhou: {falha}")
    historico = leitura.get("todos_os_movimentos")
    if historico:
        linhas.append(f"botao 'Todos Os Movimentos': {historico}")
    paginas = leitura.get("paginas_de_movimentacao")
    if paginas:
        linhas.append(f"paginas de movimentacao: {paginas}")
    if falha:
        pass
    elif not totais.get("principais") and not totais.get("movimentacoes"):
        linhas.append("nada foi lido desta tela. A estrutura dela esta no "
                      "arquivo, e e por ela que a leitura se aperta.")
    return linhas


def abrir_visualizador(pagina: Any, guarda: Any, segundos: int = 45,
                       motivo: Optional[str] = None) -> Any:
    """Clica em "Processo Eletronico - Visualizador" e devolve a JANELA NOVA.

    O visualizador abre em janela propria, com um endereco cifrado que nao se
    monta a partir do numero do processo: ele e gerado por este clique. Nao ha
    como pular esta etapa.

    Entre o clique e a janela pode entrar o formulario de justificativa, lido
    em campo em 08/10/2026. Nesse caso o motivo e digitado TECLA A TECLA, como
    o advogado pediu, e so entao o processo e aberto.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (elemento_visivel, endereco_sem_dado, pagina_de,
                         permissao_efemera)

    # ESPERANDO, e nao numa olhada so. Em 08/10/2026 esta etapa, que ja tinha
    # funcionado duas vezes, falhou com o quadro ainda em `#/consultaportal`
    # em vez de `#/consultar/detalhes-processo`: a busca tinha sido enviada e
    # a tela do processo ainda nao tinha chegado.
    #
    # E a mesma classe de defeito que ja apareceu na tela de login, na de
    # selecao de sistemas, no menu e no botao de enviar o perfil. Eu disse
    # mais de uma vez que ia generaliza-la, e aqui ela reapareceu numa funcao
    # que eu mesmo mexi no mesmo dia.
    quadro, botao = esperar_a_tela_do_processo(pagina, segundos)
    if botao is None:
        from .telas import gravar_a_tela

        gravar_a_tela(quadro, "recusa-botao-visualizador")
        raise ConsultaIndisponivel(
            f"O botao {BOTAO_VISUALIZADOR!r} nao apareceu na tela do processo "
            f"em {min(segundos, 30)}s. Endereco do quadro: "
            f"{endereco_sem_dado(getattr(quadro, 'url', '') or '(sem)', 80)}. "
            "Se ele ainda for a tela de busca, a pesquisa nao chegou a "
            "devolver o processo. Nada foi aberto.")

    alvo = f"texto={BOTAO_VISUALIZADOR}"
    alvo_do_visualizar = f"texto={BOTAO_VISUALIZAR_PROCESSO}"
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="abrir o Visualizador de Processos",
        conferido_em="execucao atual",
        seletores_clicaveis=(alvo, alvo_do_visualizar),
        # `#senhaProvisoria` NAO entra aqui, de proposito: a trava barra o
        # proprio programa se algum caminho futuro tentar preenche-la.
        seletores_preenchiveis=(CAMPO_DO_MOTIVO,),
    ))
    guarda.pode_executar(Acao.CLICAR, alvo, url=pagina.url)

    hospedeira = pagina_de(pagina)
    janela = _janela_do_clique(hospedeira, botao, min(segundos, 15))
    if janela is not None:
        return _assentar_a_janela(janela, segundos)

    # Sem janela nova: o portal pode ter pedido justificativa.
    quadro = quadro_da_consulta(pagina)
    campo = tela_de_justificativa(quadro)
    if campo is None:
        raise ConsultaIndisponivel(
            f"O visualizador nao abriu em {min(segundos, 15)}s, e a tela "
            f"tambem nao pediu justificativa ({CAMPO_DO_MOTIVO} nao esta "
            "nela). Nada foi lido.")

    texto = (motivo or "").strip()
    if not texto:
        raise MotivoNaoInformado(
            "O portal pediu o MOTIVO do acesso aos autos e nenhum foi "
            "informado. Declarar o motivo e ato do advogado, nao do programa. "
            "Repita o comando com --motivo.")

    print(f"    [JUSTIFICATIVA] O portal pediu motivo para abrir os autos.")
    print(f"    Digitando no campo {CAMPO_DO_MOTIVO}: {texto!r}")
    print("    Este texto fica registrado no portal como a justificativa do "
          "acesso.")
    guarda.pode_executar(Acao.PREENCHER, CAMPO_DO_MOTIVO, url=pagina.url)
    try:
        campo.click()
        campo.type(texto, delay=40)
    except Exception as exc:
        raise ConsultaIndisponivel(
            f"O campo {CAMPO_DO_MOTIVO} nao aceitou o texto "
            f"({type(exc).__name__}). Nada foi aberto.") from None

    senha = elemento_visivel(quadro, CAMPO_DA_SENHA_PROVISORIA)
    if senha is not None:
        print(f"    A tela tambem mostra {CAMPO_DA_SENHA_PROVISORIA} "
              "('Senha para visualizar o processo eletronico').")
        print("    Ela NAO sera preenchida: e credencial de acesso aos autos, "
              "e o programa nao a tem nem a inventa.")

    confirmar, criterio = achar_o_visualizar_processo(
        quadro, campo, min(segundos, 15))
    if confirmar is not None:
        print(f"    Botao {BOTAO_VISUALIZAR_PROCESSO!r} escolhido {criterio}.")
    if confirmar is None:
        raise ConsultaIndisponivel(
            f"O motivo foi digitado e o botao {BOTAO_VISUALIZAR_PROCESSO!r} "
            "nao esta na tela. Nada foi aberto."
            + "\n    CANDIDATOS AO BOTAO:\n    "
            + "\n    ".join(relato_dos_candidatos(
                quadro, BOTAO_VISUALIZAR_PROCESSO)))
    guarda.pode_executar(Acao.CLICAR, alvo_do_visualizar, url=pagina.url)
    janela = _janela_do_clique(hospedeira, confirmar, segundos)
    if janela is None:
        recados = _recados_do_quadro(quadro)
        raise ConsultaIndisponivel(
            f"O motivo foi digitado e {BOTAO_VISUALIZAR_PROCESSO!r} foi "
            f"clicado, e nenhuma janela abriu em {segundos}s. Nada foi lido."
            + (" O portal disse: " + "; ".join(recados) if recados
               else " O portal nao deixou mensagem na tela.")
            + (f" Se faltou {CAMPO_DA_SENHA_PROVISORIA}, ela e credencial e "
               "este programa nao a preenche." if senha is not None else ""))
    return _assentar_a_janela(janela, segundos)


# Aviso que o portal mostra em TODA tela de processo, e que nao e erro nenhum.
# Em 08/10/2026 ele saiu duas vezes dentro de uma recusa, depois de "O portal
# disse:", como se fosse a explicacao da falha. Dizer "o portal disse" sobre um
# rodape permanente e pior que nao dizer nada: manda procurar onde nao ha.
AVISOS_PERMANENTES = (
    "as informacoes aqui contidas nao produzem efeitos legais",
)


def _recados_do_quadro(quadro: Any) -> list[str]:
    """Mensagens que o portal deixou no quadro, para a recusa dizer o porque.

    Sem os avisos permanentes e sem repeticao: o mesmo texto sai uma vez.
    """
    from .portal import _mensagens_de_erro, sem_acento

    try:
        recados = _mensagens_de_erro(quadro)
    except Exception:
        return []
    saida, vistos = [], set()
    for recado in recados or []:
        limpo = sem_acento(recado)
        if any(marca in limpo for marca in AVISOS_PERMANENTES):
            continue
        if limpo in vistos:
            continue
        vistos.add(limpo)
        saida.append(recado)
    return saida


def _assentar_a_janela(janela: Any, segundos: int) -> Any:
    """Espera a janela nova carregar, e a traz PARA A FRENTE.

    A frente nao e detalhe. Esta escrito em `trazer_para_a_frente`, a partir do
    que o advogado observou em 06/10/2026: o Chromium nao desenha nem calcula
    posicao de aba que esta atras. O Visualizador abre em janela propria, monta
    o indice por script, e ate 14/10/2026 ninguem a trazia para a frente: a aba
    do portal era, esta nao.

    O indice de 164 documentos nao aparecia em 45s de espera, com a tela
    mostrando 12 botoes, e tres tentativas de autenticacao foram gastas nisso.
    """
    from .portal import AREA_DO_VISUALIZADOR, alargar_a_area

    trazer_para_a_frente(janela)
    # A LARGURA ENTRA AQUI, e so aqui. A consulta roda na area estreita em que
    # funcionou em 13/10/2026; alargar tudo, como fiz em 15/10, consertou a
    # gaveta do indice e quebrou a consulta. Esta e a unica tela que precisa de
    # largura: a gaveta do Angular Material fica ao lado em tela larga e vira
    # modo `over` em tela estreita, e em modo `over` o conteudo dela nao e
    # desenhado.
    if alargar_a_area(janela, AREA_DO_VISUALIZADOR):
        print(f"      Area da janela do Visualizador: "
              f"{AREA_DO_VISUALIZADOR['width']}x{AREA_DO_VISUALIZADOR['height']} "
              "(a gaveta do indice precisa de largura).")
    else:
        print("      [ATENCAO] Nao foi possivel alargar a area desta janela. "
              "Se o indice vier vazio, e aqui que a causa esta.")
    try:
        janela.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
    except Exception:
        pass
    # De novo depois de carregar: a propria carga pode devolver o foco para a
    # janela que abriu esta.
    frente = trazer_para_a_frente(janela)

    # `domcontentloaded` diz que o DOCUMENTO chegou, e nao que a aplicacao se
    # montou. Em 16/10/2026 a tela foi lida e gravada neste ponto com zero
    # controles: a gravacao de uma tela vazia nao serve para nada, e a recusa
    # seguinte culpou a barra por nao ter um botao que ainda nao existia.
    medida = esperar_o_visualizador_montar(frente or janela, segundos)
    print(f"      Visualizador montado: {medida['controles']} controle(s), "
          f"{medida['nos']} no(s).")
    from .telas import gravar_a_tela

    gravar_a_tela(frente or janela, "visualizador-recem-aberto")
    return frente


# ---------------------------------------------------------------------------
# Entrada no Portal de Servicos, pela tela de selecao de sistemas
#
# Conferido em campo em 06/10/2026: navegar DIRETO para a consulta nao
# funciona. O endereco `#/consproc/consultaportal` devolveu a pagina publica do
# tribunal, em `www.tjrj.jus.br`. A sessao do IdServerJus existe, e o Portal de
# Servicos so e alcancado pela entrega que este formulario faz.
# ---------------------------------------------------------------------------

TELA_DE_SELECAO = "/selecao-sistemas"
LISTA_DE_SISTEMAS = "#sistema"
ABRIR_EM_ABA = "#optionAba"
ABRIR_EM_JANELA = "#optionPopup"
BOTAO_ENVIAR = "Enviar"

# Como se reconhece que a sessao ja esta DENTRO do Portal de Servicos.
MARCA_DO_PORTAL = "/portalservicos"

SIGLA_DO_PORTAL = "PORTALSERVICOS"
NOME_DO_PORTAL = "portal de servicos"


def escolher_opcao_do_portal(lista: Any) -> Optional[str]:
    """O valor da opcao que leva ao Portal de Servicos, ou None.

    Casa primeiro pelo valor, que e a sigla, e so depois pelo texto. Exige
    UMA correspondencia: duas seriam escolha no escuro, e escolher o sistema
    errado leva a sessao para outro lugar sem dizer nada.
    """
    from .portal import sem_acento

    try:
        opcoes = lista.evaluate(
            "e => Array.from(e.options || []).map(o => [o.value, o.text])")
    except Exception:
        return None
    por_sigla = [v for v, _ in (opcoes or []) if (v or "").strip() == SIGLA_DO_PORTAL]
    if len(por_sigla) == 1:
        return por_sigla[0]
    por_nome = [v for v, t in (opcoes or [])
                if NOME_DO_PORTAL in sem_acento(t or "")]
    return por_nome[0] if len(por_nome) == 1 else None


# A RAIZ do portal e a rota que ele assume depois de montar. A diferenca entre
# as duas decidiu a corrida de 06/10/2026: o `expect_page` entregou uma janela
# em `/portalservicos/`, sem rota nenhuma, e ela foi embora para o site publico
# do tribunal enquanto o portal de verdade assumia `#/usuarios/alterar-perfil`
# em OUTRA janela, que o advogado estava vendo. O endereco conferia no instante
# em que foi olhado, e nao conferia um segundo depois.
MARCA_DE_ROTA_DO_PORTAL = "/portalservicos/#/"


def tem_rota_do_portal(url: Any) -> bool:
    """Se o endereco e uma ROTA do portal, e nao a raiz que ainda vai mudar."""
    return MARCA_DE_ROTA_DO_PORTAL in (url or "")


def _aba_do_portal_agora(abas: Any, exigir_rota: bool) -> Optional[Any]:
    """A aba do portal entre as recebidas, de tras para frente.

    De tras para frente porque janela nova e acrescentada ao fim da lista, e a
    aba de ORIGEM pode exibir o endereco do portal por um instante durante a
    entrega, antes de voltar para a pagina publica. Pegando a primeira, o
    programa ficava com a aba que ia embora.
    """
    for aba in reversed(list(abas or [])):
        try:
            endereco = aba.url or ""
        except Exception:
            continue
        if tem_rota_do_portal(endereco) if exigir_rota else (
                MARCA_DO_PORTAL in endereco):
            return aba
    return None


def achar_aba_do_portal(pagina: Any, segundos: int = 20) -> Optional[Any]:
    """A aba ou janela onde o Portal de Servicos abriu, se houver.

    A entrada no portal abre uma JANELA PROPRIA, e a aba de origem volta para a
    pagina publica do tribunal. Conferido em campo em 06/10/2026: o comando
    anunciava "a lista nao esta nela" com o endereco em `www.tjrj.jus.br`,
    enquanto o portal estava aberto e pedindo o tipo de usuario em outra
    janela, que o advogado estava vendo na tela.

    Procura em TODAS as abas do mesmo navegador, e espera, porque a janela leva
    um instante para aparecer e outro para assumir o endereco.

    Prefere a aba que ja ASSUMIU UMA ROTA, e so aceita a raiz quando o prazo
    acaba sem nenhuma rota aparecer. A raiz e endereco de passagem: na corrida
    de 06/10/2026 o programa ficou com uma janela que estava nela e que, um
    segundo depois, era o site publico do tribunal. Esperar a rota custa o
    tempo de a tela montar, que o passo seguinte gastaria de qualquer jeito.
    """
    import time as _tempo

    from .portal import pagina_de

    try:
        contexto = pagina_de(pagina).context
    except Exception:
        return None
    limite = _tempo.monotonic() + max(1, segundos)
    while True:
        try:
            abas = [a for a in (contexto.pages or []) if not a.is_closed()]
        except Exception:
            abas = []
        achada = _aba_do_portal_agora(abas, exigir_rota=True)
        if achada is not None:
            return achada
        if _tempo.monotonic() >= limite:
            # Ultima chance, e so agora: a raiz pode ser o portal que demorou
            # mais que o prazo para rotear, e devolver nada seria pior.
            crua = _aba_do_portal_agora(abas, exigir_rota=False)
            if crua is not None:
                return crua
            return None
        try:
            pagina.wait_for_timeout(400)
        except Exception:
            _tempo.sleep(0.4)


def abas_do_navegador(pagina: Any, teto: int = 10) -> list[str]:
    """Endereco de cada aba viva, sem parametros, para a recusa dizer onde esta.

    Sem parametros, pela regra de sempre: e neles que viajam identificador de
    cliente e numero de processo.
    """
    from .portal import enderecos_das_abas, pagina_de

    try:
        contexto = pagina_de(pagina).context
        abas = [a for a in (contexto.pages or []) if not a.is_closed()]
    except Exception:
        return []
    return enderecos_das_abas(abas, teto)


def trazer_para_a_frente(aba: Any) -> Any:
    """Poe a aba na frente antes de o programa agir nela, e devolve a aba.

    O advogado observou em 06/10/2026, com a janela do portal aberta na tela:
    "e voce nao consegue clicar nessa aba". Em navegador com janela visivel, o
    Chromium nao desenha nem calcula posicao de aba que esta atras, e o clique
    do Playwright depende das duas coisas: ele espera o elemento ficar estavel
    e visivel, e numa aba de fundo isso pode nunca acontecer.

    Falhar aqui nao e motivo para parar: se o navegador recusar, o clique ainda
    pode dar certo, e perder a consulta por causa do foco seria desproporcional.
    """
    try:
        aba.bring_to_front()
    except Exception:
        pass
    return aba


def conferir_janela_do_portal(candidata: Any, pagina: Any, segundos: int = 20) -> Any:
    """Devolve a janela que E o Portal de Servicos, ou recusa dizendo onde esta.

    Ate 06/10/2026 o caminho terminava em `return pagina` quando a janela nova
    nao vinha: devolvia a aba de ORIGEM, que o acompanhamento conduzido pelo
    advogado mostrou voltar para `www.tjrj.jus.br`. O comando entao procurava o
    menu do portal na pagina publica do tribunal e parava anunciando que o menu
    nao existe, que e verdade e nao ajuda em nada.

    Devolver a aba errada e pior que parar: a consulta seguiria em cima de uma
    tela que nao e a do processo. Entao, quando o portal nao esta em aba
    nenhuma, isto recusa e diz quais abas existem.
    """
    # Primeiro quem JA assumiu uma rota. A raiz nao serve aqui: foi aceitando a
    # raiz que o programa ficou, em 06/10/2026, com uma janela de passagem que
    # um segundo depois era o site publico do tribunal.
    for alvo in (candidata, pagina):
        try:
            if alvo is not None and tem_rota_do_portal(alvo.url):
                return trazer_para_a_frente(alvo)
        except Exception:
            continue

    achada = achar_aba_do_portal(pagina, segundos)
    if achada is not None:
        return trazer_para_a_frente(achada)

    # Nenhuma rota apareceu no prazo. A raiz ainda e melhor que recusar, porque
    # o portal pode so estar demorando a montar, e o passo seguinte espera.
    for alvo in (candidata, pagina):
        try:
            if alvo is not None and MARCA_DO_PORTAL in (alvo.url or ""):
                return trazer_para_a_frente(alvo)
        except Exception:
            continue

    abertas = abas_do_navegador(pagina)
    raise ConsultaIndisponivel(
        f"O Portal de Servicos ({MARCA_DO_PORTAL}) nao esta em nenhuma aba "
        "aberta. Ele abre em janela propria, e a aba de origem volta para a "
        "pagina publica do tribunal: seguir pela aba de origem procuraria o "
        "processo numa tela que nao e a do portal. "
        + ("Abas abertas, sem parametros: " + "; ".join(abertas) + ". "
           if abertas else "Nenhuma aba pode ser lida. ")
        + "Nada foi consultado.")


def entrar_no_portal_de_servicos(pagina: Any, guarda: Any, segundos: int = 45) -> Any:
    """Da tela de selecao de sistemas ate o Portal de Servicos aberto.

    Devolve a JANELA onde o portal abriu. Pede a abertura em ABA, e nao em
    janela destacada: aba e o que o navegador entrega de forma previsivel, e
    janela destacada pode ser barrada sem aviso nenhum.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (PREFIXO_DE_TEXTO, achar_opcional, elemento_visivel,
                         endereco_sem_dado, esperar_elemento, esperar_tela_montar,
                         pagina_de, permissao_efemera)

    # O endereco de login carrega `sgSist=PORTALSERVICOS`, e o portal as vezes
    # entra sozinho naquele sistema, sem passar pela escolha. Conferido em
    # campo em 06/10/2026: uma corrida parou ja dentro de `/portalservicos/`
    # sem nada ter sido selecionado. Quando a sessao ja esta la, insistir na
    # tela de selecao e procurar uma tela que nao existe mais.
    if MARCA_DO_PORTAL in (pagina.url or ""):
        return pagina

    # O portal abre em JANELA PROPRIA, e a aba de origem volta para a pagina
    # publica do tribunal. Procurar so na aba de origem fazia o comando
    # anunciar "a lista nao esta nela" com o portal aberto do lado, pedindo o
    # tipo de usuario, visivel na tela do operador.
    ja_aberta = achar_aba_do_portal(pagina, min(segundos, 10))
    if ja_aberta is not None:
        return ja_aberta

    lista = esperar_elemento(pagina, LISTA_DE_SISTEMAS, segundos)
    if lista is None and MARCA_DO_PORTAL in (pagina.url or ""):
        # Entrou enquanto se esperava.
        return pagina
    if lista is None:
        # Ultima chance: a janela pode ter aparecido durante a espera.
        tardia = achar_aba_do_portal(pagina, min(segundos, 5))
        if tardia is not None:
            return tardia
        montou = esperar_tela_montar(pagina, min(segundos, 5))
        raise ConsultaIndisponivel(
            f"A tela de selecao de sistemas nao tem {LISTA_DE_SISTEMAS}. "
            f"Endereco atual: {endereco_sem_dado(pagina.url, 80)}. "
            + ("A tela montou e a lista nao esta nela."
               if montou else "A tela nao chegou a montar: nenhum campo e nenhum "
                              "botao apareceram no prazo.")
            + " Nada foi escolhido.")

    valor = escolher_opcao_do_portal(lista)
    if valor is None:
        raise ConsultaIndisponivel(
            f"Nao achei UMA opcao do {SIGLA_DO_PORTAL} na lista de sistemas. "
            "Escolher no escuro levaria a sessao para outro sistema sem dizer "
            "nada. Nada foi escolhido.")

    enviar = elemento_visivel(pagina, f"{PREFIXO_DE_TEXTO}{BOTAO_ENVIAR}")
    if enviar is None:
        raise ConsultaIndisponivel(
            f"O botao {BOTAO_ENVIAR!r} nao esta na tela de selecao. "
            "Nada foi escolhido.")

    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao="entrada no Portal de Servicos pela selecao de sistemas",
        conferido_em="execucao atual",
        seletores_clicaveis=(ABRIR_EM_ABA, f"{PREFIXO_DE_TEXTO}{BOTAO_ENVIAR}"),
        seletores_preenchiveis=(LISTA_DE_SISTEMAS,),
    ))

    guarda.pode_executar(Acao.PREENCHER, LISTA_DE_SISTEMAS, url=pagina.url)
    lista.select_option(valor)

    # Aba, nunca janela destacada: aba e o que o navegador entrega de forma
    # previsivel, e janela destacada pode ser barrada sem aviso nenhum.
    aba = achar_opcional(pagina, ABRIR_EM_ABA)
    if aba is not None:
        guarda.pode_executar(Acao.CLICAR, ABRIR_EM_ABA, url=pagina.url)
        aba.click()

    guarda.pode_executar(Acao.CLICAR, f"{PREFIXO_DE_TEXTO}{BOTAO_ENVIAR}",
                         url=pagina.url)
    hospedeira = pagina_de(pagina)
    try:
        with hospedeira.context.expect_page(timeout=segundos * 1000) as nova:
            enviar.click()
        janela = nova.value
    except Exception:
        # Sem janela nova pelo evento, procura entre as abas: o portal pode ter
        # aberto numa janela que o evento nao entregou a tempo, ou na propria
        # aba. A conferencia recusa se nao estiver em nenhuma delas.
        return conferir_janela_do_portal(None, pagina, min(segundos, 10))
    try:
        janela.wait_for_load_state("domcontentloaded", timeout=segundos * 1000)
    except Exception:
        pass
    # `expect_page` entrega QUALQUER janela nova, e nao necessariamente o
    # portal. Conferir o endereco custa nada e evita seguir numa janela de
    # aviso ou de propaganda como se fosse a do processo.
    return conferir_janela_do_portal(janela, pagina, min(segundos, 10))


# ---------------------------------------------------------------------------
# Tipo de usuario, em `#/usuarios/alterar-perfil`
#
# Tela fotografada em 06/10/2026, logo depois de o Portal de Servicos abrir.
# Duas opcoes, "Usuario Comum" e "Advogado", e o botao "Entrar" so habilita
# depois da escolha. O perfil decide o que a sessao enxerga, exatamente como a
# inscricao no eproc, e por isso quem o nomeia e o operador.
# ---------------------------------------------------------------------------

TELA_DE_PERFIL = "/usuarios/alterar-perfil"
TITULO_DO_PERFIL = "Alterar Perfil"
ROTULO_DA_LISTA_DE_PERFIL = "Selecione perfil do usuário"
SELETOR_DA_CAIXA_DE_PERFIL = f'[placeholder="{ROTULO_DA_LISTA_DE_PERFIL}"]'
BOTAO_ENTRAR_NO_PERFIL = "Entrar"


class PerfilNaoInformado(RuntimeError):
    """A tela pediu o tipo de usuario e ninguem disse qual."""


def na_tela_de_perfil(pagina: Any, segundos: int = 8) -> bool:
    """Se a tela que pede o tipo de usuario esta aberta.

    O endereco basta e e imediato. Sem ele, espera o titulo aparecer: a tela
    chega vazia e se monta depois, e olhar uma vez so responderia "nao" a uma
    tela que esta chegando.
    """
    from .portal import PREFIXO_DE_TEXTO, esperar_elemento

    try:
        if TELA_DE_PERFIL in (pagina.url or ""):
            return True
    except Exception:
        pass
    return esperar_elemento(
        pagina, f"{PREFIXO_DE_TEXTO}{TITULO_DO_PERFIL}", segundos) is not None


def _lista_de_perfil(pagina: Any) -> Optional[Any]:
    """O `select` do tipo de usuario, quando a tela o monta como `select`."""
    from .portal import elemento_visivel

    for seletor in ("select[name=perfil]", "select#perfil", "select"):
        achado = elemento_visivel(pagina, seletor)
        if achado is not None:
            return achado
    return None


def perfis_oferecidos(pagina: Any) -> list[str]:
    """Os tipos de usuario que a tela oferece, para o relato da recusa.

    Sao nomes de PERFIL, nao dado de processo: "Usuario Comum", "Advogado".
    """
    lista = _lista_de_perfil(pagina)
    if lista is None:
        return []
    try:
        textos = lista.evaluate(
            "e => Array.from(e.options || []).map(o => o.text)")
    except Exception:
        return []
    return [" ".join((t or "").split()) for t in (textos or []) if (t or "").strip()]


# Identificadores reais da tela do tipo de usuario, lidos no acompanhamento
# conduzido pelo advogado em 06/10/2026. Ate aqui eu so alcancava esta lista
# por texto, o que e adivinhacao com outro nome: o texto prova que ACHEI algo
# com aquele nome, nunca que a lista chegou a abrir. Com o identificador da
# lista eu separo as duas perguntas, e a recusa passa a dizer qual das duas
# falhou em vez de deixar o operador tentar de novo as cegas.
CAIXA_DO_PERFIL = "app-dropdown#dropdownPerfil"
# O `input` DE VERDADE, dentro do custom element. Lido no console do navegador
# pelo advogado em 07/10/2026, e e a chave do que travou tres corridas:
#
#   <app-dropdown id="dropdownPerfil" placeholder="Selecione perfil do usuario"
#                 aria-haspopup="true" aria-expanded="false">
#     ...
#     <input type="text" role="combobox" aria-autocomplete="both"
#            class="autocomplete-serventia" placeholder="Selecione perfil do usuario">
#
# O MESMO `placeholder` esta nos dois, e `query_selector_all` devolve na ordem
# do documento, entao o hospedeiro vinha primeiro. O programa clicava e
# digitava na casca: nao aciona o que o Angular escuta no `input`, e custom
# element nao tem valor para receber texto. Nada falhava e nada acontecia.
CAMPO_DO_PERFIL = "app-dropdown#dropdownPerfil input[role=combobox]"
# A seta, segundo jeito de abrir a mesma lista.
SETA_DO_PERFIL = "app-dropdown#dropdownPerfil .botao-dropdown i"
# A lista existe SEMPRE no documento, com `style="display: none"`, e os dois
# itens ja estao dentro dela fechada. "Abrir" aqui quer dizer ficar visivel, e
# nao passar a existir, e por isso a conferencia e de visibilidade.
LISTA_DE_RESULTADOS = "ul#resultados"
ITEM_DA_LISTA = "li[id^=itemAutocomplete]"


# Onde uma opcao de lista pode morar, da forma mais especifica para a mais
# frouxa. Lista montada por script nem sempre usa `option`: usa `li`, `div` com
# papel de opcao, ou `div` puro e sem nada que a identifique alem do texto.
LUGARES_DE_OPCAO = (
    ITEM_DA_LISTA,
    "[role=option]",
    "li",
    "option",
    "button, input[type=submit], input[type=button], a",
    "span",
    "div",
)


def lista_de_opcoes_aberta(pagina: Any) -> bool:
    """Se a lista do tipo de usuario chegou a ABRIR, independente do que tem.

    Separa as duas recusas que ate aqui saiam com a mesma frase: a lista nao
    abriu, e a lista abriu sem a opcao pedida. A primeira e defeito meu, de
    clique ou de espera; a segunda e informacao sobre o portal, e o operador
    so pode agir sobre a segunda.
    """
    from .portal import elemento_visivel

    return elemento_visivel(pagina, LISTA_DE_RESULTADOS) is not None


def achar_opcao_na_lista(pagina: Any, texto: str,
                        exigir_posicao: bool = True) -> Optional[Any]:
    """Apelido de `achar_por_texto_em_qualquer_lugar`, para quem procura opcao.

    Fica porque e assim que o caminho do perfil nomeia o que procura. A busca
    em si nao tem nada de particular a listas: e a mesma pergunta de qualquer
    clicavel sem etiqueta propria.
    """
    return achar_por_texto_em_qualquer_lugar(pagina, texto, exigir_posicao)


def achar_por_texto_em_qualquer_lugar(pagina: Any, texto: str,
                                      exigir_posicao: bool = True) -> Optional[Any]:
    """O elemento cujo texto e EXATAMENTE este, em qualquer etiqueta.

    `_por_texto_exato` procura so em elemento clicavel, porque foi escrito para
    botao. Lista montada por script costuma empilhar `li` ou `div`, que nao
    entram naquela busca, e a opcao fica invisivel para ela.

    A ordem dos lugares vai do mais especifico ao mais frouxo, e para no
    primeiro que achar: comecar por `div` casaria com qualquer caixa que
    contivesse so aquela opcao, e clicar na caixa nao e clicar na opcao.

    Comparacao exata e sem acento. Exata porque "Advogado" e "Advogado
    (suspenso)" sao escolhas diferentes, e aceitar prefixo escolheria a errada.

    `exigir_posicao` controla a conferencia de que o elemento esta DENTRO da
    janela. Ela existe por um motivo real, o campo espelho empurrado para
    `left:-9999px`, e nao e dispensada de leve: sem ela, lista aberta abaixo da
    dobra tambem conta, e a diferenca entre as duas coisas e justamente o que o
    relato da recusa precisa dizer. Quem a desliga, diz que desligou.
    """
    from .portal import _na_tela, janela_de, sem_acento

    alvo = sem_acento(texto).strip()
    janela = janela_de(pagina)
    for lugar in LUGARES_DE_OPCAO:
        try:
            achados = pagina.query_selector_all(lugar)
        except Exception:
            continue
        for elemento in achados:
            try:
                if sem_acento(elemento.inner_text() or "").strip() != alvo:
                    continue
                if not elemento.is_visible():
                    continue
                if exigir_posicao and not _na_tela(
                        elemento, janela["width"], janela["height"]):
                    continue
                return elemento
            except Exception:
                continue
    return None


# Onde a lista do tipo de usuario pode estar, com o nome que o relato usa.
PECAS_DA_LISTA = (
    (CAIXA_DO_PERFIL, "a caixa do perfil"),
    (LISTA_DE_RESULTADOS, "a lista"),
    (ITEM_DA_LISTA, "os itens da lista"),
    ("[role=option]", "as opcoes por papel"),
)


def _estado_do_elemento(elemento: Any, janela: dict) -> str:
    """Como este elemento esta: visivel, onde, e dentro ou fora da janela."""
    from .portal import caixa_na_tela

    try:
        visivel = bool(elemento.is_visible())
    except Exception:
        return "ilegivel"
    try:
        caixa = elemento.bounding_box()
    except Exception:
        caixa = None
    if caixa is None:
        return "visivel, sem caixa" if visivel else "oculto, sem caixa"
    onde = (f"x={int(caixa['x'])} y={int(caixa['y'])} "
            f"l={int(caixa['width'])} a={int(caixa['height'])}")
    # Decide pela MESMA medida que acabou de imprimir. Medir de novo deixava o
    # diagnostico livre para se contradizer: a pagina pode ter rolado entre as
    # duas leituras, e dai a linha dizia uma posicao e um veredicto que nao
    # correspondia a ela.
    dentro = caixa_na_tela(caixa, janela["width"], janela["height"])
    return (f"{'visivel' if visivel else 'oculto'}, {onde}, "
            f"{'dentro' if dentro else 'FORA'} da janela")


# O que perguntar a propria caixa. `aria-expanded` e o decisivo: lido antes e
# depois do clique, ele separa em um passo "o clique nao abriu o componente" de
# "abriu e o meu seletor da lista e que esta errado". Sao os dois consertos que
# ainda disputavam a mesma frase de recusa.
PERGUNTAS_A_CAIXA = (
    "aria-expanded",
    "aria-controls",
    "aria-owns",
    "aria-haspopup",
    "role",
    # `readonly` virou a pergunta mais importante depois da corrida de
    # 07/10/2026. Caixa de escolha costuma ser `input` somente de leitura, que
    # abre no clique e nao aceita digitacao: nela, `type()` NAO levanta erro e
    # NAO escreve nada. O relato dizia "preencher" e nada acontecia, e a prova
    # positiva recusava porque o valor nunca chegou a existir.
    "readonly",
    "disabled",
    "class",
)


def valor_da_caixa_frente_ao_pedido(caixa: Any, esperado: Optional[str]) -> str:
    """Se o que esta na caixa e o perfil pedido, outra coisa, ou nada.

    Diz o SUFICIENTE sem imprimir o valor. A mesma caixa, noutra tela, teria
    numero de processo ou nome de parte, e um relato que imprime valor nao
    serve para este programa. Aqui a pergunta nao e "o que esta escrito": e
    "o que foi digitado chegou a entrar", e isso se responde comparando.
    """
    from .portal import sem_acento

    escrito = None
    for ler in (lambda e: e.evaluate("e => e.value"),
                lambda e: e.inner_text()):
        try:
            lido = ler(caixa)
        except Exception:
            continue
        if lido is not None:
            escrito = str(lido)
            break
    if escrito is None:
        return "valor ilegivel"
    if not escrito.strip():
        return "valor VAZIO (nada entrou na caixa)"
    if esperado and sem_acento(escrito).strip() == sem_acento(esperado).strip():
        return "valor IGUAL ao perfil pedido"
    return f"valor diferente do pedido, com {len(escrito.strip())} caractere(s)"


def estado_da_caixa(caixa: Any, esperado: Optional[str] = None) -> str:
    """Como a caixa do perfil esta agora, numa linha.

    O valor digitado nao e impresso: so se ele e o pedido, outro, ou nenhum.
    Em tela de escolha de processo a mesma funcao leria dado de cliente.
    """
    if caixa is None:
        return "a caixa nao foi encontrada"
    partes = []
    try:
        partes.append(f"tag={caixa.evaluate('e => e.tagName')}")
    except Exception:
        pass
    for nome in PERGUNTAS_A_CAIXA:
        try:
            lido = caixa.get_attribute(nome)
        except Exception:
            continue
        if lido is not None:
            texto = " ".join(str(lido).split())
            partes.append(f"{nome}={texto[:60]!r}")
    # Tambem pela propriedade, e nao so pelo atributo: componente que monta a
    # caixa por script costuma marcar `readOnly` sem escrever o atributo, e
    # perguntar so pelo atributo devolveria "nao e somente leitura" para uma
    # caixa que e.
    for nome, codigo in (("readOnly", "e => e.readOnly"),
                         ("disabled", "e => e.disabled")):
        try:
            if caixa.evaluate(codigo):
                partes.append(f"{nome}=True (propriedade)")
        except Exception:
            continue
    partes.append(valor_da_caixa_frente_ao_pedido(caixa, esperado))
    return "; ".join(partes) if partes else "sem atributo legivel"


def relato_da_escolha(pagina: Any, caixa: Any, perfil: str,
                      antes: str) -> str:
    """O bloco de diagnostico, para TODA recusa da escolha de perfil.

    Ate 07/10/2026 ele saia so numa das recusas. Naquela corrida o caminho de
    teclado deu certo o bastante para pular aquele ramo, e a recusa que de fato
    aconteceu, a da prova positiva, nao trazia diagnostico nenhum: a corrida
    custou uma tentativa de login e contou menos que a anterior.

    Relato de recusa que depende de QUAL recusa foi nao e relato: e sorte.
    """
    linhas = relatar_a_lista_de_perfil(pagina)
    bloco = ""
    if linhas:
        bloco += ("\n    O QUE EXISTE NA TELA DO TIPO DE USUARIO:\n    "
                  + "\n    ".join(linhas))
    bloco += (f"\n    A CAIXA ANTES DO CLIQUE: {antes}"
              f"\n    A CAIXA AGORA:           {estado_da_caixa(caixa, perfil)}"
              f"\n    O COMPONENTE: {envoltorio_da_caixa(pagina)}")
    return bloco


def envoltorio_da_caixa(pagina: Any, teto: int = 300) -> str:
    """A marcacao do componente que contem a caixa, para identifica-lo.

    Qual biblioteca o portal usa decide onde a lista nasce: ha componente que a
    monta num `div` solto no fim do documento, e nesse caso procura-la perto da
    caixa nunca a acharia. A marcacao responde isso de uma vez, e o relato
    inteiro ate aqui nao respondia.
    """
    from .portal import sem_dado_de_processo

    try:
        envoltorio = pagina.query_selector(CAIXA_DO_PERFIL)
    except Exception:
        envoltorio = None
    if envoltorio is None:
        return f"{CAIXA_DO_PERFIL} nao esta no documento"
    try:
        marcacao = envoltorio.evaluate("e => e.outerHTML") or ""
    except Exception:
        return f"{CAIXA_DO_PERFIL} esta no documento e a marcacao nao pode ser lida"
    return sem_dado_de_processo(" ".join(marcacao.split()))[:teto]


def relatar_a_lista_de_perfil(pagina: Any, teto: int = 12) -> list[str]:
    """O que existe na tela do tipo de usuario, esteja a vista ou nao.

    O advogado perguntou em 06/10/2026, depois de a escolha falhar duas vezes:
    "e possivel listar as opcoes que aparecem?". E, e era o que faltava. As
    buscas desta familia exigem elemento VISIVEL e DENTRO da janela, e quando
    nao acham nada as duas exigencias ficam indistinguiveis de "nao existe".
    Sao tres respostas diferentes, com tres consertos diferentes, e ate aqui
    saiam todas com a mesma frase.

    Aqui nada e exigido: conta o que esta no documento e diz de cada um como
    esta. O teto e o corte por tamanho ficam, porque a mesma forma de lista
    serve para escolher processo, e ali o texto seria dado de cliente.
    """
    from .portal import janela_de

    janela = janela_de(pagina)
    linhas = []
    for seletor, nome in PECAS_DA_LISTA:
        try:
            achados = pagina.query_selector_all(seletor) or []
        except Exception:
            linhas.append(f"{nome} ({seletor}): ilegivel")
            continue
        if not achados:
            linhas.append(f"{nome} ({seletor}): nao esta no documento")
            continue
        linhas.append(f"{nome} ({seletor}): {len(achados)} no documento")
        for elemento in achados[:teto]:
            estado = _estado_do_elemento(elemento, janela)
            try:
                texto = " ".join((elemento.inner_text() or "").split())
            except Exception:
                texto = ""
            if len(texto) > 60:
                texto = ""
            linhas.append(f"  {texto!r}: {estado}" if texto else f"  {estado}")
    return linhas


# Quanto esperar a lista de opcoes aparecer depois do clique na caixa.
ESPERA_DA_LISTA = 8


def esperar_opcao_na_lista(pagina: Any, texto: str,
                           segundos: int = ESPERA_DA_LISTA,
                           exigir_posicao: bool = True) -> Optional[Any]:
    """Espera a opcao aparecer depois de a caixa ser aberta.

    Olhar meio segundo depois do clique nao basta: a lista e montada por
    script, com animacao, e meio segundo pegava a tela ainda sem ela. Foi o
    que aconteceu em 06/10/2026, com a caixa ja clicada, conforme o relato da
    trava, e a opcao anunciada como ausente.
    """
    import time as _tempo

    limite = _tempo.monotonic() + max(1, segundos)
    while True:
        achada = achar_opcao_na_lista(pagina, texto, exigir_posicao)
        if achada is not None:
            return achada
        if _tempo.monotonic() >= limite:
            return None
        try:
            pagina.wait_for_timeout(300)
        except Exception:
            _tempo.sleep(0.3)


def opcoes_a_vista(pagina: Any, teto: int = 12) -> list[str]:
    """Textos curtos das opcoes visiveis, para o relato de quando nao se acha.

    Vale para a tela do TIPO DE USUARIO, onde opcao e nome de perfil. O teto e
    o corte por tamanho existem porque a mesma forma de lista serve para
    escolher processo, e ali o texto seria dado de cliente.
    """
    vistos, saida = set(), []
    for lugar in (ITEM_DA_LISTA, "[role=option]", "li", "option"):
        try:
            achados = pagina.query_selector_all(lugar)
        except Exception:
            continue
        for elemento in achados:
            if len(saida) >= teto:
                return saida
            try:
                if not elemento.is_visible():
                    continue
                texto = " ".join((elemento.inner_text() or "").split())
            except Exception:
                continue
            if texto and len(texto) <= 60 and texto not in vistos:
                vistos.add(texto)
                saida.append(texto)
    return saida


def perfil_assumido_pelo_controle(pagina: Any, perfil: str) -> bool:
    """Se o controle passou a MOSTRAR o perfil escolhido.

    Prova positiva, no lugar de confiar no clique. Nas telas fotografadas em
    06/10/2026 o botao "Entrar" nasce desabilitado, em verde claro, e so fica
    verde forte depois de o controle assumir o perfil. Clicar nele antes disso
    nao faz nada, e sem esta conferencia o comando seguiria como se tivesse
    entrado.

    Vale para os dois jeitos de a tela montar a escolha, porque a pergunta e a
    mesma nos dois: o que o controle mostra agora.
    """
    from .portal import elemento_por_rotulo, elemento_visivel, sem_acento

    alvo = sem_acento(perfil).strip()

    lista = _lista_de_perfil(pagina)
    if lista is not None:
        for leitura in ("e => (e.selectedOptions && e.selectedOptions[0]) "
                        "? e.selectedOptions[0].text : (e.value || '')",
                        "e => e.value || ''"):
            try:
                escrito = lista.evaluate(leitura) or ""
            except Exception:
                continue
            if sem_acento(str(escrito)).strip() == alvo:
                return True

    caixa = (elemento_visivel(pagina, CAMPO_DO_PERFIL)
             or elemento_por_rotulo(pagina, ROTULO_DA_LISTA_DE_PERFIL))
    if caixa is not None:
        for ler in (lambda e: e.evaluate("e => e.value || ''"),
                    lambda e: e.inner_text()):
            try:
                escrito = ler(caixa) or ""
            except Exception:
                continue
            if sem_acento(str(escrito)).strip() == alvo:
                return True
    return False


def botoes_a_vista(pagina: Any, teto: int = 12) -> list[str]:
    """Texto dos botoes visiveis, para a recusa dizer o que havia na tela.

    Sao rotulos de controle, nao dado de processo: "Entrar", "Cancelar". O
    teto e o corte por tamanho ficam porque a mesma funcao, noutra tela,
    encontraria botao cujo rotulo e o proprio andamento.
    """
    from .portal import ALVOS_CLICAVEIS

    vistos, saida = set(), []
    try:
        achados = pagina.query_selector_all(ALVOS_CLICAVEIS) or []
    except Exception:
        return saida
    for elemento in achados:
        if len(saida) >= teto:
            break
        try:
            if not elemento.is_visible():
                continue
            texto = " ".join((elemento.inner_text() or "").split())
            marca = "" if elemento.is_enabled() else " (desabilitado)"
        except Exception:
            continue
        if texto and len(texto) <= 40 and texto not in vistos:
            vistos.add(texto)
            saida.append(texto + marca)
    return saida


# Como alcancar um clicavel pelo NOME, do jeito mais exato ao mais tolerante.
# Esta sequencia foi descoberta tres vezes, em tres telas diferentes do mesmo
# portal, e nas tres eu a escrevi de novo no lugar de generaliza-la:
#
#   06/10  a opcao do perfil        nao vinha em `option`, e sim em `li`
#   07/10  o botao 'Entrar'         tinha caixa de zero por zero
#   07/10  'Consultas Processuais'  estava fora da janela, com 26 outros
#
# Sao sintomas diferentes da mesma coisa: o elemento EXISTE e nao satisfaz
# alguma exigencia da busca. Cada exigencia tem razao de ser, e por isso
# nenhuma foi removida; elas passaram a ser tentadas em ordem.
PAPEIS_CLICAVEIS = ("button", "link", "menuitem")


def tem_caixa(elemento: Any) -> bool:
    """Se o elemento ocupa algum espaco, e portanto pode ser clicado a mouse."""
    try:
        caixa = elemento.bounding_box()
    except Exception:
        return False
    return bool(caixa and caixa.get("width") and caixa.get("height"))


def clicar_com_jeito(elemento: Any) -> str:
    """Clica do jeito que este elemento aceita, e DIZ qual foi.

    Devolve "mouse", "documento" ou "nenhum". Dizer qual foi importa: clique
    de documento nao passa pelas mesmas conferencias do navegador, entao quem
    chama precisa saber que usou esse caminho para relata-lo ao operador.
    """
    if tem_caixa(elemento):
        try:
            elemento.scroll_into_view_if_needed()
        except Exception:
            pass
        try:
            elemento.click()
            return "mouse"
        except Exception:
            pass
    return "documento" if clicar_pelo_documento(elemento) else "nenhum"


def achar_clicavel(pagina: Any, nome: str, segundos: int = 15) -> Optional[Any]:
    """O clicavel com este NOME EXATO, por todas as vias, na ordem.

    1. Esperar pela busca estrita, que exige visivel e dentro da janela.
    2. A arvore acessivel, que e como a PESSOA enxerga a tela: alcanca nome
       vindo de `aria-label` e elemento com papel de botao que nao e `button`.
    3. Por texto, sem exigir que esteja dentro da janela. Elemento abaixo da
       dobra nao esta ausente: esta a um rolar de distancia.
    4. Sem tamanho, exigindo HABILITADO. Clicar no desabilitado nao faz nada
       e o comando seguiria como se tivesse clicado.

    Nenhuma exigencia foi afrouxada nas buscas gerais de `portal.py`: elas
    protegem outras telas e outros portais. O que mudou e que aqui se tenta
    mais de uma, em vez de desistir na primeira.
    """
    from .portal import (ALVOS_CLICAVEIS, PREFIXO_DE_TEXTO, esperar_elemento,
                         sem_acento)

    achado = esperar_elemento(pagina, f"{PREFIXO_DE_TEXTO}{nome}", segundos)
    if achado is not None:
        return achado

    pela_arvore = achar_pela_arvore_acessivel(pagina, nome)
    if pela_arvore is not None:
        return pela_arvore

    alvo = sem_acento(nome).strip()
    try:
        candidatos = pagina.query_selector_all(ALVOS_CLICAVEIS) or []
    except Exception:
        return None
    for elemento in candidatos:
        try:
            escrito = sem_acento(
                elemento.inner_text() or elemento.get_attribute("value") or "")
            if escrito.strip() != alvo or not elemento.is_visible():
                continue
            elemento.scroll_into_view_if_needed()
            return elemento
        except Exception:
            continue

    # Em QUALQUER etiqueta, e nao so nas que tem semantica de clique.
    # Conferido em campo em 07/10 e 08/10/2026: o menu deste portal e feito de
    # `div`, `li` e `span`. O acompanhamento de 06/10 ja tinha mostrado
    # `div#CONSULTAS`, `li#CONSULTAS` e `span#CONSULTAS`, e eu li aquilo como
    # detalhe do menu de primeiro nivel em vez de como a forma do menu INTEIRO.
    # Por isso a escolha do perfil funcionou, que usa esta busca ampla desde
    # 06/10, e o item do menu nao: ele nao e `button` nem `a`, e as buscas de
    # clicavel so olhavam para essas duas.
    for exigir in (True, False):
        achado = achar_por_texto_em_qualquer_lugar(pagina, nome, exigir)
        if achado is not None:
            return achado

    return candidato_sem_tamanho(pagina, nome)


def achar_pela_arvore_acessivel(pagina: Any, nome: str) -> Optional[Any]:
    """O botao pelo NOME ACESSIVEL, que e como a pessoa o enxerga.

    Rede que as duas buscas por texto nao cobrem, e a diferenca nao e teorica:
    `_por_texto_exato` olha `inner_text` e `value` de uma lista fixa de
    etiquetas, entao perde o botao cujo nome vem de `aria-label`, e perde
    qualquer elemento com `role=button` que nao seja `<button>`.

    `exact=True` pela mesma razao de sempre: "Entrar" e "Entrar como
    convidado" sao coisas diferentes, e aceitar prefixo escolheria a errada.

    Mais de um candidato nao e desempatado por posicao: fica o primeiro
    VISIVEL. Escolher pelo lugar na tela seria escolher no escuro.
    """
    obter = getattr(pagina, "get_by_role", None)
    if obter is None:
        return None
    for papel in PAPEIS_CLICAVEIS:
        try:
            alvos = obter(papel, name=nome, exact=True)
            total = alvos.count()
        except Exception:
            continue
        for i in range(total):
            try:
                candidato = alvos.nth(i)
                if candidato.is_visible():
                    return candidato
            except Exception:
                continue
    return None


def relato_dos_candidatos(pagina: Any, nome: str = BOTAO_ENTRAR_NO_PERFIL,
                          teto: int = 8) -> list[str]:
    """Cada botao que se parece com o de enviar, e como ele esta.

    Existe porque a recusa de 07/10/2026 dizia que o botao nao estava na tela
    e o relato logo abaixo o listava. Quando as duas leituras discordam, o
    util nao e repetir nenhuma delas: e descrever cada candidato por inteiro,
    com tudo o que decide se ele serve.
    """
    from .portal import sem_acento

    alvo = sem_acento(nome).strip()
    linhas, vistos = [], set()
    candidatos = []
    # Em todas as etiquetas, e nao so nas clicaveis. Em 08/10/2026 este relato
    # disse "nenhum clicavel com o nome 'Consultas Processuais' na tela", o que
    # era verdade sobre botoes e ancoras e falso sobre a tela: o item estava
    # la, noutra etiqueta, e a frase mandava procurar no lugar errado.
    leu_alguma_coisa = False
    for lugar in LUGARES_DE_OPCAO:
        try:
            achados = pagina.query_selector_all(lugar) or []
        except Exception:
            continue
        # Tela vazia e tela ilegivel sao respostas diferentes: a primeira diz
        # que o item nao esta la, a segunda que nao se sabe.
        leu_alguma_coisa = True
        candidatos.extend(achados)
    if not leu_alguma_coisa:
        return ["nao foi possivel ler os elementos da tela"]
    for elemento in candidatos:
        if len(linhas) >= teto:
            break
        try:
            texto = (elemento.inner_text() or "").strip()
            valor = elemento.get_attribute("value")
            rotulo = elemento.get_attribute("aria-label")
        except Exception:
            continue
        nomes = [n for n in (texto, valor, rotulo) if n]
        if not any(sem_acento(n).strip() == alvo for n in nomes):
            continue
        # O mesmo elemento aparece em mais de um lugar da lista de etiquetas.
        try:
            marca = elemento.evaluate(
                "e => e.tagName + '#' + (e.id || '') + '@' + "
                "(e.getBoundingClientRect().top + ',' + "
                "e.getBoundingClientRect().left)")
        except Exception:
            marca = None
        if marca is not None:
            if marca in vistos:
                continue
            vistos.add(marca)
        partes = []
        for nome, ler in (("tag", lambda e: e.evaluate("e => e.tagName")),
                          ("visivel", lambda e: e.is_visible()),
                          ("habilitado", lambda e: e.is_enabled())):
            try:
                partes.append(f"{nome}={ler(elemento)!r}")
            except Exception:
                partes.append(f"{nome}=ilegivel")
        partes.append(f"texto={texto[:40]!r}")
        if esta_recolhido(elemento):
            partes.append("RECOLHIDO (grupo fechado)")
        if valor:
            partes.append(f"value={valor[:40]!r}")
        if rotulo:
            partes.append(f"aria-label={rotulo[:40]!r}")
        try:
            caixa = elemento.bounding_box()
        except Exception:
            caixa = None
        partes.append(
            "caixa=nenhuma" if caixa is None else
            f"caixa=x{int(caixa['x'])} y{int(caixa['y'])} "
            f"l{int(caixa['width'])} a{int(caixa['height'])}")
        try:
            marcacao = " ".join((elemento.evaluate("e => e.outerHTML") or "").split())
            partes.append(f"marcacao={marcacao[:200]!r}")
        except Exception:
            pass
        linhas.append("; ".join(partes))
    if not linhas:
        return [f"nenhum elemento com o nome EXATO {nome!r} na tela, "
                "em etiqueta nenhuma"]
    return linhas


def candidato_sem_tamanho(pagina: Any,
                          nome: str = BOTAO_ENTRAR_NO_PERFIL) -> Optional[Any]:
    """O 'Entrar' que EXISTE, esta habilitado, e tem caixa de zero por zero.

    Lido em campo em 07/10/2026, e e o unico candidato que a tela oferece:

        tag='A'; visivel=False; habilitado=True; texto='Entrar';
        caixa=x460 y499 l0 a0

    Um `<a>` renderizado, no lugar certo da tela, com largura e altura zero.
    `is_visible()` do Playwright devolve falso para caixa vazia, e TODAS as
    minhas buscas exigem `is_visible()`. Por isso as tres redes falharam
    juntas: nenhuma delas estava errada sobre o que procurava.

    Isto nao decide clicar: so devolve o candidato. Quem decide e quem chama,
    e so depois de a prova positiva conferir que o clique levou a algum lugar.
    """
    from .portal import sem_acento

    alvo = sem_acento(nome).strip()
    # Em todas as etiquetas. Ate 08/10/2026 esta rede olhava so `button` e `a`,
    # e por isso nao alcancava o item do menu, que e `li`.
    candidatos = []
    for lugar in LUGARES_DE_OPCAO:
        try:
            candidatos.extend(pagina.query_selector_all(lugar) or [])
        except Exception:
            continue
    for elemento in candidatos:
        try:
            nomes = (elemento.inner_text() or "",
                     elemento.get_attribute("value") or "",
                     elemento.get_attribute("aria-label") or "")
            if not any(sem_acento(n).strip() == alvo for n in nomes if n):
                continue
            if not elemento.is_enabled():
                continue
        except Exception:
            continue
        return elemento
    return None


def clicar_pelo_documento(elemento: Any) -> bool:
    """Clique disparado no proprio elemento, para quem nao tem tamanho.

    `click()` do Playwright espera o elemento ficar acionavel, e elemento de
    caixa vazia nunca fica: ele mira o centro da caixa, e nao ha centro. O
    clique do documento nao mira lugar nenhum, aciona o que a pagina escuta
    naquele elemento, que e o mesmo que o navegador faria.

    Nao e um jeito de burlar protecao, e sim de alcancar um elemento que o
    operador alcanca com o mouse todo dia. E nao dispensa prova: quem chama
    confere depois se a tela mudou.
    """
    try:
        elemento.evaluate("e => e.click()")
        return True
    except Exception:
        return False


def saiu_da_tela_de_perfil(pagina: Any, segundos: int = 20) -> bool:
    """Prova positiva de que o envio do perfil levou a algum lugar.

    Sem ela, clicar num elemento invisivel seria exatamente o tipo de acao
    que este programa nao faz: a que se declara feita sem nada que a comprove.
    """
    import time as _tempo

    limite = _tempo.monotonic() + max(1, segundos)
    while True:
        try:
            if TELA_DE_PERFIL not in (pagina.url or ""):
                return True
        except Exception:
            pass
        if _tempo.monotonic() >= limite:
            return False
        try:
            pagina.wait_for_timeout(400)
        except Exception:
            _tempo.sleep(0.4)


def achar_o_entrar(pagina: Any, segundos: int = 15) -> Optional[Any]:
    """O botao de enviar o perfil. Apelido da busca geral, pelo nome dele.

    Fica como funcao propria porque e assim que o caminho do perfil a nomeia,
    e porque o nome diz o que se procura. A sequencia de tentativas, essa,
    e a mesma de qualquer outro clicavel: foi escrita tres vezes antes de eu
    perceber que era uma so.
    """
    return achar_clicavel(pagina, BOTAO_ENTRAR_NO_PERFIL, segundos)


def escolher_pelo_teclado(caixa: Any, pagina: Any) -> bool:
    """Seta para baixo e Enter, o caminho de teclado do combobox.

    Padrao comum de caixa de completar: a lista existe para o teclado antes de
    existir para o mouse, e ha componente que nem chega a desenha-la quando a
    navegacao e por tecla.

    Isto seria temerario em qualquer outro lugar deste programa, porque a seta
    escolhe por POSICAO e nao por nome, e aqui ha duas opcoes: "Usuario Comum"
    e "Advogado". Escolher a errada daria visao reduzida sem avisar, que e
    exatamente o que `escolher_perfil` existe para impedir.

    O que torna aceitavel e a conferencia que ja vem depois:
    `perfil_assumido_pelo_controle` exige que o controle MOSTRE o perfil que o
    operador nomeou, e recusa quando nao mostra. A seta nao decide nada: ela so
    propoe, e quem decide e a prova positiva. Sem aquela conferencia no lugar,
    este caminho nao poderia existir.
    """
    for tecla in ("ArrowDown", "Enter"):
        try:
            caixa.press(tecla)
        except Exception:
            return False
        try:
            pagina.wait_for_timeout(300)
        except Exception:
            pass
    return True


def escolher_perfil(pagina: Any, guarda: Any, perfil: Optional[str],
                    segundos: int = 45) -> None:
    """Escolhe o tipo de usuario que o OPERADOR nomeou e entra.

    Nao escolhe por conta propria, nem quando ha so duas opcoes. O perfil
    decide o que a sessao enxerga: entrar como "Usuario Comum" devolveria uma
    visao reduzida sem avisar, e consulta que volta vazia e indistinguivel de
    processo inexistente para quem le o resultado.
    """
    from .core.guarda_navegacao import Acao, Permissao
    from .portal import (PREFIXO_DE_TEXTO, elemento_por_rotulo, elemento_visivel,
                         permissao_efemera, sem_acento)

    if not (perfil or "").strip():
        oferecidos = perfis_oferecidos(pagina)
        recado = ("A tela pediu o TIPO DE USUARIO e nenhum foi informado. "
                  "Repita o comando com --perfil.")
        if oferecidos:
            recado += " A tela oferece: " + "; ".join(oferecidos) + "."
        recado += (" Escolher por conta propria daria visao reduzida sem avisar, "
                   "e consulta que volta vazia e indistinguivel de processo "
                   "inexistente.")
        raise PerfilNaoInformado(recado)

    procurado = sem_acento(perfil).strip()
    alvo_da_opcao = f"{PREFIXO_DE_TEXTO}{perfil.strip()}"
    alvo_do_entrar = f"{PREFIXO_DE_TEXTO}{BOTAO_ENTRAR_NO_PERFIL}"
    guarda.permissoes.append(Permissao(
        padrao_url=permissao_efemera(pagina.url).padrao_url,
        descricao=f"escolha do tipo de usuario {perfil.strip()!r}",
        conferido_em="execucao atual",
        seletores_clicaveis=(alvo_da_opcao, alvo_do_entrar,
                             SELETOR_DA_CAIXA_DE_PERFIL, CAMPO_DO_PERFIL,
                             SETA_DO_PERFIL),
        # A caixa entra nos DOIS: ela e clicada para abrir a lista e, quando a
        # lista nao abre, recebe o nome digitado. Liberar so `select` deixava o
        # caminho de digitar barrado pela propria trava, e o comando terminava
        # em traceback no meio da escolha do perfil.
        seletores_preenchiveis=("select", SELETOR_DA_CAIXA_DE_PERFIL,
                                CAMPO_DO_PERFIL),
    ))

    from .portal import esperar_tela_montar

    esperar_tela_montar(pagina, segundos=min(segundos, 8))
    lista = _lista_de_perfil(pagina)
    if lista is not None:
        casados = [t for t in perfis_oferecidos(pagina)
                   if sem_acento(t).strip() == procurado]
        if len(casados) != 1:
            raise PerfilNaoInformado(
                f"O perfil {perfil!r} nao casa com UMA opcao da tela. "
                f"Ela oferece: {'; '.join(perfis_oferecidos(pagina)) or '(nenhuma)'}. "
                "Nada foi escolhido.")
        guarda.pode_executar(Acao.PREENCHER, "select", url=pagina.url)
        lista.select_option(label=casados[0])
    else:
        # Lista montada por script, sem `select`. Abre pelo proprio rotulo que a
        # tela mostra e clica na opcao que o OPERADOR nomeou, por texto exato.
        # A caixa e `input[type=text]`, e nao botao: o unico rotulo dela e o
        # texto cinza que mostra. Procurar por texto de botao nao acha nada.
        # O seletor conferido PRIMEIRO, o rotulo como reserva. Identificacao
        # positiva vale mais que deducao por rotulo, e foi a deducao por
        # rotulo que entregou a casca em lugar do campo.
        caixa = (elemento_visivel(pagina, CAMPO_DO_PERFIL)
                 or elemento_por_rotulo(pagina, ROTULO_DA_LISTA_DE_PERFIL))
        if caixa is None:
            raise PerfilNaoInformado(
                f"A tela do tipo de usuario nao tem lista, nem {CAMPO_DO_PERFIL}, "
                f"nem {ROTULO_DA_LISTA_DE_PERFIL!r}. Nada foi escolhido.")
        guarda.pode_executar(Acao.CLICAR, SELETOR_DA_CAIXA_DE_PERFIL,
                             url=pagina.url)
        # A caixa pode estar abaixo da dobra: o clique do Playwright rola ate
        # ela sozinho, mas a lista que ela abre fica onde a caixa estiver, e e
        # a posicao da LISTA que decide se as buscas a enxergam. Rolar antes
        # deixa as duas na janela, em vez de so a caixa.
        try:
            caixa.scroll_into_view_if_needed()
        except Exception:
            pass
        antes_do_clique = estado_da_caixa(caixa)
        caixa.click()
        opcao = esperar_opcao_na_lista(pagina, perfil.strip(),
                                       min(segundos, ESPERA_DA_LISTA))

        if opcao is None:
            # A caixa e `input[type=text]`: pode ser de digitar e filtrar, e
            # nesse caso o clique sozinho nao abre lista nenhuma. Digitar o
            # que o OPERADOR nomeou nao e escolher por conta propria: e o
            # mesmo valor, por outro caminho.
            guarda.pode_executar(Acao.PREENCHER, SELETOR_DA_CAIXA_DE_PERFIL,
                                 url=pagina.url)
            try:
                caixa.click()
                caixa.type(perfil.strip(), delay=40)
            except Exception as exc:
                raise PerfilNaoInformado(
                    f"A opcao {perfil!r} nao apareceu, e digitar na caixa falhou "
                    f"({type(exc).__name__}). Nada foi escolhido.") from None
            opcao = esperar_opcao_na_lista(pagina, perfil.strip(),
                                           min(segundos, ESPERA_DA_LISTA))

        if opcao is None:
            # Ultima tentativa antes de desistir: a MESMA busca, sem exigir que
            # o elemento esteja dentro da janela. Lista que abre abaixo da
            # dobra e indistinguivel de lista que nao abriu para quem exige
            # posicao, e as duas pedem consertos diferentes. Quando e isto, o
            # comando segue E DIZ que seguiu assim: achado que depende de uma
            # regra afrouxada nao pode passar por achado comum.
            opcao = achar_opcao_na_lista(pagina, perfil.strip(),
                                         exigir_posicao=False)
            if opcao is not None:
                print(f"    [FORA DA JANELA] A opcao {perfil.strip()!r} estava "
                      "na lista, porem fora da area visivel da janela.")
                print("    O comando seguiu. Avise-me: a regra de posicao e que "
                      "precisa ser corrigida, e nao a escolha do perfil.")

        pelo_teclado = False
        if opcao is None:
            # Ultimo caminho antes de desistir. A conferencia positiva logo
            # abaixo e que o torna aceitavel: a seta propoe, ela decide.
            guarda.pode_executar(Acao.PREENCHER, SELETOR_DA_CAIXA_DE_PERFIL,
                                 url=pagina.url)
            pelo_teclado = escolher_pelo_teclado(caixa, pagina)
            if pelo_teclado:
                print("    [TECLADO] A lista nao apareceu para o mouse. Tentei "
                      "seta para baixo e Enter.")
                print("    Se o perfil certo nao for assumido, o comando para "
                      "aqui mesmo: a seta escolhe por posicao, nao por nome.")

        if opcao is None and not pelo_teclado:
            a_vista = opcoes_a_vista(pagina)
            abriu = lista_de_opcoes_aberta(pagina)
            recado = (f"A opcao {perfil!r} nao apareceu na lista de tipos de "
                      "usuario, nem depois de a caixa ser clicada e o nome ser "
                      "digitado nela.")
            if a_vista:
                recado += " A lista mostra: " + "; ".join(a_vista) + "."
            elif abriu:
                recado += (f" A lista ({LISTA_DE_RESULTADOS}) ESTA aberta e "
                           "vazia: o portal nao ofereceu nenhum tipo de usuario.")
            else:
                recado += (f" A lista ({LISTA_DE_RESULTADOS}) nao chegou a abrir.")
            # O que existe no documento, visivel ou nao, dentro da janela ou
            # nao. Sem isto, "nao achei" cobre tres defeitos diferentes e nao
            # distingue nenhum, e cada rodada as cegas custa uma tentativa de
            # login ao advogado.
            recado += relato_da_escolha(pagina, caixa, perfil.strip(),
                                        antes_do_clique)
            raise PerfilNaoInformado(recado + "\n    Nada foi escolhido.")
        if opcao is not None:
            guarda.pode_executar(Acao.CLICAR, alvo_da_opcao, url=pagina.url)
            opcao.click()

    # Prova positiva antes de enviar. O botao "Entrar" nasce desabilitado e so
    # habilita depois de a caixa assumir o perfil: clicar nele antes nao faz
    # nada, e sem esta conferencia o comando seguiria como se tivesse entrado.
    try:
        pagina.wait_for_timeout(400)
    except Exception:
        pass
    if not perfil_assumido_pelo_controle(pagina, perfil.strip()):
        recado = (f"A opcao {perfil.strip()!r} foi escolhida e o controle nao "
                  "passou a mostra-la. O botao de entrar so habilita depois "
                  "disso, entao clicar nele nao faria nada. Nada foi enviado.")
        # O MESMO bloco das outras recusas. Em 07/10/2026 esta aqui era a unica
        # sem diagnostico, e foi exatamente ela que aconteceu: o caminho de
        # teclado deu certo o bastante para pular o ramo que relatava, e a
        # corrida custou uma tentativa de login para contar menos que a
        # anterior. Relato que depende de QUAL recusa foi nao e relato.
        try:
            caixa_agora = (elemento_visivel(pagina, CAMPO_DO_PERFIL)
                           or elemento_por_rotulo(pagina,
                                                  ROTULO_DA_LISTA_DE_PERFIL))
        except Exception:
            caixa_agora = None
        recado += relato_da_escolha(pagina, caixa_agora, perfil.strip(),
                                    "(a escolha nao passou pelo caminho da caixa)")
        raise PerfilNaoInformado(recado)

    # A busca geral ja tenta, em ordem: esperar, arvore acessivel, texto fora
    # da janela, e sem tamanho. A ultima e a que esta tela exige: o 'Entrar'
    # existe, esta habilitado, e tem caixa de zero por zero.
    entrar = achar_o_entrar(pagina, min(segundos, 15))
    if entrar is None:
        a_vista = botoes_a_vista(pagina)
        raise PerfilNaoInformado(
            f"O botao {BOTAO_ENTRAR_NO_PERFIL!r} nao esta na tela do tipo de "
            "usuario, nem esperado, nem pela arvore acessivel, nem procurado "
            "fora da janela, nem sem tamanho. O perfil foi escolhido e NAO foi "
            "enviado."
            + ("\n    BOTOES A VISTA: " + "; ".join(a_vista) + "."
               if a_vista else "\n    Nenhum botao visivel na tela.")
            + "\n    CANDIDATOS AO BOTAO DE ENVIAR:\n    "
            + "\n    ".join(relato_dos_candidatos(pagina)))

    guarda.pode_executar(Acao.CLICAR, alvo_do_entrar, url=pagina.url)
    jeito = clicar_com_jeito(entrar)
    if jeito == "documento":
        print(f"    [SEM TAMANHO] O botao {BOTAO_ENTRAR_NO_PERFIL!r} existe e "
              "esta habilitado, com caixa de zero por zero.")
        print("    O clique do Playwright mira o centro da caixa, e nao ha "
              "centro. Disparando o clique no proprio elemento.")
    try:
        pagina.wait_for_load_state("networkidle", timeout=segundos * 1000)
    except Exception:
        pass

    # Prova positiva do ENVIO, e nao so da escolha. Clicar num elemento que o
    # Playwright considera invisivel so se justifica com conferencia depois:
    # sem ela, isto seria uma acao declarada feita sem nada que a comprove.
    if not saiu_da_tela_de_perfil(pagina, min(segundos, 20)):
        recado = (f"O perfil {perfil.strip()!r} foi escolhido e o clique em "
                  f"{BOTAO_ENTRAR_NO_PERFIL!r} nao tirou a tela do tipo de "
                  "usuario. Nada foi consultado.")
        if jeito == "documento":
            recado += (" O clique foi disparado no proprio elemento, porque a "
                       "caixa dele e de zero por zero.")
        elif jeito == "nenhum":
            recado += " O botao nao aceitou clique de forma nenhuma."
        recado += ("\n    CANDIDATOS AO BOTAO DE ENVIAR:\n    "
                   + "\n    ".join(relato_dos_candidatos(pagina)))
        raise PerfilNaoInformado(recado)


def reencontrar_o_portal(pagina: Any, segundos: int = 15) -> Any:
    """A aba do portal AGORA, porque a que o programa segura pode ter mudado.

    A licao de 06/10/2026 nao foi "o portal abre em janela nova": foi que a
    pagina que o programa segura NAO e estavel. A janela aceita como portal
    saiu de `/portalservicos/` para `www.tjrj.jus.br` entre um passo e o
    seguinte, e o comando levou a pagina publica do tribunal ate o fim, tres
    passos adiante, anunciando a cada parada um defeito que nao existia.

    Entao, a cada fronteira, o portal e reencontrado em vez de carregado. Nao
    recusa quando nao acha: quem recusa e o passo seguinte, que sabe o que
    procurava. Aqui so se devolve a melhor aba disponivel.
    """
    achada = achar_aba_do_portal(pagina, segundos)
    return trazer_para_a_frente(achada if achada is not None else pagina)
