"""Quem corre o comando demorado e grava o proprio desfecho.

POR QUE ESTA CAMADA EXISTE.

O download dos autos leva de minutos a horas, e o servidor da extensao
reinicia por motivos que nada tem a ver com ele: conectar o Remote Control,
reabrir o aplicativo. Desde 29/10/2026 o trabalho sobrevive a isso, porque o
relato vai para arquivo e a anotacao fica em disco.

Sobrou um buraco. O servidor que SOBE depois nao e pai do processo que ficou
rodando, e `wait()` so funciona para filho proprio: nao ha como ler o codigo
de saida de um processo alheio. Ao ver o processo sumir, esse servidor so
poderia dizer "terminou", sem saber se deu certo. Ou, pior, chutar
"concluido" e afirmar ao advogado um sucesso que ninguem verificou.

Entao quem corre grava o proprio desfecho num arquivo, ao terminar. Qualquer
servidor futuro le a marca e sabe, sem precisar ter sido o pai.

A marca e escrita no `finally`: comando que explode tem de deixar marca
tambem. Sem ela, quem ler depois conclui que o trabalho ainda corre, e um
download morto ficaria "em curso" para sempre.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Codigo reservado para "o comando levantou excecao antes de devolver codigo".
# Diferente de 1, que o proprio comando usa para recusa prevista: aqui nao
# houve recusa, houve queda.
CODIGO_DE_QUEDA = 70


def correr(argv: list[str], _comando=None) -> int:
    """Roda o comando e grava o codigo de saida em `argv[0]`.

    `argv[0]` e o arquivo da marca; o resto vai para a linha de comando.
    """
    marca = Path(argv[0])
    comando = _comando or _do_portal
    codigo = CODIGO_DE_QUEDA
    try:
        codigo = int(comando(list(argv[1:])) or 0)
    except SystemExit as saida:
        # `argparse` encerra assim em erro de uso, e isso e desfecho, nao
        # queda: o codigo dele vale.
        codigo = int(saida.code or 0)
    except BaseException:
        # O RASTRO VAI PARA O RELATO, E A EXCECAO NAO SOBE.
        #
        # Relanca-la daria o rastro e nenhum codigo de saida, porque o
        # `SystemExit(correr(...))` la embaixo nunca rodaria. Engoli-la daria
        # o codigo e nenhuma explicacao. Impressa aqui, ela cai no arquivo de
        # relato, que e para onde a saida deste processo aponta, e quem ler o
        # trabalho depois ve as duas coisas.
        import traceback

        codigo = CODIGO_DE_QUEDA
        print("\n  [QUEDA] o comando terminou por excecao:")
        traceback.print_exc()
    finally:
        try:
            marca.write_text(str(codigo), encoding="utf-8")
        except OSError:
            # Marca perdida e ruim; derrubar o comando por causa dela seria
            # pior, e o comando e o que o advogado pediu.
            pass
    return codigo


def _do_portal(argv: list[str]) -> int:
    from .portal import main

    return main(argv)


if __name__ == "__main__":
    raise SystemExit(correr(sys.argv[1:]))
