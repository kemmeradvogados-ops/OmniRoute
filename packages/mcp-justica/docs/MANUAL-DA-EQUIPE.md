# Manual do conector Justiça

Para quem vai **usar**, não para quem vai programar. Escrito em 23/10/2026.

O conector dá ao Claude acesso de **somente leitura** a processos judiciais.
Ele não peticiona, não dá ciência de intimação, não inicia prazo e não escreve
nada em sistema de tribunal. Nada do que ele lê sai da sua máquina.

---

## 1. O que você precisa antes de começar

- Windows, com o **aplicativo do Claude para computador** instalado. O
  conector não funciona pelo navegador: ele roda um programa na sua máquina, e
  o navegador não tem como fazer isso.
- Acesso à pasta do projeto no Google Drive, que o responsável indica.
- Cerca de vinte minutos, quase todos de espera do instalador.

Você **não** precisa saber programar, e não precisa instalar Python antes: o
instalador avisa se faltar e diz onde buscar.

---

## 2. Instalar o programa

Abra a pasta do projeto no Google Drive, entre em `scripts` e **copie o
caminho** do arquivo `instalar.ps1`.

Abra o PowerShell (tecla Windows, digite `powershell`, Enter) e rode, com o
caminho entre aspas:

```powershell
powershell -ExecutionPolicy Bypass -File "G:\...\scripts\instalar.ps1"
```

O `-ExecutionPolicy Bypass` é necessário porque o Windows bloqueia por padrão
qualquer script vindo de fora da máquina. Ele vale só para essa execução e não
altera configuração nenhuma.

O instalador faz sete passos e explica cada um. Ao final ele imprime **dois
caminhos em amarelo**. Copie os dois para algum lugar: o conector vai pedi-los
no passo seguinte.

Se ele parar, a mensagem diz o porquê e o que fazer. Mande a mensagem inteira
ao responsável, não só a última linha.

> **Por que ele instala numa pasta da sua máquina e não roda direto do Drive:**
> o ambiente do Python guarda caminhos absolutos da máquina que o criou, e o
> Drive transmite arquivo sob demanda. Programa rodando de lá é lento e falha
> sozinho. O Drive distribui o código; a execução é local.

---

## 3. Instalar o conector no Claude

No aplicativo do Claude para computador:

1. **Configurações → Extensões.**
2. Arraste o arquivo `justica-mcp.mcpb`, que está na pasta `conector` do
   projeto, para dentro dessa página.
3. O Claude abre uma prévia. Clique em **Instalar** e confirme.
4. Ele pede três coisas:
   - **Python do ambiente virtual:** o primeiro caminho amarelo do instalador.
   - **Pasta do projeto:** o segundo caminho amarelo.
   - **Chave da base nacional:** deixe **em branco**. Campo vazio não
     sobrescreve o que já está configurado.

Feche e reabra o Claude. O conector deve aparecer na lista com **14
ferramentas**.

> **Se não existir "Extensões" nas Configurações**, a organização desligou
> extensões de desktop. Quem religa é um responsável, nas configurações da
> organização. Não há como contornar pelo seu lado.

---

## 4. Configurar o que é seu

Duas coisas são pessoais e não se compartilham: a sua credencial e a sua
inscrição na Ordem.

Abra o arquivo de configuração:

```powershell
notepad "$env:LOCALAPPDATA\justica-mcp\.env"
```

Peça ao responsável os valores das chaves de portal, que são iguais para todo
o escritório, e preencha também:

- `JUSTICA_OAB_NUMERO` e `JUSTICA_OAB_UF`, os seus;
- `JUSTICA_PASTA_COPIAS`, a pasta de cópias no Google Drive, a mesma para todos.

Para gravar a sua credencial de portal, que fica no cofre do Windows e nunca
no arquivo. Uma linha por portal, trocando os dois nomes do final:

```powershell
& "$env:LOCALAPPDATA\justica-mcp\.venv\Scripts\python.exe" -m justica_mcp.credenciais guardar --tribunal TJRJ --sistema pje
```

Ele pergunta o usuário, a senha e, quando houver, a semente do segundo fator,
sem imprimir nada na tela. Os pares que o escritório usa:

| `--tribunal` | `--sistema` | Portal |
| --- | --- | --- |
| `TJRJ` | `dcp` | Portal de Serviços do Rio de Janeiro |
| `TJRJ` | `pje` | PJe do Rio de Janeiro |
| `TJSP` | `esaj` | e-SAJ de São Paulo |
| `TRF2` | `eproc` | eproc do Tribunal Regional Federal da 2ª Região |
| `JFRJ` | `eproc` | eproc da Seção Judiciária do Rio de Janeiro |

