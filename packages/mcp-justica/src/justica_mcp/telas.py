"""Gravacao das TELAS que a corrida toca, para parar de depurar ao vivo.

Por que este modulo existe, escrito no dia em que o advogado disse que o
programa volta passos que ja tinham sido vencidos, e estava certo:

Em 15/10/2026 um commit meu consertou a gaveta do indice do Visualizador e
quebrou a consulta, que funcionava desde 13/10. Os 1301 testes passaram, porque
eles fixam as MINHAS suposicoes sobre o portal, e nao o portal. Entre o conserto
e a descoberta foram quatro corridas do advogado, cada uma custando uma
autenticacao, e cada corrida revelando UM portao.

A causa de fundo nao e nenhum desses defeitos: e que o programa so sabe da tela
o que uma corrida ao vivo mostra, uma vez. Enquanto for assim, consertar e
adivinhar, e adivinhar em codigo compartilhado quebra o que ja passava.

Entao a corrida passa a GRAVAR cada tela que toca: etiquetas, identificadores,
classes, rotulos acessiveis, geometria, estado dos controles e as mensagens da
tela. Com isso:

  - quando algo falha, a resposta ja esta no disco, e descobrir nao custa uma
    corrida nova;
  - a tela real vira material de teste, no lugar do duble que eu inventei.

O QUE NAO E GRAVADO, e esta e a regra que torna o arquivo mostravel:

  - valor de campo nenhum. De `input` e `textarea` fica so QUANTOS caracteres
    ha, e se a caixa esta marcada;
  - texto de celula, de item de lista, de paragrafo e de caixa generica. E
    neles que moram nome de parte, descricao de andamento e dado do processo;
  - texto so e guardado de etiqueta cujo texto e ROTULO DE CONTROLE (botao,
    ligacao, rotulo de campo, opcao, cabecalho de coluna, titulo de secao), com
    teto de 60 caracteres;
  - de ligacao fica so o CAMINHO do endereco, nunca os parametros: depois da
    busca e neles que viaja o numero do processo.

Tudo o que sobra ainda passa por `sem_dado_de_processo` na gravacao, como
segunda rede, e de novo na impressao.
"""

from __future__ import annotations

import os
from typing import Any, Optional

# Liga a gravacao. A opcao da linha de comando escreve aqui, para que o modulo
# nao precise receber a decisao de mao em mao por sete camadas de chamada.
VARIAVEL_DA_GRAVACAO = "JUSTICA_GRAVAR_TELAS"

# Quantos nos o esqueleto guarda. O Visualizador chega a 543 botoes e mais de
# 500 caixas de selecao; tres mil nos cobrem isso com folga e ainda cabem num
# arquivo que abre rapido.
TETO_DE_NOS = 3000


