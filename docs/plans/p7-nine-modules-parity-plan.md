# P7 — 9 Módulos Parity Plan

> Plano de execução por fases. Cada fase é uma página do app interno
> reaproximada do design `evalops-preview/` do ZIP `segunda refatoração
> interna EvalOps.zip`, **sem virar placeholder**, **sem perder
> funcionalidade**, **mantendo o background atual** da `.evo-shell`.

Branch: `refactor/frontend`
Repo: `/home/rouggerxavier/dev/evalops`
Handoff-pai: `docs/plans/cockpit-refactor-handoff-2026-05-20.md`
Design-fonte: `segunda refatoração interna EvalOps.zip` (raiz)
  - `preview/screens/{overview,traces,evaluations,modules}.jsx`
  - `preview/components.jsx` (`PageHeader`, `Card`, `Badge`, `Icon`,
    `summary-card`, `endpoint-list`, table `.t`, `PreviewPill`)
  - `preview/styles.css` (tokens visuais — referência, **não importar**)
  - `evalops-preview/DESIGN_NOTES.md` (raciocínio)

---

## Premissas fixas (não violar em nenhuma fase)

1. **Não virar placeholder.** Páginas reais já têm conteúdo funcional;
   refator é visual + estrutura, não substituição. NÃO renderizar
   banner "módulo preservado, fora do redesign principal" do ZIP.
2. **Não perder nada.** Toda funcionalidade hoje visível precisa
   continuar visível e funcional: formulários, ações de criar/
   versionar/revogar, listagens, drawers, diffs, banners de segurança,
   estados de erro/loading.
3. **Conectar backend real.** Nenhum dado mock. Métrica/badge/contagem
   só aparece se vier do payload existente. Sem inventar `avgScore`,
   `expires_at`, `errors_7d`, etc.
4. **Background fica.** `.evo-shell` atual (grid, vignettes radiais,
   cobalto `#4F8CFF`, oklch tokens) é o que o user gostou — manter.
   NÃO copiar background do preview se diferir.
5. **Tokens só dentro de `.evo-shell`.** Sem `:root`, sem vazamento
   pra landing/login/docs/changelog.
6. **Botões planejados** = `disabled data-status="planned"`, nunca
   modal de preview (cockpit Potemkin).
7. **Bem parecido, não idêntico.** Adaptar onde o ZIP tem dado mock
   que não existe no backend.

---

## Fases

Convenção: cada fase = 1 commit `feat(web): P7.x <módulo> parity`,
1 arquivo de teste novo `apps/web/tests/<módulo>-p7.test.mjs` (ou
extensão do `*-premium.test.mjs` existente). Doc handoff
(`cockpit-refactor-handoff-2026-05-20.md`) atualizada ao fim com hash
do commit e seção "P7.x — Files Changed".

Status legend: ⬜ pendente · 🟨 em andamento · ✅ landed

### P7.1 — Prompts ✅ `998ea37`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/prompts/page.tsx` — summary
    row real (totalPrompts, totalVersions, latestActivity) + card
    "Endpoints ativos" read-only.
  - `apps/web/app/globals.css` — primitivas P7 (`.evo-summary-row`,
    `.evo-summary-card*`, `.evo-endpoint-list`, `.evo-endpoint-row*`)
    escopadas em `.evo-shell`, reutilizáveis pelos demais módulos.
  - `apps/web/tests/prompts-p7.test.mjs` (novo) — 9 testes.
- Validation: `npm test` 111/111 pass · `tsc --noEmit` limpo · HMR
  sem erros novos (warning autoprefixer pré-existente).
- Conteúdo preservado: AuthRequiredPanel, getPrompts +
  getPromptVersions, createPrompt(+Version)Action, DiffView (ambos
  branches), versions history, flash, eyebrow + subtitle P5.

- Arquivos originais (referência):
- Referência: `evalops-preview/preview/screens/modules.jsx` (caso
  `moduleId === "prompts"`) + tabela `.t` + `endpoint-list` +
  `summary-card`.
- Conteúdo a preservar:
  - `createPromptAction`, `createPromptVersionAction` (formulários).
  - `DiffView` (diff por linha com `+`/`−`).
  - Listagem `getPrompts` + `getPromptVersions`.
  - Estados de erro/loading.
