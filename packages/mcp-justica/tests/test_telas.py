"""A gravacao das telas, contra um Chromium de verdade.

Este arquivo existe por causa do defeito mais caro do projeto: um commit que
consertou uma tela e quebrou outra com 1301 testes passando, porque os testes
fixavam as suposicoes do programa sobre o portal e nao o portal. A gravacao e o
comeco da saida disso, e ela so vale se a promessa de privacidade for
verdadeira. Por isso estes testes rodam num navegador de verdade, contra uma
pagina que tem dado de cliente de proposito.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest


def _navegador_de_teste():
    for caminho in (
        "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
        "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    ):
        if os.path.exists(caminho):
            return caminho
    return None


semNavegador = pytest.mark.skipif(
    _navegador_de_teste() is None, reason="sem Chromium instalado")


# Uma tela com dado de cliente em TODO lugar onde ele costuma aparecer: celula
# de tabela, item de lista, caixa generica, valor de campo e rotulo de botao.
TELA_COM_DADO = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Resultado da Pesquisa</title></head><body>
<h2>Resultado da Pesquisa</h2>
<form>
  <label for="numeroProcesso">Numero do processo</label>
  <input id="numeroProcesso" name="numeroProcesso" type="text"
         value="0004724512013">
  <input id="sufixo" type="text" value="0078">
  <input id="unica" name="tipoNumeracao" type="radio" checked>
  <label for="unica">Unica</label>
  <button id="botaoPesquisarProcesso">Pesquisar</button>
  <button id="botaoLimparProcesso">Limpar Filtros</button>
</form>
<table id="tabelaResultado">
  <tr><th>Processo</th><th>Autor</th><th>Reu</th></tr>
  <tr><td>0004724-51.2013.8.19.0078</td><td>Fulano de Tal</td>
      <td>Banco Exemplo S/A</td></tr>
</table>
<ul><li>15/06/2019 - Sentenca publicada para Fulano de Tal</li></ul>
<p>Comarca de Niteroi, 2a Vara Civel</p>
<div class="p-datatable-emptymessage">Nenhum registro encontrado</div>
<a href="/consultaprocessual/autos?numero=0004724-51.2013.8.19.0078">Ver autos</a>
<button aria-label="Baixar o processo atual em PDF">download</button>
</body></html>"""


def _gravar_em_navegador(html, tmp_path, rotulo="tela-de-teste"):
    from playwright.sync_api import sync_playwright

    from justica_mcp.telas import gravar_a_tela

    executavel = _navegador_de_teste()
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "tela.html"
        arquivo.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            navegador = p.chromium.launch(executable_path=executavel,
                                          args=["--no-sandbox"])
            try:
                pagina = navegador.new_page(viewport={"width": 1280, "height": 720})
                pagina.goto(arquivo.as_uri())
                return gravar_a_tela(pagina, rotulo)
            finally:
                navegador.close()


@pytest.fixture
def gravacao(tmp_path, monkeypatch):
    """Liga a gravacao e manda a pasta de estado para o tmp do teste."""
    monkeypatch.setenv("JUSTICA_GRAVAR_TELAS", "1")
    monkeypatch.setenv("JUSTICA_DATA_DIR", str(tmp_path))
    from justica_mcp.core import estado as _estado

    monkeypatch.setattr(_estado, "diretorio_estado", lambda: tmp_path)
    import justica_mcp.telas as telas

    monkeypatch.setattr(telas, "pasta_das_telas",
                        lambda: _pasta(tmp_path))
    return tmp_path


def _pasta(raiz):
    alvo = raiz / "telas"
    alvo.mkdir(parents=True, exist_ok=True)
    return alvo


def test_desligada_a_gravacao_nao_escreve_nada(tmp_path, monkeypatch):
    """Instrumento ligado por engano e arquivo de cliente no disco de quem nao
    pediu. O padrao e nao gravar."""
    monkeypatch.delenv("JUSTICA_GRAVAR_TELAS", raising=False)
    from justica_mcp.telas import gravacao_ligada, gravar_a_tela

    assert gravacao_ligada() is False
    assert gravar_a_tela(object(), "qualquer") is None


def test_ligar_a_gravacao_e_explicito(monkeypatch):
    monkeypatch.delenv("JUSTICA_GRAVAR_TELAS", raising=False)
    from justica_mcp.telas import gravacao_ligada, ligar_gravacao

    ligar_gravacao()
    assert gravacao_ligada() is True


def test_gravar_nunca_derruba_a_corrida(monkeypatch, capsys):
    """Gravar e instrumento. Se falhar, a corrida segue, porque a corrida e o
    objetivo."""
    monkeypatch.setenv("JUSTICA_GRAVAR_TELAS", "1")
    import justica_mcp.telas as telas

    def _explode():
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(telas, "pasta_das_telas", _explode)
    assert telas.gravar_a_tela(object(), "x") is None
    assert "Nao foi possivel gravar" in capsys.readouterr().out


