

# --------------------------------------------------------------------------
# O comando colado no lugar do login
#
# Em 22/09/2026 o operador colou a linha de comando seguinte no prompt de
# login e ela foi gravada como se fosse a inscricao dele. O login do portal
# ficou corrompido em silencio, e o proximo acesso teria gasto uma tentativa
# do teto da conta para enviar um texto que nao e login nenhum.
# --------------------------------------------------------------------------

def test_linha_de_comando_colada_nao_vira_login():
    from justica_mcp.credenciais import motivo_para_recusar_login

    colado = r".venv\Scripts\justica-portal autenticar --tribunal TJRJ --sistema pje"
    assert motivo_para_recusar_login(colado)


def test_caminho_de_arquivo_nao_vira_login():
    from justica_mcp.credenciais import motivo_para_recusar_login

    assert motivo_para_recusar_login(r"C:\Users\Fulano\senha.txt")
    assert motivo_para_recusar_login("/home/fulano/senha")


def test_logins_de_verdade_passam():
    """Inscricao da Ordem, cadastro de pessoa fisica e matricula de portal."""
    from justica_mcp.credenciais import motivo_para_recusar_login

    for bom in ("218174", "12345678900", "FICUS00002", "advogado.teste"):
        assert motivo_para_recusar_login(bom) == "", bom


def test_texto_longo_demais_nao_vira_login():
    from justica_mcp.credenciais import motivo_para_recusar_login

    assert motivo_para_recusar_login("x" * 61)


# --------------------------------------------------------------------------
# A senha que vem do cofre de senhas
#
# Em 22/09/2026 o operador ficou impedido de gravar: ele guarda as senhas num
# cofre de senhas e precisa COLAR, e o prompt cego do terminal nao aceita
# colar em varios terminais do Windows. Digitar a mao uma senha longa, as
# cegas, e o caminho mais curto para grava-la errada.
# --------------------------------------------------------------------------

def test_a_janela_pede_duas_vezes_e_devolve_o_valor():
    from justica_mcp.credenciais import pedir_em_janela

    pedidos = []

    def janela_falsa(titulo, mensagem):
        pedidos.append(mensagem)
        return "senha-do-cofre"

    assert pedir_em_janela("Senha do portal", _construtor=janela_falsa) == "senha-do-cofre"
    assert len(pedidos) == 2


def test_digitacoes_diferentes_na_janela_nao_gravam_nada():
    from justica_mcp.credenciais import pedir_em_janela

    valores = iter(["uma", "outra"])

    assert pedir_em_janela("Senha", _construtor=lambda t, m: next(valores)) == ""


def test_cancelar_a_janela_nao_vira_senha_vazia():
    """Cancelar e diferente de digitar nada: gravar senha vazia deixaria o
    portal recusando o acesso sem ninguem entender por que."""
    from justica_mcp.credenciais import pedir_em_janela

    assert pedir_em_janela("Senha", _construtor=lambda t, m: None) is None


def test_a_semente_e_pedida_uma_vez_so():
    """Semente e codigo longo que se cola do QR Code: repetir a digitacao nao
    protege nada e so atrapalha."""
    from justica_mcp.credenciais import pedir_em_janela

    pedidos = []

    def janela_falsa(titulo, mensagem):
        pedidos.append(mensagem)
        return "ABCDEFGH"

    pedir_em_janela("Semente", confirmar=False, _construtor=janela_falsa)
    assert len(pedidos) == 1


# --------------------------------------------------------------------------
# Cada "--so-alguma-coisa" grava exatamente aquilo
#
# Consertar um pedaco da credencial nao pode obrigar a redigitar os outros:
# cada redigitacao e uma chance de errar, e foi assim que o login do PJe se
# perdeu em 22/09/2026.
# --------------------------------------------------------------------------

class _CofreFalso:
    def __init__(self):
        self.gravados = []

    def guardar_login(self, identidade, valor):
        self.gravados.append("login")

    def guardar_senha(self, identidade, valor):
        self.gravados.append("senha")

    def guardar_semente(self, identidade, valor):
        self.gravados.append("semente")

    def _codigo_segundo_fator(self, identidade):
        return "123456"


def _guardar(monkeypatch, **flags):
    from justica_mcp import credenciais as mod

    cofre = _CofreFalso()
    monkeypatch.setattr("builtins.input", lambda _: "218174")
    monkeypatch.setattr(mod, "pedir_segredo", lambda *a, **kw: "segredo")
    mod.cmd_guardar(cofre, "TJRJ", "pje", flags.get("so_senha", False),
                    flags.get("so_semente", False), False, flags.get("so_login", False))
    return cofre.gravados


def test_so_login_grava_so_o_login(monkeypatch):
    assert _guardar(monkeypatch, so_login=True) == ["login"]


def test_so_senha_grava_so_a_senha(monkeypatch):
    assert _guardar(monkeypatch, so_senha=True) == ["senha"]


def test_so_semente_grava_so_a_semente(monkeypatch):
    assert _guardar(monkeypatch, so_semente=True) == ["semente"]


def test_sem_escolha_grava_as_tres_pecas(monkeypatch):
    assert _guardar(monkeypatch) == ["login", "senha", "semente"]
