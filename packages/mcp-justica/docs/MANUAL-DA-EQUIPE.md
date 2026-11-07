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
- **Node, versão 18 ou mais nova.** O manifesto do conector declara que ele é
  iniciado pelo comando `node`. Sem Node, o conector aparece na lista do
  Claude, com as vinte ferramentas que o manifesto promete, e **nunca sobe**.
- Acesso à pasta do projeto no Google Drive, que o responsável indica.
- Cerca de vinte minutos, quase todos de espera do instalador.

Você **não** precisa saber programar, e não precisa instalar Python antes: o
instalador procura um, avisa se faltar e diz onde buscar. Com o Node é
diferente, porque ele não passa por ali. Instale assim:

```powershell
winget install OpenJS.NodeJS.LTS
```

Depois de instalar o Node, **encerre a sessão do Windows e entre de novo**, ou
reinicie a máquina. Fechar e reabrir o Claude não basta: ele herda o ambiente
de quando a sessão do Windows começou, e continuaria sem achar o Node mesmo
com ele instalado. Para conferir, abra um PowerShell **novo** e rode `node
--version`; janela que já estava aberta não enxerga o caminho novo.

O instalador confere o Node no passo 1 e avisa se faltar, mas não interrompe:
o lado do Python fica válido do mesmo jeito, e quem instalar o Node depois não
precisa rodar o instalador de novo.

---

## 2. Instalar o programa

Abra o PowerShell (tecla Windows, digite `powershell`, Enter). Primeiro
confira que o instalador está visível para a sua máquina:

```powershell
Get-Item "G:\Meu Drive\4.Processos\conector-justica\scripts\instalar.ps1"
```

Se aparecerem nome, tamanho e data, rode:

```powershell
powershell -ExecutionPolicy Bypass -File "G:\Meu Drive\4.Processos\conector-justica\scripts\instalar.ps1"
```

> **Se o primeiro comando der erro**, a letra da unidade do Google Drive na
> sua máquina não é `G:`. Descubra com `Get-PSDrive -PSProvider FileSystem` e
> troque a letra nos dois comandos. **Não digite o caminho de exemplo como se
> fosse literal**: em 06/11/2026 uma instalação da banca parou porque o texto
> do marcador foi executado tal e qual, e o PowerShell respondeu que o arquivo
> não tinha extensão `.ps1`.

O `-ExecutionPolicy Bypass` é necessário porque o Windows bloqueia por padrão
qualquer script vindo de fora da máquina. Ele vale só para essa execução e não
altera configuração nenhuma.

O instalador faz oito passos e explica cada um. O primeiro deles confere o
Node, e avisa sem interromper se ele faltar. Ao final ele imprime **dois
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

1. **Gere o arquivo da extensão.** Ele **não vem no projeto**: é gerado, e
   por isso não está numa cópia recém-baixada. Na pasta do projeto, rode:

   ```
   .venv\Scripts\python.exe scripts\empacotar.py
   ```

   O comando escreve `conector\justica-mcp.mcpb` e imprime a versão, quantas
   ferramentas ela tem e o resumo criptográfico do arquivo. Não instala nada e
   não acessa a internet.

2. **Configurações → Extensões.**
3. Arraste o `justica-mcp.mcpb` que o comando acabou de gerar para dentro
   dessa página.
4. O Claude abre uma prévia. Clique em **Instalar** e confirme.
5. Ele pede três coisas:
   - **Python do ambiente virtual:** o primeiro caminho amarelo do instalador.
   - **Pasta do projeto:** o segundo caminho amarelo.
   - **Chave da base nacional:** deixe **em branco**. Campo vazio não
     sobrescreve o que já está configurado.

Feche e reabra o Claude. O conector deve aparecer na lista com **20
ferramentas**. Se aparecer um número menor, a extensão instalada é de uma
versão anterior: gere o arquivo de novo e arraste outra vez.

> **Se não existir "Extensões" nas Configurações**, a organização desligou
> extensões de desktop. Quem religa é um responsável, nas configurações da
> organização. Não há como contornar pelo seu lado.

---

## 4. Configuração e credenciais

