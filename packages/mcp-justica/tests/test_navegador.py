"""Testes do modulo `navegador`: o navegador e a geometria da tela.

Vieram de `test_portal.py` em 22/10/2026 junto com o codigo que eles cobrem, e
os que falavam com `portal.pasta_de_descargas` passaram a falar com
`navegador.pasta_de_descargas`. A troca nao e cosmetica: depois da separacao,
quem chama `pasta_de_descargas` de dentro de `navegador.py` enxerga o nome
DESTE modulo, entao um duble posto em `portal` nao seria visto, e o teste
passaria a provar outra coisa que nao a que esta escrita nele.
"""

from __future__ import annotations

import os
import time

from justica_mcp import navegador


def _descargas_em(tmp_path, monkeypatch, arquivos):
    """Monta a pasta de descargas com (nome, bytes, idade_em_segundos)."""
    pasta = tmp_path / "descargas"
    pasta.mkdir(parents=True, exist_ok=True)
    agora = time.time()
    for nome, tamanho, idade in arquivos:
        alvo = pasta / nome
        alvo.write_bytes(b"x" * tamanho)
        os.utime(alvo, (agora - idade, agora - idade))
    monkeypatch.setattr(navegador, "pasta_de_descargas", lambda: pasta)
    return pasta, agora


def test_a_medida_da_pasta_conta_arquivos_e_bytes(tmp_path, monkeypatch):
    _descargas_em(tmp_path, monkeypatch,
                  [("a.pdf", 100, 10), ("b.pdf", 200, 10)])
    assert navegador.medida_das_descargas() == (2, 300)


def test_a_limpeza_apaga_so_o_que_e_anterior_a_corrida(tmp_path, monkeypatch):
    """O resgate compara contra uma lista tirada no instante do clique, entao
    arquivo mais novo que o inicio da corrida pode ser o que a proxima redea vai
    procurar. Apagar esse seria jogar fora o download que acabou de chegar."""
    pasta, agora = _descargas_em(
        tmp_path, monkeypatch,
        [("velho.pdf", 1000, 600), ("novo.pdf", 2000, 0)])
    apagados, bytes_livres = navegador.limpar_descargas(agora - 300)
    assert (apagados, bytes_livres) == (1, 1000)
    assert not (pasta / "velho.pdf").exists()
    assert (pasta / "novo.pdf").exists()


def test_a_limpeza_nao_levanta_quando_a_pasta_nao_existe(tmp_path, monkeypatch):
    """Pasta de cache nao pode derrubar um download."""
    monkeypatch.setattr(navegador, "pasta_de_descargas",
                        lambda: tmp_path / "nao-existe")
    assert navegador.limpar_descargas(0) == (0, 0)
    assert navegador.medida_das_descargas() == (0, 0)


# ==========================================================================
# A separacao em si: o que ela promete e o que ela NAO promete.
# ==========================================================================

NOMES_REEXPORTADOS = (
    "AREA_DA_CONSULTA", "AREA_DO_VISUALIZADOR", "ESCALA_PADRAO",
    "JANELA_LARGA", "JANELA_SUPOSTA", "JS_DA_MEDIDA_DO_CONTEUDO",
    "ROLAGEM_ATE_O_ELEMENTO", "VARIAVEL_PERFIL_EFEMERO", "abrir_navegador",
    "alargar_a_area", "bandeiras_do_navegador", "caixa_de", "caixa_na_tela",
    "descrever_caixa", "escala_da_janela", "janela_de", "limpar_descargas",
    "medida_das_descargas", "medida_do_conteudo", "na_tela_ou_rolar",
    "nome_do_perfil", "os_que_cabem_na_janela", "passou_da_borda",
    "pasta_de_descargas", "pasta_do_navegador", "relatar_a_medida_do_conteudo",
)


def test_portal_reexporta_os_mesmos_objetos():
    """Meio pacote chama `portal.janela_de`. A separacao so e invisivel para
    quem chama enquanto estes forem o MESMO objeto, e nao uma copia."""
    from justica_mcp import portal

    for nome in NOMES_REEXPORTADOS:
        assert getattr(portal, nome) is getattr(navegador, nome), nome


def test_a_dependencia_corre_num_sentido_so():
    """Guarda de fonte: `navegador.py` nao pode importar portal nenhum.

    E a unica coisa que impede a geometria de voltar a se enroscar nas telas de
    um portal especifico, que foi o estado em que uma linha de area de janela
    quebrou os cinco de uma vez em 15/10/2026."""
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(navegador))
    # So os imports RELATIVOS importam aqui: um `import os` nao enrosca nada.
    do_pacote = sorted({
        no.module for no in ast.walk(arvore)
        if isinstance(no, ast.ImportFrom) and (no.level or 0) > 0 and no.module
    })
    assert do_pacote == ["core.estado"], do_pacote


# --------------------------------------------------------------------------
# Faro de arquivos
# --------------------------------------------------------------------------


class _RespostaFalsa:
    def __init__(self, url, cabecalhos=None):
        self.url = url
        self.headers = cabecalhos or {}


class _PaginaFalsa:
    def __init__(self, url):
        self.url = url


