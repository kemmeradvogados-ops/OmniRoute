"""Leitura das pecas gravadas na pasta do processo.

Esta e a unica parte do programa que devolve CONTEUDO do processo, entao os
testes aqui cobrem duas coisas ao mesmo tempo: que a leitura esta certa, e que
o conteudo NAO escapa pelo relato de terminal. A regra vem de 06/10/2026,
quando o andamento de um processo foi parar numa conversa.

Os PDFs sao montados aqui mesmo, byte a byte: folha com texto e folha SEM
camada de texto, que e o que um documento digitalizado parece. Sem isso nao da
para testar a diferenca entre "a folha nao diz nada" e "eu nao consegui ler a
folha", e e justamente essa diferenca que vale decisao.
"""

import pytest


def pdf_com_textos(textos):
    """Um PDF minimo e valido, uma folha por texto. Texto vazio = folha sem
    camada de texto, que e o que uma folha digitalizada parece."""
    objetos = []
    n_paginas = len(textos)
    ids_paginas = [3 + 2 * i for i in range(n_paginas)]
    objetos.append(b"<</Type/Catalog/Pages 2 0 R>>")
    kids = b" ".join(b"%d 0 R" % i for i in ids_paginas)
    objetos.append(b"<</Type/Pages/Kids[" + kids + b"]/Count %d>>" % n_paginas)
    for i, texto in enumerate(textos):
        conteudo_id = ids_paginas[i] + 1
        objetos.append(
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents %d 0 R"
            b"/Resources<</Font<</F1 %d 0 R>>>>>>" % (conteudo_id, 3 + 2 * n_paginas))
        if texto:
            escapado = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            fluxo = ("BT /F1 12 Tf 72 720 Td (%s) Tj ET" % escapado).encode("latin-1")
        else:
            fluxo = b""
        objetos.append(b"<</Length %d>>stream\n" % len(fluxo) + fluxo + b"\nendstream")
    objetos.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for numero, corpo in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj" % numero + corpo + b"endobj\n"
    inicio_xref = len(saida)
    saida += b"xref\n0 %d\n" % (len(objetos) + 1)
    saida += b"0000000000 65535 f \n"
    for pos in posicoes:
        saida += b"%010d 00000 n \n" % pos
    saida += (b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objetos) + 1, inicio_xref))
    return bytes(saida)


def _pasta_com(tmp_path, monkeypatch, arquivos):
    """Monta a pasta de copias do processo e aponta o acervo para ela."""
    from justica_mcp import pecas

    pasta = tmp_path / "00000018620138190078"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, textos in arquivos.items():
        (pasta / nome).write_bytes(pdf_com_textos(textos))
    monkeypatch.setattr(pecas, "pasta_do_processo", lambda *a: pasta)
    return pasta


DIGITOS = "00000018620138190078"
FORMATADO = "0000001-86.2013.8.19.0078"


def test_a_peca_sai_do_nome_do_arquivo():
    from justica_mcp.pecas import peca_do_nome

    assert peca_do_nome("proc-pagina1666-Doc.pdf") == 1666
    assert peca_do_nome("proc-pagina13420-Doc.pdf") == 13420
    assert peca_do_nome("sem-numero.pdf") is None


def test_a_peca_1342_nao_acha_a_13420(tmp_path, monkeypatch):
    """Casar por prefixo faria 1342 abrir o arquivo de 13420, e a analise
    sairia sobre o documento errado."""
    from justica_mcp.pecas import achar_a_peca

    pasta = _pasta_com(tmp_path, monkeypatch, {
        "proc-pagina13420-Outro.pdf": ["texto do documento errado aqui"],
    })
    assert achar_a_peca(pasta, 1342) is None
    assert achar_a_peca(pasta, 13420) is not None


def test_a_lista_da_pasta_nao_traz_conteudo(tmp_path, monkeypatch):
    from justica_mcp.pecas import pecas_da_pasta

    _pasta_com(tmp_path, monkeypatch, {
        "proc-pagina1342-A.pdf": ["o segredo do cliente esta nesta folha"],
        "proc-pagina1666-B.pdf": ["outra folha", "mais uma folha com texto"],
    })
    dados = pecas_da_pasta(DIGITOS, FORMATADO)
    assert [p["peca"] for p in dados["pecas"]] == [1342, 1666]
    assert [p["folhas"] for p in dados["pecas"]] == [1, 2]
    assert dados["folhas"] == 3
    assert "segredo" not in str(dados)