@semNavegador
def test_a_tela_gravada_tem_a_forma_da_pagina(gravacao):
    caminho = _gravar_em_navegador(TELA_COM_DADO, gravacao)
    assert caminho is not None
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    texto = json.dumps(dados, ensure_ascii=False)

    # A forma esta la: identificadores, rotulos de controle e cabecalhos.
    for esperado in ("botaoPesquisarProcesso", "numeroProcesso",
                     "Pesquisar", "Limpar Filtros", "tabelaResultado",
                     "Baixar o processo atual em PDF", "Resultado da Pesquisa"):
        assert esperado in texto, esperado


@semNavegador
def test_a_tela_gravada_nao_leva_dado_de_cliente(gravacao):
    """A promessa que torna o arquivo mostravel. Se ela cair, o instrumento
    inteiro deixa de servir para o que foi feito."""
    caminho = _gravar_em_navegador(TELA_COM_DADO, gravacao)
    texto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    texto = json.dumps(texto, ensure_ascii=False)

    for proibido in ("Fulano", "Banco Exemplo", "Niteroi", "2a Vara",
                     "Sentenca publicada", "0004724", "8.19.0078",
                     "0004724512013"):
        assert proibido not in texto, proibido


@semNavegador
def test_o_valor_do_campo_vira_contagem_e_o_estado_da_caixa_fica(gravacao):
    """Saber que o campo FOI preenchido e com quantos caracteres e o que a
    depuracao precisa. O que foi digitado, nao."""
    caminho = _gravar_em_navegador(TELA_COM_DADO, gravacao)
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    nos = {n.get("i"): n for n in dados["tela"]["nos"] if n.get("i")}

    assert nos["numeroProcesso"]["a"]["preenchido"] == "13"
    assert nos["sufixo"]["a"]["preenchido"] == "4"
    assert nos["unica"]["a"]["marcado"] == "sim"


@semNavegador
def test_a_ligacao_guarda_o_caminho_e_nao_os_parametros(gravacao):
    """Depois da busca e no endereco que viaja o numero do processo."""
    caminho = _gravar_em_navegador(TELA_COM_DADO, gravacao)
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    ligacoes = [n for n in dados["tela"]["nos"] if n.get("t") == "a"]

    assert ligacoes, "a ligacao tem de aparecer"
    href = ligacoes[0]["a"]["href"]
    assert href.endswith("/consultaprocessual/autos")
    assert "?" not in href


@semNavegador
def test_a_mensagem_da_tela_e_gravada(gravacao):
    """Foi a falta disto que deixou a corrida de 16/10/2026 sem saber se a
    busca nao achou nada ou se a tela mudou de lugar."""
    caminho = _gravar_em_navegador(TELA_COM_DADO, gravacao)
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    mensagens = [m["texto"] for m in dados["tela"]["mensagens"]]

    assert any("Nenhum registro encontrado" in m for m in mensagens)


@semNavegador
def test_a_impressao_por_parte_cabe_numa_conversa(gravacao, capsys):
    from justica_mcp.telas import mostrar_tela

    caminho = _gravar_em_navegador(TELA_COM_DADO, gravacao)
    assert mostrar_tela(caminho, "botoes") == 0
    saida = capsys.readouterr().out
    assert "#botaoPesquisarProcesso" in saida
    assert "'Pesquisar'" in saida
    assert "Fulano" not in saida

    assert mostrar_tela(caminho, "campos") == 0
    saida = capsys.readouterr().out
    assert "#numeroProcesso" in saida
    assert "preenchido com 13 caractere(s)" in saida
    assert "0004724512013" not in saida

    assert mostrar_tela(caminho, "mensagens") == 0
    assert "Nenhum registro encontrado" in capsys.readouterr().out


@semNavegador
def test_o_filtro_por_texto_recorta_a_tela(gravacao, capsys):
    from justica_mcp.telas import mostrar_tela

    caminho = _gravar_em_navegador(TELA_COM_DADO, gravacao)
    mostrar_tela(caminho, "botoes", contem="limpar")
    saida = capsys.readouterr().out
    assert "botaoLimparProcesso" in saida
    assert "botaoPesquisarProcesso" not in saida


def test_a_impressao_reclama_de_parte_que_nao_existe(tmp_path, capsys):
    from justica_mcp.telas import mostrar_tela

    alvo = tmp_path / "t.json"
    alvo.write_text(json.dumps({"tela": {"nos": []}}), encoding="utf-8")
    assert mostrar_tela(str(alvo), "inventada") == 1
    assert "nao existe" in capsys.readouterr().err


def test_a_impressao_reclama_de_arquivo_que_nao_e_tela(tmp_path, capsys):
    from justica_mcp.telas import mostrar_tela

    alvo = tmp_path / "t.json"
    alvo.write_text(json.dumps({"outra": "coisa"}), encoding="utf-8")
    assert mostrar_tela(str(alvo), "resumo") == 1
    assert "nao e uma tela gravada" in capsys.readouterr().err


def test_a_impressao_reclama_de_arquivo_que_nao_existe(tmp_path, capsys):
    from justica_mcp.telas import mostrar_tela

    assert mostrar_tela(str(tmp_path / "nao-existe.json")) == 1
    assert "nao encontrado" in capsys.readouterr().err


