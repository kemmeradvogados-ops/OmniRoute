"""Resolucao do sistema pela declaracao da base nacional.

Estrutura confirmada em campo em 21 de setembro de 2026:
    sistema = {'codigo': 1, 'nome': 'PJe'}
    formato = {'codigo': 1, 'nome': 'Eletrônico'}

Apenas o codigo 1 foi observado. Por isso o casamento e feito pelo NOME
normalizado e nunca pelo codigo: montar uma tabela de codigos a partir de uma
unica amostra seria chute com aparencia de mapeamento.
"""

from datetime import datetime, timedelta, timezone

import pytest

from justica_mcp.core.resolver import sistema_de_documento
from justica_mcp.core.tribunais import identificar_tribunal


def _quando(dias_atras: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).isoformat().replace(
        "+00:00", "Z"
    )


def _doc(nome="PJe", dias_atras=1, codigo=1):
    return {
        "sistema": {"codigo": codigo, "nome": nome},
        "dataHoraUltimaAtualizacao": _quando(dias_atras),
    }


TJRJ = identificar_tribunal("8.19")   # PJe, eproc e DCP em migracao
TRT1 = identificar_tribunal("5.01")   # so PJe
TJSP = identificar_tribunal("8.26")   # e-SAJ e eproc em migracao


def test_le_o_sistema_declarado():
    r = sistema_de_documento(_doc(), TRT1)
    assert r.sistema == "pje"
    assert r.origem_da_resolucao == "datajud"


def test_tribunal_sem_ambiguidade_e_ficha_recente_da_confianca_alta():
    assert sistema_de_documento(_doc(dias_atras=1), TRT1).confianca.value == "alta"


def test_tribunal_em_migracao_nunca_recebe_confianca_alta():
    """Rio e Sao Paulo sao exatamente onde a base nacional pode estar atrasada
    em relacao a uma migracao ja ocorrida. E onde errar custa mais caro."""
    r = sistema_de_documento(_doc(dias_atras=0), TJRJ)
    assert r.confianca.value == "media"
    assert "migracao" in r.motivo
    assert sistema_de_documento(_doc(dias_atras=0), TJSP).confianca.value != "alta"


def test_ficha_antiga_rebaixa_a_confianca():
    assert sistema_de_documento(_doc(dias_atras=400), TRT1).confianca.value == "media"


def test_data_ausente_ou_invalida_nao_quebra():
    assert sistema_de_documento({"sistema": {"nome": "PJe"}}, TRT1).confianca.value == "media"
    doc = {"sistema": {"nome": "PJe"}, "dataHoraUltimaAtualizacao": "nao-e-data"}
    assert sistema_de_documento(doc, TRT1).sistema == "pje"


@pytest.mark.parametrize(
    "nome,esperado",
    [("PJe", "pje"), ("pje", "pje"), ("eproc", "eproc"), ("e-SAJ", "esaj"),
     ("SAJ", "esaj"), ("DCP", "dcp"), ("  PJe  ", "pje")],
)
def test_casa_por_nome_normalizado(nome, esperado):
    assert sistema_de_documento(_doc(nome=nome), TRT1).sistema == esperado


def test_nome_desconhecido_nao_vira_chute():
    """Sistema fora do mapa devolve indeterminado dizendo o que a fonte
    respondeu, para o operador conferir e incluir, em vez de forcar um palpite."""
    r = sistema_de_documento(_doc(nome="SistemaNovo"), TRT1)
    assert r.sistema == "indeterminado"
    assert "SistemaNovo" in r.motivo
    assert r.confianca.value == "baixa"


def test_documento_sem_campo_sistema_devolve_nada():
    assert sistema_de_documento({}, TRT1) is None
    assert sistema_de_documento({"sistema": {}}, TRT1) is None
    assert sistema_de_documento({"sistema": "PJe"}, TRT1) is None


def test_a_data_da_ficha_aparece_no_motivo():
    """O agente precisa poder dizer ao advogado o quao velha e a informacao."""
    r = sistema_de_documento(_doc(dias_atras=5), TRT1)
    assert "atualizada em" in r.motivo


# ==========================================================================
# 429 da base nacional: recuar, e recuar pouco
#
# Auditoria de 03/11/2026: o DataJud devolveu `429 Too Many Requests` durante
# a verificacao em lote, e a recusa chegava ao advogado como
#
#   erro_interno: Falha inesperada: HTTPStatusError ... 429 Too Many Requests
#
# que e falso em duas frentes: nao foi inesperada, e nao foi falha. A fonte
# estava no ar e disse, com todas as letras, para esperar.
# ==========================================================================


class _RespostaFalsa:
    def __init__(self, status, headers=None, corpo=None):
        self.status_code = status
        self.headers = headers or {}
        self._corpo = corpo if corpo is not None else {"hits": {"hits": []}}

    def json(self):
        return self._corpo

    def raise_for_status(self):
        return None


