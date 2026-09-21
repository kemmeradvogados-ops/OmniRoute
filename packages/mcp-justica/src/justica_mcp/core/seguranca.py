"""Fronteira de somente leitura da versao 1.

Esta fronteira e estrutural, nao uma instrucao no prompt. Instrucao em prompt
falha; uma barreira que impede o registro da ferramenta, nao.

Duas razoes, ambas com consequencia juridica concreta:

  1. Abrir o teor de intimacao eletronica dispara a ciencia e inicia o prazo
     (lei nº. 11.419/06, artigo 5º, §3º). Um agente que clica no lugar errado
     antecipa prazo alheio.
  2. Ato praticado com a credencial do advogado e atribuido pessoalmente ao
     titular, e a assinatura e pessoal e indelegavel.

`verificar_somente_leitura()` roda na inicializacao do servidor e ABORTA se
alguma capacidade de escrita tiver sido declarada disponivel por engano.
"""

from __future__ import annotations

from .capabilities import Capacidade, MATRIZ, Situacao

# Capacidades que alteram estado no tribunal ou consomem prazo.
CAPACIDADES_DE_ESCRITA: frozenset[Capacidade] = frozenset(
    {Capacidade.DAR_CIENCIA_INTIMACAO}
)


class FronteiraViolada(RuntimeError):
    pass


def verificar_somente_leitura() -> None:
    violacoes = [
        f"{adaptador}.{capacidade.value}"
        for adaptador, caps in MATRIZ.items()
        for capacidade, decl in caps.items()
        if capacidade in CAPACIDADES_DE_ESCRITA and decl.situacao is Situacao.DISPONIVEL
    ]
    if violacoes:
        raise FronteiraViolada(
            "Versao 1 e somente leitura, e a matriz de capacidades declara operacao "
            f"de escrita disponivel: {', '.join(violacoes)}. Habilitar escrita exige "
            "decisao expressa do operador, confirmacao humana por ato e revisao "
            "desta fronteira."
        )
