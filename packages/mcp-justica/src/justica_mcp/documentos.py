"""Copia de documentos do processo.

DECISAO CENTRAL: os documentos sao buscados pelo ENDERECO, reaproveitando a
sessao autenticada, e nao clicando nos links da tela.

Clicar seria o caminho obvio, e e o pior. Um clique pode abrir aba, disparar
script, cair em elemento vizinho ou levar a tela que nao se pretendia visitar,
e este projeto existe porque um clique errado no portal custa caro. Buscar pelo
endereco nao clica em nada, nao navega, nao muda a pagina: usa os mesmos
cookies da sessao para pedir o arquivo e pronto.

O que este modulo NAO faz: nao toca no painel de expedientes e nao abre
intimacao pendente. Os documentos vem da lista de eventos, que sao os autos.

[Nao verificado] Se baixar documento do proprio processo produz algum registro
de ciencia no eproc. A leitura do artigo 5º, §3º, da lei nº. 11.419/06 e que a
ciencia se da pela consulta ao teor da COMUNICACAO, no painel de expedientes,
e nao pela leitura dos autos. Ainda assim, a primeira execucao merece
conferencia do advogado no proprio portal.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

# Eventos cuja descricao sugere comunicacao processual. Nao sao bloqueados,
# porque documento de evento e parte dos autos, mas vao sinalizados no relato
# para o advogado conferir o que foi copiado.
_PISTAS_COMUNICACAO = ("intimacao", "citacao", "expedient", "comunicacao eletronica")

_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def nome_de_arquivo(evento: str, rotulo: str, extensao: str) -> str:
    """Nome previsivel e ordenavel, seguro em qualquer sistema de arquivos."""
    limpo = _INVALIDOS.sub("-", _sem_acento(rotulo)).strip(" .-") or "documento"
    return f"ev{str(evento).zfill(4)}-{limpo[:60]}{extensao}"


def _extensao(resposta: Any, endereco: str) -> str:
    tipo = (resposta.headers.get("content-type") or "").split(";")[0].strip().lower()
    por_tipo = {
        "application/pdf": ".pdf", "text/html": ".html", "image/jpeg": ".jpg",
        "image/png": ".png", "application/zip": ".zip",
        "application/octet-stream": ".bin",
    }
    if tipo in por_tipo:
        return por_tipo[tipo]
    achado = re.search(r"\.(pdf|html?|jpe?g|png|zip|docx?|rtf)(?:$|\?)", endereco, re.I)
    return f".{achado.group(1).lower()}" if achado else ".bin"


def parece_comunicacao(descricao: str) -> bool:
    texto = _sem_acento((descricao or "").lower())
    return any(p in texto for p in _PISTAS_COMUNICACAO)


@dataclass
class Copia:
    evento: str
    rotulo: str
    arquivo: Optional[str] = None
    bytes_gravados: int = 0
    de_comunicacao: bool = False
    erro: Optional[str] = None


@dataclass
class Resultado:
    pasta: Path
    copias: list[Copia] = field(default_factory=list)
    eventos_sem_documento: int = 0

    @property
    def gravadas(self) -> list[Copia]:
        return [c for c in self.copias if c.arquivo]

    @property
    def falhas(self) -> list[Copia]:
        return [c for c in self.copias if c.erro]

    def resumo(self) -> list[str]:
        linhas = [
            f"copiados: {len(self.gravadas)}   falhas: {len(self.falhas)}   "
            f"eventos sem documento: {self.eventos_sem_documento}",
        ]
        comunicacoes = [c for c in self.gravadas if c.de_comunicacao]
        if comunicacoes:
            linhas.append(
                f"{len(comunicacoes)} documento(s) vieram de evento de comunicacao "
                f"processual; confira no portal se era o esperado."
            )
        for c in self.falhas[:5]:
            linhas.append(f"  falhou ev{c.evento} {c.rotulo}: {c.erro}")
        return linhas


def baixar_documentos_dos_eventos(
    pagina: Any,
    guarda: Any,
    eventos: list[dict],
    destino: Path,
    *,
    quantos_eventos: int,
) -> Resultado:
    """Copia os documentos dos N eventos mais recentes.

    A lista de eventos ja vem do mais recente para o mais antigo, como o portal
    a apresenta.
    """
    from .core.guarda_navegacao import Acao

    destino.mkdir(parents=True, exist_ok=True)
    resultado = Resultado(pasta=destino)

    for evento in eventos[:quantos_eventos]:
        documentos = evento.get("documentos") or []
        if not documentos:
            resultado.eventos_sem_documento += 1
            continue
        de_comunicacao = parece_comunicacao(evento.get("descricao", ""))

        for documento in documentos:
            copia = Copia(
                evento=evento.get("evento", "?"),
                rotulo=documento.get("rotulo", "documento"),
                de_comunicacao=de_comunicacao,
            )
            endereco = documento.get("endereco") or ""
            if not endereco or endereco.lower().startswith("javascript:"):
                copia.erro = "sem endereco direto; o link depende de script da pagina"
                resultado.copias.append(copia)
                continue

            absoluto = urljoin(pagina.url, endereco)
            decisao = guarda.avaliar(Acao.BAIXAR, absoluto, url=absoluto)
            if not decisao.permitido:
                copia.erro = decisao.motivo
                resultado.copias.append(copia)
                continue

            try:
                # Pelo endereco, com os cookies da sessao. Nao clica, nao
                # navega, nao muda a pagina.
                resposta = pagina.context.request.get(absoluto, timeout=60000)
                if not resposta.ok:
                    copia.erro = f"HTTP {resposta.status}"
                    resultado.copias.append(copia)
                    continue
                conteudo = resposta.body()
                arquivo = destino / nome_de_arquivo(
                    copia.evento, copia.rotulo, _extensao(resposta, absoluto)
                )
                arquivo.write_bytes(conteudo)
                copia.arquivo = str(arquivo)
                copia.bytes_gravados = len(conteudo)
            except Exception as exc:
                copia.erro = f"{type(exc).__name__}: {exc}"
            resultado.copias.append(copia)

    return resultado
