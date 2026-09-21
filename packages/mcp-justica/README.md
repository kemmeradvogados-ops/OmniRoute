# justica-mcp

Camada padronizadora de acesso processual da Kemmer Advogados. Um servidor
Model Context Protocol que entrega, ao agente, processos, andamentos e
publicações dos tribunais onde a banca atua, sem que o agente precise saber se
o processo está no PJe, no eproc, no e-SAJ ou no DCP.

**Versão 0.1.0, Fase 1: somente leitura, sem credenciais, sem automação de
navegador.**

> Escopo somente leitura confirmado pelo operador em 21 de setembro de 2026.
> A alternativa descartada nesta fase era o servidor com escrita (protocolo de
> petições e ciência em intimações). Habilitar escrita exige decisão expressa,
> confirmação humana por ato e revisão da fronteira em `core/seguranca.py`.

## Escopo

Fechado nas credenciais da banca:

| Tribunal | Sistemas ativos | Credencial da banca |
| --- | --- | --- |
| Tribunal de Justiça do Estado do Rio de Janeiro | PJe, eproc, DCP | PJe, eproc, DCP |
| Tribunal de Justiça do Estado de São Paulo | e-SAJ, eproc | e-SAJ e eproc |
| Tribunal Regional do Trabalho da 1ª Região | PJe | PJe |
| Justiça Federal da 2ª Região | eproc | eproc |

## Decisão central do projeto

`tribunal -> sistema` **não é tabelável**, e tabelar foi o erro que este
desenho corrige.

O Tribunal de Justiça do Estado do Rio de Janeiro opera PJe, eproc e DCP em
paralelo, sob o cronograma de migração do Ato Executivo Conjunto TJ/CGJ
nº. 21/2026. O Tribunal de Justiça do Estado de São Paulo migra do SAJ para o
eproc em ciclos por competência. Nos dois casos, o mesmo número pode estar em
sistemas diferentes conforme a competência, a vara e a data de migração.

Por isso:

- `identificar_tribunal` é determinístico, derivado do próprio número, e valida
  o dígito verificador (ISO 7064 MOD 97-10, Resolução nº. 65/2008).
- `resolver_sistema` é empírico e cacheado, nunca tabelado. Ordem de decisão:
  cache válido, sondagem autenticada (Fase 2), **declaração da base nacional**,
  pista de migração, indeterminado. Evidência sempre vence heurística.
- Toda resposta traz `sistema_resolvido`, `origem_da_resolucao` e `valido_ate`,
  para o cache envelhecer em voz alta em vez de levar o agente ao adaptador
  errado em silêncio.
- Quando não sabe, responde `indeterminado` com a ordem de candidatos. Não chuta.

## Ferramentas

Todas somente leitura.

| Ferramenta | Fonte | Entrega |
| --- | --- | --- |
| `justica_identificar_tribunal` | local | tribunal, segmento, ano, validação do dígito |
| `justica_resolver_sistema` | local mais cache | sistema provável, origem e validade |
| `justica_consultar_processo` | DataJud | classe, assuntos, órgão, último andamento |
| `justica_listar_andamentos` | DataJud | movimentos, do mais recente ao mais antigo |
| `justica_publicacoes_por_oab` | Diário de Justiça Eletrônico Nacional | publicações por inscrição na Ordem |
| `justica_publicacoes_por_processo` | Diário de Justiça Eletrônico Nacional | publicações de um processo |
| `justica_verificar_novos_andamentos` | DataJud mais snapshots | apenas o que mudou desde a última consulta |
| `justica_capacidades` | local | o que cada adaptador faz, e por que não faz o resto |
| `justica_auditoria_recente` | local | últimas chamadas registradas |

## Intimação: a fronteira que não pode ser instrução de prompt

A lei nº. 11.419/06, artigo 5º, §3º, dispõe que a intimação eletrônica se
considera realizada no dia em que o intimado consulta o teor da comunicação, e,
não havendo consulta em 10 dias corridos, considera-se automaticamente
realizada. O Superior Tribunal de Justiça decidiu em outubro de 2025 que esses
10 dias corridos contam da data do **envio**.

Ou seja: **abrir o teor consome o prazo**. Um agente que clique no lugar errado
antecipa a ciência e pode custar um prazo ao cliente.

Como o projeto trata isso:

1. O caminho de leitura é o Diário de Justiça Eletrônico Nacional, canal público
   já publicado, que **não dispara ciência**.
2. A capacidade `dar_ciencia_intimacao` não existe em nenhum adaptador, e
   `verificar_somente_leitura()` **aborta a inicialização do servidor** se ela
   for declarada disponível por engano. Barreira estrutural, não promessa.
3. Limite declarado honestamente: nem toda comunicação dirigida ao advogado
   transita pelo Diário. Expediente no painel do portal e Domicílio Judicial
   Eletrônico são canais distintos. **Ausência no Diário não prova ausência de
   intimação**, e essa cobertura precisa ser conferida tribunal a tribunal antes
   de o escritório confiar o monitoramento a esta fonte isoladamente.

## O que o servidor não faz, e diz que não faz

A matriz em `core/capabilities.py` declara cada limite com o motivo, para o
agente recusar com honestidade em vez de tentar outro caminho e inventar uma
explicação quando a resposta vier vazia:

- **Busca por nome de parte**: nenhum adaptador atende. A API pública do DataJud
  não publica nomes de partes nem advogados, por política do Conselho Nacional
  de Justiça amparada na Portaria nº. 160/2020.
- **Documentos e íntegra**: nenhum adaptador atende na Fase 1. Exige acesso
  autenticado.
