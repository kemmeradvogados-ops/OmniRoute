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


def test_tolera_marca_de_ordem_de_byte_do_powershell(monkeypatch):
    """`Out-File -Encoding utf8` no PowerShell grava BOM. Sem tratar, a
    primeira chave do arquivo ganharia um caractere invisivel no nome e
    jamais seria encontrada, com o diagnostico dizendo 'chave ausente'."""
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    caminho = Path(tempfile.mkdtemp()) / ".env"
    caminho.write_bytes(b"\xef\xbb\xbfDATAJUD_API_KEY=abc\n")
    assert carregar_env(caminho) == ["DATAJUD_API_KEY"]
    assert os.environ["DATAJUD_API_KEY"] == "abc"


def test_tolera_arquivo_gravado_em_ansi_pelo_bloco_de_notas(monkeypatch):
    """O Bloco de Notas do Windows 10 mais antigo salva em ANSI, e a pasta de
    copias do escritorio tem acento. Em cp1252 o "o" acentuado e o byte 0xF3,
    que nao e UTF-8 valido: sem tolerancia, o arquivo inteiro falharia na
    leitura e nenhuma outra chave seria carregada, com erro de codificacao no
    lugar de um diagnostico util."""
    monkeypatch.delenv("JUSTICA_PASTA_COPIAS", raising=False)
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    caminho = Path(tempfile.mkdtemp()) / ".env"
    caminho.write_bytes(
        "DATAJUD_API_KEY=abc\n"
        "JUSTICA_PASTA_COPIAS=G:\\Meu Drive\\4.Processos\\Cópias\n".encode("cp1252")
    )
    assert carregar_env(caminho) == ["DATAJUD_API_KEY", "JUSTICA_PASTA_COPIAS"]
    assert os.environ["JUSTICA_PASTA_COPIAS"] == "G:\\Meu Drive\\4.Processos\\Cópias"


def test_acento_em_utf8_continua_intacto(monkeypatch):
    """A tolerancia ao ANSI nao pode estragar o caso normal: UTF-8 e tentado
    primeiro, entao o acento tem de voltar identico."""
    monkeypatch.delenv("JUSTICA_PASTA_COPIAS", raising=False)
    caminho = Path(tempfile.mkdtemp()) / ".env"
    caminho.write_text(
        "JUSTICA_PASTA_COPIAS=G:\\Meu Drive\\4.Processos\\Cópias\n", encoding="utf-8"
    )
    assert carregar_env(caminho) == ["JUSTICA_PASTA_COPIAS"]
    assert os.environ["JUSTICA_PASTA_COPIAS"] == "G:\\Meu Drive\\4.Processos\\Cópias"