JS_DO_ESQUELETO = r"""() => {
  const TETO = 3000;
  const corta = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  // Etiquetas cujo texto e ROTULO DE CONTROLE, nao conteudo do processo.
  // Celula, item de lista, paragrafo e caixa generica ficam de fora: e neles
  // que moram nome de parte, descricao de andamento e valor de campo.
  const COM_TEXTO = new Set(['BUTTON', 'A', 'LABEL', 'OPTION', 'LEGEND',
                             'TH', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
                             'SUMMARY', 'CAPTION']);
  const ATRIBUTOS = ['name', 'type', 'role', 'aria-label', 'title',
                     'placeholder', 'aria-expanded', 'aria-hidden',
                     'aria-selected', 'disabled', 'hidden'];
  const saida = [];
  let cortado = false;
  const todos = document.querySelectorAll('*');
  for (const e of todos) {
    if (saida.length >= TETO) { cortado = true; break; }
    const etiqueta = e.tagName;
    if (etiqueta === 'SCRIPT' || etiqueta === 'STYLE' || etiqueta === 'LINK'
        || etiqueta === 'META' || etiqueta === 'PATH' || etiqueta === 'path') {
      continue;
    }
    const r = e.getBoundingClientRect();
    const atributos = {};
    for (const nome of ATRIBUTOS) {
      const valor = e.getAttribute && e.getAttribute(nome);
      if (valor !== null && valor !== undefined) atributos[nome] = corta(valor, 80);
    }
    if (e.tagName === 'A' && e.getAttribute('href')) {
      // So o CAMINHO: depois da busca e no endereco que viaja o processo.
      try {
        atributos.href = new URL(e.getAttribute('href'), location.href).pathname;
      } catch (_) { atributos.href = '(ilegivel)'; }
    }
    if (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') {
      // NUNCA o valor. So se ha algo digitado, e quantos caracteres.
      const v = e.value || '';
      atributos.preenchido = v.length ? String(v.length) : '0';
      if (e.type === 'checkbox' || e.type === 'radio') {
        atributos.marcado = e.checked ? 'sim' : 'nao';
      }
    }
    const no = {
      t: etiqueta.toLowerCase(),
      i: e.id || '',
      c: corta((e.className && e.className.baseVal !== undefined
                ? e.className.baseVal : e.className) || '', 90),
      a: atributos,
      x: Math.round(r.x), y: Math.round(r.y),
      l: Math.round(r.width), h: Math.round(r.height),
      v: !!(r.width > 0 && r.height > 0),
      p: e.parentElement ? (e.parentElement.tagName.toLowerCase()
                            + (e.parentElement.id ? '#' + e.parentElement.id : '')) : '',
    };
    if (COM_TEXTO.has(etiqueta)) {
      // So o texto PROPRIO, e curto. Texto longo e conteudo, nao rotulo.
      let proprio = '';
      for (const filho of e.childNodes) {
        if (filho.nodeType === 3) proprio += filho.nodeValue;
      }
      proprio = corta(proprio, 60);
      if (!proprio) proprio = corta(e.textContent, 60);
      no.tx = proprio;
    }
    saida.push(no);
  }
  const mensagens = [];
  const SELETORES_DE_MENSAGEM = [
    '[role=alert]', '[role=status]', '.p-message', '.p-toast-detail',
    '.alert', '.mensagem', '.erro', '.empty-message', '.p-datatable-emptymessage',
    '.mat-error', '.invalid-feedback', '.text-danger',
  ];
  for (const seletor of SELETORES_DE_MENSAGEM) {
    let achados = [];
    try { achados = document.querySelectorAll(seletor); } catch (_) { continue; }
    for (const e of achados) {
      const r = e.getBoundingClientRect();
      const texto = corta(e.textContent, 160);
      if (texto) mensagens.push({ seletor: seletor, texto: texto,
                                  visivel: !!(r.width > 0 && r.height > 0) });
    }
  }
  return {
    endereco: location.href,
    titulo: corta(document.title, 120),
    area: { l: document.documentElement.clientWidth,
            h: document.documentElement.clientHeight },
    desenho: { l: document.documentElement.scrollWidth,
               h: document.documentElement.scrollHeight },
    rolagem: { x: Math.round(window.scrollX), y: Math.round(window.scrollY) },
    nos: saida,
    cortado: cortado,
    total: todos.length,
    mensagens: mensagens,
  };
}"""


def gravacao_ligada() -> bool:
    return bool((os.environ.get(VARIAVEL_DA_GRAVACAO) or "").strip())


def ligar_gravacao() -> None:
    os.environ[VARIAVEL_DA_GRAVACAO] = "1"


def pasta_das_telas():
    """Onde as telas ficam: ao lado das consultas, no diretorio de estado."""
    from .core.estado import diretorio_estado

    pasta = diretorio_estado() / "telas"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _limpar(valor: Any) -> Any:
    """Segunda rede: todo texto que entra no arquivo passa pelo filtro."""
    from .portal import sem_dado_de_processo

    if isinstance(valor, str):
        return sem_dado_de_processo(valor)
    if isinstance(valor, list):
        return [_limpar(x) for x in valor]
    if isinstance(valor, dict):
        return {k: _limpar(v) for k, v in valor.items()}
    return valor


def esqueleto_da_tela(pagina: Any) -> Optional[dict]:
    """A forma desta tela, ja filtrada, ou None quando nao da para ler."""
    from .portal import endereco_sem_dado

    try:
        bruto = pagina.evaluate(JS_DO_ESQUELETO)
    except Exception as erro:
        return {"erro": f"{type(erro).__name__}", "nos": [], "mensagens": []}
    if not isinstance(bruto, dict):
        return {"erro": "a tela devolveu algo que nao e esqueleto",
                "nos": [], "mensagens": []}
    bruto["endereco"] = endereco_sem_dado(bruto.get("endereco") or "", 120)
    return _limpar(bruto)


