"""Adaptador recusa o que nao sabe fazer ANTES de gastar chamada de rede."""

import pytest

from justica_mcp.adapters import AdaptadorDataJud, AdaptadorDJEN
from justica_mcp.adapters.base import CapacidadeIndisponivel
from justica_mcp.core.capabilities import Capacidade


def test_datajud_recusa_busca_por_parte_com_motivo_e_sem_rede():
    with pytest.raises(CapacidadeIndisponivel) as exc:
        AdaptadorDataJud(chave="irrelevante").exigir_capacidade(Capacidade.BUSCAR_POR_PARTE)
    assert "Portaria nº. 160/2020" in str(exc.value)


def test_datajud_recusa_documentos():
    with pytest.raises(CapacidadeIndisponivel, match="nao expoe documentos"):
        AdaptadorDataJud(chave="x").exigir_capacidade(Capacidade.BAIXAR_INTEGRA)


def test_djen_aponta_o_adaptador_certo_para_andamentos():
    """Recusa util indica para onde ir, em vez de so negar."""
    with pytest.raises(CapacidadeIndisponivel) as exc:
        AdaptadorDJEN().exigir_capacidade(Capacidade.LISTAR_ANDAMENTOS)
    assert "datajud" in str(exc.value)


def test_djen_separa_publicacao_de_expediente_do_portal():
    """Distincao critica: ler o Diario nao dispara ciencia; abrir expediente dispara."""
    with pytest.raises(CapacidadeIndisponivel) as exc:
        AdaptadorDJEN().exigir_capacidade(Capacidade.LISTAR_INTIMACOES_PENDENTES)
    assert "NAO dispara ciencia" in str(exc.value)


def test_datajud_sem_chave_da_erro_acionavel():
    from justica_mcp.adapters.datajud import ChaveDataJudAusente

    a = AdaptadorDataJud(chave="")
    assert not a.configurado
    with pytest.raises(ChaveDataJudAusente, match="datajud-wiki.cnj.jus.br"):
        a._cabecalhos()


def test_chave_ausente_vira_erro_de_configuracao_nao_erro_interno():
    """Falta de configuracao e acionavel pelo operador; 'erro interno' esconderia isso."""
    import asyncio
    import json

    from justica_mcp.tools import _tratar
    from justica_mcp.adapters.datajud import ChaveDataJudAusente

    resposta = json.loads(_tratar(ChaveDataJudAusente()))
    assert resposta["codigo"] == "configuracao_ausente"
    assert "DATAJUD_API_KEY" in resposta["erro"]


def test_chave_vazia_explicita_nao_cai_no_ambiente(monkeypatch):
    """Regressao encontrada em campo em 21 de setembro de 2026.

    Com a chave presente no ambiente, `chave=""` passava a usar a chave
    ambiente por causa do encadeamento com `or`. Quem passasse uma configuracao
    vazia esperando ficar sem chave acabava consultando com a chave de outro
    contexto, sem nenhum aviso.
    """
    monkeypatch.setenv("DATAJUD_API_KEY", "chave-do-ambiente")
    assert AdaptadorDataJud(chave="").configurado is False
    assert AdaptadorDataJud(chave="   ").configurado is False, "so espacos tambem e vazio"


def test_chave_none_le_do_ambiente(monkeypatch):
    """`None` continua significando 'leia do ambiente'."""
    monkeypatch.setenv("DATAJUD_API_KEY", "chave-do-ambiente")
    assert AdaptadorDataJud().configurado is True
    assert AdaptadorDataJud(chave=None).configurado is True


def test_sem_chave_no_ambiente_e_sem_argumento(monkeypatch):
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    assert AdaptadorDataJud().configurado is False


def test_chave_explicita_vence_o_ambiente(monkeypatch):
    monkeypatch.setenv("DATAJUD_API_KEY", "do-ambiente")
    a = AdaptadorDataJud(chave="explicita")
    assert a._cabecalhos()["Authorization"] == "APIKey explicita"


# ==========================================================================
# NAO_SUPORTADO fala da FONTE; NAO_IMPLEMENTADO fala deste projeto
#
# Confundir as duas e pior que nao ter matriz nenhuma: escrever NAO_SUPORTADO
# para dizer "nao pretendo construir" poe na boca do servidor uma afirmacao
# falsa sobre o tribunal, e o advogado deixa de procurar no portal uma coisa
# que esta la. Foi o que aconteceu com o DCP do Tribunal de Justica do Rio de
# Janeiro ate 06/10/2026, quando o operador confirmou que o portal baixa a
# integra do processo.
# ==========================================================================

