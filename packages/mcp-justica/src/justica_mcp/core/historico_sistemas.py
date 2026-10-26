"""Historico da banca: em qual sistema cada processo foi encontrado.

Nasceu de uma conta ruim. O Tribunal de Justica do Rio de Janeiro opera tres
sistemas ao mesmo tempo, e descobrir em qual deles um processo corre custa
uma tentativa autenticada, de uma janela de dezoito por hora. Pagar esse
preco DUAS vezes pelo mesmo processo e desperdicio puro, e pagar uma vez por
advogado da banca e o mesmo desperdicio multiplicado.

Por isso o registro mora na PASTA DE COPIAS, que fica no Google Drive
compartilhado do escritorio, e nao no estado local de cada maquina: a
sondagem de um advogado economiza a tentativa de todos os outros.

CONFIRMACAO TEM DATA, e a data e dita em voz alta. A migracao move processo
de sistema; um registro de marco pode estar errado hoje. Guardar sem a data
seria transformar uma observacao de ontem numa afirmacao de sempre, que e
exatamente o erro que o resolvedor inteiro foi escrito para nao cometer.

Este arquivo contem numero de processo, que e dado de cliente. Ele vive na
pasta do escritorio, junto das copias dos autos, nunca no repositorio.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

NOME_DO_HISTORICO = "sistemas.json"
VERSAO = 1

# Janela em que a confirmacao ainda e tratada como recente. Valor de
# julgamento, nao numero medido: separa "confirmado ha pouco" de "confirmado
# ha tempo bastante para ter havido migracao".
DIAS_RECENTE = 30


def arquivo_do_historico() -> Path:
    from .acervo import pasta_de_copias

    return pasta_de_copias() / NOME_DO_HISTORICO


def carregar() -> dict:
    """O historico inteiro. Arquivo ausente ou ilegivel vira historico vazio.

    Ilegivel NAO levanta erro de proposito: o historico e uma economia, nao um
    requisito. Se ele quebrar, a consulta volta a custar uma tentativa, que e
    ruim; se ele derrubar a consulta, o advogado fica sem o processo, que e
    pior.
    """
    arquivo = arquivo_do_historico()
    try:
        bruto = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"versao": VERSAO, "processos": {}}
    processos = bruto.get("processos")
    if not isinstance(processos, dict):
        return {"versao": VERSAO, "processos": {}}
    return {"versao": bruto.get("versao", VERSAO), "processos": processos}


def consultar(digitos: str) -> Optional[dict]:
    """O que a banca ja sabe sobre este processo, ou None."""
    registro = carregar()["processos"].get(digitos)
    if not isinstance(registro, dict) or not registro.get("sistema"):
        return None
    return registro


def dias_desde(registro: dict) -> Optional[int]:
    quando = registro.get("confirmado_em")
    if not isinstance(quando, str):
        return None
    try:
        data = datetime.fromisoformat(quando.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - data).days


def recente(registro: dict) -> bool:
    dias = dias_desde(registro)
    return dias is not None and dias <= DIAS_RECENTE


def registrar(digitos: str, formatado: str, sistema: str, *,
              origem: str, por: Optional[str] = None) -> dict:
    """Grava a confirmacao, preservando o que ja houver no arquivo.

    A releitura imediatamente antes da escrita NAO e paranoia: a pasta e
    compartilhada e dois advogados podem sondar ao mesmo tempo. Sem ela, o
    segundo a gravar apagaria o achado do primeiro. Ainda assim o ultimo a
    escrever vence quando a colisao cai na mesma fracao de segundo, e isso e
    aceito: o custo e refazer uma sondagem, nao perder prova.
    """
    atual = carregar()
    atual["processos"][digitos] = {
        "formatado": formatado,
        "sistema": sistema,
        "origem": origem,
        "confirmado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "por": por,
    }
    _gravar(atual)
    return atual["processos"][digitos]


def esquecer(digitos: str, motivo: str) -> bool:
    """Tira o registro quando ele se mostrou errado.

    Chamado quando a consulta no sistema registrado NAO acha o processo: isso
    e indicio de migracao, e manter o registro mandaria o proximo advogado ao
    portal errado com a confianca de quem tem historico.
    """
    atual = carregar()
    saiu = atual["processos"].pop(digitos, None)
    if saiu is None:
        return False
    historico_de_erros = atual.setdefault("desfeitos", [])
    historico_de_erros.append({
        **saiu, "desfeito_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "motivo": motivo,
    })
    _gravar(atual)
    return True


def listar(teto: int = 200) -> list:
    processos = carregar()["processos"]
    itens = [{"digitos": d, **r} for d, r in processos.items()
             if isinstance(r, dict)]
    itens.sort(key=lambda i: i.get("confirmado_em") or "", reverse=True)
    return itens[:teto]


def _gravar(conteudo: dict) -> Path:
    """Escreve por arquivo temporario e troca, para o historico nunca ficar
    pela metade se a maquina cair ou o Drive interromper a escrita."""
    destino = arquivo_do_historico()
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(conteudo, ensure_ascii=False, indent=2)
    temporario = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=destino.parent, prefix=".sistemas-",
        suffix=".json", delete=False)
    try:
        temporario.write(texto)
        temporario.flush()
        os.fsync(temporario.fileno())
    finally:
        temporario.close()
    os.replace(temporario.name, destino)
    return destino
