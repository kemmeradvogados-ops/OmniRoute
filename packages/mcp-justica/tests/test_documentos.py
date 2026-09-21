"""Copia de documentos do processo.

O modulo busca os arquivos pelo ENDERECO, reaproveitando a sessao autenticada,
em vez de clicar nos links da tela. Clicar poderia abrir aba, disparar script
ou cair em elemento vizinho, e este projeto existe porque clique errado no
portal custa caro.
"""

from pathlib import Path

import pytest

from justica_mcp.core.guarda_navegacao import GuardaNavegacao, Modo, Permissao
from justica_mcp.documentos import (
    Copia, Resultado, baixar_documentos_dos_eventos, nome_de_arquivo,
    parece_comunicacao,
)

BASE = "https://eproc.exemplo/eproc/processo"


class _Resposta:
    def __init__(self, corpo=b"%PDF-1.4 conteudo", status=200, tipo="application/pdf"):
        self._corpo, self.status = corpo, status
        self.headers = {"content-type": tipo}

    @property
    def ok(self):
        return 200 <= self.status < 300

    def body(self):
        return self._corpo


class _Requisicao:
    def __init__(self, respostas=None, erro=None):
        self.respostas = respostas or {}
        self.erro = erro
        self.pedidos = []

    def get(self, endereco, timeout=None):
        self.pedidos.append(endereco)
        if self.erro:
            raise self.erro
        return self.respostas.get(endereco, _Resposta())


class _Contexto:
    def __init__(self, requisicao):
        self.request = requisicao


class _Pagina:
    def __init__(self, requisicao):
        self.url = BASE
        self.context = _Contexto(requisicao)


def _guarda():
    return GuardaNavegacao(
        modo=Modo.LEITURA,
        permissoes=[Permissao(r"^https://eproc\.exemplo", "documentos", "2026-09-21")],
        permitir_download=True,
    )


def _evento(numero, descricao, docs):
    return {"evento": numero, "descricao": descricao, "data_hora": "01/01/2026",
            "documentos": [{"rotulo": r, "endereco": e} for r, e in docs]}


EVENTOS = [
    _evento("68", "Juntada de petição", [("PET1", "/doc?id=1"), ("ANEXO1", "/doc?id=2")]),
    _evento("67", "Decisão", [("DEC1", "/doc?id=3")]),
    _evento("66", "Conclusos para decisão", []),
    _evento("65", "Intimação eletrônica expedida", [("INT1", "/doc?id=4")]),
    _evento("64", "Distribuição", [("INIC1", "/doc?id=5")]),
]


# ---------------- nome de arquivo ----------------

def test_nome_e_ordenavel_e_seguro():
    """Zeros a esquerda fazem a pasta ordenar na ordem dos eventos, e os
    caracteres proibidos pelo sistema de arquivos sao trocados."""
    assert nome_de_arquivo("68", "PET1", ".pdf") == "ev0068-PET1.pdf"
    assert nome_de_arquivo("7", "A/B:C", ".pdf") == "ev0007-A-B-C.pdf"


def test_nome_sem_acento_e_com_limite():
    assert nome_de_arquivo("1", "PETIÇÃO", ".pdf") == "ev0001-PETICAO.pdf"
    assert len(nome_de_arquivo("1", "x" * 200, ".pdf")) < 80


def test_rotulo_vazio_ainda_gera_nome():
    assert nome_de_arquivo("1", "", ".pdf") == "ev0001-documento.pdf"


# ---------------- copia ----------------

def test_copia_os_documentos_dos_eventos_mais_recentes(tmp_path):
    pedido = _Requisicao()
    r = baixar_documentos_dos_eventos(
        _Pagina(pedido), _guarda(), EVENTOS, tmp_path, quantos_eventos=2
    )
    assert len(r.gravadas) == 3, "dois documentos do evento 68 e um do 67"
    assert all(Path(c.arquivo).exists() for c in r.gravadas)
    assert len(pedido.pedidos) == 3


