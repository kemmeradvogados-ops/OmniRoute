"""Testes do mural de trabalhos demorados.

O download dos autos leva de minutos a horas. A ferramenta do servidor pede e
volta na hora; quem faz o trabalho e um processo separado. Estes testes
cobrem o mural sem abrir processo nenhum: o `_abrir` e trocado por um duble.
"""

from __future__ import annotations

import time

from justica_mcp import trabalhos
from justica_mcp.trabalhos import CONCLUIDO, EM_CURSO, FALHOU, Mural


class _ProcessoDeMentira:
    """Duble do processo: entrega as linhas e um codigo de saida."""

    def __init__(self, linhas, codigo=0, demora=0.0):
        self.stdout = iter(linhas)
        self._codigo = codigo
        self._demora = demora

    def wait(self):
        if self._demora:
            time.sleep(self._demora)
        return self._codigo


def _esperar(trabalho, segundos=3.0):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if trabalho.estado != EM_CURSO:
            return True
        time.sleep(0.01)
    return False


def test_o_trabalho_termina_concluido_e_guarda_o_relato():
    mural = Mural()
    t = mural.comecar("download", "0809090-88.2023.8.19.0001", ["consultar"],
                      _abrir=lambda a: _ProcessoDeMentira(
                          ["primeira\n", "segunda\n", "AUTOS gravados\n"]))
    assert _esperar(t)
    assert t.estado == CONCLUIDO
    assert t.codigo == 0
    assert t.relato == ["primeira", "segunda", "AUTOS gravados"]


def test_codigo_de_saida_diferente_de_zero_e_falha():
    mural = Mural()
    t = mural.comecar("download", "0809090-88.2023.8.19.0001", ["consultar"],
                      _abrir=lambda a: _ProcessoDeMentira(["parou\n"], codigo=1))
    assert _esperar(t)
    assert t.estado == FALHOU
    assert t.codigo == 1


def test_comando_que_nem_comeca_nao_derruba_o_servidor():
    def _explodir(argumentos):
        raise OSError("sem executavel")

    mural = Mural()
    t = mural.comecar("download", "0809090-88.2023.8.19.0001", ["consultar"],
                      _abrir=_explodir)
    assert _esperar(t)
    assert t.estado == FALHOU
    assert "nao pode ser iniciado" in t.relato[0]


def test_dois_downloads_do_mesmo_processo_nao_correm_juntos():
    """Gastariam duas tentativas, abririam dois navegadores e escreveriam na
    mesma pasta."""
    mural = Mural()
    numero = "0809090-88.2023.8.19.0001"
    t = mural.comecar("download", numero, ["consultar"],
                      _abrir=lambda a: _ProcessoDeMentira([], demora=0.5))
    assert mural.em_curso_para(numero) is t
    assert mural.em_curso_para("0000001-86.2013.8.19.0078") is None
    assert _esperar(t)
    # Terminado, deixa de bloquear.
    assert mural.em_curso_para(numero) is None


def test_o_relato_muito_longo_guarda_o_comeco_e_o_fim():
    """A primeira linha diz o que foi pedido e a ultima diz como terminou."""
    mural = Mural()
    linhas = [f"linha {i}\n" for i in range(trabalhos.TETO_DE_LINHAS + 50)]
    t = mural.comecar("download", "0809090-88.2023.8.19.0001", ["consultar"],
                      _abrir=lambda a: _ProcessoDeMentira(linhas))
    assert _esperar(t)
    assert len(t.relato) == trabalhos.TETO_DE_LINHAS
    assert t.relato[0] == "linha 0"
    assert t.relato[-1] == f"linha {len(linhas) - 1}"
    assert t.cortadas == 50


def test_o_mural_nao_cresce_para_sempre():
    mural = Mural(teto=3)
    for i in range(6):
        t = mural.comecar("download", f"processo {i}", ["consultar"],
                          _abrir=lambda a: _ProcessoDeMentira([]))
        assert _esperar(t)
    assert len(mural.listar(limite=99)) == 3


