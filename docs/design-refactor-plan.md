# EvalOps Studio - Plano de Refatoracao de Design

Plano para o Codex aplicar depois, usando como referencia o arquivo raiz
`EvalOps Studio Design System.zip`.

O objetivo e refatorar as telas do frontend sem perder nada do pacote gerado
pelo Claude: HTMLs, tokens, previews, UI kit de dashboard, marketing pages,
copywriting, regras de produto e padroes de ligacao com backend.

## Principios

- Manter a arquitetura atual: Next.js App Router, Server Components por padrao,
  Server Actions para mutacoes e CSS puro em `apps/web/app/globals.css`.
- Nao introduzir Tailwind, shadcn, MUI, Radix ou CSS-in-JS.
- Usar `lucide-react`, que ja esta no projeto.
- Usar o zip como fonte visual, mas religar tudo aos dados reais via
  `apps/web/lib/api.ts` e `apps/web/lib/actions.ts`.
- Priorizar "copiar e colar a casca visual" do zip e substituir mocks por dados
  reais depois.
- UI final em ingles. Remover PT-BR e qualquer texto com encoding quebrado.
- Nao apresentar dado fake como real. Onde faltar backend, mostrar empty state
  honesto ou controle visual desabilitado.

## Fontes Dentro Do Zip

| Fonte | Uso |
|---|---|
| `README.md` | Regras de produto, tom, linguagem, status, numeros, spacing e layout. Ler antes de implementar. |
| `SKILL.md` | Checklist operacional do design system. |
| `colors_and_type.css` | Tokens oficiais de cor, tipo, spacing, radius, sombra e animacao. Conferir contra `globals.css`. |
| `assets/logo-evalops.svg` | Wordmark. Copiar para `apps/web/public/brand/` se divergir. |
| `assets/mark-evalops.svg` | Mark. Copiar para `apps/web/public/brand/` se divergir. |
| `assets/reference-dashboard.png` | Referencia canonica do dashboard. Usar em QA visual. |
| `screenshots/dashboard.png` | Screenshot do UI kit renderizado. Comparar com o overview real. |
| `marketing/index.html` | Fonte da landing `/`. |
| `marketing/login.html` | Fonte de `/login`. |
| `marketing/register.html` | Fonte de `/register`. |
| `marketing/app-redirect.html` | Fonte visual do entrypoint `/app`. |
| `marketing/marketing.css` | Fonte CSS das paginas publicas/auth. Ja parcialmente incorporado ao `globals.css`. |
| `ui_kits/dashboard/app.jsx` | Composicao alvo do Project Overview. |
| `ui_kits/dashboard/Sidebar.jsx` | Sidebar visual alvo. |
| `ui_kits/dashboard/Topbar.jsx` | Topbar visual alvo. |
| `ui_kits/dashboard/KPICards.jsx` | KPIs e sparkline. |
| `ui_kits/dashboard/Charts.jsx` | Charts SVG do overview. |
| `ui_kits/dashboard/RecentTraces.jsx` | Padrao de tabela densa. |
| `ui_kits/dashboard/RightRail.jsx` | Rail direito: rubrics, flags, model usage, alerts, billing. |
| `ui_kits/dashboard/dashboard.css` | Fonte CSS do app autenticado. Ja parcialmente incorporado ao `globals.css`. |
| `preview/*.html` | Contratos atomicos: badges, botoes, inputs, score bars, trace row, tipografia, spacing, sombras. |

## Estado Atual Do Projeto

| Area | Estado |
|---|---|
| `globals.css` | Ja contem boa parte dos tokens e classes do design system. Ainda tem classes legadas de compatibilidade. |
| Landing | Ja usa estrutura parecida com o zip, mas ainda tem varias strings em PT-BR. |
| Login/register | Ja funcionais com Server Actions e shell visual proximo do zip. |
| `/app` | Ja tem loading/redirect. Conferir copy e comportamento. |
| Overview | E a tela mais proxima do UI kit. Deve virar referencia para as outras paginas. |
| Sidebar | Boa base. Falta evitar dados fake no footer ou ligar a dados reais. |
| Topbar | Visual bom, mas `Prod`, `Last 7 days`, busca e notificacoes ainda estao hardcoded/sem funcao. |
| Traces list | Ainda legado: `.container`, `.panel`, tabela nua, PT-BR e encoding quebrado. |
| Trace detail | Ainda legado: `.container`, `.panel`, tabela nua, PT-BR e encoding quebrado. |
| Exports | Ainda legado e em PT-BR. |
| Evaluations/rubrics/keys/prompts/datasets/experiments | Ja usam `.main`, `.card`, `.t-table` em boa parte. Precisam polimento, idioma unico e componentes compartilhados. |
| Docs/changelog | Publicas, mas ainda usam layout legado simples. |
| AuthRequiredPanel | PT-BR, inline styles e compat legacy. |

