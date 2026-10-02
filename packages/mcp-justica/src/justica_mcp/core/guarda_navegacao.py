"""Trava de navegacao do acesso autenticado.

Existe por uma razao concreta: abrir o teor de uma intimacao eletronica
dispara a ciencia e inicia o prazo (lei nº. 11.419/06, artigo 5º, §3º, com a
contagem a partir do envio conforme decisao do Superior Tribunal de Justica de
outubro de 2025). Nao existe desfazer. Um clique errado antecipa um prazo do
cliente.

Por isso a protecao nao vive em instrucao de prompt, que falha, e sim aqui.

DESENHO: NEGAR POR PADRAO.

Nada e permitido a menos que esteja explicitamente na lista de permissao. A
lista comeca VAZIA e so e preenchida depois de conferencia em campo, com o
advogado olhando. A consequencia e proposital: enquanto ninguem confirmou uma
tela como segura, o adaptador nao consegue chegar nela.

A alternativa, listar o que e perigoso, exigiria que eu soubesse de antemao
todas as telas perigosas do portal. Nao sei, e errar nessa direcao custa um
prazo. Errar na direcao de negar custa uma linha de configuracao.

SEGUNDA CAMADA: mesmo que uma tela entre na lista de permissao por engano,
termos de risco no endereco ou no seletor bloqueiam assim mesmo. E heuristica,
reforco do desenho principal, nunca a protecao em si.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Modo(str, Enum):
    ENSAIO = "ensaio"
    """Nada e executado. Cada passo e apenas registrado como intencao.
    E o modo em que todo adaptador novo nasce e roda a primeira vez."""

    LEITURA = "leitura"
    """Executa apenas o que a lista de permissao autoriza."""


class Acao(str, Enum):
    NAVEGAR = "navegar"
    LER = "ler"
    PREENCHER = "preencher"
    CLICAR = "clicar"
    BAIXAR = "baixar"


# Termos que sugerem abertura de expediente ou ato que consome prazo.
# Segunda camada, heuristica. A protecao real e a lista de permissao vazia.
TERMOS_DE_RISCO = (
    "ciencia", "ciente", "dar-ciencia", "darciencia",
    "abrir-expediente", "abrirexpediente",
    "intimacao/abrir", "expediente/abrir",
    "peticionar", "protocolar", "assinar",
    "confirmar-leitura", "registrar-leitura",
    # Achado em campo em 22 de setembro de 2026, na propria pagina do processo
    # do e-SAJ de Sao Paulo: `button#botaoConfirmarRebebimentoIntimacao`, dentro
    # de `div#modalRecebimentoIntimacao`. O ato que dispara a ciencia nao mora
    # numa tela separada, mora a poucos nos dos dados que sao lidos. "rebebimento"
    # nao e erro de digitacao meu: e como o portal escreve, e por isso entra.
    "recebimentointimacao", "recebimento-intimacao",
    "rebebimentointimacao", "rebebimento-intimacao",
    "confirmarrecebimento", "confirmar-recebimento",
    "receberintimacao", "receber-intimacao",
    # Segunda classe de risco, descoberta na tela de segundo fator do eproc em
    # 21 de setembro de 2026: acoes que enfraquecem a seguranca da conta.
    # Nao consomem prazo, mas o dano e duradouro e silencioso.
    "desativar", "desabilitar",
    "liberardispositivo", "liberar-dispositivo",
    "cancelardispositivo", "cancelar-dispositivo",
    # Terceira classe, descoberta na tela "Alterar Cadastro" do eproc, onde a
    # autenticacao desemboca quando o portal exige atualizacao cadastral:
    # acoes que gravam alteracao no cadastro do advogado no tribunal.
    # "salvar" e "gravar" crus foram estreitados em 22 de setembro de 2026,
    # RATIFICADO pelo operador na mesma data ("voce esta autorizado a clicar na
    # opcao salvar documento"). A decisao e dele e fica registrada aqui, onde a
    # regra mora, e nao so no historico do repositorio. Eles
    # existiam para impedir GRAVAR ALTERACAO DE CADASTRO, e estavam impedindo
    # tambem `#salvarButton`, que na Pasta Digital do e-SAJ baixa um arquivo e
    # nao altera nada. Termo largo demais que barra leitura nao protege: ensina
    # a contorna-lo, que e pior que nao te-lo.
    #
    # As formas compostas cobrem o que o termo cru pretendia, e o alvo de
    # verdade, a tela de alteracao de cadastro, passou a ser barrado tambem
    # pelo endereco, que e onde o risco mora.
    "salvarcadastro", "salvar-cadastro", "gravarcadastro", "gravar-cadastro",
    "salvaralteracao", "salvar-alteracao", "gravaralteracao", "gravar-alteracao",
    "salvarsenha", "salvar-senha", "salvarperfil", "salvar-perfil",
    "salvarconfiguracao", "salvar-configuracao",
    "alterarcadastro", "alterar-cadastro", "pessoa-alterar",
    "excluir", "remover",
)

# Baixar documento foi proibido em qualquer modo ate 21 de setembro de 2026,
# quando o operador decidiu habilitar a copia dos autos. Continua NEGADO POR
# PADRAO: so passa quando quem monta a guarda liga `permitir_download`, e ainda
# assim apenas para alvos explicitamente liberados. A mudanca foi de "nunca"
# para "mediante autorizacao", nao para "livre".
ACOES_PROIBIDAS = frozenset()


@dataclass(frozen=True)
class Decisao:
    permitido: bool
    motivo: str
    acao: Acao
    alvo: str

    def exigir(self) -> None:
        if not self.permitido:
            raise NavegacaoBloqueada(self)


class NavegacaoBloqueada(PermissionError):
    def __init__(self, decisao: Decisao) -> None:
        super().__init__(
            f"Navegacao bloqueada ({decisao.acao.value} em {decisao.alvo!r}): "
            f"{decisao.motivo}"
        )
        self.decisao = decisao


@dataclass
class Permissao:
    """Uma tela conferida em campo e liberada para leitura."""

    padrao_url: str
    descricao: str
    conferido_em: str
    seletores_clicaveis: tuple[str, ...] = ()
    seletores_preenchiveis: tuple[str, ...] = ()

    @property
    def regex(self) -> re.Pattern:
        return re.compile(self.padrao_url)


@dataclass
class GuardaNavegacao:
    modo: Modo = Modo.ENSAIO
    permissoes: list[Permissao] = field(default_factory=list)
    registro: list[dict] = field(default_factory=list)
    permitir_download: bool = False

    # ---------------- avaliacao ----------------

    @staticmethod
    def _termo_de_risco(alvo: str) -> Optional[str]:
        normalizado = (alvo or "").lower().replace("_", "-")
        for termo in TERMOS_DE_RISCO:
            if termo in normalizado:
                return termo
        return None

    def _nomeado_na_tela(self, acao: "Acao", alvo: str, contexto: str) -> bool:
        """Se alguma permissao desta tela nomeia o alvo para esta acao.

        Conferencia estreita de proposito: so clicar e preencher, so por nome
        exato, e so em permissao que case com o endereco atual. Navegar, ler e
        baixar nao passam por aqui, porque nao sao atos dirigidos a um seletor
        que a tela tenha liberado.
        """
        if acao is Acao.CLICAR:
            escolher = lambda p: p.seletores_clicaveis  # noqa: E731
        elif acao is Acao.PREENCHER:
            escolher = lambda p: p.seletores_preenchiveis  # noqa: E731
        else:
            return False
        return any(alvo in escolher(p) for p in self._permissoes_para(contexto))

    def _permissoes_para(self, url: str) -> list[Permissao]:
        """TODAS as permissoes que casam, nao apenas a primeira.

        Permissoes sao concessoes que SOMAM. Devolver so a primeira fazia uma
        permissao ampla esconder as especificas: a de origem, usada para os
        documentos, casava com o portal inteiro e nao liberava clique nenhum,
        entao barrava o botao de copia integral que outra permissao liberava.
        """
        return [p for p in self.permissoes if p.regex.search(url or "")]

    def _permissao_para(self, url: str) -> Optional[Permissao]:
        casadas = self._permissoes_para(url)
        return casadas[0] if casadas else None

    def avaliar(self, acao: Acao, alvo: str, *, url: str = "") -> Decisao:
        """Decide sem executar. Toda passagem pelo adaptador vem por aqui."""
        contexto = url or alvo

        if acao in ACOES_PROIBIDAS:
            return self._registrar(Decisao(
                False,
                f"A acao {acao.value!r} nao existe nesta versao. "
                f"Habilita-la exige decisao expressa do operador.",
                acao, alvo,
            ))

        if acao is Acao.BAIXAR and not self.permitir_download:
            return self._registrar(Decisao(
                False,
                "Download nao autorizado nesta operacao. Baixar autos e ato de "
                "outra natureza e so ocorre em comando que o pede explicitamente.",
                acao, alvo,
            ))

        # Duas situacoes diferentes, tratadas como uma so ate 02/10/2026.
        #
        #   (1) o termo de risco esta no ALVO. Quem clica em "salvar cadastro"
        #       ou navega para "abrir expediente" pratica o ato. Bloqueio
        #       absoluto, nao contornavel por configuracao nem por permissao.
        #
        #   (2) o termo de risco esta so no ENDERECO DA TELA. A tela e perigosa,
        #       o alvo nao. Visto em campo no TRF2 em 02/10/2026: a autenticacao
        #       desemboca em `acao=pessoa_alterar`, e nessa MESMA pagina convivem
        #       dois formularios distintos, `frmPessoaAlteracao` (o cadastro do
        #       advogado) e `formPesquisaRapida` (a barra de busca de processo).
        #       Bloquear a pagina inteira impedia consultar processo no TRF2 por
        #       causa de um formulario em que a consulta nunca encosta.
        #
        # No caso (2) o bloqueio continua sendo o padrao, e so cede para seletor
        # que uma permissao daquela tela tenha NOMEADO expressamente.
        #
        # O que protege o botao Salvar do cadastro, entao, e UMA camada, e nao
        # duas: nenhuma permissao o nomeia. Ele NAO e pego pela lista de termos,
        # porque o seu seletor real e `button[name=btnSalvar]`, e "salvar" cru
        # foi deliberadamente tirado da lista em 22/09/2026 por pegar botao
        # inocente demais; o que ficou foi `salvarcadastro`, `salvar-cadastro` e
        # afins, que nao casam com `btnsalvar`. Dizer "duas camadas" aqui seria
        # confortavel e falso. A camada que resta e a principal e a que o projeto
        # inteiro assume: a lista de permissao nasce vazia e so recebe o que o
        # adaptador nomeia, um seletor por vez.
        termo_no_alvo = self._termo_de_risco(alvo)
        if termo_no_alvo is not None:
            return self._registrar(Decisao(
                False,
                f"Termo de risco {termo_no_alvo!r} no alvo. Abrir expediente dispara a "
                f"ciencia e inicia o prazo (lei nº. 11.419/06, artigo 5º, §3º). "
                f"Bloqueio nao contornavel por configuracao.",
                acao, alvo,
            ))

        termo_na_tela = self._termo_de_risco(url)
        if termo_na_tela is not None and not self._nomeado_na_tela(acao, alvo, contexto):
            return self._registrar(Decisao(
                False,
                f"Termo de risco {termo_na_tela!r} no endereco da tela. Nesta tela so "
                f"agem os seletores que uma permissao dela nomeia expressamente, e "
                f"{alvo!r} nao e um deles.",
                acao, alvo,
            ))

        if acao is Acao.BAIXAR:
            # Mesmo autorizado, o download obedece a lista de permissao: o alvo
            # precisa estar liberado na tela, como qualquer outra acao.
            permissao_download = self._permissao_para(contexto)
            if permissao_download is None:
                return self._registrar(Decisao(
                    False, "Endereco do documento fora da lista de permissao.", acao, alvo,
                ))
            return self._registrar(Decisao(
                True, f"Download autorizado nesta operacao ({permissao_download.descricao}).",
                acao, alvo,
            ))

        if acao is Acao.LER:
            return self._registrar(Decisao(
                True, "Extrair texto nao pratica ato no portal.", acao, alvo
            ))

        casadas = self._permissoes_para(contexto)
        permissao = casadas[0] if casadas else None
        if permissao is None:
            return self._registrar(Decisao(
                False,
                f"Endereco fora da lista de permissao. O padrao e NEGAR: uma tela "
                f"so entra na lista depois de conferida em campo. Nenhuma tela foi "
                f"conferida ainda."
                if not self.permissoes else
                f"Endereco fora da lista de permissao ({len(self.permissoes)} tela(s) "
                f"conferida(s) nao casam com {contexto!r}).",
                acao, alvo,
            ))

        if acao is Acao.NAVEGAR:
            return self._registrar(Decisao(
                True, f"Tela conferida em {permissao.conferido_em}: {permissao.descricao}.",
                acao, alvo,
            ))

        liberados: list[str] = []
        for candidata in casadas:
            seletores = (
                candidata.seletores_clicaveis if acao is Acao.CLICAR
                else candidata.seletores_preenchiveis
            )
            if alvo in seletores:
                return self._registrar(Decisao(
                    True, f"Seletor liberado nesta tela ({candidata.descricao}).", acao, alvo
                ))
            liberados.extend(seletores)
        return self._registrar(Decisao(
            False,
            f"Seletor nao liberado para {acao.value} nesta tela. Liberados: "
            f"{liberados or 'nenhum'}.",
            acao, alvo,
        ))

    def _registrar(self, decisao: Decisao) -> Decisao:
        self.registro.append({
            "acao": decisao.acao.value,
            "alvo": decisao.alvo,
            "permitido": decisao.permitido,
            "motivo": decisao.motivo,
            "executado": decisao.permitido and self.modo is Modo.LEITURA,
        })
        return decisao

    # ---------------- execucao ----------------

    def pode_executar(self, acao: Acao, alvo: str, *, url: str = "") -> bool:
        """Em ensaio devolve sempre False: registra a intencao e nao age.

        O adaptador nasce em ensaio e roda assim a primeira vez. O advogado le
        o relato do que ele FARIA antes de o codigo ganhar permissao de agir.
        """
        decisao = self.avaliar(acao, alvo, url=url)
        if not decisao.permitido:
            decisao.exigir()
        return self.modo is Modo.LEITURA

    def relato(self) -> list[str]:
        linhas = []
        for r in self.registro:
            if r["executado"]:
                marca = "EXECUTOU  "
            elif r["permitido"]:
                marca = "FARIA     "
            else:
                marca = "BLOQUEOU  "
            linhas.append(f"{marca} {r['acao']:10s} {r['alvo'][:52]:52s} {r['motivo'][:70]}")
        return linhas