def test_o_que_esta_em_curso_nao_e_descartado_pelo_teto():
    mural = Mural(teto=2)
    vivo = mural.comecar("download", "vivo", ["consultar"],
                         _abrir=lambda a: _ProcessoDeMentira([], demora=1.0))
    for i in range(4):
        t = mural.comecar("download", f"outro {i}", ["consultar"],
                          _abrir=lambda a: _ProcessoDeMentira([]))
        assert _esperar(t)
    assert mural.ver(vivo.identificador) is not None
    assert _esperar(vivo, segundos=4.0)


def test_o_resumo_nao_traz_o_relato_inteiro():
    mural = Mural()
    t = mural.comecar("download", "0809090-88.2023.8.19.0001", ["consultar"],
                      _abrir=lambda a: _ProcessoDeMentira(
                          [f"l{i}\n" for i in range(30)]))
    assert _esperar(t)
    resumo = t.resumo(ultimas=5)
    assert len(resumo["ultimas_linhas"]) == 5
    assert resumo["linhas_do_relato"] == 30
    assert resumo["estado"] == CONCLUIDO


def test_o_comando_corre_com_o_python_do_proprio_servidor():
    """Guarda de fonte: `python` solto pegaria o do sistema, sem dependencias."""
    import inspect

    fonte = inspect.getsource(trabalhos._abrir_processo)
    assert "sys.executable" in fonte
    assert "justica_mcp.portal" in fonte
    assert "stderr=subprocess.STDOUT" in fonte


def test_o_servidor_nao_compartilha_a_saida_padrao_com_o_download():
    """Guarda de fonte: o servidor fala pela saida padrao.

    Capturar a saida do programa inteiro por quinze minutos calaria tambem as
    respostas do servidor. Por isso o trabalho corre em PROCESSO separado, e
    nao em linha de execucao com `redirect_stdout`.
    """
    import ast
    import inspect

    arvore = ast.parse(inspect.getsource(trabalhos))
    # So o CODIGO: a explicacao de por que nao se usa `redirect_stdout` mora na
    # documentacao do modulo, e procurar o nome no texto acusaria a propria
    # explicacao.
    nomes = {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)}
    nomes |= {no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute)}
    assert "redirect_stdout" not in nomes
    assert "Popen" in nomes


# ==========================================================================
# O trabalho precisa sobreviver ao servidor que o pediu
#
# Encontrado em campo em 29/10/2026. O advogado pediu o download dos autos, o
# login entrou as 16h24, e depois disso nada mais foi registrado: a extensao
# reiniciou quando a conversa se ligou ao computador dele, e o pedido sumiu da
# lista. Nenhuma peca foi gravada.
#
# Duas causas, e as duas precisam de conserto:
#
# 1. O FILHO MORRE JUNTO. A saida dele ia para um CANO cuja ponta de leitura
#    e do servidor. Servidor morto, ponta fechada, e a proxima linha de
#    progresso que o filho escreve recebe cano quebrado. Nao e so perda de
#    registro: o trabalho para de verdade.
#
# 2. O MURAL ESQUECE. Era um `dict` em memoria, e a propria classe dizia
#    "nesta execucao". Depois do reinicio a lista voltava VAZIA, que e pior
#    que voltar dizendo "interrompido": lista vazia se le como "nao havia
#    nada", e foi assim que o erro passou despercebido.
#
# O download de processo grande leva de minutos a horas, e o servidor reinicia
# por motivos que nada tem a ver com ele. Um trabalho dessa duracao nao pode
# depender de o servidor continuar de pe.
# ==========================================================================

def test_o_relato_do_filho_nao_vai_para_cano(tmp_path, monkeypatch):
    """O que a funcao FAZ, e nao o que ela diz.

    A primeira versao deste teste procurava a frase `subprocess.PIPE` no texto
    da funcao, e falhou porque a frase aparece no comentario que explica o
    defeito. Teste de grafia nao ve comportamento, que e a licao do dia: aqui
    a chamada e interceptada e os argumentos conferidos."""
    import subprocess

    from justica_mcp import trabalhos

    visto = {}

    class _Fingido:
        pid = 1

    def _espiao(*argumentos, **nomeados):
        visto.update(nomeados)
        return _Fingido()

    monkeypatch.setattr(trabalhos.subprocess, "Popen", _espiao)
    relato = tmp_path / "relato.log"
    trabalhos._abrir_processo(["consultar"], arquivo_de_relato=str(relato))

    assert visto["stdout"] is not subprocess.PIPE, (
        "saida em cano morre junto com o servidor que a le")
    assert hasattr(visto["stdout"], "write"), "a saida precisa ser um arquivo"
    assert relato.exists(), "o arquivo de relato nao foi criado"
    # Solto do grupo do servidor, de um jeito ou de outro conforme o sistema.
    assert visto.get("start_new_session") or visto.get("creationflags")


