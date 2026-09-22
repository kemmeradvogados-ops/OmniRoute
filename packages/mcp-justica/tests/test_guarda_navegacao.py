"""Trava de navegacao do acesso autenticado.

Este e o teste mais importante do projeto. O que ele protege nao e um dado
errado na tela: e um prazo do cliente. Abrir o teor de uma intimacao dispara a
ciencia e inicia a contagem (lei nº. 11.419/06, artigo 5º, §3º), e nao existe
desfazer.
"""

import pytest

from justica_mcp.core.guarda_navegacao import (
    Acao, Decisao, GuardaNavegacao, Modo, NavegacaoBloqueada, Permissao,
    TERMOS_DE_RISCO,
)

PAINEL = Permissao(
    padrao_url=r"^https://eproc\.tjrj\.jus\.br/painel",
    descricao="painel de processos, somente listagem",
    conferido_em="2026-09-21",
    seletores_clicaveis=("#pagina-seguinte",),
    seletores_preenchiveis=("#campo-busca",),
)


def _guarda(modo=Modo.LEITURA, permissoes=None):
    return GuardaNavegacao(modo=modo, permissoes=list(permissoes or [PAINEL]))


# ---------------- negar por padrao ----------------

def test_sem_lista_de_permissao_nada_navega():
    """Estado inicial do projeto: nenhuma tela conferida, nada acessivel.
    E proposital. Enquanto ninguem confirmou uma tela, o adaptador nao chega
    nela."""
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    d = g.avaliar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/qualquer")
    assert d.permitido is False
    assert "NEGAR" in d.motivo


def test_endereco_desconhecido_e_bloqueado_mesmo_com_outras_telas_liberadas():
    d = _guarda().avaliar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/expedientes")
    assert d.permitido is False


def test_tela_conferida_pode_ser_navegada():
    d = _guarda().avaliar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/painel?p=1")
    assert d.permitido is True
    assert "2026-09-21" in d.motivo


def test_ler_e_sempre_permitido_porque_nao_pratica_ato():
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    assert g.avaliar(Acao.LER, "tabela de processos").permitido is True


# ---------------- a segunda camada ----------------

@pytest.mark.parametrize("termo", TERMOS_DE_RISCO)
def test_todo_termo_de_risco_bloqueia(termo):
    alvo = f"https://eproc.tjrj.jus.br/painel/{termo}/123"
    assert _guarda().avaliar(Acao.NAVEGAR, alvo).permitido is False


def test_termo_de_risco_vence_a_lista_de_permissao():
    """O caso que justifica a segunda camada: alguem libera um seletor por
    engano durante a conferencia em campo. O bloqueio tem de prevalecer."""
    permissao_com_erro = Permissao(
        padrao_url=r"eproc\.tjrj",
        descricao="tela liberada por engano",
        conferido_em="2026-09-21",
        seletores_clicaveis=("#dar-ciencia",),
    )
    g = _guarda(permissoes=[permissao_com_erro])
    d = g.avaliar(Acao.CLICAR, "#dar-ciencia", url="https://eproc.tjrj.jus.br/x")
    assert d.permitido is False
    assert "11.419/06" in d.motivo


def test_termo_de_risco_ignora_caixa_e_sublinhado():
    g = _guarda()
    assert g.avaliar(Acao.CLICAR, "#DAR_CIENCIA", url="https://eproc.tjrj.jus.br/painel").permitido is False
    assert g.avaliar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/painel/Peticionar").permitido is False


def test_download_negado_por_padrao():
    """Baixar autos foi proibido em qualquer modo ate 21 de setembro de 2026,
    quando o operador decidiu habilitar a copia. Continua NEGADO POR PADRAO: a
    mudanca foi de "nunca" para "mediante autorizacao", nao para "livre"."""
    d = _guarda().avaliar(Acao.BAIXAR, "doc.pdf", url="https://eproc.tjrj.jus.br/painel")
    assert d.permitido is False
    assert "nao autorizado nesta operacao" in d.motivo