- **Intimações pendentes do painel**: exige portal autenticado.
- **Busca por inscrição na Ordem**: só pelo Diário, nunca pelo DataJud.

## Restrição de infraestrutura, verificada

As APIs do Conselho Nacional de Justiça bloqueiam acesso por país de origem.
Chamada a `comunicaapi.pje.jus.br` a partir de máquina fora do Brasil retorna
HTTP 403 do CloudFront, com a mensagem *"configured to block access from your
country"*. O servidor **precisa rodar com saída brasileira**: máquina do
escritório ou provedor nacional. Nuvem fora do Brasil está descartada.

## Instalação

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env     # preencher DATAJUD_API_KEY
```

macOS e Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env       # preencher DATAJUD_API_KEY
```

Os comandos abaixo aparecem no formato macOS e Linux. No Windows, troque
`.venv/bin/` por `.venv\Scripts\`.

A chave do DataJud é pública, emitida pelo Departamento de Pesquisas Judiciárias
do Conselho Nacional de Justiça. Obtenha em
<https://datajud-wiki.cnj.jus.br/api-publica/acesso/>.

Registro no cliente Model Context Protocol:

```json
{
  "mcpServers": {
    "justica": {
      "command": "C:\\Users\\<usuario>\\OmniRoute\\packages\\mcp-justica\\.venv\\Scripts\\python.exe",
      "args": ["-m", "justica_mcp.server"],
      "env": { "DATAJUD_API_KEY": "..." }
    }
  }
}
```

Em macOS e Linux, `command` é o caminho absoluto de `.venv/bin/python`.

## Testes e diagnóstico de campo

Os testes de unidade não dependem de rede e rodam em qualquer máquina:

```bash
.venv/bin/python -m pytest tests/ -q
```

O diagnóstico de campo confronta o servidor com os tribunais de verdade e
**precisa rodar na máquina do escritório**, por causa do bloqueio por país:

```bash
.venv/bin/justica-diagnostico                      # relatório seguro
.venv/bin/justica-diagnostico --dias 30            # janela maior
.venv/bin/justica-diagnostico --processo <número>  # consulta um processo real
.venv/bin/justica-diagnostico --detalhe            # inclui teor das publicações
```

Ele verifica ambiente, roda os testes, confirma as siglas do Diário e os alias
do DataJud para os quatro tribunais, e imprime os nomes dos campos das respostas
reais, que é o que falta para fechar as pendências abaixo.

Por padrão a saída **não** inclui o teor das publicações, apenas estrutura e
contagens, porque publicação de Diário traz nome de parte e número de processo
da carteira. Use `--detalhe` apenas para leitura própria.

## Credenciais: o que este repositório não guarda

A Fase 1 **não usa credencial nenhuma**, de propósito. Ela entrega monitoramento
e movimentação sem tocar em senha, e por isso é a fatia que pode entrar em
produção sem risco de acesso.

Regras para a Fase 2, quando as credenciais entrarem:

- Senha e semente do segundo fator **nunca** no mesmo lugar, e nunca em planilha.
  Senha e semente juntas equivalem à conta inteira: o segundo fator deixa de ser
  segundo fator quando viaja ao lado da senha.
- Credencial **jamais** entra no contexto do modelo. O adaptador lê do cofre no
  momento da chamada; o modelo vê apenas o resultado.
- Nada de credencial em `.env` versionado, em código ou em log. A tabela de
  auditoria registra ação, tribunal, processo e solicitante, nunca segredo.
- Os códigos de segundo fator dos portais são gerados por aplicativo a partir de
  semente em base32, de modo que o servidor consegue produzi-los sem intervenção
  humana. Isso **aumenta** a responsabilidade sobre o cofre, não diminui.

## Fase 2: cofre de credenciais

Em construção. O que já existe:

O cofre guarda senha de portal e semente de segundo fator no **Gerenciador de
Credenciais do Windows** (Chaveiro no macOS, Secret Service no Linux), cifrado
pelo próprio sistema, por usuário. Decisão do operador em 21 de setembro de 2026.

**A regra que governa o módulo: o segredo nunca chega ao modelo.** O adaptador
lê do cofre no instante da chamada ao portal. Nenhuma ferramenta devolve senha,
semente ou código de segundo fator, e nada disso aparece em log, em auditoria
ou em mensagem de erro. A ferramenta `justica_credenciais_situacao` responde
apenas se a credencial existe, e um teste trava esse formato.

Login, senha e semente ficam em **entradas separadas**. Senha e semente juntas
equivalem à conta inteira: o segundo fator deixa de ser segundo fator quando
viaja ao lado da senha, que foi exatamente o defeito da planilha que originou
o projeto.

A prontidão exige login e senha, **não** o segundo fator. Está confirmado que o
eproc o exige de usuário externo desde abril de 2024, mas para os demais
portais não há confirmação, e exigir de todos marcaria como incompleta uma
credencial que funciona.

### Importar a planilha da banca

A planilha existente vira cofre com um comando, sem copiar e colar segredo:

```powershell
justica-credenciais importar --planilha "C:\caminho\senhas_tribunais.xlsx" --simular
justica-credenciais importar --planilha "C:\caminho\senhas_tribunais.xlsx"
```

A leitura acontece na máquina do advogado e o valor vai da célula direto para o
cofre do sistema. Nada é impresso na tela, nada passa por arquivo intermediário
e nada trafega por chat. O relatório mostra apenas quais campos entraram.

Os rótulos do escritório são mapeados para os códigos do projeto: `JFRJ` vira
`TRF2` e `TRT RJ` vira `TRT1`. Linha de tribunal fora do escopo é ignorada com
o motivo, em vez de falhar a importação inteira.

Campo de segundo fator inválido não derruba a linha: login e senha entram assim
mesmo, e a observação diz o que houve. É o caso do portal legado do Rio, cujo
campo de autenticação tem três caracteres e não é semente de autenticador.

Depois de conferir, **apague a planilha** ou guarde-a fora da máquina. Manter
senha e semente juntas num arquivo anula o segundo fator.

### Carregar manualmente

Quem carrega o cofre é o advogado, pelo terminal da própria máquina:

```powershell
justica-credenciais listar
justica-credenciais guardar --tribunal TJRJ --sistema eproc
justica-credenciais testar  --tribunal TJRJ --sistema eproc
justica-credenciais remover --tribunal TJRJ --sistema eproc
```

O valor digitado não aparece na tela e não passa por chat nem por arquivo.
O comando `guardar` gera um código logo após gravar a semente, para conferência
imediata contra o aplicativo autenticador; se não bater, a transcrição está
errada e nada mais adianta.

Confirmado que a semente da planilha é de segundo fator: 39 caracteres com
espaços viram 32 em base32 e geram código de seis dígitos válido, que é o que
o eproc pede desde que passou a exigir segundo fator para usuário externo.

### Trava de navegação

Construída **antes** do adaptador, de propósito: é ela que impede o clique que
consome prazo.

**Nega por padrão.** Nada é permitido a menos que esteja explicitamente na
lista de permissão, e a lista começa **vazia**. Uma tela só entra depois de
conferida em campo, com o advogado olhando. A consequência é intencional:
enquanto ninguém confirmou uma tela como segura, o adaptador não chega nela.

A alternativa, listar o que é perigoso, exigiria conhecer de antemão todas as
telas perigosas do portal. Errar nessa direção custa um prazo; errar na direção
de negar custa uma linha de configuração.

**Segunda camada.** Mesmo que uma tela entre na lista por engano durante a
conferência, termos de risco no endereço ou no seletor bloqueiam assim mesmo.
Um seletor `#dar-ciencia` deliberadamente liberado continua bloqueado. É
heurística, reforço do desenho principal, nunca a proteção em si.

