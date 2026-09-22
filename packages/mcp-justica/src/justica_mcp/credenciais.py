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
from pathlib import Path

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


def cmd_importar(cofre: Cofre, planilha: str, simular: bool) -> int:
    """Le a planilha da banca e carrega o cofre, sem copiar e colar segredo."""
    from .planilha import PlanilhaInvalida, importar

    caminho = Path(planilha).expanduser()
    print("=" * LARGURA)
    print(("SIMULACAO DE IMPORTACAO" if simular else "IMPORTACAO DA PLANILHA").center(LARGURA))
    print("=" * LARGURA)
    print(f"Arquivo: {caminho}")
    print("Os valores vao da celula direto para o cofre do sistema.")
    print("Nada e impresso na tela e nada passa por arquivo intermediario.\n")

    try:
        resultados = importar(caminho, cofre, simular=simular)
    except PlanilhaInvalida as exc:
        print(f"  {exc}")
        return 1

    for r in resultados:
        if r.identidade is None:
            print(f"  [ignorada] linha {r.linha}: {r.rotulo_planilha}")
            print(f"             {r.observacao}")
            continue
        marca = "[completa]" if r.completa else "[ parcial]"
        campos = ", ".join(
            nome for nome, ok in
            (("login", r.login), ("senha", r.senha), ("segundo fator", r.semente)) if ok
        ) or "nada"
        verbo = "importaria" if simular else "importado"
        print(f"  {marca} {r.identidade.rotulo:16s} {verbo}: {campos}")
        if r.observacao:
            print(f"             {r.observacao}")

    aproveitadas = [r for r in resultados if r.identidade is not None]
    print(f"\n  {len(aproveitadas)} par(es) processado(s).")
    if simular:
        print("  Simulacao: NADA foi gravado. Repita sem --simular para valer.")
    else:
        print("\n  Confira com: justica-credenciais listar")
        print("  Depois de conferir, APAGUE a planilha ou guarde-a fora desta")
        print("  maquina: o cofre passa a ser a fonte, e manter senha e semente")
        print("  juntas num arquivo anula o segundo fator.")
    return 0


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
            f"  {marca} {identidade.rotulo:16s} "
            f"login: {'sim' if s['login_guardado'] else 'NAO'}  "
            f"senha: {'sim' if s['senha_guardada'] else 'NAO'}  "
            f"segundo fator: {'sim' if s['semente_guardada'] else 'NAO'}"
        )
    print()
    if faltando:
        print(f"  {faltando} par(es) incompleto(s). Use `guardar` para preencher.")
    else:
        print("  Todos os pares previstos estao completos.")
    return 0


def pedir_em_janela(rotulo: str, confirmar: bool = True, _construtor=None,
                    mascarar: bool = True) -> "str | None":
    """Pede um segredo numa janelinha, com os pontinhos e com Ctrl+V.

    Nasceu de um impedimento real, em 22 de setembro de 2026: o operador guarda
    as senhas num cofre de senhas e precisa COLAR. O prompt de terminal esconde
    o que se digita, o que e certo, mas em varios terminais do Windows ele nao
    aceita colar, e ai a senha simplesmente nao entra. Digitar a mao uma senha
    longa, as cegas, e o caminho mais curto para grava-la errada.

    A janela nao afrouxa nada: o campo continua mascarado, o valor nao passa
    por arquivo nem por variavel de ambiente, nao entra no historico do
    terminal e vai direto para o cofre do sistema.
    """
    construtor = _construtor
    if construtor is None:
        try:
            import tkinter
            from tkinter import simpledialog
        except Exception:
            return None

        def construtor(titulo, mensagem):
            raiz = tkinter.Tk()
            raiz.withdraw()
            raiz.attributes("-topmost", True)
            try:
                return simpledialog.askstring(
                    titulo, mensagem, show="*" if mascarar else "", parent=raiz)
            finally:
                raiz.destroy()

    primeira = construtor("justica-mcp", f"{rotulo}:")
    if primeira is None:
        return None
    if not confirmar:
        return primeira
    segunda = construtor("justica-mcp", f"Repita {rotulo.lower()}:")
    if segunda is None:
        return None
    if primeira != segunda:
        return ""
    return primeira


def pedir_segredo(rotulo: str, janela: bool, confirmar: bool = True,
                  mascarar: bool = True) -> "str | None":
    """Pede um segredo pela janela, quando pedida, ou pelo terminal."""
    if janela:
        valor = pedir_em_janela(rotulo, confirmar=confirmar, mascarar=mascarar)
        if valor is None:
            print("\n  Nao consegui abrir a janela (ou voce cancelou).")
            print("  Repita sem --janela para digitar no terminal.")
            return None
        if valor == "" and confirmar:
            print("\n  As duas digitacoes diferem. Nada foi gravado.")
            return None
        return valor

    if not mascarar:
        return input(f"  {rotulo}: ").strip()
    primeira = getpass.getpass(f"  {rotulo}: ")
    if not confirmar:
        return primeira
    segunda = getpass.getpass("  Repita:  ")
    if primeira != segunda:
        print("\n  As duas digitacoes diferem. Nada foi gravado.")
        return None
    return primeira