def test_download_autorizado_so_vale_na_tela_liberada():
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[PAINEL], permitir_download=True)
    assert g.avaliar(Acao.BAIXAR, "https://eproc.tjrj.jus.br/painel/doc/1").permitido is True
    assert g.avaliar(Acao.BAIXAR, "https://outro.tribunal.jus.br/doc/1").permitido is False


def test_termo_de_risco_bloqueia_download_mesmo_autorizado():
    """A autorizacao de download nao desliga a segunda camada."""
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[PAINEL], permitir_download=True)
    alvo = "https://eproc.tjrj.jus.br/painel/dar-ciencia/9"
    assert g.avaliar(Acao.BAIXAR, alvo).permitido is False


# ---------------- seletores ----------------

def test_clique_so_no_seletor_liberado():
    g = _guarda()
    url = "https://eproc.tjrj.jus.br/painel"
    assert g.avaliar(Acao.CLICAR, "#pagina-seguinte", url=url).permitido is True
    assert g.avaliar(Acao.CLICAR, "#outro-botao", url=url).permitido is False


def test_preencher_so_no_campo_liberado():
    g = _guarda()
    url = "https://eproc.tjrj.jus.br/painel"
    assert g.avaliar(Acao.PREENCHER, "#campo-busca", url=url).permitido is True
    assert g.avaliar(Acao.PREENCHER, "#campo-qualquer", url=url).permitido is False


def test_seletor_clicavel_nao_vale_para_preencher():
    """Listas separadas de proposito: clicar e preencher sao atos distintos."""
    d = _guarda().avaliar(Acao.PREENCHER, "#pagina-seguinte", url="https://eproc.tjrj.jus.br/painel")
    assert d.permitido is False


# ---------------- modo ensaio ----------------

def test_ensaio_nao_executa_nem_o_que_e_permitido():
    """O adaptador nasce em ensaio e roda assim a primeira vez. O advogado le
    o relato do que ele FARIA antes de o codigo ganhar permissao de agir."""
    g = _guarda(modo=Modo.ENSAIO)
    assert g.pode_executar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/painel") is False
    assert g.registro[-1]["permitido"] is True
    assert g.registro[-1]["executado"] is False


def test_leitura_executa_o_que_e_permitido():
    g = _guarda(modo=Modo.LEITURA)
    assert g.pode_executar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/painel") is True
    assert g.registro[-1]["executado"] is True


def test_bloqueio_levanta_excecao_em_vez_de_devolver_falso():
    """`pode_executar` devolvendo False significaria 'nao execute agora'.
    Bloqueio e outra coisa: o adaptador nao pode simplesmente seguir adiante."""
    g = _guarda(modo=Modo.ENSAIO)
    with pytest.raises(NavegacaoBloqueada, match="Navegacao bloqueada"):
        g.pode_executar(Acao.CLICAR, "#dar-ciencia", url="https://eproc.tjrj.jus.br/painel")


def test_ensaio_bloqueia_igual_ao_modo_leitura():
    """Ensaio nao e modo permissivo: e modo que nao executa. O que seria
    bloqueado em producao tambem e bloqueado no ensaio, para o relato mostrar
    a barreira."""
    for modo in (Modo.ENSAIO, Modo.LEITURA):
        d = _guarda(modo=modo).avaliar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/expedientes/abrir/9")
        assert d.permitido is False


# ---------------- relato ----------------

def test_relato_distingue_executou_faria_e_bloqueou():
    g = _guarda(modo=Modo.ENSAIO)
    g.avaliar(Acao.NAVEGAR, "https://eproc.tjrj.jus.br/painel")
    g.avaliar(Acao.CLICAR, "#dar-ciencia", url="https://eproc.tjrj.jus.br/painel")
    texto = "\n".join(g.relato())
    assert "FARIA" in texto and "BLOQUEOU" in texto and "EXECUTOU" not in texto