**Modo ensaio.** Todo adaptador nasce em ensaio e roda assim a primeira vez:
registra o que faria e não executa nada. O advogado lê o relato antes de o
código ganhar permissão de agir. Ensaio não é modo permissivo, é modo que não
executa: o que seria bloqueado em produção também aparece como bloqueado no
relato.

Download está proibido em qualquer modo nesta versão.

Trinta testes cobrem a trava, incluindo cada termo de risco individualmente.

### Reconhecimento de portal

Primeiro passo do acesso autenticado, e o mais tímido possível. Abre um
endereço, **lê** a estrutura da página e relata. Não preenche campo, não clica
em botão, não autentica, não baixa nada.

```powershell
justica-portal reconhecer --url "<endereço copiado da barra do navegador>"
```

Exige o navegador do Playwright:

```powershell
pip install -e ".[navegador]"
playwright install chromium
```

Se a máquina já tem um Chrome ou Chromium, dá para apontar para ele e pular o
download: `$env:JUSTICA_CHROMIUM = "C:\caminho\para\chrome.exe"`.

O relatório traz título da página, campos de formulário (com nome, id, rótulo e
marcação do campo de senha), botões, e o que a trava decidiu em cada passo.
Campo oculto é ignorado. Nenhum dado de processo aparece: só a estrutura.

**A trava vale aqui também.** O endereço digitado na linha de comando é uma
autorização explícita do operador e vira permissão efêmera, válida só naquela
execução, ancorada em esquema, domínio e caminho. Uma página vizinha do mesmo
portal **não** fica autorizada por tabela, e um redirecionamento para fora do
endereço autorizado interrompe a leitura. Termo de risco no endereço bloqueia
mesmo que tenha sido o operador a digitá-lo.

### Ensaio de login

Preenche o formulário de login com a credencial do cofre e **confere o efeito**,
sem enviar.

```powershell
justica-portal ensaiar-login --url "<tela de login>" --tribunal TRF2 --sistema eproc
```

Por que não envia: se o preenchimento programático não funcionar e o código
clicar em Entrar assim mesmo, isso conta como tentativa de login falha, e
tentativas repetidas **bloqueiam a conta do advogado**. O risco não é uma
mensagem de erro, é perder o acesso.

A dúvida vem da própria página. O campo de senha visível do eproc traz
`inputmode=none`, que suprime o teclado do dispositivo: assinatura de portal com
teclado virtual, onde o valor talvez só se forme a partir de cliques na tela. Se
for o caso, preencher não surte efeito, e este ensaio revela isso sem custo.

A conferência lê de volta o **campo oculto**, que é o efetivamente enviado, e
compara apenas comprimentos. Nenhum valor de credencial é impresso.

A tela recebe permissão de preenchimento nos dois campos e **nenhuma permissão
de clique**. Assim, mesmo que o código tentasse enviar por engano, a trava
barraria: a impossibilidade não depende de ninguém lembrar.

Estrutura do eproc da Justiça Federal do Rio, confirmada em campo em 21 de
setembro de 2026: formulário `frmLogin`, usuário em `#txtUsuario`, senha visível
em `#pwdSenha` (tipo texto) e campo enviado em `input[name=pwdSenha]` (tipo
senha, oculto). Não há campo de segundo fator nessa tela, então o código de seis
dígitos deve ser pedido numa segunda tela, ainda não observada.

### Envio único de login

Primeiro comando do projeto que pratica um ato no portal.