def motivo_para_recusar_login(login: str) -> str:
    """Diz por que este texto nao pode ser um login, ou devolve vazio.

    Login de portal e inscricao, cadastro de pessoa fisica ou matricula: nao
    tem espaco, nem barra, nem tracos duplos. Um texto assim no prompt e quase
    sempre um comando colado no lugar errado, e grava-lo corrompe o acesso em
    silencio ate a proxima tentativa de login, que ja sai gasta.
    """
    if " " in login:
        return "login de portal nao tem espaco."
    if "--" in login:
        return "isto parece uma linha de comando, nao um login."
    if "\\" in login or "/" in login:
        return "isto parece um caminho de arquivo, nao um login."
    if len(login) > 60:
        return "isto e longo demais para uma inscricao ou cadastro."
    return ""


def cmd_guardar(cofre: Cofre, tribunal: str, sistema: str, so_senha: bool,
                so_semente: bool, janela: bool = False, so_login: bool = False) -> int:
    """Grava as tres pecas da credencial, ou so a que for pedida.

    Cada `--so-alguma-coisa` grava EXATAMENTE aquilo, e nada mais. A regra
    parece obvia e nao era: ate 22/09/2026 o `--so-senha` perguntava tambem o
    login, o operador colou ali a linha de comando seguinte, e o login do
    portal ficou corrompido em silencio. Consertar um pedaco nao pode obrigar
    a redigitar os outros, porque cada redigitacao e uma chance de errar.
    """
    identidade = _resolver(tribunal, sistema)
    escolheu = so_login or so_senha or so_semente
    pedir_login = so_login or not escolheu
    pedir_senha = so_senha or not escolheu
    pedir_semente = so_semente or not escolheu

    print(f"\nGravando credencial de {identidade.rotulo}.")
    print("O que voce digitar NAO aparece na tela e NAO fica em arquivo.\n")

    if pedir_login or pedir_senha:
        if pedir_login:
            # Com `--janela`, o login tambem sai do terminal. Nao e conforto: em
            # 22/09/2026 o operador colou DUAS vezes a linha de comando seguinte
            # dentro do prompt de login, porque quem cola um comando enquanto um
            # prompt espera ve o texto ser engolido como resposta. Prompt aberto
            # no terminal e uma armadilha para quem trabalha colando comandos.
            if janela:
                print("  Abrindo a janela para o login.")
            login = (pedir_segredo(
                "Login (inscricao, cadastro de pessoa fisica, matricula)",
                janela, confirmar=False, mascarar=False) or "").strip()
            if login:
                recusa = motivo_para_recusar_login(login)
                if recusa:
                    print(f"\n  Login NAO gravado: {recusa}")
                    print("  Nada foi alterado. Repita o comando.")
                    return 1
                cofre.guardar_login(identidade, login)
                print("  Login gravado.")
        if not pedir_senha:
            return 0
        if janela:
            print("  Abrindo a janela para a senha. Ela aceita colar (Ctrl+V).")
        senha = pedir_segredo("Senha do portal", janela)
        if senha is None:
            return 1
        try:
            cofre.guardar_senha(identidade, senha)
        except ValueError as exc:
            print(f"\n  {exc}")
            return 1
        print("  Senha gravada.")

    if pedir_semente:
        print("\n  Semente do segundo fator: e o codigo longo do QR Code, com")
        print("  32 caracteres, e nao o codigo de 6 digitos do aplicativo.")
        print("  Pode colar com espacos; eles sao ignorados.")
        semente = pedir_segredo("Semente", janela, confirmar=False)
        if semente is None:
            return 1
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

    imp = sub.add_parser("importar", help="carrega o cofre a partir da planilha da banca")
    imp.add_argument("--planilha", required=True, help="caminho do arquivo .xlsx")
    imp.add_argument("--simular", action="store_true",
                     help="mostra o que faria sem gravar nada")

    g = sub.add_parser("guardar", help="grava senha e semente de segundo fator")
    g.add_argument("--tribunal", required=True)
    g.add_argument("--sistema", required=True)
    g.add_argument("--so-login", action="store_true", help="grava apenas o login")
    g.add_argument("--so-senha", action="store_true", help="grava apenas a senha")
    g.add_argument("--so-semente", action="store_true", help="grava apenas a semente")
    g.add_argument("--janela", action="store_true",
                   help="pede o segredo numa janela, que aceita colar do cofre de senhas")

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
    if args.comando == "importar":
        return cmd_importar(cofre, args.planilha, args.simular)
    if args.comando == "guardar":
        return cmd_guardar(cofre, args.tribunal, args.sistema, args.so_senha,
                           args.so_semente, args.janela, args.so_login)
    if args.comando == "testar":
        return cmd_testar(cofre, args.tribunal, args.sistema)
    if args.comando == "remover":
        return cmd_remover(cofre, args.tribunal, args.sistema)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
