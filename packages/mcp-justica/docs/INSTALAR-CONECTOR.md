# Instalar o `justica_mcp` como conector do Claude

Guia escrito em 22/10/2026 para colocar em uso **o que já está pronto**,
enquanto o restante é terminado. Ele diz, ferramenta por ferramenta, o que foi
provado em corrida real e o que não foi, porque instalar sem essa separação é
instalar uma promessa.

> **Um servidor, não quatro.** O `justica_mcp` é um servidor só, que atende os
> quatro sistemas (Portal de Serviços do Rio de Janeiro, eproc, e-SAJ e PJe).
> Não há como instalar "só o do Portal de Serviços": instala-se o servidor
> inteiro e usa-se a parte pronta. A tabela de maturidade abaixo é o que
> substitui essa separação.

---

## 1. O que instalar

A máquina precisa de Python 3.11 ou mais novo e de saída de rede brasileira,
porque as interfaces do Conselho Nacional de Justiça recusam acesso de fora do
país.

No Windows, com PowerShell, dentro da pasta do pacote:

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,navegador]"
.venv\Scripts\playwright install chromium
copy .env.example .env
```

O extra `navegador` e o `playwright install` só são necessários para as
ferramentas autenticadas, que abrem uma janela de verdade. Para usar apenas a
base nacional e a leitura das peças já gravadas, `".[dev]"` basta.

Depois, abra o `.env` e preencha `DATAJUD_API_KEY`. A chave é **pública**,
emitida pelo Departamento de Pesquisas Judiciárias do Conselho Nacional de
Justiça: <https://datajud-wiki.cnj.jus.br/api-publica/acesso/>.

---

## 2. Registrar no Claude

O arquivo de configuração do Claude Desktop fica, no Windows, em
`%APPDATA%\Claude\claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "justica": {
      "command": "C:\\caminho\\para\\mcp-justica\\.venv\\Scripts\\python.exe",
      "args": ["-m", "justica_mcp.server"],
      "env": { "DATAJUD_API_KEY": "a chave do DataJud" }
    }
  }
}
```

Troque `C:\\caminho\\para\\mcp-justica` pelo caminho real da pasta. O `command`
precisa ser o Python **do ambiente virtual**, com caminho absoluto: o Python do
sistema não enxerga as dependências instaladas acima.

Feche e reabra o Claude. O servidor deve aparecer com **14 ferramentas**.

### Conferir antes de confiar

Na máquina, sem o Claude, para separar um defeito de instalação de um defeito
do conector:

```powershell
.venv\Scripts\python -m justica_mcp.server
```

Ele fica em silêncio esperando o protocolo, o que é o comportamento certo.
`Ctrl+C` encerra. Se ele morrer com erro, o erro é de instalação.

---

## 3. O que já funciona, e com que grau de prova

### Pronto, sem portal e sem credencial

Lêem a base nacional do Conselho Nacional de Justiça ou o Diário de Justiça
Eletrônico Nacional. Não autenticam, não gastam tentativa, não disparam
ciência, e podem ser repetidas à vontade.

| Ferramenta | O que faz |
| --- | --- |
| `justica_identificar_tribunal` | Tribunal, segmento e ano pelo número, sem rede. Confere o dígito verificador. |
| `justica_resolver_sistema` | Em qual sistema o processo tramita. |
| `justica_consultar_processo` | Classe, assuntos, órgão e último andamento. |
| `justica_listar_andamentos` | Movimentos, do mais recente para o mais antigo. |
| `justica_verificar_novos_andamentos` | Só o que mudou desde a última consulta gravada. |
| `justica_publicacoes_por_oab` | Publicações do Diário pela inscrição na Ordem. |
| `justica_publicacoes_por_processo` | Publicações do Diário referentes a um processo. |

Dois limites que a própria ferramenta repete na resposta, e que valem repetir
aqui: a base nacional **não** entrega partes, advogados nem documentos, por
política do Conselho Nacional de Justiça, e ela replica os tribunais com
atraso, então **não serve para contagem de prazo** sem conferência no portal.

### Pronto, lendo do disco

Lêem o que uma corrida de download já gravou. Não abrem o portal, não
autenticam, não têm teto por hora.

| Ferramenta | O que faz |
| --- | --- |
| `justica_pecas_do_processo` | Lista as peças gravadas: nome, página inicial, folhas, bytes. Nenhum conteúdo. |
| `justica_ler_peca` | O texto de uma peça. É a **única** ferramenta do servidor que devolve conteúdo dos autos. |

É por aqui que a análise processual acontece sem gastar autenticação.

### Pronto, com credencial, provado em campo

| Ferramenta | Situação |
| --- | --- |
| `justica_consultar_processo_autenticado` (sistema `dcp`) | Provado na corrida de 21/10/2026: autenticação, perfil, busca, capa, partes, movimentações, Visualizador, índice completo e download. |

### Com credencial, **não** provado desde as mudanças desta semana

| Sistema | Situação |
| --- | --- |
| `eproc` | A ferramenta aceita, e o código existe. **[Não verificado]** se continua funcionando: não houve corrida em campo depois das mudanças de código compartilhado desta semana. |
| `e-SAJ` (Tribunal de Justiça de São Paulo) | Mesma situação: código existe, sem corrida de confirmação recente. |
| `PJe` | **Não finalizado.** A consulta autenticada recusa o PJe de propósito: `justica_consultar_processo_autenticado` só aceita `dcp` e `eproc`. A extração da linha do tempo não foi escrita e o download não existe. |

### Serviço

| Ferramenta | O que faz |
| --- | --- |
| `justica_capacidades` | Matriz do que cada adaptador sabe fazer e o motivo do que não faz. |
| `justica_credenciais_situacao` | Quais credenciais o cofre tem, sem revelar nenhuma. |
| `justica_acesso_autenticado_situacao` | Tentativas gastas e tetos. |
| `justica_auditoria_recente` | O que o servidor fez por último. |

---

## 4. O download continua fora do Claude

Baixar os autos é feito pela linha de comando, não por ferramenta do conector,
e isso é deliberado: a corrida abre uma janela de verdade, pede presença humana
no desafio de verificação e pode levar horas. Não cabe dentro de uma chamada de
ferramenta.

```powershell
justica-portal consultar --tribunal TJRJ --sistema dcp --processo <numero> --documentos auto
```

Depois que ela roda, o conector enxerga o resultado por
`justica_pecas_do_processo` e `justica_ler_peca`.

Para ver o que a pasta cobre e onde estão os buracos:

```powershell
justica-portal reindexar --processo <numero>
```

---

## 5. O que este conector não faz, de propósito

- **Não dá ciência de intimação e não inicia prazo.** Ler o Diário é canal
  público. Abrir o expediente no painel do portal, não, e por isso nenhuma
  ferramenta abre expediente.
- **Não escreve nada em sistema de tribunal.** Todas as ferramentas são
  declaradas somente leitura, e a inicialização do servidor aborta se alguma
  capacidade de escrita vazar.
- **Não manda dado do cliente para fora da máquina.** O transporte é local
  (`stdio`), o cofre e a auditoria ficam em disco local.
- **Ausência não é prova.** Nem a base nacional, nem o Diário, nem a pasta de
  cópias provam que algo não existe nos autos. As três avisam isso na própria
  resposta.