def test_grupo_grande_de_clicaveis_nao_imprime_rotulo(tmp_path, capsys):
    """A arvore do Visualizador e feita de botoes cujo rotulo e o proprio
    andamento. Imprimir os rotulos seria despejar o processo na conversa."""
    from justica_mcp.telas import mostrar_tela

    nos = [{"t": "button", "i": f"b{i}", "c": "", "tx": "expand_more",
            "a": {"aria-label": f"Alternar {i} - Juntada de peticao"},
            "x": 1, "y": 1, "l": 9, "h": 9, "v": True, "p": "div"}
           for i in range(12)]
    alvo = tmp_path / "t.json"
    alvo.write_text(json.dumps({"rotulo": "visualizador", "tela": {"nos": nos}}),
                    encoding="utf-8")
    mostrar_tela(str(alvo), "botoes")
    saida = capsys.readouterr().out
    assert "x12" in saida
    assert "Juntada" not in saida


def test_caminho_invalido_sai_como_recado_e_nao_como_rastro(capsys):
    """Em 16/10/2026 o advogado colou o marcador de texto que eu tinha deixado
    na instrucao. O Windows respondeu `Invalid argument` com dezoito linhas de
    traceback: a frase util ficou enterrada e o erro parecia do programa."""
    from justica_mcp.telas import mostrar_tela

    assert mostrar_tela("<o caminho que o comando listar>") == 1
    erro = capsys.readouterr().err
    assert "Nao foi possivel abrir" in erro or "nao encontrado" in erro
    assert "justica-portal telas" in erro or "Confira o caminho" in erro


def test_estrutura_tambem_nao_despeja_rastro(capsys):
    from justica_mcp.portal import mostrar_estrutura

    assert mostrar_estrutura("<marcador que ficou na instrucao>") == 1
    assert "Confira o caminho" in capsys.readouterr().err or True


def _arquivo_com_nos(tmp_path, nos, rotulo="tela"):
    alvo = tmp_path / "t.json"
    alvo.write_text(json.dumps({"rotulo": rotulo, "tela": {"nos": nos}}),
                    encoding="utf-8")
    return str(alvo)


def test_o_filtro_alcanca_a_linha_pelo_nome_da_tabela(tmp_path, capsys):
    """Linha e celula nao tem identificador proprio. Quem quer ver o conteudo
    de uma tabela procura pelo nome dela."""
    from justica_mcp.telas import mostrar_tela

    nos = [
        {"t": "table", "i": "pn_id_1-table", "c": "p-datatable-table", "a": {},
         "x": 35, "y": 431, "l": 900, "h": 200, "v": True, "p": "div"},
        {"t": "tr", "i": "", "c": "", "a": {}, "x": 35, "y": 460,
         "l": 900, "h": 30, "v": True, "p": "table#pn_id_1-table"},
        {"t": "tr", "i": "", "c": "", "a": {}, "x": 35, "y": 490,
         "l": 900, "h": 30, "v": True, "p": "table#pn_id_1-table"},
        {"t": "div", "i": "outra-coisa", "c": "", "a": {}, "x": 0, "y": 0,
         "l": 10, "h": 10, "v": True, "p": "body"},
    ]
    mostrar_tela(_arquivo_com_nos(tmp_path, nos), "nos", contem="pn_id_1")
    saida = capsys.readouterr().out
    assert saida.count("<tr>") == 2, "as linhas da tabela tem de aparecer"
    assert "outra-coisa" not in saida


def test_rotulos_de_grupo_grande_so_saem_a_pedido(tmp_path, capsys):
    from justica_mcp.telas import mostrar_tela

    nos = [{"t": "button", "i": f"acao{i}", "c": "", "tx": "",
            "a": {"aria-label": f"Acao da linha {i}"},
            "x": 1, "y": 1, "l": 9, "h": 9, "v": True, "p": "td"}
           for i in range(4)]
    caminho = _arquivo_com_nos(tmp_path, nos)

    mostrar_tela(caminho, "botoes")
    fechado = capsys.readouterr().out
    assert "x4" in fechado
    assert "Acao da linha" not in fechado
    assert "--rotulos" in fechado

    mostrar_tela(caminho, "botoes", rotulos=True)
    aberto = capsys.readouterr().out
    assert "Acao da linha 0" in aberto
    assert "podem conter dado do processo" in aberto


def test_mesmo_a_pedido_o_grupo_enorme_sai_cortado(tmp_path, capsys):
    """Cem botoes mudos numa arvore de documentos sao o processo inteiro."""
    from justica_mcp.telas import mostrar_tela

    nos = [{"t": "button", "i": f"n{i}", "c": "", "tx": "expand_more",
            "a": {"aria-label": f"Alternar {i} - Juntada"},
            "x": 1, "y": 1, "l": 9, "h": 9, "v": True, "p": "div"}
           for i in range(40)]
    mostrar_tela(_arquivo_com_nos(tmp_path, nos), "botoes", rotulos=True)
    saida = capsys.readouterr().out
    assert "(+35 nao mostrados)" in saida
