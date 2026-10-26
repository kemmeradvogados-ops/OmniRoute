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
    url: str = "https://portal.exemplo"
    perfil: str = None
    rotulo: str = "portal de teste"


UM = "0000001-16.2019.8.19.0001"
DOIS = "0000002-98.2019.8.19.0001"


@pytest.fixture
def portais(monkeypatch):
    """Todos os tres sistemas do Rio de Janeiro configurados."""
    monkeypatch.setenv("JUSTICA_ACESSO_AUTENTICADO", "1")
    monkeypatch.setattr("justica_mcp.core.acesso.config_portal",
                        lambda t, s: _Config())
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

    def procurar(sistema, pagina, guarda, numero, url, segundos):
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