A configuração e as credenciais de portal são **compartilhadas pelo
escritório**, por decisão da banca. Você não precisa montar nada: o
instalador já copia o arquivo de configuração da pasta compartilhada na
primeira execução.

### O que já vem pronto

O arquivo `.env`, com os endereços dos portais, a chave da base nacional e a
pasta de cópias no Google Drive. Para conferir que ele foi lido, sem que
nenhum valor apareça na tela:

```powershell
& "$env:LOCALAPPDATA\justica-mcp\.venv\Scripts\python.exe" -m justica_mcp.portal ambiente
```

Ele lista os nomes das chaves e os portais que o programa enxerga, nunca os
valores.

> **O acesso autenticado vem LIGADO.** Conferido em 05/11/2026 numa máquina
> recém-instalada: o arquivo da banca traz `JUSTICA_ACESSO_AUTENTICADO=1`.
> Isso significa que a máquina já nasce capaz de disparar autenticação real,
> e passa a fazê-lo assim que houver credencial no cofre. Para conferir na
> sua:
>
> ```powershell
> Select-String -Path "$env:LOCALAPPDATA\justica-mcp\.env" -Pattern "^JUSTICA_ACESSO_AUTENTICADO="
> ```

### Carregar as credenciais

As credenciais vêm da planilha da banca, que o responsável indica. Uma única
linha de comando leva os valores da planilha direto para o cofre do Windows,
sem copiar e colar senha e sem deixar arquivo intermediário:

```powershell
& "$env:LOCALAPPDATA\justica-mcp\.venv\Scripts\python.exe" -m justica_mcp.credenciais importar --planilha "CAMINHO_DA_PLANILHA"
```

Troque `CAMINHO_DA_PLANILHA`, entre aspas, pelo caminho do arquivo que o
responsável indicou. Antes de valer, dá para ensaiar: acrescente `--simular`
ao final e ele mostra o que faria sem gravar nada.

Confira depois, sem ver nenhum segredo:

```powershell
& "$env:LOCALAPPDATA\justica-mcp\.venv\Scripts\python.exe" -m justica_mcp.credenciais listar
```

### O segundo fator, e a primeira execução de cada máquina

Nem todo portal pede código de segundo fator. O Portal de Serviços do
Tribunal de Justiça do Estado do Rio de Janeiro **não pede**.

O conector não presume isso: ele decide por observação, e a observação é de
cada máquina. Enquanto nenhuma autenticação real tiver mostrado se a tela de
código aparece, ele **recusa** o acesso àquele portal, dizendo que não haveria
a quem perguntar o código. É recusa correta, e não defeito: ela protege contra
começar uma sessão que não se pode terminar.

Para ensinar isso à máquina, basta **uma** execução com o navegador visível,
pela linha de comando, com alguém na frente da tela:

```powershell
& "$env:LOCALAPPDATA\justica-mcp\.venv\Scripts\justica-portal.exe" consultar --tribunal TJRJ --sistema dcp --processo NUMERO-DO-PROCESSO --confirmo-tentativa-unica
```

Troque `NUMERO-DO-PROCESSO` por um número real, com pontos e traço. A execução
gasta uma tentativa, e não é desperdício: é uma consulta de verdade, e o
resultado fica gravado. A partir dela o conector passa a decidir por
observação e deixa de recusar.

### Três cuidados que a equipe precisa observar

**Não deixe a planilha na sua máquina.** Depois de importar, o cofre passa a
ser a fonte. Manter senha e semente de segundo fator juntas num arquivo anula
a proteção do segundo fator.

**O teto de tentativas é da conta, não da pessoa.** Como a credencial é a
mesma para todos, as tentativas de autenticação de cada um somam no mesmo
limite do tribunal. Duas pessoas consultando o mesmo portal ao mesmo tempo
gastam o dobro, e tentativas seguidas bloqueiam o acesso de **todo o
escritório**, não só de quem tentou.

**E a trava do conector não cobre esse risco.** Ela existe, e é útil, mas
protege contra outra coisa. Conferido no código em 29/10/2026:

