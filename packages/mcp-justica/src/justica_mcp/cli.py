"""A LINHA DE COMANDO do `justica-portal`.

Separada de `portal.py` em 22/10/2026. O arquivo de origem tinha 7.394 linhas e
fazia tres trabalhos ao mesmo tempo: a linha de comando, as primitivas
compartilhadas de navegador e a orquestracao de cada um dos cinco portais.

A mistura custou dinheiro uma vez, e esta registrada: em 15/10/2026 o commit
`6adaefbd` trocou a area da janela para consertar a gaveta do Visualizador do
Rio de Janeiro, e quebrou a consulta que funcionava desde 13/10 nos cinco
portais. Uma decisao tomada para UMA tela de UM portal foi parar no lugar que
serve a todos.

Esta e a primeira das tres separacoes, e foi escolhida primeiro por ser a de
menor risco: `main` nao e chamada por ninguem a nao ser pelo terminal, e usa de
`portal.py` apenas 22 nomes, todos importados aqui de uma vez.

O ponto de entrada instalado continua sendo `justica_mcp.portal:main`, que
delega para ca. Trocar o ponto de entrada obrigaria quem ja tem o programa
instalado a reinstalar, e nao ha ganho nenhum nisso.
"""

from __future__ import annotations

import argparse
import sys

