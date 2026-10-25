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
    assert "nao conclua que uma peca nao existe nos" in fonte.lower()
    assert "faixas_que_faltam" in fonte


def test_as_duas_ferramentas_novas_respeitam_onde_ler():
    """Acervo da banca e pasta de leituras sao lugares diferentes."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    trecho = fonte.split("async def justica_cobertura_do_processo")[1].split(
        "async def justica_ler_peca")[0]
    assert trecho.count("_na_pasta(") == 2


# --------------------------------------------------------------------------
# Varios processos numa autenticacao so
# --------------------------------------------------------------------------


def test_todos_os_numeros_sao_conferidos_antes_de_abrir_o_navegador(capsys):
    """Descobrir na quarta consulta que o terceiro numero esta errado custaria
    a corrida inteira, e ela ja gastou a autenticacao."""
    from justica_mcp import portal

    codigo = portal.consultar_processo(
        "https://x.jus.br/", "TJRJ", "pje", "0809090-88.2023.8.19.0001",
        processos_adicionais=("0000000-00.0000.0.00.0000",))
    assert codigo == 1
    assert "igito verificador" in capsys.readouterr().err


def test_o_laco_corre_todos_e_nao_para_no_primeiro_erro():
    """Numa corrida de dez, perder o restante porque o terceiro nao abriu
    seria trocar nove resultados por um erro."""
    import ast
    import inspect
    import textwrap

    from justica_mcp import portal

    fonte = textwrap.dedent(inspect.getsource(portal.consultar_processo))
    arvore = ast.parse(fonte)
    laco = next(n for n in ast.walk(arvore)
                if isinstance(n, ast.FunctionDef) and n.name == "depois")
    corpo = ast.unparse(laco)
    assert "for posicao, cada in enumerate(numeros" in corpo
    # A falha de um vira registro, e nao `raise`.
    assert "falharam.append" in corpo
    assert "except Exception as exc" in corpo
    # E nao ha `return` dentro do laco, que encerraria a corrida.
    for no in ast.walk(laco):
        if isinstance(no, ast.For):
            assert not [s for s in ast.walk(no) if isinstance(s, ast.Return)], \
                "um return dentro do laco encerraria os processos seguintes"


def test_o_codigo_de_saida_denuncia_qualquer_falha():
    """Quem roda por script precisa saber que um dos dez nao veio."""
    import ast
    import inspect
    import textwrap

    from justica_mcp import portal

    fonte = textwrap.dedent(inspect.getsource(portal.consultar_processo))
    laco = next(n for n in ast.walk(ast.parse(fonte))
                if isinstance(n, ast.FunctionDef) and n.name == "depois")
    assert "return 1 if falharam else 0" in ast.unparse(laco)


def test_a_opcao_de_processo_e_repetivel_na_linha_de_comando():
    import inspect

    from justica_mcp import cli

    fonte = inspect.getsource(cli.main)
    assert 'action="append"' in fonte
    assert "processos_adicionais=tuple(pedidos[1:])" in fonte


def test_sem_processo_nenhum_o_do_env_entra_como_unico():
    """`--processo` repetivel chega como lista, e o padrao do .env tem de
    entrar na mesma forma, senao o primeiro caractere do numero viraria o
    processo inteiro."""
    from justica_mcp import portal

    class _Args:
        url = "https://x.jus.br/"
        tribunal = "TJRJ"
        sistema = "pje"
        perfil = None
        processo = None
        grau = 1

    args = _Args()

    class _Config:
        url = "https://x.jus.br/"
        perfil = None
        processo_teste = "0809090-88.2023.8.19.0001"
        processo_teste_2g = None
        rotulo = "TJRJ / pje"

    import justica_mcp.portal as modulo

    original = modulo.config_portal
    modulo.config_portal = lambda t, s: _Config()
    try:
        modulo._do_ambiente(args)
    finally:
        modulo.config_portal = original
    assert args.processo == ["0809090-88.2023.8.19.0001"]


def test_o_conector_recusa_processos_de_portais_diferentes():
    """Guarda de fonte: eles exigem sessoes diferentes, e aceitar faria a
    corrida gastar a autenticacao para falhar na tela errada."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    assert "portais_diferentes" in fonte
    assert "sistema_do_outro != sistema" in fonte
    # E a conferencia acontece ANTES de o trabalho comecar.
    assert fonte.index("sistema_do_outro != sistema") < fonte.index(
        'MURAL.comecar("download dos autos"')


