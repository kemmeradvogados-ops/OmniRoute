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


def test_tolera_marca_de_ordem_de_byte_no_meio_do_arquivo(monkeypatch):
    """`Add-Content -Encoding UTF8` do Windows PowerShell pode gravar a marca
    de ordem de byte a cada acrescimo, e nao so no inicio do arquivo. No meio
    o utf-8-sig nao a remove: a chave acrescentada ganharia um caractere
    invisivel no nome e jamais seria encontrada, com o arquivo parecendo
    perfeito na tela."""
    monkeypatch.delenv("JUSTICA_PASTA_COPIAS", raising=False)
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    caminho = Path(tempfile.mkdtemp()) / ".env"
    caminho.write_bytes(
        b"\xef\xbb\xbfDATAJUD_API_KEY=abc\n"
        b"\xef\xbb\xbfJUSTICA_PASTA_COPIAS=G:\\Copias\n"
    )
    assert carregar_env(caminho) == ["DATAJUD_API_KEY", "JUSTICA_PASTA_COPIAS"]
    assert os.environ["JUSTICA_PASTA_COPIAS"] == "G:\\Copias"


# --------------------------------------------------------------------------
# Caractere invisivel no nome da chave
#
# Em 22/09/2026 o `.env` do operador produziu a pior especie de defeito: a
# listagem mostrava "TJRJ / pje", identico ao que se espera, e a busca pelo
# mesmo portal dizia que ele nao estava configurado. O arquivo parecia certo
# na tela e nao havia como ver a diferenca.
# --------------------------------------------------------------------------

def test_marca_de_ordem_de_byte_no_meio_do_nome_da_chave(tmp_path):
    from justica_mcp.core.config import carregar_env

    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE﻿_URL=https://exemplo\n",
                       encoding="utf-8")
    lidas = carregar_env(arquivo)
    assert "JUSTICA_PORTAL_TJRJ_PJE_URL" in lidas


def test_espaco_de_largura_zero_no_nome_da_chave(tmp_path, monkeypatch):
    """Vem de copiar e colar de pagina de internet ou de documento."""
    import os

    from justica_mcp.core.config import carregar_env

    monkeypatch.delenv("JUSTICA_PORTAL_TJRJ_PJE_URL", raising=False)
    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE​_URL=https://exemplo\n",
                       encoding="utf-8")
    carregar_env(arquivo)
    assert os.environ.get("JUSTICA_PORTAL_TJRJ_PJE_URL") == "https://exemplo"


def test_espaco_sem_quebra_tambem_sai_do_nome(tmp_path):
    from justica_mcp.core.config import limpar_invisiveis

    assert limpar_invisiveis("JUSTICA _PORTAL") == "JUSTICA_PORTAL"


def test_nome_limpo_continua_intacto():
    """A limpeza nao pode comer caractere legitimo de nome de variavel."""
    from justica_mcp.core.config import limpar_invisiveis

    assert limpar_invisiveis("JUSTICA_PORTAL_TJRJ_PJE_URL") == "JUSTICA_PORTAL_TJRJ_PJE_URL"


def test_o_erro_mostra_o_que_o_programa_enxerga(monkeypatch):
    """Ver os dois lados lado a lado e o que transforma um misterio num erro
    de digitacao."""
    from justica_mcp.core.acesso import PortalNaoConfigurado

    monkeypatch.setenv("JUSTICA_PORTAL_TJRJ_PJE_URL", "https://exemplo")
    texto = str(PortalNaoConfigurado("TJRJ", "pjee"))
    assert "TJRJ / pje" in texto
    assert "invisivel" in texto


def test_o_erro_sem_portal_nenhum_aponta_para_o_arquivo(monkeypatch):
    import os

    from justica_mcp.core.acesso import PortalNaoConfigurado

    for chave in [k for k in os.environ if k.startswith("JUSTICA_PORTAL_")]:
        monkeypatch.delenv(chave, raising=False)
    texto = str(PortalNaoConfigurado("TJRJ", "pje"))
    assert "nao enxerga portal nenhum" in texto


# --------------------------------------------------------------------------
# Saber ONDE o programa procura, e o que ha la
# --------------------------------------------------------------------------

def test_arquivo_em_utf16_e_dito_pelo_nome(tmp_path):
    """O latin-1 decodifica qualquer byte sem reclamar, entao um arquivo em
    UTF-16 passaria por lido e viraria chaves cheias de caractere nulo, sem
    nada na tela explicando por que o programa nao acha configuracao."""
    from justica_mcp.core.config import codificacao_do_env

    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE_URL=https://exemplo\n", encoding="utf-16")
    assert "UTF-16" in codificacao_do_env(arquivo)