def test_arquivo_vazio_nao_entra_na_lista(tmp_path, monkeypatch):
    from justica_mcp.pecas import pecas_da_pasta

    pasta = _pasta_com(tmp_path, monkeypatch,
                       {"proc-pagina1342-A.pdf": ["folha com texto aqui"]})
    (pasta / "proc-pagina1999-Vazio.pdf").write_bytes(b"")
    assert [p["peca"] for p in pecas_da_pasta(DIGITOS, FORMATADO)["pecas"]] == [1342]


def test_pasta_que_nao_existe_diz_que_nao_existe(tmp_path, monkeypatch):
    from justica_mcp import pecas

    monkeypatch.setattr(pecas, "pasta_do_processo",
                        lambda *a: tmp_path / "nao-existe")
    dados = pecas.pecas_da_pasta(DIGITOS, FORMATADO)
    assert dados["existe"] is False
    assert "nao existe" in dados["aviso"]


def test_o_texto_da_peca_volta_com_a_folha_identificada(tmp_path, monkeypatch):
    from justica_mcp.pecas import ler_peca

    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "primeira folha da certidao de publicacao",
        "segunda folha do ato ordinatorio",
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert lido["folhas_na_peca"] == 2
    assert lido["folhas_com_texto"] == 2
    assert "--- folha 1 ---" in lido["texto"]
    assert "certidao de publicacao" in lido["texto"]
    assert "ato ordinatorio" in lido["texto"]
    assert lido["cortado"] is False


def test_a_faixa_de_folhas_e_respeitada(tmp_path, monkeypatch):
    from justica_mcp.pecas import ler_peca

    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "folha um com bastante texto", "folha dois com bastante texto",
        "folha tres com bastante texto",
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666, de=2, ate=3)
    assert lido["de"] == 2 and lido["ate"] == 3
    assert "folha um" not in lido["texto"]
    assert "folha dois" in lido["texto"] and "folha tres" in lido["texto"]


def test_folha_sem_camada_de_texto_nao_e_folha_em_branco(tmp_path, monkeypatch):
    """A diferenca que vale decisao: concluir que a peca nada diz numa folha
    que o programa so nao soube ler seria erro de analise."""
    from justica_mcp.pecas import ler_peca

    _pasta_com(tmp_path, monkeypatch,
               {"proc-pagina1666-B.pdf": ["", "", ""]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert lido["folhas_com_texto"] == 0
    assert lido["folhas_sem_texto"] == [1, 2, 3]
    assert "imagem digitalizada" in lido["aviso"]
    assert "NAO significa que a peca esteja em branco" in lido["aviso"]


def test_folha_digitalizada_no_meio_e_nomeada(tmp_path, monkeypatch):
    from justica_mcp.pecas import ler_peca

    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "folha um com bastante texto", "", "folha tres com bastante texto",
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert lido["folhas_sem_texto"] == [2]
    assert lido["folhas_com_texto"] == 2
    assert "1 folha(s) sem camada de texto" in lido["aviso"]


def test_o_corte_pelo_teto_diz_onde_continuar(tmp_path, monkeypatch):
    """Cortar e aceitavel. Cortar em silencio faria a analise concluir sobre
    meia peca achando que viu a peca inteira."""
    from justica_mcp.pecas import ler_peca

    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "a" * 400, "b" * 400, "c" * 400,
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666, teto=500)
    assert lido["cortado"] is True
    assert lido["ate"] == 1
    assert "de=2" in lido["aviso"]
    assert "c" * 400 not in lido["texto"]


def test_peca_que_nao_esta_na_pasta_lista_as_que_estao(tmp_path, monkeypatch):
    from justica_mcp.pecas import ler_peca

    _pasta_com(tmp_path, monkeypatch, {
        "proc-pagina1342-A.pdf": ["folha com texto aqui"],
        "proc-pagina1666-B.pdf": ["outra folha com texto"],
    })
    lido = ler_peca(DIGITOS, FORMATADO, 9999)
    assert "Nenhuma peca gravada comeca na pagina 9999" in lido["erro"]
    assert lido["pecas_na_pasta"] == [1342, 1666]


def test_folha_depois_do_fim_da_peca_recusa_dizendo_o_tamanho(tmp_path, monkeypatch):
    from justica_mcp.pecas import ler_peca

    _pasta_com(tmp_path, monkeypatch,
               {"proc-pagina1666-B.pdf": ["folha unica com texto aqui"]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666, de=5)
    assert "tem 1 folha(s)" in lido["erro"]


def test_arquivo_que_nao_e_pdf_recusa_sem_derrubar(tmp_path, monkeypatch):
    from justica_mcp import pecas

    pasta = tmp_path / "proc"
    pasta.mkdir()
    (pasta / "proc-pagina1342-A.pdf").write_bytes(b"isto nao e um PDF")
    monkeypatch.setattr(pecas, "pasta_do_processo", lambda *a: pasta)
    lido = pecas.ler_peca(DIGITOS, FORMATADO, 1342)
    assert "erro" in lido


# ======================================================================
# O TEXTO NAO SAI PELO TERMINAL
# ======================================================================


def test_o_relato_da_leitura_nunca_carrega_o_texto(tmp_path, monkeypatch):
    from justica_mcp.pecas import ler_peca, relatar_a_leitura

    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "o segredo do cliente esta escrito nesta folha",
    ]})
    lido = ler_peca(DIGITOS, FORMATADO, 1666)
    assert "segredo" in lido["texto"], "o texto volta para quem chamou"
    junto = " ".join(relatar_a_leitura(lido, "/caminho/arquivo.txt"))
    assert "segredo" not in junto, "e nao sai no relato de terminal"
    assert "folha(s) com texto" in junto
    assert "Nao o cole em conversa nenhuma" in junto


