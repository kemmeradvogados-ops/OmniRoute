"""Ferramentas expostas ao agente. Todas somente leitura na versao 1."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Optional

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .adapters import AdaptadorDataJud, AdaptadorDJEN, CapacidadeIndisponivel
from .adapters.datajud import ChaveDataJudAusente
from .core.capabilities import matriz_serializavel
from .core.cnj import NumeroCNJInvalido, parse_numero
from .core.estado import Estado
from .core.resolver import resolver_sistema
from .core.resiliencia import PortalIndisponivel
from .core.schemas import Erro
from .core.tribunais import TribunalForaDoEscopo, identificar_tribunal

_estado = Estado()
_datajud = AdaptadorDataJud()
_djen = AdaptadorDJEN()


def _json(dados: Any) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2, default=str)


def _erro(mensagem: str, codigo: str, sugestao: Optional[str] = None) -> str:
    return _json(Erro(erro=mensagem, codigo=codigo, sugestao=sugestao).model_dump(exclude_none=True))


def _tratar(exc: Exception) -> str:
    """Erro acionavel: o agente precisa saber o proximo passo, nao so que falhou."""
    if isinstance(exc, NumeroCNJInvalido):
        return _erro(str(exc), "numero_invalido", "Confira a transcricao do numero junto ao advogado.")
    if isinstance(exc, TribunalForaDoEscopo):
        return _erro(str(exc), "tribunal_fora_do_escopo", "Consulta exige novo adaptador e credencial propria.")
    if isinstance(exc, CapacidadeIndisponivel):
        return _erro(str(exc), "capacidade_indisponivel",
                     "Nao tente outra ferramenta a esmo; informe a limitacao ao advogado.")
    if isinstance(exc, PortalIndisponivel):
        return _erro(str(exc), "portal_indisponivel", "Aguarde a janela indicada antes de repetir.")
    if isinstance(exc, ChaveDataJudAusente):
        return _erro(str(exc), "configuracao_ausente",
                     "Servidor sem chave do DataJud. Nao ha como consultar a base nacional ate configurar.")
    if isinstance(exc, PermissionError):
        return _erro(str(exc), "acesso_recusado", "Verifique chave de acesso e pais de origem do servidor.")
    if isinstance(exc, LookupError):
        return _erro(str(exc), "nao_encontrado",
                     "Ausencia na base nacional nao prova inexistencia do processo.")
    return _erro(f"Falha inesperada: {type(exc).__name__}: {exc}", "erro_interno",
                 "Consulte a auditoria local para o contexto da chamada.")


# ----------------------------- entradas -----------------------------

class NumeroInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    numero: str = Field(..., description="Numero no padrao NNNNNNN-DD.AAAA.J.TR.OOOO, com ou sem mascara.")
    solicitante: Optional[str] = Field(default=None, description="Quem pediu, para a auditoria.")


class AndamentosInput(NumeroInput):
    limite: int = Field(default=50, ge=1, le=500, description="Maximo de movimentos retornados.")


class PublicacoesOabInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    numero_oab: str = Field(..., description="Inscricao na Ordem, apenas digitos, por exemplo '218174'.")
    uf_oab: str = Field(..., description="Unidade federativa da inscricao, por exemplo 'RJ'.", min_length=2, max_length=2)
    dias: int = Field(default=7, ge=1, le=90, description="Janela retroativa em dias corridos.")
    sigla_tribunal: Optional[str] = Field(default=None, description="Filtro opcional, por exemplo 'TJRJ'.")
    pagina: int = Field(default=1, ge=1)
    solicitante: Optional[str] = None


# ----------------------------- registro -----------------------------

def registrar(mcp: Any) -> None:
    def somente_leitura(titulo: str) -> ToolAnnotations:
        """Anotacoes da versao 1: nenhuma ferramenta altera estado no tribunal."""
        return ToolAnnotations(
            title=titulo, read_only_hint=True, destructive_hint=False,
            idempotent_hint=True, open_world_hint=True,
        )

    @mcp.tool(name="justica_identificar_tribunal", annotations=somente_leitura("Identificar tribunal"))
    async def justica_identificar_tribunal(params: NumeroInput) -> str:
        """Identifica tribunal, segmento e ano a partir do numero, sem acessar a rede.

        Valida o digito verificador (ISO 7064 MOD 97-10). Nao decide o sistema:
        para isso use `justica_resolver_sistema`.
        """
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            return _json({
                "numero": numero.formatado,
                "tribunal": tribunal.codigo,
                "tribunal_nome": tribunal.nome,
                "segmento": numero.segmento_nome,
                "ano": numero.ano,
                "origem": numero.origem,
                "digito_verificador_valido": True,
                "sistemas_candidatos": [s.value for s in tribunal.sistemas_candidatos],
                "credenciais_da_banca": [s.value for s in tribunal.credencial_disponivel],
                "observacao": tribunal.observacao,
            })
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_resolver_sistema", annotations=somente_leitura("Resolver sistema do processo"))
    async def justica_resolver_sistema(params: NumeroInput) -> str:
        """Resolve em qual sistema o processo tramita (PJe, eproc, e-SAJ ou DCP).

        Nao e tabelado: no Tribunal de Justica do Estado do Rio de Janeiro
        convivem tres sistemas em migracao, e no de Sao Paulo, dois. A resposta
        traz `origem_da_resolucao` e `valido_ate`; quando vier
        'indeterminado', trate como desconhecido e informe o advogado, nao
        assuma o primeiro candidato.
        """
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            resolvido = await resolver_sistema(numero, _estado)
            _estado.registrar(acao="resolver_sistema", solicitante=params.solicitante,
                              tribunal=tribunal.codigo, sistema=resolvido.sistema,
                              numero=numero.formatado, resultado=resolvido.origem_da_resolucao)
            return _json(resolvido.model_dump())
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_consultar_processo", annotations=somente_leitura("Consultar processo"))
    async def justica_consultar_processo(params: NumeroInput) -> str:
        """Ficha do processo pela base nacional: classe, assuntos, orgao e ultimo andamento.

        A fonte NAO entrega partes, advogados nem documentos, por politica do
        Conselho Nacional de Justica. Esses campos voltam como `null` e sao
        listados em `indisponivel_nesta_fonte`: ausencia aqui nao significa que
        o processo nao os tenha.
        """
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            sistema = await resolver_sistema(numero, _estado)
            resposta = await _datajud.consultar_processo(numero, tribunal, sistema)
            _estado.registrar(acao="consultar_processo", solicitante=params.solicitante,
                              tribunal=tribunal.codigo, sistema=sistema.sistema,
                              numero=numero.formatado, resultado="ok")
            return _json(resposta.model_dump())
        except Exception as exc:
            _estado.registrar(acao="consultar_processo", solicitante=params.solicitante,
                              numero=params.numero, resultado="erro", detalhe=type(exc).__name__)
            return _tratar(exc)

    @mcp.tool(name="justica_listar_andamentos", annotations=somente_leitura("Listar andamentos"))
    async def justica_listar_andamentos(params: AndamentosInput) -> str:
        """Movimentos do processo, do mais recente para o mais antigo.

        A base nacional replica os tribunais e pode atrasar. Para contagem de
        prazo, confirme no portal.
        """
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            dados = await _datajud.listar_andamentos(numero, tribunal, limite=params.limite)
            _estado.registrar(acao="listar_andamentos", solicitante=params.solicitante,
                              tribunal=tribunal.codigo, numero=numero.formatado, resultado="ok")
            return _json(dados)
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_publicacoes_por_oab", annotations=somente_leitura("Publicacoes por inscricao na Ordem"))
    async def justica_publicacoes_por_oab(params: PublicacoesOabInput) -> str:
        """Publicacoes do Diario de Justica Eletronico Nacional por inscricao na Ordem.

        Espinha dorsal do monitoramento diario. Canal publico: ler aqui NAO
        dispara ciencia e NAO inicia prazo, ao contrario de abrir o expediente
        no painel do portal.

        Limite conhecido: nem toda comunicacao dirigida ao advogado transita
        pelo Diario. Ausencia aqui nao prova ausencia de intimacao.
        """
        try:
            fim = date.today()
            dados = await _djen.publicacoes_por_oab(
                params.numero_oab, params.uf_oab,
                data_inicio=fim - timedelta(days=params.dias), data_fim=fim,
                sigla_tribunal=params.sigla_tribunal, pagina=params.pagina,
            )
            _estado.registrar(acao="publicacoes_por_oab", solicitante=params.solicitante,
                              tribunal=params.sigla_tribunal, resultado=f"{dados['total']} item(ns)")
            return _json(dados)
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_publicacoes_por_processo", annotations=somente_leitura("Publicacoes do processo"))
    async def justica_publicacoes_por_processo(params: NumeroInput) -> str:
        """Publicacoes do Diario referentes a um processo. Nao dispara ciencia."""
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            dados = await _djen.publicacoes_por_processo(numero, tribunal)
            _estado.registrar(acao="publicacoes_por_processo", solicitante=params.solicitante,
                              tribunal=tribunal.codigo, numero=numero.formatado, resultado="ok")
            return _json(dados)
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_verificar_novos_andamentos", annotations=somente_leitura("Verificar novidades"))
    async def justica_verificar_novos_andamentos(params: NumeroInput) -> str:
        """Compara os andamentos atuais com a ultima consulta gravada e devolve so o que mudou.

        Na primeira execucao nao ha base de comparacao: grava a referencia e
        avisa. Nao trate a primeira resposta como "sem novidades".
        """
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            anterior = _estado.ultimo_snapshot(numero.apenas_digitos)
            atual = await _datajud.listar_andamentos(numero, tribunal, limite=500)
            movimentos = atual["movimentos"]
            registro = _estado.gravar_snapshot(numero.apenas_digitos, movimentos)

            if anterior is None:
                resultado = {
                    "numero": numero.formatado, "primeira_consulta": True,
                    "novos": [], "total_atual": len(movimentos),
                    "aviso": ("Referencia inicial gravada. Sem consulta anterior nao e "
                              "possivel afirmar que nao houve novidade."),
                }
            else:
                vistos = {(m.get("data_hora"), m.get("codigo"), m.get("nome"))
                          for m in anterior["conteudo"]}
                novos = [m for m in movimentos
                         if (m.get("data_hora"), m.get("codigo"), m.get("nome")) not in vistos]
                resultado = {
                    "numero": numero.formatado, "primeira_consulta": False,
                    "comparado_com": anterior["coletado_em"],
                    "houve_mudanca": registro["mudou"],
                    "quantidade_novos": len(novos), "novos": novos,
                    "total_atual": len(movimentos),
                }
            resultado["proveniencia"] = atual["proveniencia"]
            _estado.registrar(acao="verificar_novos_andamentos", solicitante=params.solicitante,
                              tribunal=tribunal.codigo, numero=numero.formatado,
                              resultado=f"{resultado.get('quantidade_novos', 0)} novo(s)")
            return _json(resultado)
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_capacidades", annotations=somente_leitura("Capacidades declaradas"))
    async def justica_capacidades() -> str:
        """Matriz do que cada adaptador sabe fazer, e o motivo do que nao faz.

        Consulte antes de prometer algo ao advogado. Se uma capacidade aparece
        como `nao_suportado` ou `nao_implementado`, diga isso em vez de tentar
        contornar por outro caminho.
        """
        return _json({
            "versao": "0.1.0 (Fase 1, somente leitura, sem credenciais)",
            "adaptadores": matriz_serializavel(),
            "datajud_configurado": _datajud.configurado,
        })

    @mcp.tool(name="justica_auditoria_recente", annotations=somente_leitura("Auditoria recente"))
    async def justica_auditoria_recente(limite: int = 50) -> str:
        """Ultimas chamadas registradas: data, acao, tribunal, sistema, processo e resultado."""
        return _json({"registros": _estado.auditoria_recente(limite=limite)})
