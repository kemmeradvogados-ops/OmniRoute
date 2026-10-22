# O conector, para instalar arrastando

Este é o pacote `.mcpb` do `justica_mcp`: um arquivo que se arrasta para
**Configurações > Extensões** no aplicativo do Claude, sem editar arquivo de
configuração nenhum.

## Por que ele existe

Em 22/10/2026 uma instalação inteira foi feita pelo caminho antigo, escrevendo
`%APPDATA%\Claude\claude_desktop_config.json` na mão. Tudo foi conferido e tudo
passou: o arquivo gravado, o caminho existente, o servidor subindo e
respondendo ao protocolo. E não apareceu conector nenhum.

A causa só ficou clara ao listar a pasta: `%APPDATA%\Claude` continha **apenas**
o arquivo que acabáramos de criar, enquanto o aplicativo guardava os dados dele
em `%LOCALAPPDATA%\Claude-Data`, mexido no mesmo dia. Editamos um arquivo que
aquela versão do Claude não lê.

## Por que o lançador é em Node, se o servidor é em Python

A especificação manda um servidor `python` trazer **todas** as dependências
dentro do pacote. As deste servidor incluem código compilado por plataforma
(`pydantic-core`, `cryptography`, `greenlet`) e o Chromium do Playwright, que
sozinho passa de 150 MB. Um pacote assim teria de ser montado uma vez por
sistema operacional, e ainda duplicaria o ambiente que a máquina já tem.

Então o pacote não carrega o servidor: ele **aponta** para o ambiente virtual já
instalado. O Node é usado porque o aplicativo do Claude o traz consigo, então
`command: "node"` funciona sem nada instalado a mais, enquanto
`command: "python"` dependeria de o Python estar no caminho do sistema.

O lançador não fala o protocolo. Ele confere a configuração, entrega a execução
ao Python do ambiente virtual com `stdio: "inherit"` e sai de cena.

## O que o pacote NÃO resolve

Ele resolve o registro, não a preparação. A máquina ainda precisa de:

- Python 3.11 ou mais novo, com o ambiente virtual criado e o pacote instalado
  (`pip install -e ".[dev,navegador]"`);
- o Chromium do Playwright, para as ferramentas autenticadas
  (`playwright install chromium`);
- o `.env` com os endereços dos portais;
- as credenciais do próprio advogado no cofre.

Para uma equipe, isso significa que cada pessoa prepara a máquina uma vez, e
depois instala o conector arrastando o arquivo.

## Gerar o pacote

```bash
npx -y @anthropic-ai/mcpb@latest validate conector/manifest.json
npx -y @anthropic-ai/mcpb@latest pack conector conector/justica-mcp.mcpb
```

O `.mcpb` é gerado, não versionado: versionar o zip faria conviverem duas
verdades, a fonte e uma cópia que envelhece em silêncio.
