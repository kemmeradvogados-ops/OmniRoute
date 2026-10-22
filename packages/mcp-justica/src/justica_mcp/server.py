"""Servidor MCP `justica_mcp`. Transporte stdio, execucao local.

Local de proposito: o dado processual e a credencial da banca nao devem sair da
maquina do escritorio. A maquina precisa ter saida brasileira, porque as APIs
do Conselho Nacional de Justica bloqueiam acesso por pais de origem.
"""

from __future__ import annotations

import sys

from mcp.server.mcpserver import MCPServer

from .core.config import carregar_env
from .core.seguranca import verificar_somente_leitura
from .tools import registrar

mcp = MCPServer("justica_mcp")


def construir() -> MCPServer:
    carregar_env()
    # Aborta a inicializacao se alguma capacidade de escrita vazar para a versao 1.
    verificar_somente_leitura()
    registrar(mcp)
    return mcp


def main() -> None:
    try:
        construir().run(transport="stdio")
    except KeyboardInterrupt:
        # Um `Ctrl+C` num servidor parado esperando o protocolo NAO e defeito,
        # e ate 22/10/2026 ele parecia um: a biblioteca deixava o
        # KeyboardInterrupt subir e despejava sessenta linhas de pilha, com
        # `WouldBlock` e `CancelledError` no meio, em cima de quem so queria
        # encerrar. Quem conferiu a instalacao desse jeito leu aquilo como
        # instalacao quebrada, e nao estava.
        #
        # O silencio e que e o sinal certo: parado esperando a entrada padrao e
        # exatamente o que um servidor stdio faz quando ninguem falou com ele.
        print("\nServidor encerrado.", file=sys.stderr)


if __name__ == "__main__":
    main()