```powershell
justica-portal entrar --url "<tela de login>" --tribunal TRF2 --sistema eproc --confirmo-tentativa-unica
```

Duas travas, pelo mesmo motivo: tentativa de login falha repetida **bloqueia a
conta do advogado**.

1. Exige confirmação expressa na linha de comando. Sem a opção, recusa e explica.
2. Clica **uma vez**. Não há repetição, nem em caso de falha. Se falhar, para e
   relata; decidir tentar de novo é do advogado, nunca do código.

Antes de clicar, confere que a senha chegou ao campo enviado. Sem essa
conferência, um espelhamento que falhasse produziria clique com campo vazio, que
é justamente o que consome tentativa e leva ao bloqueio.

Depois do envio apenas **lê** a tela seguinte, marcando o campo que tem cara de
segundo fator. Não preenche o código, não navega, não baixa. O destino do
redirecionamento passa pela trava: termo de risco no endereço interrompe a
leitura. A tentativa fica registrada na auditoria local.

O espelhamento do eproc da Justiça Federal do Rio foi confirmado em campo em 21
de setembro de 2026: o valor preenchido no campo visível chega ao campo oculto,
então o receio de teclado virtual, levantado pelo `inputmode=none`, não se
confirmou.

### Autenticação completa

```powershell
justica-portal autenticar --url "<tela de login>" --tribunal TRF2 --sistema eproc --confirmo-tentativa-unica
```

Credencial e segundo fator numa execução só, porque a tela do código só existe
dentro da sessão aberta pelo login. Uma tentativa em cada etapa: código errado
também conta como tentativa falha.

O código é gerado pelo cofre com **janela útil mínima**. Um código gerado a dois
segundos do fim expira entre o preenchimento e o envio, e o portal registraria
falha por um motivo que não é culpa da credencial. Esperar a próxima janela
custa segundos; a tentativa perdida custa mais.

O que a tela de segundo fator do eproc revelou, em 21 de setembro de 2026:
o campo é `#txtAcessoCodigo` e o botão `#btnValidar`, mas ao lado deles ficam
**`Desativar 2FA`**, **`Cancelar Dispositivos Liberados`** e a caixa **"Não usar
o 2FA neste dispositivo e navegador"**.

Nenhum dos três é tocado. A caixa, em particular, **nunca é marcada**: marcá-la
facilitaria as próximas execuções, e é exatamente por isso que não se marca,
porque o cofre já gera o código sozinho e não há ganho, só perda de proteção da
conta. Os três ficam barrados duas vezes, por não estarem na lista de permissão
e por casarem com termo de risco.

Essa tela obrigou a ampliar os termos de risco para uma segunda classe: ações
que **enfraquecem a segurança da conta**. Não consomem prazo, mas o dano é
duradouro e silencioso.

### Seleção de perfil

Terceira etapa, descoberta em campo: depois do segundo fator o eproc pode pedir
que se escolha entre as inscrições ligadas ao mesmo acesso.

**O perfil escolhido determina quais processos o sistema mostra.** Escolher por
conta própria daria visão incompleta sem nenhum aviso, então sem indicação o
comando lista as opções e para:

```powershell
justica-portal autenticar --url "..." --tribunal TRF2 --sistema eproc --perfil RJ168943 --confirmo-tentativa-unica
```

O casamento é por trecho do rótulo, sem distinguir caixa. Perfil que não
corresponde a nada **não é aproximado**: falhar é melhor que entrar no perfil
errado.

A tela de perfil fica em endereço próprio, fora da permissão do login, e a
trava barrou o clique na primeira versão. Ela estava certa. A autorização foi
feita estreita: vale só para aquela tela e só para o botão do perfil escolhido,
como permissão separada, em vez de liberar o endereço inteiro.

### O que a autenticação em campo revelou

Executada com sucesso no eproc da Justiça Federal do Rio em 21 de setembro de
2026: credencial, segundo fator e perfil, sete ações, todas autorizadas.

Três descobertas que mudaram o código:

**A chegada não é o painel.** Quando o portal exige atualização cadastral, a
autenticação desemboca em `acao=pessoa_alterar`, a tela "Alterar Cadastro", com
campos de identidade editáveis e um botão `Salvar`. Um clique ali alteraria o
cadastro do advogado no tribunal. Os termos de risco ganharam uma terceira
classe para isso: `salvar`, `gravar`, `excluir`, `remover`.

**A barra superior é duplicada.** O eproc monta duas, uma para tela grande e
outra para telefone, com os **mesmos identificadores**. O campo de busca rápida
`#txtNumProcessoPesquisaRapida` aparece duas vezes, uma visível e outra oculta.
Preencher a oculta falha em silêncio: não levanta erro, simplesmente não
acontece nada. Daí a função `elemento_visivel`, que escolhe a ocorrência que
está de fato na tela.

**A busca rápida está em todas as telas.** `#txtNumProcessoPesquisaRapida` com
`btnPesquisaRapidaSubmit` é o caminho para a consulta de processo autenticada.

### Consulta autenticada de processo

```powershell
justica-portal consultar --url "..." --tribunal TRF2 --sistema eproc --perfil RJ168943 --processo "5001234-54.2023.4.02.5101" --confirmo-tentativa-unica
```

Autentica e consulta pela barra de busca rápida que o eproc mantém em **todas**
as telas. Isso contorna a tela de atualização cadastral em que a autenticação
desemboca quando o portal a exige: o campo de busca vive em
`formPesquisaRapida`, formulário distinto do `frmPessoaAlteracao`, então
consultar não encosta no cadastro. Um teste garante que os campos de identidade
e o botão `Salvar` continuam barrados enquanto a busca é usada.