def test_arquivo_em_utf8_e_reconhecido(tmp_path):
    from justica_mcp.core.config import codificacao_do_env

    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE_URL=https://exemplo\n", encoding="utf-8")
    assert codificacao_do_env(arquivo) == "utf-8-sig"


def test_arquivo_do_bloco_de_notas_antigo_e_reconhecido(tmp_path):
    """Acento em caminho do Drive gravado em ANSI."""
    from justica_mcp.core.config import codificacao_do_env

    arquivo = tmp_path / ".env"
    arquivo.write_bytes("JUSTICA_PASTA_COPIAS=G:\\Meu Drive\\Cópias\n".encode("cp1252"))
    assert codificacao_do_env(arquivo) in ("cp1252", "latin-1")


def test_arquivo_inexistente_nao_explode(tmp_path):
    from justica_mcp.core.config import codificacao_do_env

    assert "nao deu para abrir" in codificacao_do_env(tmp_path / "nao-existe")


# --------------------------------------------------------------------------
# Copia de seguranca da configuracao
#
# Em 22/09/2026 o `.env` do escritorio amanheceu com zero bytes: uma edicao o
# esvaziou. O programa continuou funcionando e simplesmente parou de enxergar
# portal nenhum, e reconstruir os enderecos exigiu garimpar relatorios
# antigos. Configuracao nao e segredo, e perde-la assim e estrago barato
# demais para nao ter rede.
# --------------------------------------------------------------------------

def test_ler_a_configuracao_deixa_uma_copia(tmp_path, monkeypatch):
    from justica_mcp.core.config import carregar_env, pasta_das_copias_do_env

    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path / "estado"))
    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE_URL=https://exemplo\n", encoding="utf-8")
    carregar_env(arquivo)

    copias = list(pasta_das_copias_do_env().glob("env-*.txt"))
    assert len(copias) == 1
    assert "JUSTICA_PORTAL_TJRJ_PJE_URL" in copias[0].read_text(encoding="utf-8")


def test_arquivo_vazio_nao_apaga_a_copia_boa(tmp_path, monkeypatch):
    """E o caso exato do estrago: se a copia fosse feita do arquivo vazio, ela
    apagaria a unica chance de recuperar a configuracao."""
    from justica_mcp.core.config import carregar_env, pasta_das_copias_do_env

    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path / "estado"))
    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE_URL=https://exemplo\n", encoding="utf-8")
    carregar_env(arquivo)

    arquivo.write_text("", encoding="utf-8")
    carregar_env(arquivo)

    copias = list(pasta_das_copias_do_env().glob("env-*.txt"))
    assert len(copias) == 1
    assert "JUSTICA_PORTAL_TJRJ_PJE_URL" in copias[0].read_text(encoding="utf-8")


def test_a_copia_do_dia_nao_e_reescrita_a_cada_execucao(tmp_path, monkeypatch):
    """Reescrever a cada execucao faria uma edicao ruim sobrescrever a copia
    boa em segundos."""
    from justica_mcp.core.config import carregar_env, pasta_das_copias_do_env

    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path / "estado"))
    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE_URL=https://primeiro\n", encoding="utf-8")
    carregar_env(arquivo)

    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE_URL=https://segundo\n", encoding="utf-8")
    carregar_env(arquivo)

    copia = next(pasta_das_copias_do_env().glob("env-*.txt"))
    assert "primeiro" in copia.read_text(encoding="utf-8")


def test_so_as_ultimas_copias_ficam(tmp_path, monkeypatch):
    from justica_mcp.core.config import (
        COPIAS_DO_ENV_MANTIDAS, carregar_env, pasta_das_copias_do_env,
    )

    monkeypatch.setenv("JUSTICA_MCP_HOME", str(tmp_path / "estado"))
    pasta = pasta_das_copias_do_env()
    for dia in range(1, 20):
        (pasta / f"env-2026090{dia:02d}.txt").write_text("velho", encoding="utf-8")

    arquivo = tmp_path / ".env"
    arquivo.write_text("JUSTICA_PORTAL_TJRJ_PJE_URL=https://exemplo\n", encoding="utf-8")
    carregar_env(arquivo)

    assert len(list(pasta.glob("env-*.txt"))) == COPIAS_DO_ENV_MANTIDAS