## Ordem De Aplicacao

1. Criar utilitarios de formatacao e componentes compartilhados.
2. Refatorar `AuthRequiredPanel` e padronizar empty states.
3. Migrar as telas mais legadas: `/traces`, `/traces/[trace]`, `/exports`.
4. Polir telas semi-modernas: `/evaluations`, `/rubrics`, `/keys`,
   `/prompts`, `/datasets`, `/experiments`.
5. Revisar landing, auth, `/docs` e `/changelog`.
6. Ligar topbar/sidebar a dados reais onde ja houver backend.
7. Rodar build e QA visual contra `screenshots/dashboard.png`.

## Componentes Reutilizaveis

Criar em `apps/web/components/ui/` ou diretamente em `apps/web/components/`,
mantendo simples e sem dependencia externa.

| Componente | Origem | Uso |
|---|---|---|
| `PageHeader` | `ui_kits/dashboard/app.jsx` | Header com titulo, subtitulo e actions/meta a direita. |
| `SectionHead` | Cards atuais + zip | Titulo e descricao de card, com action/badge opcional. |
| `StatusBadge` | `preview/components-badges.html`, `RecentTraces.jsx` | Mapear status de trace/eval/export para badges. |
| `ScoreCell` | `RecentTraces.jsx`, `components-score-bar.html` | Score numerico com barra verde/amber/red. |
| `DataTable` | `RecentTraces.jsx` | Tabela densa com `t-table`, hover e action arrow opcional. |
| `StatCard` | `KPICards.jsx` | KPI compacto com label, valor, unidade, icone, delta e sparkline opcional. |
| `Sparkline` | `KPICards.jsx` | SVG simples sem lib externa. Usar gradient id unico. |
| `Flash` | Paginas atuais | Mensagem `success`/`error` com `.flash`. |
| `EmptyState` | `QuickstartCard` + README do zip | Empty states educativos com steps e snippet. |
| `JsonBlock` | Trace detail, prompts, datasets | Bloco mono scrollavel para JSON/YAML/codigo. |
| `FiltersBar` | Traces/exports | Form GET horizontal em card. |
| `UsageBar` | `RightRail.jsx` | Barra para usage/billing. |
| `CopyButton` | Keys/snippets | Client component pequeno para copiar secrets/snippets. Opcional. |

## Utilitarios De Formatacao

Criar `apps/web/lib/format.ts`.

Funcoes recomendadas:

```ts
export function formatCount(value: number): string;
export function formatCurrency(value: number, digits?: number): string;
export function formatCost(value: number): string;
export function formatLatency(ms: number): string;
export function formatDateTime(value: string): string;
export function formatRelativeTime(value: string): string;
export function formatPercent(value: number, digits?: number): string;
```

Regras:

- `formatCurrency(1842.63)` -> `$1,842.63`.
- `formatLatency(742)` -> `742 ms`.
- `formatLatency(2480)` -> `2.48 s`.
- `formatPercent(0.186)` -> `18.6%` ou `+18.6%` quando delta.
- Usar `en-US` e UTC quando exibir data absoluta.

## CSS A Consolidar

Manter `globals.css` por enquanto. Dividir em arquivos menores so depois da
migracao visual, para reduzir risco.

Adicionar/conferir classes:

| Classe | Uso |
|---|---|
| `.filters-card` | Card horizontal de filtros. |
| `.stat-grid` | Grid generico de stats em paginas internas. |
| `.detail-grid` | Layout de detalhe com main + rail. |
| `.code-block` | JSON/YAML/snippet com scroll. |
| `.table-meta` | Texto secundario em celulas de tabela. |
| `.actions-row` | Linha de actions em headers/cards. |
| `.subtle-link` | Link pequeno azul usado em cards. |
| `.copy-btn` | Botao pequeno de copiar. |
| `.danger-zone` | Secoes perigosas como revoke/delete. |
| `.public-page` | Wrapper de docs/changelog publicos. |

