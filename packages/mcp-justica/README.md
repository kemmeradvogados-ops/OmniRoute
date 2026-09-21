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

### O que ainda falta na Fase 2

- Adaptador autenticado de eproc (cobre três dos quatro tribunais do escopo).
- Sondagem real de sistema, via `registrar_sonda`, que hoje não tem nenhuma
  sonda registrada.
- Conferência em campo das telas do eproc, com `justica-portal reconhecer`,
  para preencher a lista de permissão, que hoje está vazia e bloqueia tudo.
- O passo de autenticação, que só será escrito depois que o reconhecimento
  mostrar a estrutura real da tela de login.
- Listagem de intimações pendentes **sem abrir**. Decisão do operador: listar
  sim, abrir não. A primeira execução precisa ser assistida, porque a premissa
  de que listar não dispara ciência ainda não foi confirmada para o eproc.
- Download de documentos e da íntegra.

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
