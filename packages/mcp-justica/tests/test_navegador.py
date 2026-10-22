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