class _ContextoFalso:
    """Um contexto que so sabe guardar ouvintes e devolver abas."""

    def __init__(self, paginas=()):
        self.pages = list(paginas)
        self.ouvintes: dict = {}

    def on(self, evento, tratador):
        self.ouvintes.setdefault(evento, []).append(tratador)

    def remove_listener(self, evento, tratador):
        self.ouvintes.get(evento, []).remove(tratador)

    def emitir(self, evento, carga):
        for tratador in list(self.ouvintes.get(evento, [])):
            tratador(carga)


def test_parece_arquivo_pelo_tipo_declarado():
    assert navegador.parece_arquivo(
        "https://x.jus.br/a", {"content-type": "application/pdf;charset=utf-8"})


def test_parece_arquivo_pela_disposicao():
    assert navegador.parece_arquivo(
        "https://x.jus.br/a", {"content-disposition": "attachment; file=1"})


def test_parece_arquivo_pela_terminacao_mesmo_sem_tipo():
    """Servidor que nao declara tipo nenhum ainda diz o que e pelo caminho."""
    assert navegador.parece_arquivo("https://x.jus.br/autos.PDF?t=1", {})


def test_pagina_de_portal_nao_parece_arquivo():
    assert not navegador.parece_arquivo(
        "https://x.jus.br/1g/listView.seam", {"content-type": "text/html"})


def test_resumo_do_endereco_apaga_os_numeros_longos():
    """O numero do processo viaja no caminho, e o relato vai parar em conversa."""
    resumo = navegador.resumo_do_endereco(
        "https://docs.x.jus.br/arquivo/08090908820238190001/autos.pdf?token=a")
    assert "0809090" not in resumo
    assert resumo.startswith("https://docs.x.jus.br/arquivo/.../autos.pdf")
    assert "token" not in resumo


def test_resumo_do_endereco_aguenta_lixo():
    assert navegador.resumo_do_endereco("") == "(endereco sem servidor)"


def test_o_faro_anota_a_resposta_com_cara_de_arquivo():
    contexto = _ContextoFalso()
    faro = navegador.FarejadorDeArquivos(contexto)
    assert faro.ligar()
    contexto.emitir("response", _RespostaFalsa(
        "https://x.jus.br/a.pdf", {"content-type": "application/pdf"}))
    contexto.emitir("response", _RespostaFalsa(
        "https://x.jus.br/pagina", {"content-type": "text/html"}))
    assert faro.enderecos() == ["https://x.jus.br/a.pdf"]


def test_o_faro_nao_anota_o_mesmo_endereco_duas_vezes():
    contexto = _ContextoFalso()
    faro = navegador.FarejadorDeArquivos(contexto)
    faro.ligar()
    for _ in range(3):
        contexto.emitir("response", _RespostaFalsa(
            "https://x.jus.br/a.pdf", {"content-type": "application/pdf"}))
    assert len(faro.enderecos()) == 1


def test_o_faro_colhe_o_endereco_da_aba_parada_num_pdf():
    """Quando o navegador ABRE o arquivo em vez de baixar, nao ha evento algum.

    O que ha e uma aba com o endereco do arquivo na barra, e e ela que responde.
    """
    contexto = _ContextoFalso()
    faro = navegador.FarejadorDeArquivos(contexto)
    faro.ligar()
    nova = _PaginaFalsa("about:blank")
    contexto.emitir("page", nova)
    # A aba nasce em branco e so depois recebe o endereco do arquivo.
    nova.url = "https://x.jus.br/gerado/autos.pdf"
    assert faro.enderecos() == ["https://x.jus.br/gerado/autos.pdf"]


def test_o_faro_descarta_endereco_que_nao_se_pode_pedir():
    contexto = _ContextoFalso()
    faro = navegador.FarejadorDeArquivos(contexto)
    faro.ligar()
    for endereco in ("about:blank", "chrome://downloads", "data:application/pdf,x"):
        contexto.emitir("response", _RespostaFalsa(
            endereco, {"content-type": "application/pdf"}))
    assert faro.enderecos() == []


def test_o_faro_desligado_para_de_anotar():
    contexto = _ContextoFalso()
    faro = navegador.FarejadorDeArquivos(contexto)
    faro.ligar()
    faro.desligar()
    contexto.emitir("response", _RespostaFalsa(
        "https://x.jus.br/a.pdf", {"content-type": "application/pdf"}))
    assert faro.enderecos() == []
    assert contexto.ouvintes["response"] == []


def test_o_faro_nao_le_o_corpo_da_resposta():
    """Guarda de fonte: ler o corpo aqui gastaria a resposta do navegador."""
    import ast
    import inspect

    fonte = inspect.getsource(navegador.FarejadorDeArquivos)
    chamadas = {
        no.func.attr for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert "body" not in chamadas
    assert "text" not in chamadas


def test_o_faro_relata_sem_soltar_o_endereco_inteiro(capsys):
    contexto = _ContextoFalso()
    faro = navegador.FarejadorDeArquivos(contexto)
    faro.ligar()
    contexto.emitir("response", _RespostaFalsa(
        "https://x.jus.br/a/08090908820238190001/autos.pdf?t=segredo",
        {"content-type": "application/pdf"}))
    faro.relatar()
    saida = capsys.readouterr().out
    assert "0809090" not in saida
    assert "segredo" not in saida
    assert "autos.pdf" in saida


def test_o_faro_diz_quando_nao_viu_nada(capsys):
    navegador.FarejadorDeArquivos(_ContextoFalso()).relatar()
    assert "nenhum" in capsys.readouterr().out.lower()
