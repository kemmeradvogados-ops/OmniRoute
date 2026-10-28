"""O pacote da extensao.

Ate 28/10/2026 o `.mcpb` era gerado a mao e o manual mandava arrastar um
arquivo que um clone novo nao tem. O que este arquivo guarda e o que custou
descobrir: a lista de arquivos e fixa, o pacote e conferido depois de escrito,
e a versao de dentro bate com a do manifesto.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import empacotar as empacotador  # noqa: E402


def _conector_de_mentira(tmp_path, versao="9.9.9", ferramentas=3):
    conector = tmp_path / "conector"
    (conector / "server").mkdir(parents=True)
    (conector / "manifest.json").write_text(json.dumps({
        "manifest_version": "0.3", "name": "justica-mcp", "version": versao,
        "tools": [{"name": f"ferramenta_{i}"} for i in range(ferramentas)],
    }), encoding="utf-8")
    (conector / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (conector / "server" / "lancador.mjs").write_text("// lancador\n",
                                                      encoding="utf-8")
    (conector / "README.md").write_text("# conector\n", encoding="utf-8")
    return conector


def test_o_pacote_leva_exatamente_os_quatro_arquivos(tmp_path):
    alvo = empacotador.empacotar(_conector_de_mentira(tmp_path))
    with zipfile.ZipFile(alvo) as pacote:
        assert tuple(i.filename for i in pacote.infolist()) == (
            "manifest.json", "icon.png", "server/lancador.mjs", "README.md")


def test_sobra_na_pasta_nao_entra_no_pacote(tmp_path):
    """A lista e fixa, e nao uma varredura. Um pacote que cresce sozinho e um
    pacote que ninguem confere."""
    conector = _conector_de_mentira(tmp_path)
    (conector / "rascunho.txt").write_text("nao deve entrar", encoding="utf-8")
    (conector / "credenciais.env").write_text("SEGREDO=1", encoding="utf-8")
    alvo = empacotador.empacotar(conector)
    with zipfile.ZipFile(alvo) as pacote:
        dentro = [i.filename for i in pacote.infolist()]
    assert "rascunho.txt" not in dentro
    assert "credenciais.env" not in dentro


def test_o_pacote_anterior_nao_entra_dentro_do_novo(tmp_path):
    conector = _conector_de_mentira(tmp_path)
    empacotador.empacotar(conector)
    alvo = empacotador.empacotar(conector)
    with zipfile.ZipFile(alvo) as pacote:
        assert not any(i.filename.endswith(".mcpb")
                       for i in pacote.infolist())


def test_a_versao_de_dentro_e_a_do_manifesto(tmp_path):
    alvo = empacotador.empacotar(_conector_de_mentira(tmp_path, versao="1.2.3"))
    with zipfile.ZipFile(alvo) as pacote:
        assert json.loads(pacote.read("manifest.json"))["version"] == "1.2.3"


def test_arquivo_faltando_para_o_empacotamento(tmp_path):
    """Pacote incompleto so se denuncia na hora de instalar, que e tarde:
    quem instala e outra pessoa."""
    conector = _conector_de_mentira(tmp_path)
    (conector / "icon.png").unlink()
    with pytest.raises(FileNotFoundError) as erro:
        empacotador.empacotar(conector)
    assert "icon.png" in str(erro.value)


def test_o_pacote_de_verdade_bate_com_o_manifesto_de_verdade():
    """Contra os arquivos do projeto, e nao contra molde de teste."""
    conector = empacotador.pasta_do_conector()
    manifesto = json.loads(
        (conector / "manifest.json").read_text(encoding="utf-8"))
    alvo = empacotador.empacotar()
    with zipfile.ZipFile(alvo) as pacote:
        lido = json.loads(pacote.read("manifest.json"))
    assert lido["version"] == manifesto["version"]
    assert len(lido["tools"]) == len(manifesto["tools"])