Depois da refatoracao, nenhuma pagina autenticada nova deve depender de
`.container`, `.panel`, `.row`, `.grid-2` ou `.grid-4`. Essas classes podem
ficar temporariamente como compatibilidade, mas nao devem ser usadas em telas
refatoradas.

## Plano Por Pagina

### `/` - Landing

Arquivo: `apps/web/app/page.tsx`

Fonte: `marketing/index.html`

Manter:

- `LightPillar`.
- `MarketingNav`.
- `MarketingFooter`.
- Links reais para `/register`, `/login` e `/docs`.

Aplicar:

- Trocar todo texto restante em PT-BR pelo copy do zip.
- Hero: `Observability and evaluation for AI applications.`
- Lede: `AI observability, tracing and evaluation for production AI systems.`
- CTAs: `Start tracing free`, `Read the docs`.
- Secao plataforma: `Everything you need to ship LLM apps that don't degrade silently.`
- Secao SDK: `Instrument an agent in three lines.`
- Secao workflow: `From production traffic to a regression-tested deploy.`
- CTA final: `Stop debugging your agent through screenshots.`
- No mock do dashboard, trocar `Visao geral`, `Avaliacoes`, `Chaves API`,
  `Ultimos 7d`, `Score medio`, `Latencia P95` etc. para ingles.

Backend:

- Nenhuma ligacao obrigatoria.

Aceite:

- Landing 100% em ingles.
- Sem encoding quebrado.
- Visual ainda usa `mk-shell`, `hero`, `feature-grid`, `steps`, `cta-card`.

### `/login`

Arquivo: `apps/web/app/login/page.tsx`

Fonte: `marketing/login.html`

Manter:

- `<form action={loginAction}>`.
- Campos reais usados pela action.
- `sp.error` com `.auth-error`.

Aplicar:

- Conferir paridade visual com auth shell do zip.
- Se os botoes GitHub/Magic link forem mantidos, deixar disabled ou claramente
  futuro para nao prometer fluxo inexistente.
- Usar `mk-btn mk-btn--primary mk-btn--block mk-btn--lg` no submit.
- Garantir `AuthSidePanel` com quote/mock visual.

Backend:

- Ja ligado via `loginAction`.

Aceite:

- Login continua autenticando.
- Visual bate com o mock.

### `/register`

Arquivo: `apps/web/app/register/page.tsx`

Fonte: `marketing/register.html`

Manter:

- `<form action={registerAction}>`.
- Campos reais atuais: nome, email, senha e workspace/org.

Aplicar:

- Copy do zip: `Create your workspace` e
  `Trace your first agent in under five minutes. Free during beta - no card required.`
- Auth side panel do register mock.
- OAuth visual disabled/futuro se existir.

Backend:

- Ja ligado via `registerAction`.

Aceite:

- Registro continua criando sessao/workspace.
- Sem PT-BR.

### `/app`

Arquivo: `apps/web/app/app/page.tsx`

Fonte: `marketing/app-redirect.html`

Aplicar:

- Texto em ingles: `Opening your workspace...`.
- Manter redirect server-side para login ou workspace.

Backend:

- Futuro: usar ultimo workspace/projeto da sessao se backend expuser.

Aceite:

- Usuario autenticado nao fica preso no loading.
- Usuario anonimo vai para `/login`.

### `/docs`

Arquivo: `apps/web/app/docs/page.tsx`

Fonte: marketing shell + cards do design system.

Aplicar:

- Trocar `container/panel` por `mk-shell`, `MarketingNav` e `MarketingFooter`.
- Hero compacto:
  - `Documentation`
  - `Implementation guides, API reference and product specs for EvalOps Studio.`
- Grid de cards:
  - `API reference` -> `${API_ROOT}/docs`
  - `OpenAPI JSON` -> `${API_ROOT}/openapi.json`
  - `Python SDK quickstart`
  - `Product specs`
- Incluir snippet rapido do SDK com `.snippet`.

Backend:

- Continuar usando `EVALOPS_API_BASE_URL` para montar links do FastAPI.

Aceite:

- Nao usa `.container`/`.panel`.
- Parece parte do marketing site.

### `/changelog`

Arquivo: `apps/web/app/changelog/page.tsx`

Fonte: marketing shell + card patterns.

Aplicar:

- Trocar para `mk-shell`, `MarketingNav`, `MarketingFooter`.
- Hero:
  - `Changelog`
  - `Release notes for EvalOps Studio.`