def _quadros(pagina: Any) -> list:
    from .portal import quadros_do_mesmo_portal

    try:
        return quadros_do_mesmo_portal(pagina)
    except Exception:
        return []


def gravar_a_tela(pagina: Any, rotulo: str) -> Optional[str]:
    """Grava esta tela e os quadros dela, e devolve o caminho do arquivo.

    Nao levanta erro nunca. Gravar e instrumento: se falhar, a corrida segue,
    porque a corrida e que e o objetivo.
    """
    if not gravacao_ligada():
        return None
    import json
    from datetime import datetime, timezone

    try:
        marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")[:-4]
        apelido = "".join(c if c.isalnum() or c in "-_" else "-"
                          for c in (rotulo or "tela").lower())[:60]
        dados = {
            "rotulo": rotulo,
            "momento": marca,
            "tela": esqueleto_da_tela(pagina),
            "quadros": [],
        }
        for quadro in _quadros(pagina):
            dados["quadros"].append(esqueleto_da_tela(quadro))
        destino = pasta_das_telas() / f"{marca}-{apelido}.json"
        destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        print(f"      Tela gravada: {destino}")
        return str(destino)
    except Exception as erro:
        print(f"      [ATENCAO] Nao foi possivel gravar a tela {rotulo!r}: "
              f"{type(erro).__name__}.")
        return None


# ---------------------------------------------------------------------------
# Impressao de uma tela gravada
#
# A gravacao so vale se der para PERGUNTAR a ela sem abrir o portal de novo.
# Uma tela inteira nao cabe numa conversa; uma fatia dela cabe. Por isso a
# impressao e por parte, com filtro por texto.
# ---------------------------------------------------------------------------

# Quantos controles com o MESMO rotulo ainda contam como controle. Acima disso
# sao itens de lista, e o rotulo de cada um e conteudo do processo. Mesma regra
# de `linhas_de_botoes`, pela mesma razao: a arvore do Visualizador e feita de
# botoes cujo rotulo e o proprio andamento.
TETO_DE_IGUAIS = 3

PARTES = ("resumo", "botoes", "campos", "mensagens", "tabelas", "nos")

CLICAVEIS = ("button", "a")
CONTROLES = ("input", "select", "textarea")


def _onde(no: dict) -> str:
    marca = "na tela" if no.get("v") else "sem caixa"
    return f"x={no.get('x', 0)} y={no.get('y', 0)} {marca}"


def _alvo(no: dict) -> str:
    if no.get("i"):
        return f"#{no['i']}"
    nome = (no.get("a") or {}).get("name")
    if nome:
        return f"[name={nome}]"
    classe = (no.get("c") or "").split(" ")[0]
    return f".{classe}" if classe else "(sem id)"


def _rotulo_do_no(no: dict) -> str:
    atributos = no.get("a") or {}
    for chave in ("aria-label", "title", "placeholder"):
        if atributos.get(chave):
            return str(atributos[chave])
    return ""


def _casa(no: dict, procurado: str) -> bool:
    if not procurado:
        return True
    alvo = procurado.lower()
    # O pai entra porque linha e celula nao tem identificador proprio: quem
    # quer ver o conteudo de `#pn_id_1-table` procura pelo nome da tabela, e
    # sem isto nao acharia nenhuma das linhas dela.
    pedacos = [no.get("i") or "", no.get("c") or "", no.get("tx") or "",
               _rotulo_do_no(no), no.get("t") or "", no.get("p") or ""]
    pedacos += [str(v) for v in (no.get("a") or {}).values()]
    return any(alvo in str(p).lower() for p in pedacos)