def test_a_situacao_explica_o_que_e_perfil_definido():
    """Dado que chega sem explicacao vira resposta hesitante.

    Em 25/10/2026 o modelo respondeu, em voz alta, "nao posso verificar o que
    esse campo significa na pratica", sobre um campo do nosso proprio
    servidor. A explicacao custa tres linhas.
    """
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    assert "sobre_perfil_definido" in fonte
    assert "a tentativa ja foi gasta" in fonte
    assert "DESDE O ULTIMO" in fonte


# --------------------------------------------------------------------------
# Download cortado, que comeca com a marca de PDF e nao termina
# --------------------------------------------------------------------------


def test_arquivo_sem_a_marca_de_fim_e_tratado_como_cortado(tmp_path):
    """Conferir so o COMECO nao basta: download interrompido tem `%PDF-`
    tambem. O que ele nao tem e a marca de encerramento."""
    from justica_mcp.core.acervo import parece_truncado

    inteiro = tmp_path / "inteiro.pdf"
    inteiro.write_bytes(b"%PDF-1.4" + b"x" * 500 + b"\n%%EOF\n")
    cortado = tmp_path / "cortado.pdf"
    cortado.write_bytes(b"%PDF-1.4" + b"x" * 5000)
    assert parece_truncado(inteiro) is False
    assert parece_truncado(cortado) is True


def test_arquivo_vazio_conta_como_cortado(tmp_path):
    from justica_mcp.core.acervo import parece_truncado

    vazio = tmp_path / "vazio.pdf"
    vazio.write_bytes(b"")
    assert parece_truncado(vazio) is True


def test_sem_poder_conferir_a_resposta_e_duvida_e_nao_negativa(tmp_path):
    """Dizer que esta inteiro sem ter conferido seria pior que admitir a
    duvida."""
    from justica_mcp.core.acervo import parece_truncado

    assert parece_truncado(tmp_path / "nao-existe.pdf") is None


def test_lixo_depois_da_marca_de_fim_nao_acusa_corte(tmp_path):
    """A norma admite bytes depois do encerramento, e leitor nenhum reclama."""
    from justica_mcp.core.acervo import parece_truncado

    arquivo = tmp_path / "com-sobra.pdf"
    arquivo.write_bytes(b"%PDF-1.4" + b"x" * 300 + b"%%EOF" + b"\x00" * 200)
    assert parece_truncado(arquivo) is False


def test_a_cobertura_acusa_o_arquivo_cortado(acervo):
    from justica_mcp.core.acervo import carregar_indice, cobertura_do_acervo

    pasta = acervo / UM
    pasta.mkdir(parents=True)
    (pasta / "doc-pagina1-cortado.pdf").write_bytes(b"%PDF-1.4" + b"x" * 900)
    dados = cobertura_do_acervo(carregar_indice(UM, formatar_numero(UM)))
    assert len(dados["truncados"]) == 1
    assert dados["truncados"][0]["arquivo"] == "doc-pagina1-cortado.pdf"


def test_o_download_recusa_indexar_arquivo_cortado():
    """Guarda de fonte: indexar um PDF cortado como integra faria quem o lesse
    concluir que o processo acaba onde o download parou."""
    import inspect

    from justica_mcp import portal

    fonte = inspect.getsource(portal._baixar_autos_do_pje)
    assert "_cortado(baixado)" in fonte
    assert "chegou CORTADO" in fonte
    assert fonte.index("_cortado(baixado)") < fonte.index(
        "indice.avaliar_repeticao(baixado)")


