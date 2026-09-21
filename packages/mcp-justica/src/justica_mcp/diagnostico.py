"""Diagnostico de campo: roda na maquina do escritorio e confronta o servidor
com os tribunais de verdade.

Existe porque o desenvolvimento ocorreu fora do Brasil, e as APIs do Conselho
Nacional de Justica bloqueiam por pais de origem. Tudo que depende de rede
ficou por confirmar. Este script confirma, e imprime um relatorio colavel.

Uso:
    justica-diagnostico              # relatorio seguro, sem conteudo de cliente
    justica-diagnostico --detalhe    # inclui o texto das publicacoes (so para voce)

Privacidade: por padrao imprime NOMES DE CAMPOS e contagens, nunca o teor das
publicacoes. Publicacao de Diario e publica, mas traz nome de parte e numero de
processo da carteira; o padrao seguro evita que isso va parar num chat sem que
voce tenha decidido.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

from .core.tribunais import TRIBUNAIS

LARGURA = 74


def titulo(texto: str) -> None:
    print("\n" + "=" * LARGURA)
    print(texto)
    print("=" * LARGURA)


def item(rotulo: str, valor: Any, ok: Optional[bool] = None) -> None:
    marca = "" if ok is None else ("[ok]   " if ok else "[FALHA] ")
    print(f"  {marca}{rotulo}: {valor}")


def mascarar(texto: Optional[str], detalhe: bool, limite: int = 90) -> str:
    if texto is None:
        return "(vazio)"
    if detalhe:
        return texto[:600]
    return f"<{len(texto)} caracteres, omitido; use --detalhe para ver>"


# --------------------------------------------------------------------------
# 1. Ambiente
# --------------------------------------------------------------------------

def checar_ambiente() -> None:
    titulo("1. AMBIENTE")
    item("Python", sys.version.split()[0], sys.version_info >= (3, 11))
    for modulo in ("mcp", "pydantic", "httpx", "yaml"):
        try:
            __import__(modulo)
            item(f"modulo {modulo}", "instalado", True)
        except ImportError:
            item(f"modulo {modulo}", "AUSENTE, rode: pip install -e .", False)
    chave = os.environ.get("DATAJUD_API_KEY", "")
    item(
        "DATAJUD_API_KEY",
        f"definida ({len(chave)} caracteres)" if chave else
        "NAO definida. Obtenha em https://datajud-wiki.cnj.jus.br/api-publica/acesso/",
        bool(chave),
    )


# --------------------------------------------------------------------------
# 2. Testes offline
# --------------------------------------------------------------------------

def rodar_testes() -> None:
    titulo("2. TESTES OFFLINE (nao dependem de rede)")
    raiz = Path(__file__).resolve().parents[2]
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(raiz / "tests"), "-q", "--no-header"],
            capture_output=True, text=True, timeout=300, cwd=raiz,
        )
        saida = (r.stdout or "") + (r.stderr or "")
        ultima = [l for l in saida.strip().splitlines() if l.strip()][-1] if saida.strip() else "(sem saida)"
        item("resultado", ultima, r.returncode == 0)
        if r.returncode != 0:
            print("\n".join(saida.splitlines()[-25:]))
    except FileNotFoundError:
        item("pytest", "nao instalado. Rode: pip install -e '.[dev]'", False)
    except subprocess.TimeoutExpired:
        item("pytest", "estourou o tempo limite", False)


# --------------------------------------------------------------------------
# 3. Diario de Justica Eletronico Nacional
# --------------------------------------------------------------------------

async def checar_djen(oab: str, uf: str, dias: int, detalhe: bool) -> None:
    titulo("3. DIARIO DE JUSTICA ELETRONICO NACIONAL (sem autenticacao)")
    base = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
    fim = date.today()
    inicio = fim - timedelta(days=dias)

    print(f"  Consulta: inscricao {oab}/{uf}, ultimos {dias} dias corridos.\n")
    async with httpx.AsyncClient(timeout=45) as cliente:
        try:
            r = await cliente.get(base, params={
                "numeroOab": oab, "ufOab": uf,
                "dataDisponibilizacaoInicio": inicio.isoformat(),
                "dataDisponibilizacaoFim": fim.isoformat(),
                "pagina": 1, "itensPorPagina": 5,
            }, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            item("conexao", f"falhou: {type(exc).__name__}: {exc}", False)
            return

        item("HTTP", r.status_code, r.status_code == 200)
        if r.status_code == 403:
            # Inspeciona o corpo INTEIRO: a mensagem do CloudFront sobre pais
            # aparece por volta do caractere 400, depois do cabecalho HTML.
            corpo = r.text.lower()
            if "from your country" in corpo or "cloudfront" in corpo:
                item("causa", "BLOQUEIO POR PAIS. Esta maquina nao tem saida brasileira.", False)
                print("      Confirme que o computador esta no Brasil e sem VPN estrangeira.")
            else:
                item("causa", f"403 sem mencao a pais: {r.text[:200]}", False)
            return
        if r.status_code != 200:
            item("corpo", r.text[:300], False)
            return

        try:
            dados = r.json()
        except ValueError:
            item("formato", f"resposta nao e JSON: {r.text[:200]}", False)
            return

        item("chaves do topo", list(dados.keys()) if isinstance(dados, dict) else f"lista de {len(dados)}")
        itens = dados.get("items") if isinstance(dados, dict) else dados
        item("total informado", dados.get("count") if isinstance(dados, dict) else "n/d")
        item("itens nesta pagina", len(itens or []))

        if isinstance(dados, dict) and isinstance(dados.get("count"), int) and dados["count"] >= 10000:
            item("ATENCAO no total", "contagem saturada em 10000, o total real e maior ou igual", False)

        if itens:
            print("\n  >>> CAMPOS DE UM ITEM:")
            for chave, valor in (itens[0] or {}).items():
                tipo = type(valor).__name__
                if chave in ("texto",):
                    amostra = mascarar(valor if isinstance(valor, str) else None, detalhe)
                elif isinstance(valor, (dict, list)):
                    amostra = f"{tipo} com {len(valor)} elemento(s)"
                else:
                    amostra = str(valor)[:70]
                print(f"      {chave:32s} ({tipo:5s}) = {amostra}")

            # ---- A pergunta decisiva: o filtro de inscricao foi aplicado? ----
            print("\n  >>> O FILTRO DE INSCRICAO NA ORDEM FOI APLICADO?")
            alvo = "".join(c for c in oab if c.isdigit()).lstrip("0")
            com_oab = 0
            for it in itens:
                bruto = json.dumps(it.get("destinatarioadvogados") or [], ensure_ascii=False)
                digitos = "".join(c if c.isdigit() else " " for c in bruto).split()
                if any(d.lstrip("0") == alvo for d in digitos):
                    com_oab += 1
            item(f"itens que citam a inscricao {oab}", f"{com_oab} de {len(itens)}", com_oab == len(itens))
            if com_oab < len(itens):
                print("       O filtro pode nao estar sendo aplicado como esperado.")

            tribunais = {}
            for it in itens:
                sigla = it.get("siglaTribunal") or "?"
                tribunais[sigla] = tribunais.get(sigla, 0) + 1
            item("tribunais nesta amostra", ", ".join(f"{k}={v}" for k, v in sorted(tribunais.items())))

            advogados = (itens[0] or {}).get("destinatarioadvogados") or []
            if advogados and isinstance(advogados[0], dict):
                print(f"      campos de destinatarioadvogados[0]: {list(advogados[0].keys())}")
            destinatarios = (itens[0] or {}).get("destinatarios") or []
            if destinatarios and isinstance(destinatarios[0], dict):
                print(f"      campos de destinatarios[0]:         {list(destinatarios[0].keys())}")
        else:
            print("\n  Nenhuma publicacao na janela. Isso NAO valida os campos;")
            print("  repita com --dias 30 para aumentar a chance de retorno.")


async def checar_siglas_djen() -> None:
    titulo("4. SIGLAS DO DIARIO POR TRIBUNAL (pendencia do README)")
    base = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
    fim = date.today()
    inicio = fim - timedelta(days=3)
    async with httpx.AsyncClient(timeout=45) as cliente:
        for t in TRIBUNAIS.values():
            try:
                r = await cliente.get(base, params={
                    "siglaTribunal": t.sigla_djen,
                    "dataDisponibilizacaoInicio": inicio.isoformat(),
                    "dataDisponibilizacaoFim": fim.isoformat(),
                    "pagina": 1, "itensPorPagina": 1,
                }, headers={"Accept": "application/json"})
                if r.status_code != 200:
                    item(f"{t.codigo} (sigla {t.sigla_djen})", f"HTTP {r.status_code}", False)
                    continue
                d = r.json()
                itens_t = (d.get("items") or []) if isinstance(d, dict) else []
                if not itens_t:
                    item(f"{t.codigo} (sigla {t.sigla_djen})", "nenhum item devolvido", False)
                    print("         sigla possivelmente errada ou periodo sem publicacao")
                else:
                    # A contagem satura em 10000 e por isso nao valida nada.
                    # O que valida e a sigla do item que voltou.
                    devolvida = itens_t[0].get("siglaTribunal")
                    confere = devolvida == t.sigla_djen
                    item(f"{t.codigo} (sigla {t.sigla_djen})",
                         f"item devolvido e do tribunal {devolvida}", confere)
                    if not confere:
                        print(f"         FILTRO NAO APLICADO: pedi {t.sigla_djen}, veio {devolvida}")
            except httpx.HTTPError as exc:
                item(f"{t.codigo} (sigla {t.sigla_djen})", f"erro: {type(exc).__name__}", False)
            await asyncio.sleep(0.5)  # respeita o espacamento recomendado


# --------------------------------------------------------------------------
# 5. DataJud
# --------------------------------------------------------------------------

async def checar_datajud(numero_exemplo: Optional[str], detalhe: bool) -> None:
    titulo("5. DATAJUD, ALIAS POR TRIBUNAL (pendencia do README)")
    chave = os.environ.get("DATAJUD_API_KEY", "")
    if not chave:
        item("chave", "ausente, secao pulada", False)
        return

    cabecalhos = {"Authorization": f"APIKey {chave}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=45) as cliente:
        for t in TRIBUNAIS.values():
            url = f"https://api-publica.datajud.cnj.jus.br/{t.alias_datajud}/_search"
            try:
                r = await cliente.post(url, headers=cabecalhos,
                                       json={"query": {"match_all": {}}, "size": 1})
                if r.status_code != 200:
                    item(f"{t.codigo} ({t.alias_datajud})", f"HTTP {r.status_code}: {r.text[:110]}", False)
                    await asyncio.sleep(0.5)
                    continue
                d = r.json()
                acertos = d.get("hits", {}).get("hits", [])
                item(f"{t.codigo} ({t.alias_datajud})", f"alias responde, {len(acertos)} registro(s)", True)
                if acertos and t.codigo == "TJRJ":
                    print("\n  >>> CAMPOS DE _source (preciso para conferir o mapeamento):")
                    for chave_campo, valor in (acertos[0].get("_source") or {}).items():
                        tipo = type(valor).__name__
                        amostra = (f"{tipo} com {len(valor)} elemento(s)"
                                   if isinstance(valor, (dict, list)) else str(valor)[:60])
                        print(f"      {chave_campo:28s} ({tipo:5s}) = {amostra}")
                    print()
            except httpx.HTTPError as exc:
                item(f"{t.codigo} ({t.alias_datajud})", f"erro: {type(exc).__name__}", False)
            await asyncio.sleep(0.5)

    if numero_exemplo:
        await checar_processo_real(numero_exemplo, cabecalhos, detalhe)


async def checar_processo_real(numero: str, cabecalhos: dict[str, str], detalhe: bool) -> None:
    titulo("6. CONSULTA A UM PROCESSO REAL")
    from .core.cnj import NumeroCNJInvalido, parse_numero
    from .core.tribunais import TribunalForaDoEscopo, identificar_tribunal

    try:
        n = parse_numero(numero)
        t = identificar_tribunal(n.chave_segmento_tribunal)
    except (NumeroCNJInvalido, TribunalForaDoEscopo) as exc:
        item("numero", str(exc), False)
        return

    item("numero", n.formatado, True)
    item("tribunal", f"{t.codigo}, alias {t.alias_datajud}")
    url = f"https://api-publica.datajud.cnj.jus.br/{t.alias_datajud}/_search"
    async with httpx.AsyncClient(timeout=45) as cliente:
        r = await cliente.post(url, headers=cabecalhos, json={
            "query": {"match": {"numeroProcesso": n.apenas_digitos}}, "size": 1,
        })
    if r.status_code != 200:
        item("HTTP", f"{r.status_code}: {r.text[:140]}", False)
        return
    acertos = r.json().get("hits", {}).get("hits", [])
    if not acertos:
        item("resultado", "processo nao localizado na base nacional", False)
        print("      Pode ser sigiloso, recem distribuido, ou de outro tribunal.")
        return
    f = acertos[0].get("_source", {})
    movimentos = f.get("movimentos") or []
    item("classe", (f.get("classe") or {}).get("nome"), True)
    item("orgao julgador", (f.get("orgaoJulgador") or {}).get("nome"))
    item("grau", f.get("grau"))
    item("nivel de sigilo", f.get("nivelSigilo"))
    item("movimentos", len(movimentos), len(movimentos) > 0)
    item("tem campo de partes?", "sim" if f.get("partes") else "nao (esperado: nao)")
    if movimentos and detalhe:
        recente = sorted(movimentos, key=lambda m: m.get("dataHora") or "", reverse=True)[0]
        item("movimento mais recente", f"{recente.get('dataHora')} {recente.get('nome')}")


# --------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Diagnostico de campo do justica-mcp")
    p.add_argument("--oab", default=os.environ.get("JUSTICA_OAB_NUMERO", "218174"))
    p.add_argument("--uf", default=os.environ.get("JUSTICA_OAB_UF", "RJ"))
    p.add_argument("--dias", type=int, default=7, help="janela retroativa em dias corridos")
    p.add_argument("--processo", default=None, help="numero para consulta real, opcional")
    p.add_argument("--detalhe", action="store_true",
                   help="inclui teor das publicacoes; nao cole a saida em chat depois disso")
    p.add_argument("--pular-testes", action="store_true")
    args = p.parse_args()

    print("=" * LARGURA)
    print("DIAGNOSTICO justica-mcp".center(LARGURA))
    print(f"executado em {date.today().isoformat()}".center(LARGURA))
    print("=" * LARGURA)

    checar_ambiente()
    if not args.pular_testes:
        rodar_testes()

    async def rede() -> None:
        await checar_djen(args.oab, args.uf, args.dias, args.detalhe)
        await checar_siglas_djen()
        await checar_datajud(args.processo, args.detalhe)

    asyncio.run(rede())

    titulo("FIM")
    if args.detalhe:
        print("  Rodado com --detalhe: a saida contem teor de publicacao.")
        print("  Revise antes de compartilhar.")
    else:
        print("  Saida segura: sem teor de publicacao, apenas estrutura e contagens.")
    print("  Cole este relatorio para eu ajustar os adaptadores ao formato real.\n")


if __name__ == "__main__":
    main()