def _linhas_de_clicaveis(nos: list, contem: str,
                         rotulos: bool = False) -> list[str]:
    from collections import OrderedDict

    from .portal import sem_dado_de_processo

    escolhidos = [n for n in nos
                  if (n.get("t") in CLICAVEIS
                      or (n.get("a") or {}).get("role") == "button")
                  and _casa(n, contem)]
    grupos: "OrderedDict[str, list]" = OrderedDict()
    for no in escolhidos:
        grupos.setdefault((no.get("tx") or "")[:50], []).append(no)

    saida = [f"  CLICAVEIS ({len(escolhidos)}, "
             f"{sum(1 for n in escolhidos if n.get('v'))} na tela):"]
    if not escolhidos:
        saida.append("    (nenhum)")
    for texto, membros in grupos.items():
        if len(membros) > TETO_DE_IGUAIS and not rotulos:
            saida.append(
                f"    {sem_dado_de_processo(texto)!r} x{len(membros)}  "
                f"({sum(1 for n in membros if n.get('v'))} na tela)  "
                "(rotulos omitidos: grupo grande e lista, e rotulo de item e "
                "conteudo do processo. Use --rotulos para ve-los)")
            continue
        if len(membros) > TETO_DE_IGUAIS:
            # Pedido explicito. Quatro botoes mudos numa lista de resultado sao
            # a acao de cada linha, e saber o nome deles e o que falta; cem
            # botoes mudos numa arvore de documentos sao o processo inteiro. O
            # teto de cinco atende o primeiro caso sem servir o segundo, e o
            # aviso fica na propria saida, para quem for colar decidir vendo.
            saida.append(
                f"    {sem_dado_de_processo(texto)!r} x{len(membros)}  "
                f"({sum(1 for n in membros if n.get('v'))} na tela)  "
                "ATENCAO: rotulos abertos a pedido, podem conter dado do "
                "processo. Confira antes de colar.")
            for no in membros[:5]:
                rotulo = sem_dado_de_processo(_rotulo_do_no(no))
                # A ETIQUETA entra aqui. Em 16/10/2026 cinco linhas de
                # resultado sairam como `.ng-tns-c816854197-0` e eu nao tinha
                # como saber se eram `a`, `button` ou `td`, que e exatamente o
                # que decide por onde procura-las.
                saida.append(f"      <{no.get('t')}> {_alvo(no):30s} "
                             f"rotulo={rotulo!r}  dentro de {no.get('p') or '-'}"
                             f"  {_onde(no)}")
            if len(membros) > 5:
                saida.append(f"      (+{len(membros) - 5} nao mostrados)")
            continue
        for no in membros:
            rotulo = _rotulo_do_no(no)
            marca = f"  rotulo={sem_dado_de_processo(rotulo)!r}" if rotulo else ""
            saida.append(f"    <{no.get('t')}> {_alvo(no):32s} "
                         f"{sem_dado_de_processo(texto)!r}{marca}  {_onde(no)}")
    return saida


def _linhas_de_controles(nos: list, contem: str) -> list[str]:
    from .portal import sem_dado_de_processo

    escolhidos = [n for n in nos if n.get("t") in CONTROLES and _casa(n, contem)]
    saida = [f"  CONTROLES ({len(escolhidos)}, "
             f"{sum(1 for n in escolhidos if n.get('v'))} na tela):"]
    if not escolhidos:
        saida.append("    (nenhum)")
    for no in escolhidos:
        atributos = no.get("a") or {}
        marcas = [f"<{no.get('t')}>", f"tipo={atributos.get('type') or '-'}"]
        rotulo = _rotulo_do_no(no)
        if rotulo:
            marcas.append(f"rotulo={sem_dado_de_processo(rotulo)!r}")
        if atributos.get("marcado"):
            marcas.append(f"marcado={atributos['marcado']}")
        # Quantos caracteres ha, nunca quais.
        if atributos.get("preenchido") and atributos["preenchido"] != "0":
            marcas.append(f"preenchido com {atributos['preenchido']} caractere(s)")
        if atributos.get("disabled") is not None:
            marcas.append("desabilitado")
        saida.append(f"    {_alvo(no):36s} {' '.join(marcas)}  {_onde(no)}")
    return saida