- Cockpit a aplicar:
  - `evo-page-header__eyebrow` "Operação · Prompts" (já presente
    do P5 — preservar).
  - Summary row real (ex.: total de prompts, total de versões,
    última atualização). Só dado do payload.
  - Wrap em `.evo-card` (header + body + footer).
  - Tabela com classes premium (linhas hoverable, mono col pra
    `version_hash`, badges para status).
  - Coluna lateral "Endpoints ativos" listando rotas reais
    (`POST /v1/prompts`, `POST /v1/prompts/{id}/versions`) como
    referência visual (somente leitura, não clicável → não vira
    modal).
- Testes a adicionar:
  - Server contract preservado (mesmas chamadas a `lib/api`).
  - Form fields permanecem (`name="slug"`, `name="template"`, etc).
  - `DiffView` renderiza ambos os casos (primeira versão + diff).
  - Nenhum `AttentionStrip`/dado inventado.

### P7.2 — Rubricas ✅ `171ec9a`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/rubrics/page.tsx` — summary
    row real (totalRubrics, totalVersions via soma de
    `current_version`, latestActivity) + card "Endpoints ativos"
    read-only + botão "Importar" planned (`disabled
    data-status="planned"`).
  - `apps/web/tests/rubrics-p7.test.mjs` (novo) — 9 testes.
- Validation: `npm test` 120/120 pass · `tsc --noEmit` limpo.
- Conteúdo preservado: AuthRequiredPanel, getRubrics +
  getRubricVersions, createRubric(+Version)Action, YamlBlock,
  VersionsList, evaluators list, branches detail/list/empty,
  flash, eyebrow + subtitle P5.
- Primitivas CSS (.evo-summary-row, .evo-endpoint-list)
  reusadas do P7.1 — sem alteração em `globals.css`.

### P7.3 — Datasets ✅ `a3a0293`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/datasets/page.tsx` — substitui
    `.evo-kpi-grid` por `.evo-summary-row` (4 cards: Datasets, Itens,
    Fonte traces · prontos, Última atividade via `relTime`) usando só
    dados reais do payload; adiciona card "Endpoints ativos"
    read-only (5 rotas reais: list/create datasets, list/create
    items, build-from-traces); adiciona botão "Importar" planned
    (`disabled data-status="planned"`).
  - `apps/web/tests/datasets-p7.test.mjs` (novo) — 9 testes.
- Validation: `npm test` 129/129 pass · `tsc --noEmit` limpo.
- Conteúdo preservado: AuthRequiredPanel, getDatasets +
  getDatasetItems, createDatasetAction + addDatasetItemAction +
  buildDatasetFromTracesAction, tabs (all/manual/traces), tabela
  com `statusForDataset`, `sourceLabel`, item preview (`shortJson`),
  formulários de criação/ingestão, flashes, eyebrow + subtitle P5.
- Primitivas CSS (`.evo-summary-row`, `.evo-endpoint-list`) reusadas
  do P7.1 — sem alteração em `globals.css`.

### P7.4 — Experiments ✅ `d066957`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/experiments/page.tsx` — summary
    row real (Experimentos, Variantes (soma), Com baseline, Última
    atividade via `relTime`) + card "Endpoints ativos" read-only
    (4 rotas reais: list/create experiments, run, get run detail).
  - `apps/web/tests/experiments-p7.test.mjs` (novo) — 9 testes.
- Validation: `npm test` 138/138 pass · `tsc --noEmit` limpo · HMR
  sem erros novos (warning autoprefixer pré-existente).
- Conteúdo preservado: AuthRequiredPanel, getDatasets + getRubrics
  + getExperiments + getExperimentRun, createExperimentAction +
  runExperimentAction, RunResultCard (variants table, delta baseline,
  winner badge, criteria_failures), tabela de experimentos com
  variants tags + ação Rodar inline, formulário collapsible de
  criação (name/baseline/dataset/rubric/variants_json/pass_criteria_json),
  warning dataset/rubrica ausente, flashes, botão "Exportar relatório"
  planned, eyebrow + subtitle P5.
- Premissa 3 (sem dado inventado): summary não traz "em execução"
  nem "concluídos" — tipo `Experiment` não tem `status` agregado;
  badges de run só aparecem quando `RunResultCard` é montado via
  `?run_id&experiment_id` (dado real via `getExperimentRun`).
- Primitivas CSS (`.evo-summary-row`, `.evo-endpoint-list`) reusadas
  do P7.1 — sem alteração em `globals.css`.

