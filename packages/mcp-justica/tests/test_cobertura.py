"""Cobertura da pasta de copias, em paginas do PROCESSO.

Esta conta foi feita A MAO em 20/10/2026, sobre os numeros que o `reindexar`
imprimia, e achou numa pasta que se apresentava como 35 arquivos e 624 folhas:

  - quatro arquivos que eram subconjunto EXATO do anterior, sempre com a mesma
    pagina final, somando 264 folhas contadas duas vezes, 42% da pasta;
  - 26 paginas numeradas pelo indice que nao estavam em arquivo nenhum, e que
    eram certidoes de publicacao e atos ordinatorios, as pecas que fixam termo
    inicial de prazo.

Enquanto a conta for feita a mao, nenhuma pasta do escritorio tem essa
conferencia, porque ninguem a faz duas vezes.
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


def _indice_com(tmp_path, arquivos):
    """Monta a pasta e devolve um indice apontando para ela."""
    from justica_mcp.core.acervo import Indice

    pasta = tmp_path / "00047245120138190078"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, folhas in arquivos.items():
        (pasta / nome).write_bytes(pdf_com_textos(["folha com texto aqui"] * folhas))
    return Indice(numero="0004724-51.2013.8.19.0078", pasta=pasta)


def N(pagina):
    return f"00047245120138190078-pagina{pagina}-doc.pdf"


def test_a_pagina_do_processo_sai_do_nome_do_arquivo():
    from justica_mcp.core.acervo import pagina_do_nome

    assert pagina_do_nome(N(1666)) == 1666
    assert pagina_do_nome("integra-2026.pdf") is None


def test_a_peca_contida_noutra_e_apontada(tmp_path):
    """O caso de campo: o documento de uma folha so traz o seguinte inteiro
    junto, e as duas pecas terminam na MESMA pagina."""
    from justica_mcp.core.acervo import cobertura_do_acervo

    indice = _indice_com(tmp_path, {N(1356): 3, N(1357): 2})
    cob = cobertura_do_acervo(indice)
    assert len(cob["contidas"]) == 1
    assert cob["contidas"][0]["arquivo"] == N(1357)
    assert cob["contidas"][0]["dentro_de"] == N(1356)
    assert cob["folhas_repetidas"] == 2
    assert cob["distintas"] == 3, "cinco folhas somadas, tres paginas distintas"


def test_peca_que_apenas_encosta_na_outra_nao_e_contida(tmp_path):
    """1342 com duas folhas cobre 1342 e 1343; 1344 comeca onde a outra acaba e
    nao esta dentro dela."""
    from justica_mcp.core.acervo import cobertura_do_acervo

    cob = cobertura_do_acervo(_indice_com(tmp_path, {N(1342): 2, N(1344): 2}))
    assert cob["contidas"] == []
    assert cob["faltam"] == []
    assert cob["distintas"] == 4


def test_o_buraco_entre_duas_pecas_e_apontado(tmp_path):
    """1349 com duas folhas cobre 1349 e 1350; a proxima peca comeca em 1354.
    As paginas 1351 a 1353 nao estao em arquivo nenhum."""
    from justica_mcp.core.acervo import cobertura_do_acervo

    cob = cobertura_do_acervo(_indice_com(tmp_path, {N(1349): 2, N(1354): 2}))
    assert cob["faltam"] == [1351, 1352, 1353]
    assert cob["faixas_que_faltam"] == [(1351, 1353)]


def test_buracos_separados_viram_faixas_separadas(tmp_path):
    from justica_mcp.core.acervo import cobertura_do_acervo

    cob = cobertura_do_acervo(
        _indice_com(tmp_path, {N(1): 1, N(5): 1, N(7): 1}))
    assert cob["faixas_que_faltam"] == [(2, 4), (6, 6)]


def test_arquivo_sem_pagina_no_nome_fica_de_fora_e_e_dito(tmp_path):
    """Integra antiga nao tem pagina no nome. Ela nao pode entrar na conta como
    se comecasse na pagina zero, e tampouco sumir em silencio."""
    from justica_mcp.core.acervo import cobertura_do_acervo

    indice = _indice_com(tmp_path, {N(1342): 2, "integra-2026.pdf": 5})
    cob = cobertura_do_acervo(indice)
    assert cob["sem_pagina"] == ["integra-2026.pdf"]
    assert [p["inicio"] for p in cob["pecas"]] == [1342]


def test_pasta_que_nao_existe_nao_derruba(tmp_path):
    from justica_mcp.core.acervo import Indice, cobertura_do_acervo

    cob = cobertura_do_acervo(
        Indice(numero="x", pasta=tmp_path / "nao-existe"))
    assert cob["existe"] is False


# ======================================================================
# O RELATO
# ======================================================================


def test_o_relato_diz_quantas_folhas_estao_repetidas(tmp_path):
    from justica_mcp.core.acervo import cobertura_do_acervo, relatar_a_cobertura

    cob = cobertura_do_acervo(_indice_com(tmp_path, {N(1356): 3, N(1357): 2}))
    junto = " ".join(relatar_a_cobertura(cob))
    assert "REPETIDO: 1 peca(s)" in junto
    assert "2 folha(s) contadas duas vezes de 5" in junto
    assert "nao se descarta por inferencia" in junto


def test_o_relato_liga_o_buraco_ao_prazo(tmp_path):
    """Quem le precisa saber por que 26 paginas ausentes importam: elas podem
    ser as pecas que fixam termo inicial."""
    from justica_mcp.core.acervo import cobertura_do_acervo, relatar_a_cobertura

    cob = cobertura_do_acervo(_indice_com(tmp_path, {N(1349): 2, N(1354): 2}))
    junto = " ".join(relatar_a_cobertura(cob))
    assert "FALTAM 3 pagina(s)" in junto
    assert "1351-1353" in junto
    assert "termo inicial de prazo" in junto


def test_pasta_sem_buraco_nao_se_declara_completa(tmp_path):
    """O intervalo pode comecar depois do inicio dos autos, e foi exatamente o
    que aconteceu: a pasta comecava na pagina 1342 de um processo cujo indice
    numera documentos a partir de pagina de tres algarismos."""
    from justica_mcp.core.acervo import cobertura_do_acervo, relatar_a_cobertura

    cob = cobertura_do_acervo(_indice_com(tmp_path, {N(1342): 2, N(1344): 2}))
    junto = " ".join(relatar_a_cobertura(cob))
    assert "Sem repeticao e sem buraco" in junto
    assert "nao diz que a copia esta completa" in junto


def test_o_reindexar_relata_a_cobertura():
    """Guarda de fonte: a conta nao pode voltar a ser feita a mao."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.reindexar)
    assert "cobertura_do_acervo(indice)" in fonte
    assert "relatar_a_cobertura(" in fonte


def test_a_pagina_do_nome_tem_uma_fonte_so():
    """Duas copias do mesmo padrao divergem no primeiro conserto, e divergir
    aqui faria a leitura abrir um documento e a cobertura medir outro."""
    import inspect

    from justica_mcp import pecas

    fonte = inspect.getsource(pecas.peca_do_nome)
    assert "from .core.acervo import pagina_do_nome" in fonte
    assert "re.compile" not in inspect.getsource(pecas)
