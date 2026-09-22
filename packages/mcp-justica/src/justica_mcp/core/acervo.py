"""Acervo de copias: pasta por processo, com indice de folhas.

Regra de negocio definida pelo operador em 21 de setembro de 2026:

    Sem copia na pasta  -> baixa a INTEGRA.
    Com copia na pasta  -> baixa so o que falta, COMPLEMENTANDO, e informa
                           quais folhas o complemento cobre.

A numeracao de folhas e a da COPIA DA BANCA, continua e crescente: a integra
ocupa de 1 ate N, e cada complemento segue de N+1 em diante. Nao e a numeracao
do tribunal, que o eproc nem usa (la sao eventos). Serve para o advogado citar
"fls. 245/250 da copia" e achar o documento.

O indice fica na propria pasta do processo, em `indice.json`. Ele e a memoria
do que ja foi copiado: sem ele, todo complemento viraria copia repetida.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

NOME_INDICE = "indice.json"
VARIAVEL_PASTA = "JUSTICA_PASTA_COPIAS"


def pasta_de_copias() -> Path:
    """Raiz das copias. Padrao no diretorio de estado; o operador aponta para
    a pasta do escritorio, tipicamente dentro do Google Drive sincronizado."""
    from .estado import diretorio_estado

    bruto = os.environ.get(VARIAVEL_PASTA, "").strip()
    return Path(bruto).expanduser() if bruto else diretorio_estado() / "processos"


def pasta_do_processo(numero_digitos: str) -> Path:
    return pasta_de_copias() / numero_digitos


def garantir_pasta(numero_digitos: str) -> Path:
    """Cria a pasta do processo quando ainda nao existe, e a devolve.

    Antes a pasta so nascia no instante de gravar o primeiro arquivo. Uma
    consulta que nao copiasse nada nao deixava pasta nenhuma, e o advogado ia
    procurar no Drive um lugar que nunca foi criado. A pasta passa a existir
    desde a consulta, mesmo vazia: ela e o endereco do processo no acervo, nao
    um efeito colateral do download.
    """
    pasta = pasta_do_processo(numero_digitos)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def pdfs_fora_do_indice(indice: "Indice") -> list[str]:
    """Arquivos PDF na pasta que o indice nao conhece.

    A pasta de copias e do escritorio, compartilhada, e pode ja conter copias
    que alguem baixou a mao. Sem o indice nao ha como saber o que elas cobrem,
    e tratar a pasta como vazia por causa disso seria concluir demais a partir
    da ausencia de um arquivo de controle.
    """
    if not indice.pasta.is_dir():
        return []
    conhecidos = {Path(i.arquivo).name for i in indice.itens}
    return sorted(
        a.name for a in indice.pasta.iterdir()
        if a.is_file() and a.suffix.lower() == ".pdf" and a.name not in conhecidos
    )


def contar_paginas(arquivo: Path) -> Optional[int]:
    """Paginas de um PDF. Devolve None quando nao da para saber.

    Nao inventa numero: sem contagem confiavel, o indice registra a ausencia em
    vez de chutar, porque folha errada em citacao e pior que folha ausente.
    """
    if arquivo.suffix.lower() != ".pdf":
        return None
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(arquivo)).pages)
    except Exception:
        return None


def impressao_do_arquivo(arquivo: Path) -> Optional[str]:
    """Impressao digital do conteudo, para reconhecer copia repetida.

    Lida em pedacos: a integra de um processo grande nao cabe confortavelmente
    na memoria, e ler tudo de uma vez para calcular um resumo seria desperdicio
    em cima de arquivo que ja esta no disco.
    """
    import hashlib

    try:
        digestor = hashlib.sha256()
        with open(arquivo, "rb") as fonte:
            for pedaco in iter(lambda: fonte.read(1024 * 1024), b""):
                digestor.update(pedaco)
        return digestor.hexdigest()
    except OSError:
        return None


REPETIDA_IGUAL = "igual"
REPETIDA_SUSPEITA = "suspeita"
NOVA = "nova"


@dataclass
class Item:
    tipo: str                      # "integra" ou "documento"
    arquivo: str
    em: str
    paginas: Optional[int] = None
    folha_inicial: Optional[int] = None
    folha_final: Optional[int] = None
    evento: Optional[str] = None
    rotulo: Optional[str] = None
    # Para a integra: maior numero de evento existente quando ela foi tirada.
    # Sem isso o complemento recopia o processo inteiro, porque a integra ja
    # contem os documentos dos eventos anteriores a ela.
    evento_ate: Optional[int] = None
    # Resumo do conteudo, para reconhecer a mesma copia baixada duas vezes.
    # Nasceu vazio nos indices antigos, e e por isso que ele tem valor padrao.
    impressao: Optional[str] = None

    @property
    def chave(self) -> Optional[str]:
        """Identidade do documento no processo, para nao copiar duas vezes."""
        return f"{self.evento}|{self.rotulo}" if self.evento else None

    def faixa(self) -> str:
        if self.folha_inicial is None:
            return "folhas nao contadas"
        if self.folha_inicial == self.folha_final:
            return f"fl. {self.folha_inicial}"
        return f"fls. {self.folha_inicial}/{self.folha_final}"


@dataclass
class Indice:
    numero: str
    pasta: Path
    itens: list[Item] = field(default_factory=list)
    criado_em: Optional[str] = None

    @property
    def vazio(self) -> bool:
        return not self.itens

    @property
    def tem_integra(self) -> bool:
        return any(i.tipo == "integra" for i in self.itens)

    @property
    def ultima_folha(self) -> int:
        return max((i.folha_final or 0) for i in self.itens) if self.itens else 0

    @property
    def chaves_copiadas(self) -> set[str]:
        return {i.chave for i in self.itens if i.chave}

    @property
    def evento_coberto_pela_integra(self) -> int:
        """Ate qual evento a integra mais recente cobre. Zero se nao ha."""
        return max((i.evento_ate or 0) for i in self.itens) if self.itens else 0

    def avaliar_repeticao(self, arquivo: Path) -> tuple[str, Optional[Item]]:
        """Diz se este arquivo ja esta no acervo, antes de gastar numeracao.

        Em 22 de setembro de 2026 a integra do mesmo processo entrou duas
        vezes, e a segunda foi numerada como fls. 115/228: o acervo passou a
        dizer que o processo tem 228 folhas quando tem 114. Folha errada em
        citacao e o pior defeito possivel neste indice, porque o advogado cita
        "fls. 245/250 da copia" e o juiz procura no lugar que nao existe.

        Tres desfechos, e nao dois, porque as certezas sao diferentes:

        `igual`    o conteudo bate byte a byte. E a mesma copia, sem duvida.
        `suspeita` e uma integra com o mesmo numero de paginas de outra que ja
                   esta no acervo, mas o conteudo difere. Provavelmente e a
                   mesma copia com data de geracao diferente, coisa que o
                   proprio portal escreve dentro do PDF; pode tambem ser outra
                   coisa. Quem decide e o operador, nao este codigo.
        `nova`     nao se parece com nada que ja esteja aqui.
        """
        impressao = impressao_do_arquivo(arquivo)
        if impressao:
            for item in self.itens:
                if item.impressao and item.impressao == impressao:
                    return REPETIDA_IGUAL, item
        paginas = contar_paginas(arquivo)
        if paginas:
            for item in self.itens:
                if item.tipo == "integra" and item.paginas == paginas:
                    return REPETIDA_SUSPEITA, item
        return NOVA, None

    def acrescentar(
        self, arquivo: Path, tipo: str, *,
        evento: Optional[str] = None, rotulo: Optional[str] = None,
        evento_ate: Optional[int] = None,
    ) -> Item:
        paginas = contar_paginas(arquivo)
        inicial = final = None
        if paginas:
            inicial = self.ultima_folha + 1
            final = inicial + paginas - 1
        item = Item(
            tipo=tipo, arquivo=str(arquivo),
            em=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            paginas=paginas, folha_inicial=inicial, folha_final=final,
            evento=evento, rotulo=rotulo, evento_ate=evento_ate,
            impressao=impressao_do_arquivo(arquivo),
        )
        self.itens.append(item)
        return item

    def gravar(self) -> Path:
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino = self.pasta / NOME_INDICE
        destino.write_text(json.dumps({
            "numero": self.numero,
            "criado_em": self.criado_em or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "folhas_totais": self.ultima_folha,
            "itens": [vars(i) for i in self.itens],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return destino


def carregar_indice(numero_digitos: str, numero_formatado: str) -> Indice:
    pasta = pasta_do_processo(numero_digitos)
    arquivo = pasta / NOME_INDICE
    if not arquivo.is_file():
        return Indice(numero=numero_formatado, pasta=pasta)
    try:
        bruto = json.loads(arquivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Indice corrompido nao pode apagar o historico nem travar a copia:
        # segue como se estivesse vazio, e a gravacao o refaz.
        return Indice(numero=numero_formatado, pasta=pasta)
    return Indice(
        numero=bruto.get("numero", numero_formatado),
        pasta=pasta,
        criado_em=bruto.get("criado_em"),
        itens=[Item(**i) for i in bruto.get("itens", [])],
    )


def planejar_reindexacao(indice: "Indice") -> dict:
    """Monta o plano de refazer o indice a partir dos arquivos que existem.

    Nasceu de um estrago real: em 22/09/2026 a mesma integra entrou duas vezes
    e o indice passou a dizer 228 folhas num processo de 114. Consertar isso na
    mao significaria editar JSON, que e pedir para errar folha.

    O plano NAO e executado aqui. Quem varre e quem apaga sao passos separados
    de proposito: o operador le o que vai acontecer com os arquivos do
    escritorio antes de qualquer coisa acontecer.

    Regras:
      - arquivos de conteudo identico sao uma copia so; fica o mais antigo,
        que e o que ja pode ter sido citado, e os outros saem;
      - a numeracao e refeita na ordem de chegada dos que ficam;
      - o que o indice antigo sabia sobre um arquivo que fica (se e integra ou
        documento, o evento, o rotulo) e preservado, porque isso nao esta no
        PDF e seria perdido para sempre.
    """
    if not indice.pasta.is_dir():
        return {"manter": [], "apagar": [], "total": 0}

    arquivos = sorted(
        (a for a in indice.pasta.iterdir()
         if a.is_file() and a.suffix.lower() == ".pdf"),
        key=lambda a: (a.stat().st_mtime, a.name),
    )
    antigos = {Path(i.arquivo).name: i for i in indice.itens}

    manter: list[dict] = []
    apagar: list[dict] = []
    vistos: dict[str, Path] = {}
    folha = 0
    for arquivo in arquivos:
        impressao = impressao_do_arquivo(arquivo)
        if impressao and impressao in vistos:
            apagar.append({"arquivo": arquivo, "igual_a": vistos[impressao]})
            continue
        if impressao:
            vistos[impressao] = arquivo
        antigo = antigos.get(arquivo.name)
        paginas = contar_paginas(arquivo)
        inicial = final = None
        if paginas:
            inicial, final = folha + 1, folha + paginas
            folha = final
        manter.append({
            "arquivo": arquivo, "paginas": paginas,
            "folha_inicial": inicial, "folha_final": final,
            "impressao": impressao,
            "tipo": antigo.tipo if antigo else (
                "integra" if arquivo.name.startswith("integra") else "documento"),
            "evento": antigo.evento if antigo else None,
            "rotulo": antigo.rotulo if antigo else None,
            "evento_ate": antigo.evento_ate if antigo else None,
            "em": antigo.em if antigo else None,
        })
    return {"manter": manter, "apagar": apagar, "total": folha}


def aplicar_reindexacao(indice: "Indice", plano: dict, *, apagar_repetidos: bool) -> list[str]:
    """Executa o plano e devolve o que foi feito, linha por linha."""
    feito = []
    if apagar_repetidos:
        for repetido in plano["apagar"]:
            try:
                repetido["arquivo"].unlink()
                feito.append(f"apagado {repetido['arquivo'].name} "
                             f"(identico a {repetido['igual_a'].name})")
            except OSError as exc:
                feito.append(f"NAO consegui apagar {repetido['arquivo'].name}: {exc}")

    indice.itens = [
        Item(tipo=m["tipo"], arquivo=str(m["arquivo"]),
             em=m["em"] or datetime.now(timezone.utc).isoformat(timespec="seconds"),
             paginas=m["paginas"], folha_inicial=m["folha_inicial"],
             folha_final=m["folha_final"], evento=m["evento"], rotulo=m["rotulo"],
             evento_ate=m["evento_ate"], impressao=m["impressao"])
        for m in plano["manter"]
    ]
    feito.append(f"indice refeito com {len(indice.itens)} item(ns), "
                 f"{indice.ultima_folha} folha(s)")
    indice.gravar()
    return feito


def numero_do_evento(evento: dict) -> Optional[int]:
    bruto = str(evento.get("evento") or "").strip()
    return int(bruto) if bruto.isdigit() else None


def maior_evento(eventos: list[dict]) -> int:
    numeros = [n for n in (numero_do_evento(e) for e in eventos) if n is not None]
    return max(numeros) if numeros else 0


def decidir_estrategia(indice: Indice, eventos: list[dict]) -> dict[str, Any]:
    """Integra quando nao ha copia; complemento quando ha.

    O complemento traz apenas o que a copia existente NAO cobre. Dois filtros,
    e os dois sao necessarios:

    1. Eventos posteriores ao que a integra alcancou. A integra contem os
       documentos dos eventos anteriores a ela, e sem este filtro o complemento
       recopiaria o processo inteiro a cada consulta.
    2. Documentos ainda nao registrados no indice, para nao repetir os
       complementos anteriores.
    """
    if indice.vazio:
        return {"acao": "integra", "motivo": "Nao ha copia na pasta deste processo."}

    coberto = indice.evento_coberto_pela_integra
    faltantes = []
    for evento in eventos:
        numero = numero_do_evento(evento)
        if numero is not None and numero <= coberto:
            continue
        for documento in evento.get("documentos") or []:
            chave = f"{evento.get('evento')}|{documento.get('rotulo')}"
            if chave not in indice.chaves_copiadas:
                faltantes.append({"evento": evento, "documento": documento})

    alcance = f" A integra cobre ate o evento {coberto}." if coberto else ""
    return {
        "acao": "complemento",
        "faltantes": faltantes,
        "evento_coberto": coberto,
        "motivo": (
            f"Ja ha copia ate a folha {indice.ultima_folha}.{alcance} "
            f"{len(faltantes)} documento(s) por copiar."
            if faltantes else
            f"Ja ha copia ate a folha {indice.ultima_folha}.{alcance} Nada novo a copiar."
        ),
    }
