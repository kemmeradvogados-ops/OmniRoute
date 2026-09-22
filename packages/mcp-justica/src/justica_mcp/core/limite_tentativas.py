"""Teto de tentativas de autenticacao por janela de tempo.

Ate aqui a protecao contra bloqueio de conta era a confirmacao na linha de
comando: um humano digitava `--confirmo-tentativa-unica` a cada execucao, e
tentar de novo era decisao dele.

Expor a autenticacao como ferramenta do servidor quebra essa premissa. Um
agente que receba erro e tente de novo, num laco, queima as tentativas da conta
do advogado em segundos, sem ninguem no meio para perceber. A confirmacao
humana deixa de existir justamente onde ela mais importava.

Daí este teto, que nao depende de ninguem lembrar: as tentativas ficam na
tabela de auditoria, que ja e gravada, e o limite e conferido antes de comecar.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .estado import Estado

# O que consome tentativa e a credencial CHEGAR ao portal, venha do comando
# `autenticar` ou do `entrar`. Os dois enviam senha de verdade, e o bloqueio da
# conta nao distingue por qual comando ela foi enviada.
ACOES_TENTATIVA = frozenset({"login_etapa_credencial", "login_tentativa_unica"})

# Bloqueio de conta vem de falhas CONSECUTIVAS, nao de login que deu certo.
# Contar tentativas bem sucedidas barrava o advogado por trabalhar, e nao por
# risco: seis autenticacoes bem sucedidas numa hora nao ameacam conta nenhuma.
# Um sucesso zera o contador, que e como as politicas de bloqueio funcionam.
ACAO_SUCESSO = "login_sucesso"

# Mantido porque e o nome usado nos registros do fluxo completo.
ACAO_TENTATIVA = "login_etapa_credencial"

# Numero conservador de proposito. Um advogado autentica poucas vezes por hora;
# um laco descontrolado passa disso em segundos.
TETO_PADRAO = 6
JANELA_PADRAO_MINUTOS = 60


class TetoDeTentativasAtingido(RuntimeError):
    def __init__(self, usadas: int, teto: int, janela: int, liberacao: Optional[str]) -> None:
        super().__init__(
            f"Teto de tentativas de autenticacao atingido: {usadas} de {teto} "
            f"nos ultimos {janela} minutos"
            + (f", proxima liberacao por volta de {liberacao}" if liberacao else "")
            + ". O limite existe para o acesso do advogado nao ser bloqueado pelo "
            "portal apos tentativas seguidas. Se as tentativas falharam por "
            "credencial errada, corrija o cofre antes de insistir."
        )
        self.usadas, self.teto = usadas, teto


@dataclass
class LimiteTentativas:
    estado: Estado
    teto: int = TETO_PADRAO
    janela_minutos: int = JANELA_PADRAO_MINUTOS

    @classmethod
    def do_ambiente(cls, estado: Estado) -> "LimiteTentativas":
        def inteiro(nome: str, padrao: int) -> int:
            try:
                valor = int(os.environ.get(nome, padrao))
            except ValueError:
                return padrao
            return valor if valor > 0 else padrao

        return cls(
            estado=estado,
            teto=inteiro("JUSTICA_TETO_TENTATIVAS", TETO_PADRAO),
            janela_minutos=inteiro("JUSTICA_JANELA_TENTATIVAS_MIN", JANELA_PADRAO_MINUTOS),
        )

    def _tentativas_na_janela(self) -> list[str]:
        """Tentativas desde o ultimo sucesso, dentro da janela.

        A varredura e pela ORDEM dos registros, e nao por comparacao de
        horario: a auditoria grava com precisao de segundo, e sucesso e
        tentativa gravados no mesmo segundo empatam. Com empate, comparar
        horarios contaria como pendente a tentativa que o sucesso encerrou.
        """
        corte = datetime.now(timezone.utc) - timedelta(minutes=self.janela_minutos)
        # A lista vem da mais recente para a mais antiga, entao a varredura
        # caminha para tras no tempo e para no primeiro sucesso que encontrar.
        pendentes: list[str] = []
        for r in self.estado.auditoria_recente(limite=200):
            quando = datetime.fromisoformat(r["ocorrido_em"])
            if quando < corte:
                break
            if r["acao"] == ACAO_SUCESSO:
                break
            # O limite protege a conta como um todo, entao conta tentativas de
            # qualquer tribunal: o bloqueio costuma ser por credencial, nao por
            # sistema, e varias identidades podem compartilhar o mesmo cadastro.
            if r["acao"] in ACOES_TENTATIVA:
                pendentes.append(r["ocorrido_em"])
        return pendentes

    def situacao(self) -> dict[str, object]:
        usadas = self._tentativas_na_janela()
        return {
            "tentativas_na_janela": len(usadas),
            "teto": self.teto,
            "janela_minutos": self.janela_minutos,
            "restantes": max(self.teto - len(usadas), 0),
            "mais_antiga_na_janela": min(usadas) if usadas else None,
        }

    def exigir_folga(self) -> None:
        """Conferido ANTES de abrir o navegador, para nem chegar ao portal."""
        usadas = self._tentativas_na_janela()
        if len(usadas) < self.teto:
            return
        liberacao = None
        if usadas:
            quando = datetime.fromisoformat(min(usadas)) + timedelta(minutes=self.janela_minutos)
            liberacao = quando.astimezone().strftime("%H:%M")
        raise TetoDeTentativasAtingido(len(usadas), self.teto, self.janela_minutos, liberacao)