- Renderizar cada release como card com badge `badge--primary` e data em mono.
- Remover inline styles.

Backend:

- Nenhuma ligacao obrigatoria.

Aceite:

- Layout publico consistente.
- Sem inline styles.

### Workspace layout

Arquivo: `apps/web/app/o/[org]/p/[project]/layout.tsx`

Fonte: `ui_kits/dashboard/Topbar.jsx`

Aplicar:

- Extrair `Topbar` para componente se o arquivo crescer.
- Remover inline style do star button; usar classe `.star-btn`.
- Busca deve virar form GET para `/o/${org}/p/${project}/traces?name=...`.
- Environment deve ler/escrever `?environment=prod|staging|dev` quando aplicavel.
- `Last 7 days` deve ficar visual/disabled ate backend aceitar range real.
- Notificacoes ficam visuais ou escondidas enquanto nao houver endpoint.

Backend:

- `environment` ja existe em `getOverview` e `getTraces`.
- Range e notificacoes ainda precisam de backend.

Aceite:

- Topbar visual igual ao UI kit.
- Busca faz algo util ou nao promete funcao falsa.

### Sidebar

Arquivo: `apps/web/components/Sidebar.tsx`

Fonte: `ui_kits/dashboard/Sidebar.jsx`

Aplicar:

- Manter rotas reais.
- Ordem recomendada:
  `Overview`, `Traces`, `Evaluations`, `Rubrics`, `Prompts`, `Datasets`,
  `Experiments`, `Exports`, `API Keys`.
- Usar asset `/brand/mark-evalops.svg` se estiver confiavel.
- Footer nao deve afirmar `Healthy`/`Last seen: 1m ago` se isso for fake.
  Usar copy neutra como `Ready to ingest` ate ter dado real.

Backend:

- Para contagem de API keys e SDK health, criar server wrapper no futuro.
- Nao fazer fetch autenticado dentro do client component.

Aceite:

- Active state continua correto.
- Sem dados operacionais falsos.

### Project Overview

Arquivo: `apps/web/app/o/[org]/p/[project]/page.tsx`

Fonte: `ui_kits/dashboard/app.jsx`, `KPICards.jsx`, `Charts.jsx`,
`RecentTraces.jsx`, `RightRail.jsx`

Aplicar:

- Usar como tela referencia do design system.
- Extrair componentes somente se reduzir duplicacao.
- KPIs com dados reais:
  - Total traces -> `overview.kpis.traces`.
  - Avg eval score -> `overview.kpis.avg_score`.
  - P95 latency -> `overview.kpis.latency_p95_ms`.
  - Estimated cost -> `overview.kpis.cost_usd`.
- Recent traces com `getTraces({ projectId, limit: 5, environment })`.
- Model usage com `overview.model_breakdown`.
- Critical flags com `overview.recent_flagged`.
- Active rubrics e billing podem usar dados reais se nao deixarem a pagina lenta.

Backend:

- Usar `Promise.all` para evitar fetch sequencial.
- Se evaluation quality nao tiver dado real, mostrar empty chart honesto.

Aceite:

- Nenhum mock sem aviso.
- Visual proximo de `screenshots/dashboard.png`.

### `/traces`

Arquivo: `apps/web/app/o/[org]/p/[project]/traces/page.tsx`

Fonte: `RecentTraces.jsx`, `preview/components-trace-row.html`,
`preview/components-inputs.html`

Prioridade: alta.

Aplicar:

- Trocar `<main className="container">` por `<main className="main">`.
- Header:
  - `Traces`
  - `Inspect captured requests, spans, latency, token usage and cost.`
- Filtros em `<form method="get" className="card filters-card">`.
- Campo `name`: placeholder `Search by trace name`.
- Select `status`: `All statuses`, `ok`, `partial`, `error`.
- Select `environment`: `All environments`, `dev`, `staging`, `prod`.
- Submit: `Apply filters`.
- Empty state em ingles:
  - `No traces yet`
  - `Connect the Python SDK to start seeing traces, spans and cost in this project.`
- Tabela `.t-table` dentro de `.card.table-card`.
- Colunas:
  - `Trace`
  - `Status`
  - `Environment`
  - `Duration`
  - `Tokens`
  - `Cost`
  - `Created`
  - action arrow.
