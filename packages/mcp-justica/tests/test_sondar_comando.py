"""O comando `sondar`: uma autenticacao por sistema, e nenhuma por processo.

Nenhum teste aqui abre navegador. O autenticador e os enderecos dos portais
sao simulados; o que se mede e quantas vezes o autenticador foi CHAMADO, que
e o custo real da corrida na janela de dezoito tentativas por hora.
"""

from dataclasses import dataclass

import pytest

from justica_mcp import portal


@dataclass
class _Config:
    """Dublê da configuração do portal. Espelha `ConfigPortal` no que a
    sondagem usa, inclusive o endereço por grau: sem `url_2g`, só o primeiro
    grau é varrido, que é o caso comum do .env de hoje."""

    url: str = "https://portal.exemplo"
    perfil: str = None
    rotulo: str = "portal de teste"
    url_2g: str = None
    perfil_2g: str = None

    def url_do_grau(self, grau):
        return self.url_2g if grau == 2 else self.url

    def perfil_do_grau(self, grau):
        if grau == 2 and self.url_2g:
            return self.perfil_2g or self.perfil
        return self.perfil


UM = "0000001-16.2019.8.19.0001"
DOIS = "0000002-98.2019.8.19.0001"


@pytest.fixture
def portais(monkeypatch):
    """Todos os tres sistemas do Rio de Janeiro configurados.

    O preparo da sessao entra neutralizado: estes testes medem o LACO, e o
    preparo de verdade abre portal. Ele tem testes proprios, mais abaixo.
    """
    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", "1")
    monkeypatch.setattr("justica_mcp.core.acesso.config_portal",
                        lambda t, s: _Config())
    from justica_mcp.sondas import Preparo

    monkeypatch.setattr(
        "justica_mcp.sondas.preparar",
        lambda sistema, pagina, guarda, perfil, segundos:
            Preparo(pagina, True, "simulado"))
    return _Config()


def _autenticador(registro, achados):
    """Finge o login e roda o que viria depois, como o de verdade faz."""
    def autenticar(url, tribunal, sistema, *, apos_autenticar=None, **k):
        registro.append(sistema)
        if apos_autenticar is not None:
            apos_autenticar(_Pagina(), _Guarda(), _Estado(), _Identidade(tribunal))
        return 0
    return autenticar


class _Pagina:
    url = "https://portal.exemplo/x"


class _Guarda:
    pass


class _Estado:
    def registrar(self, **k):
        pass


@dataclass
class _Identidade:
    tribunal: str
    sistema: str = ""


def test_achado_no_primeiro_sistema_custa_uma_autenticacao(
        portais, monkeypatch, capsys):
    """A economia inteira do comando. O eproc e o primeiro da ordem; se tudo
    estiver la, PJe e DCP nunca sao abertos."""
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))
    monkeypatch.setattr(
        "justica_mcp.sondas.procurar",
        lambda sistema, *a, **k: __import__(
            "justica_mcp.sondas", fromlist=["Resposta"]
        ).Resposta(sistema == "eproc", "simulado"))

    codigo = portal.sondar_sistemas([UM, DOIS], confirmado=True)
    saida = capsys.readouterr().out
    assert codigo == 0
    assert logins == ["eproc"]
    assert "Autenticacoes gastas: 1" in saida
    assert "2 de 2 processo(s) resolvido(s)" in saida


def test_a_fila_encolhe_e_o_dcp_e_o_ultimo(portais, monkeypatch, capsys):
    logins: list = []
    vistos: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))

    from justica_mcp.sondas import Resposta

    def procurar(sistema, pagina, guarda, numero, url, segundos,
                 perfil=None):
        vistos.append((sistema, numero.formatado))
        achou = (sistema == "eproc" and numero.formatado == UM) or \
                (sistema == "dcp" and numero.formatado == DOIS)
        return Resposta(True if achou else None, "simulado")

    monkeypatch.setattr("justica_mcp.sondas.procurar", procurar)
    portal.sondar_sistemas([UM, DOIS], confirmado=True)
    assert logins == ["eproc", "pje", "dcp"]
    # O que foi achado no eproc nao e procurado de novo no PJe nem no DCP.
    assert [n for s, n in vistos if s == "eproc"] == [UM, DOIS]
    assert [n for s, n in vistos if s == "pje"] == [DOIS]
    assert [n for s, n in vistos if s == "dcp"] == [DOIS]


