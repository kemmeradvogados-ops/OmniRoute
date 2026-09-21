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
    # Segunda classe de risco, descoberta na tela de segundo fator do eproc em
    # 21 de setembro de 2026: acoes que enfraquecem a seguranca da conta.
    # Nao consomem prazo, mas o dano e duradouro e silencioso.
    "desativar", "desabilitar",
    "liberardispositivo", "liberar-dispositivo",
    "cancelardispositivo", "cancelar-dispositivo",
    # Terceira classe, descoberta na tela "Alterar Cadastro" do eproc, onde a
    # autenticacao desemboca quando o portal exige atualizacao cadastral:
    # acoes que gravam alteracao no cadastro do advogado no tribunal.
    "salvar", "gravar", "excluir", "remover",
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

    def _permissao_para(self, url: str) -> Optional[Permissao]:
        for p in self.permissoes:
            if p.regex.search(url or ""):
                return p
        return None

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

        termo = self._termo_de_risco(alvo) or self._termo_de_risco(url)
        if termo is not None:
            return self._registrar(Decisao(
                False,
                f"Termo de risco {termo!r} no alvo. Abrir expediente dispara a "
                f"ciencia e inicia o prazo (lei nº. 11.419/06, artigo 5º, §3º). "
                f"Bloqueio nao contornavel por configuracao.",
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

        permissao = self._permissao_para(contexto)
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

        seletores = (
            permissao.seletores_clicaveis if acao is Acao.CLICAR
            else permissao.seletores_preenchiveis
        )
        if alvo in seletores:
            return self._registrar(Decisao(
                True, f"Seletor liberado nesta tela ({permissao.descricao}).", acao, alvo
            ))
        return self._registrar(Decisao(
            False,
            f"Seletor nao liberado para {acao.value} nesta tela. Liberados: "
            f"{list(seletores) or 'nenhum'}.",
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