- `Trace`: nome como link e id em mono abaixo.
- `Status`: `StatusBadge`.
- `Environment`: `badge badge--env`.
- `Duration`: `formatLatency(trace.duration_ms)`.
- `Tokens`: `in / out` ou total com label.
- `Cost`: `formatCost(trace.total_cost_usd)`.

Backend:

- Ja usa `getTraces({ projectId, status, environment, name, limit: 50 })`.
- Paginacao fica para depois; backend ja retorna `next_cursor`, mas lib ainda nao usa cursor.

Aceite:

- Zero PT-BR.
- Zero encoding quebrado.
- Zero `.container`, `.panel`, tabela nua.

### `/traces/[trace]`

Arquivo: `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`

Fonte: cards, tables, code blocks e rail do design system.

Prioridade: alta.

Aplicar:

- Trocar para `<main className="main">`.
- Header:
  - Titulo `traceRow.name`.
  - Subtitle mono `Trace ID: ...`.
  - Actions: status badge + `Back to traces`.
- Stat cards:
  - `Duration`
  - `Tokens in/out`
  - `Cost`
  - `Events`
- Layout principal:
  - Coluna principal para spans e raw data.
  - Rail/card lateral para feedback e metadata, ou cards sequenciais se preferir.
- `Spans` em `.t-table`:
  - `Span`, `Type`, `Status`, `Provider/model`, `Duration`, `Events`.
- Feedback:
  - Titulo `Human feedback`.
  - Preservar `createTraceFeedbackAction`.
  - `Comment` placeholder `What happened in this trace?`.
  - Submit `Send feedback`.
- Feedback existente em `.t-table`:
  - `Thumbs`, `Comment`, `Source`, `Created`.
- JSON/raw:
  - `Trace metadata`.
  - `First span raw`.
  - Usar `JsonBlock`/`.code-block`.

Backend:

- Ja usa `getTrace(traceId)` e `createTraceFeedbackAction`.

Aceite:

- Feedback continua salvando com redirect `?feedback=1`.
- JSON nao estoura layout.
- Sem PT-BR.

### `/evaluations`

Arquivo: `apps/web/app/o/[org]/p/[project]/evaluations/page.tsx`

Fonte: tables, cards e score bars do design system.

Aplicar:

- Manter estrutura: `Run evaluation`, `Recent runs`, `Score breakdown`.
- Header:
  - `Evaluations`
  - `Run rubric-based checks against captured traces and inspect score breakdowns.`
- Empty prereq em ingles:
  - `Evaluation prerequisites`
  - `Evaluations need captured traces and a versioned YAML rubric.`
- Recent runs:
  - `StatusBadge`.
  - `ScoreCell` quando houver `aggregate_score`.
  - `formatCost`.
- Score breakdown:
  - Chips `.chip--ok` e `.chip--bad`.
  - Scores formatados.

Backend:

- Hoje faz N+1 com `getTraceEvaluations` por trace.
- Futuro ideal: `GET /projects/{project_id}/evaluations?limit=50`.

Aceite:

- Sem PT-BR.
- `triggerEvaluationAction` continua funcionando.

### `/rubrics`

Arquivo: `apps/web/app/o/[org]/p/[project]/rubrics/page.tsx`

Fonte: `RightRail.jsx` + cards/details.

Aplicar:

- Manter form `createRubricAction`.
- Cards por rubric com:
  - slug.
  - description.
  - badges `vN`, `threshold 0.70`, `Active`.
  - evaluator count.
  - chips para evaluators.
- Details:
  - `Version history`.
  - `Create new version`.
- YAML sempre em `.code-block`.
- Empty state:
  - `No rubrics yet`
  - `Create a YAML rubric to turn traces into evaluation scores.`

Backend:

- Ja usa `getRubrics`, `getRubricVersions`, `createRubricAction`,
  `createRubricVersionAction`.

Aceite:

- YAML legivel.
- Form de versao preservado.

### `/keys`

Arquivo: `apps/web/app/o/[org]/p/[project]/keys/page.tsx`

Fonte: badges, buttons e inputs do preview.

Aplicar:

- Secret card quando `qp.key` existir:
  - `New API key`
  - `Copy it now. It will not be shown again.`
  - Secret mono em `.secret-value`.
- Create key:
  - `Name`, `Environment`, `Scopes`.
  - Checkboxes `.checkbox-row`.
- Existing keys tabela:
  - `Name`, `Prefix`, `Environment`, `Scopes`, `Status`, `Rate limit`,
    `Created`, actions.
