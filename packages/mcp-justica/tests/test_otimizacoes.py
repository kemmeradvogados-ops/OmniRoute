"""Testes das otimizacoes pedidas em 24/10/2026.

Tres delas sao de leitura e uma apaga arquivo. A que apaga e a unica com
ensaio obrigatorio, porque pasta de arquivo de processo nao se limpa por
engano.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from justica_mcp.core.acervo import (
    NOME_INDICE, VARIAVEL_PASTA, formatar_numero, processos_guardados,
)

UM = "08090908820238190001"
OUTRO = "00000018620138190078"


@pytest.fixture()
def acervo(tmp_path, monkeypatch):
    monkeypatch.setenv(VARIAVEL_PASTA, str(tmp_path))
    return tmp_path


def _envelhecer(pasta: Path, dias: int) -> None:
    """Empurra para tras a data da pasta E a de cada arquivo dentro dela."""
    quando = time.time() - 86400 * dias
    for caminho in list(pasta.iterdir()) + [pasta]:
        os.utime(caminho, (quando, quando))


def _processo(raiz: Path, digitos: str, arquivos: dict,
              folhas: int | None = None) -> Path:
    pasta = raiz / digitos
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in arquivos.items():
        (pasta / nome).write_bytes(conteudo)
    if folhas is not None:
        (pasta / NOME_INDICE).write_text(
            json.dumps({"folhas_totais": folhas, "itens": []}),
            encoding="utf-8")
    return pasta


# --------------------------------------------------------------------------
# Formatar o numero a partir do nome da pasta
# --------------------------------------------------------------------------


def test_o_numero_sai_formatado_do_nome_da_pasta():
    assert formatar_numero(UM) == "0809090-88.2023.8.19.0001"


def test_nome_que_nao_e_numero_volta_como_veio():
    """Recusar a listagem por causa do nome esconderia uma pasta que esta la."""
    assert formatar_numero("rascunho") == "rascunho"
    assert formatar_numero("123") == "123"


# --------------------------------------------------------------------------
# Listar os processos do acervo
# --------------------------------------------------------------------------


def test_lista_os_processos_com_tamanho_e_folhas(acervo):
    _processo(acervo, UM, {"peca-1.pdf": b"%PDF-1.4" + b"x" * 100}, folhas=42)
    achados = processos_guardados()
    assert len(achados) == 1
    assert achados[0]["numero"] == "0809090-88.2023.8.19.0001"
    assert achados[0]["arquivos"] == 1
    assert achados[0]["folhas_no_indice"] == 42
    assert achados[0]["bytes"] == 108


def test_processo_sem_indice_aparece_mesmo_assim(acervo):
    """Sem indice nao quer dizer vazio, e esconder seria pior que nao contar."""
    _processo(acervo, UM, {"peca-1.pdf": b"%PDF-1.4"})
    achados = processos_guardados()
    assert achados[0]["folhas_no_indice"] is None
    assert achados[0]["arquivos"] == 1


def test_pasta_que_nao_e_numero_de_processo_fica_de_fora(acervo):
    _processo(acervo, UM, {"a.pdf": b"%PDF"})
    (acervo / "rascunhos").mkdir()
    (acervo / "123").mkdir()
    assert [p["digitos"] for p in processos_guardados()] == [UM]


def test_a_listagem_vem_do_mais_recente_para_o_mais_antigo(acervo):
    velho = _processo(acervo, OUTRO, {"a.pdf": b"%PDF"})
    _envelhecer(velho, 10)
    _processo(acervo, UM, {"a.pdf": b"%PDF"})
    assert [p["digitos"] for p in processos_guardados()] == [UM, OUTRO]


def test_raiz_que_nao_existe_devolve_lista_vazia(tmp_path, monkeypatch):
    monkeypatch.setenv(VARIAVEL_PASTA, str(tmp_path / "nao-existe"))
    assert processos_guardados() == []


def test_a_listagem_nao_abre_pdf_nenhum():
    """Guarda de fonte: abrir todos os arquivos de todos os processos tornaria
    a listagem lenta justamente quando o acervo cresce."""
    import ast
    import inspect
    import textwrap

    arvore = ast.parse(textwrap.dedent(inspect.getsource(processos_guardados)))
    chamadas = {n.func.id for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "contar_paginas" not in chamadas
    assert "PdfReader" not in chamadas


# --------------------------------------------------------------------------
# Limpar a pasta de leituras
# --------------------------------------------------------------------------


def test_o_ensaio_nao_apaga_nada(tmp_path, monkeypatch, capsys):
    from justica_mcp import portal

    leituras = tmp_path / "leituras"
    monkeypatch.setattr("justica_mcp.core.acervo.pasta_de_leituras",
                        lambda: leituras)
    pasta = _processo(leituras, UM, {"a.pdf": b"%PDF"})
    _envelhecer(pasta, 90)

    assert portal.limpar_leituras(dias=30) == 0
    assert pasta.is_dir()
    saida = capsys.readouterr().out
    assert "ENSAIO" in saida
    assert "APAGAR" in saida


def test_com_confirmar_apaga_so_o_que_passou_do_prazo(tmp_path, monkeypatch):
    from justica_mcp import portal

    leituras = tmp_path / "leituras"
    monkeypatch.setattr("justica_mcp.core.acervo.pasta_de_leituras",
                        lambda: leituras)
    velho = _processo(leituras, UM, {"a.pdf": b"%PDF"})
    novo = _processo(leituras, OUTRO, {"a.pdf": b"%PDF"})
    _envelhecer(velho, 90)

    assert portal.limpar_leituras(dias=30, confirmar=True) == 0
    assert not velho.exists()
    assert novo.is_dir()


def test_a_limpeza_nao_enxerga_o_acervo_da_banca(tmp_path, monkeypatch):
    """O acervo do escritorio NAO e tocado aqui, em hipotese alguma."""
    from justica_mcp import portal

    banca = tmp_path / "drive"
    leituras = tmp_path / "leituras"
    monkeypatch.setenv(VARIAVEL_PASTA, str(banca))
    monkeypatch.setattr("justica_mcp.core.acervo.pasta_de_leituras",
                        lambda: leituras)
    do_escritorio = _processo(banca, UM, {"a.pdf": b"%PDF"})
    _envelhecer(do_escritorio, 365)
    _processo(leituras, OUTRO, {"a.pdf": b"%PDF"})

    portal.limpar_leituras(dias=1, confirmar=True)
    assert do_escritorio.is_dir(), "a limpeza tocou no acervo da banca"


def test_a_limpeza_devolve_a_variavel_de_ambiente(tmp_path, monkeypatch):
    from justica_mcp import portal

    leituras = tmp_path / "leituras"
    leituras.mkdir()
    monkeypatch.setenv(VARIAVEL_PASTA, "/tmp/acervo-de-mentira")
    monkeypatch.setattr("justica_mcp.core.acervo.pasta_de_leituras",
                        lambda: leituras)
    portal.limpar_leituras(dias=30)
    assert os.environ[VARIAVEL_PASTA] == "/tmp/acervo-de-mentira"


def test_pasta_de_leituras_inexistente_nao_e_erro(tmp_path, monkeypatch, capsys):
    from justica_mcp import portal

    monkeypatch.setattr("justica_mcp.core.acervo.pasta_de_leituras",
                        lambda: tmp_path / "nunca-criada")
    assert portal.limpar_leituras() == 0
    assert "nao existe" in capsys.readouterr().out


# --------------------------------------------------------------------------
# A cobertura como ferramenta, que e a que evita conclusao errada
# --------------------------------------------------------------------------


def test_a_cobertura_aponta_a_faixa_que_falta(acervo):
    """Sem isto, o Claude le a pasta, nao acha a peca e diz que ela nao existe
    nos autos, quando ela apenas nao foi baixada."""
    from justica_mcp.core.acervo import carregar_indice, cobertura_do_acervo

    pasta = acervo / UM
    pasta.mkdir(parents=True)
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    def _pdf(nome: str, folhas: int) -> None:
        escritor = PdfWriter()
        for _ in range(folhas):
            escritor.add_blank_page(width=200, height=200)
        with open(pasta / nome, "wb") as saida:
            escritor.write(saida)

    # O nome carrega a pagina do PROCESSO em que a peca comeca, no formato
    # que o download grava: `-paginaN-`.
    _pdf("doc-pagina1-inicial.pdf", 3)      # folhas 1 a 3
    _pdf("doc-pagina10-sentenca.pdf", 2)    # folhas 10 e 11, buraco de 4 a 9

    indice = carregar_indice(UM, formatar_numero(UM))
    dados = cobertura_do_acervo(indice)
    assert dados["faixas_que_faltam"], dados
    assert dados["primeira"] == 1
    assert dados["ultima"] == 11


def test_a_ferramenta_de_cobertura_diz_a_conclusao_em_palavras():
    """Guarda de fonte: numero sozinho nao impede a conclusao errada. A
    resposta precisa dizer, em texto, que ausencia na pasta nao prova ausencia
    nos autos."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    assert "justica_cobertura_do_processo" in fonte
    assert "nao conclua que uma peca nao existe nos autos" in fonte.lower()
    assert "faixas_que_faltam" in fonte


def test_as_duas_ferramentas_novas_respeitam_onde_ler():
    """Acervo da banca e pasta de leituras sao lugares diferentes."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    trecho = fonte.split("async def justica_cobertura_do_processo")[1].split(
        "async def justica_ler_peca")[0]
    assert trecho.count("_na_pasta(") == 2
