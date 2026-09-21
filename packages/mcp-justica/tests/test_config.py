"""Leitura do `.env`. O README mandava criar o arquivo e nada o lia."""

import os
import tempfile
from pathlib import Path

from justica_mcp.core.config import carregar_env


def _env(conteudo: str) -> Path:
    caminho = Path(tempfile.mkdtemp()) / ".env"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_le_chave_do_arquivo(monkeypatch):
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    lidas = carregar_env(_env("DATAJUD_API_KEY=abc123\n"))
    assert lidas == ["DATAJUD_API_KEY"]
    assert os.environ["DATAJUD_API_KEY"] == "abc123"


def test_ignora_comentario_linha_vazia_e_chave_sem_valor(monkeypatch):
    monkeypatch.delenv("X_TESTE", raising=False)
    lidas = carregar_env(_env("# comentario\n\nVAZIA=\nX_TESTE=1\n"))
    assert lidas == ["X_TESTE"]


def test_remove_aspas(monkeypatch):
    monkeypatch.delenv("X_ASPAS", raising=False)
    carregar_env(_env('X_ASPAS="com aspas"\n'))
    assert os.environ["X_ASPAS"] == "com aspas"


def test_ambiente_explicito_tem_precedencia(monkeypatch):
    """Quem exporta a variavel na sessao manda mais que o arquivo."""
    monkeypatch.setenv("X_PREC", "do_ambiente")
    carregar_env(_env("X_PREC=do_arquivo\n"))
    assert os.environ["X_PREC"] == "do_ambiente"


def test_arquivo_ausente_nao_quebra():
    assert carregar_env(Path(tempfile.mkdtemp()) / "nao-existe.env") == []


def test_nao_devolve_valores_apenas_nomes(monkeypatch):
    """O retorno vai para o relatorio de diagnostico; nao pode vazar segredo."""
    monkeypatch.delenv("SEGREDO", raising=False)
    lidas = carregar_env(_env("SEGREDO=valor-sensivel\n"))
    assert lidas == ["SEGREDO"]
    assert "valor-sensivel" not in str(lidas)