def test_sistema_sem_endereco_no_env_nao_conta_como_autenticacao(
        monkeypatch, capsys):
    """Deixa-lo dentro faria o relatorio contar um login que nunca houve e
    apresentar como 'nao achado' um sistema onde ninguem buscou."""
    from justica_mcp.core.acesso import PortalNaoConfigurado

    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", "1")

    def config(tribunal, sistema):
        if sistema == "eproc":
            return _Config()
        raise PortalNaoConfigurado(tribunal, sistema)

    monkeypatch.setattr("justica_mcp.core.acesso.config_portal", config)
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))

    from justica_mcp.sondas import Resposta

    monkeypatch.setattr("justica_mcp.sondas.procurar",
                        lambda *a, **k: Resposta(True, "simulado"))
    codigo = portal.sondar_sistemas([UM], confirmado=True)
    saida = capsys.readouterr().out
    assert codigo == 0
    assert logins == ["eproc"]
    assert "FORA: pje nao sera sondado" in saida
    assert "FORA: dcp nao sera sondado" in saida


def test_sem_nenhum_portal_configurado_nao_abre_navegador(monkeypatch):
    from justica_mcp.core.acesso import PortalNaoConfigurado

    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", "1")
    monkeypatch.setattr(
        "justica_mcp.core.acesso.config_portal",
        lambda t, s: (_ for _ in ()).throw(PortalNaoConfigurado(t, s)))
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))
    assert portal.sondar_sistemas([UM], confirmado=True) == 1
    assert logins == []


def test_acesso_autenticado_desligado_recusa_antes_de_tudo(monkeypatch):
    monkeypatch.delenv("JUSTICA_ACESSO_AUTENTICADO", raising=False)
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))
    assert portal.sondar_sistemas([UM], confirmado=True) == 1
    assert logins == []


def test_numero_invalido_recusa_antes_de_abrir_navegador(portais, monkeypatch):
    """Numero errado descoberto no meio da corrida ja custou a autenticacao."""
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))
    assert portal.sondar_sistemas([UM, "1234"], confirmado=True) == 1
    assert logins == []


def test_tribunais_misturados_recusam_antes_de_olhar_configuracao(
        portais, monkeypatch, capsys):
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))
    codigo = portal.sondar_sistemas([UM, "0000002-97.2019.8.26.0100"],
                                    confirmado=True)
    assert codigo == 1
    assert logins == []


def test_sonda_que_nao_confirma_nao_vira_nao_esta_aqui(
        portais, monkeypatch, capsys):
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))

    from justica_mcp.sondas import Resposta

    monkeypatch.setattr(
        "justica_mcp.sondas.procurar",
        lambda *a, **k: Resposta(None, "a tela nao montou."))
    portal.sondar_sistemas([UM], confirmado=True)
    saida = capsys.readouterr().out
    assert "nao confirmado" in saida
    assert "0 de 1 processo(s) resolvido(s)" in saida
    assert "nao conseguiu responder" in saida


# --------------------------------------------------------------------------
# A corrida nao pode acontecer dentro de laco assincrono
# --------------------------------------------------------------------------