Somente leitura: preenche o número, envia a busca e relata a tela, com as
tabelas encontradas e suas colunas. Não abre documento, não baixa nada, não
toca em expediente.

O número é validado antes de qualquer ida à rede. Número com dígito errado
devolveria "não encontrado", e o agente concluiria que o processo não existe.

### Extração dos dados do processo

A consulta autenticada foi executada contra o eproc real em 21 de setembro de
2026 e a tela de processo revelou a estrutura:

| Tabela | Colunas |
| --- | --- |
| `#tblEventos` | Evento, Data/Hora, Descrição, Usuário, Documentos |
| `#tblPartesERepresentantes` | AUTOR, RÉU (como **cabeçalho**, não como valor) |
| sem identificador | Código, Descrição, Principal (assuntos) |

Os polos vêm do cabeçalho das colunas, e não de uma coluna de valor. Ler ao
contrário inverteria autor e réu, que é um erro grave num resumo processual.

A coluna Documentos traz os links dos arquivos. Eles são apenas **listados**,
com rótulo e endereço. Abrir é outro ato e outra decisão.

Duas escolhas sobre o destino do que sai daqui:

**O conteúdo vai para arquivo, o terminal recebe só um resumo.** São dezenas de
eventos por processo, e despejá-los na tela convida a colar dado de cliente
onde não deve. O arquivo fica em `~/.justica-mcp/consultas/`.

**Os eventos alimentam o mecanismo de comparação da Fase 1.** Cada consulta
grava um snapshot, então `verificar_novos_andamentos` passa a enxergar também
o acervo autenticado, e não só o que a base nacional publica.

### Ferramentas autenticadas no servidor

`justica_consultar_processo_autenticado` traz o que a base nacional não tem:
partes, eventos completos e a lista de documentos de cada evento.

**Desligado por padrão.** Ligar (`JUSTICA_ACESSO_AUTENTICADO=1`) permite que o
agente dispare autenticação real no tribunal com a credencial do advogado, e
isso é decisão do operador, não um comportamento herdado da instalação.

O endereço e o perfil de cada portal ficam no ambiente, não como parâmetro de
ferramenta: o agente não deve precisar saber o endereço do portal nem ter como
apontar a autenticação para outro lugar.

**O que conta como tentativa.** Conta o ato de a credencial **chegar ao
portal**, venha do comando `autenticar` ou do `entrar`: o bloqueio da conta não
distingue por qual comando a senha foi enviada. O **desfecho** de uma tentativa,
como a tela do segundo fator não aparecer, é auditado com nome próprio e não
conta de novo. Execução que para antes do envio, no desafio do Cloudflare por
exemplo, não gasta tentativa alguma, porque nada chegou ao portal.

**Teto de tentativas.** Até aqui a proteção contra bloqueio de conta era a
confirmação na linha de comando: um humano digitava a opção a cada execução.
Expor a autenticação como ferramenta quebra essa premissa, porque um agente que
tente de novo diante de erro queima as tentativas da conta em segundos, sem
ninguém no meio para perceber. O teto (6 por hora, ajustável) é conferido
**antes** de abrir o navegador, e a ferramenta é marcada como **não
idempotente**, para o agente saber que repetir custa.

`justica_acesso_autenticado_situacao` responde se está ligado, quais portais
estão configurados e quantas tentativas ainda cabem, para o agente não gastar
tentativa à toa nem prometer o que o servidor não pode fazer.

### Cópia de documentos

```powershell
justica-portal consultar --tribunal TRF2 --sistema eproc --processo "..."                      # auto
justica-portal consultar --tribunal TRF2 --sistema eproc --processo "..." --documentos integra
justica-portal consultar --tribunal TRF2 --sistema eproc --processo "..." --documentos ultimos:5
justica-portal consultar --tribunal TRF2 --sistema eproc --processo "..." --documentos nenhum
```

O `--url` deixou de ser obrigatorio: quando omitido, vem do `.env`
(`JUSTICA_PORTAL_<TRIBUNAL>_<SISTEMA>_URL`), e o comando avisa de onde o tirou.
Repetir o endereco a mao a cada execucao convidava a errar o destino da
autenticacao, que e exatamente o que este projeto existe para evitar. O que vier
no comando continua tendo precedencia sobre o arquivo.

Baixar autos esteve **proibido em qualquer modo** até 21 de setembro de 2026,
quando o operador decidiu habilitar a cópia. A mudança foi de "nunca" para
"mediante autorização", **não** para "livre": o download continua negado por
padrão e só passa no comando que o pede, com o alvo dentro da lista de permissão
e com os termos de risco valendo.

**Os arquivos são buscados pelo endereço, reaproveitando a sessão, e não
clicando nos links.** Clicar seria o caminho óbvio e é o pior: pode abrir aba,
disparar script ou cair em elemento vizinho, e este projeto existe porque
clique errado no portal custa caro. Buscar pelo endereço não clica, não navega
e não muda a página. A única exceção é a cópia integral, cujo botão não tem
endereço próprio.

Documento vindo de evento de comunicação processual é **sinalizado** no
relatório, não bloqueado: documento de evento é parte dos autos. Mas o aviso
existe para o advogado conferir o que foi copiado.

[Não verificado] Se baixar documento do próprio processo produz algum registro
de ciência no eproc. A leitura do artigo 5º, §3º, da lei nº. 11.419/06 é que a
ciência se dá pela consulta ao teor da **comunicação**, no painel de
expedientes, e não pela leitura dos autos, e esse painel nunca é tocado. Ainda
assim, a primeira execução merece conferência do advogado no próprio portal.

