<#
    Instalacao do justica_mcp numa maquina da equipe.

    Rode UMA vez. Pode rodar de novo quando houver versao nova: o codigo e
    atualizado e o seu `.env` e as suas credenciais NAO sao tocados.

    O que ele faz, nesta ordem, parando e explicando em qualquer falha:

      1. confere se existe Node, que e quem INICIA o conector;
      2. acha um Python 3.11 ou mais novo;
      3. copia o codigo desta pasta para uma pasta LOCAL da sua maquina;
      4. cria o ambiente virtual ali, local;
      5. instala o pacote e o navegador do Playwright;
      6. cria o `.env` a partir do exemplo, SEM sobrescrever um existente;
      7. confere que o servidor sobe;
      8. imprime os dois caminhos que o conector vai pedir.

    A conferencia do Node NAO interrompe a instalacao: o lado do Python fica
    valido de qualquer forma, e quem instalar o Node depois nao precisa rodar
    isto de novo. Ela existe porque, sem Node, a extensao aparece na lista do
    Claude com as vinte ferramentas que o manifesto promete e NUNCA sobe. Em
    05/11/2026 isso custou uma tarde de investigacao numa maquina da equipe:
    o manifesto declara `command: node`, e aquela maquina nao tinha nenhum.

    POR QUE LOCAL, e nao no Google Drive: ambiente virtual guarda caminhos
    absolutos da maquina que o criou, e o Drive transmite arquivo sob demanda.
    Programa rodando de la e lento e falha sozinho. O Drive serve para
    DISTRIBUIR o codigo; a execucao e local.
#>

# Nao usamos "Stop" global: todo comando externo aqui (pip, playwright,
# robocopy) escreve em erro padrao durante o trabalho normal, e com "Stop" o
# PowerShell trata isso como falha e aborta uma instalacao que estava indo bem.
# Cada passo abaixo confere o proprio resultado, de forma explicita.
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Passo($n, $texto) {
    Write-Host ""
    Write-Host "[$n] $texto" -ForegroundColor Cyan
}

function Parar($texto) {
    Write-Host ""
    Write-Host "PAROU: $texto" -ForegroundColor Red
    Write-Host ""
    Read-Host "Pressione Enter para fechar"
    exit 1
}

Write-Host "=========================================================="
Write-Host "        INSTALACAO DO justica_mcp NESTA MAQUINA"
Write-Host "=========================================================="

# A origem e a pasta que contem ESTE script, subindo um nivel: e la que estao
# pyproject.toml, src e conector.
$origem = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $origem "pyproject.toml"))) {
    Parar "nao achei pyproject.toml em '$origem'. Rode este script de dentro da pasta 'scripts' do projeto."
}

# Destino sem espaco e sem acento, de proposito: caminho com acento ja quebrou
# leitura de arquivo neste projeto, e caminho com espaco exige aspas em todo
# lugar.
$destino = Join-Path $env:LOCALAPPDATA "justica-mcp"
$venv = Join-Path $destino ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

# O Node nao e conferido com `node --version`: chamar um comando que nao
# existe levanta erro e, num script sem "Stop" global, isso suja a tela com
# rastro vermelho antes de chegarmos a explicacao. `Get-Command` pergunta sem
# chamar.
$faltaNode = $true
Passo 1 "Conferindo o Node, que e quem inicia o conector"
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $faltaNode = $false
    $versaoNode = (& node --version 2>&1) -join " "
    Write-Host "    Encontrado: $versaoNode"
    Write-Host "    Em: $($node.Source)"
} else {
    Write-Host "    NAO ENCONTRADO." -ForegroundColor Yellow
    Write-Host "    A instalacao segue: o lado do Python fica valido do mesmo"
    Write-Host "    jeito. Mas a extensao nao vai subir enquanto faltar o Node,"
    Write-Host "    e o aviso completo esta no final desta tela."
}

Passo 2 "Procurando um Python 3.11 ou mais novo"
$pyExe = $null
$pyArgs = @()
foreach ($tentativa in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3"), @("python"))) {
    $exe = $tentativa[0]
    $argumentos = @()
    if ($tentativa.Count -gt 1) { $argumentos = $tentativa[1..($tentativa.Count - 1)] }
    # Perguntar ANTES de chamar: chamar um comando que nao existe levanta erro
    # do proprio PowerShell, que nao e capturavel por `2>$null` e enche a tela
    # de vermelho numa tentativa que era so uma sondagem.
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $versao = $null
    try {
        $versao = (& $exe @argumentos -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1)
    } catch { continue }
    if (-not $versao) { continue }
    try { $n = [version]($versao.Trim()) } catch { continue }
    if ($n -ge [version]"3.11") {
        $pyExe = $exe
        $pyArgs = $argumentos
        Write-Host "    Python $($versao.Trim()) encontrado."
        break
    }
}
if (-not $pyExe) {
    Parar @"
nenhum Python 3.11 ou mais novo foi encontrado nesta maquina.
    Instale em https://www.python.org/downloads/ e marque
    'Add python.exe to PATH' na PRIMEIRA tela do instalador.
    Depois feche o PowerShell, abra de novo e rode este script outra vez.
"@
}

