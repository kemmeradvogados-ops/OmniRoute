#!/usr/bin/env node
/**
 * Lancador do conector `justica_mcp` para o aplicativo do Claude.
 *
 * Por que existe um lancador em Node para um servidor em Python.
 *
 * A especificacao do pacote `.mcpb` manda um servidor Python trazer TODAS as
 * suas dependencias dentro do arquivo. As deste servidor incluem codigo
 * compilado por plataforma (`pydantic-core`, `cryptography`, `greenlet`) e o
 * Chromium do Playwright, que sozinho passa de 150 MB. Um pacote assim teria
 * de ser montado uma vez por sistema operacional, e ainda assim duplicaria o
 * ambiente que a maquina ja tem.
 *
 * Entao o pacote nao carrega o servidor: ele APONTA para o ambiente virtual ja
 * instalado. O Node e usado porque o aplicativo do Claude o traz consigo,
 * entao `command: "node"` funciona sem nada instalado a mais, enquanto
 * `command: "python"` dependeria de o Python estar no caminho do sistema.
 *
 * Este arquivo nao fala o protocolo. Ele confere a configuracao, entrega a
 * execucao ao Python do ambiente virtual e repassa os canais.
 *
 * POR QUE NAO `stdio: "inherit"`, que era como estava ate 23/10/2026.
 *
 * Com `inherit`, o filho recebe os MESMOS descritores do pai, e quem le a
 * entrada padrao passa a ser uma disputa entre os dois. No Windows, o
 * resultado observado foi o pior possivel: o Python subia, nao recebia o
 * `initialize` que o aplicativo tinha escrito, via a entrada acabar e
 * encerrava em silencio, com codigo zero. O log do aplicativo registrava
 * apenas "process exiting early", sem erro nenhum, porque erro nao houve: um
 * servidor que fala pela entrada padrao encerra mesmo quando ela acaba.
 *
 * O mesmo Python, chamado a mao na mesma maquina, respondia ao `initialize`
 * em um segundo, com saida limpa. Isso isolou a causa no repasse.
 *
 * Agora os canais sao CANOS explicitos, e este arquivo os liga ponta a ponta.
 * O erro padrao continua herdado, de proposito: e por ele que um rastro de
 * pilha do Python chega ao log do aplicativo.
 */

import { spawn } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { join } from "node:path";

/** Recado de erro que uma PESSOA consiga agir, nao um rastro de pilha. */
function desistir(titulo, linhas) {
  process.stderr.write(`\n[conector justica] ${titulo}\n`);
  for (const linha of linhas) process.stderr.write(`  ${linha}\n`);
  process.stderr.write("\n");
  process.exit(1);
}

const python = (process.env.JUSTICA_PYTHON || "").trim();
const pacote = (process.env.JUSTICA_PACOTE || "").trim();

if (!python) {
  desistir("Falta dizer qual Python usar.", [
    "Em Configuracoes > Extensoes, abra este conector e preencha",
    "'Python do ambiente virtual'. O arquivo fica dentro da pasta do",
    "projeto, em .venv\\Scripts\\python.exe no Windows ou",
    ".venv/bin/python no macOS e no Linux.",
  ]);
}
if (!existsSync(python) || !statSync(python).isFile()) {
  desistir("O Python indicado nao existe nesse caminho.", [
    python,
    "",
    "Confira o campo 'Python do ambiente virtual' nas configuracoes do",
    "conector. Ele aponta para um ARQUIVO, nao para a pasta.",
  ]);
}
if (!pacote) {
  desistir("Falta dizer onde esta o projeto.", [
    "Preencha 'Pasta do projeto' nas configuracoes do conector. E a pasta",
    "que contem pyproject.toml e src.",
  ]);
}
if (!existsSync(join(pacote, "pyproject.toml"))) {
  desistir("A pasta indicada nao parece ser a do projeto.", [
    pacote,
    "",
    "Nao ha um pyproject.toml ali dentro. A pasta certa e a que contem",
    "pyproject.toml, src e tests.",
  ]);
}

// O ambiente do processo filho. Variavel VAZIA e retirada de proposito: o
// campo da chave do DataJud e opcional, e um valor vazio vindo dele entraria
// no ambiente como "", que TEM precedencia sobre o .env. O efeito seria
// desligar uma chave que ja funcionava, por causa de um campo em branco.
const ambiente = { ...process.env, PYTHONUNBUFFERED: "1" };

/**
 * Um valor assim e MOLDE de substituicao que nao foi substituido.
 *
 * Conferido em campo em 26/10/2026. O manifesto pede `${user_config.<campo>}`
 * e o aplicativo troca pelo que o advogado digitou. Com o campo da chave do
 * DataJud VAZIO, ele nao mandou vazio: mandou o proprio texto do molde.
 *
 * Isso e pior que mandar vazio. O valor nao fica em branco, entao o descarte
 * abaixo nao o pegava; ele vencia o `.env` por precedencia de ambiente e
 * seguia como credencial ate o Conselho Nacional de Justica, que respondia
 * 401 como se a chave gravada estivesse errada. A chave estava certa, e
 * respondia 200 quando enviada por fora. Custou uma noite achar.
 */
const moldeNaoSubstituido = (v) => /^\$\{[^}]*\}$/.test(v);

for (const chave of ["DATAJUD_API_KEY", "JUSTICA_PASTA_COPIAS"]) {
  const valor = (ambiente[chave] || "").trim();
  if (!valor || moldeNaoSubstituido(valor)) delete ambiente[chave];
}
delete ambiente.JUSTICA_PYTHON;
delete ambiente.JUSTICA_PACOTE;