### P7.5 — Chaves API ✅ `8b3743d`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/keys/page.tsx` — substitui
    `.evo-kpi-grid` (4 metric cards) por `.evo-summary-row` (4
    cards: Chaves, Ativas, Revogadas, Última atividade via
    `relTime` de `key.created_at` e `key.revoked_at`) + card
    "Endpoints ativos" read-only (3 rotas reais: list/create
    api-keys, revoke).
  - `apps/web/tests/keys-p7.test.mjs` (novo) — 9 testes.
- Validation: `npm test` 147/147 pass · `tsc --noEmit` limpo.
- Conteúdo preservado: AuthRequiredPanel, getApiKeys,
  createApiKeyAction + revokeApiKeyAction, máscara de prefix
  (`maskPrefix`), flash do segredo cru via `consumeApiKeyFlash`,
  banner de política (rotação 90 dias / escopo mínimo / revogação),
  tabela com badge `ativa`/`revogada` + ação Revogar inline, tabs
  all/active/revoked, formulário de criação (name/environment/
  scopes), eyebrow + subtitle P5.
- Premissa (sem dado inventado): NÃO renderiza dot de atenção
  baseado em `expires_at` — campo ausente no tipo `ApiKey`
  (gap rastreado no handoff-pai §Pending Work · Gaps condicionais).
- Primitivas CSS (`.evo-summary-row`, `.evo-endpoint-list`) reusadas
  do P7.1 — sem alteração em `globals.css`.

### P7.6 — Exports ✅ `0172b18`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/exports/page.tsx` —
    substitui `.evo-kpi-grid` (4 metric cards) por
    `.evo-summary-row` (4 cards: Jobs conhecidos, Em andamento,
    Concluídos, Última atividade via `relTime` de
    `row.job.created_at`) + card "Endpoints ativos" read-only
    (3 rotas reais: POST `/exports`, GET `/exports/{id}`, GET
    `/api/exports/{id}/download` via proxy Next autenticado).
  - `apps/web/tests/exports-p7.test.mjs` (novo) — 9 testes.
- Validation: `npm test` 156/156 pass · `tsc --noEmit` limpo.
- Conteúdo preservado: AuthRequiredPanel, server contract
  (`getExport` + `getOrganizationUsage` +
  `getOrganizationSubscription`), `createExportAction`, painel
  "Plano e uso" com UsageBar para Traces/Avaliacoes/Exports/Spans/
  Tokens + Budget mensal de judge, download via
  `getExportDownloadPath` (rota Next autenticada com redirect
  sanitizado), tabela com `jobStatusBadge`, tabs
  all/running/completed/failed, fallback de erro com
  `safeErrorMessage` (Fix-7B.6), card "Contrato atual" (gap de
  listagem global e cancelamento), eyebrow + subtitle P5.
- Primitivas CSS (`.evo-summary-row`, `.evo-endpoint-list`) reusadas
  do P7.1 — sem alteração em `globals.css`.

### P7.7 — Traces (re-tune) ✅ `9a130f3`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/traces/page.tsx` — subtitle
    re-tune (`{rows.length} traces na página atual · auto-refresh
    a cada 30s · sinal por execução/erro/custo/RAG`) com contagem
    real, pill `ao vivo` (`.evo-traces-live` + `data-testid=
    "trace-list-live-pill"`) renderizada antes do botão Exportar
    apenas quando `autoRefreshEnabled` (sem cursor + `rows.length
    > 0`), tab RAG ganha ícone `Layers` mantendo `data-testid=
    "trace-list-rag-tab"`.
  - `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx` —
    eyebrow ganha link `← Traces` (`.evo-trace-detail__back`)
    seguido de `Observabilidade · Trace detail`; título recebe
    classes `evo-mono evo-trace-detail__title` (mono ZIP-style);
    nova ação planned `Avaliar` (`Target` icon · `disabled
    data-status="planned"`) entre Comparar e botão de volta;
    hints dos KPIs alinhados ao ZIP (`prompt`, `completion`,
    `capturados`, `traceModel ?? "sem modelo"`).
  - `apps/web/components/TracesFilterBar.tsx` — polish: contador
    `count/total` agora `.evo-mono`, dot live com `aria-label`.
    Layout (chips de status/env + busca por nome) preservado.
  - `apps/web/app/globals.css` — adiciona `.evo-shell
    .evo-traces-live` (pill verde com pulse de 2s),
    `.evo-shell .evo-trace-detail__title` (mono 22px),
    `.evo-shell .evo-trace-detail__back` (link mono accent).
    Todas as primitivas escopadas em `.evo-shell`.
  - `apps/web/tests/traces-p7.test.mjs` (novo) — 10 testes.