- Revoke com `.danger-btn`.
- Empty:
  - `No API keys yet`
  - `Create an ingest key before connecting the Python SDK.`

Backend:

- Ja usa `getApiKeys`, `createApiKeyAction`, `revokeApiKeyAction`.

Aceite:

- Secret aparece uma vez apos criacao.
- Revoke funciona.

### `/prompts`

Arquivo: `apps/web/app/o/[org]/p/[project]/prompts/page.tsx`

Fonte: rubrics/version cards + code blocks.

Aplicar:

- Create prompt com `Slug`, `Description`, `Template`, `Variables JSON`,
  `Metadata JSON`.
- Cards por prompt:
  - slug.
  - description.
  - badge `vN`.
  - variables count.
  - created date.
- Details:
  - `Version history`.
  - `Create new version`.
- Empty:
  - `No prompts yet`
  - `Create a versioned prompt before running controlled experiments.`

Backend:

- Ja usa `getPrompts`, `getPromptVersions`, `createPromptAction`,
  `createPromptVersionAction`.

Aceite:

- Templates preservam whitespace.
- JSON invalido mostra flash de erro vindo da action.

### `/datasets`

Arquivo: `apps/web/app/o/[org]/p/[project]/datasets/page.tsx`

Fonte: cards/details/code blocks.

Aplicar:

- Create dataset:
  - `Slug`, `Description`, `Source`.
- Dataset cards:
  - slug.
  - description.
  - badges `manual/traces`, `N items`.
- Details:
  - `Add item manually`.
  - `Build from traces`.
  - `Preview items`.
- Empty:
  - `No datasets yet`
  - `Datasets power regression checks, experiments and fine-tuning exports.`

Backend:

- Ja usa `getDatasets`, `getDatasetItems`, `createDatasetAction`,
  `addDatasetItemAction`, `buildDatasetFromTracesAction`.
- Futuro: endpoint com `item_count` para evitar buscar todos os items.

Aceite:

- Build from traces continua funcionando.
- JSON previews nao quebram layout.

### `/experiments`

Arquivo: `apps/web/app/o/[org]/p/[project]/experiments/page.tsx`

Fonte: cards, chips, score bars.

Aplicar:

- Latest run summary:
  - status badge.
  - pass rate.
  - avg score.
  - avg latency.
  - total cost.
  - total items.
- Create experiment:
  - Se faltarem datasets/rubrics, mostrar prereq empty state em vez de selects vazios.
  - Manter JSON para variants e pass criteria no primeiro passe.
- Experiment cards:
  - Resolver dataset/rubric slug via maps locais.
  - Variant chips com model em mono.
  - Action `Run experiment`.
- Empty:
  - `No experiments yet`
  - `Create variants to compare prompts, models or parameters against the same dataset.`

Backend:

- Ja usa `getExperiments`, `createExperimentAction`, `runExperimentAction`,
  `getExperimentRun`.
- Futuro: listar runs por experiment.

Aceite:

- Nao tentar criar experimento sem dataset/rubric.
- Run summary legivel e real.

### `/exports`

Arquivo: `apps/web/app/o/[org]/p/[project]/exports/page.tsx`

Fonte: `RightRail.jsx` Billing/Usage + tables.

Prioridade: alta.

Aplicar:

- Trocar para `<main className="main">`.
- Header:
  - `Exports`
  - `Create JSONL exports for datasets, fine-tuning and offline analysis.`
- Flash:
  - `Export created.`
- Layout `.content-grid`:
  - Card `Create JSONL export`.
  - Card `Plan and usage`.
  - Card inferior `Latest export`.
- Create export:
  - Environment: `All environments`, dev/staging/prod.
  - Status: `All statuses`, ok/partial/error.
  - Submit `Generate export`.
- Plan and usage:
  - Plan name/code.
  - Usage rows/bars para traces, evals, exports.
  - Cost com `formatCost`.
- Latest export table:
  - `ID`, `Status`, `Rows`, `File`, `Created`, `Completed`.
  - Status badge por estado.
- Empty:
  - `Create an export to see job details here.`

Backend:

- Ja usa `createExportAction`, `getExport`, `getOrganizationUsage`,
  `getOrganizationSubscription`.
- Futuro: `GET /projects/{project_id}/exports?limit=20`.

Aceite:

- Export continua gerando job e redirecionando com `export_id`.
- Sem `.container`/`.panel`.

## AuthRequiredPanel