const filho = spawn(python, ["-m", "justica_mcp.server"], {
  cwd: pacote,
  env: ambiente,
  // entrada e saida por cano, erro herdado para o log do aplicativo.
  stdio: ["pipe", "pipe", "inherit"],
  // Sem isto, o Windows abre uma JANELA DE CONSOLE preta a cada vez que o
  // conector sobe, e ela fica aberta enquanto o servidor viver. Nao e defeito
  // do programa: `python.exe` e aplicacao de console, e o Windows cria um
  // console para ela quando quem a chamou nao tem um. `windowsHide` manda o
  // Node criar o processo sem janela. Em outros sistemas a opcao e ignorada.
  windowsHide: true,
});

// O cano quebra quando o outro lado morre primeiro, e isso nao e defeito que
// mereca rastro de pilha: e a ordem de encerramento. Sem estes ouvintes, o
// Node derruba o processo com EPIPE e o log fica pior do que estava.
for (const canal of [process.stdin, process.stdout, filho.stdin, filho.stdout]) {
  if (canal) canal.on("error", () => { /* o outro lado fechou */ });
}
/**
 * A SONDA DE ERA, respondida aqui e nao pelo Python.
 *
 * Antes de aceitar a extensao, o aplicativo sobe um processo so para
 * perguntar qual revisao de protocolo o servidor fala, e espera QUATRO
 * SEGUNDOS pela resposta. Medido no registro dele em 26/10/2026: 4,001s,
 * 4,001s, 4,010s e 4,004s, sempre terminando em "legacy (sibling did not
 * complete the exchange)".
 *
 * O servidor responde certo, so que tarde. Numa maquina Windows do
 * escritorio foram 8,55s do nascimento do processo ate a primeira resposta,
 * contra 0,7s em Linux; so carregar a biblioteca leva de 2,6s a 4,5s la. O
 * nosso codigo custa 0,07s desse total, entao nao ha o que otimizar do nosso
 * lado: o peso e da biblioteca, que precisa estar carregada para responder.
 *
 * Este processo, porem, ja esta de pe. Ele responde em milissegundos.
 *
 * O QUE ISSO CUSTA, dito sem disfarce: o lancador afirma, em nome de um
 * servidor que ainda nao subiu, o que esse servidor vai dizer. Mudando a
 * biblioteca de revisao sem mudar estas constantes, ele mentiria. O teste
 * `test_o_descritor_do_lancador_bate_com_o_servidor_de_verdade` sobe o
 * servidor Python, faz a mesma pergunta e exige resposta identica, de modo
 * que a divergencia nao passa em silencio.
 *
 * E so vale ANTES de o Python falar. Depois da primeira resposta dele, tudo
 * passa direto, sem este arquivo olhar.
 */
const REVISOES_SERVIDAS = ["2026-07-28"];
const CAPACIDADES = {
  prompts: { listChanged: true },
  resources: { listChanged: true, subscribe: true },
  tools: { listChanged: true },
};

function ehSondaDeEra(linha) {
  try {
    const pedido = JSON.parse(linha);
    return pedido && pedido.method === "server/discover" && pedido.id !== undefined;
  } catch {
    return false; // linha partida ou ainda incompleta: segue o fluxo normal
  }
}

function respostaDaSonda(linha) {
  const pedido = JSON.parse(linha);
  return JSON.stringify({
    jsonrpc: "2.0",
    id: pedido.id,
    result: {
      cacheScope: "private",
      capabilities: CAPACIDADES,
      resultType: "complete",
      supportedVersions: REVISOES_SERVIDAS,
      ttlMs: 0,
    },
  }) + "\n";
}

let filhoJaFalou = false;
filho.stdout.on("data", () => { filhoJaFalou = true; });
filho.stdout.pipe(process.stdout);

// Leitura por LINHA, e nao `pipe`, porque e preciso olhar cada mensagem
// antes de repassar. O pedaco que chega pode conter meia linha, entao o
// resto fica guardado ate a proxima vez.
let resto = "";
process.stdin.on("data", (pedaco) => {
  resto += pedaco.toString("utf8");
  let quebra;
  while ((quebra = resto.indexOf("\n")) >= 0) {
    const linha = resto.slice(0, quebra + 1);
    resto = resto.slice(quebra + 1);
    if (!filhoJaFalou && ehSondaDeEra(linha)) {
      process.stdout.write(respostaDaSonda(linha));
      continue;
    }
    try { filho.stdin.write(linha); } catch { /* o filho ja morreu */ }
  }
});
process.stdin.on("end", () => {
  try { if (resto) filho.stdin.write(resto); } catch { /* idem */ }
  try { filho.stdin.end(); } catch { /* idem */ }
});

filho.on("error", (erro) => {
  desistir("Nao foi possivel iniciar o servidor.", [
    String(erro && erro.message ? erro.message : erro),
    "",
    "O Python existe, mas nao executou. Confira se as dependencias estao",
    "instaladas nesse ambiente:",
    "  <python> -m pip install -e \".[dev,navegador]\"",
  ]);
});
filho.on("exit", (codigo, sinal) => {
  // Dito em voz alta, no erro padrao, que e o que vai para o log do
  // aplicativo. Antes o servidor sumia sem deixar linha nenhuma, e descobrir
  // por que custou uma noite.
  process.stderr.write(
    `[conector justica] o servidor encerrou (codigo ${codigo}, sinal ${sinal}).\n`
  );
  process.exit(sinal ? 1 : (codigo === null ? 1 : codigo));
});

for (const aviso of ["SIGINT", "SIGTERM"]) {
  process.on(aviso, () => { try { filho.kill(aviso); } catch { /* ja morreu */ } });
}
