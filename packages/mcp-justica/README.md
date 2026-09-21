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
| Tribunal de Justiça do Estado de São Paulo | e-SAJ, eproc | eproc apenas |
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
  cache válido, sondagem autenticada (Fase 2), pista de migração, indeterminado.
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

## Próximas fases

- **Fase 2**: adaptadores autenticados de eproc para o Tribunal de Justiça do
  Estado do Rio de Janeiro e para a Justiça Federal da 2ª Região, com cofre de
  segredos, sondagem real de sistema (`registrar_sonda`) e download de documentos.
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
- **`sistema`** pode permitir que `resolver_sistema` decida por evidência da
  própria base, em vez de cair na pista de migração. O conteúdo ainda não foi
  observado, então o campo viaja cru como `sistema_informado_pela_fonte` e
  **não** alimenta o resolvedor até ser confirmado.

Um defeito real apareceu por causa dessa execução: com a chave presente no
ambiente, `AdaptadorDataJud(chave="")` passava a usar a chave do ambiente, por
causa de um encadeamento com `or`. Quem passasse configuração vazia esperando
ficar sem chave consultaria silenciosamente com a chave de outro contexto.
Corrigido: `None` significa "leia do ambiente", `""` significa "sem chave".
A correção foi validada revertendo-a e confirmando que o teste falha.

## Pendências que dependem do operador

1. Confirmar a natureza do campo de três caracteres do DCP na planilha.
2. Credencial de e-SAJ para São Paulo: sem ela, o acervo não migrado fica sem
   acesso autenticado.
3. Observar o conteúdo de `sistema` no DataJud e, se servir, ligá-lo ao
   resolvedor.
4. Testar, tribunal a tribunal, se as intimações da banca aparecem no Diário.