def _linhas_de_tabelas(nos: list, contem: str) -> list[str]:
    from .portal import sem_dado_de_processo

    tabelas = [n for n in nos if n.get("t") == "table" and _casa(n, contem)]
    cabecalhos = [n for n in nos if n.get("t") == "th"]
    linhas = [n for n in nos if n.get("t") == "tr"]
    saida = [f"  TABELAS ({len(tabelas)}), linhas no total: {len(linhas)}:"]
    if not tabelas:
        saida.append("    (nenhuma)")
    for tabela in tabelas:
        saida.append(f"    {_alvo(tabela):36s} classe={(tabela.get('c') or '-')[:50]}"
                     f"  {_onde(tabela)}")
    textos = [sem_dado_de_processo(c.get("tx") or "") for c in cabecalhos]
    textos = [x for x in textos if x]
    if textos:
        saida.append(f"  CABECALHOS DE COLUNA ({len(textos)}):")
        saida.append("    " + " | ".join(textos[:40]))
    return saida


def _linhas_de_mensagens(tela: dict) -> list[str]:
    from .portal import sem_dado_de_processo

    mensagens = tela.get("mensagens") or []
    saida = [f"  MENSAGENS DA TELA ({len(mensagens)}):"]
    if not mensagens:
        saida.append("    (nenhuma)")
    for mensagem in mensagens:
        marca = "visivel" if mensagem.get("visivel") else "oculta"
        saida.append(f"    [{marca}] {mensagem.get('seletor')}: "
                     f"{sem_dado_de_processo(mensagem.get('texto') or '')}")
    return saida


def _linhas_de_nos(nos: list, contem: str, teto: int) -> list[str]:
    from .portal import sem_dado_de_processo

    escolhidos = [n for n in nos if _casa(n, contem)]
    saida = [f"  NOS ({len(escolhidos)} de {len(nos)}):"]
    for no in escolhidos[:teto]:
        texto = sem_dado_de_processo(no.get("tx") or "")
        saida.append(
            f"    <{no.get('t')}> {_alvo(no):30s} classe={(no.get('c') or '-')[:40]}"
            + (f" texto={texto!r}" if texto else "")
            + f"  dentro de {no.get('p') or '-'}  {_onde(no)}")
    if len(escolhidos) > teto:
        saida.append(f"    (+{len(escolhidos) - teto} nao mostrados)")
    return saida


def _cabecalho(tela: dict, titulo: str) -> list[str]:
    if tela.get("erro"):
        return [f"  {titulo}: ILEGIVEL ({tela['erro']})"]
    area = tela.get("area") or {}
    desenho = tela.get("desenho") or {}
    rolagem = tela.get("rolagem") or {}
    return [
        f"  {titulo}",
        f"    endereco: {tela.get('endereco') or '(sem)'}",
        f"    titulo: {tela.get('titulo') or '(sem)'}",
        f"    area {area.get('l', 0)}x{area.get('h', 0)}, "
        f"desenho {desenho.get('l', 0)}x{desenho.get('h', 0)}, "
        f"rolagem em {rolagem.get('x', 0)},{rolagem.get('y', 0)}",
        f"    nos guardados: {len(tela.get('nos') or [])} de "
        f"{tela.get('total', 0)}" + ("  (CORTADO)" if tela.get("cortado") else ""),
    ]


def resolver_a_tela(caminho: str):
    """Aceita `ultima`, o nome solto do arquivo, ou o caminho inteiro.

    Escrito em 23/10/2026 porque o mesmo erro aconteceu TRES vezes com o mesmo
    advogado, e as tres foram minhas: a instrucao trazia um marcador de texto
    para ele substituir (`<nome>`), e ele colou o marcador. O Windows respondeu
    "Operador '<' reservado para uso futuro", que nao tem relacao visivel com o
    que ele estava fazendo.

    Marcador em linha de comando e erro a espera: a linha PARECE pronta. A
    correcao nao e escrever o aviso maior; e o comando saber se virar.

    `ultima` escolhe a tela mais recente pelo nome, que comeca com a marca de
    tempo em UTC e por isso ordena sozinho. Nome solto e procurado na pasta das
    telas. Caminho inteiro continua valendo.
    """
    import pathlib

    bruto = (caminho or "").strip().strip('"').strip("'")
    if bruto.lower() in ("ultima", "última", "last"):
        gravadas = sorted(pasta_das_telas().glob("*.json"))
        if gravadas:
            return gravadas[-1]
        return pasta_das_telas() / "nenhuma-tela-gravada.json"
    alvo = pathlib.Path(bruto).expanduser()
    if alvo.is_file():
        return alvo
    # Nome solto, sem pasta: procurar onde as telas moram.
    if alvo.parent in (pathlib.Path("."), pathlib.Path("")):
        vizinho = pasta_das_telas() / alvo.name
        if vizinho.is_file():
            return vizinho
    return alvo


