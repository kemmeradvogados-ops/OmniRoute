"""Servidor MCP `justica_mcp`. Transporte stdio, execucao local.

Local de proposito: o dado processual e a credencial da banca nao devem sair da
maquina do escritorio. A maquina precisa ter saida brasileira, porque as APIs
do Conselho Nacional de Justica bloqueiam acesso por pais de origem.
"""

from __future__ import annotations

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
    construir().run(transport="stdio")


if __name__ == "__main__":
    main()