def test_o_dcp_nao_declara_mais_que_o_portal_nao_baixa_a_integra():
    """A REGRA, e so ela: o Portal de Servicos oferece a integra, entao dizer
    NAO_SUPORTADO poria na boca do servidor uma afirmacao falsa sobre o
    tribunal.

    Ate 29/10/2026 este teste exigia tambem `is NAO_IMPLEMENTADO`, o que
    congelou a declaracao: o adaptador foi escrito ao longo de outubro e a
    matriz nao pode mudar sem este teste quebrar. Um teste que fixa a
    conclusao impede justamente a correcao que ele deveria permitir. A regra
    sobrevive; a conclusao, nao.
    """
    from justica_mcp.core.capabilities import Situacao, consultar

    assert consultar("dcp", Capacidade.BAIXAR_INTEGRA).situacao is not (
        Situacao.NAO_SUPORTADO)


def test_o_motivo_do_dcp_diz_que_falta_o_adaptador_e_nao_o_portal():
    """O motivo nao pode culpar o portal pelo que e deste lado.

    A frase exigida mudou em 29/10/2026 junto com a situacao: nao se trata
    mais de "o portal baixa e o adaptador nao foi escrito", e sim do que foi
    MEDIDO em 20/10/2026, que o botao da integra existe e nao entrega em
    processo grande. O que o teste guarda continua sendo o mesmo: o texto
    atribui ao portal o que e do portal."""
    from justica_mcp.core.capabilities import consultar

    motivo = consultar("dcp", Capacidade.BAIXAR_INTEGRA).motivo.lower()
    assert "o portal oferece" in motivo
    assert "medido em" in motivo, "afirmacao sobre o portal precisa de data"


def test_o_que_a_fonte_realmente_nao_expoe_continua_nao_suportado():
    """A correcao do DCP nao afrouxa a matriz: o DataJud publica metadados e
    movimentos, e isso e desenho da fonte, nao falta de trabalho nosso."""
    from justica_mcp.core.capabilities import Situacao, consultar

    assert consultar("datajud", Capacidade.BAIXAR_INTEGRA).situacao is (
        Situacao.NAO_SUPORTADO)


def test_nenhuma_capacidade_do_dcp_ficou_sem_declaracao():
    """Toda capacidade do DCP tem situacao E motivo.

    A metade que exigia `is NAO_IMPLEMENTADO` saiu em 29/10/2026 pelo motivo
    descrito acima. O que o teste existe para impedir e uma capacidade MUDA,
    e isso continua guardado."""
    from justica_mcp.core.capabilities import consultar

    for capacidade in Capacidade:
        assert consultar("dcp", capacidade).motivo, capacidade


# --------------------------------------------------------------------------
# O 401 do DataJud precisa dizer POR QUE, sem mostrar a chave.
#
# Em 26/10/2026 um 401 custou uma noite: a mesma chave respondia 200 de duas
# maquinas, o valor no arquivo tinha os 60 caracteres exatos e o campo da
# extensao estava vazio. Faltava saber QUAL valor o servidor usava e de onde
# ele vinha. O 401 nem ramo proprio tinha: caia no `raise_for_status`.

def test_o_401_informa_o_comprimento_e_nao_a_chave():
    from justica_mcp.adapters.datajud import AdaptadorDataJud

    chave = "k" * 60
    texto = AdaptadorDataJud(chave=chave)._diagnostico_do_401()
    assert "60 caractere" in texto
    assert chave not in texto


def test_o_401_denuncia_molde_nao_substituido():
    from justica_mcp.adapters.datajud import AdaptadorDataJud

    texto = AdaptadorDataJud(
        chave="${user_config.chave_do_datajud}")._diagnostico_do_401()
    assert "MOLDE" in texto


def test_o_401_aponta_quando_o_ambiente_venceu_o_arquivo(tmp_path, monkeypatch):
    from justica_mcp.adapters import datajud as mod
    from justica_mcp.core import config as conf

    monkeypatch.setattr(conf, "raiz_do_pacote", lambda: tmp_path)
    (tmp_path / ".env").write_text(
        "DATAJUD_API_KEY=" + "a" * 60 + "\n", encoding="utf-8")
    monkeypatch.setenv("DATAJUD_API_KEY", "b" * 31)
    texto = mod.AdaptadorDataJud(chave="b" * 31)._diagnostico_do_401()
    assert "60 caractere(s), diferente" in texto
    assert "AMBIENTE" in texto


def test_sem_arquivo_nao_afirma_que_sao_iguais(tmp_path, monkeypatch):
    # "Nao achei diferenca" nao e "sao iguais": o arquivo pode nem existir.
    from justica_mcp.adapters import datajud as mod
    from justica_mcp.core import config as conf

    monkeypatch.setattr(conf, "raiz_do_pacote", lambda: tmp_path)
    texto = mod.AdaptadorDataJud(chave="c" * 60)._diagnostico_do_401()
    assert "nao sei dizer" in texto


