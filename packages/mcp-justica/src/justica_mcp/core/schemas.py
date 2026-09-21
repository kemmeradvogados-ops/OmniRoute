"""Contrato de resposta com proveniencia obrigatoria.

Toda resposta do servidor carrega COMO o dado foi obtido, nao apenas o dado.
Sem isso o agente trata numero do DataJud (que atrasa) e leitura de portal
autenticado (ao vivo) como se tivessem o mesmo peso, e apresenta um ao
advogado com a confianca do outro.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Metodo(str, Enum):
    """Como o dado chegou. Ordem de preferencia do projeto."""

    API_OFICIAL = "api"          # DataJud, Comunica/DJEN, MNI
    CONSULTA_PUBLICA = "publica"  # pagina publica sem autenticacao
    NAVEGADOR = "navegador"       # automacao autenticada, ultimo recurso
    CACHE = "cache"               # resposta servida de estado local


class Confianca(str, Enum):
    ALTA = "alta"      # fonte oficial estruturada, coletada agora
    MEDIA = "media"    # fonte publica, heuristica ou cache dentro da validade
    BAIXA = "baixa"    # inferencia, cache vencido ou extracao de tela


class Proveniencia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fonte: str = Field(..., description="Identificador do adaptador, por exemplo 'datajud' ou 'djen'.")
    metodo: Metodo
    confianca: Confianca
    coletado_em: str = Field(default_factory=agora_iso)
    endpoint: Optional[str] = Field(default=None, description="Endereco efetivamente consultado.")
    observacao: Optional[str] = Field(
        default=None, description="Limitacao conhecida da fonte que o agente precisa considerar."
    )


class SistemaResolvido(BaseModel):
    """Resultado de `resolver_sistema`, com validade explicita.

    `resolvido_em` e `valido_ate` existem para o cache envelhecer em voz alta:
    a migracao move processos de sistema, e um cache mudo levaria o agente ao
    adaptador errado sem qualquer sinal.
    """

    model_config = ConfigDict(extra="forbid")

    sistema: str
    resolvido_em: str = Field(default_factory=agora_iso)
    valido_ate: Optional[str] = None
    origem_da_resolucao: str = Field(
        ..., description="Como se chegou ao sistema: 'sondagem', 'cache', 'regra_migracao' ou 'indeterminado'."
    )
    candidatos: list[str] = Field(
        default_factory=list, description="Ordem de sondagem restante, quando indeterminado."
    )
    confianca: Confianca = Confianca.MEDIA
    motivo: Optional[str] = None


class RespostaProcesso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero: str
    tribunal: str
    tribunal_nome: str
    sistema_resolvido: SistemaResolvido
    classe: Optional[str] = None
    assuntos: list[str] = Field(default_factory=list)
    orgao_julgador: Optional[str] = None
    grau: Optional[str] = None
    data_ajuizamento: Optional[str] = None
    nivel_sigilo: Optional[int] = None
    ultimo_andamento: Optional[dict[str, Any]] = None
    total_movimentos: int = 0
    # Campos que a fonte publica nao entrega. Declarados como indisponiveis em
    # vez de omitidos, para o agente nao concluir que o processo nao os tem.
    partes: Optional[list[dict[str, Any]]] = Field(
        default=None, description="None significa INDISPONIVEL nesta fonte, nao inexistente."
    )
    advogados: Optional[list[dict[str, Any]]] = None
    documentos: Optional[list[dict[str, Any]]] = None
    indisponivel_nesta_fonte: list[str] = Field(default_factory=list)
    proveniencia: Proveniencia


class Erro(BaseModel):
    """Erro acionavel: diz o que houve e qual o proximo passo possivel."""

    model_config = ConfigDict(extra="forbid")

    erro: str
    codigo: str
    sugestao: Optional[str] = None
    proveniencia: Optional[Proveniencia] = None
