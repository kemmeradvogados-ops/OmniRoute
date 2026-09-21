"""Matriz de capacidades declarada por adaptador.

Sem esta matriz o agente tenta baixar a integra por um adaptador que nao baixa,
recebe vazio e inventa uma explicacao. Com ela, o servidor responde antes de
gastar a chamada: "o DCP nao expoe documentos por esta via".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Capacidade(str, Enum):
    CONSULTAR_PROCESSO = "consultar_processo"
    LISTAR_ANDAMENTOS = "listar_andamentos"
    LISTAR_PUBLICACOES_POR_OAB = "listar_publicacoes_por_oab"
    LISTAR_PUBLICACOES_POR_PROCESSO = "listar_publicacoes_por_processo"
    BUSCAR_POR_PARTE = "buscar_por_parte"
    LISTAR_DOCUMENTOS = "listar_documentos"
    BAIXAR_DOCUMENTO = "baixar_documento"
    BAIXAR_INTEGRA = "baixar_integra"
    LISTAR_INTIMACOES_PENDENTES = "listar_intimacoes_pendentes"
    DAR_CIENCIA_INTIMACAO = "dar_ciencia_intimacao"


class Situacao(str, Enum):
    DISPONIVEL = "disponivel"
    NAO_SUPORTADO = "nao_suportado"        # a fonte nao expoe, por politica ou desenho
    NAO_IMPLEMENTADO = "nao_implementado"  # previsto em fase futura
    EXIGE_CREDENCIAL = "exige_credencial"


@dataclass(frozen=True)
class Declaracao:
    situacao: Situacao
    motivo: str


DISPONIVEL = Declaracao(Situacao.DISPONIVEL, "")


def _nao_suportado(motivo: str) -> Declaracao:
    return Declaracao(Situacao.NAO_SUPORTADO, motivo)


def _fase2(motivo: str = "Previsto para a Fase 2, que introduz acesso autenticado.") -> Declaracao:
    return Declaracao(Situacao.NAO_IMPLEMENTADO, motivo)


MATRIZ: dict[str, dict[Capacidade, Declaracao]] = {
    "datajud": {
        Capacidade.CONSULTAR_PROCESSO: DISPONIVEL,
        Capacidade.LISTAR_ANDAMENTOS: DISPONIVEL,
        Capacidade.BUSCAR_POR_PARTE: _nao_suportado(
            "A API publica do DataJud nao publica nomes de partes nem advogados, "
            "por politica do Conselho Nacional de Justica amparada na Portaria nº. 160/2020."
        ),
        Capacidade.LISTAR_DOCUMENTOS: _nao_suportado(
            "O DataJud expoe metadados e movimentos, nunca documentos ou inteiro teor."
        ),
        Capacidade.BAIXAR_DOCUMENTO: _nao_suportado("O DataJud nao expoe documentos."),
        Capacidade.BAIXAR_INTEGRA: _nao_suportado("O DataJud nao expoe documentos."),
        Capacidade.LISTAR_PUBLICACOES_POR_OAB: _nao_suportado(
            "Nao ha campo de inscricao na Ordem no DataJud. Use o adaptador 'djen'."
        ),
        Capacidade.LISTAR_INTIMACOES_PENDENTES: _nao_suportado(
            "Expediente pendente so existe no painel autenticado do portal."
        ),
        Capacidade.DAR_CIENCIA_INTIMACAO: _nao_suportado("Fonte somente leitura."),
    },
    "djen": {
        Capacidade.LISTAR_PUBLICACOES_POR_OAB: DISPONIVEL,
        Capacidade.LISTAR_PUBLICACOES_POR_PROCESSO: DISPONIVEL,
        Capacidade.CONSULTAR_PROCESSO: _nao_suportado(
            "O Diario entrega comunicacoes publicadas, nao a ficha do processo. Use 'datajud'."
        ),
        Capacidade.LISTAR_ANDAMENTOS: _nao_suportado(
            "O Diario nao traz a cadeia de movimentos. Use 'datajud'."
        ),
        Capacidade.BUSCAR_POR_PARTE: _nao_suportado(
            "A busca do Diario e por inscricao na Ordem, processo ou tribunal."
        ),
        Capacidade.BAIXAR_INTEGRA: _nao_suportado("O Diario nao da acesso aos autos."),
        Capacidade.LISTAR_INTIMACOES_PENDENTES: _nao_suportado(
            "Publicacao no Diario e canal distinto do expediente do portal. "
            "Ler aqui NAO dispara ciencia, e tambem nao lista pendencias do painel."
        ),
        Capacidade.DAR_CIENCIA_INTIMACAO: _nao_suportado("Fonte somente leitura."),
    },
    "eproc": {
        **{c: _fase2() for c in Capacidade},
        # Validado em campo na Justica Federal do Rio em 21 de setembro de 2026.
        Capacidade.CONSULTAR_PROCESSO: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "Consulta autenticada pelo navegador. Exige credencial no cofre e "
            "`JUSTICA_ACESSO_AUTENTICADO=1`. Cada uso consome uma tentativa de "
            "autenticacao no tribunal e leva dezenas de segundos.",
        ),
        Capacidade.LISTAR_ANDAMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "Eventos completos do processo, mais do que a base nacional publica.",
        ),
        Capacidade.LISTAR_DOCUMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "Os documentos de cada evento sao LISTADOS, com rotulo e endereco. "
            "Abrir e baixar continuam fora do escopo.",
        ),
        Capacidade.BAIXAR_DOCUMENTO: _nao_suportado(
            "Download permanece proibido na versao somente leitura, em qualquer modo."
        ),
        Capacidade.BAIXAR_INTEGRA: _nao_suportado(
            "O portal oferece 'Download Completo', mas baixar autos e ato de outra "
            "natureza e exige decisao expressa do operador."
        ),
        Capacidade.DAR_CIENCIA_INTIMACAO: _nao_suportado(
            "Abrir expediente dispara a ciencia e inicia o prazo."
        ),
    },
    "pje": {c: _fase2() for c in Capacidade},
    "dcp": {
        **{c: _fase2() for c in Capacidade},
        Capacidade.BAIXAR_INTEGRA: _nao_suportado(
            "Portal legado do Tribunal de Justica do Estado do Rio de Janeiro, "
            "em extincao pela migracao ao eproc. Nao ha previsao de adaptador de documentos."
        ),
    },
}


def consultar(adaptador: str, capacidade: Capacidade) -> Declaracao:
    return MATRIZ.get(adaptador, {}).get(
        capacidade,
        Declaracao(Situacao.NAO_IMPLEMENTADO, f"Adaptador {adaptador!r} nao declara {capacidade.value!r}."),
    )


def adaptadores_para(capacidade: Capacidade) -> list[str]:
    """Quem sabe fazer isso hoje. Usado para rotear e para explicar recusa."""
    return [
        nome
        for nome, decl in MATRIZ.items()
        if decl.get(capacidade, Declaracao(Situacao.NAO_IMPLEMENTADO, "")).situacao
        is Situacao.DISPONIVEL
    ]


def matriz_serializavel() -> dict[str, dict[str, dict[str, str]]]:
    return {
        adaptador: {
            cap.value: {"situacao": d.situacao.value, "motivo": d.motivo}
            for cap, d in caps.items()
        }
        for adaptador, caps in MATRIZ.items()
    }