def test_toda_avaliacao_entra_no_registro():
    """O registro vira prova do que o robo fez e do que foi impedido."""
    g = _guarda()
    for i in range(4):
        g.avaliar(Acao.NAVEGAR, f"https://eproc.tjrj.jus.br/painel?p={i}")
    assert len(g.registro) == 4


def test_decisao_e_imutavel():
    d = Decisao(True, "ok", Acao.LER, "x")
    with pytest.raises(Exception):
        d.permitido = False


def test_permissoes_somam_em_vez_de_se_anular():
    """Defeito encontrado ao ligar a copia integral: a permissao de origem,
    ampla e sem seletores, escondia a permissao especifica que liberava o
    botao, porque a trava so olhava a primeira que casava. Concessao e coisa
    que soma."""
    ampla = Permissao(
        padrao_url=r"^https://eproc\.tjrj\.jus\.br/",
        descricao="documentos, mesma origem",
        conferido_em="2026-09-21",
    )
    especifica = Permissao(
        padrao_url=r"^https://eproc\.tjrj\.jus\.br/painel",
        descricao="copia integral pelo botao",
        conferido_em="2026-09-21",
        seletores_clicaveis=("#btnDownloadCompletoRS",),
    )
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[ampla, especifica])
    url = "https://eproc.tjrj.jus.br/painel"
    d = g.avaliar(Acao.CLICAR, "#btnDownloadCompletoRS", url=url)
    assert d.permitido is True
    assert "copia integral" in d.motivo


def test_somar_permissoes_nao_libera_o_que_nenhuma_libera():
    ampla = Permissao(r"^https://eproc\.tjrj\.jus\.br/", "origem", "2026-09-21")
    especifica = Permissao(
        r"^https://eproc\.tjrj\.jus\.br/painel", "painel", "2026-09-21",
        seletores_clicaveis=("#btnPermitido",),
    )
    g = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[ampla, especifica])
    d = g.avaliar(Acao.CLICAR, "#btnQualquer", url="https://eproc.tjrj.jus.br/painel")
    assert d.permitido is False
    assert "#btnPermitido" in d.motivo, "o motivo lista o que de fato esta liberado"


# --------------------------------------------------------------------------
# O botao de ciencia mora na pagina do processo
#
# Achado em campo em 22 de setembro de 2026, no e-SAJ de Sao Paulo: a pagina do
# processo, a mesma de onde se leem partes e movimentacoes, contem
# `div#modalRecebimentoIntimacao` e `button#botaoConfirmarRebebimentoIntimacao`.
# O ato que dispara a ciencia e inicia o prazo esta a poucos nos do que se le.
# --------------------------------------------------------------------------

def test_botao_de_confirmar_recebimento_de_intimacao_e_barrado():
    """Exatamente como o portal o escreve, com o erro de digitacao dele."""
    guarda = GuardaNavegacao(
        modo=Modo.LEITURA,
        permissoes=[Permissao(
            padrao_url="^https://esaj\\.tjsp\\.jus\\.br/",
            descricao="pagina do processo",
            conferido_em="teste",
            seletores_clicaveis=("#botaoConfirmarRebebimentoIntimacao",),
        )],
    )
    d = guarda.avaliar(
        Acao.CLICAR, "#botaoConfirmarRebebimentoIntimacao",
        url="https://esaj.tjsp.jus.br/cpopg/show.do",
    )
    assert d.permitido is False
    assert "ciencia" in d.motivo


def test_a_grafia_correta_tambem_e_barrada():
    """O portal pode corrigir o erro de digitacao a qualquer momento, e a trava
    nao pode depender de ele continuar errado."""
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    for alvo in ("#botaoConfirmarRecebimentoIntimacao",
                 "#modalRecebimentoIntimacao",
                 "#btnReceberIntimacao"):
        assert guarda.avaliar(Acao.CLICAR, alvo).permitido is False