def mostrar_tela(caminho: str, parte: str = "resumo", contem: str = "",
                 teto: int = 60, rotulos: bool = False) -> int:
    """Imprime uma fatia de uma tela gravada. Nunca abre navegador."""
    import json
    import pathlib
    import sys

    alvo = resolver_a_tela(caminho)
    try:
        dados = json.loads(alvo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Arquivo nao encontrado: {alvo}\n"
              "Confira o caminho. `justica-portal telas` lista os arquivos "
              "gravados, com o nome exato de cada um.", file=sys.stderr)
        return 1
    except OSError as erro:
        # Caminho invalido tem de sair como RECADO, e nao como rastro de pilha.
        # Em 16/10/2026 o advogado colou o marcador de texto que eu tinha
        # deixado na instrucao, e o Windows respondeu `Invalid argument` com
        # dezoito linhas de traceback: a mensagem util ficou enterrada, e o
        # erro parecia do programa quando era do caminho.
        print(f"Nao foi possivel abrir {alvo}: {erro.strerror or type(erro).__name__}.\n"
              "Confira o caminho. `justica-portal telas` lista os arquivos "
              "gravados, com o nome exato de cada um.", file=sys.stderr)
        return 1
    except json.JSONDecodeError as erro:
        print(f"O arquivo nao e JSON valido: {erro.msg} (linha {erro.lineno}).",
              file=sys.stderr)
        return 1
    if not isinstance(dados, dict) or "tela" not in dados:
        print("Este arquivo nao e uma tela gravada.", file=sys.stderr)
        return 1
    if parte not in PARTES:
        print(f"--parte {parte!r} nao existe. Use uma de: "
              f"{', '.join(PARTES)}.", file=sys.stderr)
        return 1

    linhas = ["", f"TELA GRAVADA: {dados.get('rotulo') or '(sem rotulo)'}"
                 f"  ({dados.get('momento') or '-'})", "=" * 64]
    telas = [(dados.get("tela") or {}, "DOCUMENTO DE FORA")]
    for ordem, quadro in enumerate(dados.get("quadros") or [], start=1):
        telas.append((quadro or {}, f"QUADRO EMBUTIDO {ordem}"))

    for tela, titulo in telas:
        linhas += _cabecalho(tela, titulo)
        nos = tela.get("nos") or []
        if parte in ("resumo", "mensagens"):
            linhas += _linhas_de_mensagens(tela)
        if parte in ("resumo", "tabelas"):
            linhas += _linhas_de_tabelas(nos, contem)
        if parte in ("resumo", "campos"):
            linhas += _linhas_de_controles(nos, contem)
        if parte in ("resumo", "botoes"):
            linhas += _linhas_de_clicaveis(nos, contem, rotulos)
        if parte == "nos":
            linhas += _linhas_de_nos(nos, contem, teto)
        linhas.append("")
    print("\n".join(linhas))
    return 0


def listar_telas(teto: int = 40) -> int:
    """As telas gravadas, da mais recente para a mais antiga."""
    import sys

    try:
        pasta = pasta_das_telas()
    except Exception as erro:
        print(f"Nao foi possivel abrir a pasta das telas: {type(erro).__name__}.",
              file=sys.stderr)
        return 1
    arquivos = sorted(pasta.glob("*.json"), reverse=True)
    if not arquivos:
        print(f"Nenhuma tela gravada em {pasta}.\n"
              "Rode a consulta com --gravar-telas para comecar a gravar.")
        return 0
    print(f"\nTELAS GRAVADAS em {pasta} ({len(arquivos)}):")
    for arquivo in arquivos[:teto]:
        print(f"  {arquivo.name}")
    if len(arquivos) > teto:
        print(f"  (+{len(arquivos) - teto})")
    print()
    return 0