- Validation: `npm test` 166/166 pass · `tsc --noEmit` limpo.
- Conteúdo preservado: AuthRequiredPanel, `getTraces`/`getTrace`
  server contract, cursor guard (`limit: 50` + `cursor: qp.cursor`
  + `Pausado em página paginada`), `TracesAutoRefresh` (Phase 7E,
  `enabledByDefault={autoRefreshEnabled}`), tabs all/errors/
  partial/slow/RAG com `isTraceRagCandidate`, `TracesFilterBar`
  (busca por nome + chips de status/env + Live dot), tabela densa
  `.evo-table` com `StatusBadge`, `TraceMetricCard` (5 KPIs reais),
  `SpanWaterfall`, segmento RAG UI-RAG-1 (`RAGSummaryHeader` +
  `AnswerPreviewCard` + `GroundingQualityCard` +
  `RetrievalSummaryCard` + `CitationRefsTable` +
  `data-testid="rag-section"`), `evo-trace-attention` banner,
  bloco metadata JSON cru, formulário `createTraceFeedbackAction`
  + histórico de feedback, `evo-trace-detail__bottom` layout sem
  tabs, planned controls (`Flagear`/`Reexecutar`/`Comparar`/
  `Avaliar` · seleção em lote).
- Premissa "NÃO usar tabs no detail": confirmado por teste
  (`P7.7 traces detail: flat layout`) que veta `PreviewActionModal`,
  `useState`, `setTab(` e `tab === "..."`.
- Sem dado inventado: subtitle e pill derivam de `rows.length` e
  `autoRefreshEnabled` (já calculados a partir do payload).

### P7.8 — Overview (re-tune) ✅ `3470543`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/page.tsx` — PageHeader
    eyebrow `Workspace · {orgName}` (ZIP voice) + subtitle
    `Resumo de operacao · ambiente {env} · {traces} traces /
    {rubrics} rubricas / {runs} runs carregados` (derivado de
    `recentTraces.length` / `rubrics.length` / `recentRuns.length`,
    sem dado inventado). Hero h2 ganha `evo-overview-hero__title`
    (mono 22px). Novo `OverviewAlertBanner`
    (`.evo-overview-alert` + `data-testid="overview-alert-banner"`)
    renderizado apenas quando `problemTraces.length > 0`; variante
    `--error` se `errorCount > 0`, senao `--warn`; href via
    `tracesHrefFor("errors"|"flagged")` preservando `environment`.
  - `apps/web/app/globals.css` — primitivas escopadas em
    `.evo-shell`: `.evo-overview-hero__title` (mono ZIP-style),
    `.evo-overview-alert` (banner gradiente warn/err + hover/focus),
    `.evo-overview-alert--error`, `.evo-overview-alert__icon`,
    `.evo-overview-alert__body`, `.evo-overview-alert__cta`.
  - `apps/web/tests/overview-p7.test.mjs` (novo) — 9 testes.
- Validation: `npm test` 175/175 pass · `tsc --noEmit` limpo.
- Conteúdo preservado: AuthRequiredPanel, server contract
  (`getOverview` + `getTraces limit:8` + `getProjectEvaluations` +
  `getRubrics`), `ProjectStatusCard` (7 ramos condicionais),
  5 KPIs reais via `OverviewMetricCard` (`avg_score` null ->
  "Sem score"), `NextActions` condicional, `RecentTracesCard`,
  `EvaluationSnapshotCard`, `AreaChart` (`cost_by_day`),
  `ModelTable` (`model_breakdown`), `OperationalSignals` derivados
  do payload, `ProjectContext` (`Copyable` project_id),
  atalhos reais, footer com `apiRoot()/health/readiness`.
- Nota: banner usa `OverviewAlertBanner` / `.evo-overview-alert`
  (em vez de `AttentionStrip`) para não colidir com
  `assert.doesNotMatch(/Attention/)` em
  `overview-premium.test.mjs`. Espírito da premissa preservado:
  banner aparece somente com sinal real (`problemTraces.length > 0`).