### Acervo de cópias: íntegra na primeira vez, complemento depois

`--documentos auto`, que é o padrão, olha primeiro a pasta do processo:

| Pasta do processo | O que ele faz |
| --- | --- |
| Sem nenhuma cópia | Baixa a **íntegra** pelo botão do portal |
| Já tem cópia | Baixa **só o que falta** e diz quais folhas o complemento cobre |

A numeração de folhas é a **da cópia da banca**, contínua e crescente: a íntegra
ocupa de 1 até N, e cada complemento segue de N+1 em diante. Não é a numeração
do tribunal, que o eproc nem usa, porque lá são eventos. Serve para citar
"fls. 245/250 da cópia" e achar o documento.

Sem contagem confiável de páginas o índice registra a ausência em vez de chutar
um número: folha errada em citação é pior que folha ausente.

Dois filtros decidem o que entra no complemento, e os dois são necessários:

1. **Eventos posteriores ao que a íntegra alcançou.** A íntegra já contém os
   documentos dos eventos anteriores a ela. Sem este filtro, o complemento
   recopiaria o processo inteiro a cada consulta. O índice guarda, em
   `evento_ate`, até qual evento cada íntegra cobre.
2. **Documentos ainda não registrados no índice**, para não repetir os
   complementos anteriores.

A memória disso é o `indice.json`, gravado na própria pasta do processo. Apagar
o índice não apaga as cópias, mas faz a próxima execução tratar a pasta como
nova.

#### Onde os arquivos ficam

Padrão: `~/.justica-mcp/processos/<numero>/`. Para apontar à pasta do
escritório, ponha no `.env`:

```ini
JUSTICA_PASTA_COPIAS=G:\Meu Drive\4.Processos\Cópias
```

Cada processo ganha uma subpasta com o número sem pontuação, e dentro dela ficam
os PDF com nome ordenável (`ev0068-PET1.pdf`) mais o `indice.json`.

A subpasta é criada **na consulta**, e não no instante de gravar o primeiro
arquivo. Uma consulta que não copiasse nada não deixava pasta alguma, e o
advogado iria procurar no Drive um lugar que nunca foi criado. A pasta é o
endereço do processo no acervo, não um efeito colateral do download.

A pasta de cópias é do escritório e pode já conter arquivos que alguém baixou à
mão. PDF que não esteja no índice é **sinalizado na tela**, não contado como
cópia: sem o índice não há como saber quais folhas ele cobre, e tratá-lo como
cobertura seria concluir demais a partir da ausência de um arquivo de controle.

[Inferência] Apontar para uma pasta do Google Drive sincronizada localmente faz
o Drive subir as cópias sozinho, o que é o comportamento desejado, mas também
significa que **os autos saem da máquina** para a nuvem do escritório. É decisão
do operador, não do servidor; registro aqui para ficar explícito.

Cada cópia entra na auditoria, agora com a faixa de folhas no lugar do tamanho
em bytes: "fls. 241/252" diz algo ao advogado, "31244 bytes" não.

### Desafio "Confirme que é humano" do Cloudflare

Verificado em campo em 21 de setembro de 2026: o eproc do Tribunal Regional
Federal da 2ª Região passou a exibir o desafio do Cloudflare antes da tela de
login.

**Este projeto não resolve, não contorna e não disfarça esse desafio.** Ele é um
controle de segurança do tribunal. Automatizá-lo seria contornar proteção de
terceiro em nome do advogado, com o risco recaindo sobre a inscrição dele, e
nenhuma comodidade compensa isso.

O caminho oferecido é o honesto e é o único: o programa **detecta** o desafio,
**avisa** e **espera** o operador marcar a caixa na janela já aberta. Verificação
humana feita por um humano.

O desafio aparece em dois momentos, e os dois são tratados: ao abrir a página e
**depois do envio da credencial**. Neste segundo caso o portal devolve
`acao=principal&acao_retorno=login`, e a espera aceita como conclusão tanto a
tela do segundo fator quanto a de seleção de perfil, porque o portal pode ir
direto para qualquer uma das duas.

```powershell
justica-portal consultar --tribunal TRF2 --sistema eproc --processo "..." --espera-humana 240
```

O padrão são 180 segundos. É espera de pessoa caminhando até a janela, não
espera de rede, por isso é generosa.

#### Por que o desafio aparecia em toda execução

Defeito do projeto, não rigor do Cloudflare. Cada execução abria um navegador
**vazio** (`launch` mais `new_page`), sem cookie nenhum, então o advogado era um
visitante inédito toda vez. Cada reaparição custava uma tentativa do teto e a
presença dele diante da tela.

O navegador passa a usar **perfil persistente**, na pasta de estado
(`~/.justica-mcp/navegador/`). Isso não resolve, não contorna e não disfarça o
desafio: quem responde continua sendo uma pessoa, uma vez. O que muda é que a
liberação obtida por ela deixa de ser jogada fora ao fechar o programa, que é o
comportamento normal de qualquer navegador. Descartar o perfil não tornava nada
mais seguro; apenas obrigava a repetir a prova já dada.

Medido nesta base de código, com o Chromium do próprio Playwright:

| Tipo de cookie | Sobrevive ao fechamento |
| --- | --- |
| Com prazo de validade, como a liberação do desafio | sim |
| Só de sessão, como o login do portal | não |

Ou seja: o desafio deve parar de aparecer a cada execução, e o **login continua
sendo pedido**, porque o cookie de sessão do portal não fica em disco. É o
equilíbrio desejado.

