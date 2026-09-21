"""Importacao da planilha de credenciais.

Estrutura reproduzida da planilha real da banca: colunas ADV, Tribunal,
Sistema, Login, Senha e Codigo Autenticacao, com os rotulos do escritorio
("JFRJ", "TRT RJ") que nao coincidem com os codigos do projeto.

Os valores aqui sao ficticios. O que se testa e o mapeamento e a discricao.
"""

import json
from pathlib import Path

import openpyxl
import pytest

from justica_mcp.core.cofre import Cofre
from justica_mcp.planilha import PlanilhaInvalida, importar

SEMENTE = "ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567"

LINHAS = [
    ("ADV", "Tribunal", "Sistema", "Login", "Senha", "Código Autenticação"),
    ("Diego", "TJRJ", "PJE", "11122233344", "senha-pje", SEMENTE),
    ("Diego", "TJRJ", "EPROC", "11122233344", "senha-eproc", SEMENTE),
    ("Diego", "TJRJ", "DCP", "11122233344", "senha-dcp", "X9!"),
    ("Diego", "JFRJ", "EPROC", "RJ000000", "senha-jfrj", SEMENTE),
    ("Diego", "TRT RJ", "PJE", "11122233344", "senha-trt", SEMENTE),
    ("Diego", "TJSP", "EPROC", "11122233344", "senha-tjsp", SEMENTE),
    ("Carlos", "TJSP", "ESAJ", "99988877766", "senha-esaj", None),
    ("Outro", "TJMG", "PJE", "123", "senha-mg", SEMENTE),
]


class Memoria:
    def __init__(self):
        self.d = {}

    def get_password(self, s, u):
        return self.d.get((s, u))

    def set_password(self, s, u, p):
        self.d[(s, u)] = p

    def delete_password(self, s, u):
        self.d.pop((s, u), None)


@pytest.fixture
def planilha(tmp_path) -> Path:
    wb = openpyxl.Workbook()
    for linha in LINHAS:
        wb.active.append(linha)
    caminho = tmp_path / "senhas_tribunais.xlsx"
    wb.save(caminho)
    return caminho


@pytest.fixture
def cofre():
    return Cofre(Memoria())


def _por_rotulo(resultados):
    return {r.identidade.rotulo: r for r in resultados if r.identidade}


def test_mapeia_rotulos_do_escritorio_para_os_codigos_do_projeto(planilha, cofre):
    """A planilha diz "JFRJ" e "TRT RJ"; o projeto usa TRF2 e TRT1."""
    chaves = {r.identidade.chave for r in importar(planilha, cofre) if r.identidade}
    assert "TRF2:eproc" in chaves, "JFRJ deve virar TRF2"
    assert "TRT1:pje" in chaves, "TRT RJ deve virar TRT1"


def test_importa_os_tres_campos(planilha, cofre):
    r = _por_rotulo(importar(planilha, cofre))["TJRJ / eproc"]
    assert (r.login, r.senha, r.semente) == (True, True, True)
    assert r.completa is True


def test_grava_de_fato_no_cofre(planilha, cofre):
    from justica_mcp.core.cofre import Identidade

    importar(planilha, cofre)
    identidade = Identidade("TJRJ", "eproc")
    assert cofre.situacao(identidade)["pronta_para_uso"] is True
    assert len(cofre._codigo_segundo_fator(identidade)) == 6


def test_segundo_fator_invalido_nao_impede_o_resto(planilha, cofre):
    """Caso real: a linha do portal legado do Rio traz tres caracteres no campo
    de autenticacao, que nao sao semente. Login e senha devem entrar assim
    mesmo, e a linha nao pode ser perdida."""
    r = _por_rotulo(importar(planilha, cofre))["TJRJ / dcp"]
    assert (r.login, r.senha) == (True, True)
    assert r.semente is False
    assert "Segundo fator nao importado" in r.observacao


def test_sem_segundo_fator_na_planilha_e_registrado(planilha, cofre):
    r = _por_rotulo(importar(planilha, cofre))["TJSP / esaj"]
    assert (r.login, r.senha, r.semente) == (True, True, False)
    assert "Sem valor de segundo fator" in r.observacao


def test_tribunal_fora_do_escopo_e_ignorado_com_motivo(planilha, cofre):
    ignoradas = [r for r in importar(planilha, cofre) if r.identidade is None]
    assert len(ignoradas) == 1
    assert "TJMG" in ignoradas[0].rotulo_planilha
    assert "nao reconhecido" in ignoradas[0].observacao


def test_simular_nao_grava_nada(planilha, cofre):
    from justica_mcp.core.cofre import Identidade

    resultados = importar(planilha, cofre, simular=True)
    assert _por_rotulo(resultados)["TJRJ / eproc"].completa is True
    assert cofre.situacao(Identidade("TJRJ", "eproc"))["pronta_para_uso"] is False


def test_resultado_nunca_carrega_valor_de_credencial(planilha, cofre):
    """A invariante do projeto aplicada ao importador: o relatorio e presenca,
    jamais conteudo. Se vazasse, a senha apareceria no terminal e num eventual
    copiar e colar de volta para o chat."""
    resultados = importar(planilha, cofre)
    texto = json.dumps([
        {"linha": r.linha, "rotulo": r.rotulo_planilha,
         "login": r.login, "senha": r.senha, "semente": r.semente,
         "obs": r.observacao}
        for r in resultados
    ])
    for segredo in ("senha-pje", "senha-eproc", "senha-esaj", "11122233344", "RJ000000"):
        assert segredo not in texto
    assert SEMENTE.replace(" ", "") not in texto


def test_planilha_inexistente_da_erro_claro(tmp_path, cofre):
    with pytest.raises(PlanilhaInvalida, match="nao encontrada"):
        importar(tmp_path / "nao-existe.xlsx", cofre)


def test_cabecalho_incompleto_diz_o_que_falta(tmp_path, cofre):
    wb = openpyxl.Workbook()
    wb.active.append(("Tribunal", "Sistema"))
    caminho = tmp_path / "torta.xlsx"
    wb.save(caminho)
    with pytest.raises(PlanilhaInvalida, match="login"):
        importar(caminho, cofre)
