

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