| | A trava do conector | O limite do tribunal |
| --- | --- | --- |
| O que conta | Falhas **seguidas** de autenticação. Um acerto zera a contagem. | A política do portal, que a banca não controla. |
| Quanto | **18 em 60 minutos** na configuração da banca. O padrão do programa é 6, e foi elevado de propósito. | Não divulgado, e a banca não tem como conferir. |
| Onde é contado | No arquivo `.justica-mcp` **da sua máquina e do seu usuário do Windows**. | Na conta do escritório, que é uma só. |

A consequência é direta: **cada pessoa tem a sua própria contagem, e o
tribunal vê a soma.** Cada máquina pode estar dentro do seu limite enquanto a
conta compartilhada leva o total de todas. A trava evita que **um** programa
em laço queime a conta sozinho; ela não evita que o escritório inteiro faça
isso junto.

E há um ponto que costuma ser lido ao contrário. O teto foi elevado de 6 para
18 porque, com credencial compartilhada, as falhas de várias pessoas somam na
mesma janela e o número baixo parava gente trabalhando. Mas **teto maior não
é mais proteção, é menos**: ele faz o nosso freio parar mais tarde, portanto
mais perto do ponto em que quem bloqueia é o tribunal. Qual é esse ponto não
está documentado em lugar nenhum que a banca possa conferir.

Por isso duas regras práticas:

1. **Diante de erro de autenticação, pare e avise o responsável.** Não repita.
   Repetir é o que bloqueia, e o seu contador local não saberá das tentativas
   de mais ninguém.
2. **Combine antes, quando a equipe for consultar o mesmo portal no mesmo
   dia.** O conector não tem como coordenar isso entre as máquinas.

Para ver quanto resta no **seu** contador, a qualquer hora e sem custo
nenhum, pergunte ao Claude:

- "Como está o acesso autenticado."

Ele responde pela ferramenta `justica_acesso_autenticado_situacao`, que
informa quantas tentativas foram usadas na janela, qual é o teto e quantas
restam. Essa resposta vale só para a sua máquina, pela razão explicada acima.

**O registro de quem fez o quê é local.** Cada máquina guarda a própria
auditoria. Com credencial compartilhada, o portal do tribunal não distingue
quem consultou. Se for preciso saber quem fez determinado acesso, a resposta
está na máquina de quem fez, pela ferramenta `justica_auditoria_recente`.

## 5. Como chamar: diga **extensão**, não conector

Detalhe pequeno que faz diferença na prática, observado em 25/10/2026: pedir
"use o **conector** Justiça" não funcionou, e pedir "use a **extensão**
Justiça" funcionou na mesma hora.

A razão é que o aplicativo do Claude chama de **conector** o que se liga por
endereço de internet, como o Gmail e o Google Drive, e de **extensão** o que
roda na sua máquina, que é o nosso caso. Usar a palavra certa poupa uma volta.

Na dúvida, diga apenas o que você quer, sem nomear nada:

- "Quais peças existem no processo tal?"

O Claude escolhe a ferramenta sozinho. Nomear só ajuda quando ele não escolheu.

---

## 6. O que dá para pedir ao Claude

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

Pelo Claude, funciona hoje para o **Portal de Serviços do Rio de Janeiro** e
para o **eproc**. Para o **e-SAJ** e o **PJe**, a ferramenta recusa, e a
recusa é de propósito: ela sabe chegar à tela do Portal de Serviços e à busca
rápida do eproc, e nenhum desses dois caminhos serve àquelas telas. Aceitar
gastaria uma autenticação para falhar na tela errada, que é o pior desfecho
possível.

Isso **não** quer dizer que o e-SAJ e o PJe estejam de fora do projeto: os
dois funcionam pela linha de comando, com autenticação e download, e quem
precisar deles pede ao responsável. O que falta é ligar esses caminhos à
ferramenta, não escrevê-los.

O **download**, esse sim, funciona nos quatro portais pelo próprio Claude.

### Processo que subiu: primeiro e segundo grau

Vale para o Portal de Serviços do Rio de Janeiro, e é a causa mais comum de
confusão na leitura.

O número único **não muda** quando o processo sobe. O mesmo número serve à
primeira instância e ao recurso, e o portal mostra **uma linha para cada
registro**: cada grau, e às vezes cada serventia, tem a sua linha, com
movimentações próprias. Nenhuma delas é "a certa": são partes diferentes da
mesma história.