def test_o_autenticador_nunca_e_chamado_dentro_de_laco_assincrono(
        portais, monkeypatch):
    """A primeira corrida real, em 26/10/2026, morreu em `sync_playwright()`
    com "Playwright Sync API inside the asyncio loop": a sondagem era `async`
    por simetria com o resolvedor, e a sonda de verdade abre navegador.

    Os testes de entao nao pegaram porque o autenticador simulado deles nao
    tinha a restricao. Este tem: ele recusa exatamente como a biblioteca do
    navegador recusa.
    """
    import asyncio

    from justica_mcp.sondas import Resposta

    def autenticar(url, tribunal, sistema, *, apos_autenticar=None, **k):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Playwright Sync API inside the asyncio loop")
        if apos_autenticar is not None:
            apos_autenticar(_Pagina(), _Guarda(), _Estado(), _Identidade(tribunal))
        return 0

    monkeypatch.setattr(portal, "autenticar", autenticar)
    monkeypatch.setattr("justica_mcp.sondas.procurar",
                        lambda *a, **k: Resposta(True, "simulado"))
    assert portal.sondar_sistemas([UM], confirmado=True) == 0


def test_o_miolo_da_sondagem_nao_e_assincrono():
    """Guarda do mesmo conserto, um degrau abaixo: se alguem tornar
    `sondar_em_lote` assincrona de novo, a corrida volta a morrer no
    navegador, e nao aqui."""
    import inspect

    from justica_mcp.core.sondagem import sondar_em_lote

    assert not inspect.iscoroutinefunction(sondar_em_lote)


# --------------------------------------------------------------------------
# O preparo da sessao, que o Portal de Servicos exige
# --------------------------------------------------------------------------

def test_o_preparo_corre_uma_vez_por_sessao_e_nao_por_processo(
        monkeypatch, capsys):
    """Repetir por processo seria entrar no portal quatro vezes para fazer
    quatro buscas."""
    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", "1")
    monkeypatch.setattr("justica_mcp.core.acesso.config_portal",
                        lambda t, s: _Config())
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))

    from justica_mcp.sondas import Preparo, Resposta

    preparos: list = []

    def preparar(sistema, pagina, guarda, perfil, segundos):
        preparos.append(sistema)
        return Preparo(pagina, True, "simulado")

    monkeypatch.setattr("justica_mcp.sondas.preparar", preparar)
    monkeypatch.setattr("justica_mcp.sondas.procurar",
                        lambda *a, **k: Resposta(None, "simulado"))
    portal.sondar_sistemas([UM, DOIS], confirmado=True)
    # Dois processos, tres sistemas: tres preparos, nao seis.
    assert preparos == ["eproc", "pje", "dcp"]


def test_sessao_que_nao_ficou_pronta_nao_procura_nada_e_nao_afirma_ausencia(
        monkeypatch, capsys):
    """Em 26/10/2026 a sonda do Portal de Servicos pulou a entrada no portal
    e as quatro buscas estouraram. O que nao pode acontecer e isso virar
    'nao esta aqui' para os quatro."""
    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", "1")
    monkeypatch.setattr("justica_mcp.core.acesso.config_portal",
                        lambda t, s: _Config())
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))

    from justica_mcp.sondas import Preparo, Resposta

    monkeypatch.setattr(
        "justica_mcp.sondas.preparar",
        lambda sistema, pagina, guarda, perfil, segundos:
            Preparo(pagina, False, "nao deu para entrar no portal"))
    procuras: list = []

    def procurar(sistema, *a, **k):
        procuras.append(sistema)
        return Resposta(True, "nao deveria ter sido chamada")

    monkeypatch.setattr("justica_mcp.sondas.procurar", procurar)
    portal.sondar_sistemas([UM], confirmado=True)
    saida = capsys.readouterr().out
    assert procuras == []
    assert "A sessao nao ficou pronta" in saida
    assert "0 de 1 processo(s) resolvido(s)" in saida


def test_a_varredura_liga_a_gravacao_de_telas_sozinha(portais, monkeypatch):
    """Enquanto a sonda nao souber reconhecer o 'nada encontrado', a tela
    gravada E metade do resultado. Deixar isso a cargo de uma variavel de
    ambiente custou tres autenticacoes e uma colheita vazia em 26/10/2026."""
    import os

    monkeypatch.delenv("JUSTICA_GRAVAR_TELAS", raising=False)
    monkeypatch.setattr(portal, "autenticar", _autenticador([], None))

    from justica_mcp.sondas import Resposta

    monkeypatch.setattr("justica_mcp.sondas.procurar",
                        lambda *a, **k: Resposta(True, "simulado"))
    portal.sondar_sistemas([UM], confirmado=True)
    assert os.environ.get("JUSTICA_GRAVAR_TELAS")


