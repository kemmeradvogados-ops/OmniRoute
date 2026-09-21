"""Estado local: cache com validade, snapshots para diferenca e auditoria.

Tudo em SQLite num diretorio do operador. Sem servico externo, porque o dado
processual da banca nao deve sair da maquina do escritorio.
"""

from __future__ import annotations

import json
import os
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS cache (
    chave       TEXT PRIMARY KEY,
    valor       TEXT NOT NULL,
    gravado_em  TEXT NOT NULL,
    valido_ate  TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
    numero      TEXT NOT NULL,
    coletado_em TEXT NOT NULL,
    impressao   TEXT NOT NULL,
    conteudo    TEXT NOT NULL,
    PRIMARY KEY (numero, coletado_em)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_numero ON snapshots(numero, coletado_em DESC);
CREATE TABLE IF NOT EXISTS auditoria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ocorrido_em TEXT NOT NULL,
    solicitante TEXT,
    acao        TEXT NOT NULL,
    tribunal    TEXT,
    sistema     TEXT,
    numero      TEXT,
    documento   TEXT,
    resultado   TEXT,
    detalhe     TEXT
);
CREATE INDEX IF NOT EXISTS idx_auditoria_data ON auditoria(ocorrido_em DESC);
"""


def diretorio_estado() -> Path:
    bruto = os.environ.get("JUSTICA_MCP_HOME")
    base = Path(bruto).expanduser() if bruto else Path.home() / ".justica-mcp"
    base.mkdir(parents=True, exist_ok=True)
    return base


class Estado:
    def __init__(self, caminho: Optional[Path] = None) -> None:
        self.caminho = caminho or (diretorio_estado() / "estado.sqlite3")
        with self._conectar() as cx:
            cx.executescript(_ESQUEMA)

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        cx = sqlite3.connect(self.caminho)
        cx.row_factory = sqlite3.Row
        try:
            yield cx
            cx.commit()
        finally:
            cx.close()

    # ---------------- cache ----------------

    def obter_cache(self, chave: str) -> Optional[dict[str, Any]]:
        """Devolve o registro ou None. Registro vencido nao e apagado em silencio:
        volta com `vencido=True` para quem chamou decidir, e para o contrato de
        resposta poder marcar confianca baixa."""
        with self._conectar() as cx:
            linha = cx.execute("SELECT * FROM cache WHERE chave = ?", (chave,)).fetchone()
        if linha is None:
            return None
        vencido = bool(
            linha["valido_ate"]
            and datetime.fromisoformat(linha["valido_ate"]) < datetime.now(timezone.utc)
        )
        return {
            "valor": json.loads(linha["valor"]),
            "gravado_em": linha["gravado_em"],
            "valido_ate": linha["valido_ate"],
            "vencido": vencido,
        }

    def gravar_cache(self, chave: str, valor: Any, validade: Optional[timedelta] = None) -> str:
        agora = datetime.now(timezone.utc)
        valido_ate = (agora + validade).isoformat(timespec="seconds") if validade else None
        with self._conectar() as cx:
            cx.execute(
                "INSERT INTO cache (chave, valor, gravado_em, valido_ate) VALUES (?,?,?,?) "
                "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, "
                "gravado_em=excluded.gravado_em, valido_ate=excluded.valido_ate",
                (chave, json.dumps(valor, ensure_ascii=False), agora.isoformat(timespec="seconds"), valido_ate),
            )
        return valido_ate or ""

    # ---------------- snapshots ----------------

    @staticmethod
    def impressao(conteudo: Any) -> str:
        bruto = json.dumps(conteudo, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()

    def gravar_snapshot(self, numero: str, conteudo: Any) -> dict[str, Any]:
        """Grava so quando mudou, para o historico virar linha do tempo real."""
        impressao = self.impressao(conteudo)
        anterior = self.ultimo_snapshot(numero)
        if anterior and anterior["impressao"] == impressao:
            return {"mudou": False, "impressao": impressao, "coletado_em": anterior["coletado_em"]}
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conectar() as cx:
            cx.execute(
                "INSERT OR REPLACE INTO snapshots (numero, coletado_em, impressao, conteudo) VALUES (?,?,?,?)",
                (numero, agora, impressao, json.dumps(conteudo, ensure_ascii=False)),
            )
        return {"mudou": True, "impressao": impressao, "coletado_em": agora, "primeiro": anterior is None}

    def ultimo_snapshot(self, numero: str) -> Optional[dict[str, Any]]:
        with self._conectar() as cx:
            linha = cx.execute(
                "SELECT * FROM snapshots WHERE numero = ? ORDER BY coletado_em DESC LIMIT 1", (numero,)
            ).fetchone()
        if linha is None:
            return None
        return {
            "coletado_em": linha["coletado_em"],
            "impressao": linha["impressao"],
            "conteudo": json.loads(linha["conteudo"]),
        }

    # ---------------- auditoria ----------------

    def registrar(
        self,
        *,
        acao: str,
        solicitante: Optional[str] = None,
        tribunal: Optional[str] = None,
        sistema: Optional[str] = None,
        numero: Optional[str] = None,
        documento: Optional[str] = None,
        resultado: Optional[str] = None,
        detalhe: Optional[str] = None,
    ) -> None:
        """Registro obrigatorio por chamada. Nunca recebe credencial."""
        with self._conectar() as cx:
            cx.execute(
                "INSERT INTO auditoria (ocorrido_em, solicitante, acao, tribunal, sistema, "
                "numero, documento, resultado, detalhe) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    solicitante, acao, tribunal, sistema, numero, documento, resultado, detalhe,
                ),
            )

    def auditoria_recente(self, limite: int = 50) -> list[dict[str, Any]]:
        with self._conectar() as cx:
            linhas = cx.execute(
                "SELECT * FROM auditoria ORDER BY ocorrido_em DESC, id DESC LIMIT ?", (limite,)
            ).fetchall()
        return [dict(linha) for linha in linhas]
