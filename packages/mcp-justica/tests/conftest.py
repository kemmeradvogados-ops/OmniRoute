import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def fonte_da_consulta() -> str:
    """O texto da consulta inteira, agora espalhada por cinco funcoes.

    Ate 24/10/2026 a consulta era uma funcao aninhada de 997 linhas, e dezenas
    de testes de guarda liam o texto dela para provar que uma decisao continua
    escrita no codigo. A separacao em uma funcao por portal nao mudou uma
    linha do corpo, mas espalhou esse texto.

    Em vez de cada teste escolher a funcao certa, o que os tornaria fragil a
    cada nova separacao, eles perguntam pela consulta INTEIRA. A guarda
    continua provando a mesma coisa: aquela decisao esta no caminho da
    consulta.
    """
    import inspect

    from justica_mcp import portal

    partes = (
        portal.consultar_processo,
        portal._consultar_esaj,
        portal._consultar_dcp,
        portal._consultar_pje,
        portal._consultar_eproc,
    )
    return "\n".join(inspect.getsource(parte) for parte in partes)


def fonte_do_portal(sistema: str) -> str:
    """O texto do caminho de UM portal, depois da separacao de 24/10/2026.

    Antes, para olhar so o Portal de Servicos, os testes recortavam o texto
    entre `identidade.sistema == "dcp"` e `identidade.sistema == "pje"`. Agora
    cada caminho e uma funcao, e perguntar por ela e mais direto e mais
    honesto que recortar por marcador de texto.
    """
    import inspect

    from justica_mcp import portal

    return inspect.getsource(getattr(portal, f"_consultar_{sistema}"))


@pytest.fixture(autouse=True)
def _acervo_isolado(tmp_path_factory, monkeypatch):
    """Nenhum teste escreve na pasta de copias de verdade.

    Em 25/10/2026 os testes da sondagem gravaram `sistemas.json` na pasta
    padrao da maquina, porque nao apontavam `JUSTICA_PASTA_COPIAS` para lugar
    nenhum. No contentor isso foi inofensivo; na maquina de um advogado da
    banca aquela variavel aponta para a pasta do Google Drive COMPARTILHADA,
    com as copias dos autos de todos os processos. Teste que escreve no acervo
    do escritorio e um acidente esperando a hora.

    O conserto e aqui e nao em cada teste: assim vale tambem para os testes
    que ainda nao foram escritos. Quem precisa de outra pasta continua
    sobrescrevendo a variavel com o proprio `monkeypatch`, que roda depois
    deste.
    """
    monkeypatch.setenv(
        "JUSTICA_PASTA_COPIAS",
        str(tmp_path_factory.mktemp("acervo-de-teste")),
    )