# --------------------------------------------------------------------------
# Primeiro e segundo grau sao portais diferentes
#
# O numero NAO diz a instancia atual: recurso processado nos autos principais,
# como a apelacao, sobe com o mesmo numero (Resolucao nº. 65/2008, artigo 3º,
# § 2º). Entre 25 e 26/10/2026 quatro varreduras procuraram dois processos so
# em primeira instancia, porque nenhum endereco de segundo grau estava no
# .env, e devolveram "nao achado" sem nunca ter olhado la.
# --------------------------------------------------------------------------

def test_sem_endereco_de_segundo_grau_so_o_primeiro_e_varrido(
        portais, monkeypatch, capsys):
    """E o .env de hoje: um endereco por sistema, todos de primeiro grau. O
    custo nao muda, e o relatorio diz que o segundo grau ficou de fora."""
    logins: list = []
    monkeypatch.setattr(portal, "autenticar", _autenticador(logins, None))

    from justica_mcp.sondas import Resposta

    monkeypatch.setattr("justica_mcp.sondas.procurar",
                        lambda *a, **k: Resposta(True, "simulado"))
    portal.sondar_sistemas([UM], confirmado=True)
    saida = capsys.readouterr().out
    assert logins == ["eproc"]
    assert "SEM 2o GRAU: eproc" in saida
    assert "_EPROC_2G_URL" in saida


def test_com_endereco_de_segundo_grau_o_outro_grau_vira_etapa(
        monkeypatch, capsys):
    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", "1")
    monkeypatch.setattr(
        "justica_mcp.core.acesso.config_portal",
        lambda t, s: _Config(url_2g="https://portal.exemplo/2g")
        if s == "eproc" else _Config())
    from justica_mcp.sondas import Preparo, Resposta

    monkeypatch.setattr(
        "justica_mcp.sondas.preparar",
        lambda sistema, pagina, guarda, perfil, segundos:
            Preparo(pagina, True, "simulado"))
    enderecos: list = []

    def autenticar(url, tribunal, sistema, *, apos_autenticar=None, **k):
        enderecos.append((sistema, url))
        if apos_autenticar is not None:
            apos_autenticar(_Pagina(), _Guarda(), _Estado(), _Identidade(tribunal))
        return 0

    monkeypatch.setattr(portal, "autenticar", autenticar)
    monkeypatch.setattr("justica_mcp.sondas.procurar",
                        lambda *a, **k: Resposta(False, "simulado"))
    portal.sondar_sistemas([UM], confirmado=True)
    # Todos os sistemas em primeiro grau e, depois, o eproc em segundo, que e
    # o unico com endereco proprio.
    assert enderecos == [
        ("eproc", "https://portal.exemplo"),
        ("pje", "https://portal.exemplo"),
        ("dcp", "https://portal.exemplo"),
        ("eproc", "https://portal.exemplo/2g"),
    ]


def test_o_relatorio_avisa_quando_so_o_primeiro_grau_foi_olhado(
        portais, monkeypatch, capsys):
    """Nao dizer isto faria "nao achado em primeiro grau" parecer "nao
    existe", que e o pior desfecho deste programa."""
    monkeypatch.setattr(portal, "autenticar", _autenticador([], None))

    from justica_mcp.sondas import Resposta

    monkeypatch.setattr("justica_mcp.sondas.procurar",
                        lambda *a, **k: Resposta(False, "ausencia confirmada"))
    portal.sondar_sistemas([UM], confirmado=True)
    saida = capsys.readouterr().out
    assert "SO EM PRIMEIRO GRAU" in saida
    assert "nao diz a instancia atual" in saida
