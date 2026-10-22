"""O pacote `.mcpb`: o conector que se instala arrastando para o Claude.

Nasceu em 22/10/2026, depois de uma instalacao inteira feita pelo caminho
errado. O guia mandava registrar o servidor escrevendo
`%APPDATA%\\Claude\\claude_desktop_config.json` na mao. Tudo foi conferido e
tudo passou: o arquivo gravado, o caminho existente, o servidor subindo e
respondendo ao protocolo. E nao apareceu conector nenhum.

A causa so ficou clara ao listar a pasta: `%APPDATA%\\Claude` continha APENAS
o arquivo que nos tinhamos acabado de criar, enquanto o aplicativo guardava os
dados dele em `%LOCALAPPDATA%\\Claude-Data`, mexido no mesmo dia. Editamos um
arquivo que aquela versao do Claude nao le. A documentacao atual descreve um
caminho so para conector local, e e este: um `.mcpb` arrastado para
Configuracoes > Extensoes.
"""

from __future__ import annotations

import json
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CONECTOR = RAIZ / "conector"


def _manifesto() -> dict:
    return json.loads((CONECTOR / "manifest.json").read_text(encoding="utf-8"))


def test_o_manifesto_existe_e_e_json_valido():
    assert (CONECTOR / "manifest.json").is_file()
    assert _manifesto()["name"] == "justica-mcp"


def test_o_manifesto_anuncia_exatamente_as_ferramentas_que_existem():
    """Nome a mais no manifesto e ferramenta anunciada que nao existe, e o
    modelo so descobre isso tentando usar."""
    from justica_mcp import tools

    import inspect

    fonte = inspect.getsource(tools.registrar)
    do_servidor = set()
    for pedaco in fonte.split('@mcp.tool(')[1:]:
        trecho = pedaco.split(")")[0]
        if 'name="' in trecho:
            do_servidor.add(trecho.split('name="')[1].split('"')[0])
        else:
            # Forma com `name=` na linha seguinte.
            do_servidor.add(pedaco.split('name="')[1].split('"')[0])
    do_manifesto = {f["name"] for f in _manifesto()["tools"]}
    assert do_manifesto == do_servidor, {
        "so no manifesto": do_manifesto - do_servidor,
        "so no servidor": do_servidor - do_manifesto,
    }


def test_o_lancador_e_node_porque_o_claude_traz_node():
    """`command: "python"` dependeria de o Python estar no caminho do sistema;
    o aplicativo do Claude traz o Node consigo."""
    servidor = _manifesto()["server"]
    assert servidor["type"] == "node"
    assert servidor["mcp_config"]["command"] == "node"
    assert "${__dirname}" in servidor["mcp_config"]["args"][0]


def test_o_pacote_nao_promete_trazer_as_dependencias():
    """A especificacao manda um servidor `python` trazer tudo dentro do
    pacote. As daqui incluem codigo compilado por plataforma e o Chromium do
    Playwright. Por isso o pacote APONTA para o ambiente virtual ja instalado,
    e pergunta onde ele esta."""
    config = _manifesto()["user_config"]
    assert config["python_do_ambiente"]["type"] == "file"
    assert config["python_do_ambiente"]["required"] is True
    assert config["pasta_do_projeto"]["type"] == "directory"
    assert config["pasta_do_projeto"]["required"] is True


def test_a_chave_do_datajud_e_opcional_e_protegida():
    """Opcional porque ela pode ja estar no .env; protegida porque e
    credencial, ainda que publica."""
    chave = _manifesto()["user_config"]["chave_do_datajud"]
    assert chave["sensitive"] is True
    assert chave.get("required", False) is False


def test_o_lancador_retira_variavel_vazia_do_ambiente():
    """Guarda de fonte, e ela protege um defeito real: o campo da chave e
    opcional, e um valor vazio vindo dele entraria no ambiente como "", que TEM
    precedencia sobre o .env. O efeito seria DESLIGAR uma chave que ja
    funcionava, por causa de um campo em branco."""
    fonte = (CONECTOR / "server" / "lancador.mjs").read_text(encoding="utf-8")
    sem_comentario = "\n".join(
        linha for linha in fonte.splitlines()
        if not linha.strip().startswith(("*", "/*", "//")))
    assert "delete ambiente[chave]" in sem_comentario
    assert "DATAJUD_API_KEY" in sem_comentario


def test_o_lancador_passa_a_entrada_e_a_saida_direto():
    """`stdio: "inherit"`. O lancador NAO fala o protocolo: se ele
    intermediasse, seria mais um lugar onde uma mensagem pode se perder."""
    fonte = (CONECTOR / "server" / "lancador.mjs").read_text(encoding="utf-8")
    assert '"inherit"' in fonte


def test_o_icone_e_um_png_de_512():
    import struct

    dados = (CONECTOR / "icon.png").read_bytes()
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", dados[16:24]) == (512, 512)


@pytest.mark.parametrize("campo", ["manifest_version", "name", "version",
                                   "description", "author", "server"])
def test_os_campos_exigidos_pela_especificacao_estao_presentes(campo):
    assert campo in _manifesto()