# --------------------------------------------------------------------------
# Tempo esgotado na base nacional: o limite era curto demais.
#
# Medido na maquina do escritorio em 27/10/2026: a consulta por numero de
# processo levou 37,2s, contra fracao de segundo para uma consulta vazia no
# mesmo indice. O limite de 30s cortava antes da resposta, e o advogado lia
# "tempo esgotado" sobre uma interface que estava no ar.

def test_o_padrao_tem_folga_sobre_o_pior_observado():
    from justica_mcp.adapters.datajud import SEGUNDOS_PADRAO

    assert SEGUNDOS_PADRAO >= 37.2 * 2, (
        "o padrao precisa de folga sobre os 37,2s medidos em campo")


def test_o_operador_ajusta_sem_versao_nova(monkeypatch):
    from justica_mcp.adapters.datajud import tempo_limite

    monkeypatch.setenv("JUSTICA_DATAJUD_SEGUNDOS", "150")
    assert tempo_limite() == 150


def test_valor_torto_cai_no_padrao_em_vez_de_quebrar(monkeypatch):
    from justica_mcp.adapters.datajud import SEGUNDOS_PADRAO, tempo_limite

    for torto in ("abc", "", "0", "-5"):
        monkeypatch.setenv("JUSTICA_DATAJUD_SEGUNDOS", torto)
        assert tempo_limite() == SEGUNDOS_PADRAO, torto


def test_o_recado_do_tempo_esgotado_diz_quanto_e_como_mudar():
    import inspect

    from justica_mcp.adapters.datajud import AdaptadorDataJud

    # O texto e quebrado em varias linhas no fonte, entao as aspas e as
    # quebras saem antes da comparacao: o que se confere e a FRASE, e nao
    # como ela foi digitada.
    import re

    fonte = inspect.getsource(AdaptadorDataJud._buscar)
    frase = " ".join(re.sub(r'"\s*\n\s*"', "", fonte).split())
    assert "JUSTICA_DATAJUD_SEGUNDOS" in frase
    assert "nao respondeu em" in frase
    # E precisa dizer que repetir nao custa tentativa: senao o advogado
    # aplica a regra do "nao repita diante de erro", que vale para o portal
    # autenticado e nao para esta consulta.
    assert "nao custa tentativa de autenticacao" in frase


# ==========================================================================
# A matriz nao pode envelhecer em silencio
#
# Em 28/10/2026 o advogado pediu a consulta do DCP pela extensao e recebeu
# "DCP: nao implementado". Nao era verdade havia tres semanas: o adaptador
# vinha sendo escrito desde 06/10, e a declaracao ficou parada. `tools.py`
# instrui o assistente a DIZER QUE NAO DA quando a matriz diz
# `nao_implementado`, em vez de tentar, entao uma matriz atrasada nao gera um
# erro: gera uma recusa educada e falsa, que ninguem investiga.
#
# A matriz e uma afirmacao sobre o codigo. O codigo ja declara, em duas
# constantes, quais sistemas tem consulta. Os testes abaixo amarram a
# afirmacao as constantes, para que a proxima defasagem quebre uma linha
# vermelha em vez de chegar ao advogado.
# ==========================================================================

def test_quem_tem_consulta_no_codigo_nao_pode_dizer_que_nao_tem():
    """`SISTEMAS_COM_CONSULTA` e a lista do que a LINHA DE COMANDO aceita.
    Estar nela e ter o adaptador escrito, que e a definicao exata do que
    NAO_IMPLEMENTADO nega."""
    from justica_mcp.core.capabilities import MATRIZ, Situacao, consultar
    from justica_mcp.portal import SISTEMAS_COM_CONSULTA

    for sistema in sorted(SISTEMAS_COM_CONSULTA):
        assert sistema in MATRIZ, (
            f"{sistema!r} tem consulta no codigo e nao aparece na matriz; "
            "ausencia aqui vale como negativa, porque `consultar()` devolve "
            "NAO_IMPLEMENTADO para quem nao declara")
        decl = consultar(sistema, Capacidade.CONSULTAR_PROCESSO)
        assert decl.situacao is not Situacao.NAO_IMPLEMENTADO, (
            f"{sistema!r} esta em SISTEMAS_COM_CONSULTA e a matriz diz "
            "nao_implementado")
        assert decl.motivo, sistema