def test_o_trabalho_e_anotado_em_disco_ao_comecar(tmp_path, monkeypatch):
    """Anotar DEPOIS nao serve: o reinicio pode chegar antes do fim."""
    from justica_mcp import trabalhos

    monkeypatch.setattr(trabalhos, "diretorio_dos_trabalhos", lambda: tmp_path)
    mural = trabalhos.Mural()

    class _Fingido:
        stdout = None
        pid = 4242

        def wait(self):
            return 0

    t = mural.comecar("baixar", "123", [], _abrir=lambda *a, **kw: _Fingido())
    gravados = trabalhos.trabalhos_gravados(tmp_path)
    assert any(g["trabalho"] == t.identificador for g in gravados), (
        "o trabalho nao foi anotado em disco")


def test_depois_do_reinicio_a_lista_nao_volta_vazia(tmp_path, monkeypatch):
    """O NUCLEO do defeito de 29/10/2026: a lista vazia se le como 'nao havia
    nada', e o que havia era um download interrompido."""
    from justica_mcp import trabalhos

    monkeypatch.setattr(trabalhos, "diretorio_dos_trabalhos", lambda: tmp_path)

    class _Fingido:
        stdout = None
        pid = 4242

        def wait(self):
            return 0

    antigo = trabalhos.Mural()
    t = antigo.comecar("baixar", "123", [], _abrir=lambda *a, **kw: _Fingido())

    # O servidor morre e outro sobe. Mural novo, memoria zerada.
    novo = trabalhos.Mural()
    listados = novo.listar()
    assert listados, "a lista voltou vazia depois do reinicio"
    assert any(x["trabalho"] == t.identificador for x in listados)


def test_trabalho_cujo_processo_morreu_e_dito_interrompido(tmp_path, monkeypatch):
    """Nao basta lembrar: tem que dizer a VERDADE sobre o que aconteceu.

    A anotacao e escrita A MAO aqui, de proposito. A primeira versao usava um
    duble que terminava na hora, e por isso o trabalho nunca chegava a ficar
    EM_CURSO em disco: o teste media outra coisa. O que se quer reproduzir e o
    rastro deixado por um servidor que MORREU no meio, e esse rastro e um
    registro em curso cujo processo nao responde mais."""
    import json

    from justica_mcp import trabalhos

    monkeypatch.setattr(trabalhos, "diretorio_dos_trabalhos", lambda: tmp_path)
    monkeypatch.setattr(trabalhos, "processo_vivo", lambda pid, desde: False)

    (tmp_path / "abc123.json").write_text(json.dumps({
        "trabalho": "abc123", "acao": "baixar", "processo": "123",
        "estado": trabalhos.EM_CURSO, "comecou_em": "2026-10-29T16:24:00+00:00",
        "terminou_em": None, "codigo_de_saida": None,
        "arquivo_de_relato": str(tmp_path / "abc123.log"), "pid": 4242,
        "observacao": None,
    }), encoding="utf-8")

    achado = trabalhos.Mural().listar()[0]
    assert achado["estado"] == trabalhos.INTERROMPIDO
    assert "reinic" in (achado.get("observacao") or "").lower(), (
        "quem le precisa saber POR QUE parou, nao so que parou")
    assert "retomar" in (achado.get("observacao") or "").lower(), (
        "e precisa saber o que FAZER, que aqui e retomar por uma autenticacao")


def test_trabalho_em_curso_cujo_processo_responde_continua_em_curso(tmp_path,
                                                                    monkeypatch):
    """O outro lado da mesma regra: nao declarar morto o que esta vivo.

    Sem isto, bastaria marcar tudo como interrompido para o teste acima passar,
    e um download em andamento apareceria como parado."""
    import json

    from justica_mcp import trabalhos

    monkeypatch.setattr(trabalhos, "diretorio_dos_trabalhos", lambda: tmp_path)
    monkeypatch.setattr(trabalhos, "processo_vivo", lambda pid, desde: True)

    (tmp_path / "vivo01.json").write_text(json.dumps({
        "trabalho": "vivo01", "acao": "baixar", "processo": "123",
        "estado": trabalhos.EM_CURSO, "comecou_em": "2026-10-29T16:24:00+00:00",
        "terminou_em": None, "codigo_de_saida": None,
        "arquivo_de_relato": str(tmp_path / "vivo01.log"), "pid": 4242,
        "observacao": None,
    }), encoding="utf-8")

    achado = trabalhos.Mural().listar()[0]
    assert achado["estado"] == trabalhos.EM_CURSO