O preço é real e fica registrado: a pasta passa a conter cookie do portal. Quem
tiver acesso a ela tem acesso ao que ele cobrir, enquanto valer. Por isso fica na
pasta de estado, junto da auditoria, e não em lugar temporário.
`JUSTICA_NAVEGADOR_EFEMERO=1` devolve o descarte a cada execução, para quem
preferir pagar o desafio toda vez.

#### O desafio reprova o navegador automatizado

**Verificado em campo em 21 de setembro de 2026, e é a conclusão mais importante
desta fase.** O operador marcou a caixa várias vezes e o Cloudflare respondeu
**"Falha na verificação"**.

O que foi recusado não é a pessoa: é o **navegador automatizado**. O tribunal
ligou um controle cuja finalidade exata é impedir acesso por programa, e ele está
cumprindo essa finalidade. Marcar a caixa mais vezes não muda isso.

Fazer o Turnstile aceitar exigiria **disfarçar a automação**, e este projeto não
faz isso. Não é preciosismo: é a linha entre usar o acesso que o advogado tem e
falsificar a natureza de quem acessa.

O programa passa a reconhecer a reprovação e a dizer o que ela é, em vez de
deixar o operador clicando em vão. O texto vive dentro do quadro do próprio
Cloudflare, então a busca percorre os quadros da página.

**Consequência para o projeto:** enquanto esse controle estiver ativo, o acesso
autenticado ao eproc por este servidor **não é viável**, e nenhuma quantidade de
código muda isso. O que continua valendo:

| Caminho | Situação |
| --- | --- |
| Fontes públicas (base nacional e Diário Eletrônico) | Funcionam, sem desafio nem login |
| Navegador do próprio advogado, à mão | Funciona, é o que as habilidades já prescrevem |
| Via programática autorizada pelo tribunal | [Não verificado] Precisa ser perguntado ao tribunal |

#### O que o eproc faz depois do desafio

Confirmado em campo em 21 de setembro de 2026, com o operador diante da tela:
ele marcou a caixa e o portal **voltou ao formulário de login**, não ao segundo
fator. A primeira credencial nunca chegou a ser avaliada, foi desviada para o
desafio.

Por padrão o comando **não reenvia sozinho**, porque credencial recusada devolve
a mesma tela e reenviar às cegas é como se bloqueia uma conta. Dois caminhos:

```powershell
# repetir o comando: a liberação fica guardada no perfil, e a 2ª execução passa direto
justica-portal consultar --tribunal TRF2 --sistema eproc --processo "..." --confirmo-tentativa-unica

# ou autorizar o reenvio na hora, numa execução só
justica-portal consultar --tribunal TRF2 --sistema eproc --processo "..." --confirmo-tentativa-unica --reenviar-apos-desafio
```

O reenvio só acontece quando **não há mensagem de erro na tela**. Havendo
mensagem, ele para e a imprime, mesmo com a opção ligada. E mantém as mesmas
travas do primeiro envio, inclusive a conferência de que a senha chegou ao campo
efetivamente enviado.

Ele também não conta como nova tentativa no teto, pelo mesmo motivo por que
existe: é a conclusão do envio já contado, não um segundo envio.

Com `--oculto` não há janela onde responder, então o comando **recusa e explica**
em vez de esperar em silêncio até o tempo acabar. Pela mesma razão, a ferramenta
do servidor, que roda sempre oculta, não passa por telas com desafio: quando ele
aparece, o acesso tem de ser feito pela linha de comando, com o advogado
presente.

### O que ainda falta na Fase 2

Já em campo, contra o eproc do Tribunal Regional Federal da 2ª Região:
autenticação com segundo fator, escolha de perfil, consulta de processo com
partes e eventos, cópia de documentos e cópia integral.

Falta:

- **Listagem de intimações pendentes sem abrir.** Decisão do operador: listar
  sim, abrir não. A primeira execução precisa ser assistida, porque a premissa
  de que listar não dispara ciência ainda não foi confirmada para o eproc.
- **O segundo clique da cópia integral.** Verificado em campo em 21 de setembro
  de 2026: o clique em `#btnDownloadCompletoRS` **não devolve arquivo**. O eproc
  abre uma tela intermediária pedindo que a cópia seja gerada, e o download só
  vem depois disso. O comando não adivinha esse segundo clique: quando o arquivo
  não chega, ele **relata a tela** que apareceu, com os botões visíveis e as
  ligações cujo texto contenha "gerar", "baixar", "download", "completo" ou
  "íntegra", inclusive em aba nova, e para sem clicar em nada. O seletor real
  entra no código depois de conferido nesse relato, nunca antes.
- **Sondagem real de sistema**, via `registrar_sonda`, que hoje não tem nenhuma
  sonda registrada.
- **Os outros três tribunais do escopo**: PJe, e-SAJ e o portal legado do Rio de
  Janeiro. Só o eproc tem adaptador autenticado.

## Próximas fases
- **Fase 3**: PJe do Rio de Janeiro e do Tribunal Regional do Trabalho da 1ª
  Região; depois São Paulo. O DCP é legado em extinção pela migração ao eproc e
  provavelmente não merece adaptador de documentos.
- **Prazos**: a contagem fica na habilidade `analise-processual`, não aqui. Este
  servidor entrega o movimento e a publicação com proveniência; a contagem exige
  calendário forense por tribunal e permanece sempre conferível, nunca automática.

## Validação de campo, 21 de setembro de 2026

Executado na máquina do escritório, com saída brasileira. Resultado:

- Diário de Justiça Eletrônico Nacional responde HTTP 200, sem autenticação.
- As siglas `TJRJ`, `TJSP`, `TRT1` e `TRF2` são aceitas.
- Os 27 testes de unidade passam também no Python 3.13.

