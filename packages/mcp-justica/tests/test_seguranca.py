"""A fronteira de somente leitura precisa ser estrutural, nao uma promessa."""

import pytest

from justica_mcp.core.capabilities import (
    MATRIZ, Capacidade, Declaracao, Situacao, adaptadores_para,
)
from justica_mcp.core.seguranca import FronteiraViolada, verificar_somente_leitura


def test_versao_1_sobe_somente_leitura():
    verificar_somente_leitura()


def test_habilitar_ciencia_por_engano_aborta_a_inicializacao(monkeypatch):
    """Dar ciencia consome prazo (lei nº. 11.419/06, artigo 5º, §3º).
    Se algum dia isso for declarado disponivel sem decisao expressa, o servidor
    deve se recusar a subir em vez de expor a ferramenta."""
    monkeypatch.setitem(
        MATRIZ["eproc"], Capacidade.DAR_CIENCIA_INTIMACAO,
        Declaracao(Situacao.DISPONIVEL, ""),
    )
    with pytest.raises(FronteiraViolada, match="somente leitura"):
        verificar_somente_leitura()


def test_nenhum_adaptador_da_ciencia_hoje():
    assert adaptadores_para(Capacidade.DAR_CIENCIA_INTIMACAO) == []


def test_busca_por_parte_nao_e_prometida_por_ninguem():
    """DataJud nao publica partes. Declarar isso evita que o agente invente
    uma explicacao quando a busca voltar vazia."""
    assert adaptadores_para(Capacidade.BUSCAR_POR_PARTE) == []


def test_integra_nao_e_prometida_na_fase_1():
    assert adaptadores_para(Capacidade.BAIXAR_INTEGRA) == []


def test_ferramenta_de_credenciais_nao_pode_devolver_segredo():
    """A ferramenta de situacao do cofre alimenta o contexto do modelo.
    Se algum dia passar a devolver valor, a credencial vaza para o chat.
    Este teste trava o formato: apenas presenca."""
    import json

    from justica_mcp.core.cofre import Cofre, Identidade

    class Memoria:
        def __init__(self):
            self.d = {}

        def get_password(self, s, u):
            return self.d.get((s, u))

        def set_password(self, s, u, p):
            self.d[(s, u)] = p

        def delete_password(self, s, u):
            self.d.pop((s, u), None)

    cofre = Cofre(Memoria())
    identidade = Identidade("TJRJ", "eproc")
    cofre.guardar_senha(identidade, "SenhaSecreta123!")
    cofre.guardar_semente(identidade, "ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567")

    saida = json.dumps([cofre.situacao(identidade)])
    assert "SenhaSecreta123!" not in saida
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" not in saida
    # E so pode conter estas chaves.
    assert set(cofre.situacao(identidade)) == {
        "identidade", "login_guardado", "senha_guardada", "semente_guardada",
        "pronta_para_uso",
    }


# --------------------------------------------------------------------------
# Numero de processo em repositorio publico
#
# Este repositorio e PUBLICO. Numero de processo identifica parte, e por isso
# nenhum numero de processo de verdade pode estar no codigo, nos testes ou na
# documentacao. Em 23/10/2026 tres numeros reais, dados pelo operador para
# servirem de caso de teste, foram encontrados em arquivos versionados: um
# deles em trinta e sete lugares. Foram trocados por numeros ficticios.
#
# A guarda abaixo e por LISTA DECLARADA, e nao por lista de proibidos. Lista de
# proibidos obrigaria a escrever o numero real aqui para poder proibi-lo, que e
# exatamente o que nao se quer. Assim, todo numero com forma de processo que
# aparecer na arvore tem de constar desta lista, e acrescentar um e um ato
# deliberado de quem o escreve.
# --------------------------------------------------------------------------

import re as _re
from pathlib import Path as _Path

FORMA_DE_NUMERO = _re.compile(
    r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b|\b\d{20}\b")

PASTAS_CONFERIDAS = ("src", "tests", "docs", "conector")
FINAIS_CONFERIDOS = (".py", ".md", ".json", ".mjs", ".txt")

# Numeros FICTICIOS declarados. Nenhum pertence a processo de cliente.
NUMEROS_DECLARADOS = {
    "00000000000000000000",
    "00000000000000000001",
    "00000010220208190001",
    "00000011120208190001",
    "00000011120208190002",
    "00000016920268190001",
    "00000017820208260100",
    "00000018620138190078",
    "00000018820198190001",
    "00000019920264025101",
    "00000019920268190001",
    "00001230000000000000",
    "00111111120158190001",
    "00222222220168190002",
    "00450259320218190002",
    "00699003119995010009",
    "00961025220188190001",
    "08090908820238190001",
    "09989755320258190001",
    "10000015620238260100",
    "20817221720268260000",
    "50012345420234025101",
    "50684566820254025101",
    "90040295020258230000",
    "99999999920998190001",
    "99999999920999990000",
}


def _numeros_na_arvore() -> dict:
    # Este arquivo e a DECLARACAO, nao uso: contar os numeros dele faria toda
    # entrada declarada parecer usada, e a guarda de entrada morta nunca mais
    # acusaria nada.
    raiz = _Path(__file__).resolve().parent.parent
    aqui = _Path(__file__).resolve()
    achados: dict = {}
    for pasta in PASTAS_CONFERIDAS:
        alvo = raiz / pasta
        if not alvo.is_dir():
            continue
        for caminho in alvo.rglob("*"):
            if caminho.suffix not in FINAIS_CONFERIDOS or not caminho.is_file():
                continue
            if caminho.resolve() == aqui:
                continue
            try:
                texto = caminho.read_text(errors="ignore")
            except OSError:
                continue
            for bruto in FORMA_DE_NUMERO.findall(texto):
                digitos = _re.sub(r"\D", "", bruto)
                achados.setdefault(digitos, set()).add(
                    str(caminho.relative_to(raiz)))
    return achados


def test_nenhum_numero_de_processo_nao_declarado_na_arvore():
    """Repositorio publico: todo numero com forma de processo e ficticio.

    Se este teste quebrou ao acrescentar um caso novo, a pergunta nao e como
    calar a guarda: e se o numero que entrou e de processo de verdade. Sendo
    ficticio, declare-o em `NUMEROS_DECLARADOS`. Sendo real, tire-o.
    """
    achados = _numeros_na_arvore()
    intrusos = {
        numero: sorted(arquivos) for numero, arquivos in achados.items()
        if numero not in NUMEROS_DECLARADOS
    }
    # O relato nao imprime o numero: imprime onde ele esta, que e o que
    # resolve, sem repetir o dado numa saida que vai parar em conversa.
    onde = sorted({arq for lista in intrusos.values() for arq in lista})
    assert not intrusos, (
        f"{len(intrusos)} numero(s) com forma de processo fora da lista "
        f"declarada, em: {onde}")


def test_a_lista_declarada_nao_tem_entrada_morta():
    """Entrada que nao corresponde a nada na arvore e lixo que esconde o resto."""
    achados = set(_numeros_na_arvore())
    mortas = sorted(NUMEROS_DECLARADOS - achados)
    assert not mortas, f"{len(mortas)} entrada(s) declarada(s) sem uso: {mortas}"
