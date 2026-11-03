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
# Declarar aqui NAO torna um numero ficticio: declarar diz que alguem
# CONFERIU que ele e ficticio. Em 25/10/2026 dois numeros reais de
# processo de cliente estavam nesta lista, e por isso o guarda os deixava
# passar num repositorio publico. Digito verificador valido nao prova
# nada: os ficticios daqui tambem tem digito valido, de proposito, para
# que `parse_numero` os aceite. A unica conferencia que vale e olhar se o
# numero esta no acervo do escritorio. Na duvida, troque em vez de
# declarar: trocar custa um sed, e o numero que vaza nao volta.
NUMEROS_DECLARADOS = {
    "00000000000000000000",
    "00000000000000000001",
    "00000010220208190001",
    "00000011120208190001",
    "00000011120208190002",
    "00000011620198190001",
    "00000016920268190001",
    "00000017820208260100",
    "00000018620138190078",
    "00000018820198190001",
    "00000018820198260100",
    "00000019920264025101",
    "00000019920268190001",
    "00000028820198190001",
    "00000029720198260100",
    "00000029820198190001",
    "00000038820198190001",
    "00000049420218190002",
    "00000057620254025101",
    "00001230000000000000",
    "00111111120158190001",
    "00222222220168190002",
    "00699003119995010009",
    "00961025220188190001",
    "08090908820238190001",
    "09989755320258190001",
    "10000015620238260100",
    "20817221720268260000",
    "50000019120264020000",
    "50012345420234025101",
    "90040295020258230000",
    "99999999920998190001",
    "99999999920999990000",
    # Escritos em 03/11/2026 para os testes de grau, EM SUBSTITUICAO a quatro
    # numeros reais que vieram da auditoria de 30/10 e que este guarda pegou
    # antes do envio. Sequenciais 0000001 e 9999999 de proposito: numero com
    # essa cara nao se confunde com processo de ninguem.
    "00000017220258199000",   # origem 9000, Conselho Recursal
    "99999992920268190000",   # origem 0000, segunda instancia
    "99999990720188190001",   # primeira instancia
    "99999998020138190001",   # primeira instancia, numero antigo
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


# ==========================================================================
# A espinha dorsal do monitoramento nunca funcionou
#
# Apontado pela auditoria de 30/10/2026: `justica_publicacoes_por_oab`
# devolvia erro "total" para QUALQUER inscricao testada, e a descoberta do
# dossie teve de ser feita a mao, pelo Comunica no navegador.
#
# A auditoria inferiu que "a resposta da fonte deixou de trazer o campo
# 'total'". Nao e isso, e a diferenca importa: o NOSSO proprio adaptador
# nunca devolveu esse campo. Ele devolve `total_informado`, de proposito,
# porque a contagem da fonte satura em 10.000 e reportar aquilo como total
# faria o agente afirmar um numero falso. A ferramenta, do outro lado,
# sempre leu `dados['total']`.
#
# As duas linhas vieram na PRIMEIRA confirmacao do projeto, `ca5ed089`. A
# ferramenta que o proprio texto dela chama de "espinha dorsal do
# monitoramento diario" nunca funcionou, e nao havia um unico teste sobre
# ela.
#
# Pior: a linha que quebrava era a do REGISTRO DE AUDITORIA, depois de os
# dados terem chegado inteiros. A consulta funcionava e o resultado ia para
# o lixo por causa do rotulo de uma anotacao.
# ==========================================================================

def test_o_rotulo_do_total_usa_o_campo_que_o_adaptador_devolve():
    from justica_mcp.adapters.djen import AdaptadorDJEN
    from justica_mcp.tools import rotulo_do_total

    dados = dict(AdaptadorDJEN._resumo_total({"count": 7}, [1, 2, 3]))
    assert "total" not in dados, (
        "se o adaptador voltar a ter 'total', este teste perde o objeto")
    assert rotulo_do_total(dados) == "7 item(ns)"


def test_contagem_saturada_nao_e_anunciada_como_exata():
    """A API satura em 10.000. Anotar isso como total exato poria no registro
    um numero que ninguem pode confirmar."""
    from justica_mcp.adapters.djen import AdaptadorDJEN
    from justica_mcp.tools import rotulo_do_total

    dados = dict(AdaptadorDJEN._resumo_total({"count": 10000}, []))
    rotulo = rotulo_do_total(dados)
    assert "10000" in rotulo
    assert "ou mais" in rotulo, rotulo


def test_consulta_que_deu_certo_nao_se_perde_por_causa_do_rotulo():
    """O NUCLEO do defeito: o registro de auditoria derrubava a chamada
    inteira. Anotacao e importante, mas nunca ao ponto de jogar fora o
    trabalho que ja foi feito e pago."""
    from justica_mcp.tools import rotulo_do_total

    for esquisito in ({}, {"total_informado": None}, {"total_informado": "x"},
                      None):
        assert isinstance(rotulo_do_total(esquisito), str)


# ==========================================================================
# O cliente desiste em 60s, e a consulta continua rodando
#
# Item 2 da auditoria de 30/10/2026, constatado em mais de uma chamada: o
# cliente desiste apos 60 segundos, a consulta CONTINUA, termina e grava, e o
# resultado so aparece depois em `justica_consulta_gravada`.
#
# Essa espera NAO esta no nosso codigo: ela e do aplicativo do Claude, e nao
# temos como mudar. O que da para mudar e de quem e a ultima palavra. Hoje
# quem desiste e o cliente, e o que ele mostra ao advogado e um erro, embora a
# consulta tenha dado certo. O risco esta na reacao: repetir a chamada, gastar
# outra tentativa da conta compartilhada, e nao precisava.
#
# Entao o servidor responde ANTES do limite dele, dizendo onde o resultado vai
# aparecer. O trabalho segue: `asyncio.to_thread` nao para quando a espera
# acaba, e e por isso que a consulta gravava mesmo depois de o cliente sumir.
# ==========================================================================

def test_consulta_que_passa_do_teto_vira_recado_e_nao_erro():
    import asyncio

    from justica_mcp.tools import esperar_ou_avisar

    async def _demorada():
        await asyncio.sleep(0.2)
        return {"ok": True}

    async def _correr():
        return await esperar_ou_avisar(_demorada(), teto=0.01,
                                       aviso={"em_curso": True})

    assert asyncio.run(_correr()) == {"em_curso": True}


def test_consulta_rapida_devolve_o_resultado_de_verdade():
    """O recado e para o caso lento. Processo pequeno tem de continuar
    respondendo de uma vez, sem obrigar a uma segunda pergunta."""
    import asyncio

    from justica_mcp.tools import esperar_ou_avisar

    async def _rapida():
        return {"ok": True}

    async def _correr():
        return await esperar_ou_avisar(_rapida(), teto=5,
                                       aviso={"em_curso": True})

    assert asyncio.run(_correr()) == {"ok": True}


def test_erro_da_consulta_continua_subindo():
    """O teto nao pode engolir falha: erro de credencial precisa chegar ao
    advogado como erro, e nao como 'ainda esta rodando'."""
    import asyncio

    from justica_mcp.tools import esperar_ou_avisar

    async def _explode():
        raise RuntimeError("credencial recusada")

    async def _correr():
        return await esperar_ou_avisar(_explode(), teto=5, aviso={})

    try:
        asyncio.run(_correr())
    except RuntimeError as exc:
        assert "credencial recusada" in str(exc)
    else:
        raise AssertionError("a falha foi engolida pelo teto")


def test_o_teto_do_servidor_fica_abaixo_do_teto_do_cliente():
    """Sessenta segundos e o que a auditoria mediu no cliente. Responder em
    cima da hora nao resolveria: o recado tem de chegar ANTES."""
    from justica_mcp.tools import TETO_DA_RESPOSTA_AO_CLIENTE

    assert TETO_DA_RESPOSTA_AO_CLIENTE < 60