def test_a_permissao_explicita_nao_contorna_o_termo_de_risco():
    """Listar o seletor na permissao nao libera: o termo de risco e conferido
    antes, e e por isso que ele e a garantia e a lista e so a conveniencia."""
    guarda = GuardaNavegacao(
        modo=Modo.LEITURA,
        permissoes=[Permissao(
            padrao_url="^https://esaj\\.tjsp\\.jus\\.br/",
            descricao="permissao ampla de proposito, para o teste",
            conferido_em="teste",
            seletores_clicaveis=("#botaoConfirmarRebebimentoIntimacao",),
            seletores_preenchiveis=("#botaoConfirmarRebebimentoIntimacao",),
        )],
    )
    for acao in (Acao.CLICAR, Acao.PREENCHER):
        d = guarda.avaliar(acao, "#botaoConfirmarRebebimentoIntimacao",
                           url="https://esaj.tjsp.jus.br/cpopg/show.do")
        assert d.permitido is False


def test_ler_a_pagina_do_processo_continua_permitido():
    """A trava precisa barrar o ato, nao a leitura: barrar a pagina inteira
    inutilizaria a consulta, que e o que o advogado pediu."""
    guarda = GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])
    d = guarda.avaliar(
        Acao.LER, "table#tablePartesPrincipais",
        url="https://esaj.tjsp.jus.br/cpopg/show.do?processo.numero=1037850-62.2023.8.26.0100",
    )
    assert d.permitido is True


# --------------------------------------------------------------------------
# "salvar" cru era largo demais
#
# Estreitado em 22/09/2026, com o operador informado. O termo existia para
# impedir gravar alteracao de cadastro, e estava impedindo `#salvarButton`, que
# na Pasta Digital do e-SAJ baixa um arquivo e nao altera nada.
# --------------------------------------------------------------------------

def _guarda_livre():
    return GuardaNavegacao(modo=Modo.LEITURA, permissoes=[])


def test_baixar_arquivo_deixou_de_ser_confundido_com_gravar_cadastro():
    """Termo largo demais que barra leitura nao protege: ensina a contorna-lo."""
    d = _guarda_livre().avaliar(Acao.CLICAR, "#salvarButton",
                                url="https://esaj.tjsp.jus.br/pastadigital/abrir.do")
    assert "Termo de risco" not in d.motivo


def test_gravar_alteracao_de_cadastro_continua_barrado():
    for alvo in ("#salvarCadastro", "#btnGravarCadastro", "#salvarAlteracao",
                 "#salvar_senha", "#salvarPerfil"):
        d = _guarda_livre().avaliar(Acao.CLICAR, alvo)
        assert d.permitido is False, alvo
        assert "Termo de risco" in d.motivo


def test_a_tela_de_alteracao_de_cadastro_e_barrada_pelo_endereco():
    """O risco mora no endereco, e barra-lo ali cobre qualquer botao que a tela
    tenha, inclusive os que nao previmos."""
    for url in ("https://eproc.jfrj.jus.br/eproc/controlador.php?acao=pessoa_alterar",
                "https://portal.exemplo/alterar-cadastro"):
        assert _guarda_livre().avaliar(Acao.NAVEGAR, url, url=url).permitido is False


def test_excluir_e_remover_continuam_crus():
    """Sao destrutivos: nao ha versao inofensiva de excluir."""
    for alvo in ("#excluirTudo", "#removerDocumento"):
        assert _guarda_livre().avaliar(Acao.CLICAR, alvo).permitido is False


def test_o_botao_de_ciencia_nao_foi_afetado_pelo_estreitamento():
    """A mudanca mexeu em `salvar` e `gravar`. A protecao central, que e a
    ciencia, tem de continuar exatamente como estava."""
    d = _guarda_livre().avaliar(Acao.CLICAR, "#botaoConfirmarRebebimentoIntimacao")
    assert d.permitido is False
    assert "ciencia" in d.motivo