def test_o_relato_da_lista_nunca_carrega_o_texto(tmp_path, monkeypatch):
    from justica_mcp.pecas import pecas_da_pasta, relatar_as_pecas

    _pasta_com(tmp_path, monkeypatch, {"proc-pagina1666-B.pdf": [
        "o segredo do cliente esta escrito nesta folha",
    ]})
    junto = " ".join(relatar_as_pecas(pecas_da_pasta(DIGITOS, FORMATADO)))
    assert "segredo" not in junto
    assert "1 peca(s)" in junto


def test_o_comando_de_terminal_grava_o_texto_em_arquivo():
    """Guarda de fonte. Um `print` do texto aqui poe dado de cliente numa tela
    que se cola em conversa, e foi assim que isso ja aconteceu uma vez."""
    import inspect

    from justica_mcp import cli

    fonte = inspect.getsource(cli.main)
    trecho = fonte.split('if args.comando in ("pecas", "peca"):')[1].split(
        'if args.comando == "reconhecer":')[0]
    assert "gravar_o_texto(" in trecho
    assert "relatar_a_leitura(" in trecho
    assert 'print(lido["texto"]' not in trecho
    assert 'print(f"{lido' not in trecho


def test_a_ferramenta_de_leitura_avisa_que_devolve_dado_do_cliente():
    """Quem chama precisa saber o que esta recebendo."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    trecho = fonte.split("async def justica_ler_peca")[1][:2000]
    assert "dado do cliente" in trecho
    assert "reconhecimento optico" in trecho or "optico" in trecho


def test_a_ferramenta_da_lista_avisa_que_a_pasta_pode_estar_incompleta():
    """Ausencia na pasta nao prova ausencia nos autos.

    O aviso ja esteve errado por estar velho: ate 22/10/2026 ele dizia que o
    leitor do indice via 35 de 340 documentos, numero consertado no dia
    anterior. Descricao de ferramenta e lida pelo modelo como verdade, entao
    numero desatualizado ali nao e detalhe de documentacao: e o modelo
    concluindo coisa errada sobre os autos do cliente. Por isso a guarda passa
    a cobrar tambem o caminho de conferencia, que nao envelhece."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    trecho = fonte.split("async def justica_pecas_do_processo")[1][:2000]
    assert "INCOMPLETA" in trecho
    assert "nao prova ausencia" in trecho
    assert "reindexar" in trecho
    assert "35 de 340" not in trecho
