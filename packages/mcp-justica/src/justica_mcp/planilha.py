"""Importacao da planilha de credenciais da banca.

Existe para que o segredo NAO precise ser copiado e colado em lugar nenhum.
A leitura acontece na maquina do advogado, e o valor vai da celula direto para
o Gerenciador de Credenciais do sistema. Nada e impresso, nada trafega por
chat, nada vai para arquivo intermediario.

A planilha traz os rotulos do escritorio, que nao coincidem com os codigos do
projeto: a Justica Federal do Rio aparece como "JFRJ" e corresponde ao TRF2; o
Tribunal Regional do Trabalho aparece como "TRT RJ" e corresponde ao TRT1.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .core.cofre import Cofre, Identidade, SementeInvalida, normalizar_semente
from .core.tribunais import TRIBUNAIS

# Rotulo na planilha -> codigo do projeto.
_TRIBUNAIS = {
    "tjrj": "TJRJ",
    "tjsp": "TJSP",
    "jfrj": "TRF2",        # Justica Federal do Rio, sob a 2ª Regiao
    "jf rj": "TRF2",
    "trf2": "TRF2",
    "trt rj": "TRT1",      # Tribunal Regional do Trabalho da 1ª Regiao
    "trtrj": "TRT1",
    "trt1": "TRT1",
}
_SISTEMAS = {"pje": "pje", "eproc": "eproc", "esaj": "esaj", "e-saj": "esaj", "dcp": "dcp"}

COLUNAS = {
    "tribunal": ("tribunal",),
    "sistema": ("sistema",),
    "login": ("login", "usuario", "usuário"),
    "senha": ("senha", "password"),
    "semente": ("codigo autenticacao", "código autenticação", "autenticador", "2fa"),
}


def _normalizar(texto: object) -> str:
    bruto = str(texto or "").strip().lower()
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", bruto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento)


@dataclass
class Resultado:
    linha: int
    rotulo_planilha: str
    identidade: Optional[Identidade]
    login: bool = False
    senha: bool = False
    semente: bool = False
    observacao: str = ""

    @property
    def completa(self) -> bool:
        return self.login and self.senha and self.semente


class PlanilhaInvalida(ValueError):
    pass


def _mapear_colunas(cabecalho: list[str]) -> dict[str, int]:
    normalizado = [_normalizar(c) for c in cabecalho]
    indices: dict[str, int] = {}
    for campo, aceitos in COLUNAS.items():
        for i, nome in enumerate(normalizado):
            if nome in aceitos:
                indices[campo] = i
                break
    faltando = [c for c in COLUNAS if c not in indices]
    if faltando:
        raise PlanilhaInvalida(
            f"Colunas nao encontradas na planilha: {', '.join(faltando)}. "
            f"Cabecalho lido: {cabecalho}"
        )
    return indices


def resolver_caminho(caminho: Path) -> Path:
    """Aceita o arquivo ou a PASTA que o contem.

    Apontar a pasta e o mais natural para quem guarda a planilha num diretorio
    proprio, e evita errar o nome do arquivo. Com mais de uma planilha na
    pasta, a escolha volta para o operador em vez de o programa adivinhar.
    """
    caminho = caminho.expanduser()

    if caminho.is_file():
        return caminho

    if caminho.is_dir():
        encontrados = sorted(
            f for f in caminho.glob("*.xls*") if not f.name.startswith("~$")
        )
        if not encontrados:
            raise PlanilhaInvalida(
                f"Nenhuma planilha (.xlsx) encontrada na pasta {caminho}"
            )
        if len(encontrados) > 1:
            nomes = "\n    ".join(f.name for f in encontrados)
            raise PlanilhaInvalida(
                f"Ha {len(encontrados)} planilhas em {caminho}. Indique qual, "
                f"apontando o arquivo:\n    {nomes}"
            )
        return encontrados[0]

    raise PlanilhaInvalida(
        f"Nao encontrei nada em {caminho}. Confira o caminho; no PowerShell, "
        f"caminho com espaco ou acento precisa vir entre aspas."
    )


def importar(
    caminho: Path, cofre: Cofre, *, simular: bool = False
) -> list[Resultado]:
    """Le a planilha e grava no cofre. Nao imprime nem devolve valor algum."""
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise PlanilhaInvalida(
            "A leitura de planilha exige a biblioteca openpyxl. Rode: "
            'pip install -e ".[dev]"'
        ) from exc

    caminho = resolver_caminho(caminho)

    wb = openpyxl.load_workbook(caminho, data_only=True)
    linhas = list(wb.worksheets[0].iter_rows(values_only=True))
    if not linhas:
        raise PlanilhaInvalida("Planilha vazia.")

    idx = _mapear_colunas([str(c or "") for c in linhas[0]])
    pares_validos = {
        f"{t.codigo}:{s.value}" for t in TRIBUNAIS.values() for s in t.credencial_disponivel
    }

    resultados: list[Resultado] = []
    for n, linha in enumerate(linhas[1:], start=2):
        if not any(linha):
            continue

        bruto_tribunal = str(linha[idx["tribunal"]] or "").strip()
        bruto_sistema = str(linha[idx["sistema"]] or "").strip()
        rotulo = f"{bruto_tribunal} / {bruto_sistema}"

        codigo = _TRIBUNAIS.get(_normalizar(bruto_tribunal))
        sistema = _SISTEMAS.get(_normalizar(bruto_sistema))
        if codigo is None or sistema is None:
            resultados.append(Resultado(
                n, rotulo, None,
                observacao=f"Par nao reconhecido. Tribunais aceitos: {sorted(set(_TRIBUNAIS.values()))}.",
            ))
            continue

        identidade = Identidade(codigo, sistema)
        if identidade.chave not in pares_validos:
            resultados.append(Resultado(
                n, rotulo, identidade,
                observacao="Par fora do escopo declarado do projeto.",
            ))
            continue

        r = Resultado(n, rotulo, identidade)

        login = str(linha[idx["login"]] or "").strip()
        if login:
            if not simular:
                cofre.guardar_login(identidade, login)
            r.login = True

        senha = str(linha[idx["senha"]] or "")
        if senha.strip():
            if not simular:
                cofre.guardar_senha(identidade, senha)
            r.senha = True

        semente = str(linha[idx["semente"]] or "")
        if semente.strip():
            try:
                normalizar_semente(semente)
                if not simular:
                    cofre.guardar_semente(identidade, semente)
                r.semente = True
            except SementeInvalida as exc:
                # Caso real conhecido: a linha do portal legado do Rio traz um
                # campo de tres caracteres que nao e semente de autenticador.
                r.observacao = f"Segundo fator nao importado. {exc}"
        else:
            r.observacao = "Sem valor de segundo fator na planilha."

        resultados.append(r)
    return resultados
