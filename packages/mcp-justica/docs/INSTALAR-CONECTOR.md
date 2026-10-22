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
      "args": ["-m", "justica_mcp.server"]
    }
  }
}
```

Troque `C:\\caminho\\para\\mcp-justica` pelo caminho real da pasta. O `command`
precisa ser o Python **do ambiente virtual**, com caminho absoluto: o Python do
sistema não enxerga as dependências instaladas acima.

**A chave do DataJud não entra aqui**, e isso foi conferido em 22/10/2026 e não
deduzido: `carregar_env` procura o `.env` na raiz do pacote, calculada a partir
do próprio arquivo de código, e não na pasta de trabalho de quem abriu o
processo. Com a pasta de trabalho em outro lugar, a chave foi encontrada do
mesmo jeito. Repeti-la na configuração do Claude criaria uma segunda cópia que
envelhece sozinha, e o `.env` tem precedência menor que o ambiente, então a
cópia velha é que venceria.

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

## 2b. A sequência completa, linha por linha (Windows, PowerShell)

Uma linha por vez, na ordem. Só a primeira precisa ser ajustada.

Primeiro, **descubra** o caminho em vez de digitá-lo. Em 22/10/2026 a versão
anterior deste guia abria com uma linha contendo `C:\caminho\para\...`, para
quem instalava substituir pelo caminho real, e ela foi colada literalmente. O
mesmo aconteceu com uma data de arquivo mais adiante. Lugar reservado em linha
de comando é erro à espera: a linha parece pronta.

```powershell
Get-ChildItem -Path $env:USERPROFILE -Filter "mcp-justica" -Directory -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
```

Se não devolver nada, a pasta está fora do perfil do usuário:

```powershell
Get-PSDrive -PSProvider FileSystem | ForEach-Object { Get-ChildItem -Path $_.Root -Filter "mcp-justica" -Directory -Recurse -ErrorAction SilentlyContinue } | Select-Object -ExpandProperty FullName
```

Se continuar sem resultado, o repositório não está nesta máquina, e o primeiro
passo é cloná-lo, não instalá-lo.

Com o caminho em mãos, guarde-o. Caminho com espaço ou acento funciona, desde
que entre aspas aqui:

```powershell
$projeto = "<cole aqui o caminho que a busca devolveu>"
```

```powershell
cd $projeto
```

```powershell
dir
```

Tem que listar `pyproject.toml`, `src` e `tests`. Se não listar, o caminho da
primeira linha está errado.

```powershell
git fetch origin
```

```powershell
git reset --hard origin/<a branch em uso>
```

```powershell
git log --oneline -1
```

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\pip install -e ".[dev,navegador]"
```

```powershell
.venv\Scripts\playwright install chromium
```

### O `.env`: uma linha que se recusa a sobrescrever

```powershell
if (Test-Path .env) { "JA EXISTE, nao vou sobrescrever." } else { Copy-Item .env.example .env; "criado a partir do exemplo." }
```

Esta linha é segura rodada em qualquer situação, e isso **não** é detalhe de
estilo. A versão anterior deste guia mandava rodar `Test-Path .env` e, se a
resposta fosse `True`, **não** rodar a linha seguinte, que era
`copy .env.example .env`. Quer dizer: a proteção era o leitor ler um aviso e
decidir não executar um comando que estava ali, pronto, na linha de baixo.

Em 22/10/2026, na primeira instalação feita por este guia, as duas linhas foram
rodadas, como qualquer pessoa seguindo uma lista faria, e a configuração de
verdade (sete portais, perfis, pasta de cópias) virou o arquivo de exemplo.
Proteção que depende de alguém não fazer o que a lista manda não é proteção.

**Se isso acontecer**, a configuração não se perdeu: o programa guarda uma
cópia por dia, as dez últimas, toda vez que lê o `.env`. Repor é um comando:

```powershell
.venv\Scripts\python -m justica_mcp.portal repor-config
```

Ele mostra qual cópia usaria, e **não altera nada** sem `--confirmar`. Com
`--confirmar`, guarda o `.env` atual antes de substituir.

```powershell
notepad .env
```

Preencha `DATAJUD_API_KEY`. Ao salvar, se o Bloco de Notas perguntar a
codificação, escolha **UTF-8**: o programa tolera marca de ordem de byte e
página de código do Windows, mas não lê UTF-16.

### Prova de que o servidor sobe

```powershell
.venv\Scripts\python -m justica_mcp.server
```

Ele fica em silêncio, parado, esperando o protocolo. **Silêncio aqui é o
comportamento certo.** Espere alguns segundos e encerre com `Ctrl+C`. Se
aparecer erro, o defeito é de instalação e não adianta seguir.

### Registrar no Claude sem apagar o que já existe

```powershell
$cfg = "$env:APPDATA\Claude\claude_desktop_config.json"
```

```powershell
if (Test-Path $cfg) { Copy-Item $cfg "$cfg.bak" -Force }
```

```powershell
if (-not (Test-Path $cfg)) { New-Item -ItemType Directory -Force -Path (Split-Path $cfg) | Out-Null; [System.IO.File]::WriteAllText($cfg, '{"mcpServers":{}}') }
```

```powershell
$j = Get-Content $cfg -Raw | ConvertFrom-Json
```

```powershell
if (-not $j.mcpServers) { $j | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
```

```powershell
$entrada = [pscustomobject]@{ command = "$projeto\.venv\Scripts\python.exe"; args = @("-m","justica_mcp.server") }
```

```powershell
$j.mcpServers | Add-Member -NotePropertyName justica -NotePropertyValue $entrada -Force
```

```powershell
[System.IO.File]::WriteAllText($cfg, ($j | ConvertTo-Json -Depth 10))
```

`WriteAllText` em vez de `Set-Content -Encoding utf8`: o Windows PowerShell 5.1
grava marca de ordem de byte com `utf8`, e um arquivo de configuração que
começa com essa marca pode não ser lido.

```powershell
Get-Content $cfg -Raw
```

Tem que aparecer `"justica"` com o caminho do `python.exe` do ambiente virtual,
e tem que continuar aparecendo qualquer outro servidor que já estivesse ali. Se
sumiu algo, a cópia está em `claude_desktop_config.json.bak`.

Por fim, feche o Claude por inteiro, pelo ícone na bandeja ao lado do relógio, e
abra de novo. Fechar só a janela não encerra o processo, e o conector não é
relido.

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