# O MODULO, e nao os nomes dele. `from .portal import reconhecer` congela a
# referencia no instante da importacao: trocar `portal.reconhecer` depois disso
# nao chega mais aqui, e foi o que quebrou dois testes na primeira tentativa
# desta separacao. Com o modulo, a ligacao continua tardia, como era quando
# tudo morava no mesmo arquivo.
from . import portal


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="justica-portal",
        description="Le a estrutura de uma pagina de portal sem interagir com ela.",
    )
    sub = p.add_subparsers(dest="comando", required=True)
    r = sub.add_parser("reconhecer", help="abre um endereco e relata a estrutura")
    r.add_argument("--url", required=True, help="endereco completo, copiado da barra do navegador")
    r.add_argument("--oculto", action="store_true",
                   help="nao mostra a janela do navegador (o padrao e mostrar)")
    r.add_argument("--segundos", type=int, default=30, help="tempo limite de carregamento")

    ac = sub.add_parser(
        "acompanhar",
        help="VOCE navega e o programa le a tela onde voce parar",
    )
    ac.add_argument("--url", default=None,
                    help="endereco de partida; sem isto, o do portal no .env")
    ac.add_argument("--tribunal", default=None, help="por exemplo TJRJ")
    ac.add_argument("--sistema", default=None, help="por exemplo dcp")
    ac.add_argument("--segundos", type=int, default=30)
    ac.add_argument("--teto", type=int, default=20,
                    help="quantas telas, no maximo, podem ser registradas")

    cpu = sub.add_parser(
        "consulta-publica",
        help="consulta o processo na tela publica do portal, sem login",
    )
    cpu.add_argument("--url", default=None, help=portal.AJUDA_URL)
    cpu.add_argument("--tribunal", required=True)
    cpu.add_argument("--sistema", required=True)
    cpu.add_argument("--processo", default=None)
    cpu.add_argument("--grau", type=int, default=1)
    cpu.add_argument("--oculto", action="store_true")
    cpu.add_argument("--segundos", type=int, default=30)

    sub.add_parser(
        "ambiente",
        help="diz onde o programa procura a configuracao e o que encontrou la",
    )

    rc = sub.add_parser(
        "repor-config",
        help="repoe o .env a partir da copia de seguranca mais recente",
    )
    rc.add_argument("--confirmar", action="store_true",
                    help="sem isto e ensaio: diz qual copia usaria e nao altera nada")
    rc.add_argument("--copia", default=None,
                    help="usar outra copia que nao a mais recente, pelo nome do arquivo")

    ri = sub.add_parser(
        "reindexar",
        help="refaz o indice de folhas de um processo a partir dos arquivos na pasta",
    )
    ri.add_argument("--processo", required=True)
    ri.add_argument("--confirmar", action="store_true",
                    help="sem isto e ensaio: mostra o que faria e nao altera nada")

    m = sub.add_parser(
        "mapear",
        help="le a tela de entrada de cada portal do .env e grava um mapa por portal",
    )
    m.add_argument("--portal", action="append", dest="alvos", default=None,
                   help="TRIBUNAL/sistema, repetivel; sem isto, todos os do .env")
    m.add_argument("--oculto", action="store_true")
    m.add_argument("--segundos", type=int, default=30)

    s = sub.add_parser(
        "sessao",
        help="diz se a sessao guardada ainda vale, sem gastar tentativa nem codigo",
    )
    s.add_argument("--url", default=None, help=portal.AJUDA_URL)
    s.add_argument("--tribunal", required=True)
    s.add_argument("--sistema", required=True)
    s.add_argument("--oculto", action="store_true")
    s.add_argument("--segundos", type=int, default=30)

    e = sub.add_parser(
        "ensaiar-login",
        help="preenche o formulario e confere o efeito, SEM clicar em Entrar",
    )
    e.add_argument("--url", default=None, help=portal.AJUDA_URL)
    e.add_argument("--tribunal", required=True, help="por exemplo TRF2")
    e.add_argument("--sistema", required=True, help="por exemplo eproc")
    e.add_argument("--campo-usuario", default=None)
    e.add_argument("--campo-senha", default=None)
    e.add_argument("--campo-senha-oculto", default=None)
    e.add_argument("--botao-entrar", default=None,
                   help="conferido, NUNCA clicado: o ensaio so relata se ele habilitou")
    e.add_argument("--oculto", action="store_true")
    e.add_argument("--segundos", type=int, default=30)
    e.add_argument("--espera-humana", type=int, default=portal.ESPERA_HUMANA_PADRAO, dest="espera_humana",
                     help="segundos para o operador marcar a caixa do desafio do Cloudflare")

    tl = sub.add_parser(
        "telas", help="lista as telas ja gravadas, da mais recente para a mais antiga")
    tl.add_argument("--teto", type=int, default=40)

    tv = sub.add_parser(
        "tela",
        help="imprime UMA FATIA de uma tela gravada, sem valor de campo, para "
             "poder ser colada numa conversa")
    tv.add_argument("--arquivo", required=True,
                    help="o arquivo .json da tela (ver `justica-portal telas`)")
    tv.add_argument("--parte", default="resumo",
                    help="resumo (padrao), botoes, campos, mensagens, tabelas "
                         "ou nos")
    tv.add_argument("--contem", default="",
                    help="filtra por texto no identificador, na classe, no "
                         "rotulo ou no texto do elemento")
    tv.add_argument("--teto", type=int, default=60,
                    help="quantos nos imprimir em --parte nos")
    tv.add_argument("--rotulos", action="store_true",
                    help="mostra os rotulos de grupo grande de botoes, que por "
                         "padrao ficam omitidos porque em lista longa o rotulo "
                         "de cada item e conteudo do processo. Mostra no "
                         "maximo cinco, com aviso na propria saida")

    es = sub.add_parser(
        "estrutura",
        help="imprime SO a forma da tela de uma consulta ja gravada, sem valor "
             "de campo, para poder ser colada numa conversa")
    es.add_argument("--arquivo", required=True,
                    help="o arquivo .json que a consulta gravou (o caminho que "
                         "ela imprimiu em 'Conteudo completo em:')")

    t = sub.add_parser("entrar", help="envia o login UMA vez e le a tela seguinte")
    t.add_argument("--url", default=None, help=portal.AJUDA_URL)
    t.add_argument("--tribunal", required=True)
    t.add_argument("--sistema", required=True)
    t.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado",
                   help="confirma que autoriza UMA tentativa de login real")
    t.add_argument("--campo-usuario", default=None)
    t.add_argument("--campo-senha", default=None)
    t.add_argument("--campo-senha-oculto", default=None)
    t.add_argument("--botao-entrar", default=None)
    t.add_argument("--oculto", action="store_true")
    t.add_argument("--segundos", type=int, default=45)
    t.add_argument("--espera-humana", type=int, default=portal.ESPERA_HUMANA_PADRAO, dest="espera_humana",
                     help="segundos para o operador marcar a caixa do desafio do Cloudflare")

    a = sub.add_parser("autenticar", help="credencial e segundo fator, numa sessao so")
    a.add_argument("--url", default=None, help=portal.AJUDA_URL)
    a.add_argument("--tribunal", required=True)
    a.add_argument("--sistema", required=True)
    a.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado")
    a.add_argument("--campo-usuario", default=None)
    a.add_argument("--campo-senha", default=None)
    a.add_argument("--campo-senha-oculto", default=None)
    a.add_argument("--botao-entrar", default=None)
    a.add_argument("--campo-codigo", default=None)
    a.add_argument("--botao-validar", default=None)
    a.add_argument("--reconhecer-apos", action="append", default=None,
                   dest="reconhecer_apos",
                   help="apos autenticar, LE a estrutura desta tela interna; pode ser "
                        "repetido para varias telas na mesma autenticacao. Nao clica "
                        "nem preenche nada em nenhuma delas")
    a.add_argument("--perfil", default=None,
                   help="inscricao a usar quando houver mais de um perfil, "
                        "por exemplo RJ000111")
    a.add_argument("--oculto", action="store_true")
    a.add_argument("--segundos", type=int, default=45)
    a.add_argument("--espera-humana", type=int, default=portal.ESPERA_HUMANA_PADRAO, dest="espera_humana",
                     help="segundos para o operador marcar a caixa do desafio do Cloudflare")
    a.add_argument("--reenviar-apos-desafio", action="store_true",
                     dest="reenviar",
                     help="reenvia a credencial na hora se o portal voltar ao login apos o desafio, e so quando nao houver mensagem de erro")

    pc = sub.add_parser("pecas", help="lista as pecas ja gravadas na pasta do processo")
    pc.add_argument("--processo", required=True)
    pc.add_argument("--teto", type=int, default=40,
                    help="quantas pecas listar")

    pl = sub.add_parser("peca", help="le o texto de UMA peca gravada na pasta")
    pl.add_argument("--processo", required=True)
    pl.add_argument("--peca", type=int, required=True,
                    help="pagina em que a peca comeca, a que aparece no indice")
    pl.add_argument("--de", type=int, default=1,
                    help="primeira folha a ler, dentro da peca")
    pl.add_argument("--ate", type=int, default=None,
                    help="ultima folha a ler, dentro da peca")

    cp = sub.add_parser("consultar", help="autentica e consulta um processo pela busca rapida")
    cp.add_argument("--url", default=None, help=portal.AJUDA_URL)
    cp.add_argument("--tribunal", required=True)
    cp.add_argument("--sistema", required=True)
    cp.add_argument("--grau", type=int, choices=(1, 2), default=1,
                    help="qual processo de teste usar quando --processo e omitido; "
                         "o grau do processo informado e deduzido do proprio numero")
    cp.add_argument("--processo", default=None,
                    help="numero no padrao da numeracao unica; quando omitido, vem do .env "
                         "(JUSTICA_PORTAL_<TRIBUNAL>_<SISTEMA>_PROCESSO_TESTE)")
    cp.add_argument("--campo-usuario", default=None)
    cp.add_argument("--campo-senha", default=None)
    cp.add_argument("--campo-senha-oculto", default=None)
    cp.add_argument("--botao-entrar", default=None)
    cp.add_argument("--campo-codigo", default=None)
    cp.add_argument("--botao-validar", default=None)
    cp.add_argument("--perfil", default=None,
                    help="qual perfil usar quando o portal pergunta: a inscricao "
                         "no eproc (RJ000111) ou o tipo de usuario no DCP "
                         "(Advogado)")
    cp.add_argument("--segundos-download", type=int, default=None,
                    dest="segundos_download",
                    help="quanto esperar pelo ARQUIVO, que e diferente de "
                         "esperar por tela: o portal GERA o PDF quando se pede. "
                         "Minimo e padrao: 300. Processo muito grande pode "
                         "precisar de mais")
    cp.add_argument("--motivo", default=None,
                    help="justificativa do acesso aos autos, quando o portal a "
                         "pedir. O do Rio de Janeiro pede, no campo 'Motivo', "
                         "antes de abrir o Visualizador. Padrao: 'consulta'")
    cp.add_argument("--sem-movimentacoes", action="store_true",
                    dest="sem_movimentacoes",
                    help="pula a leitura do historico de movimentacoes, que no "
                         "DCP do Rio de Janeiro abre o historico e percorre "
                         "todas as paginas dele. A capa e as partes continuam "
                         "sendo lidas. Serve para testar o download sem "
                         "esperar o historico inteiro")
    cp.add_argument("--documentos", default="auto",
                    help="'auto' (padrao: um download por documento, que e o "
                         "unico tamanho que o DCP do Rio de Janeiro foi visto "
                         "entregar), "
                         "'integra', 'ultimos:N' ou 'nenhum'. No DCP do Rio de "
                         "Janeiro, para processo grande que nao baixa de uma vez: "
                         "'peca:N' baixa SO o documento que comeca na pagina N "
                         "(o numero que aparece ao lado do nome no indice), e "
                         "'lotes' ou 'lotes:N' baixa o processo inteiro de N em "
                         "N paginas, 300 por padrao, e 'lote:K' baixa SO o "
                         "K-esimo desses lotes, para conferir o caminho ou "
                         "repetir um que falhou. 'um-a-um' baixa o processo "
                         "inteiro com UM download por documento, reabrindo o "
                         "Visualizador a cada um, e pula o que ja estiver em "
                         "disco: e o unico tamanho de selecao que este portal "
                         "entrega em processo grande. 'um-a-um:N' sobe o teto "
                         "de documentos do percurso, que e 200 por padrao")
    cp.add_argument("--pular", default=None,
                    help="paginas iniciais de documento que o percurso deve "
                         "PULAR, separadas por virgula. Serve para passar "
                         "adiante de um documento que derruba o navegador "
                         "inteiro: ele nao entra na pasta, e o `reindexar` "
                         "aponta as paginas que faltam")
    cp.add_argument("--linha", type=int, default=1,
                    help="qual linha do resultado abrir, quando a busca "
                         "devolve mais de uma com o mesmo numero. Cada linha "
                         "costuma ser o processo numa serventia ou num grau "
                         "diferente, com historico proprio. Padrao: 1")
    cp.add_argument("--gravar-telas", action="store_true", dest="gravar_telas",
                    help="grava em disco a FORMA de cada tela que a corrida "
                         "tocar (etiquetas, identificadores, rotulos, geometria "
                         "e mensagens), sem valor de campo nenhum. Serve para "
                         "descobrir o que a tela oferecia sem gastar outra "
                         "autenticacao. Ver `justica-portal telas`")
    cp.add_argument("--confirmo-tentativa-unica", action="store_true", dest="confirmado")
    cp.add_argument("--aceito-o-termo", action="store_true", dest="aceitar_termo",
                    help="aceita o aviso de responsabilidade que o PJe levanta ao abrir "
                         "os autos (resolucao nº. 121 do Conselho Nacional de Justica). "
                         "Sem esta opcao o comando mostra o texto do aviso e para: o "
                         "aceite e ato do advogado, nao do programa")
    cp.add_argument("--oculto", action="store_true")
    cp.add_argument("--segundos", type=int, default=45)
    cp.add_argument("--espera-humana", type=int, default=portal.ESPERA_HUMANA_PADRAO, dest="espera_humana",
                      help="segundos para o operador marcar a caixa do desafio do Cloudflare")
    cp.add_argument("--reenviar-apos-desafio", action="store_true",
                      dest="reenviar",
                      help="reenvia a credencial na hora se o portal voltar ao login apos o desafio, e so quando nao houver mensagem de erro")

    args = p.parse_args(argv)

    # O .env nunca era lido aqui: so o servidor o carregava. Quem configurasse
    # a pasta de copias ou o endereco do portal no arquivo via a linha de
    # comando ignorar tudo, em silencio, e gravar no lugar antigo.
    portal.carregar_env()

    try:
        # `estrutura` le um arquivo ja gravado: nao tem tribunal, nao tem
        # sistema e nao abre navegador nenhum.
        if args.comando not in ("reconhecer", "mapear", "reindexar", "ambiente",
                                "repor-config", "estrutura", "telas", "tela",
                                "pecas", "peca"):
            portal._do_ambiente(args)
            portal.completar_seletores(args)
        if args.comando in ("pecas", "peca"):
            # Nao abre navegador, nao autentica, nao gasta tentativa: le a
            # pasta de copias do disco.
            from .core.cnj import parse_numero as _parse
            from .pecas import (ler_peca, pecas_da_pasta, gravar_o_texto,
                                relatar_a_leitura, relatar_as_pecas)
            try:
                _numero = _parse(args.processo)
            except ValueError as exc:
                print(f"Numero de processo invalido: {exc}", file=sys.stderr)
                return 1
            if args.comando == "pecas":
                dados = pecas_da_pasta(_numero.apenas_digitos,
                                       _numero.formatado)
                for linha in relatar_as_pecas(dados, args.teto):
                    print(linha)
                return 0
            lido = ler_peca(_numero.apenas_digitos, _numero.formatado,
                            args.peca, de=args.de, ate=args.ate)
            if "erro" in lido:
                print(f"[PAROU] {lido['erro']}", file=sys.stderr)
                if lido.get("pecas_na_pasta"):
                    print("  Pecas na pasta: "
                          + ", ".join(str(p) for p in lido["pecas_na_pasta"]),
                          file=sys.stderr)
                return 1
            # O TEXTO vai para arquivo. O terminal recebe so o caminho e as
            # contagens: dado de cliente nao se imprime em tela que se cola.
            destino = (gravar_o_texto(_numero.apenas_digitos,
                                      _numero.apenas_digitos, args.peca,
                                      lido["texto"])
                       if lido["texto"] else None)
            for linha in relatar_a_leitura(lido, destino):
                print(f"  {linha}")
            return 0
        if args.comando == "reconhecer":
            return portal.reconhecer(args.url, oculto=args.oculto, segundos=args.segundos)
        if args.comando == "acompanhar":
            if not args.url:
                if not (args.tribunal and args.sistema):
                    print("Informe --url, ou --tribunal e --sistema para usar o "
                          "endereco do .env.", file=sys.stderr)
                    return 1
                portal._do_ambiente(args)
            return portal.acompanhar(args.url, segundos=args.segundos, teto=args.teto)
        if args.comando == "consulta-publica":
            if not args.processo:
                print("Nenhum processo informado. Passe --processo, ou defina "
                      "o de teste no .env.", file=sys.stderr)
                return 1
            return portal.consulta_publica(args.tribunal, args.sistema, args.processo,
                                    args.url, oculto=args.oculto,
                                    segundos=args.segundos)
        if args.comando == "ambiente":
            return portal.mostrar_ambiente()
        if args.comando == "repor-config":
            return portal.repor_config(confirmar=args.confirmar, copia=args.copia)
        if args.comando == "estrutura":
            return portal.mostrar_estrutura(args.arquivo)
        if args.comando == "telas":
            from .telas import listar_telas

            return listar_telas(args.teto)
        if args.comando == "tela":
            from .telas import mostrar_tela

            return mostrar_tela(args.arquivo, args.parte, args.contem,
                                args.teto, args.rotulos)
        if args.comando == "reindexar":
            return portal.reindexar(args.processo, confirmar=args.confirmar)
        if args.comando == "mapear":
            return portal.mapear(args.alvos, oculto=args.oculto, segundos=args.segundos)
        if args.comando == "sessao":
            return portal.conferir_sessao(args.url, args.tribunal, args.sistema,
                                   oculto=args.oculto, segundos=args.segundos)
        if args.comando == "consultar":
            # A gravacao e ligada por variavel de ambiente, e nao passada de mao
            # em mao: ela e lida nas pontas, dentro de `dcp.py`, a sete camadas
            # de chamada daqui, e enfiar um parametro por todas elas so para
            # carregar um sim ou nao sujaria sete assinaturas.
            if getattr(args, "gravar_telas", False):
                from .telas import ligar_gravacao, pasta_das_telas

                ligar_gravacao()
                print(f"Gravando a FORMA de cada tela em {pasta_das_telas()}.")
                print("Nenhum valor de campo e gravado. Ver `justica-portal telas`.")
            if not args.processo:
                print(
                    "Nenhum processo informado. Passe --processo, ou defina no .env:\n"
                    f"    JUSTICA_PORTAL_{args.tribunal.upper()}_{args.sistema.upper()}"
                    "_PROCESSO_TESTE=<numero>",
                    file=sys.stderr,
                )
                return 1
            return portal.consultar_processo(
                args.url, args.tribunal, args.sistema, args.processo,
                campo_usuario=args.campo_usuario, campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto, botao_entrar=args.botao_entrar,
                campo_codigo=args.campo_codigo, botao_validar=args.botao_validar,
                documentos=args.documentos, confirmado=args.confirmado,
                aceitar_termo=args.aceitar_termo, motivo=args.motivo,
                segundos_download=args.segundos_download,
                sem_movimentacoes=args.sem_movimentacoes,
                linha_do_resultado=args.linha,
                paginas_a_pular=portal._paginas_pedidas(args.pular),
                perfil=args.perfil, oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana, reenviar=args.reenviar,
            )
        if args.comando == "autenticar":
            return portal.autenticar(
                args.url, args.tribunal, args.sistema, confirmado=args.confirmado,
                campo_usuario=args.campo_usuario, campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto, botao_entrar=args.botao_entrar,
                campo_codigo=args.campo_codigo, botao_validar=args.botao_validar,
                perfil=args.perfil, oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana, reenviar=args.reenviar,
                reconhecer_apos=args.reconhecer_apos,
            )
        if args.comando == "entrar":
            return portal.entrar(
                args.url, args.tribunal, args.sistema, confirmado=args.confirmado,
                campo_usuario=args.campo_usuario, campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto, botao_entrar=args.botao_entrar,
                oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana,
            )
        if args.comando == "ensaiar-login":
            return portal.ensaiar_login(
                args.url, args.tribunal, args.sistema,
                campo_usuario=args.campo_usuario,
                campo_senha=args.campo_senha,
                campo_senha_oculto=args.campo_senha_oculto,
                botao_entrar=args.botao_entrar,
                oculto=args.oculto, segundos=args.segundos,
                espera_humana=args.espera_humana,
            )
    except (portal.PortalIndisponivel, portal.PortalNaoConfigurado) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Rede de seguranca so para UM caso, e nao para erro em geral: a janela
        # do navegador fechada. Ela e fechada pelo operador, e em 30/09/2026
        # isso subiu como traceback de Playwright no meio de uma autenticacao
        # que tinha dado certo, o que parece defeito grave e nao e. Qualquer
        # outro erro continua subindo inteiro: esconde-lo seria pior.
        if portal.leitura_perdida_para_navegacao(exc):
            # Segundo caso, e pelo mesmo motivo do primeiro: nao e defeito
            # grave e chegava como traceback de Playwright. Conferido em campo
            # em 07/10/2026, com a autenticacao ja concluida: a aba de origem
            # voltava para a pagina publica do tribunal enquanto era lida.
            # A leitura morre, a sessao nao: por isso o recado diz que repetir
            # o comando nao gasta credencial nova.
            print("\n  [PARADO] A tela mudou de endereco enquanto era lida.",
                  file=sys.stderr)
            print("  Isto e defeito deste programa, nao do portal, e a sessao",
                  file=sys.stderr)
            print("  continua aberta neste navegador: repetir o comando nao",
                  file=sys.stderr)
            print("  recomeca a autenticacao do zero.", file=sys.stderr)
            return 1
        if "has been closed" not in str(exc):
            raise
        print("\n  [PARADO] A janela do navegador nao esta mais aberta.", file=sys.stderr)
        print("  Se foi voce que a fechou, ou que concluiu o login por la, nada",
              file=sys.stderr)
        print("  se perdeu: a sessao fica guardada no perfil do navegador.",
              file=sys.stderr)
        print("  Confira sem gastar tentativa nenhuma com o comando 'sessao'.",
              file=sys.stderr)
        return 1
    return 2