Arquivo: `apps/web/components/AuthRequiredPanel.tsx`

Aplicar:

- Texto:
  - `Authentication required`
  - `Sign in to access this project dashboard.`
  - `Sign in`
  - `Create account`
- Usar `.card`, `.section-head`, `.actions-row`.
- Remover inline styles.
- Manter compat temporaria com `layout="container"` ate traces/exports migrarem.

Aceite:

- Sem PT-BR.
- Funciona em qualquer pagina.

## QuickstartCard / EmptyState

Arquivo: `apps/web/components/QuickstartCard.tsx`

Aplicar:

- Manter o componente no primeiro passe.
- Todos os chamadores devem enviar copy em ingles.
- Opcional: renomear para `EmptyState` depois.
- Opcional: adicionar action/link.

Aceite:

- Empty states sao educativos e tecnicos, nunca "no data" generico.

## Regras De Conversao Do Zip Para TSX

- `class` vira `className`.
- `for` vira `htmlFor`.
- `style="..."` vira classe CSS quando reutilizavel.
- `data-lucide="activity"` vira import de `lucide-react`.
- Link interno usa `next/link`.
- Forms com mutacao usam Server Actions.
- Filtros usam `method="get"`.
- Remover `onclick` e `onsubmit` dos HTMLs estaticos.
- IDs, slugs, modelos e chaves usam mono.
- Evitar caracteres especiais desnecessarios se houver risco de encoding.

## Backend Wiring Checklist

| Tela | Ligacoes atuais | Lacunas |
|---|---|---|
| Overview | `resolveProject`, `getOverview`, `getTraces` | Evaluation quality real, billing/rubrics se desejado. |
| Traces | `getTraces` | Cursor/paginacao e range. |
| Trace detail | `getTrace`, `createTraceFeedbackAction` | Visual melhor de eventos/spans. |
| Evaluations | `getTraceEvaluations`, `triggerEvaluationAction`, `getRubrics`, `getTraces` | Endpoint de runs por projeto. |
| Rubrics | `getRubrics`, `getRubricVersions`, create/version actions | Endpoint agregado com versions preview. |
| Keys | `getApiKeys`, create/revoke actions | Count real na sidebar. |
| Prompts | `getPrompts`, `getPromptVersions`, create/version actions | Selector de prompt versions em experiments. |
| Datasets | `getDatasets`, `getDatasetItems`, create/build actions | Item count sem buscar tudo. |
| Experiments | `getExperiments`, `createExperimentAction`, `runExperimentAction`, `getExperimentRun` | Historico de runs. |
| Exports | `createExportAction`, `getExport`, `getOrganizationUsage`, `getOrganizationSubscription` | Listagem de exports. |
| Topbar | query para traces/overview | Range e notificacoes. |
| Sidebar | rotas/client active state | Server wrapper para dados reais. |

## Verificacao

Rodar:

```powershell
cd apps/web
npm run build
```

Fluxos manuais:

- `/` em ingles.
- `/login` e `/register` autenticam.
- `/app` redireciona.
- Overview abre com dados seed.
- `/traces` filtra por nome/status/environment.
- Trace detail envia feedback.
- Criar rubric, prompt, dataset, experiment e export.
- Criar e revogar API key.
- Empty states com banco limpo.

## Criterios Gerais De Aceite

- Nenhuma rota autenticada refatorada usa `.container`, `.panel` ou tabela nua.
- Nenhuma string PT-BR permanece na UI final.
- Nenhum encoding quebrado permanece.
- Nenhum dado fake e apresentado como real.
- Todas as mutacoes continuam via Server Actions.
- `npm run build` passa.
- Overview continua visualmente proximo de `tmp/evalops-design-system/screenshots/dashboard.png`.
- Assets do zip estao preservados ou copiados para `apps/web/public/brand`.

## Riscos

- A arvore tinha muitas alteracoes antes deste plano. O checkpoint foi criado
  em `edeb8da` antes desta documentacao.
- `globals.css` esta grande e misto. Refatorar telas primeiro; dividir CSS depois.
- Algumas telas fazem fetch N+1. Aceitar no MVP, mas planejar endpoints agregados.
- O zip contem mocks como `Rogue Labs`, `DocOps Agent`, `Healthy` e
  `Last seen: 1m ago`. Substituir por dados reais ou copy neutra.
- Dashboard e desktop-first; nao quebrar mobile basico mesmo que a prioridade
  seja console desktop.