def test_quem_a_ferramenta_recusa_precisa_dizer_isso_no_motivo():
    """Os dois portoes nao sao o mesmo, e a diferenca e cara.

    `SISTEMAS_COM_CONSULTA` (`portal.py`) vale para a linha de comando e tem
    os quatro. `SISTEMAS_AUTENTICADOS` (`tools.py`) vale para a ferramenta do
    conector e tem so `dcp` e `eproc`: o e-SAJ e o PJe sao recusados antes de
    autenticar, de proposito.

    Declarar EXIGE_CREDENCIAL sem dizer por onde faria o assistente prometer
    ao advogado uma consulta que a ferramenta recusa em seguida, que e o erro
    de 28/10/2026 virado do avesso. Entao: quem a ferramenta nao aceita diz
    isso no proprio motivo.
    """
    from justica_mcp.core.capabilities import Situacao, consultar
    from justica_mcp.portal import SISTEMAS_COM_CONSULTA
    from justica_mcp.tools import SISTEMAS_AUTENTICADOS

    so_na_linha_de_comando = set(SISTEMAS_COM_CONSULTA) - set(SISTEMAS_AUTENTICADOS)
    assert so_na_linha_de_comando, (
        "se a ferramenta passar a aceitar os quatro, este teste perde o "
        "objeto e as ressalvas 'SO PELA LINHA DE COMANDO' precisam sair dos "
        "motivos")

    for sistema in sorted(so_na_linha_de_comando):
        decl = consultar(sistema, Capacidade.CONSULTAR_PROCESSO)
        assert decl.situacao is Situacao.EXIGE_CREDENCIAL, sistema
        assert "SO PELA LINHA DE COMANDO" in decl.motivo, (
            f"{sistema!r} e recusado pela ferramenta e o motivo nao avisa")


def test_quem_a_ferramenta_aceita_nao_leva_a_ressalva():
    """O contrario tambem engana: dizer 'so pela linha de comando' para o DCP
    faria o assistente deixar de usar a ferramenta que funciona."""
    from justica_mcp.core.capabilities import Capacidade, consultar
    from justica_mcp.tools import SISTEMAS_AUTENTICADOS

    for sistema in sorted(SISTEMAS_AUTENTICADOS):
        for capacidade in Capacidade:
            motivo = consultar(sistema, capacidade).motivo
            assert "SO PELA LINHA DE COMANDO" not in motivo, (
                f"{sistema!r}/{capacidade.value} e alcancado pela ferramenta")


# ==========================================================================
# NAO_SUPORTADO nao pode significar "nao quero"
#
# O preambulo da matriz diz, com todas as letras, que NAO_SUPORTADO e
# afirmacao sobre A FONTE: aquele portal nao oferece aquilo, e nenhum trabalho
# deste lado muda isso. Usa-lo para dizer "e ato de outra natureza e exige
# decisao do operador" poe na boca do servidor uma afirmacao falsa sobre o
# tribunal, e o advogado deixa de procurar no portal uma coisa que esta la.
#
# Era o que o eproc fazia, e o proprio motivo se denunciava: dizia "o portal
# OFERECE 'Download Completo', MAS ...". Quando o motivo precisa de um "mas"
# para sustentar a situacao, a situacao esta errada.
# ==========================================================================

def test_nenhum_motivo_de_nao_suportado_admite_que_a_fonte_oferece():
    """Guarda de coerencia interna, e nao de conteudo: uma declaracao que diz
    'a fonte nao expoe' nao pode, na mesma frase, dizer que ela expoe."""
    from justica_mcp.core.capabilities import MATRIZ, Situacao

    for sistema, capacidades in MATRIZ.items():
        for capacidade, decl in capacidades.items():
            if decl.situacao is not Situacao.NAO_SUPORTADO:
                continue
            baixo = decl.motivo.lower()
            for contradicao in ("o portal oferece", "o portal baixa",
                                "a fonte oferece"):
                assert contradicao not in baixo, (
                    f"{sistema}/{capacidade.value}: declarado NAO_SUPORTADO "
                    f"e o motivo diz {contradicao!r}. NAO_SUPORTADO fala da "
                    "fonte; se a fonte oferece, a recusa e deste lado")


def test_o_eproc_nao_nega_um_download_que_ele_faz():
    """Corrida registrada em 23/10/2026: copia integral do eproc, 2237 folhas.
    `_baixar_integra` existe em `portal.py` e o complemento baixa documento a
    documento. Declarar NAO_SUPORTADO para os dois era negar o que o programa
    faz todo dia."""
    from justica_mcp.core.capabilities import Situacao, consultar

    for capacidade in (Capacidade.BAIXAR_INTEGRA, Capacidade.BAIXAR_DOCUMENTO):
        assert consultar("eproc", capacidade).situacao is not (
            Situacao.NAO_SUPORTADO), capacidade