Passo 3 "Copiando o codigo para $destino"
# Guarda: so sobrescreve pasta que ja e desta instalacao, ou que esta vazia.
# `/MIR` apaga o que sobra no destino, e apontado para o lugar errado isso
# seria destrutivo.
if (Test-Path $destino) {
    $temProjeto = Test-Path (Join-Path $destino "pyproject.toml")
    $vazia = -not (Get-ChildItem -Force $destino | Select-Object -First 1)
    if (-not $temProjeto -and -not $vazia) {
        Parar "a pasta '$destino' ja existe, tem conteudo e nao e uma instalacao deste projeto. Nao vou mexer nela."
    }
}
$jaExistia = Test-Path (Join-Path $destino "pyproject.toml")
New-Item -ItemType Directory -Force -Path $destino | Out-Null
# `/XD` e `/XF` protegem o que e SEU: o ambiente virtual local, o cache do
# Python e, acima de tudo, o `.env`, que guarda a sua configuracao. O que esta
# excluido nao e copiado nem apagado.
robocopy $origem $destino /MIR /NJH /NJS /NP /NDL /NFL `
    /XD ".venv" "__pycache__" ".git" ".pytest_cache" "node_modules" `
    /XF ".env" | Out-Null
if ($LASTEXITCODE -ge 8) { Parar "a copia do codigo falhou (robocopy devolveu $LASTEXITCODE)." }
Write-Host "    Codigo copiado."
if ($jaExistia) { Write-Host "    A pasta ja existia: o codigo foi atualizado e o seu .env foi preservado." }

Passo 4 "Criando o ambiente virtual"
if (-not (Test-Path $venvPython)) {
    & $pyExe @pyArgs -m venv $venv
    if (-not (Test-Path $venvPython)) { Parar "o ambiente virtual nao foi criado." }
    Write-Host "    Criado."
} else {
    Write-Host "    Ja existia, reaproveitado."
}

Passo 5 "Instalando o pacote. Pode levar alguns minutos."
& $venvPython -m pip install --upgrade pip --quiet
Push-Location $destino
try {
    & $venvPython -m pip install -e ".[navegador]" --quiet
    if ($LASTEXITCODE -ne 0) { Parar "a instalacao do pacote falhou. A saida do pip esta acima." }
} finally {
    Pop-Location
}
Write-Host "    Pacote instalado."

Passo 6 "Instalando o navegador do Playwright. Cerca de 150 MB, uma vez so."
& $venvPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Parar "a instalacao do navegador falhou." }
Write-Host "    Navegador instalado."

Passo 7 "Preparando o arquivo de configuracao"
$arquivoEnv = Join-Path $destino ".env"
$envDaBanca = Join-Path $origem ".env"
$exemplo = Join-Path $destino ".env.example"
if (Test-Path $arquivoEnv) {
    # Nunca sobrescrever: a configuracao local pode ter ajustes que so valem
    # nesta maquina, e perde-la ja custou uma recuperacao de backup.
    Write-Host "    JA EXISTE um .env nesta maquina. Nao toquei nele."
} elseif (Test-Path $envDaBanca) {
    # O arquivo da banca, na pasta compartilhada, e a fonte: enderecos dos
    # portais, pasta de copias e chave da base nacional sao os mesmos para
    # todos. Copiado so na PRIMEIRA instalacao.
    Copy-Item $envDaBanca $arquivoEnv
    Write-Host "    Copiado do arquivo da banca, na pasta compartilhada."
} elseif (Test-Path $exemplo) {
    Copy-Item $exemplo $arquivoEnv
    Write-Host "    Criado a partir do exemplo. Falta preencher: ver o manual."
} else {
    Write-Host "    Nao achei configuracao nenhuma. Peca o .env ao responsavel."
}

Passo 8 "Conferindo que o servidor sobe"
$conferencia = (& $venvPython -c "import justica_mcp.server; print('ok')" 2>&1) -join " "
if ($conferencia -notmatch "ok") {
    Parar "o pacote nao importou. A mensagem foi: $conferencia"
}
Write-Host "    O servidor importa sem erro."

Write-Host ""
Write-Host "=========================================================="
Write-Host "                 INSTALACAO CONCLUIDA"
Write-Host "=========================================================="
Write-Host ""
Write-Host "Guarde estes dois caminhos. O conector vai pedir os dois:"
Write-Host ""
Write-Host "  Python do ambiente virtual:"
Write-Host "    $venvPython" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Pasta do projeto:"
Write-Host "    $destino" -ForegroundColor Yellow
Write-Host ""
if ($faltaNode) {
    Write-Host "=========================================================="
    Write-Host "   FALTA O NODE, E SEM ELE A EXTENSAO NAO VAI FUNCIONAR" -ForegroundColor Yellow
    Write-Host "=========================================================="
    Write-Host ""
    Write-Host "O conector e iniciado pelo Node. Sem ele, a extensao aparece"
    Write-Host "na lista do Claude com as vinte ferramentas e nunca sobe."
    Write-Host ""
    Write-Host "  1. Instale, numa janela do PowerShell:"
    Write-Host ""
    Write-Host "       winget install OpenJS.NodeJS.LTS" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  2. ENCERRE A SESSAO DO WINDOWS e entre de novo, ou reinicie."
    Write-Host "     Fechar e reabrir o Claude NAO basta: ele herda o ambiente"
    Write-Host "     de quando a sessao do Windows comecou."
    Write-Host ""
    Write-Host "  3. Confira numa janela NOVA do PowerShell:"
    Write-Host ""
    Write-Host "       node --version" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Nao e preciso rodar este instalador de novo."
    Write-Host ""
}
Write-Host "Proximo passo: o manual, secao 3, 'Instalar o conector no Claude'."
Write-Host ""
Read-Host "Pressione Enter para fechar"
