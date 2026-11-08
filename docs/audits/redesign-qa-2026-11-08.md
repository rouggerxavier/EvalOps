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

## Correção F31 — veredito e paginação de traces

Base integrada: `main` em `be5500b83f17b0bd2456f600cdf618cc1a6fa471`
(inclui #28 e #32), preservando o histórico de avaliações aprovado em `d960168`.
Modo standard, CI targeted; revisão integrada do diff. Nenhum arquivo de schema,
migration, ingestão, worker, uso ou SDK foi modificado nesta correção.

### Defeito e comportamento final

A tela buscava somente 100 avaliações globais e filtrava os 50 traces já
paginados. Uma aprovação antiga desaparecia atrás de 105 runs de outro trace,
e correspondências em páginas seguintes produziam páginas vazias.

A API usa a execução mais recente de cada trace para `last_score` e o novo
`last_verdict`, com desempate por `created_at DESC, id DESC`. O filtro `verdict`
aceita `approved`, `rejected`, `partial` e `unknown` e precede cursor e limite.
`passed=true/false` prevalece; `partial` exige `passed=null` e o booleano JSON
`partial_failure=true`. Runs sem veredito e traces sem run continuam como
`unknown`/“Sem dados”. Strings e números semelhantes a booleanos não contam
como falha parcial. `failed` e `score_lt` preservam a semântica legada de
qualquer execução histórica.

A tela consome diretamente esse resultado, sem consulta global de avaliações ou
filtro posterior. Os controles de paginação usam links GET nativos, preservando
os mesmos parâmetros; isso evita a transição cliente intermitente observada no
QA depois de enviar o formulário, sem alterar o shell. O limite de navegação
RSC já relatado na base permanece fora desta correção; não foi corrigida a
navegação global.

### Testes e revisão

- RED: os quatro testes novos de API falharam antes da correção, incluindo
  ausência de veredito e filtro ignorado antes da paginação.
- GREEN: 97 testes de API afetados passaram. Incluem os quatro casos novos em
  SQLite e os mesmos quatro em PostgreSQL 16, com JSON, todos os vereditos,
  105 runs concorrentes no histórico, 55 correspondências depois de 55 traces
  mais novos, desempate temporal, filtros combinados, exclusão lógica,
  ambiente, projeto, chave somente de leitura e recusa de outro tenant.
- A instrumentação adicional confirma uma única consulta de avaliações tanto
  para limite 1 quanto 50, nos dois bancos; os oito casos foram repetidos após
  essa asserção. A aplicação recebe somente as linhas da página.
- Web: 190 testes passaram, incluindo quatro novos testes que executam TS/TSX
  real, verificam renderização de veredito e nota, envio do filtro à API,
  parâmetros do cursor e descarte de veredito inválido. Typecheck e build
  passaram.
- Detector Impeccable dos três arquivos frontend: zero achados.
- Revisão integrada: sem achado bloqueante no diff da correção. Isolamento,
  autenticação, estado de ingestão, ambiente, filtros e semântica histórica
  foram preservados. A revisão independente e CI do SHA publicado seguem como
  gates anteriores a qualquer merge.

Comandos: `PYTHONPATH="$PWD/apps/api" DATABASE_URL=sqlite:////tmp/evalops-f31-bootstrap.sqlite
REDIS_URL=redis://127.0.0.1:18379/14 R31_POSTGRES_URL=<banco exclusivo evalops_r31>
apps/api/.venv/bin/python -m pytest` sobre `test_trace_verdict_filter.py`,
`test_audit_product_regressions.py`, `test_refactor_endpoints_edge_cases.py`,
`test_refactor_project_admin_endpoints.py`, `test_audit_read_key_and_prompt_refs.py`
e `test_phase10_audit_privacy_exports.py`; em `apps/web`, `npm run test`,
`npx tsc --noEmit` e `npm run build`.

PostgreSQL: somente o container `evalops-sampling-20261108` (ID iniciado por
`4275b06a`), PostgreSQL 16.15, porta `127.0.0.1:55432`, banco descartável
`evalops_r31`. O banco de E10 não foi acessado. SQLite por teste é isolado pelo
conftest; nenhuma chamada a LLM foi executada.

### QA do filtro no build

API `127.0.0.1:18431`, web `localhost:18430`, SQLite descartável
`/tmp/evalops-f31-qa/qa.sqlite`, rate limit em memória e Redis explicitamente em
`127.0.0.1:18379/14`, indisponível e sem worker. A URL local da API usa
`localhost.` somente no ambiente de QA para passar pela configuração do build.

Dados: 113 traces e 162 avaliações; 55 aprovações são anteriores às 105
avaliações de outro trace. Chromium headless, 1280×900 e 375×900:

- Aplicar “Aprovado” mostra a aprovação antiga como “Aprovado”, nota 1.00;
  resultados divididos em 50 e 5, com veredito e ambiente preservados no cursor.
- “Parcial” e “Reprovado” retornam uma linha cada; “Sem dados” retorna 50 e 6,
  incluindo traces sem execução e execução sem veredito.
- Trocar o filtro pelo formulário limpa o cursor. Nenhum erro JavaScript ou
  rolagem horizontal da página foi observado; a tabela mantém rolagem própria.
- Artefatos locais: `/tmp/evalops-f31-qa/results.json`, `qa.cjs`,
  `approved-{1280,375}.png`, `page2-{1280,375}.png` e capturas de cada veredito.

Não executados nesta rodada: suíte API/SDK completa, carga de produção, worker,
export/replay assíncronos, juiz externo, Firefox, WebKit ou hardware físico.
A aba Avaliações não foi reinvestigada: a ocorrência já reproduzida na base não
é evidência de regressão deste redesign. A paginação com filtro foi verificada
separadamente nesta correção. Este relatório não autoriza merge.
