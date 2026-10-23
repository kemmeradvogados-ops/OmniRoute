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
