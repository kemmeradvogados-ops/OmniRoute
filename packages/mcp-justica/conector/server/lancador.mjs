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
 * execucao ao Python do ambiente virtual com `stdio: "inherit"`, e sai de
 * cena: a entrada e a saida padrao passam direto, sem intermediario.
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
for (const chave of ["DATAJUD_API_KEY", "JUSTICA_PASTA_COPIAS"]) {
  if (!(ambiente[chave] || "").trim()) delete ambiente[chave];
}
delete ambiente.JUSTICA_PYTHON;
delete ambiente.JUSTICA_PACOTE;

const filho = spawn(python, ["-m", "justica_mcp.server"], {
  cwd: pacote,
  env: ambiente,
  stdio: "inherit",
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
  process.exit(sinal ? 1 : (codigo === null ? 1 : codigo));
});

for (const aviso of ["SIGINT", "SIGTERM"]) {
  process.on(aviso, () => { try { filho.kill(aviso); } catch { /* ja morreu */ } });
}
