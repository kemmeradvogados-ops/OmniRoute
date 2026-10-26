"""Registro dos tribunais no escopo da banca e ordem de sondagem de sistema.

Ponto central do desenho: `J.TR` -> tribunal e DETERMINISTICO (vem do numero).
`tribunal -> sistema` NAO e, e nao pode ser tabelado como verdade.

Motivo verificado (setembro de 2026):

  - Tribunal de Justica do Estado do Rio de Janeiro opera PJe, eproc e DCP em
    paralelo. O Ato Executivo Conjunto TJ/CGJ nº. 21/2026 fixou o cronograma de
    migracao do PJe para o eproc; ja foram migrados 104.455 processos (82.818
    do PJe e 21.637 do DCP), e a distribuicao nas competencias civeis esta
    bloqueada no PJe e no DCP.
  - Tribunal de Justica do Estado de Sao Paulo migra do SAJ para o eproc em
    ciclos: Juizado Especial Civel desde outubro de 2025; Civel, Registros
    Publicos, Falencias e Recuperacoes Judiciais desde fevereiro de 2026;
    Fazenda Publica a partir de agosto de 2026.

Por isso `SISTEMAS_CANDIDATOS` e uma ORDEM DE SONDAGEM (o que tentar primeiro),
nunca uma afirmacao sobre onde o processo esta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Sistema(str, Enum):
    PJE = "pje"
    EPROC = "eproc"
    ESAJ = "esaj"
    DCP = "dcp"
    # Central do Processo Eletronico do Superior Tribunal de Justica. Sistema
    # proprio daquele tribunal, sem parentesco com os outros quatro.
    CPE = "cpe"
    INDETERMINADO = "indeterminado"


# O nome que uma PESSOA le. As chaves acima sao internas, e uma delas vazou
# para o relatorio do resolvedor em 26/10/2026: o advogado leu "DCP" e
# perguntou o que era, com razao. Nome interno em texto de usuario e defeito
# de interface, nao detalhe. A chave continua sendo a chave; isto e so para
# texto.
NOME_DO_SISTEMA: dict[str, str] = {
    "pje": "Processo Judicial Eletronico",
    "eproc": "eproc",
    "esaj": "e-SAJ",
    "dcp": "Portal de Servicos",
    "cpe": "Central do Processo Eletronico",
    "indeterminado": "sistema nao determinado",
}


def nome_do_sistema(sistema) -> str:
    """O nome por extenso, para texto que alguem vai ler.

    Aceita tanto o `Sistema` quanto a string crua, porque os dois circulam:
    o resolvedor guarda a string no historico e o sondador carrega o enum.
    Desconhecido volta como veio, em vez de virar "None": um nome estranho e
    pior que um nome feio, mas sumir com a informacao e pior que os dois.
    """
    chave = getattr(sistema, "value", sistema)
    return NOME_DO_SISTEMA.get(str(chave), str(chave))


@dataclass(frozen=True)
class Tribunal:
    codigo: str
    nome: str
    chave_segmento_tribunal: str
    alias_datajud: str
    sigla_djen: str
    sistemas_candidatos: tuple[Sistema, ...]
    observacao: str = ""
    credencial_disponivel: tuple[Sistema, ...] = field(default_factory=tuple)


# Sistemas que NAO tem instalacao propria de segundo grau, por tribunal.
#
# Informado pelo operador em 26/10/2026, e importa porque o contrario seria
# pedir que alguem configure um endereco que nao existe. A sondagem usa isto
# para dizer o motivo em vez de sugerir uma chave de .env inutil.
#
#   PJe do Tribunal de Justica do Rio de Janeiro: nao ha segundo grau.
#   Portal de Servicos do mesmo tribunal: o endereco e o MESMO nos dois graus.
#     Ao inserir o numero, quando ha recurso, a busca abre uma tabela com as
#     possibilidades (apelacao, agravo e outras). Isso explica as corridas de
#     25 e 26/10/2026 em que a busca devolveu 5, 2 e 1 linha para numeros
#     exatos: nao eram processos homonimos, eram as pecas do mesmo processo
#     nos graus e serventias.
SEM_SEGUNDO_GRAU_PROPRIO: dict = {
    ("TJRJ", "pje"): "o PJe do Tribunal de Justica do Rio de Janeiro nao tem "
                     "segundo grau (informado pelo operador em 26/10/2026)",
    ("TJRJ", "dcp"): "o Portal de Servicos atende os dois graus no MESMO "
                     "endereco: com recurso, a busca abre uma tabela com as "
                     "possibilidades (informado pelo operador em 26/10/2026)",
}


def motivo_sem_segundo_grau(tribunal: str, sistema: str) -> str:
    """Por que este sistema nao tem endereco de segundo grau, ou vazio.

    Vazio significa "ninguem registrou o motivo", e nesse caso quem chama
    sugere a chave do .env. Com motivo, sugerir a chave seria pedir que
    alguem configure um endereco que nao existe.
    """
    return SEM_SEGUNDO_GRAU_PROPRIO.get(
        ((tribunal or "").upper(), (sistema or "").lower()), "")


# Escopo fechado nas credenciais da planilha da banca.
TRIBUNAIS: dict[str, Tribunal] = {
    "8.19": Tribunal(
        codigo="TJRJ",
        nome="Tribunal de Justica do Estado do Rio de Janeiro",
        chave_segmento_tribunal="8.19",
        alias_datajud="api_publica_tjrj",
        sigla_djen="TJRJ",
        # eproc primeiro: recebe toda distribuicao nova das competencias civeis.
        sistemas_candidatos=(Sistema.EPROC, Sistema.PJE, Sistema.DCP),
        observacao=(
            "Tres sistemas ativos em migracao. eproc recebe as distribuicoes novas; "
            "acervo antigo permanece em PJe e DCP ate migrar."
        ),
        credencial_disponivel=(Sistema.PJE, Sistema.EPROC, Sistema.DCP),
    ),
    "8.26": Tribunal(
        codigo="TJSP",
        nome="Tribunal de Justica do Estado de Sao Paulo",
        chave_segmento_tribunal="8.26",
        alias_datajud="api_publica_tjsp",
        sigla_djen="TJSP",
        # e-SAJ ainda concentra a maior parte do acervo nao migrado.
        sistemas_candidatos=(Sistema.EPROC, Sistema.ESAJ),
        observacao=(
            "Migracao SAJ para eproc em ciclos. A banca possui credencial dos "
            "dois sistemas, entao cobre tanto o acervo migrado quanto o antigo."
        ),
        credencial_disponivel=(Sistema.EPROC, Sistema.ESAJ),
    ),
    "5.01": Tribunal(
        codigo="TRT1",
        nome="Tribunal Regional do Trabalho da 1ª Regiao",
        chave_segmento_tribunal="5.01",
        alias_datajud="api_publica_trt1",
        sigla_djen="TRT1",
        sistemas_candidatos=(Sistema.PJE,),
        observacao="Justica do Trabalho opera integralmente em PJe.",
        credencial_disponivel=(Sistema.PJE,),
    ),
    "3.00": Tribunal(
        codigo="STJ",
        nome="Superior Tribunal de Justica",
        chave_segmento_tribunal="3.00",
        # [NAO CONFERIDO] O alias do DataJud e a sigla do Diario Eletronico
        # Nacional para o Superior Tribunal de Justica ainda nao foram testados
        # em producao. Estao escritos no padrao dos demais, e e PRECISO conferi-los
        # antes de confiar numa consulta que os use: um alias errado devolve
        # "nada encontrado", que se confunde com processo inexistente.
        alias_datajud="api_publica_stj",
        sigla_djen="STJ",
        sistemas_candidatos=(Sistema.CPE,),
        observacao=(
            "Central do Processo Eletronico, em cpe.web.stj.jus.br. Tela de "
            "entrada lida em 05/10/2026: aplicacao de pagina unica, com "
            "`input#cpf`, `input[name=password]` e botao 'Entrar' SEM "
            "identificador. Ha tambem entrada por gov.br e por certificado "
            "digital, nenhuma das duas escrita aqui."
        ),
        credencial_disponivel=(Sistema.CPE,),
    ),
    "4.02": Tribunal(
        codigo="TRF2",
        nome="Justica Federal da 2ª Regiao",
        chave_segmento_tribunal="4.02",
        alias_datajud="api_publica_trf2",
        sigla_djen="TRF2",
        sistemas_candidatos=(Sistema.EPROC,),
        observacao=(
            "Abrange a Justica Federal do Rio de Janeiro (primeiro grau). "
            "Alias do DataJud para o primeiro grau federal precisa ser conferido "
            "em producao."
        ),
        credencial_disponivel=(Sistema.EPROC,),
    ),
}


class TribunalForaDoEscopo(LookupError):
    """Tribunal identificado, porem fora das credenciais e adaptadores da banca."""


def identificar_tribunal(chave_segmento_tribunal: str) -> Tribunal:
    """Resolve `J.TR` para um tribunal do escopo. Deterministico, sem rede."""
    tribunal = TRIBUNAIS.get(chave_segmento_tribunal)
    if tribunal is None:
        raise TribunalForaDoEscopo(
            f"Segmento.tribunal {chave_segmento_tribunal} fora do escopo atual. "
            f"Cobertos: "
            + ", ".join(f"{t.codigo} ({k})" for k, t in TRIBUNAIS.items())
            + ". Consulta a este tribunal exige novo adaptador e credencial propria."
        )
    return tribunal