def test_a_conclusao_nao_afirma_cobertura_quando_nada_foi_medido():
    """Guarda de fonte: em 25/10/2026 a conclusao disse "a pasta cobre as
    folhas sem buraco" num processo cujo unico arquivo ficou de fora da conta.
    Lista de faixas faltantes vazia por nao haver o que comparar nao e o mesmo
    que nada faltando, e a conclusao e a frase que alguem le rapido e
    repete."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    assert "NAO DA PARA MEDIR a cobertura por faixa" in fonte
    assert "NAO porque nada falte" in fonte
    assert 'medidas = dados.get("pecas") or []' in fonte
    # E quando ha medida, a frase nao promete o processo inteiro.
    assert "NAO quer dizer" in fonte
    assert "pode haver folhas antes da" in fonte


# --------------------------------------------------------------------------
# Tribunal com mais de um sistema ativo
# --------------------------------------------------------------------------


def test_o_advogado_pode_dizer_o_sistema_quando_o_programa_nao_sabe():
    """O Tribunal de Justica do Rio de Janeiro esta em migracao e tem tres
    sistemas ativos. O resolvedor responde `indeterminado`, o que e honesto, e
    ate 25/10/2026 nao havia como contornar: a ferramenta recusava com uma
    mensagem sobre portal nao configurado, que apontava para o lugar errado."""
    from justica_mcp.tools import _sistema_pedido_ou_resolvido

    class _Resolucao:
        sistema = "indeterminado"
        motivo = "tres sistemas ativos em migracao"

    sistema, duvida = _sistema_pedido_ou_resolvido(None, "pje", _Resolucao())
    assert sistema == "pje"
    assert duvida is None


def test_sem_o_advogado_dizer_o_programa_admite_que_nao_sabe():
    from justica_mcp.tools import _sistema_pedido_ou_resolvido

    class _Resolucao:
        sistema = "indeterminado"
        motivo = "tres sistemas ativos"

    sistema, duvida = _sistema_pedido_ou_resolvido(None, None, _Resolucao())
    assert sistema is None
    assert "tres sistemas" in duvida


def test_o_que_o_programa_descobre_sozinho_continua_valendo():
    from justica_mcp.tools import _sistema_pedido_ou_resolvido

    class _Resolucao:
        sistema = "eproc"
        motivo = ""

    assert _sistema_pedido_ou_resolvido(None, None, _Resolucao())[0] == "eproc"
    # E o que o advogado diz tem precedencia sobre o palpite.
    assert _sistema_pedido_ou_resolvido(None, "pje", _Resolucao())[0] == "pje"


def test_a_recusa_diz_o_que_fazer_e_quais_sistemas_existem():
    """Guarda de fonte: recusa que nao diz o caminho obriga o modelo a
    adivinhar, e ele adivinhou errado em 25/10/2026."""
    import inspect

    from justica_mcp import tools

    fonte = inspect.getsource(tools.registrar)
    assert "sistema_indeterminado" in fonte
    assert "Pergunte ao advogado e repita com `sistema`" in fonte
    assert "Configurados para este tribunal" in fonte


def test_o_diagnostico_nao_tenta_rodar_a_suite_inteira():
    """Guarda de fonte: em 25/10/2026 o diagnostico acusou [FALHA] por tempo
    limite numa suite que estava verde. Diagnostico que grita falha onde nao
    ha manda procurar defeito inexistente, e custa o tempo de quem procura."""
    import inspect

    from justica_mcp import diagnostico

    fonte = inspect.getsource(diagnostico)
    assert "amostra rapida" in fonte
    assert "A suite completa passa de" in fonte
    # E nao passa a pasta de testes inteira ao pytest.
    assert 'str(raiz / "tests")]' not in fonte
    assert 'rapidos = [' in fonte
