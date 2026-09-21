"""Comando `justica-credenciais`: carrega o cofre sem intermediario.

O advogado digita a senha e a semente direto no terminal da propria maquina.
O valor vai do teclado para o Gerenciador de Credenciais do sistema, e nao
passa por chat, por arquivo, nem por log.

    justica-credenciais listar
    justica-credenciais guardar --tribunal TJRJ --sistema eproc
    justica-credenciais testar  --tribunal TJRJ --sistema eproc
    justica-credenciais remover --tribunal TJRJ --sistema eproc
"""

from __future__ import annotations

import argparse
import getpass
import sys

from .core.cofre import (
    Cofre, CofreIndisponivel, CredencialAusente, Identidade, SementeInvalida,
)
from .core.tribunais import TRIBUNAIS

LARGURA = 66


def _pares_esperados() -> list[Identidade]:
    """Pares tribunal e sistema para os quais a banca declarou ter credencial."""
    return [
        Identidade(t.codigo, s.value)
        for t in TRIBUNAIS.values()
        for s in t.credencial_disponivel
    ]


def _resolver(tribunal: str, sistema: str) -> Identidade:
    identidade = Identidade(tribunal, sistema)
    validos = {i.chave for i in _pares_esperados()}
    if identidade.chave not in validos:
        raise SystemExit(
            f"Par {identidade.rotulo} nao consta do escopo da banca.\n"
            f"Pares previstos: " + ", ".join(sorted(validos))
        )
    return identidade


def cmd_listar(cofre: Cofre) -> int:
    print("=" * LARGURA)
    print("CREDENCIAIS NO COFRE".center(LARGURA))
    print("=" * LARGURA)
    print("O cofre guarda no Gerenciador de Credenciais do sistema, cifrado.")
    print("Esta listagem mostra apenas SE existe, jamais o valor.\n")
    faltando = 0
    for identidade in _pares_esperados():
        s = cofre.situacao(identidade)
        marca = "[completa]" if s["pronta_para_uso"] else "[  falta ]"
        if not s["pronta_para_uso"]:
            faltando += 1
        print(
            f"  {marca} {identidade.rotulo:20s} "
            f"senha: {'sim' if s['senha_guardada'] else 'NAO'}   "
            f"segundo fator: {'sim' if s['semente_guardada'] else 'NAO'}"
        )
    print()
    if faltando:
        print(f"  {faltando} par(es) incompleto(s). Use `guardar` para preencher.")
    else:
        print("  Todos os pares previstos estao completos.")
    return 0


def cmd_guardar(cofre: Cofre, tribunal: str, sistema: str, so_senha: bool, so_semente: bool) -> int:
    identidade = _resolver(tribunal, sistema)
    print(f"\nGravando credencial de {identidade.rotulo}.")
    print("O que voce digitar NAO aparece na tela e NAO fica em arquivo.\n")

    if not so_semente:
        senha = getpass.getpass("  Senha do portal: ")
        confere = getpass.getpass("  Repita a senha:  ")
        if senha != confere:
            print("\n  As duas digitacoes diferem. Nada foi gravado.")
            return 1
        try:
            cofre.guardar_senha(identidade, senha)
        except ValueError as exc:
            print(f"\n  {exc}")
            return 1
        print("  Senha gravada.")

    if not so_senha:
        print("\n  Semente do segundo fator: e o codigo longo do QR Code, com")
        print("  32 caracteres, e nao o codigo de 6 digitos do aplicativo.")
        print("  Pode colar com espacos; eles sao ignorados.")
        semente = getpass.getpass("  Semente: ")
        try:
            cofre.guardar_semente(identidade, semente)
        except SementeInvalida as exc:
            print(f"\n  {exc}\n  Nada foi gravado para o segundo fator.")
            return 1
        print("  Semente gravada.")
        codigo = cofre._codigo_segundo_fator(identidade)
        print(f"\n  Confira agora: o codigo gerado e {codigo}.")
        print("  Ele deve bater com o do seu aplicativo autenticador neste")
        print("  momento. Se nao bater, a semente esta errada: rode de novo")
        print("  com --so-semente.")
    return 0


def cmd_testar(cofre: Cofre, tribunal: str, sistema: str) -> int:
    identidade = _resolver(tribunal, sistema)
    situacao = cofre.situacao(identidade)
    print(f"\n{identidade.rotulo}")
    print(f"  senha guardada        : {'sim' if situacao['senha_guardada'] else 'NAO'}")
    print(f"  semente guardada      : {'sim' if situacao['semente_guardada'] else 'NAO'}")
    if not situacao["semente_guardada"]:
        print("\n  Sem semente nao da para gerar codigo.")
        return 1
    try:
        codigo = cofre._codigo_segundo_fator(identidade)
    except CredencialAusente as exc:
        print(f"\n  {exc}")
        return 1
    print(f"\n  Codigo agora: {codigo}")
    print("  Compare com o aplicativo autenticador. Se bater, a semente esta")
    print("  correta e o servidor conseguira autenticar sozinho.")
    return 0


def cmd_remover(cofre: Cofre, tribunal: str, sistema: str) -> int:
    identidade = _resolver(tribunal, sistema)
    resposta = input(f"Remover a credencial de {identidade.rotulo}? (digite SIM) ")
    if resposta.strip() != "SIM":
        print("Nada foi removido.")
        return 1
    removidos = cofre.remover(identidade)
    print(f"Removido: {', '.join(removidos) if removidos else 'nada havia gravado'}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="justica-credenciais",
        description="Carrega o cofre de credenciais do justica-mcp.",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("listar", help="mostra o que esta guardado, nunca o valor")

    g = sub.add_parser("guardar", help="grava senha e semente de segundo fator")
    g.add_argument("--tribunal", required=True)
    g.add_argument("--sistema", required=True)
    g.add_argument("--so-senha", action="store_true", help="grava apenas a senha")
    g.add_argument("--so-semente", action="store_true", help="grava apenas a semente")

    t = sub.add_parser("testar", help="gera um codigo para conferir com o aplicativo")
    t.add_argument("--tribunal", required=True)
    t.add_argument("--sistema", required=True)

    r = sub.add_parser("remover", help="apaga a credencial do cofre")
    r.add_argument("--tribunal", required=True)
    r.add_argument("--sistema", required=True)

    args = p.parse_args(argv)
    try:
        cofre = Cofre()
    except CofreIndisponivel as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Nao foi possivel abrir o cofre do sistema: {type(exc).__name__}.\n"
            f"No Windows isso costuma indicar que o Gerenciador de Credenciais "
            f"esta indisponivel para este usuario.",
            file=sys.stderr,
        )
        return 2

    if not cofre.disponivel():
        print(
            "O cofre de credenciais do sistema nao esta acessivel.\n"
            "No Windows: confirme que o servico Gerenciador de Credenciais esta\n"
            "em execucao e que voce entrou com a conta de sempre.\n"
            "Em Linux sem ambiente grafico nao ha chaveiro, e este comando nao roda.",
            file=sys.stderr,
        )
        return 2

    if args.comando == "listar":
        return cmd_listar(cofre)
    if args.comando == "guardar":
        return cmd_guardar(cofre, args.tribunal, args.sistema, args.so_senha, args.so_semente)
    if args.comando == "testar":
        return cmd_testar(cofre, args.tribunal, args.sistema)
    if args.comando == "remover":
        return cmd_remover(cofre, args.tribunal, args.sistema)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