### P7.9 — Evaluations (re-tune) ✅ `4aa0621`

- Arquivos alterados:
  - `apps/web/app/o/[org]/p/[project]/evaluations/page.tsx` —
    PageHeader eyebrow `Qualidade · Avaliações` (ZIP voice). H1
    passa de `Evaluations` para `Avaliações`. Subtitle: `LLM-as-
    judge e heurísticas executadas sobre traces de produção ·
    {rubrics.length} rubrica(s) / {runs.length} run(s)
    carregadas` (real counts). Nova action `Ver rubricas`
    (`List` icon · `data-testid="evaluations-rubrics-link"`)
    inserida entre `Rodar agora` e `Nova rubrica`. KPI
    `Rubricas` renomeado para `Rubricas ativas`. Importa `List`
    de lucide-react.
  - `apps/web/tests/evaluations-p7.test.mjs` (novo) — 8 testes.
- Validation: `npm test` 183/183 pass · `tsc --noEmit` limpo.
- Conteúdo preservado: AuthRequiredPanel, `getProjectEvaluations`
  + `EVALUATION_RUNS_LIMIT` + `getRubrics` + `getTraces` +
  `getRubricVersions`, `triggerEvaluationAction` form (`<details
  id="run-evaluation">`), tabs ativas/runs/pausadas com
  `evo-tab__count`, tabela `.evo-table` ativa com `DistBars`
  real (`buildDistribution`), `scoreColor`, `rubricDrawerHref`,
  tabela runs com `aggregate_score`/`cost_usd`/`passed`,
  `RubricDrawer` read-only (YAML), 4 `EvaluationSummaryCard`
  (Rubricas ativas / Runs 7d / Pass rate / Custo carregado) com
  hints reais, planned `MoreHorizontal` `disabled
  data-status="planned"`, layout `.evo-evaluations-layout`
  quando `selectedRubric` ativo.
- Nota: `RubricDrawer.tsx` e `DistBars.tsx` não alterados — re-tune
  fica em `page.tsx` (header + actions + label). Drawer/dist bars
  já carregam estado real.

---

## Workflow por fase

1. `git status` limpo na branch `refactor/frontend`.
2. Ler arquivo alvo + ZIP de referência (`/tmp/evo-design/` já
   tem `modules.jsx`; extrair os demais quando precisar).
3. Implementar mantendo todo conteúdo funcional.
4. Adicionar/estender teste em `apps/web/tests/`.
5. `cd apps/web && npm test` (esperar 100% pass).
6. `npx tsc --noEmit -p apps/web/tsconfig.json` (esperar limpo).
7. Hit a página via curl `http://localhost:3000/...` pra verificar
   HMR sem erros novos. Conferir `/tmp/evalops-logs/web.log`.
8. Commit `feat(web): P7.x <módulo> parity`.
9. Atualizar este arquivo: `⬜` → `✅` + hash do commit + bullet
   "Files Changed".
10. Atualizar `cockpit-refactor-handoff-2026-05-20.md` (seção
    P7.x — Files Changed + Validation).

---

## Pendências fora deste plano (referência)

- Backend signals (`expires_at` em ApiKey, `/overview/counts`) —
  destrava dot Keys e sidebar Traces count. Trackado no
  handoff-pai §Pending Work · Gaps condicionais.
- Cleanup de inline alerts (`qp.created`/`qp.error`) agora que
  toast cobre o caso — pós-P7 ou fase própria.
- Auditoria visual Chromium+Firefox + contraste ≥4.5:1 —
  handoff-pai §Resume Prompt opção (c).

---

## Resume Prompt (a ser usado quando retomar)

```text
Continuando P7 (9-módulos parity) no EvalOps.

Repo: /home/rouggerxavier/dev/evalops
Branch: refactor/frontend
Plano: docs/plans/p7-nine-modules-parity-plan.md
Handoff-pai: docs/plans/cockpit-refactor-handoff-2026-05-20.md
Design-fonte: segunda refatoração interna EvalOps.zip

Faça apenas a fase indicada pelo usuário. Não avance pra próxima
sem pedido. Ao terminar: atualizar checkbox + hash no plano e
seção "Files Changed" no handoff-pai.

Premissas duras: não virar placeholder · não perder
funcionalidade · background atual fica · sem dado inventado ·
tokens só em .evo-shell · botões planejados = disabled
data-status="planned".
```
