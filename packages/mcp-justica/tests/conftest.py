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