def test_nao_clica_em_nada_busca_pelo_endereco(tmp_path):
    """A pagina dublada nao oferece clique: se o modulo tentasse clicar,
    quebraria. Buscar pelo endereco e a garantia de que nao ha interacao."""
    pedido = _Requisicao()
    baixar_documentos_dos_eventos(
        _Pagina(pedido), _guarda(), EVENTOS[:1], tmp_path, quantos_eventos=1
    )
    assert pedido.pedidos == [
        "https://eproc.exemplo/doc?id=1", "https://eproc.exemplo/doc?id=2",
    ]


def test_conta_eventos_sem_documento(tmp_path):
    r = baixar_documentos_dos_eventos(
        _Pagina(_Requisicao()), _guarda(), EVENTOS, tmp_path, quantos_eventos=3
    )
    assert r.eventos_sem_documento == 1


def test_sinaliza_documento_vindo_de_comunicacao(tmp_path):
    """Nao bloqueia, porque documento de evento e parte dos autos, mas vai
    sinalizado para o advogado conferir o que foi copiado."""
    r = baixar_documentos_dos_eventos(
        _Pagina(_Requisicao()), _guarda(), EVENTOS, tmp_path, quantos_eventos=5
    )
    marcados = [c for c in r.gravadas if c.de_comunicacao]
    assert [c.evento for c in marcados] == ["65"]
    assert "comunicacao processual" in "\n".join(r.resumo())


def test_link_dependente_de_script_e_registrado_como_falha(tmp_path):
    eventos = [_evento("1", "Petição", [("X", "javascript:abrirDoc(1)")])]
    r = baixar_documentos_dos_eventos(
        _Pagina(_Requisicao()), _guarda(), eventos, tmp_path, quantos_eventos=1
    )
    assert r.gravadas == [] and "script" in r.falhas[0].erro


def test_resposta_de_erro_nao_grava_arquivo(tmp_path):
    pedido = _Requisicao(respostas={"https://eproc.exemplo/doc?id=3": _Resposta(status=403)})
    r = baixar_documentos_dos_eventos(
        _Pagina(pedido), _guarda(), EVENTOS[1:2], tmp_path, quantos_eventos=1
    )
    assert r.gravadas == [] and "403" in r.falhas[0].erro


def test_guarda_pode_barrar_um_documento(tmp_path):
    """A autorizacao de download nao dispensa a lista de permissao."""
    guarda = GuardaNavegacao(
        modo=Modo.LEITURA,
        permissoes=[Permissao(r"^https://outro\.site", "outra tela", "2026-09-21")],
        permitir_download=True,
    )
    r = baixar_documentos_dos_eventos(
        _Pagina(_Requisicao()), guarda, EVENTOS[:1], tmp_path, quantos_eventos=1
    )
    assert r.gravadas == [] and len(r.falhas) == 2


def test_sem_autorizacao_de_download_nada_e_copiado(tmp_path):
    guarda = _guarda()
    guarda.permitir_download = False
    r = baixar_documentos_dos_eventos(
        _Pagina(_Requisicao()), guarda, EVENTOS[:1], tmp_path, quantos_eventos=1
    )
    assert r.gravadas == []
    assert "nao autorizado" in r.falhas[0].erro


def test_extensao_vem_do_tipo_de_conteudo(tmp_path):
    pedido = _Requisicao(respostas={
        "https://eproc.exemplo/doc?id=3": _Resposta(b"<html>", tipo="text/html"),
    })
    r = baixar_documentos_dos_eventos(
        _Pagina(pedido), _guarda(), EVENTOS[1:2], tmp_path, quantos_eventos=1
    )
    assert r.gravadas[0].arquivo.endswith(".html")


@pytest.mark.parametrize("descricao,esperado", [
    ("Intimação eletrônica", True), ("Citação postal", True),
    ("Comunicação eletrônica recebida", True), ("Expediente expedido", True),
    ("Juntada de petição", False), ("Decisão", False), ("Sentença", False),
])
def test_deteccao_de_comunicacao(descricao, esperado):
    assert parece_comunicacao(descricao) is esperado
