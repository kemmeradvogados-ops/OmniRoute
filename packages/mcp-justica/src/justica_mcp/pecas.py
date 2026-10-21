"""Leitura das pecas que ja estao gravadas na pasta do processo.

ESTE MODULO DEVOLVE CONTEUDO DO PROCESSO. Ele e a unica parte do programa que
faz isso, e foi escrito depois de tudo o mais justamente por causa disso.

O resto deste pacote passa cada relato por `sem_dado_de_processo` e so imprime
ESTRUTURA: contagem, molde, identificador, geometria. A razao esta registrada em
06/10/2026, quando o andamento de um processo foi parar numa conversa. Aqui a
regra nao muda, ela so se aplica em outro lugar: o conteudo volta para quem
CHAMOU a ferramenta, que e o assistente rodando na maquina do advogado, e nunca
e impresso no terminal nem passa por relato.

Por isso o caminho de linha de comando grava em ARQUIVO e imprime so o caminho e
as contagens. Quem le o texto e quem ja tem direito de ler os autos.

A leitura e da PASTA, nao do portal. Ler do portal custa uma autenticacao por
vez, dezenas de segundos, e tem teto por hora; o arquivo em disco se rele
quantas vezes for preciso, sem portal e sem espera. Analise e iterativa por
natureza, entao disco ganha de tela com folga.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

# Quanto texto volta numa chamada so. Peca de 131 folhas passa facil de um
# milhao de caracteres, e devolver isso de uma vez estoura o contexto de quem
# chamou sem aviso nenhum. Cortar e aceitavel; cortar EM SILENCIO nao e, e por
# isso a resposta sempre diz se cortou e onde parou.
TETO_DE_CARACTERES = 200_000

# Abaixo disto, a folha nao tem camada de texto: e imagem digitalizada. A
# diferenca entre "a folha nao diz nada" e "eu nao consegui ler a folha" e a
# mesma diferenca de sempre, e ela vale decisao.
MINIMO_POR_FOLHA = 20

def peca_do_nome(nome: str) -> Optional[int]:
    """A pagina inicial que o nome do arquivo carrega, se carregar.

    Delega ao acervo de proposito. Duas copias deste padrao divergem no
    primeiro conserto, e divergir aqui significa a leitura abrir um documento e
    a cobertura medir outro.
    """
    from .core.acervo import pagina_do_nome

    return pagina_do_nome(nome)


def pasta_do_processo(numero_digitos: str, numero_formatado: str) -> Path:
    """A pasta de copias deste processo, pelo mesmo caminho que o acervo usa."""
    from .core.acervo import carregar_indice

    return carregar_indice(numero_digitos, numero_formatado).pasta


def pecas_da_pasta(numero_digitos: str, numero_formatado: str) -> dict:
    """O que esta gravado na pasta, SEM conteudo nenhum.

    So nome de arquivo, pagina inicial, quantas folhas e quantos bytes. Serve
    para o assistente escolher o que ler antes de ler, e para o advogado ver o
    tamanho do que tem.
    """
    from .core.acervo import contar_paginas

    pasta = pasta_do_processo(numero_digitos, numero_formatado)
    if not pasta.is_dir():
        return {"pasta": str(pasta), "existe": False, "pecas": [],
                "folhas": 0,
                "aviso": "A pasta de copias deste processo nao existe. Nada "
                         "foi baixado ainda."}

    pecas = []
    for arquivo in sorted(pasta.glob("*.pdf")):
        try:
            tamanho = arquivo.stat().st_size
        except OSError:
            continue
        if tamanho <= 0:
            continue
        pecas.append({
            "peca": peca_do_nome(arquivo.name),
            "arquivo": arquivo.name,
            "folhas": contar_paginas(arquivo),
            "bytes": tamanho,
        })
    pecas.sort(key=lambda p: (p["peca"] is None, p["peca"] or 0))
    return {"pasta": str(pasta), "existe": True, "pecas": pecas,
            "folhas": sum(p["folhas"] or 0 for p in pecas)}


def achar_a_peca(pasta: Path, peca: int) -> Optional[Path]:
    """O arquivo da peca que comeca nesta pagina, se houver.

    Pelo mesmo criterio que o download usa para pular o que ja esta em disco:
    o nome comeca por `<chave>-pagina<N>-`. Casar por `-pagina<N>-` evita que a
    peca 1342 ache a 13420.
    """
    try:
        achados = sorted(pasta.glob("*.pdf"))
    except OSError:
        return None
    for caminho in achados:
        if peca_do_nome(caminho.name) != peca:
            continue
        try:
            if caminho.is_file() and caminho.stat().st_size > 0:
                return caminho
        except OSError:
            continue
    return None


def texto_das_folhas(arquivo: Path, de: int, ate: Optional[int],
                     teto: int = TETO_DE_CARACTERES) -> dict:
    """O texto das folhas pedidas, e o que nao deu para ler.

    Folha que levanta na extracao nao derruba a leitura inteira: ela entra em
    `folhas_ilegiveis` e as outras continuam. Peca grande com uma folha
    corrompida ainda vale muito mais que recusa.
    """
    try:
        from pypdf import PdfReader
    except Exception:
        return {"erro": "pypdf nao esta instalado neste ambiente."}

    try:
        leitor = PdfReader(str(arquivo))
        total = len(leitor.pages)
    except Exception as erro:
        return {"erro": f"O arquivo nao pode ser aberto ({type(erro).__name__})."}

    inicio = max(1, int(de or 1))
    fim = total if ate is None else min(total, max(inicio, int(ate)))
    if inicio > total:
        return {"erro": f"A peca tem {total} folha(s) e a leitura foi pedida a "
                        f"partir da folha {inicio}."}

    partes: list = []
    sem_texto: list = []
    ilegiveis: list = []
    caracteres = 0
    cortou_em: Optional[int] = None
    for numero in range(inicio, fim + 1):
        try:
            bruto = leitor.pages[numero - 1].extract_text() or ""
        except Exception:
            ilegiveis.append(numero)
            continue
        limpo = bruto.strip()
        if len(limpo) < MINIMO_POR_FOLHA:
            sem_texto.append(numero)
            continue
        if caracteres + len(limpo) > teto:
            cortou_em = numero
            break
        partes.append(f"--- folha {numero} ---\n{limpo}")
        caracteres += len(limpo)

    lidas = fim - inicio + 1 - len(sem_texto) - len(ilegiveis)
    resposta: dict = {
        "folhas_na_peca": total,
        "de": inicio,
        "ate": (cortou_em - 1) if cortou_em else fim,
        "texto": "\n\n".join(partes),
        "caracteres": caracteres,
        "folhas_com_texto": len(partes),
        "folhas_sem_texto": sem_texto,
        "folhas_ilegiveis": ilegiveis,
        "cortado": cortou_em is not None,
    }
    if cortou_em is not None:
        resposta["aviso"] = (
            f"O texto foi CORTADO na folha {cortou_em}: o teto de {teto} "
            f"caracteres por chamada foi atingido. Peca a continuacao com "
            f"de={cortou_em}.")
    elif not partes and (sem_texto or ilegiveis):
        # A diferenca que vale decisao: nao e que a peca nao diga nada.
        resposta["aviso"] = (
            f"Nenhuma das {fim - inicio + 1} folha(s) pedidas tem camada de "
            "texto. Isto NAO significa que a peca esteja em branco: significa "
            "que ela e imagem digitalizada, e ler o conteudo dela exigiria "
            "reconhecimento optico, que este programa nao faz.")
    elif sem_texto:
        resposta["aviso"] = (
            f"{len(sem_texto)} folha(s) sem camada de texto (imagem "
            f"digitalizada): {sem_texto[:20]}. O que voltou e o texto das "
            f"outras {len(partes)}.")
    _ = lidas
    return resposta


def ler_peca(numero_digitos: str, numero_formatado: str, peca: int,
             de: int = 1, ate: Optional[int] = None,
             teto: int = TETO_DE_CARACTERES) -> dict:
    """O texto de UMA peca da pasta. Devolve conteudo do processo."""
    pasta = pasta_do_processo(numero_digitos, numero_formatado)
    if not pasta.is_dir():
        return {"erro": "A pasta de copias deste processo nao existe. Nada "
                        "foi baixado ainda."}
    arquivo = achar_a_peca(pasta, peca)
    if arquivo is None:
        disponiveis = [p["peca"] for p in
                       pecas_da_pasta(numero_digitos, numero_formatado)["pecas"]
                       if p["peca"] is not None]
        return {"erro": f"Nenhuma peca gravada comeca na pagina {peca}.",
                "pecas_na_pasta": disponiveis[:40],
                "total_na_pasta": len(disponiveis)}

    lido = texto_das_folhas(arquivo, de, ate, teto)
    if "erro" in lido:
        return {"erro": lido["erro"], "arquivo": arquivo.name}
    lido["peca"] = peca
    lido["arquivo"] = arquivo.name
    return lido


# --------------------------- linha de comando ---------------------------
#
# O terminal NAO imprime o texto da peca. Ele grava em arquivo e imprime o
# caminho e as contagens, que e a mesma regra que a consulta ja segue desde
# 06/10/2026 ("O arquivo contem dado de cliente. Nao o cole em conversa
# nenhuma."). Quem le o texto e quem ja tem direito de ler os autos, na propria
# maquina.


def gravar_o_texto(numero_digitos: str, chave: str, peca: int,
                   texto: str) -> Any:
    """Grava o texto lido ao lado das consultas, e devolve o caminho."""
    from datetime import datetime, timezone

    from .core.estado import diretorio_estado

    pasta = diretorio_estado() / "consultas"
    pasta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = pasta / f"{chave}-peca{peca}-{marca}.txt"
    destino.write_text(texto, encoding="utf-8")
    return destino


def relatar_as_pecas(dados: dict, teto: int = 40) -> list:
    """A lista da pasta em linhas, sem conteudo nenhum."""
    if not dados.get("existe"):
        return [dados.get("aviso") or "A pasta nao existe."]
    pecas = dados.get("pecas") or []
    if not pecas:
        return [f"Pasta: {dados['pasta']}", "Nenhum PDF gravado nela."]
    linhas = [f"Pasta: {dados['pasta']}",
              f"{len(pecas)} peca(s), {dados.get('folhas') or 0} folha(s) "
              "somadas."]
    for item in pecas[:teto]:
        folhas = item.get("folhas")
        linhas.append(
            f"  peca {item['peca'] if item['peca'] is not None else '(?)'}"
            f"  {folhas if folhas is not None else '?'} folha(s)"
            f"  {item['bytes']} byte(s)")
    if len(pecas) > teto:
        linhas.append(f"  e mais {len(pecas) - teto} peca(s).")
    return linhas


def relatar_a_leitura(dados: dict, caminho: Any) -> list:
    """O resultado da leitura em linhas, SEM o texto."""
    linhas = [
        f"Peca {dados['peca']}, arquivo {dados['arquivo']}.",
        f"A peca tem {dados['folhas_na_peca']} folha(s). Foram lidas da "
        f"{dados['de']} a {dados['ate']}.",
        f"{dados['folhas_com_texto']} folha(s) com texto, "
        f"{dados['caracteres']} caractere(s).",
    ]
    if dados.get("folhas_sem_texto"):
        linhas.append(
            f"{len(dados['folhas_sem_texto'])} folha(s) SEM camada de texto "
            f"(imagem digitalizada): {dados['folhas_sem_texto'][:20]}. Elas nao "
            "estao em branco: este programa nao faz reconhecimento optico.")
    if dados.get("folhas_ilegiveis"):
        linhas.append(
            f"{len(dados['folhas_ilegiveis'])} folha(s) levantaram erro na "
            f"extracao: {dados['folhas_ilegiveis'][:20]}.")
    if dados.get("aviso"):
        linhas.append(dados["aviso"])
    if caminho is not None:
        linhas.append(f"Texto gravado em {caminho}")
        linhas.append("O arquivo contem dado de cliente. Nao o cole em "
                      "conversa nenhuma.")
    return linhas
