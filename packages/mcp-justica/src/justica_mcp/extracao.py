"""Extracao das tabelas da tela de processo do eproc.

Estrutura observada em campo em 21 de setembro de 2026, na Justica Federal do
Rio, tela `acao=processo_selecionar`:

    #tblEventos                  Evento, Data/Hora, Descricao, Usuario, Documentos
    #tblPartesERepresentantes    AUTOR, REU
    (sem id)                     Codigo, Descricao, Principal  (assuntos)

O que sai daqui e DADO DE CLIENTE. Por isso a extracao devolve estrutura e
quem chama decide o destino: o padrao e gravar em arquivo local e imprimir
apenas um resumo, em vez de despejar o conteudo no terminal, de onde ele
facilmente acaba colado em outro lugar.
"""

from __future__ import annotations

import re
from typing import Any, Optional


def _texto(elemento: Any) -> str:
    try:
        return re.sub(r"\s+", " ", (elemento.inner_text() or "")).strip()
    except Exception:
        return ""


def _linhas(tabela: Any) -> list[list[Any]]:
    return [linha.query_selector_all("td") for linha in tabela.query_selector_all("tr")]


def _por_id(pagina: Any, identificador: str) -> Optional[Any]:
    return pagina.query_selector(f"#{identificador}")


def _tabela_por_colunas(pagina: Any, esperadas: tuple[str, ...]) -> Optional[Any]:
    """Acha tabela pelos rotulos das colunas, para as que nao tem id."""
    alvo = {c.lower() for c in esperadas}
    for tabela in pagina.query_selector_all("table"):
        titulos = {_texto(t).lower() for t in tabela.query_selector_all("th")}
        if alvo.issubset(titulos):
            return tabela
    return None


def extrair_eventos(pagina: Any) -> list[dict[str, Any]]:
    """Movimentacoes do processo, da tabela `tblEventos`.

    A coluna Documentos traz os links dos arquivos. Aqui eles sao apenas
    LISTADOS, com rotulo e endereco: nada e aberto nem baixado.
    """
    tabela = _por_id(pagina, "tblEventos")
    if tabela is None:
        return []

    eventos = []
    for celulas in _linhas(tabela):
        if len(celulas) < 3:
            continue
        documentos = []
        for link in celulas[-1].query_selector_all("a"):
            rotulo = _texto(link)
            if rotulo:
                documentos.append({"rotulo": rotulo, "endereco": link.get_attribute("href")})
        eventos.append({
            "evento": _texto(celulas[0]),
            "data_hora": _texto(celulas[1]),
            "descricao": _texto(celulas[2]),
            "usuario": _texto(celulas[3]) if len(celulas) > 3 else None,
            "documentos": documentos,
        })
    return eventos


def extrair_partes(pagina: Any) -> list[dict[str, Any]]:
    """Partes e representantes.

    A tabela usa os polos como CABECALHO das colunas (AUTOR, REU), e nao como
    valor de uma coluna, entao cada celula pertence ao polo da sua posicao.
    """
    tabela = _por_id(pagina, "tblPartesERepresentantes")
    if tabela is None:
        return []

    polos = [_texto(t) for t in tabela.query_selector_all("th")]
    partes = []
    for celulas in _linhas(tabela):
        for posicao, celula in enumerate(celulas):
            conteudo = _texto(celula)
            if not conteudo:
                continue
            partes.append({
                "polo": polos[posicao] if posicao < len(polos) else None,
                "conteudo": conteudo,
            })
    return partes


def extrair_assuntos(pagina: Any) -> list[dict[str, Any]]:
    tabela = _tabela_por_colunas(pagina, ("código", "descrição"))
    if tabela is None:
        return []
    assuntos = []
    for celulas in _linhas(tabela):
        if len(celulas) < 2:
            continue
        assuntos.append({
            "codigo": _texto(celulas[0]),
            "descricao": _texto(celulas[1]),
            "principal": _texto(celulas[2]) if len(celulas) > 2 else None,
        })
    return assuntos


def extrair_processo(pagina: Any, numero: str) -> dict[str, Any]:
    eventos = extrair_eventos(pagina)
    partes = extrair_partes(pagina)
    assuntos = extrair_assuntos(pagina)
    documentos = sum(len(e["documentos"]) for e in eventos)
    return {
        "numero": numero,
        "titulo_da_pagina": pagina.title(),
        "endereco": pagina.url,
        "eventos": eventos,
        "partes": partes,
        "assuntos": assuntos,
        "totais": {
            "eventos": len(eventos),
            "partes": len(partes),
            "assuntos": len(assuntos),
            "documentos_listados": documentos,
        },
    }


def resumo(dados: dict[str, Any], *, ultimos: int = 5) -> list[str]:
    """Resumo seguro de imprimir: contagens e os eventos mais recentes.

    O conteudo completo fica no arquivo. Despejar 69 eventos no terminal
    convida a colar dado de cliente onde nao deve.
    """
    t = dados["totais"]
    linhas = [
        f"eventos: {t['eventos']}   partes: {t['partes']}   "
        f"assuntos: {t['assuntos']}   documentos listados: {t['documentos_listados']}",
    ]
    if dados["eventos"]:
        linhas.append(f"ultimos {min(ultimos, len(dados['eventos']))} evento(s):")
        for e in dados["eventos"][:ultimos]:
            docs = f"  [{len(e['documentos'])} doc]" if e["documentos"] else ""
            linhas.append(f"  {e['evento']:>5}  {e['data_hora']:<20} {e['descricao'][:52]}{docs}")
    return linhas
