"""Cofre de credenciais da Fase 2.

Guarda senha de portal e semente de segundo fator no Gerenciador de
Credenciais do Windows, cifrado pelo proprio sistema operacional, por usuario.
Em macOS usa o Chaveiro, em Linux o Secret Service.

REGRA QUE GOVERNA ESTE MODULO: o segredo nunca chega ao modelo.

O adaptador le do cofre no instante da chamada e usa direto contra o portal.
Nenhuma ferramenta do servidor devolve senha, semente ou codigo de segundo
fator, e nenhuma delas aparece em log, em mensagem de erro ou em auditoria.
Por isso os acessores de leitura levam sublinhado no nome: sao de uso interno
dos adaptadores, e a interface publica so responde se a credencial EXISTE.

Por que senha e semente ficam em entradas separadas: juntas, equivalem a conta
inteira. O segundo fator deixa de ser segundo fator quando viaja ao lado da
senha, que foi exatamente o problema da planilha que originou o projeto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol

SERVICO_LOGIN = "justica-mcp:login"
SERVICO_SENHA = "justica-mcp:senha"
SERVICO_SEMENTE = "justica-mcp:semente-segundo-fator"

# Base32 conforme a RFC 4648, que e o alfabeto dos autenticadores.
_BASE32 = re.compile(r"^[A-Z2-7]+=*$")


class CofreIndisponivel(RuntimeError):
    """O armazenamento do sistema nao respondeu.

    Sem este tratamento, a falha sobe como traceback bruto, que nao diz nada a
    quem opera o servidor. A causa costuma ser trivial e a mensagem precisa
    apontar para ela.
    """

    def __init__(self, causa: Exception) -> None:
        super().__init__(
            f"O cofre de credenciais do sistema nao respondeu ({type(causa).__name__}). "
            f"No Windows, verifique se o Gerenciador de Credenciais esta ativo para "
            f"este usuario. Em Linux, e preciso um servico de chaveiro em execucao; "
            f"maquina sem ambiente grafico normalmente nao tem."
        )
        self.causa = causa


class CredencialAusente(LookupError):
    """Pedida uma credencial que nao esta no cofre."""

    def __init__(self, identidade: "Identidade", tipo: str) -> None:
        super().__init__(
            f"{tipo} de {identidade.rotulo} nao esta no cofre. Grave com: "
            f"justica-credenciais guardar --tribunal {identidade.tribunal} "
            f"--sistema {identidade.sistema}"
        )


class SementeInvalida(ValueError):
    pass


@dataclass(frozen=True)
class Identidade:
    """Par tribunal e sistema. Uma credencial por par."""

    tribunal: str
    sistema: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tribunal", self.tribunal.strip().upper())
        object.__setattr__(self, "sistema", self.sistema.strip().lower())

    @property
    def chave(self) -> str:
        return f"{self.tribunal}:{self.sistema}"

    @property
    def rotulo(self) -> str:
        return f"{self.tribunal} / {self.sistema}"


class Backend(Protocol):
    """Interface do armazenamento. Permite testar sem cofre de verdade."""

    def get_password(self, service: str, username: str) -> Optional[str]: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def normalizar_semente(bruta: str) -> str:
    """Aceita a semente no formato em que o autenticador a exibe.

    O QR Code do portal costuma ser transcrito em grupos de quatro separados
    por espaco, com 32 caracteres uteis. Espacos, hifens e caixa sao ruido de
    transcricao, nao conteudo.
    """
    limpa = re.sub(r"[\s-]", "", bruta or "").upper()
    if not limpa:
        raise SementeInvalida("Semente vazia.")
    if not _BASE32.match(limpa):
        raise SementeInvalida(
            "Semente fora do alfabeto base32 (A a Z e 2 a 7). Confira a "
            "transcricao: caracteres como 0, 1 e 8 nao existem em base32 e "
            "costumam ser confusao com O, I e B."
        )
    if len(limpa.rstrip("=")) < 16:
        raise SementeInvalida(
            f"Semente com {len(limpa)} caracteres, curta demais para um "
            f"autenticador (o padrao dos portais tem 32)."
        )
    return limpa


class Cofre:
    def __init__(self, backend: Optional[Backend] = None) -> None:
        if backend is None:
            import keyring

            backend = keyring.get_keyring()
        self._backend = backend

    # ---------------- escrita ----------------

    def _ler(self, servico: str, chave: str) -> Optional[str]:
        try:
            return self._backend.get_password(servico, chave)
        except Exception as exc:
            raise CofreIndisponivel(exc) from exc

    def _gravar(self, servico: str, chave: str, valor: str) -> None:
        try:
            self._backend.set_password(servico, chave, valor)
        except Exception as exc:
            raise CofreIndisponivel(exc) from exc

    def disponivel(self) -> bool:
        """Sonda barata, para o comando avisar antes de tentar gravar."""
        try:
            self._backend.get_password(SERVICO_SENHA, "__sonda__")
            return True
        except Exception:
            return False

    def guardar_login(self, identidade: Identidade, login: str) -> None:
        """O login varia por cadastro: numero de inscricao em um portal,
        cadastro de pessoa fisica em outro. Fica no cofre junto do resto porque
        e dado pessoal, e nao aparece em nenhuma resposta de ferramenta."""
        if not (login or "").strip():
            raise ValueError("Login vazio nao e gravado.")
        self._gravar(SERVICO_LOGIN, identidade.chave, login.strip())

    def guardar_senha(self, identidade: Identidade, senha: str) -> None:
        if not (senha or "").strip():
            raise ValueError("Senha vazia nao e gravada.")
        self._gravar(SERVICO_SENHA, identidade.chave, senha)

    def guardar_semente(self, identidade: Identidade, semente: str) -> None:
        self._gravar(SERVICO_SEMENTE, identidade.chave, normalizar_semente(semente))

    def remover(self, identidade: Identidade) -> list[str]:
        removidos = []
        for servico, nome in (
            (SERVICO_LOGIN, "login"),
            (SERVICO_SENHA, "senha"),
            (SERVICO_SEMENTE, "semente"),
        ):
            try:
                if self._backend.get_password(servico, identidade.chave) is not None:
                    self._backend.delete_password(servico, identidade.chave)
                    removidos.append(nome)
            except Exception:
                continue
        return removidos

    # ---------------- consulta sem vazamento ----------------

    def tem_login(self, identidade: Identidade) -> bool:
        return self._ler(SERVICO_LOGIN, identidade.chave) is not None

    def tem_senha(self, identidade: Identidade) -> bool:
        return self._ler(SERVICO_SENHA, identidade.chave) is not None

    def tem_semente(self, identidade: Identidade) -> bool:
        return self._ler(SERVICO_SEMENTE, identidade.chave) is not None

    def situacao(self, identidade: Identidade) -> dict[str, object]:
        """Resposta segura para ferramenta e relatorio: presenca, nunca valor."""
        return {
            "identidade": identidade.rotulo,
            "login_guardado": self.tem_login(identidade),
            "senha_guardada": self.tem_senha(identidade),
            "semente_guardada": self.tem_semente(identidade),
            # Prontidao exige login e senha. O segundo fator fica a parte
            # porque nem todo portal o usa: esta confirmado para o eproc, que
            # o exige de usuario externo desde abril de 2024, mas para os
            # demais nao ha confirmacao. Exigir de todos marcaria como
            # incompleta uma credencial que funciona.
            "pronta_para_uso": self.tem_login(identidade) and self.tem_senha(identidade),
        }

    # ---------------- leitura interna ----------------
    # Sublinhado de proposito: uso exclusivo dos adaptadores, no instante da
    # chamada ao portal. O retorno destes metodos NUNCA pode entrar em resposta
    # de ferramenta, log, auditoria ou mensagem de erro.

    def _login(self, identidade: Identidade) -> str:
        valor = self._ler(SERVICO_LOGIN, identidade.chave)
        if valor is None:
            raise CredencialAusente(identidade, "Login")
        return valor

    def _senha(self, identidade: Identidade) -> str:
        valor = self._ler(SERVICO_SENHA, identidade.chave)
        if valor is None:
            raise CredencialAusente(identidade, "Senha")
        return valor

    def _codigo_segundo_fator(self, identidade: Identidade) -> str:
        """Gera o codigo de seis digitos a partir da semente guardada.

        O portal exige segundo fator para usuario externo. Com a semente no
        cofre o servidor gera o codigo sozinho, sem interromper o advogado.
        Isso AUMENTA a responsabilidade sobre o cofre, nao diminui: quem tiver
        a semente e a senha tem a conta inteira.
        """
        import pyotp

        semente = self._ler(SERVICO_SEMENTE, identidade.chave)
        if semente is None:
            raise CredencialAusente(identidade, "Semente de segundo fator")
        return pyotp.TOTP(semente).now()

    def __repr__(self) -> str:  # evita que um repr descuidado exponha o backend
        return f"<Cofre backend={type(self._backend).__name__}>"
