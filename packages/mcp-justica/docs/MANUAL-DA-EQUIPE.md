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

### Três cuidados que a equipe precisa observar

**Não deixe a planilha na sua máquina.** Depois de importar, o cofre passa a
ser a fonte. Manter senha e semente de segundo fator juntas num arquivo anula
a proteção do segundo fator.

**O teto de tentativas é da conta, não da pessoa.** Como a credencial é a
mesma para todos, as tentativas de autenticação de cada um somam no mesmo
limite do tribunal. Duas pessoas consultando o mesmo portal ao mesmo tempo
gastam o dobro, e tentativas seguidas bloqueiam o acesso de **todo o
escritório**, não só de quem tentou.

**O registro de quem fez o quê é local.** Cada máquina guarda a própria
auditoria. Com credencial compartilhada, o portal do tribunal não distingue
quem consultou. Se for preciso saber quem fez determinado acesso, a resposta
está na máquina de quem fez, pela ferramenta `justica_auditoria_recente`.

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
**eproc**. Para o **e-SAJ** e o **PJe**, essa consulta recusa, de propósito: os
caminhos dessas telas ainda não foram escritos dentro da ferramenta, e aceitar
faria a chamada gastar uma autenticação para falhar na tela errada. O
**download**, esse sim, funciona nos quatro portais.

### Baixar os autos

- "Baixe os autos desse processo."

O conector pede o download e **responde na hora**, com um número de trabalho.
Ele não fica esperando, porque isso leva de minutos a horas: o portal gera o
arquivo quando se pede, e no eproc a geração pode demorar.

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

## 6. O que o conector não faz, e por quê

| Não faz | Por quê |
| --- | --- |
| Dar ciência de intimação | Ciência inicia prazo. É ato do advogado, nunca de um programa. |
| Escrever em sistema de tribunal | Nenhuma das 16 ferramentas altera nada no tribunal. O download grava arquivos na sua pasta de cópias, e só. |
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
