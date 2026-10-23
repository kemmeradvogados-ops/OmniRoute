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

    pasta = tmp_path / "00000018620138190078"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, folhas in arquivos.items():
        (pasta / nome).write_bytes(pdf_com_textos(["folha com texto aqui"] * folhas))
    return Indice(numero="0000001-86.2013.8.19.0078", pasta=pasta)


def N(pagina):
    return f"00000018620138190078-pagina{pagina}-doc.pdf"


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


# ==========================================================================
# BYTES DIFERENTES, TEXTO IDENTICO
#
# Corrida do e-SAJ em 22/10/2026. O acervo ja tinha a integra de um processo,
# de setembro; a corrida baixou de novo, e as duas copias tinham 114 folhas e
# bytes diferentes. O programa classificou como `suspeita` e, corretamente, nao
# numerou: folha errada em citacao e o pior defeito deste indice.
#
# So que "suspeita" devolvia a pergunta ao advogado sem lhe dar como
# responde-la. A resposta foi obtida a mao, comparando o texto das 114 folhas
# com um comando escrito na hora: ZERO folhas diferentes. Era a mesma integra,
# e o que mudava era o carimbo de geracao, que mora fora da camada de texto.
#
# Medir isso e barato e cabe ao programa, nao ao advogado.
# ==========================================================================


def _pdf(paginas, produtor="A"):
    """Um PDF minimo. `produtor` muda os BYTES sem tocar no texto das folhas."""
    import zlib  # noqa: F401  (mantido para simetria com os outros geradores)

    conteudos = [f"BT /F1 12 Tf 72 720 Td ({t}) Tj ET".encode("latin-1")
                 for t in paginas]
    n = len(paginas)
    corpo = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3+i} 0 R" for i in range(n))
    corpo.append(f"<< /Type /Pages /Count {n} /Kids [{kids}] >>".encode())
    for i in range(n):
        corpo.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {3+n*2} 0 R >> >> "
            f"/Contents {3+n+i} 0 R >>".encode())
    for fluxo in conteudos:
        corpo.append(b"<< /Length %d >>\nstream\n" % len(fluxo) + fluxo + b"\nendstream")
    corpo.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    # O produtor entra como objeto proprio: muda o arquivo, nao a folha.
    corpo.append(f"<< /Producer ({produtor}) >>".encode())

    saida, deslocamentos = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(corpo, 1):
        deslocamentos.append(len(saida))
        saida += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    inicio = len(saida)
    saida += f"xref\n0 {len(corpo)+1}\n0000000000 65535 f \n".encode()
    for d in deslocamentos:
        saida += f"{d:010d} 00000 n \n".encode()
    saida += (f"trailer\n<< /Size {len(corpo)+1} /Root 1 0 R /Info "
              f"{len(corpo)} 0 R >>\nstartxref\n{inicio}\n%%EOF\n").encode()
    return bytes(saida)


def test_bytes_diferentes_e_texto_identico_nao_e_suspeita(tmp_path):
    """O caso do e-SAJ. A medida existe para o advogado nao ter de fazer a
    comparacao a mao, como foi preciso em 22/10/2026."""
    from justica_mcp.core.acervo import (
        REPETIDA_NO_TEXTO, Indice, carregar_indice,
    )

    folhas = ["Peticao inicial", "Contrato", "Procuracao"]
    velho = tmp_path / "integra-velha.pdf"
    novo = tmp_path / "integra-nova.pdf"
    velho.write_bytes(_pdf(folhas, produtor="geracao de setembro"))
    novo.write_bytes(_pdf(folhas, produtor="geracao de outubro"))
    assert velho.read_bytes() != novo.read_bytes(), "o ensaio exige bytes diferentes"

    indice = carregar_indice(tmp_path, "00000000000000000000")
    assert isinstance(indice, Indice)
    indice.acrescentar(velho, "integra")

    veredicto, gemeo = indice.avaliar_repeticao(novo)
    assert veredicto == REPETIDA_NO_TEXTO, veredicto
    assert gemeo is not None