Por isso a primeira consulta traz a relação de todas as linhas, com a
instância de cada uma. Leia e diga qual você quer:

- "Consulte esse processo no portal."
- "Agora consulte a linha do segundo grau desse mesmo processo."

Duas consequências práticas:

**Cada linha custa uma autenticação.** Ver o primeiro e o segundo grau do
mesmo processo são dois acessos, não um.

**Não conclua que falta movimentação sem conferir a linha.** Um processo que
parece parado na primeira instância pode estar andando no recurso, em outra
linha. A ausência que você vê é da linha que você abriu, não do processo.

### Baixar os autos

- "Baixe os autos desse processo."

O conector pede o download e **responde na hora**, com um número de trabalho.
Ele não fica esperando, porque isso leva de minutos a horas: o portal gera o
arquivo quando se pede, e no eproc a geração pode demorar.

**Essa primeira resposta nunca diz que baixou**, porque naquele instante não
baixou mesmo. Ela diz que o pedido começou. Para saber se terminou:

- "Como está o download."

O estado deixa de ser "em curso" quando acaba. E **concluído não quer dizer
que veio arquivo**: pode ter vindo só a confirmação de que o portal aceitou o
pedido e está montando. As últimas linhas do relato dizem qual dos dois.

Depois de concluído, confirme o que de fato chegou. As duas perguntas abaixo
leem o disco, são gratuitas e não abrem portal:

- "Quais peças existem nesse processo."
- "Qual a cobertura desse processo, e que folhas faltam."

A segunda é a que evita conclusão errada: uma cópia pode vir incompleta sem
que nada avise, e ela diz exatamente quais faixas de páginas faltaram, em vez
de deixar você estimar.

> **Nunca peça o mesmo download duas vezes.** Cada pedido gasta uma tentativa
> de autenticação da credencial do escritório, abre outro navegador e escreve
> na mesma pasta. Em 06/11/2026 um processo recebeu quatro pedidos em dez
> minutos: o primeiro funcionou e gravou os arquivos, e os outros três
> autenticaram de novo e colidiram com o navegador já aberto. Vale também
> entre conversas: se você pediu numa conversa, não peça em outra. Pergunte
> primeiro como está o download.

### Guardar ou só ler: as duas formas

Você escolhe, e a escolha muda onde o arquivo fica.

| | Guardando (padrão) | Sem guardar |
| --- | --- | --- |
| Onde fica | Pasta de cópias da banca, no Google Drive | Pasta local desta máquina |
| Quem lê depois | O escritório inteiro, de graça, para sempre | Só você, enquanto não apagar |
| Entra no índice | Sim | Não |
| Quando usar | Processo que o escritório vai trabalhar | Processo que você consulta uma vez |

Para não guardar, diga isso ao pedir:

- "Leia os autos desse processo **sem guardar**."

Nos dois casos a leitura é igual. Para ler o que ficou sem guardar, diga de
onde:

- "Quais peças existem nesse processo, **na pasta de leituras**."
- "Leia a peça tal desse processo, **na pasta de leituras**."

Uma conta que vale fazer antes de escolher: guardar custa **uma** autenticação
e depois a equipe lê quantas vezes quiser. Não guardar custa uma autenticação
por vez que alguém precisar do processo de novo.

### Vários processos de uma vez

Se os processos forem **do mesmo portal**, peça todos juntos:

- "Baixe os autos desses três processos."

Eles correm na mesma sessão, com **uma autenticação só**. Dez processos do
mesmo tribunal custam uma, e não dez.

Duas regras:

**Processos de portais diferentes não entram juntos.** O conector recusa antes
de começar, em vez de gastar a autenticação para falhar na tela errada. Peça
um pedido por portal.

**Falha em um não derruba os outros.** O que falhou é dito no fim, pelo
número, e os demais seguem. Numa corrida de dez, perder nove por causa de um
seria o pior desfecho possível.

Para acompanhar:

- "Como está o download que você pediu."

Quando terminar, as peças estão na pasta de cópias e todo o escritório pode
lê-las pelo conector, sem autenticar.

