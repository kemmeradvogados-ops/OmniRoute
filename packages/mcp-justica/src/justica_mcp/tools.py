"""Ferramentas expostas ao agente. Todas somente leitura na versao 1."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Optional

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .adapters import AdaptadorDataJud, AdaptadorDJEN, CapacidadeIndisponivel
from .adapters.datajud import ChaveDataJudAusente
from .core.capabilities import matriz_serializavel
from .core.acesso import PortalNaoConfigurado, autenticado_habilitado, portais_configurados
from .core.cofre import Cofre, CofreIndisponivel
from .core.limite_tentativas import LimiteTentativas, TetoDeTentativasAtingido
from .core.cnj import NumeroCNJInvalido, parse_numero
from .core.estado import Estado, detalhe_do_erro
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


class LerPecaInput(NumeroInput):
    peca: int = Field(..., ge=1, description=(
        "Pagina em que a peca COMECA, que e o numero que aparece ao lado do "
        "nome do documento no indice do Visualizador e que esta no nome do "
        "arquivo gravado."))
    de: int = Field(default=1, ge=1, description=(
        "Primeira folha a ler, contada dentro da propria peca."))
    ate: Optional[int] = Field(default=None, ge=1, description=(
        "Ultima folha a ler, dentro da peca. Em branco le ate o fim ou ate o "
        "teto de caracteres."))
    onde: str = Field(
        default="acervo",
        description=("'acervo' (padrao) para o que foi guardado na pasta da "
                     "banca; 'leitura' para o que foi lido sem guardar, que "
                     "fica so nesta maquina."),
    )


class PublicacoesOabInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    numero_oab: str = Field(..., description="Inscricao na Ordem, apenas digitos, por exemplo '218174'.")
    uf_oab: str = Field(..., description="Unidade federativa da inscricao, por exemplo 'RJ'.", min_length=2, max_length=2)
    dias: int = Field(default=7, ge=1, le=90, description="Janela retroativa em dias corridos.")
    sigla_tribunal: Optional[str] = Field(default=None, description="Filtro opcional, por exemplo 'TJRJ'.")
    pagina: int = Field(default=1, ge=1)
    solicitante: Optional[str] = None


# As duas pastas em que um processo pode estar. O acervo e o do escritorio, no
# Google Drive, indexado e compartilhado. As leituras sao locais, de quem leu,
# nao indexadas, e podem ser apagadas sem perder nada.
ONDE_ACERVO = "acervo"
ONDE_LEITURA = "leitura"
CAMPO_ONDE = Field(
    default=ONDE_ACERVO,
    description=("'acervo' (padrao) para o que foi guardado na pasta da banca; "
                 "'leitura' para o que foi lido sem guardar, que fica so nesta "
                 "maquina."),
)


@contextmanager
def _na_pasta(onde: str):
    """Aponta a raiz das copias para o acervo ou para as leituras.

    A raiz sai de UMA variavel de ambiente, lida a cada chamada, entao trocar
    a variavel pelo tempo da leitura redireciona tudo sem tocar em caminho
    nenhum. Nao ha `await` dentro do bloco, de proposito: a variavel e do
    processo inteiro, e uma pausa aqui deixaria outra chamada enxergar a pasta
    trocada.
    """
    import os

    from .core.acervo import VARIAVEL_PASTA, pasta_de_leituras

    if onde != ONDE_LEITURA:
        yield
        return
    antes = os.environ.get(VARIAVEL_PASTA)
    os.environ[VARIAVEL_PASTA] = str(pasta_de_leituras())
    try:
        yield
    finally:
        if antes is None:
            os.environ.pop(VARIAVEL_PASTA, None)
        else:
            os.environ[VARIAVEL_PASTA] = antes


CAMPO_SISTEMA = Field(
    default=None,
    description=("Qual sistema do tribunal: 'pje', 'eproc', 'dcp' ou 'esaj'. "
                 "Deixe em branco para o programa descobrir. Diga quando ele "
                 "responder que nao sabe: o Tribunal de Justica do Rio de "
                 "Janeiro esta em migracao e tem tres sistemas ativos, e o "
                 "advogado sabe em qual o processo dele corre."),
)


def _sistema_pedido_ou_resolvido(numero, pedido, resolucao):
    """O sistema que o advogado disse, ou o que o programa descobriu.

    O resolvedor responde `indeterminado` quando o tribunal tem mais de um
    sistema ativo e nao ha regra que decida, o que e honesto e e o caso do
    Tribunal de Justica do Rio de Janeiro. Ate 25/10/2026 nao havia como
    contornar isso: a ferramenta recusava o pedido com uma mensagem sobre
    portal nao configurado, que apontava para o lugar errado.
    """
    escolhido = (pedido or "").strip().lower()
    if escolhido:
        return escolhido, None
    if resolucao.sistema and resolucao.sistema != "indeterminado":
        return resolucao.sistema, None
    return None, (resolucao.motivo or "")


class PecasInput(NumeroInput):
    onde: str = CAMPO_ONDE


class ConsultaAutenticadaInput(NumeroInput):
    sistema: Optional[str] = CAMPO_SISTEMA


class SondarSistemasInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    numeros: list = Field(
        ...,
        description=("Os processos a sondar, no padrao da numeracao unica. "
                     "TODOS do mesmo tribunal. Mande a lista inteira de uma "
                     "vez: a varredura custa uma autenticacao por SISTEMA e "
                     "nenhuma por processo, entao dez processos custam o "
                     "mesmo que dois, e pedir um de cada vez multiplica o "
                     "custo por dez."),
    )
    conferir_segundo_grau: bool = Field(
        default=False,
        description=("Nao parar no primeiro sistema que reconhecer o "
                     "processo. Serve para processo com RECURSO, em que o "
                     "primeiro e o segundo grau podem estar em sistemas "
                     "diferentes. Custa uma autenticacao por sistema, sempre. "
                     "Pergunte ao advogado se ha recurso antes de marcar."),
    )
    solicitante: Optional[str] = Field(
        default=None, description="Quem pediu, para a auditoria.")


class BaixarAutosInput(NumeroInput):
    guardar: bool = Field(
        default=True,
        description=("Verdadeiro (padrao) guarda os autos no acervo da banca, "
                     "no Google Drive, indexado e disponivel para a equipe "
                     "inteira ler de graca depois. Falso le sem guardar: o "
                     "arquivo fica numa pasta local, nao e indexado e pode ser "
                     "apagado. Guardar e o certo para processo que o "
                     "escritorio vai trabalhar; nao guardar serve para o que se "
                     "consulta uma vez."),
    )
    documentos: str = Field(
        default="integra",
        description=("'integra' (padrao) para os autos num arquivo so; 'auto' "
                     "para um download por documento; 'um-a-um' para processo "
                     "grande do Portal de Servicos do Rio de Janeiro."),
    )
    aceito_o_termo: bool = Field(
        default=False,
        description=("Aceita o aviso de responsabilidade que o PJe levanta ao "
                     "abrir os autos (resolucao nº. 121 do Conselho Nacional "
                     "de Justica). O aceite e ato do advogado: so marque "
                     "quando ele disser isso em palavras."),
    )
    segundos_download: Optional[int] = Field(
        default=None, ge=60, le=7200,
        description="Quanto esperar pelo ARQUIVO. Minimo e padrao do programa: 300.",
    )
    sistema: Optional[str] = CAMPO_SISTEMA
    tambem: list = Field(
        default_factory=list,
        max_length=20,
        description=("Outros processos DO MESMO PORTAL para correr na mesma "
                     "sessao. Todos juntos custam UMA autenticacao, em vez de "
                     "uma por processo. Processo de portal diferente nao entra "
                     "aqui: ele exige outra sessao."),
    )


# ----------------------------- registro -----------------------------

# Sistemas que a ferramenta autenticada sabe percorrer. O eproc entra pela
# busca rapida; o DCP do Rio de Janeiro entra pela tela de selecao, escolhe o
# tipo de usuario e vai pelo menu. Os dois param na tela do processo: nenhum
# abre documento, nenhum baixa nada.
SISTEMAS_AUTENTICADOS = ("dcp", "eproc")


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
            documento = None
            # A nota diz QUAL dos casos aconteceu. Sem ela, um 'indeterminado'
            # nao distingue "a base nacional nao sabe" de "a base nacional nem
            # foi perguntada", e a diferenca manda o advogado gastar tentativa
            # autenticada para descobrir o que era de graca (25/10/2026, cinco
            # processos indeterminados sem causa declarada).
            nota = None
            if not _datajud.configurado:
                nota = ("nao foi consultada: a chave de acesso a base nacional "
                        "nao esta configurada no .env")
            else:
                try:
                    documento = await _datajud.buscar_documento(numero, tribunal)
                    if documento is None:
                        nota = "consultada, e ela nao tem ficha deste processo"
                except Exception as exc:
                    # A base nacional e um reforco aqui, nao um requisito: sem
                    # ela o resolvedor cai na pista de migracao normalmente.
                    documento = None
                    nota = (f"a consulta falhou ({type(exc).__name__}). Confira "
                            "a chave de acesso e a rede")
            resolvido = await resolver_sistema(
                numero, _estado, documento_datajud=documento,
                nota_da_base_nacional=nota,
            )
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
            # Uma consulta so: o mesmo documento serve para montar a ficha e
            # para resolver o sistema pela declaracao da propria base.
            documento = await _datajud.buscar_documento(numero, tribunal)
            sistema = await resolver_sistema(numero, _estado, documento_datajud=documento)
            resposta = _datajud.montar_resposta(numero, tribunal, sistema, documento)
            _estado.registrar(acao="consultar_processo", solicitante=params.solicitante,
                              tribunal=tribunal.codigo, sistema=sistema.sistema,
                              numero=numero.formatado, resultado="ok")
            return _json(resposta.model_dump())
        except Exception as exc:
            _estado.registrar(acao="consultar_processo", solicitante=params.solicitante,
                              numero=params.numero, resultado="erro", detalhe=detalhe_do_erro(exc))
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
            "versao": "0.1.0 (somente leitura; acesso autenticado disponivel para dcp e eproc)",
            "adaptadores": matriz_serializavel(),
            "datajud_configurado": _datajud.configurado,
        })

    @mcp.tool(name="justica_credenciais_situacao", annotations=somente_leitura("Situacao das credenciais"))
    async def justica_credenciais_situacao() -> str:
        """Diz para quais tribunais e sistemas ha credencial guardada no cofre.

        Devolve apenas PRESENCA, jamais senha, semente ou codigo de segundo
        fator: credencial nunca entra no contexto do modelo. Quem grava e o
        advogado, pelo comando `justica-credenciais` no terminal da propria
        maquina.

        Consulte antes de prometer acesso autenticado. Se o par aparecer como
        incompleto, diga isso ao advogado em vez de tentar o acesso.
        """
        from .credenciais import _pares_esperados

        try:
            cofre = Cofre()
            if not cofre.disponivel():
                raise CofreIndisponivel(RuntimeError("sonda negativa"))
            return _json({
                "fase": "2 (acesso autenticado) ainda em construcao",
                "cofre": "Gerenciador de Credenciais do sistema operacional",
                "pares": [cofre.situacao(i) for i in _pares_esperados()],
                "observacao": (
                    "Somente presenca. Nenhum valor de credencial e exposto por "
                    "esta ou por qualquer outra ferramenta."
                ),
            })
        except CofreIndisponivel as exc:
            return _erro(str(exc), "cofre_indisponivel",
                         "O advogado precisa verificar o Gerenciador de Credenciais.")
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(
        name="justica_consultar_processo_autenticado",
        annotations=ToolAnnotations(
            title="Consultar processo no portal autenticado",
            read_only_hint=True,
            destructive_hint=False,
            # Nao idempotente: cada chamada consome uma tentativa de
            # autenticacao no tribunal, e tentativas seguidas bloqueiam a conta.
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )
    async def justica_consultar_processo_autenticado(
            params: ConsultaAutenticadaInput) -> str:
        """Consulta o processo no portal do tribunal, com a credencial do advogado.

        Traz o que a base nacional NAO tem. Somente leitura: nao abre
        documento, nao baixa nada, nao toca em expediente de intimacao.

        O que vem depende do sistema, e a diferenca importa:

        - eproc: partes, eventos completos e a lista de documentos de cada
          evento, lidos por seletor conferido na tela real.
        - dcp (Portal de Servicos do Rio de Janeiro): capa e movimentacoes
          lidas pela ESTRUTURA da pagina, nao por seletor conferido. O
          resultado traz `leitura.confirmada_em_tela_real: false` e
          `proveniencia.confianca: "nao conferida"`. Nao apresente esses dados
          como certos: diga ao advogado que a leitura ainda nao foi conferida
          contra a tela.

        CUSTO REAL POR CHAMADA: cada uso autentica de verdade no tribunal, o
        que leva dezenas de segundos e consome uma tentativa. Tentativas
        seguidas bloqueiam o acesso do advogado, entao ha um teto por hora e a
        ferramenta recusa quando ele e atingido. **Nao repita a chamada diante
        de erro**: relate ao advogado e espere instrucao.

        Use `justica_consultar_processo` (base nacional) quando bastarem classe,
        orgao e movimentos: e instantaneo, gratuito e sem risco.
        """
        import asyncio

        from .portal import consultar_processo_estruturado

        if not autenticado_habilitado():
            return _erro(
                "Acesso autenticado desligado neste servidor.", "acesso_desligado",
                "Ligar permite disparar autenticacao real no tribunal com a credencial "
                "do advogado, e e decisao do operador. Informe isso a ele em vez de "
                "tentar outro caminho.",
            )
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            LimiteTentativas.do_ambiente(_estado).exigir_folga()

            sistema, duvida = _sistema_pedido_ou_resolvido(
                numero, params.sistema, await resolver_sistema(numero, _estado))
            if sistema is None:
                return _erro(
                    f"Nao da para saber em qual sistema do {tribunal.codigo} "
                    f"o processo {numero.formatado} corre.",
                    "sistema_indeterminado",
                    f"Pergunte ao advogado e repita com `sistema`. {duvida}".strip(),
                )
            if sistema not in SISTEMAS_AUTENTICADOS:
                return _erro(
                    f"Consulta autenticada ainda nao implementada para {sistema!r}.",
                    "sistema_sem_adaptador",
                    "Hoje ha adaptador autenticado para "
                    f"{', '.join(sorted(SISTEMAS_AUTENTICADOS))}. "
                    "Use a base nacional para os demais.",
                )

            # Playwright sincrono nao roda dentro do laco de eventos; vai para
            # uma thread propria.
            dados = await asyncio.to_thread(
                consultar_processo_estruturado, tribunal.codigo, sistema, numero.formatado
            )
            # A confianca sai do PROPRIO dado, e nao de uma constante: quem
            # le por estrutura nao sabe o mesmo que quem le por seletor
            # conferido, e dizer "alta" para os dois apaga essa diferenca
            # justamente onde ela pesa.
            conferida = (dados.get("leitura") or {}).get(
                "confirmada_em_tela_real", True)
            observacao = ("Leitura autenticada do portal, ao vivo. Nenhum documento "
                          "foi aberto e nenhum expediente foi tocado.")
            if not conferida:
                observacao += (
                    " A capa e as movimentacoes foram lidas pela estrutura da "
                    "pagina, e nao por seletor conferido na tela real. Trate "
                    "como leitura nao conferida e diga isso ao advogado.")
            dados["proveniencia"] = {
                "fonte": f"{tribunal.codigo}/{sistema}",
                "metodo": "navegador",
                "confianca": "alta" if conferida else "nao conferida",
                "coletado_em": agora_iso(),
                "observacao": observacao,
            }
            return _json(dados)
        except TetoDeTentativasAtingido as exc:
            return _erro(str(exc), "teto_de_tentativas",
                         "NAO repita a chamada. Relate ao advogado e aguarde.")
        except PortalNaoConfigurado as exc:
            return _erro(str(exc), "portal_nao_configurado",
                         "O operador precisa configurar o endereco do portal.")
        except PermissionError as exc:
            return _erro(str(exc), "acesso_desligado", None)
        except Exception as exc:
            _estado.registrar(acao="consulta_processo_autenticada", numero=params.numero,
                              resultado="erro", detalhe=detalhe_do_erro(exc))
            return _tratar(exc)

    @mcp.tool(name="justica_pecas_do_processo",
              annotations=somente_leitura("Pecas gravadas na pasta"))
    async def justica_pecas_do_processo(params: PecasInput) -> str:
        """O que ja esta GRAVADO na pasta de copias deste processo.

        Nao abre o portal, nao autentica, nao baixa: le a pasta do disco. De
        graca e instantaneo, e pode ser repetido a vontade.

        Devolve so a lista: nome do arquivo, pagina em que a peca comeca,
        quantas folhas e quantos bytes. NENHUM conteudo. Serve para escolher o
        que ler antes de ler, e para ver o tamanho do que a pasta tem.

        A pasta pode estar INCOMPLETA, e isso NAO aparece aqui. Quem baixa e
        o comando `justica-portal consultar --documentos`, e mesmo uma corrida
        inteira pode nao trazer tudo: na corrida de 21/10/2026, a primeira a
        ler o indice completo, vieram 338 dos 340 documentos listados, cobrindo
        1.783 das 1.897 paginas do processo. Das 114 paginas que faltaram, 6
        foram puladas de proposito (dois documentos derrubam o navegador) e as
        outras 108 estao em faixas que o indice do portal nao lista.

        Entao, antes de concluir que o processo nao tem determinada peca,
        confira o indice no portal: a ausencia na pasta nao prova ausencia nos
        autos. Use `justica-portal reindexar`, que relata a cobertura por
        faixa de paginas e mostra exatamente onde estao os buracos.
        """
        try:
            from .pecas import pecas_da_pasta

            numero = parse_numero(params.numero)
            with _na_pasta(params.onde):
                dados = pecas_da_pasta(numero.apenas_digitos, numero.formatado)
            dados["onde"] = params.onde
            _estado.registrar(acao="pecas_do_processo",
                              solicitante=params.solicitante,
                              tribunal="", numero=numero.formatado,
                              resultado=f"{len(dados['pecas'])} peca(s)")
            return _json(dados)
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_cobertura_do_processo",
              annotations=somente_leitura("Cobertura da pasta do processo"))
    async def justica_cobertura_do_processo(params: PecasInput) -> str:
        """Que folhas do processo a pasta cobre, e QUAIS FALTAM.

        Consulte esta ferramenta ANTES de concluir qualquer coisa sobre a
        ausencia de uma peca. A pasta pode estar incompleta, e a lista de
        pecas sozinha nao mostra isso: ela diz o que ha, nunca o que falta.

        Na corrida de 21/10/2026, a primeira a ler o indice completo de um
        processo, vieram 338 dos 340 documentos listados, cobrindo 1.783 das
        1.897 paginas. Quem lesse so a lista de pecas naquele dia concluiria
        que o processo tem 1.783 folhas, e estaria errado por 114.

        `faixas_que_faltam` e o campo que decide. Com ele vazio, a pasta cobre
        tudo o que ja foi baixado sem buraco no meio. Com faixas nele, ha
        folhas que a pasta NAO tem, e dizer que uma peca nao existe nos autos
        sem antes conferir o indice no portal seria afirmar o que nao se sabe.

        `sem_pagina` lista arquivos cujo nome nao traz a pagina inicial, como
        a integral baixada de uma vez. Eles contam no acervo, mas nao entram
        na conta de cobertura por faixa.
        """
        try:
            from .core.acervo import carregar_indice, cobertura_do_acervo

            numero = parse_numero(params.numero)
            with _na_pasta(params.onde):
                indice = carregar_indice(numero.apenas_digitos, numero.formatado)
                dados = cobertura_do_acervo(indice)
            dados["onde"] = params.onde
            dados["processo"] = numero.formatado
            faltam = dados.get("faixas_que_faltam") or []
            cortados = dados.get("truncados") or []
            if cortados:
                dados["atencao_arquivos_cortados"] = (
                    f"{len(cortados)} arquivo(s) nao tem a marca de fim do "
                    "PDF e podem ser download interrompido. PDF cortado abre "
                    "e mostra so o comeco, entao a ausencia de uma peca "
                    "DENTRO dele nao prova nada. Convem baixar de novo."
                )
            # A conclusao e a frase que alguem vai ler rapido e repetir. Ela
            # nao pode afirmar cobertura quando NADA foi medido, e foi
            # exatamente o que fez em 25/10/2026: disse "a pasta cobre as
            # folhas sem buraco" num processo cujo unico arquivo tinha ficado
            # de fora da conta. Lista de faixas faltantes vazia por nao haver
            # o que comparar nao e o mesmo que nada faltando.
            medidas = dados.get("pecas") or []
            if not medidas:
                dados["conclusao"] = (
                    "NAO DA PARA MEDIR a cobertura por faixa: nenhum arquivo "
                    "desta pasta traz a pagina inicial no nome. A lista de "
                    "faixas faltantes veio vazia por nao haver o que "
                    "comparar, e NAO porque nada falte. Arquivo unico, como a "
                    "integra baixada de uma vez, cai sempre neste caso."
                )
            elif faltam:
                dados["conclusao"] = (
                    f"ATENCAO: ha {len(faltam)} faixa(s) de folhas que a "
                    "pasta NAO tem. Nao conclua que uma peca nao existe nos "
                    "autos sem conferir o indice no portal."
                )
            else:
                dados["conclusao"] = (
                    f"A pasta cobre as folhas {dados.get('primeira')} a "
                    f"{dados.get('ultima')} sem buraco. Isso NAO quer dizer "
                    "que cubra o processo inteiro: pode haver folhas antes da "
                    "primeira e depois da ultima, e ausencia de uma peca aqui "
                    "ainda pode significar que ela nunca foi baixada."
                )
            if cortados:
                dados["conclusao"] = (
                    "ARQUIVO CORTADO NA PASTA. " + dados["conclusao"]
                )
            _estado.registrar(
                acao="cobertura_do_processo", solicitante=params.solicitante,
                tribunal="", numero=numero.formatado,
                resultado=f"{len(faltam)} faixa(s) faltando")
            return _json(dados)
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_processos_guardados",
              annotations=somente_leitura("Processos na pasta de copias"))
    async def justica_processos_guardados(onde: str = ONDE_ACERVO,
                                          limite: int = 50) -> str:
        """Os processos que ja existem na pasta, do mais recente ao mais antigo.

        Serve para quando o advogado nao tem o numero a mao: em vez de pedir
        que ele digite, liste e pergunte qual. Nao abre o portal, nao
        autentica e nao le conteudo nenhum.

        `onde` vale "acervo", que e a pasta do escritorio no Google Drive, ou
        "leitura", que e a pasta local do que foi lido sem guardar.

        `folhas_no_indice` pode vir vazio: significa que aquele processo ainda
        nao tem indice, e nao que esteja vazio. A contagem de arquivos vale
        sempre.
        """
        try:
            from .core.acervo import processos_guardados

            with _na_pasta(onde):
                achados = processos_guardados()
            cortados = achados[:max(1, min(limite, 200))]
            _estado.registrar(acao="processos_guardados", tribunal="",
                              resultado=f"{len(achados)} processo(s)")
            return _json({
                "onde": onde,
                "total": len(achados),
                "mostrados": len(cortados),
                "processos": cortados,
            })
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_ler_peca",
              annotations=somente_leitura("Ler o texto de uma peca"))
    async def justica_ler_peca(params: LerPecaInput) -> str:
        """O TEXTO de uma peca ja gravada na pasta. Devolve conteudo dos autos.

        Esta e a unica ferramenta deste servidor que devolve conteudo do
        processo. Todas as outras devolvem estrutura, contagem e metadado. O
        texto que volta aqui e dado do cliente: use-o para a analise e nao o
        reproduza fora do trabalho para o qual o advogado o pediu.

        Le do disco, nao do portal: nao autentica, nao gasta tentativa, nao tem
        teto por hora, e pode ser repetido quantas vezes a analise precisar.

        Tres avisos que a resposta pode trazer, e os tres mudam a conclusao:

        - `cortado: true` com `aviso`: o teto de caracteres foi atingido e o
          texto parou numa folha. Peca a continuacao com `de` na folha que o
          aviso indica.
        - `folhas_sem_texto`: folhas que sao imagem digitalizada. Elas NAO
          estao em branco: o programa e que nao faz reconhecimento optico. Nao
          conclua que a peca nada diz nessas folhas.
        - `folhas_ilegiveis`: folhas que levantaram erro na extracao. As outras
          vieram assim mesmo.
        """
        try:
            from .pecas import ler_peca

            numero = parse_numero(params.numero)
            with _na_pasta(params.onde):
                dados = ler_peca(numero.apenas_digitos, numero.formatado,
                                 params.peca, de=params.de, ate=params.ate)
            dados["onde"] = params.onde
            _estado.registrar(
                acao="ler_peca", solicitante=params.solicitante, tribunal="",
                numero=numero.formatado,
                resultado=(dados.get("erro") or
                           f"peca {params.peca}, "
                           f"{dados.get('caracteres', 0)} caractere(s)"))
            return _json(dados)
        except Exception as exc:
            return _tratar(exc)

    @mcp.tool(name="justica_acesso_autenticado_situacao",
              annotations=somente_leitura("Situacao do acesso autenticado"))
    async def justica_acesso_autenticado_situacao() -> str:
        """Diz se o acesso autenticado esta ligado, quais portais estao
        configurados e quantas tentativas de autenticacao ainda cabem na janela.

        Consulte antes de usar a consulta autenticada, para nao gastar tentativa
        a toa nem prometer ao advogado algo que o servidor nao pode fazer.
        """
        return _json({
            "habilitado": autenticado_habilitado(),
            "portais": [
                {"tribunal": c.tribunal, "sistema": c.sistema,
                 "perfil_definido": c.perfil is not None}
                for c in portais_configurados()
            ],
            "tentativas": LimiteTentativas.do_ambiente(_estado).situacao(),
            "observacao": ("Cada consulta autenticada consome uma tentativa. O teto "
                           "existe para o acesso do advogado nao ser bloqueado pelo "
                           "portal apos tentativas seguidas."),
            # Campo que o modelo nao tinha como interpretar, e sobre o qual
            # respondia "nao posso verificar o que significa". Dado que chega
            # sem explicacao vira resposta hesitante, e a explicacao custa tres
            # linhas.
            "sobre_perfil_definido": (
                "O perfil e a inscricao na Ordem ou o tipo de usuario que o "
                "portal pergunta DEPOIS de autenticar: o eproc pergunta qual "
                "inscricao usar quando ha mais de uma, e o Portal de Servicos "
                "do Rio de Janeiro pergunta o tipo de usuario. "
                "`perfil_definido: false` NAO impede a consulta, mas, no "
                "portal que pergunta, a corrida para na tela de escolha DEPOIS "
                "de a credencial ter sido enviada, e a tentativa ja foi gasta. "
                "Com o perfil definido na configuracao, a corrida escolhe "
                "sozinha e segue. Nem todo portal pergunta: em 23/10/2026 o "
                "PJe do Rio de Janeiro nao perguntou e o eproc da Justica "
                "Federal da 2a Regiao perguntou."
            ),
            "tetos_por_sistema": ("O teto conta tentativas DESDE O ULTIMO "
                                  "SUCESSO: um login que da certo zera o "
                                  "contador, porque bloqueio de conta vem de "
                                  "falhas consecutivas e nao de trabalho."),
        })

    @mcp.tool(
        name="justica_sondar_sistemas",
        annotations=ToolAnnotations(
            title="Descobrir em qual sistema cada processo corre",
            # Nao grava nada do processo; grava o resultado da sondagem no
            # historico da banca, que e o ponto da ferramenta.
            read_only_hint=False,
            destructive_hint=False,
            # Cada corrida consome ate uma tentativa de autenticacao por
            # sistema do tribunal.
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )
    async def justica_sondar_sistemas(params: SondarSistemasInput) -> str:
        """Descobre em qual sistema cada processo corre, UMA autenticacao por
        sistema e nenhuma por processo. Volta na hora, sem esperar o fim.

        QUANDO USAR: quando `justica_resolver_sistema` responder
        'indeterminado' para um ou mais processos do mesmo tribunal. O
        Tribunal de Justica do Rio de Janeiro opera eproc, PJe e DCP ao mesmo
        tempo, e o numero do processo nao diz em qual deles o processo esta.

        MANDE A LISTA INTEIRA DE UMA VEZ. O custo e por SISTEMA, nao por
        processo: a lista toda e procurada dentro de cada sessao ja aberta.
        Dez processos custam o mesmo que dois, e pedir um de cada vez
        multiplica o custo por dez numa janela que e do escritorio inteiro.

        A ordem e eproc, depois PJe, depois DCP, e processo achado sai da
        fila: se todos estiverem no eproc, a corrida custa UMA autenticacao e
        os outros dois sistemas nem sao abertos.

        O QUE A RESPOSTA NAO DIZ. A sonda responde 'achado' ou 'nao
        confirmado', nunca 'nao esta aqui'. Nenhuma corrida deste projeto
        jamais viu a tela de 'nada encontrado' destes portais, entao afirmar
        ausencia seria afirmar o que ninguem olhou. **Nao conclua que um
        processo nao existe num sistema a partir de 'nao confirmado'.**

        O resultado fica no historico da banca, na pasta de copias
        compartilhada: ninguem mais precisa sondar o mesmo processo.

        CUSTO REAL: autentica de verdade no tribunal. **Diante de erro, nao
        repita a chamada**: relate ao advogado e espere instrucao.

        PRESENCA HUMANA: o eproc levanta o desafio "Confirme que e humano", e
        ele exige uma pessoa na frente da tela. Avise o advogado antes.
        """
        from .core.tribunais import identificar_tribunal as _tribunal_de
        from .trabalhos import MURAL

        if not autenticado_habilitado():
            return _erro(
                "Acesso autenticado desligado neste servidor.", "acesso_desligado",
                "Ligar permite disparar autenticacao real no tribunal com a "
                "credencial do advogado, e e decisao do operador.",
            )
        if not params.numeros:
            return _erro("Nenhum processo informado.", "sem_processos")

        # TODOS conferidos antes de qualquer navegador abrir. Numero errado
        # descoberto no meio da corrida ja custou a autenticacao.
        try:
            numeros = [parse_numero(bruto) for bruto in params.numeros]
            casas = {n.chave_segmento_tribunal for n in numeros}
            if len(casas) > 1:
                return _erro(
                    f"Vieram processos de {len(casas)} tribunais diferentes.",
                    "tribunais_diferentes",
                    "Uma varredura, um tribunal: cada tribunal tem os seus "
                    "proprios portais e a sua propria credencial. Peca uma "
                    "sondagem por tribunal.",
                )
            tribunal = _tribunal_de(numeros[0].chave_segmento_tribunal)
        except NumeroCNJInvalido as exc:
            return _erro(str(exc), "numero_invalido")
        except TribunalForaDoEscopo as exc:
            return _erro(str(exc), "tribunal_fora_do_escopo")

        configurados = sorted(
            c.sistema for c in portais_configurados()
            if c.tribunal == tribunal.codigo)
        if not configurados:
            return _erro(
                f"Nenhum portal do {tribunal.codigo} configurado.",
                "portal_nao_configurado",
                "O endereco dos portais mora no arquivo de configuracao da "
                "banca. Sem nenhum deles nao ha onde sondar.",
            )

        emCurso = next(
            (MURAL.em_curso_para(cada.formatado) for cada in numeros
             if MURAL.em_curso_para(cada.formatado) is not None), None)
        if emCurso is not None:
            return _erro(
                "Ja ha um trabalho em curso para um destes processos.",
                "trabalho_em_curso",
                f"Acompanhe com justica_situacao_do_download, trabalho "
                f"{emCurso.identificador}. Comecar outro gastaria mais "
                "tentativas de autenticacao sem trazer nada novo.",
            )
        try:
            LimiteTentativas.do_ambiente(_estado).exigir_folga()
        except TetoDeTentativasAtingido as exc:
            return _erro(str(exc), "teto_de_tentativas")

        argumentos = ["sondar", "--tribunal", tribunal.codigo,
                      "--confirmo-tentativa-unica"]
        for cada in numeros:
            argumentos += ["--processo", cada.formatado]
        if params.conferir_segundo_grau:
            argumentos.append("--conferir-segundo-grau")

        rotulo = (numeros[0].formatado if len(numeros) == 1
                  else f"{numeros[0].formatado} e mais {len(numeros) - 1}")
        trabalho = MURAL.comecar("sondagem de sistema", rotulo, argumentos)
        _estado.registrar(
            acao="sondagem_pedida", tribunal=tribunal.codigo,
            numero=rotulo, resultado=trabalho.identificador,
            solicitante=params.solicitante,
        )
        return _json({
            "trabalho": trabalho.identificador,
            "tribunal": tribunal.codigo,
            "processos": [cada.formatado for cada in numeros],
            "ordem_da_varredura": [s.value for s in tribunal.sistemas_candidatos
                                   if s.value in configurados],
            "estado": trabalho.estado,
            "autenticacoes_no_maximo": len(configurados),
            "aviso": (
                "A varredura comecou. Acompanhe com "
                "justica_situacao_do_download. Ela custa ATE uma autenticacao "
                "por sistema, e menos do que isso quando os processos sao "
                "achados logo no primeiro. NAO chame esta ferramenta de novo "
                "para os mesmos processos."
            ),
        })

    @mcp.tool(
        name="justica_baixar_autos",
        annotations=ToolAnnotations(
            title="Baixar os autos do processo",
            # Nao e leitura: grava arquivos na pasta de copias da banca.
            read_only_hint=False,
            # Nao destroi nada. O acervo confere repeticao antes de indexar, e
            # arquivo que nao e PDF nem chega a ser gravado.
            destructive_hint=False,
            # Cada chamada consome uma tentativa de autenticacao no tribunal.
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )
    async def justica_baixar_autos(params: BaixarAutosInput) -> str:
        """Pede a copia integral dos autos e VOLTA NA HORA, sem esperar o fim.

        O trabalho corre num processo separado, porque ele leva de minutos a
        horas: o portal GERA o arquivo quando se pede, e no eproc da Justica
        Federal da 2a Regiao a geracao e assincrona, podendo levar horas ate o
        tribunal avisar que ficou pronta.

        A resposta traz o identificador do trabalho. Acompanhe com
        `justica_situacao_do_download` e, quando terminar, use
        `justica_pecas_do_processo` para ver o que foi gravado.

        CUSTO REAL: autentica de verdade no tribunal e consome uma tentativa.
        Tentativas seguidas bloqueiam o acesso. **Diante de erro, nao repita a
        chamada**: relate ao advogado e espere instrucao.

        PRESENCA HUMANA: o eproc levanta o desafio "Confirme que e humano", e
        ele exige uma pessoa na frente da tela. Sem ela, o trabalho espera e
        termina sem arquivo, dizendo isso. Avise o advogado antes de comecar.

        O AVISO DE RESPONSABILIDADE do PJe (resolucao nº. 121 do Conselho
        Nacional de Justica) so e aceito quando `aceito_o_termo` vier
        verdadeiro, e esse aceite e ato do advogado: peca a ele em palavras
        antes de marcar, nunca decida sozinho.
        """
        from .core.acesso import config_portal
        from .trabalhos import MURAL

        if not autenticado_habilitado():
            return _erro(
                "Acesso autenticado desligado neste servidor.", "acesso_desligado",
                "Ligar permite disparar autenticacao real no tribunal com a "
                "credencial do advogado, e e decisao do operador.",
            )
        try:
            numero = parse_numero(params.numero)
            tribunal = identificar_tribunal(numero.chave_segmento_tribunal)
            sistema, duvida = _sistema_pedido_ou_resolvido(
                numero, params.sistema, await resolver_sistema(numero, _estado))
            if sistema is None:
                configurados = sorted(
                    c.sistema for c in portais_configurados()
                    if c.tribunal == tribunal.codigo)
                return _erro(
                    f"Nao da para saber em qual sistema do {tribunal.codigo} "
                    f"o processo {numero.formatado} corre.",
                    "sistema_indeterminado",
                    "Pergunte ao advogado e repita com `sistema`. "
                    f"Configurados para este tribunal: "
                    f"{', '.join(configurados) or 'nenhum'}. "
                    f"{duvida}".strip(),
                )
            config_portal(tribunal.codigo, sistema)
            # Os outros processos sao conferidos AQUI, antes de o navegador
            # abrir. Descobrir na quarta consulta que o terceiro numero e de
            # outro portal custaria a corrida inteira, e ela ja gastou a
            # autenticacao.
            outros = []
            for bruto in params.tambem:
                outro = parse_numero(bruto)
                sistema_do_outro, _ = _sistema_pedido_ou_resolvido(
                    outro, params.sistema,
                    await resolver_sistema(outro, _estado))
                if sistema_do_outro is not None and sistema_do_outro != sistema:
                    return _erro(
                        f"{outro.formatado} tramita no {sistema_do_outro}, e "
                        f"{numero.formatado} no {sistema}.",
                        "portais_diferentes",
                        "Processos de portais diferentes exigem sessoes "
                        "diferentes. Peca um pedido por portal.",
                    )
                outros.append(outro)
        except NumeroCNJInvalido as exc:
            return _erro(str(exc), "numero_invalido")
        except TribunalForaDoEscopo as exc:
            return _erro(str(exc), "tribunal_fora_do_escopo")
        except PortalNaoConfigurado as exc:
            return _erro(str(exc), "portal_nao_configurado",
                         "O endereco do portal mora no arquivo de configuracao "
                         "da banca, e nao em parametro de ferramenta.")

        # Um trabalho por processo. Dois ao mesmo tempo gastariam duas
        # tentativas, abririam dois navegadores e escreveriam na mesma pasta.
        emCurso = next(
            (MURAL.em_curso_para(cada.formatado)
             for cada in [numero] + outros
             if MURAL.em_curso_para(cada.formatado) is not None), None)
        if emCurso is not None:
            return _erro(
                f"Ja ha um download em curso para {numero.formatado}.",
                "trabalho_em_curso",
                f"Acompanhe com justica_situacao_do_download, trabalho "
                f"{emCurso.identificador}. Comecar outro gastaria mais uma "
                "tentativa de autenticacao sem trazer nada novo.",
            )
        try:
            LimiteTentativas.do_ambiente(_estado).exigir_folga()
        except TetoDeTentativasAtingido as exc:
            return _erro(str(exc), "teto_de_tentativas")

        argumentos = [
            "consultar",
            "--tribunal", tribunal.codigo,
            "--sistema", sistema,
            "--processo", numero.formatado,
            "--documentos", params.documentos,
            "--confirmo-tentativa-unica",
        ]
        if params.aceito_o_termo:
            argumentos.append("--aceito-o-termo")
        if not params.guardar:
            argumentos.append("--sem-guardar")
        for outro in outros:
            argumentos += ["--processo", outro.formatado]
        if params.segundos_download:
            argumentos += ["--segundos-download", str(params.segundos_download)]

        rotulo = numero.formatado
        if outros:
            rotulo = f"{numero.formatado} e mais {len(outros)}"
        trabalho = MURAL.comecar("download dos autos", rotulo, argumentos)
        _estado.registrar(
            acao="baixar_autos_pedido", tribunal=tribunal.codigo, sistema=sistema,
            numero=numero.formatado, resultado=trabalho.identificador,
            solicitante=params.solicitante,
        )
        return _json({
            "trabalho": trabalho.identificador,
            "processo": numero.formatado,
            "tribunal": tribunal.codigo,
            "sistema": sistema,
            "estado": trabalho.estado,
            "onde_vai_ficar": ONDE_ACERVO if params.guardar else ONDE_LEITURA,
            "processos": [cada.formatado for cada in [numero] + outros],
            "autenticacoes": 1,
            "aviso": (
                "O pedido comecou. Isso leva de minutos a horas conforme o "
                "portal e o tamanho do processo. NAO chame esta ferramenta de "
                "novo para o mesmo processo: use justica_situacao_do_download."
            ),
        })

    @mcp.tool(name="justica_situacao_do_download",
              annotations=somente_leitura("Situacao do download"))
    async def justica_situacao_do_download(trabalho: Optional[str] = None,
                                           ultimas_linhas: int = 12) -> str:
        """Em que pe esta um download pedido com `justica_baixar_autos`.

        Sem o identificador, lista os ultimos trabalhos desta execucao. O
        relato vem do proprio comando, linha a linha, e nada nele e inferido.

        `estado` vale "em curso", "concluido" ou "falhou". Concluido NAO quer
        dizer que veio arquivo: pode ter vindo a resposta de que o portal
        aceitou o pedido e esta montando, que e o caso normal do eproc. As
        ultimas linhas do relato dizem qual dos dois.
        """
        from .trabalhos import MURAL

        if not trabalho:
            return _json({"trabalhos": MURAL.listar()})
        achado = MURAL.ver(trabalho)
        if achado is None:
            return _erro(
                f"Nao ha trabalho {trabalho!r} nesta execucao.", "trabalho_desconhecido",
                "O mural vive enquanto o servidor vive: reiniciar o Claude "
                "apaga a lista, mas nao desfaz o que ja foi gravado em disco. "
                "Use justica_pecas_do_processo para ver o que ha na pasta.",
            )
        return _json(achado.resumo(ultimas=max(1, min(ultimas_linhas, 60))))

    @mcp.tool(name="justica_auditoria_recente", annotations=somente_leitura("Auditoria recente"))
    async def justica_auditoria_recente(limite: int = 50) -> str:
        """Ultimas chamadas registradas: data, acao, tribunal, sistema, processo e resultado."""
        return _json({"registros": _estado.auditoria_recente(limite=limite)})
