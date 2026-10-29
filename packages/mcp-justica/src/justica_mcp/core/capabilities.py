"""Matriz de capacidades declarada por adaptador.

Sem esta matriz o agente tenta baixar a integra por um adaptador que nao baixa,
recebe vazio e inventa uma explicacao. Com ela, o servidor responde antes de
gastar a chamada: "o DataJud expoe metadados e movimentos, nunca documentos".

A diferenca entre as duas recusas e o ponto da matriz, e confundi-las e pior
que nao ter matriz nenhuma. NAO_SUPORTADO e afirmacao sobre A FONTE: aquele
portal nao oferece aquilo, e nenhum trabalho deste lado muda isso.
NAO_IMPLEMENTADO e afirmacao sobre ESTE PROJETO: a fonte oferece e o adaptador
ainda nao foi escrito. Escrever NAO_SUPORTADO para dizer "nao pretendo
construir" poe na boca do servidor uma afirmacao falsa sobre o tribunal, e o
advogado deixa de procurar no portal uma coisa que esta la. Foi o que
aconteceu com o DCP do Tribunal de Justica do Rio de Janeiro ate 06/10/2026.
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
    # e-SAJ: conferido em campo em 22/09/2026, ponta a ponta, ate a integra.
    #
    # ESTE ADAPTADOR NAO ESTAVA NA MATRIZ. Ausente, `consultar()` devolvia
    # NAO_IMPLEMENTADO por omissao, e o e-SAJ e o adaptador mais verificado do
    # projeto. Omissao numa matriz de declaracao nao e silencio: e negativa.
    #
    # DOIS PORTOES, E ELES NAO SAO O MESMO. `SISTEMAS_COM_CONSULTA`, em
    # `portal.py`, diz o que a LINHA DE COMANDO aceita: os quatro.
    # `SISTEMAS_AUTENTICADOS`, em `tools.py`, diz o que a FERRAMENTA do
    # conector aceita: so `dcp` e `eproc`. O e-SAJ e o PJe sao recusados pela
    # ferramenta ANTES de autenticar, de proposito, porque o caminho dela tem
    # um ramo para o Portal de Servicos e outro para a busca rapida do eproc,
    # e nenhum dos dois serve a essas telas: aceitar gastaria uma autenticacao
    # para falhar na tela errada.
    #
    # Por isso o motivo precisa dizer POR ONDE. Declarar so EXIGE_CREDENCIAL
    # faria o assistente prometer ao advogado uma consulta que a ferramenta
    # recusa em seguida, que e o mesmo erro de antes virado do avesso.
    "esaj": {
        **{c: _fase2() for c in Capacidade},
        Capacidade.CONSULTAR_PROCESSO: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO: a ferramenta "
            "`justica_consultar_processo_autenticado` recusa 'esaj' antes de "
            "autenticar. Pela linha de comando a consulta foi conferida em "
            "campo em 22/09/2026; exige credencial no cofre e "
            "`JUSTICA_ACESSO_AUTENTICADO=1`, e gasta uma tentativa.",
        ),
        Capacidade.LISTAR_ANDAMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO. Movimentacoes da tela do processo, com "
            "a expansao de 'exibir mais movimentacoes' ja percorrida.",
        ),
        Capacidade.LISTAR_DOCUMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO. Pelas pecas da Pasta Digital, "
            "listadas com rotulo e endereco.",
        ),
        Capacidade.BAIXAR_INTEGRA: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO. A copia da Pasta Digital foi "
            "percorrida ponta a ponta em campo em 22/09/2026. ATENCAO: a "
            "copia e o PADRAO do comando, nao um extra. Sem `--documentos`, "
            "vale 'auto', que escolhe a integra quando a pasta do processo "
            "ainda esta vazia. Quem nao quer copia precisa dizer "
            "`--documentos nenhum`.",
        ),
        Capacidade.DAR_CIENCIA_INTIMACAO: _nao_suportado(
            "Abrir o expediente dispara a ciencia e inicia o prazo. O botao de "
            "ciencia fica na pagina de intimacoes, e o adaptador nao encosta "
            "nele."
        ),
    },
    # PJe: caminho fotografado pelo operador em 30/09/2026, do menu ate os
    # autos em aba nova, e conferido em campo na mesma data.
    "pje": {
        **{c: _fase2() for c in Capacidade},
        Capacidade.CONSULTAR_PROCESSO: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO: a ferramenta "
            "`justica_consultar_processo_autenticado` recusa 'pje' antes de "
            "autenticar. Os identificadores dos campos nao apareceram nas "
            "fotos, entao o adaptador procura os campos pela forma e confere "
            "o que digitou antes de pesquisar; se a forma nao bater, ele "
            "para.",
        ),
        Capacidade.LISTAR_ANDAMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO. Pela linha do tempo dos autos, "
            "percorrida ate o fim.",
        ),
        Capacidade.LISTAR_DOCUMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO. As pecas da linha do tempo, com "
            "rotulo e endereco.",
        ),
        Capacidade.BAIXAR_INTEGRA: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "SO PELA LINHA DE COMANDO, e dependente do aceite do termo de "
            "responsabilidade da resolucao nº. 121 do Conselho Nacional de "
            "Justica. O aceite e ato do advogado: sem `--aceito-o-termo` o "
            "comando mostra o texto e para, e NADA e lido, nem a linha do "
            "tempo. A copia em si e o PADRAO (`--documentos` vale 'auto'); "
            "quem nao a quer precisa dizer `--documentos nenhum`.",
        ),
        Capacidade.DAR_CIENCIA_INTIMACAO: _nao_suportado(
            "Abrir expediente dispara a ciencia e inicia o prazo."
        ),
    },
    # CPE do Superior Tribunal de Justica: sem adaptador escrito. Esta e a
    # unica entrada desta matriz que continua inteira em NAO_IMPLEMENTADO, e
    # continua com razao: `SISTEMAS_COM_CONSULTA` tambem nao o inclui.
    "cpe": {c: _fase2() for c in Capacidade},
    # DCP, o Portal de Servicos do Tribunal de Justica do Rio de Janeiro.
    #
    # ATE 29/10/2026 ESTA ENTRADA DIZIA QUE NADA ESTAVA IMPLEMENTADO, com a
    # justificativa de que "nenhuma tela do DCP foi lida ate aqui". Isso era
    # verdade em 06/10. Deixou de ser no dia seguinte, e a declaracao ficou
    # congelada no passado enquanto o adaptador crescia.
    #
    # O preco de uma matriz desatualizada e o inverso do que ela existe para
    # evitar: o assistente le "nao implementado" e DIZ AO ADVOGADO QUE NAO DA,
    # em vez de tentar. Aconteceu em 28/10/2026, com o proprio operador.
    #
    # Telas lidas em campo: 05, 06, 08, 13, 21, 27, 28 e 29/10/2026, nos dois
    # graus. As movimentacoes do segundo grau foram conferidas pelo advogado
    # contra a tela, linha a linha, em 29/10/2026.
    "dcp": {
        **{c: _fase2() for c in Capacidade},
        Capacidade.CONSULTAR_PROCESSO: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "Pela ferramenta do conector E pela linha de comando: 'dcp' esta "
            "em `SISTEMAS_AUTENTICADOS` desde 13/10/2026. Consulta "
            "autenticada pelo navegador, nos dois graus. O numero unico e o "
            "mesmo em todas as instancias: quem escolhe a instancia e "
            "`--linha`, e a busca lista as linhas com a instancia de cada "
            "uma.",
        ),
        Capacidade.LISTAR_ANDAMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "Historico completo, paginado ate o fim: no primeiro grau pelos "
            "botoes numerados, no segundo pelo icone 'proximos 50 "
            "movimentos'. A contagem lida e conferida contra o total que a "
            "propria tela declara.",
        ),
        Capacidade.LISTAR_DOCUMENTOS: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "No segundo grau, os documentos de inteiro teor saem em lista "
            "propria, com rotulo, endereco e data.",
        ),
        Capacidade.BAIXAR_DOCUMENTO: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "Um download por documento, pelo Visualizador. ATENCAO: o "
            "Visualizador abre por PADRAO, porque `--documentos` vale 'auto'. "
            "Consultar sem entrar nos autos exige dizer `--documentos "
            "nenhum`.",
        ),
        Capacidade.BAIXAR_INTEGRA: Declaracao(
            Situacao.EXIGE_CREDENCIAL,
            "O portal OFERECE o botao da integra, mas medido em 20/10/2026 "
            "ele nao entrega em processo grande: nem a integral nem o lote de "
            "300 paginas. O que se viu entregar e um download por documento "
            "(`--documentos um-a-um`), que reabre o Visualizador a cada um e "
            "pula o que ja esta em disco.",
        ),
        Capacidade.DAR_CIENCIA_INTIMACAO: _nao_suportado(
            "Abrir expediente dispara a ciencia e inicia o prazo."
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