def test_o_relato_herdado_e_lido_do_arquivo_do_filho(tmp_path, monkeypatch):
    """Depois do reinicio nao ha relato em memoria, e o do filho esta no
    arquivo. Sem ler dali, o trabalho herdado apareceria mudo."""
    import json

    from justica_mcp import trabalhos

    monkeypatch.setattr(trabalhos, "diretorio_dos_trabalhos", lambda: tmp_path)
    monkeypatch.setattr(trabalhos, "processo_vivo", lambda pid, desde: True)

    (tmp_path / "rel001.log").write_text(
        "login enviado\nVisualizador aberto\n17 documentos no indice\n",
        encoding="utf-8")
    (tmp_path / "rel001.json").write_text(json.dumps({
        "trabalho": "rel001", "acao": "baixar", "processo": "123",
        "estado": trabalhos.EM_CURSO, "comecou_em": "2026-10-29T16:24:00+00:00",
        "terminou_em": None, "codigo_de_saida": None,
        "arquivo_de_relato": str(tmp_path / "rel001.log"), "pid": 4242,
        "observacao": None,
    }), encoding="utf-8")

    achado = trabalhos.Mural().listar()[0]
    assert "17 documentos no indice" in achado["ultimas_linhas"][-1]


def test_a_anotacao_nunca_e_lida_pela_metade(tmp_path, monkeypatch):
    """A gravacao e atomica: temporario e depois troca de nome.

    Escrever direto no alvo deixava uma janela em que o arquivo existia pela
    metade, e `trabalhos_gravados` pula JSON invalido em silencio. O leitor
    que chegasse ali nao via o trabalho, e a lista voltava sem ele: o MESMO
    sintoma que este modulo corrige, por outra causa. Achado em 29/10/2026 por
    um teste que falhava de forma intermitente."""
    from justica_mcp import trabalhos

    monkeypatch.setattr(trabalhos, "diretorio_dos_trabalhos", lambda: tmp_path)

    vistos = []
    escrita_real = trabalhos.Path.write_text

    def _espiar(self, *a, **kw):
        # Enquanto o temporario e escrito, o alvo final nao pode existir pela
        # metade: ou nao existe, ou esta inteiro.
        final = tmp_path / "abc.json"
        if final.exists():
            import json as _j
            _j.loads(final.read_text(encoding="utf-8"))  # levanta se parcial
            vistos.append(True)
        return escrita_real(self, *a, **kw)

    monkeypatch.setattr(trabalhos.Path, "write_text", _espiar)

    t = trabalhos.Trabalho(identificador="abc", acao="baixar", numero="1")
    mural = trabalhos.Mural()
    mural._gravar(t)
    mural._gravar(t)
    assert (tmp_path / "abc.json").exists()
    assert not list(tmp_path.glob("*.parcial")), (
        "o arquivo temporario precisa sumir na troca de nome")


def test_a_pasta_de_relatos_nao_cresce_para_sempre(tmp_path, monkeypatch):
    """O mural em memoria tinha teto. Em disco, sem limpeza, trocariamos um
    defeito por outro."""
    from justica_mcp import trabalhos

    monkeypatch.setattr(trabalhos, "diretorio_dos_trabalhos", lambda: tmp_path)

    class _Fingido:
        stdout = None
        pid = 4242

        def wait(self):
            return 0

    mural = trabalhos.Mural()
    for i in range(trabalhos.TETO_DE_TRABALHOS + 8):
        mural.comecar("baixar", str(i), [], _abrir=lambda *a, **kw: _Fingido())

    gravados = trabalhos.trabalhos_gravados(tmp_path)
    assert len(gravados) <= trabalhos.TETO_DE_TRABALHOS, len(gravados)
