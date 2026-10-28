"""Gera o `conector/justica-mcp.mcpb`, que e o que se arrasta para o Claude.

POR QUE ISTO EXISTE COMO SCRIPT, e nao como receita no manual.

O `.mcpb` nao e rastreado pelo git (`.gitignore`: `conector/*.mcpb`), e esta
certo que nao seja: e artefato de construcao, e versiona-lo encheria o
historico de binario que ninguem le. So que ate 28/10/2026 o manual da equipe
mandava arrastar esse arquivo da pasta `conector`, e quem clonasse o
repositorio nao o teria. A instrucao apontava para um arquivo inexistente.

Pior: o arquivo que existia na maquina de quem ja o tinha podia estar velho.
Em 28/10/2026 o que havia em disco era de dois dias antes, atras de cinco
commits que mexeram no manifesto ou no lancador, inclusive o que acrescentou
a vigesima ferramenta. Nada avisava.

Como rodar, de dentro da pasta `packages/mcp-justica`:

    .venv\\Scripts\\python.exe scripts\\empacotar.py      (Windows)
    .venv/bin/python scripts/empacotar.py                (macOS e Linux)

Nao instala nada e nao toca em rede. So le quatro arquivos e escreve um.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import zipfile

# A LISTA E FIXA, e nao uma varredura da pasta.
#
# Varredura entra com o que estiver la, e o que estiver la inclui o proprio
# `.mcpb` da vez anterior, arquivo de rascunho e o que mais alguem tenha
# deixado. Um pacote que cresce sozinho e um pacote que ninguem confere.
PARTES = ("manifest.json", "icon.png", "server/lancador.mjs", "README.md")


def pasta_do_conector() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "conector"


def empacotar(conector: pathlib.Path | None = None) -> pathlib.Path:
    """Escreve o pacote e devolve o caminho dele. Levanta se algo faltar."""
    conector = conector or pasta_do_conector()
    faltando = [n for n in PARTES if not (conector / n).is_file()]
    if faltando:
        raise FileNotFoundError(
            "faltam arquivos do conector: " + ", ".join(faltando))

    manifesto = json.loads(
        (conector / "manifest.json").read_text(encoding="utf-8"))
    alvo = conector / "justica-mcp.mcpb"
    if alvo.exists():
        alvo.unlink()
    with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as pacote:
        for nome in PARTES:
            pacote.write(conector / nome, nome)

    # CONFERIR O QUE SAIU, e nao so o que entrou. Um pacote corrompido so se
    # denuncia na hora de instalar, que e tarde: quem instala e outra pessoa.
    with zipfile.ZipFile(alvo) as pacote:
        if pacote.testzip() is not None:
            raise OSError(f"o pacote saiu corrompido: {alvo}")
        dentro = tuple(item.filename for item in pacote.infolist())
        if dentro != PARTES:
            raise OSError(f"o pacote saiu com outro conteudo: {dentro}")
        lido = json.loads(pacote.read("manifest.json"))
    if lido.get("version") != manifesto.get("version"):
        raise OSError("a versao dentro do pacote nao bate com a do manifesto")
    return alvo


def main() -> int:
    try:
        alvo = empacotar()
    except (FileNotFoundError, OSError, ValueError) as erro:
        print(f"Nao deu para empacotar: {erro}", file=sys.stderr)
        return 1

    dados = alvo.read_bytes()
    manifesto = json.loads(
        (alvo.parent / "manifest.json").read_text(encoding="utf-8"))
    print(f"\nPacote gerado: {alvo}")
    print(f"  versao: {manifesto.get('version')}")
    print(f"  ferramentas declaradas: {len(manifesto.get('tools') or [])}")
    print(f"  tamanho: {len(dados)} bytes")
    print(f"  sha256: {hashlib.sha256(dados).hexdigest()}")
    print("\nO codigo Python NAO vai dentro dele: o manifesto aponta para a")
    print("sua pasta do projeto e para o Python do ambiente virtual, entao o")
    print("que a extensao roda e o codigo que estiver em disco. Reempacotar so")
    print("e preciso quando o manifesto ou o lancador mudam.")
    print("\nPara instalar: Configuracoes > Extensoes, e arraste este arquivo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
