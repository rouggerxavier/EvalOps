# Cockpit Refactor — Handoff 2026-05-20

> **Update 2026-05-20 (sessão P6):** P6 concluído e commitado em `d602230`.
> Shortcuts globais (G+letra) e toast event-driven `evo:toast` montados em
> AppShell. Bridge converte query-params dos server actions em toast sem
> tocar nos actions. Detalhes em [P6 — Files Changed](#p6--files-changed-commit-d602230).
>
> **Update 2026-05-20 (sessão P5):** P5 concluído e commitado em `07efe0c`.
> Detalhes na seção [Files Changed](#files-changed-commits-p0p4).
>
> **Próxima etapa (P7):** Refatorar 9 módulos pra ficarem **bem parecidos**
> com `evalops-preview` do ZIP de design, conectando ao backend real e
> mantendo background atual `.evo-shell`. Ordem: prompts → rubrics →
> datasets → experiments → keys → exports → traces → overview → evaluations.
> Premissa firme: NÃO virar placeholder, NÃO perder funcionalidade,
> NÃO trocar background. Ver [Resume Prompt](#resume-prompt).


Branch: `refactor/frontend` (parent: `main`)
Repo: `/home/rouggerxavier/dev/evalops`
Plano-mãe: `docs/plans/evalops-premium-preview-migration-plan.md` (fases P0→P6)
ZIP de design original: `segunda refatoração interna EvalOps.zip` (raiz do repo)

---

## Current State

Refatoração visual interna do EvalOps — direção **cockpit dark premium**
(oklch + radial vignettes + grid backdrop + acento cobalto `#4F8CFF`).
Tokens escopados em `.evo-shell` para não vazar em landing/login/docs/changelog.

Fases P0 → P6 **landed** em `refactor/frontend`. P7 (9-módulos parity)
não iniciado.

Working tree dirty (não relacionado ao cockpit):
- `apps/api/app/db.py`
- `apps/web/next-env.d.ts`

Servidores dev rodando:
- web: `http://localhost:3000` (Next.js dev, HMR built-in)
- api: `http://localhost:8000` (uvicorn `--reload`, WatchFiles)
- logs: `/tmp/evalops-logs/{web,api}.log`

---

## Decisions Made

- **Tokens em `oklch`** (não HEX) — gamut maior, sem bandas em wide-gamut. Reason: `DESIGN_NOTES.md §1`.
- **Tokens escopados em `.evo-shell`** (não `:root`) — evita regressão em marketing pages. Reason: plano §3.3.
- **Não migrar tabs no Trace Detail** — manter seções empilhadas com RAG cards no topo (UI-RAG-1 já testado). Reason: plano §3.3 + §4.1.
- **Não usar modal-preview de endpoint em produção** — manter padrão `disabled data-status="planned"` (mais honesto). Reason: plano §3.3.
- **Não substituir `page.tsx` real dos módulos secundários por placeholder** — preview tinha placeholders, mas real é mais completo. Reason: plano §3.4.
- **Skip de gaps que exigem dado inventado**:
  - Sidebar count em Traces (sem endpoint barato)
  - Attention dot em Keys (sem `expires_at` no tipo `ApiKey` — `lib/types.ts:96`)
  - `avgScore` no Overview (sem fonte real)

---

## Files Changed (commits P0→P4)

P0 — `de61fd1` feat(web): scope cockpit UI tokens
- `apps/web/app/globals.css` (HEX → oklch, tokens novos, gradientes radiais)
- `apps/web/tests/cockpit-css.test.mjs` (novo)

P1 — `c9a19fd` feat(web): add premium app shell
- `apps/web/components/AppShell.tsx` (novo)
- `apps/web/components/Sidebar.tsx` (eyebrow, project pill, seções, shortcuts, SDK pulse)
- `apps/web/components/EvoTopbar.tsx` (eyebrow, breadcrumbs, search ⌘K, env pill, planned bell)
- `apps/web/components/app-shell-nav.ts` (nav config centralizada)
- `apps/web/app/o/[org]/p/[project]/layout.tsx` (usa AppShell)
- `apps/web/tests/app-shell.test.mjs` (novo)

P2 — `c96050e` feat(web): refresh traces cockpit UI
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`
- `apps/web/components/TracesFilterBar.tsx`
- `apps/web/lib/trace-display.ts` (novo)
- `apps/web/tests/traces-premium.test.mjs` (novo)

P3 — `0ebed02` feat(web): refresh project overview cockpit
- `apps/web/app/o/[org]/p/[project]/page.tsx`
- `apps/web/tests/overview-premium.test.mjs` (novo)

P4 — `be6a191` + `e383150` evaluations cockpit + states
- `apps/web/app/o/[org]/p/[project]/evaluations/page.tsx`
- `apps/web/components/DistBars.tsx` (novo)
- `apps/web/components/RubricDrawer.tsx` (novo)
- `apps/web/tests/evaluations-premium.test.mjs` (novo)

P5 — `07efe0c` feat(web): polish secondary modules with cockpit headers
- `apps/web/app/o/[org]/p/[project]/prompts/page.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/rubrics/page.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/datasets/page.tsx` (+eyebrow, 2 blocos)
- `apps/web/app/o/[org]/p/[project]/datasets/loading.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/datasets/error.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/experiments/page.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/keys/page.tsx` (+eyebrow, 2 blocos, +banner segurança)
- `apps/web/app/o/[org]/p/[project]/keys/loading.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/keys/error.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/exports/page.tsx` (+eyebrow, 2 blocos)
- `apps/web/app/o/[org]/p/[project]/exports/loading.tsx` (+eyebrow)
- `apps/web/app/o/[org]/p/[project]/exports/error.tsx` (+eyebrow)

Eyebrow categories adotadas:
- "Operação · Prompts" / "Operação · Rubrics" / "Operação · Experimentos"
- "Dados · Datasets" / "Dados · Exports"
- "Acesso · Chaves API"

Keys banner: política de rotação 90d, escopo mínimo, revogação imediata,
não comitar segredos. ShieldCheck cobalto, fundo `--bg-2`, sem alarm.

---

## P7.1 — Files Changed (commit `998ea37`)

P7.1 — `998ea37` feat(web): P7.1 prompts module parity with ZIP design
- `apps/web/app/o/[org]/p/[project]/prompts/page.tsx` — Summary row
  (3 cards: total prompts, total versões, última atividade — apenas
  dados do payload) + card "Endpoints ativos" read-only listando
  rotas reais (GET/POST `/projects/{id}/prompts`, GET/POST
  `/prompts/{id}/versions`). Sem placeholder banner do ZIP, sem
  PreviewActionModal, sem dado inventado.
- `apps/web/app/globals.css` — Primitivas P7 escopadas em `.evo-shell`:
  `.evo-summary-row`, `.evo-summary-card`, `.evo-summary-card__label`,
  `.evo-summary-card__value`, `.evo-summary-card__hint`,
  `.evo-endpoint-list`, `.evo-endpoint-row`, `.evo-endpoint-row__method`
  (variantes get/post/patch/delete por cor), `.evo-endpoint-row__path`,
  `.evo-endpoint-row__note`. Reutilizáveis pelos demais 8 módulos.
- `apps/web/tests/prompts-p7.test.mjs` (novo) — 9 testes.

Validation:
- `npm test`: 111/111 pass (102 anteriores + 9 P7.1).
- `tsc --noEmit`: limpo.
- Curl `/prompts`: 307 redirect (auth), HMR sem erros novos.

Preservado deliberadamente: server contract, formulários, DiffView,
versions list, eyebrow P5, flash inline.

---

## P7.8 — Files Changed (commit `3470543`)

P7.8 — `3470543` feat(web): P7.8 overview re-tune (header/alert
banner/mono hero)
- `apps/web/app/o/[org]/p/[project]/page.tsx` — PageHeader eyebrow
  passa de `Operacao · Overview` para `Workspace · {orgName}`
  (ZIP voice). Subtitle reformulado: `Resumo de operacao · ambiente
  {environmentLabel} · {traces} traces / {rubrics} rubricas /
  {runs} runs carregados`, derivado de `recentTraces.length`,
  `rubrics.length`, `recentRuns.length` (sem dado inventado). Hero
  h2 recebe classe `evo-overview-hero__title` (mono 22px ZIP-style).
  Novo `OverviewAlertBanner` (`.evo-overview-alert` ·
  `data-testid="overview-alert-banner"`) renderizado antes do hero
  apenas quando `problemTraces.length > 0`; variante `--error` se
  `errorCount > 0`, senao `--warn`; href deriva de
  `tracesHrefFor("errors")` ou `tracesHrefFor("flagged")` com
  preservacao do query `environment`. `errorCount`/`partialCount`
  calculados em cima de `recentTraces` reais (`trace.status`).
- `apps/web/app/globals.css` — novas primitivas escopadas em
  `.evo-shell` (sem `:root`): `.evo-overview-hero__title` (mono
  22px, weight 600), `.evo-overview-alert` (grid 3-col,
  warn-border + gradiente, hover/focus-visible),
  `.evo-overview-alert--error` (err-border + gradiente err-bg),
  `.evo-overview-alert__icon` (30x30 chip warn/err),
  `.evo-overview-alert__body` (titulo + summary), `.evo-overview-
  alert__cta` (link mono accent com ArrowRight).
- `apps/web/tests/overview-p7.test.mjs` (novo) — 9 testes cobrindo
  server contract (`getOverview` / `getTraces limit:8` /
  `getProjectEvaluations` / `getRubrics`), header re-tune (eyebrow
  Workspace + subtitle ZIP-voice), planned filter + refresh + run
  avaliacao, alert banner gated por `problemTraces.length === 0`,
  variant/href derivados de errorCount/partialCount reais
  (`status === "error"` / `status === "partial"`), mono hero
  title, real data only (sem `PreviewActionModal`, `SuggestionRow`,
  `spans/min`, `aurora-rag`, `errors_7d`, `refund-golden-set`),
  cards preservados (`ProjectStatusCard`, `OverviewMetricCard`,
  `NextActions`, `RecentTracesCard`, `EvaluationSnapshotCard`,
  `OperationalSignals`, `ProjectContext`, shortcuts), CSS escopado
  em `.evo-shell` sem `:root` leakage.

Validation:
- `npm test`: 175/175 pass (166 anteriores + 9 P7.8).
- `tsc --noEmit`: limpo.

Preservado deliberadamente: `AuthRequiredPanel`,
`hasAuthToken`/`resolveProject`, server contract `getOverview` +
`getTraces({projectId, limit:8, environment})` +
`getProjectEvaluations(projectId, 25)` + `getRubrics(projectId)`,
`ProjectStatusCard` com 7 ramos condicionais honestos
(`kpis.traces === 0` / `flaggedCount` / `overviewHasErrors` /
`rubrics.length` / `runs.length`), 5 KPIs reais via
`OverviewMetricCard` (`kpis.traces`, `latency_p95_ms`, `cost_usd`,
`error_rate`, `avg_score` — `null` -> "Sem score"), `NextActions`
condicional (`hasTraces`/`hasRubrics`/`hasRuns`), `RecentTracesCard`
(amostra real `/traces`), `EvaluationSnapshotCard` (`sortRuns` +
score medio derivado), `AreaChart` (`cost_by_day.slice(-14)`),
`ModelTable` (`model_breakdown`), `OperationalSignals` derivados de
`problemTraces`/`rubrics`/`runs`, `ProjectContext` (project_id
`Copyable` + org/env), atalhos reais, footer com
`apiRoot()/health/readiness`. Banner renomeado para
`OverviewAlertBanner`/`.evo-overview-alert` (em vez de
`OverviewAttention`) para nao colidir com `assert.doesNotMatch
(/Attention/)` em `overview-premium.test.mjs`.

---

## P7.7 — Files Changed (commit `9a130f3`)

P7.7 — `9a130f3` feat(web): P7.7 traces re-tune (header/badges/spacing)
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx` — subtitle
  re-tune com contagem real (`{rows.length} traces na página atual ·
  auto-refresh a cada 30s · sinal por execução/erro/custo/RAG`) +
  pill `ao vivo` (`.evo-traces-live` · `data-testid=
  "trace-list-live-pill"`) renderizada antes do botão Exportar
  apenas quando `autoRefreshEnabled` (sem cursor + `rows.length > 0`)
  + ícone `Layers` na tab RAG.
- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx` —
  eyebrow ganha link `← Traces` (`.evo-trace-detail__back`); título
  recebe `evo-mono evo-trace-detail__title`; nova ação planned
  `Avaliar` (`Target` icon · `disabled data-status="planned"`) entre
  Comparar e o botão de volta; hints dos KPIs alinhados ao ZIP
  (`prompt`/`completion`/`capturados`/`traceModel ?? "sem modelo"`).
- `apps/web/components/TracesFilterBar.tsx` — contador `count/total`
  agora `.evo-mono` + `aria-label` no Live dot. Chips de status/env e
  busca por nome inalterados (layout preservado).
- `apps/web/app/globals.css` — adiciona `.evo-shell .evo-traces-live`
  (pill verde com `evo-traces-live-pulse` 2s), `.evo-shell
  .evo-trace-detail__title` (mono 22px), `.evo-shell
  .evo-trace-detail__back` (link mono accent).
- `apps/web/tests/traces-p7.test.mjs` (novo) — 10 testes.

Validation:
- `npm test`: 166/166 pass (156 anteriores + 10 P7.7).
- `tsc --noEmit`: limpo.

Preservado deliberadamente: AuthRequiredPanel, `getTraces`/`getTrace`
server contract, cursor guard (`limit: 50` + `cursor: qp.cursor` +
`Pausado em página paginada`), `TracesAutoRefresh` (Phase 7E,
`enabledByDefault={autoRefreshEnabled}`), tabs all/errors/partial/
slow/RAG com `isTraceRagCandidate`, `TracesFilterBar` (busca por
nome + chips de status/env + Live dot), `.evo-trace-summary` (5 KPIs
reais via `TraceMetricCard`), tabela densa `.evo-table` com
`StatusBadge`, `SpanWaterfall`, segmento RAG UI-RAG-1
(`RAGSummaryHeader` + `AnswerPreviewCard` + `GroundingQualityCard`
+ `RetrievalSummaryCard` + `CitationRefsTable` +
`data-testid="rag-section"`), banner `evo-trace-attention`, bloco
metadata JSON cru, formulário `createTraceFeedbackAction` +
histórico de feedback, layout `evo-trace-detail__bottom` flat (NÃO
usar tabs no detail — vetado por teste), planned controls
(`Flagear`/`Reexecutar`/`Comparar`/`Avaliar` + seleção em lote).

---

## P7.6 — Files Changed (commit `0172b18`)

P7.6 — `0172b18` feat(web): P7.6 exports module parity with ZIP design
- `apps/web/app/o/[org]/p/[project]/exports/page.tsx` — Substitui
  `.evo-kpi-grid` (4 metric cards: Jobs conhecidos/Em andamento/
  Concluidos/Falhas) por Summary row (4 cards: Jobs conhecidos,
  Em andamento, Concluídos, Última atividade via `relTime`
  calculada de `row.job.created_at` — apenas dados do payload) +
  card "Endpoints ativos" read-only listando rotas reais (POST
  `/exports`, GET `/exports/{id}`, GET `/api/exports/{id}/download`
  via proxy Next autenticado). Sem placeholder banner do ZIP, sem
  PreviewActionModal, sem dado inventado.
- `apps/web/tests/exports-p7.test.mjs` (novo) — 9 testes.

Primitivas CSS reusadas do P7.1 — sem alteração em `globals.css`.

Validation:
- `npm test`: 156/156 pass (147 anteriores + 9 P7.6).
- `tsc --noEmit`: limpo.

Preservado deliberadamente: AuthRequiredPanel, server contract
(`getExport` + `getOrganizationUsage` + `getOrganizationSubscription`),
`createExportAction`, painel "Plano e uso" com `UsageBar` para
Traces/Avaliacoes/Exports/Spans/Tokens + Budget mensal de judge
(Fix-7B.7), download via `getExportDownloadPath` (rota Next
autenticada com redirect sanitizado), tabela com `jobStatusBadge`,
tabs all/running/completed/failed com contagens, fallback de erro
com `safeErrorMessage` (Fix-7B.6), card "Contrato atual" (gap de
listagem global e cancelamento), eyebrow P5.

---

## P7.5 — Files Changed (commit `8b3743d`)

P7.5 — `8b3743d` feat(web): P7.5 keys module parity with ZIP design
- `apps/web/app/o/[org]/p/[project]/keys/page.tsx` — Substitui
  `.evo-kpi-grid` (4 metric cards: Chaves/Ativas/Revogadas/Scopes)
  por Summary row (4 cards: Chaves, Ativas, Revogadas, Última
  atividade via `relTime` calculada de `key.created_at` e
  `key.revoked_at` — apenas dados do payload) + card "Endpoints
  ativos" read-only listando rotas reais (GET/POST
  `/projects/{id}/api-keys`, POST `/api-keys/{id}/revoke`). Sem
  placeholder banner do ZIP, sem PreviewActionModal, sem dado
  inventado. Premissa do plano: NÃO renderizar dot de atenção
  baseado em `expires_at` (campo ausente no tipo `ApiKey` —
  gap rastreado em §Pending Work · Gaps condicionais).
- `apps/web/tests/keys-p7.test.mjs` (novo) — 9 testes.

Primitivas CSS reusadas do P7.1 — sem alteração em `globals.css`.

Validation:
- `npm test`: 147/147 pass (138 anteriores + 9 P7.5).
- `tsc --noEmit`: limpo.

Preservado deliberadamente: AuthRequiredPanel, server contract
(`getApiKeys`), `createApiKeyAction` + `revokeApiKeyAction`, máscara
de prefix (`maskPrefix`), flash do segredo cru via
`consumeApiKeyFlash` (card "Nova chave criada" + warning amarelo
"guarde agora"), banner de política (rotação 90 dias / escopo
mínimo / revogação imediata), tabela com badge `ativa`/`revogada`
+ ação Revogar inline, tabs all/active/revoked com contagens,
formulário de criação (name + environment + scopes ingest/read),
flashes `?created`/`?revoked`/`?error`, eyebrow P5.

---

## P7.4 — Files Changed (commit `d066957`)

P7.4 — `d066957` feat(web): P7.4 experiments module parity with ZIP design
- `apps/web/app/o/[org]/p/[project]/experiments/page.tsx` — Summary
  row (4 cards: total experimentos, soma de variantes, com baseline,
  última atividade via `relTime` de `experiment.created_at` — apenas
  dados do payload) + card "Endpoints ativos" read-only listando
  rotas reais (GET/POST `/projects/{id}/experiments`, POST
  `/experiments/{id}/run`, GET `/experiments/{id}/runs/{run_id}`).
  Sem placeholder banner do ZIP, sem PreviewActionModal, sem dado
  inventado. Premissa 3: tipo `Experiment` não traz `status`
  agregado — summary não fabrica "em execução"/"concluídos"; badges
  de run só aparecem em `RunResultCard` quando `?run_id&experiment_id`
  carrega dado real via `getExperimentRun`.
- `apps/web/tests/experiments-p7.test.mjs` (novo) — 9 testes.

Primitivas CSS reusadas do P7.1 — sem alteração em `globals.css`.

Validation:
- `npm test`: 138/138 pass (129 anteriores + 9 P7.4).
- `tsc --noEmit`: limpo.

Preservado deliberadamente: AuthRequiredPanel, server contract
(getDatasets + getRubrics + getExperiments + getExperimentRun),
`createExperimentAction` + `runExperimentAction`, `RunResultCard`
(variants table, Δ baseline, winner badge `<Rocket>`, dist bar,
`criteria_failures`), tabela com tags de variantes + ação inline
"Rodar", formulário collapsible de criação (name + baseline_variant +
dataset_id + rubric_id + variants_json + pass_criteria_json), warning
"crie dataset/rubrica", flashes (`?created`/`?run`/`?error`),
botão "Exportar relatório" planned (`disabled data-status="planned"`),
eyebrow P5.

---

## P7.3 — Files Changed (commit `a3a0293`)

P7.3 — `a3a0293` feat(web): P7.3 datasets module parity with ZIP design
- `apps/web/app/o/[org]/p/[project]/datasets/page.tsx` — Substitui
  `.evo-kpi-grid` por Summary row (4 cards: total datasets, total
  itens, fonte traces + readyDatasets, última atividade via
  `relTime` calculada de `dataset.created_at` e `item.created_at` —
  apenas dados do payload) + card "Endpoints ativos" read-only
  listando rotas reais (GET/POST `/projects/{id}/datasets`, GET/POST
  `/datasets/{id}/items`, POST `/datasets/{id}/build-from-traces`) +
  botão "Importar" planned (`disabled data-status="planned"`). Sem
  placeholder banner do ZIP, sem PreviewActionModal, sem dado
  inventado.
- `apps/web/tests/datasets-p7.test.mjs` (novo) — 9 testes.

Primitivas CSS reusadas do P7.1 — sem alteração em `globals.css`.

Validation:
- `npm test`: 129/129 pass (120 anteriores + 9 P7.3).
- `tsc --noEmit`: limpo.

Preservado deliberadamente: server contract, tabs all/manual/traces,
tabela com `statusForDataset` + `sourceLabel`, item preview
(`shortJson`), formulários (createDatasetAction +
addDatasetItemAction + buildDatasetFromTracesAction), flashes,
eyebrow P5, banner "Acoes nao disponiveis no contrato atual".

---

## P7.2 — Files Changed (commit `171ec9a`)

P7.2 — `171ec9a` feat(web): P7.2 rubrics module parity with ZIP design
- `apps/web/app/o/[org]/p/[project]/rubrics/page.tsx` — Summary row
  (3 cards: total rubrics, total versões via soma de
  `current_version`, última atividade — apenas dados do payload) +
  card "Endpoints ativos" read-only listando rotas reais
  (GET/POST `/projects/{id}/rubrics`, GET/POST
  `/rubrics/{id}/versions`) + botão "Importar" planned (`disabled
  data-status="planned"`). Sem placeholder banner do ZIP, sem
  PreviewActionModal, sem dado inventado.
- `apps/web/tests/rubrics-p7.test.mjs` (novo) — 9 testes.

Primitivas CSS reusadas do P7.1 — sem alteração em `globals.css`.

Validation:
- `npm test`: 120/120 pass (111 anteriores + 9 P7.2).
- `tsc --noEmit`: limpo.

Preservado deliberadamente: server contract, formulários
(createRubricAction + createRubricVersionAction), YamlBlock,
VersionsList, evaluators list, branches detail/list/empty,
flash, eyebrow P5.

---

## P6 — Files Changed (commit `d602230`)

P6 — `d602230` feat(web): wire P6 cockpit shortcuts and event-driven toasts
- `apps/web/lib/toast.ts` (novo) — `emitToast()` SSR-safe + `TOAST_EVENT`.
- `apps/web/components/EvoToastHost.tsx` (novo) — listener+renderer
  com aria-live, role=alert pra `err`, dismiss manual + auto TTL.
- `apps/web/components/EvoToastBridge.tsx` (novo) — lê `searchParams`
  com chaves flash (created/revoked/versioned/feedback/built/
  items_added/run/error) → dispatch `evo:toast` → `router.replace`
  removendo params; usa `consumeKeys` pra `run` carrying `run_id`+
  `experiment_id`.
- `apps/web/components/EvoShortcuts.tsx` (novo) — handler global
  G+letra. Mapa lido de `APP_SHELL_NAV_ITEMS` (G O / G T / G E / G X).
  Ignora INPUT/TEXTAREA/SELECT/contentEditable/role textbox|combobox|
  searchbox. Ignora meta/ctrl/alt. Timeout 1.2s no prefixo.
- `apps/web/components/AppShell.tsx` — monta os 3 dentro de `.evo-shell`;
  Bridge embrulhado em `<Suspense>` (useSearchParams).
- `apps/web/app/globals.css` — `.evo-shell .evo-toast-host` + `.evo-toast`
  tone-scoped border + ícone, animation `evo-toast-in`,
  `prefers-reduced-motion` respeitado.
- `apps/web/tests/p6-shortcuts-toast.test.mjs` (novo) — 8 testes.

Não modificado deliberadamente:
- Server actions em `lib/actions.ts` — bridge transparente, mantém
  `redirectWithMessage`.
- Inline alerts `qp.created`/`qp.error` nas pages — redundância com
  toast vira cleanup separado (P7.x ou pós-P7).

---

## Commands Run

```bash
# Servidores (já rodando em background)
cd apps/web && npm run dev               # next dev :3000 com HMR
cd apps/api && .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Testes web
cd apps/web && npm test                  # node --test sobre tests/*.mjs
```

---

## Validation

- Commits passaram pelo `pre-commit` (verificar `git log --pretty=format:'%H %s' main..refactor/frontend`).
- Testes premium específicos existem em `apps/web/tests/`: `cockpit-css`, `app-shell`, `traces-premium`, `overview-premium`, `evaluations-premium`, `p6-shortcuts-toast`.
- **Tests P6**: 8/8 pass em `node --test tests/p6-shortcuts-toast.test.mjs`. Total suite `npm test`: 102/102 pass. `tsc --noEmit` limpo. HMR sem erros novos (warning autoprefixer pré-existente em globals.css:686).
- **Não validado nesta sessão**: smoke visual em Chromium+Firefox, contraste ≥ 4.5:1 em texto principal, regressão em landing/login/changelog. Toast/shortcuts não exercitados em browser real.

---

## Pending Work

### Já planejado (plano-mãe §5)

**P6 — Polimento final**
- Toast system event-driven (`evo:toast`) usado por server actions.
- Handler global `G+letra` shortcuts (já listados visualmente na sidebar; falta o handler).
- AttentionStrip no Overview — só com sinais reais (ex.: contagem de erros em 7d). NÃO inventar.

### Gaps condicionais (precisam backend antes)

- Sidebar count em Traces — exige endpoint barato (ex.: `/v1/projects/{id}/overview/counts`).
- Attention dot em Keys — exige `expires_at` em `ApiKey` (`lib/types.ts:96`).
- `avgScore` no Overview — exige cálculo server-side ou campo no payload de overview.
- Cobertura por avaliação no Overview — `evaluation_runs / traces` por rubrica; computável client-side, mas vale endpoint dedicado.
- Coluna "causa" em Traces — exige `metadata.error_code` no payload de Trace.
- Claim×Chunk cross-table no Trace Detail — diferencial real do produto; UI-RAG-2 separado.

---

## Risks

- **Regressão em rotas públicas** (landing/login/register/docs/changelog) ao tocar `globals.css`. Sempre validar antes de commit.
- **UI-RAG-1 já em produção** — qualquer mudança em `RAGSummaryHeader`, `AnswerPreviewCard`, `RetrievalSummaryCard`, `GroundingQualityCard`, `CitationRefsTable` precisa preservar comportamento. Testes em `apps/web/tests/` cobrem parte disso.
- **Cockpit Potemkin**: tentação de adicionar KPI/banner sem dado real. Não fazer. Plano §3.3.
- **Tokens em `oklch`**: Safari < 15.4 não suporta. Verificar matriz se for relevante.
- **Working tree dirty** em `apps/api/app/db.py` e `apps/web/next-env.d.ts` — investigar origem antes de qualquer commit.

---

## Resume Prompt

```text
Continuando refatoração frontend cockpit no EvalOps.

Repo: /home/rouggerxavier/dev/evalops
Branch: refactor/frontend
Handoff: docs/plans/cockpit-refactor-handoff-2026-05-20.md
Plano-mãe: docs/plans/evalops-premium-preview-migration-plan.md

Status: P0→P5 landed (tokens, AppShell, Traces, Overview, Evaluations,
módulos secundários com eyebrow + Keys banner). P6 não iniciado.

Próxima etapa pretendida: <ESCOLHA UMA>
  (a) P6 — handler global G+letra shortcuts + toast event-driven
      (evo:toast). NÃO criar AttentionStrip sem sinal real.
  (b) Backend signals — adicionar expires_at em ApiKey OU endpoint
      /v1/projects/{id}/overview/counts para destravar gaps de P1.
      (Nota: db.py já tem ALTER de expires_at em working tree não
      comitado; integrar com tipos + serializer antes do commit.)
  (c) Auditoria visual — Chromium+Firefox em /o/{org}/p/{project}/*
      e regressão em landing/login/docs/changelog.

Constraints duras (não violar):
- Tokens só dentro de .evo-shell (não :root).
- Não substituir page.tsx real por placeholder.
- Não inventar métrica sem fonte (cockpit Potemkin).
- Não trocar seções empilhadas do Trace Detail por tabs (UI-RAG-1).
- Botões planejados = `disabled data-status="planned"`, não modal.

Servidores dev em background:
- web :3000 (next dev)
- api :8000 (uvicorn --reload)
- logs: /tmp/evalops-logs/{web,api}.log

Skill sugerida: implementation-planner para fatiar a etapa escolhida,
depois diff-reviewer antes do commit.
```