**Duas condições.** O eproc levanta o desafio "Confirme que é humano", e isso
exige **uma pessoa na frente da tela** da máquina onde o conector roda. E, no
PJe, o aviso de responsabilidade da resolução nº. 121 do Conselho Nacional de
Justiça só é aceito se você disser ao Claude, em palavras, que aceita: o
aceite é ato do advogado, nunca do programa.

---

## 7. O que o conector não faz, e por quê

| Não faz | Por quê |
| --- | --- |
| Dar ciência de intimação | Ciência inicia prazo. É ato do advogado, nunca de um programa. |
| Escrever em sistema de tribunal | Nenhuma das 20 ferramentas altera nada no tribunal. O download grava arquivos na sua pasta de cópias, e só. |
| Mandar dado para fora | Tudo roda na sua máquina. O que sai são as consultas aos portais, com a sua credencial. |
| Usar a credencial de outra pessoa | O cofre é da sua máquina e da sua conta do Windows. |

---

## 8. Quando alguma coisa não funciona

**O Claude diz que não tem as ferramentas. Comece por aqui.** Há dois
interruptores, e não um. O primeiro fica em Configurações → Extensões e liga o
conector na máquina. O segundo fica **na própria conversa**, no campo de
extensões ao lado da caixa de mensagem, e liga o conector naquele diálogo. Um
conector instalado e ativo nas Configurações pode estar desligado na conversa,
e o Claude então responde, com toda a sinceridade, que não encontrou a
ferramenta. Na primeira instalação da banca foi exatamente isso, depois de uma
tarde de investigação.

**Se o interruptor da conversa já estava ligado, confira o Node.** Abra um
PowerShell **novo** e rode `node --version`. Se o comando não for reconhecido,
volte à seção 1: sem Node o conector não sobe, e depois de instalar é preciso
encerrar a sessão do Windows.

**O número de ferramentas na página de Extensões não prova que o conector
subiu.** Esse número vem do manifesto, que é um arquivo de texto dentro do
pacote. Ver vinte ali confirma que o pacote certo foi instalado, e nada além.

**Leia o nome na notificação de falha.** O aplicativo avisa quando qualquer
conector não inicia, e o aviso traz o nome dele. Falha de outro conector não
diz nada sobre este.

**Procurando os registros.** Instalado pela Loja, o aplicativo grava em pasta
redirecionada, e não em `AppData\Roaming`. Procure por arquivos `mcp*.log`
dentro de `AppData\Local\Packages`. O recado deste conector começa sempre com
`[conector justica]`.

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

## 9. Atualizar

Quando houver versão nova, rode o mesmo instalador outra vez. Ele atualiza o
código e **não toca** no seu `.env` nem nas suas credenciais.

**Na maior parte das vezes é só isso.** A extensão não carrega o código dentro
dela: o manifesto aponta para a sua pasta do projeto e para o Python do
ambiente virtual, então o que ela executa é o código que estiver em disco.
Atualizar o código já atualiza o que a extensão faz.

**Mas é preciso reiniciar o Claude, e reiniciar tudo.** O servidor que está
no ar carregou o código antigo na memória, e só troca ao subir de novo. Feche
o aplicativo **por inteiro**, inclusive pelo ícone ao lado do relógio: fechar
a janela não encerra o processo.

E feche também sessão de código e Cowork, se houver alguma aberta. Cada uma
dessas superfícies sobe a própria instância do servidor, com a própria
memória. Enquanto uma continuar com o código antigo, ela segue se comportando
como antes, e o sintoma é confuso: a mesma pergunta responde diferente em
duas conversas da mesma máquina.

**Reinstalar a extensão só é preciso quando o manifesto ou o lançador mudam**,
isto é, quando há ferramenta nova, campo de configuração novo ou conserto na
partida do conector. Nesse caso:

```
.venv\Scripts\python.exe scripts\empacotar.py
```

e arraste o arquivo gerado para Configurações → Extensões. O Claude só aceita
substituir por uma versão de número maior.

Para saber se a sua está atrasada, compare o número de ferramentas que o
Claude mostra com o que o comando acima imprime. Se forem diferentes, a
instalada é antiga.