def _adaptador_com_respostas(monkeypatch, respostas, dormidas):
    """Adaptador cujas buscas devolvem a fila dada, sem rede e sem dormir."""
    import asyncio

    from justica_mcp.adapters.datajud import AdaptadorDataJud

    adaptador = AdaptadorDataJud()
    fila = list(respostas)
    monkeypatch.setattr(adaptador, "_cabecalhos", lambda: {})

    async def _uma(_url, _consulta, _segundos):
        return fila.pop(0)

    async def _dormir(quanto):
        dormidas.append(quanto)

    monkeypatch.setattr(adaptador, "_uma_busca", _uma)
    monkeypatch.setattr(asyncio, "sleep", _dormir)
    return adaptador


def _tribunal_do_rio():
    from justica_mcp.core.tribunais import identificar_tribunal

    return identificar_tribunal("8.19")


def test_o_429_e_tentado_de_novo_antes_de_virar_recusa(monkeypatch):
    """O NUCLEO: rajada que bate no limite nao pode morrer na primeira."""
    import asyncio

    dormidas = []
    adaptador = _adaptador_com_respostas(
        monkeypatch,
        [_RespostaFalsa(429), _RespostaFalsa(200, corpo={"hits": {"hits": [1]}})],
        dormidas)

    dados = asyncio.run(adaptador._buscar(_tribunal_do_rio(), {"query": {}}))
    assert dados == {"hits": {"hits": [1]}}
    assert dormidas == [2.0], "a primeira espera e a curta"


def test_o_429_que_insiste_vira_recusa_que_diz_quanto_esperar(monkeypatch):
    import asyncio

    from justica_mcp.core.resiliencia import LimiteDeTaxa, PortalIndisponivel

    dormidas = []
    adaptador = _adaptador_com_respostas(
        monkeypatch, [_RespostaFalsa(429)] * 3, dormidas)

    with pytest.raises(LimiteDeTaxa) as erro:
        asyncio.run(adaptador._buscar(_tribunal_do_rio(), {"query": {}}))

    recado = str(erro.value)
    assert "excesso de chamadas" in recado
    assert "nao falhou por defeito nosso" in recado.replace("NAO", "nao")
    assert "disjuntor" not in recado.lower(), (
        "limite de taxa nao e disjuntor; a frase mandaria procurar defeito "
        "que nao existe")
    # Herda de PortalIndisponivel para que `_tratar` ja a traduza como
    # "aguarde a janela indicada antes de repetir".
    assert isinstance(erro.value, PortalIndisponivel)


def test_a_espera_pedida_pela_fonte_e_obedecida_e_dita(monkeypatch):
    """Retry-After nao e sugestao, e o advogado precisa saber de onde veio o
    numero: "a fonte pediu" pesa diferente de "este e o nosso padrao"."""
    import asyncio

    from justica_mcp.core.resiliencia import LimiteDeTaxa

    dormidas = []
    adaptador = _adaptador_com_respostas(
        monkeypatch,
        [_RespostaFalsa(429, headers={"Retry-After": "3"}),
         _RespostaFalsa(200)],
        dormidas)
    asyncio.run(adaptador._buscar(_tribunal_do_rio(), {"query": {}}))
    assert dormidas == [3.0], "a espera da fonte vale mais que o nosso padrao"

    dormidas.clear()
    adaptador = _adaptador_com_respostas(
        monkeypatch, [_RespostaFalsa(429, headers={"Retry-After": "600"})],
        dormidas)
    with pytest.raises(LimiteDeTaxa) as erro:
        asyncio.run(adaptador._buscar(_tribunal_do_rio(), {"query": {}}))
    assert dormidas == [], (
        "600s estoura o teto: a recusa sai na hora em vez de o cliente perder "
        "a janela esperando")
    assert "a propria fonte pediu" in str(erro.value)


def test_a_espera_total_nao_passa_do_teto(monkeypatch):
    """O cliente do conector desiste por volta de 45s. Recuo generoso aqui
    trocaria um erro honesto por um silencio."""
    import asyncio

    from justica_mcp.adapters.datajud import AdaptadorDataJud

    assert sum(AdaptadorDataJud.ESPERAS_NO_429) <= AdaptadorDataJud.TETO_DA_ESPERA_NO_429
    assert AdaptadorDataJud.TETO_DA_ESPERA_NO_429 < 45, (
        "a espera precisa caber na janela que o cliente ainda aguarda")


def test_retry_after_ilegivel_cai_no_padrao_em_vez_de_quebrar(monkeypatch):
    """A norma admite data HTTP no cabecalho. Adivinhar uma data seria pior
    que usar o padrao."""
    import asyncio

    dormidas = []
    adaptador = _adaptador_com_respostas(
        monkeypatch,
        [_RespostaFalsa(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
         _RespostaFalsa(200)],
        dormidas)
    asyncio.run(adaptador._buscar(_tribunal_do_rio(), {"query": {}}))
    assert dormidas == [2.0]