Para conferir o que ficou guardado, sem ver nenhum segredo:

```powershell
& "$env:LOCALAPPDATA\justica-mcp\.venv\Scripts\python.exe" -m justica_mcp.credenciais listar
```

---

## 5. O que dá para pedir ao Claude

### Sem gastar nada, a qualquer hora

Estas respostas vêm da base nacional do Conselho Nacional de Justiça ou do
Diário de Justiça Eletrônico. São instantâneas, não usam a sua credencial e
não têm limite por hora.

- "Em que pé está o processo tal."
- "Quais os últimos andamentos desse processo."
- "Mudou alguma coisa nesse processo desde a última vez."
- "Quais publicações saíram no meu nome esta semana."

### Lendo o que já foi baixado

Estas são as mais úteis no dia a dia e também não custam nada: leem os
arquivos que já estão na pasta de cópias.

- "Quais peças existem nesse processo."
- "Leia a petição inicial desse processo e me diga os pedidos."
- "Compare o que a contestação alega com o que a inicial pediu."

É aqui que a análise acontece. Quem baixou os autos uma vez abriu o caminho
para o escritório inteiro ler.

### Com a sua credencial, com custo real

- "Consulte esse processo no portal do tribunal."

**Cada chamada dessas autentica de verdade no tribunal, demora dezenas de
segundos e gasta uma tentativa da sua conta.** Tentativas seguidas bloqueiam o
seu acesso. Há um teto por hora e o conector recusa quando ele é atingido.

**Diante de erro, não repita o pedido.** Diga ao responsável o que aconteceu.
Repetir é o que bloqueia a conta.

Funciona hoje para o **Portal de Serviços do Rio de Janeiro** e para o
**eproc**. Para o **e-SAJ** e o **PJe** o conector recusa, de propósito: os
caminhos dessas telas ainda não foram escritos dentro da ferramenta, e aceitar
faria a chamada gastar uma autenticação para falhar na tela errada.

---

## 6. O que o conector não faz, e por quê

| Não faz | Por quê |
| --- | --- |
| Baixar os autos | O download abre uma janela de verdade, pode exigir que uma pessoa marque a caixa de verificação e, no eproc, pode levar horas até o tribunal montar o arquivo. Isso é feito pela linha de comando, por quem tem o processo em mãos. |
| Dar ciência de intimação | Ciência inicia prazo. É ato do advogado, nunca de um programa. |
| Escrever em sistema de tribunal | Todas as 14 ferramentas são de leitura. |
| Mandar dado para fora | Tudo roda na sua máquina. O que sai são as consultas aos portais, com a sua credencial. |
| Usar a credencial de outra pessoa | O cofre é da sua máquina e da sua conta do Windows. |

---

## 7. Quando alguma coisa não funciona

**O conector não aparece na lista do Claude.** Confira se você usa o
aplicativo para computador e não o navegador. Depois, Configurações →
Extensões.

**Aparece, mas as ferramentas dão erro.** Rode isto, que testa o programa sem
o Claude no meio:

```powershell
& "$env:LOCALAPPDATA\justica-mcp\.venv\Scripts\python.exe" -m justica_mcp.server
```

Ele fica **em silêncio**, sem imprimir nada. Isso é o certo: um servidor desse
tipo espera calado até alguém falar com ele. Encerre com `Ctrl+C`. Se em vez
do silêncio aparecer um erro, o problema é de instalação e a mensagem é o que
o responsável precisa ver.

**As ferramentas da base nacional não respondem.** Falta a chave do DataJud no
`.env`, ou a máquina está acessando de fora do Brasil. As interfaces do
Conselho Nacional de Justiça recusam acesso estrangeiro.

**"Acesso autenticado desligado".** É proposital. `JUSTICA_ACESSO_AUTENTICADO`
começa em `0`, e ligar permite que o agente dispare autenticação real com a
sua credencial. Essa decisão é do responsável, não sua.

---

## 8. Atualizar

Quando houver versão nova, rode o mesmo instalador outra vez. Ele atualiza o
código e **não toca** no seu `.env` nem nas suas credenciais.

Se o `.mcpb` também mudar, arraste o novo para Configurações → Extensões. O
Claude só aceita substituir por uma versão de número maior.