Confirmado em campo, com amostra real:

- O filtro por inscrição na Ordem aplica **número e seccional** corretamente.
  Numa amostra de cinco publicações, as cinco nomeavam exatamente 218174/RJ.
- A estrutura de `destinatarioadvogados[].advogado` é
  `{id, nome, numero_oab, uf_oab}`.
- `destinatarios[]` traz `{nome, comunicacao_id, polo}`.
- Publicações de tribunais fora do estado da inscrição (Roraima, Amazonas)
  são legítimas: a banca atua em causas fora do Rio ao lado de colegas de
  inscrição carioca. Distribuição por tribunal, sozinha, não indica erro de
  filtro.

Cinco correções nasceram dessa execução:

1. **Campos que faltavam.** O adaptador tinha sido escrito a partir de
   documentação de terceiro e ignorava `id`, `numeroComunicacao`, `nomeClasse`,
   `codigoClasse` e `numeroprocessocommascara`.
2. **Cancelamento.** Uma publicação pode ser cancelada (`ativo`,
   `motivo_cancelamento`, `data_cancelamento`). O adaptador não olhava esses
   campos, e uma publicação cancelada tratada como viva produziria prazo
   fantasma. Agora vem com `cancelada` e um alerta explícito. O campo `status`
   traz códigos de uma letra cujo significado não foi confirmado em fonte
   oficial, então viaja cru e não é interpretado.
3. **Contagem saturada.** O campo `count` satura em 10.000: os quatro tribunais
   devolveram exatamente esse valor, o que é impossível como total real. Agora
   a resposta traz `total_e_estimativa` e diz que o total é maior ou igual,
   em vez de afirmar um número falso.
4. **Advogados achatados e conferidos.** A lista de advogados vem normalizada
   com número e seccional, e cada publicação traz
   `inscricao_consultada_confere`. O filtro do servidor funciona hoje; a
   conferência é guarda de regressão, porque uma mudança nesse filtro falharia
   em **silêncio** e a banca passaria a monitorar processo de terceiro sem
   qualquer sinal.
5. **O `.env` passou a ser lido.** O README mandava criar o arquivo, mas o
   código só consultava variáveis de ambiente do sistema. Quem seguisse a
   instrução ficaria sem a chave sem entender por quê.

## Validação do DataJud, 21 de setembro de 2026

Consulta autenticada executada na máquina do escritório, com a chave pública
do Conselho Nacional de Justiça.

- Os quatro alias respondem: `api_publica_tjrj`, `api_publica_tjsp`,
  `api_publica_trt1` e `api_publica_trf2`. **A pendência do alias federal está
  resolvida**: a Justiça Federal da 2ª Região responde sob `api_publica_trf2`.
- Consulta a um processo real do Rio devolveu classe, órgão julgador, grau,
  nível de sigilo e 81 movimentos.
- **Confirmado que não há campo de partes**, como a matriz de capacidades já
  declarava. A recusa de `buscar_por_parte` está correta.

Campos de `_source` observados: `id`, `tribunal`, `grau`, `numeroProcesso`,
`dataAjuizamento`, `nivelSigilo`, `orgaoJulgador`, `classe`, `sistema`,
`formato`, `dataHoraUltimaAtualizacao`, `movimentos`, `assuntos`.

Dois deles mudam o projeto:

- **`dataHoraUltimaAtualizacao`** informa quando a base nacional recebeu a ficha
  do tribunal. Passa a integrar a proveniência: sem isso, o agente não sabia se
  olhava dado de hoje ou de semanas atrás, e o aviso de que "o DataJud atrasa"
  era genérico. Agora é mensurável por processo.
- **`sistema`** traz `{'codigo': 1, 'nome': 'PJe'}`, ou seja, a base declara em
  qual sistema o processo tramita. **Passou a alimentar o resolvedor**, na
  frente da pista de migração: um processo de 2019 no Rio que antes voltava
  `indeterminado` agora resolve, e um de 2026 onde a heurística chutaria
  `eproc` responde `PJe` se for isso que a base diz.

  Duas salvaguardas, porque a base pode atrasar:

  - O casamento é feito pelo **nome normalizado**, nunca pelo `codigo`. Só o
    código 1 foi observado, e montar uma tabela de códigos a partir de uma
    amostra seria chute com aparência de mapeamento. Nome desconhecido devolve
    `indeterminado` dizendo o que a fonte respondeu, em vez de forçar um palpite.
  - Tribunal com mais de um sistema candidato (Rio de Janeiro e São Paulo, ambos
    em migração) **nunca** recebe confiança alta, por mais recente que seja a
    ficha. É exatamente onde a base pode não ter registrado uma migração já
    ocorrida, e onde errar custa mais caro.

Um defeito real apareceu por causa dessa execução: com a chave presente no
ambiente, `AdaptadorDataJud(chave="")` passava a usar a chave do ambiente, por
causa de um encadeamento com `or`. Quem passasse configuração vazia esperando
ficar sem chave consultaria silenciosamente com a chave de outro contexto.
Corrigido: `None` significa "leia do ambiente", `""` significa "sem chave".
A correção foi validada revertendo-a e confirmando que o teste falha.

## Pendências que dependem do operador

1. Confirmar a natureza do campo de três caracteres do DCP na planilha.
2. Rotacionar as senhas antes de importar, se alguma já circulou fora do cofre.
3. Observar os nomes de sistema devolvidos para eproc, e-SAJ e DCP. Só `PJe`
   foi visto em campo; os demais estão no mapa como rótulo esperado, ainda não
   confirmado.
4. Testar, tribunal a tribunal, se as intimações da banca aparecem no Diário.
