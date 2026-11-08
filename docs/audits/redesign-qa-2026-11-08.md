# Redesign do painel — QA de retomada (D31)

Base: `548da615f166169f87b1f74b3c6251ac67a0a70b`, branch `feat/redesign-painel`.
Worktree limpa antes da validação. Escopo visual e limites funcionais em
[`DESIGN.md`](../../DESIGN.md); contexto em [`PRODUCT.md`](../../PRODUCT.md).

## Resultado

- `npm ci`: passou, 0 vulnerabilidades reportadas.
- `npm run test`: 184/184 passaram, incluindo regressões da etapa 4 e promessas falsas.
- `npx tsc --noEmit`: passou.
- `npm run build`: passou.
- Smoke Playwright: 13/13 passaram. As 11 rotas principais são verificadas em
  1280×900 e 375×900; o atalho G T e o menu móvel têm testes de interação.
- QA adicional em Chromium headless: 12 telas, incluindo detalhe do trace e
  comparação com dados, em 1280×900 e 375×900. Todas responderam 200; nenhuma teve
  rolagem horizontal da página ou erro JavaScript observado.
- Menu em 375 px: Enter abre, foco inicial dentro da gaveta, Tab/Shift+Tab circulam,
  Escape fecha e devolve o foco; navegar ou alargar a janela fecha e libera o scroll.

O smoke anterior falhou antes da correção: procurava `.page-header__title` e
`Workspace ·`, removidos pelo redesign. Agora usa o H1 e os títulos atuais em
português. O cookie de teste usa a origem de `baseURL`, permitindo execução numa
porta/host isolados. A retomada não alterou código de produto nem contratos API.

## Ambiente e dados

API local em `127.0.0.1:18311`; web em `127.0.0.1:18310`, servindo o build.
SQLite descartável em `/tmp/d31-redesign-qa.sqlite`, exports em diretório temporário
e rate limit em memória. Redis configurado explicitamente em
`redis://127.0.0.1:18379/15`, sem serviço nessa porta: fila indisponível, sem worker.
Nenhum banco Redis compartilhado foi usado.

Conta, organização, projeto, três traces (`ok`, `error`, `partial`), mensagens,
avaliação heurística, rubrica, prompt, dataset e experimento sintético foram criados
somente nessa API descartável. Nenhuma chamada a juiz LLM foi necessária.

## Evidência visual

Capturas do build com os dados descartáveis deste QA, geradas por Playwright em
2026-11-08. Não são ilustrações nem dados adicionados ao produto.

- [Visão geral em 1280 px](img/redesign-qa-2026-11-08-overview-1280.png)
- [Visão geral em 375 px](img/redesign-qa-2026-11-08-overview-375.png)
- [Menu aberto em 375 px](img/redesign-qa-2026-11-08-menu-375.png)

O detector de fontes Impeccable retornou cinco avisos e uma observação: Geist,
dois textos com gradiente e fundo quadriculado pertencem às superfícies públicas
mantidas fora do redesign; a borda do toast é anterior; a borda crítica no motivo
da reprovação identifica evidência, sem bloqueio funcional observado. Nenhuma
mudança estética adicional foi feita para silenciar esses avisos.

## Lacunas

- Não executados: worker/lote assíncrono, replay, export assíncrono, juiz externo,
  suíte API/SDK completa, Postgres, WebKit, Firefox ou dispositivo físico.
- Viewport emulado comprova layout e teclado; não comprova gestos reais de toque
  nem uma auditoria WCAG completa.
- As limitações da auditoria de produto permanecem, incluindo datas relativas em
  inglês/deslocadas com SQLite e a promessa de promoção no stepper público.
- A configuração Impeccable não registra `buildPath`; isso não muda as telas de
  operação, construídas diretamente em código. Não foi alterada nesta retomada.
- Review independente e CI do PR são etapas posteriores; este relatório descreve
  os comandos locais efetivamente executados.

## Regressão encontrada na revisão do histórico

A tabela de avaliações descartava execuções sem scores e os metadados de cada
execução. Um erro antigo deixava de aparecer quando havia scores de outra
execução; avisos de avaliação parcial, flags críticas e dispersão das amostras
não eram mais exibidos.

O histórico agora agrupa os avaliadores por execução, preservando o desenho de
tabela, veredito, custo e data de cada execução. Dois testes de renderização real
falharam antes da correção e passaram depois. A asserção que exigia a ausência de
`raised_flags` foi corrigida para preservar essa informação.

Após integrar a main com #30: 186 testes web, typecheck e build passaram.
O detector Impeccable do componente retornou zero achados. A inspeção visual
adicional usa o componente renderizado com CSS do produto e dados sintéticos,
em 1280 e 375 px; não substitui o QA da aplicação completa descrito acima.

A reprodução adicional do clique na aba Avaliações em 375 px ainda está pendente.
As revisões independentes de #28 e #31 foram interrompidas pelo limite de uso dos
agentes. Nenhuma aprovação é inferida dessa interrupção; o merge aguarda revisão
concluída e CI verde no SHA final.