def test_texto_diferente_continua_suspeita(tmp_path):
    """A medida nao pode engolir o caso em que ha de fato o que decidir.
    Mesmo numero de folhas e texto diferente continua sendo pergunta."""
    from justica_mcp.core.acervo import (
        REPETIDA_SUSPEITA, carregar_indice,
    )

    velho = tmp_path / "a.pdf"
    novo = tmp_path / "b.pdf"
    velho.write_bytes(_pdf(["Peticao inicial", "Contrato", "Procuracao"]))
    novo.write_bytes(_pdf(["Peticao inicial", "Contrato", "OUTRA COISA"]))

    indice = carregar_indice(tmp_path, "00000000000000000001")
    indice.acrescentar(velho, "integra")
    veredicto, _ = indice.avaliar_repeticao(novo)
    assert veredicto == REPETIDA_SUSPEITA, veredicto


def test_pdf_ilegivel_nao_vira_mesma_copia(tmp_path):
    """`None` precisa ser distinguivel de "sao iguais": um PDF corrompido
    classificado como repetido seria DESCARTADO, e o acervo perderia a copia."""
    from justica_mcp.core.acervo import mesmo_texto

    bom = tmp_path / "bom.pdf"
    bom.write_bytes(_pdf(["Folha"]))
    quebrado = tmp_path / "quebrado.pdf"
    quebrado.write_bytes(b"isto nao e um PDF")
    assert mesmo_texto(bom, quebrado) is None


def test_numero_de_folhas_diferente_e_falso_e_nao_nulo(tmp_path):
    from justica_mcp.core.acervo import mesmo_texto

    uma = tmp_path / "uma.pdf"
    duas = tmp_path / "duas.pdf"
    uma.write_bytes(_pdf(["Folha"]))
    duas.write_bytes(_pdf(["Folha", "Outra"]))
    assert mesmo_texto(uma, duas) is False


def test_a_consulta_trata_o_texto_identico_sem_perguntar():
    """Guarda de fonte: o ramo novo precisa existir no caminho que o advogado
    roda, e nao so na funcao que o mede."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal.consultar_processo)
    assert "REPETIDA_NO_TEXTO" in fonte
    assert "MESMO TEXTO" in fonte
    # E precisa REMOVER o repetido, como ja faz o ramo de bytes iguais: deixar
    # a copia na pasta foi o que produziu dois arquivos com gramaticas de nome
    # diferentes convivendo.
    # Pelo `elif`, e nao pelo nome solto: o nome aparece ANTES, na linha do
    # import, e fatiar por ele devolvia dois caracteres. O teste falhou por
    # isso na primeira escrita, e falhou com razao.
    trecho = (fonte.split("elif veredicto == REPETIDA_NO_TEXTO:")[1]
                   .split("elif veredicto == REPETIDA_SUSPEITA:")[0])
    assert "baixado.unlink()" in trecho


def test_sem_camada_de_texto_a_medida_se_recusa(tmp_path):
    """Integra DIGITALIZADA e imagem pura: toda folha extrai string vazia.

    Sem esta recusa, duas integras digitalizadas DIFERENTES com o mesmo numero
    de folhas dariam "mesmo texto", e o programa APAGARIA uma delas. Ausencia
    de texto nao e prova de igualdade.
    """
    from pypdf import PdfWriter

    from justica_mcp.core.acervo import mesmo_texto

    def em_branco(nome, marca):
        escritor = PdfWriter()
        for _ in range(3):
            escritor.add_blank_page(width=595, height=842)
        escritor.add_metadata({"/Producer": marca})
        caminho = tmp_path / nome
        with open(caminho, "wb") as saida:
            escritor.write(saida)
        return caminho

    a = em_branco("a.pdf", "manha")
    b = em_branco("b.pdf", "tarde")
    assert a.read_bytes() != b.read_bytes()
    assert mesmo_texto(a, b) is None


def test_uma_folha_com_texto_ja_basta_para_medir(tmp_path):
    """A guarda exige QUE HAJA texto, nao que todas as folhas tenham. Integra
    mista, com peticao digitada e anexo digitalizado, continua mensuravel."""
    from justica_mcp.core.acervo import mesmo_texto

    a = tmp_path / "mista-a.pdf"
    b = tmp_path / "mista-b.pdf"
    a.write_bytes(_pdf(["Peticao inicial", "", ""], produtor="setembro"))
    b.write_bytes(_pdf(["Peticao inicial", "", ""], produtor="outubro"))
    assert a.read_bytes() != b.read_bytes()
    assert mesmo_texto(a, b) is True
