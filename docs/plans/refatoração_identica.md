# Refatoração Idêntica ao Preview Interno — Plano de Execução

> Branch: `tentativa_refactor`
> Fonte visual: `segunda refatoração interna EvalOps.zip` (extraída em `evalops-preview/`)
> Objetivo: deixar o app autenticado **idêntico** ao preview cockpit do Claude Design — em estrutura de cards, tabs, hierarquia de informação, microcopy, densidade, atalhos e fluxos — preservando **apenas o background e a paleta de cores atuais** do `apps/web/app/globals.css` (que o usuário considera melhores que os do preview). Toda ação de UI deve disparar **chamada real ao backend**; qualquer botão sem backend ganha implementação nova (frontend + backend + migração se preciso).

---

## 1. Princípios e escopo

### 1.1 O que muda
- **Toda a área autenticada do app**: `apps/web/app/o/[org]/p/[project]/**` (overview, traces, evaluations, prompts, rubrics, datasets, experiments, keys, exports), `Sidebar.tsx`, `EvoTopbar.tsx`, `AppShell.tsx`, `ui.tsx`, componentes auxiliares.
- **Backend (`apps/api`)**: novos endpoints para o que o preview promete e ainda não existe (flag, rerun, compare, coverage, attention, rag consolidado, notifications). Migração Alembic onde precisar persistir.
- **README raiz**: trocar pelo texto novo (seção §10).
- **`apps/web/lib/api.ts` e `lib/actions.ts`**: novos wrappers e Server Actions para endpoints novos.

### 1.2 O que NÃO muda
- **`--surface-0` … `--surface-4`, `--primary-*`, `--accent-cyan`, semânticos (`--success/--warning/--danger/--info`), fundo radial do body, grid sutil**. A paleta atual do `globals.css` é mantida. Tokens novos do preview (`--bg-0` oklch etc.) são **adaptados** para os tokens existentes (mapeamento §3.2), não substituídos.
- Rotas públicas (`/`, `/login`, `/register`, `/docs`, `/changelog`, `/app`). Fora de escopo.
- Stack: Next.js App Router + Server Components + Server Actions + CSS puro + `lucide-react`. Sem Tailwind, sem shadcn, sem CSS-in-JS, sem React 18 inline UMD.
- Idioma: PT-BR (o preview é PT-BR; o documento antigo `docs/design-refactor-plan.md` pedia EN, mas o pedido atual é "idêntico ao preview" → mantém PT-BR).

### 1.3 Regras operacionais
- **Nada de mock**. Toda tela puxa dado real via `getOverview`, `getTraces`, `getProjectEvaluations`, `getRubrics`, `getPrompts`, `getDatasets`, `getExperiments`, `getApiKeys`, `getExports` etc. Empty states honestos quando faltar dado.
- **Nada de botão decorativo**. Se o preview tem botão, ele precisa de Server Action conectada a um endpoint real. Se o endpoint não existe ainda, ele é criado no backend (§4) antes de o botão ser ligado.
- **Atalhos `G + letra`**: ligados em todo o app, idênticos ao preview (`G O / G T / G E / G X / G P / G R / G D / G K`). Já existe `EvoShortcuts.tsx` — estender.

---

## 2. Fonte de verdade — mapa do preview

Conteúdo extraído de `evalops-preview/preview/`:

| Arquivo do preview | Conteúdo | Destino no app real |
|---|---|---|
| `styles.css` | Design system completo (tokens, sidebar, topbar, cards, tabela, badges, tabs, filters, waterfall, RAG, modal, toast, attention strip) | Refatora `apps/web/app/globals.css` adaptando aos tokens existentes |
| `components.jsx` | `Icon`, `Badge`, `StatusBadge`, `PreviewPill`, `Sparkline`, `Metric`, `Card`, `AreaChart`, `Modal`, `EndpointSnippet`, `ToastHost`, `PageHeader`, `ScoreCell`, `Copyable`, `fmt` | Novos componentes em `apps/web/components/ui/` (lista §3.4) |
| `shell.jsx` | Sidebar (3 seções, brand, workspace switcher, SDK status pulse, atalhos), Topbar (crumbs, search, env-chip, bell+dropdown, settings, avatar) | Reescreve `Sidebar.tsx`, `EvoTopbar.tsx` |
| `screens/overview.jsx` | KPIs (5 cards), attention strip, custo+volume area chart, custo por modelo table, últimos traces com problema, saúde do SDK, próximos passos sugeridos, cobertura por avaliação, footer | Reescreve `app/o/[org]/p/[project]/page.tsx` |
| `screens/traces.jsx` | Lista com tabs (Todos/Erros/Parciais/Lentos/RAG), filtros, tabela densa com seleção em lote, paginação, detail com KPIs do trace, tabs (RAG/Waterfall/Metadata/Feedback), painel RAG completo, error banner | Reescreve `app/o/[org]/p/[project]/traces/page.tsx` e `traces/[trace]/page.tsx` |
| `screens/evaluations.jsx` | Summary (4 KPIs), tabs (Ativas/Runs/Pausadas), tabela densa com DistBars, drawer com YAML | Reescreve `app/o/[org]/p/[project]/evaluations/page.tsx` |
| `screens/modules.jsx` | Layout único para Prompts, Rubricas, Datasets, Experimentos, Keys, Exports | Reescreve as 6 páginas de módulo respectivas |
| `data.jsx` | `ENDPOINTS` registry + mocks | Mocks descartados. Registry vira `lib/endpoint-registry.ts` (usado pelo `EndpointSnippet` em painel "ações reais"). |

---

## 3. Frontend — plano de execução

### 3.1 Setup inicial (commit 1)

1. Criar branch `tentativa_refactor` (✅ feito).
2. Adicionar import da fonte JetBrains Mono no `globals.css` (já tem Inter, Geist). Não remover Geist — só não usar.
3. Confirmar que `lucide-react` cobre todos os ícones do preview (já cobre).

### 3.2 Tokens — adaptação preservando cores atuais (commit 2)

Mapeamento de tokens do preview → tokens existentes do `globals.css` que **permanecem**:

| Preview | Atual (mantém) |
|---|---|
| `--bg-0` (oklch slate-navy) | `--surface-0` (#060a18) |
| `--bg-1`/`--bg-2` | `--surface-1` (#0a1024) / `--surface-2` (#0f1730) |
| `--surface-1/2/3` (preview) | `--surface-2/3/4` (atuais) |
| `--accent` (#4F8CFF) | `--primary-400` (#3b8df5) — já é cobalto compatível |
| `--ok / --warn / --err / --eval` | `--success / --warning / --danger / --info` |
| `--text / --text-dim / --text-muted / --text-faint` | `--fg-1 / --fg-2 / --fg-3 / --fg-4` |
| `--border-subtle / --border / --border-strong` | `--border-subtle / --border-default / --border-strong` |

Tokens novos a **adicionar** ao `globals.css` (sem trocar bg/cor):

```css
:root {
  --r-xs: 4px;
  --r-sm: 6px;
  --r-md: 8px;
  --r-lg: 12px;
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px;
  --sp-5: 20px; --sp-6: 24px; --sp-8: 32px;
  --sidebar-w: 232px;
  --topbar-h: 48px;
  --font-mono: 'JetBrains Mono', 'Geist Mono', ui-monospace, monospace;
  --eval-soft: rgba(154, 122, 255, 0.14);
  --rag: #5ad4d4;
  --rag-soft: rgba(90, 212, 212, 0.14);
  --rag-border: rgba(90, 212, 212, 0.32);
}
```

### 3.3 Classes do design system — substituição em massa (commit 3)

Adicionar/reescrever no `globals.css` blocos do preview, mas todos com cores adaptadas:

- `.app-shell` (grid `var(--sidebar-w) 1fr`)
- `.sidebar`, `.sb-brand`, `.sb-workspace`, `.sb-section`, `.sb-nav-item` (+ `.is-active`, `.__shortcut`, `.__count`, `.__dot`), `.sb-footer`, `.sb-status` (com `@keyframes pulse`)
- `.topbar`, `.crumbs`, `.topbar__search`, `.env-chip`, `.user-avatar`, `.icon-btn`
- `.page`, `.page-header`
- `.btn`, `.btn--primary`, `.btn--ghost`, `.btn--sm`, `.btn--icon`, `.btn--danger`
- `.card`, `.card__header`, `.card__title`, `.card__subtitle`, `.card__body`, `.card__body--flush`
- `.kpi-grid`, `.kpi-grid--5`, `.metric`, `.metric__*`
- `.badge`, `.badge--ok/--warn/--err/--info/--eval/--rag`, `.tag`, `.preview-pill`
- `.table-wrap`, `table.t`, `.t__num/__name/__id/__mono/__muted/__faint/__chev/__empty`, `.is-flagged`
- `.tabs`, `.tab`, `.tab__count`
- `.filters`, `.filter-group`, `.filter-input`, `.filter-select`
- `.attention`, `.attention__icon/__title/__desc`
- `.waterfall`, `.waterfall__*`, `k-root/tool/retrieval/embed/llm/eval`
- `.rag-header`, `.rag-stat__*`, `.citation`, `.citation__*`, `.claim-row` (ClaimRow ok/ng)
- `.distbars`
- `.modal-overlay`, `.modal`, `.modal__*`
- `.toast-host`, `.toast`, `.toast__*`
- `.share`, `.share__bar`, `.share__pct`, `.score`, `.score__bar`
- `.endpoint-snippet`, `.endpoint-row`, `.endpoint-list`, `.method-GET/POST/DELETE`
- `.empty`, `.empty__*`
- `.code` (pre)
- `.copyable`
- `.grid-2`, `.grid-2-eq`, `.grid-3`, `.grid-detail`
- `.app-footer`, `.module-summary`, `.summary-card`

**Limpeza**: remover classes legadas `.container`, `.panel`, `.section-header` que ainda restem no `globals.css` referentes a páginas legadas (traces/exports).

### 3.4 Componentes compartilhados (commit 4)

Criar em `apps/web/components/ui/` (criar pasta), cada um isolado, server-renderable onde possível:

| Arquivo | Tipo | Origem preview | Função |
|---|---|---|---|
| `Card.tsx` | server | `Card` | Casca com `title/subtitle/action/flush` |
| `PageHeader.tsx` | server | `PageHeader` | Eyebrow + título + subtitle + actions + badges |
| `Metric.tsx` | server | `Metric` | KPI card com label/value/unit/delta/spark |
| `Sparkline.tsx` | server | `Sparkline` | SVG inline com gradient único |
| `AreaChart.tsx` | **client** | `AreaChart` | ResizeObserver — precisa client |
| `Badge.tsx` | server | `Badge` + `StatusBadge` | Variants ok/warn/err/info/eval/rag + dot |
| `PreviewPill.tsx` | server | `PreviewPill` | Chip dashed |
| `Tag.tsx` | server | `tag` inline | Span mono leve |
| `Tabs.tsx` | **client** | `tabs` em screens | Tab list controlada por estado; aceita `searchParams` para SSR fallback |
| `FiltersBar.tsx` | **client** | `filters` em traces.jsx | Form GET horizontal com inputs/selects |
| `DataTable.tsx` | server | `table.t` | Estrutura semântica com slots; row click via `<Link>` ou form |
| `ScoreCell.tsx` | server | `ScoreCell` | Score + barra com threshold tone |
| `DistBars.tsx` | server | inline em evaluations | 6 buckets coloridos |
| `Copyable.tsx` | **client** | `Copyable` | Click → clipboard + toast |
| `ToastHost.tsx` | **client** | `ToastHost` | Event-driven (`evo:toast`); manter como já existe (`EvoToastHost`/`EvoToastBridge`) — só atualizar visual |
| `Modal.tsx` | **client** | `Modal` | Overlay + ESC handler |
| `EndpointSnippet.tsx` | server | `EndpointSnippet` | Lê `endpoint-registry.ts` |
| `AttentionStrip.tsx` | server | `attention` strip | Banner amarelo no Overview |
| `SuggestionRow.tsx` | **client** | `SuggestionRow` | Card clicável que abre modal de confirmação para Server Action |
| `Waterfall.tsx` | server | `waterfall` em trace detail | SVG/divs proporcionais à duração |
| `RagPanel.tsx` | server | `RagPanel` + `ClaimRow` | Painel RAG completo |
| `WorkspaceSwitcher.tsx` | **client** | `sb-workspace` | Combobox real de orgs/projects do usuário (chama `getMe`) |
| `NotificationsBell.tsx` | **client** | bell + dropdown | Lista de notificações (endpoint novo §4.7) |
| `EmptyState.tsx` | server | `empty` em traces.jsx | Ícone + título + descrição + snippet SDK |
| `JsonBlock.tsx` | server | `<pre className="code">` | Bloco JSON/YAML formatado |
| `format.ts` (existente) | util | `fmt` | Acrescentar `ms()`, `pct()` se não tiver |

Remover quando já cobertos pelos novos: `KeyboardShortcuts.tsx` (substituído por `EvoShortcuts.tsx` ampliado), `AnswerPreviewCard.tsx`, `CitationRefsTable.tsx`, `GroundingQualityCard.tsx`, `RAGSummaryHeader.tsx`, `RetrievalSummaryCard.tsx` → absorvidos por `RagPanel.tsx`.

Manter: `EvoToastHost.tsx`, `EvoToastBridge.tsx`, `EvoShortcuts.tsx`, `RubricDrawer.tsx` (reformar visual), `SpanWaterfall.tsx` (substituir por `Waterfall.tsx` mas redirecionar imports), `CopyTextButton.tsx` (reusar como `Copyable.tsx`), `AuthRequiredPanel.tsx`, `RouteError.tsx`, `UserMenu.tsx`, `TracesFilterBar.tsx` (substituir por `FiltersBar.tsx`).

### 3.5 Shell — Sidebar + Topbar (commit 5)

**`Sidebar.tsx`** (server + client island para workspace switcher e shortcuts):
- Brand (logo, "EvalOps", versão `v0.7` lida de `package.json`)
- Workspace switcher real (`WorkspaceSwitcher.tsx`): chama `/v1/me` (já existe), lista orgs e projects do usuário, navega para `/o/{org}/p/{project}`
- 3 seções (Projeto / Recursos / Operação) com `APP_SHELL_NAV_SECTIONS` (já tem) + atalhos `G + letra` exibidos no hover
- SDK status com pulse animado — ligado a novo endpoint `GET /v1/projects/{id}/sdk-status` (§4.7)
- Dot de atenção em "Chaves API" se houver chave expirando em <7d (cálculo no servidor)

**`EvoTopbar.tsx`** (client):
- Crumbs reais (workspace/project/section/...) — já existe parcialmente, refinar
- Search input — submit dispara `?name=` em `/traces` (já faz); add `⌘K` real para focar
- Env-chip clicável: abre dropdown com `prod/staging/dev` e persiste em cookie via Server Action (`setEnvironmentAction`)
- Sino com badge + dropdown (`NotificationsBell.tsx`)
- Settings icon → `/o/{org}/p/{project}/settings` (criar página stub se faltar — §3.6.8)
- Avatar com `UserMenu` (já existe; ajustar visual)

### 3.6 Páginas — reescrita 1:1 com o preview

#### 3.6.1 Overview (`/o/[org]/p/[project]/page.tsx`)
Layout idêntico ao `screens/overview.jsx`:
- `PageHeader` com eyebrow `Workspace · {org}` + select de janela (24h/7d/30d) → query param `?window=` → `getOverview(projectId, env, window)`
- **Attention strip** — só renderiza se houver traces flagged; ler de novo endpoint `GET /v1/projects/{id}/attention` (§4.2)
- **5 KPI cards**: traces, p95 latência, custo, taxa de erro, score médio — todos vindos de `getOverview` (já retorna; ampliar schema se faltar; §4.1)
- **Custo & volume por dia**: `AreaChart` com 14 dias — `getOverview` já retorna `cost_by_day`
- **Custo por modelo**: tabela com 5 colunas (modelo, calls, custo, share) — já existe no overview response
- **Últimos traces com problema** (até 4): `getTraces({status: "error,partial", limit: 4})`; row click → `/traces/{id}`
- **Saúde do SDK**: novo card com p95 ingestão, spans/min — endpoint `GET /v1/projects/{id}/sdk-status`
- **Próximos passos sugeridos**: 3 `SuggestionRow`s que abrem modal de confirmação → dispara Server Action (`triggerEvaluationAction`, `createExperimentAction`, `createExportAction`)
- **Cobertura por avaliação**: % de traces com run por rubrica — endpoint novo `GET /v1/projects/{id}/coverage` (§4.3)
- Botão "Atualizar" → revalida path
- Botão "Rodar avaliação" → abre modal com select de rubrica + trace alvo (último flagged); submete `triggerEvaluationAction`
- Footer com link `/docs`, `/health`

#### 3.6.2 Traces lista (`/o/[org]/p/[project]/traces/page.tsx`)
- `PageHeader` com botões "Exportar JSONL" (chama `createExportAction({format:"jsonl", filters:current})`), "Refresh" (revalida)
- Auto-refresh client-side a cada 30s (client island), só quando a aba está visível
- **Tabs** Todos / Erros / Parciais / Lentos / RAG → query param `?tab=` → traduz para `status=`/`name~rag.`/`duration_gt`
- `FiltersBar`: search por name, status, env — ligado a `getTraces`
- Seleção em lote (checkbox) — habilitar com endpoint novo `POST /v1/traces/bulk-flag` (§4.4)
- Tabela com 12 colunas idêntica ao preview (incluindo `score` da última avaliação — adicionar campo `last_score` no `getTraces` response — §4.5)
- Paginação com cursor (já existe)
- Row click → `/traces/{id}`
- Empty state com snippet do SDK (estático, já vem do preview)

#### 3.6.3 Trace detail (`/o/[org]/p/[project]/traces/[trace]/page.tsx`)
- `PageHeader` com nome, status, env, badge RAG, copyable trace_id, service, ago, user.ref
- 4 botões: **Flagear**, **Reexecutar**, **Comparar**, **Avaliar** — TODOS funcionais:
  - Flagear → `flagTraceAction` → `POST /v1/traces/{id}/flags` (§4.4)
  - Reexecutar → `rerunTraceAction` → `POST /v1/traces/{id}/rerun` (§4.6)
  - Comparar → modal com selector do segundo trace → `compareTracesAction` → `POST /v1/traces/compare` (§4.6); resultado renderiza em `/traces/compare?left=&right=` (nova rota)
  - Avaliar → modal com select de rubrica → `triggerEvaluationAction`
- Error banner (se `trace.status==="error"`): mostra `error.type`, `error.message`, `error.at` — campos já existem em `events`
- **5 KPIs**: duração, tokens entrada, tokens saída, custo, spans/eventos
- **Tabs** RAG (só se `isRagTrace(trace)`), Waterfall, Metadata, Feedback
- **RAG tab** (`RagPanel.tsx`):
  - Header com 4 stats (docs, score médio, claims grounded, risco)
  - Card Resposta gerada (preview do answer com tags de entidade — ler do `events` com `event_type = "llm.completion"`)
  - Card Grounding & qualidade com `ClaimRow`s — endpoint novo `GET /v1/traces/{id}/rag` (§4.8) consolidando o que hoje é montado em `lib/rag.ts`
  - Retrieval (lista ordenada por score)
  - Citação por claim (tabela cruzada)
- **Waterfall tab**: spans em escala absoluta com kinds coloridos
- **Metadata tab**: pre com JSON formatado + botão "Copiar JSON" + card lateral com endpoints da tela
- **Feedback tab**: histórico (`getTraceFeedback`) + formulário (`createTraceFeedbackAction` — já existe)

#### 3.6.4 Evaluations (`/o/[org]/p/[project]/evaluations/page.tsx`)
- `PageHeader` com 3 botões: "Rodar agora" (modal de seleção rubric + trace), "Ver rubricas" (link), "Nova rubrica" (modal com textarea YAML → `createRubricAction`)
- **4 KPIs**: rubricas ativas, runs 7d, taxa de aprovação, custo de avaliação (todos calculáveis no backend — §4.9)
- **Tabs** Ativas / Runs recentes / Pausadas
  - Ativas: tabela com `DistBars` e threshold inline
  - Runs recentes: tabela de últimos `EvaluationRun` (já existe `getProjectEvaluations`)
  - Pausadas: empty state
- Row click → abre `EvaluationDrawer` (Modal) com KPIs + YAML da rubrica + botões "Publicar" / "Rodar"
- Botão "Publicar v{N+1}" abre editor inline da rubrica (textarea pre-preenchida) → `createRubricVersionAction`

#### 3.6.5 Prompts (`/o/[org]/p/[project]/prompts/page.tsx`)
Layout do `screens/modules.jsx` com `moduleId=prompts`:
- Banner "Funcionalidade preservada" — REMOVER (o usuário quer feature inteira, não placeholder)
- Tabela real: lista `getPrompts(projectId)` com colunas Prompt / Versão atual / Usado por / Atualização
- Row click → `/prompts/{prompt_id}` (criar rota se não existir; mostra todas versões com diff)
- Botão "Nova versão" → modal com textarea + variables + changelog → `createPromptAction` ou `createPromptVersionAction`
- Coluna "Usado por" precisa de novo endpoint `GET /v1/prompts/{id}/usage` (lista de traces que referenciam o prompt) — §4.10

#### 3.6.6 Rubrics (`/o/[org]/p/[project]/rubrics/page.tsx`)
- Tabela real de `getRubrics(projectId)`
- Row click → drawer com YAML e versões
- Botão "Nova rubrica" → modal YAML → `createRubricAction`
- Botão "Publicar" por linha → `publishRubricAction` (renomear `createRubricVersionAction`)

#### 3.6.7 Datasets (`/o/[org]/p/[project]/datasets/page.tsx`)
- Tabela real de `getDatasets(projectId)`
- Row click → `/datasets/{id}` mostrando `getDatasetItems`
- Botão "Criar dataset" → modal com slug + source ("manual" / "from-traces" com filtro) → `createDatasetAction` ou `buildDatasetFromTracesAction`

#### 3.6.8 Experiments (`/o/[org]/p/[project]/experiments/page.tsx`)
- Tabela real de `getExperiments(projectId)`
- Botão "Criar experimento" → wizard modal (select dataset, rubric, variants, baseline, pass_criteria) → `createExperimentAction`
- Botão "Rodar" por linha → `runExperimentAction`
- Row click → `/experiments/{id}/runs/{run_id}` (já existe endpoint `getExperimentRun`; criar página de detalhe se faltar)

#### 3.6.9 Keys (`/o/[org]/p/[project]/keys/page.tsx`)
- Tabela real de `getApiKeys(projectId)` mascaradas
- Botão "Criar API key" → modal com name + environment + scopes → `createApiKeyAction` (já existe) → mostra `key` cru via flash
- Botão de revogar por linha → `revokeApiKeyAction` (já existe)
- Card lateral "Política de segurança" estático
- Novo: aviso de chave expirando em 7d (campo `expires_at` — já existe via "API key expiry polling spec")

#### 3.6.10 Exports (`/o/[org]/p/[project]/exports/page.tsx`)
- Tabela real de exports — endpoint `GET /v1/projects/{id}/exports` precisa ser criado (§4.11) — hoje só tem `POST /v1/exports` e `GET /v1/exports/{id}`
- Botão "Novo export JSONL" → modal com filtros (status, env, name_contains, date_range) → `createExportAction` (existe)
- Botão "Baixar" por linha pronto → link para `getExportDownloadPath`
- Card lateral "Limites do export" estático

#### 3.6.11 Settings (nova rota stub) `/o/[org]/p/[project]/settings/page.tsx`
- Página simples com seções: General (nome do projeto, env padrão), Members (lista de memberships da org), Billing (link para usage)
- Endpoints novos: `PATCH /v1/projects/{id}` (renomear projeto), `GET /v1/organizations/{id}/members` (§4.12)

#### 3.6.12 Trace compare (nova rota) `/o/[org]/p/[project]/traces/compare/page.tsx`
- Layout lado a lado com 2 traces, KPIs e waterfalls
- Aceita `?left=&right=`
- Server-side: chama `getTrace` duas vezes em paralelo

### 3.7 Atalhos (commit 6)
Ampliar `EvoShortcuts.tsx` para incluir todos os combos do preview:

```
G O → /
G T → /traces
G E → /evaluations
G X → /experiments
G P → /prompts
G R → /rubrics
G D → /datasets
G K → /keys
G S → /settings
/   → focus search
⌘K  → focus search
?   → modal de atalhos
```

### 3.8 Endpoint registry no frontend (commit 7)
`apps/web/lib/endpoint-registry.ts`:
```ts
export const ENDPOINTS = {
  overview: { method: "GET", path: "/v1/analytics/overview", desc: "..." },
  listTraces: { method: "GET", path: "/v1/traces", desc: "..." },
  // ... 30+ entradas idênticas ao data.jsx
};
```
Usado pelo `EndpointSnippet.tsx` em painéis "Ações reais preservadas" (cards laterais dos módulos) — referência operacional, não decoração.

---

## 4. Backend — novos endpoints e migrações

Cada item lista: endpoint, schema, side-effect, migração se preciso, arquivo.

### 4.1 Overview — ampliar payload
**Já existe**: `GET /v1/analytics/overview` em `routes.py:322`.
**Adicionar** ao response:
- `avg_score: float | null` (média ponderada dos `evaluation_runs` no período)
- `last_window: "24h"|"7d"|"30d"`
- query param novo `?window=`
**Arquivo**: `apps/api/app/api/routes.py`
**Migração**: não precisa.

### 4.2 Attention list
**Novo**: `GET /v1/projects/{project_id}/attention`
Retorna lista canônica e ranqueada do que precisa atenção: traces com `status != "ok"` nas últimas 24h, agrupados por causa (`schema_mismatch`, `vector_db_timeout`, `low_confidence`, `cost_spike`).
Response:
```json
{
  "count": 4,
  "items": [
    {"trace_id": "...", "cause": "schema_mismatch", "service": "billing-agent", "at": "2026-05-20T01:..."}
  ]
}
```
**Arquivo**: `apps/api/app/api/routes.py` (nova função `get_attention`)
**Migração**: não precisa (lê de `traces` + `events`).

### 4.3 Coverage por avaliação
**Novo**: `GET /v1/projects/{project_id}/coverage`
Para cada rubrica do projeto, calcula `% de traces com pelo menos uma EvaluationRun bem-sucedida` nas últimas 24h/7d/30d.
Response:
```json
{ "data": [{"rubric_id": "...", "rubric_slug": "...", "coverage": 0.62, "runs_7d": 4218}] }
```
**Arquivo**: `apps/api/app/api/routes_evaluations.py`
**Migração**: não precisa.

### 4.4 Trace flagging
**Novo**: `POST /v1/traces/{trace_id}/flags`
Body: `{ "reason": "schema_mismatch"|"manual"|"low_quality", "note": "..." }`
Persiste em nova tabela `trace_flags` (campos: `id`, `trace_id` FK, `org_id`, `user_id`, `reason`, `note`, `created_at`).
**Migração Alembic**: `add_trace_flags.py` cria tabela com índice em `trace_id`.
**Arquivo**: `apps/api/app/api/routes.py` + `apps/api/app/models.py` (`TraceFlag` model).

**Novo bulk**: `POST /v1/traces/bulk-flag`
Body: `{ "trace_ids": [...], "reason": "...", "note": "..." }`. Mesma tabela.

### 4.5 Last score em listagem
**Adicionar** ao `GET /v1/traces` response: campo `last_score: float | null` (último `EvaluationRun.score` ordenado por `created_at desc`).
**Migração**: opcional — criar view materializada `trace_last_score` ou subquery on-the-fly. Decisão: subquery on-the-fly, sem migração.
**Arquivo**: `apps/api/app/api/routes.py`.

### 4.6 Rerun + Compare
**Novo**: `POST /v1/traces/{trace_id}/rerun`
Cria job assíncrono que reexecuta o trace original com mesmo prompt/inputs. Body opcional `{ "model": "...", "variables": {...} }`. Retorna `{ "new_trace_id": "...", "status": "queued" }`.
Implementação: enfileira no worker existente (mesmo padrão do `experiment_runner`), usa `prompt_version_ref` + `metadata.input` do trace original. Marca novo trace com `metadata.replay_of = original_trace_id`.

**Novo**: `POST /v1/traces/compare`
Body: `{ "left_trace_id": "...", "right_trace_id": "..." }`. Retorna ambos os traces + diff calculado (status, duration delta, cost delta, span-by-span match por `name`, score delta da última avaliação).

**Arquivo**: novo `apps/api/app/api/routes_trace_actions.py`.
**Migração**: não precisa.

### 4.7 Notifications + SDK status
**Novo**: `GET /v1/projects/{project_id}/notifications?limit=20`
Lista ordenada de eventos relevantes: publicação de rubrica, traces com causa nova, expirações de chave, jobs de export concluídos.
Implementação: nova tabela `notifications` (`id`, `project_id`, `kind` enum, `title`, `meta`, `created_at`, `read_at`).
**Migração Alembic**: `add_notifications.py`.
Listeners de domínio (em `domain/services/*`) inserem na tabela quando relevante. Inicialmente popula via: rubric publish hook, trace ingest com `status=error`, export job state machine.

**Novo**: `POST /v1/projects/{project_id}/notifications/mark-read`
Body: `{ "ids": [...] }`.

**Novo**: `GET /v1/projects/{project_id}/sdk-status`
Retorna `{ p95_ingestion_ms, spans_per_minute, last_event_at, services_seen }` calculado da tabela `events` nos últimos 60min.

### 4.8 RAG consolidado
**Novo**: `GET /v1/traces/{trace_id}/rag`
Retorna estrutura consolidada que hoje é montada no client em `apps/web/lib/rag.ts`:
```json
{
  "retrieved_docs": 6,
  "avg_score": 0.71,
  "grounded_claims": 4,
  "ungrounded_claims": 2,
  "hallucination_risk": "medium",
  "answer_preview": "...",
  "citations": [{"rank":1, "title":"...", "score":0.91, "source":"...", "chunk":"..."}],
  "claims": [{"text":"...", "grounded":true, "cite":"..."}],
  "claim_to_chunk": [{"claim":"...", "chunk":"...", "score":0.91}]
}
```
Server roda heurística de claim extraction + grounding scoring (placeholder: reusa lógica de `lib/rag.ts` em Python).

**Migração**: não precisa.

### 4.9 Evaluation summary
**Novo**: `GET /v1/projects/{project_id}/evaluations/summary`
Retorna 4 KPIs do header: rubrics ativas, runs 7d totais, pass rate ponderado, custo total de avaliação (somatório de `EvaluationRun.cost_usd`).

### 4.10 Prompt usage
**Novo**: `GET /v1/prompts/{prompt_id}/usage?limit=50`
Retorna lista de traces que referenciam `prompt_version_ref` desse prompt em `metadata.prompt_ref`. Calcula `usage_count` agregado.

### 4.11 Exports listing
**Novo**: `GET /v1/projects/{project_id}/exports`
Lista paginada de jobs. Hoje só existe `GET /v1/exports/{id}`. Adicionar listagem.

### 4.12 Members + Project patch
**Novo**: `GET /v1/organizations/{org_id}/members` — lista `Membership` com user info.
**Novo**: `PATCH /v1/projects/{project_id}` — body `{ "name": "...", "default_environment": "prod" }`.

### 4.13 Environment switcher persistência
Cookie (`evalops_env`) lido em Server Component layout e propagado para `getOverview`/`getTraces`. Server Action `setEnvironmentAction` apenas seta o cookie. Sem endpoint backend.

### 4.14 Alembic migrações resumidas
- `2026XXXXXXXX_add_trace_flags.py`
- `2026XXXXXXXX_add_notifications.py`
- `2026XXXXXXXX_add_prompt_ref_index.py` (índice em `traces.metadata->>'prompt_ref'` para suportar §4.10)

### 4.15 Schemas Pydantic
Atualizar `apps/api/app/schemas.py` com:
- `AttentionItemOut`, `AttentionResponse`
- `CoverageItemOut`, `CoverageResponse`
- `TraceFlagIn`, `TraceFlagOut`
- `TraceRerunIn`, `TraceRerunOut`
- `TraceCompareIn`, `TraceCompareOut`
- `NotificationOut`, `NotificationListResponse`
- `SdkStatusOut`
- `RagConsolidatedOut`
- `EvaluationSummaryOut`
- `PromptUsageOut`
- `MemberOut`
- `ProjectUpdateIn`

### 4.16 Testes backend
Para cada endpoint novo, adicionar teste em `apps/api/tests/`:
- `test_attention.py`, `test_coverage.py`, `test_trace_flags.py`, `test_trace_rerun_compare.py`, `test_notifications.py`, `test_sdk_status.py`, `test_rag_consolidated.py`, `test_evaluation_summary.py`, `test_prompt_usage.py`, `test_exports_listing.py`, `test_members.py`, `test_project_patch.py`.
Padrão: `pytest` + fixture `client` + `seed_project`.

---

## 5. Wrappers em `apps/web/lib/api.ts`

Adicionar funções: `getAttention`, `getCoverage`, `flagTrace`, `bulkFlagTraces`, `rerunTrace`, `compareTraces`, `getNotifications`, `markNotificationsRead`, `getSdkStatus`, `getTraceRag`, `getEvaluationSummary`, `getPromptUsage`, `listExports`, `getMembers`, `patchProject`.

Cada uma com seu tipo em `apps/web/lib/types.ts`.

## 6. Server Actions em `apps/web/lib/actions.ts`

Adicionar: `flagTraceAction`, `bulkFlagTracesAction`, `rerunTraceAction`, `compareTracesAction` (redireciona para `/traces/compare?left=&right=`), `markNotificationsReadAction`, `setEnvironmentAction`, `patchProjectAction`, `publishRubricAction` (sobre o `createRubricVersionAction`), `triggerEvaluationFromOverviewAction` (variante com seleção de trace).

Padrão: cada Action chama wrapper, captura erro com `sanitizeApiError`, redireciona com `?error=` ou `?success=`.

---

## 7. Sequência de commits sugerida

Em `tentativa_refactor`:

Status atualizado em 2026-05-21:

| # | Status | Commit real | Plano original |
|---:|---|---|---|
| 1 | ✅ feito | `46ba04f chore(refactor): scaffold branch + extract preview source` | `chore(refactor): scaffold branch + extract preview source` |
| 2 | ✅ feito | `0c3cf75 feat(tokens): add preview tokens preserving palette` | `feat(tokens): add radii/spacing/font-mono/eval/rag tokens preserving palette` |
| 3 | ✅ feito | `bef3fc6 feat(css): port preview design-system classes` | `feat(css): port preview design-system classes adapted to current palette` |
| 4 | ✅ feito | `2c19d14 feat(ui): add shared cockpit components` | `feat(ui): create shared components (Card, Metric, Badge, PageHeader, Tabs, etc.)` |
| 5 | ✅ feito | `a2e39a1 feat(shell): match preview cockpit chrome` | `feat(shell): rewrite Sidebar + Topbar matching preview` |
| 6 | ✅ feito | `a6fc2bf feat(api): add cockpit status endpoints` | `feat(api): add attention/coverage/sdk-status/notifications endpoints + migrations` |
| 7 | ✅ feito | `f6e7ef1 feat(api): add trace action endpoints` | `feat(api): add trace flags + rerun + compare endpoints + migrations` |
| 8 | ✅ feito | `1fb86fe feat(api): add read model endpoints` | `feat(api): add rag consolidated + evaluation summary + prompt usage + exports listing` |
| 9 | ✅ feito | `3083e31 feat(api): add project admin endpoints` | `feat(api): add members + project patch + last_score in trace listing` |
| 10 | ✅ feito | `5db1f22 feat(lib): add endpoint actions` | `feat(lib): add api wrappers + server actions for new endpoints` |
| 11 | ✅ feito | `feat(overview): rewrite to match preview cockpit` | `feat(overview): rewrite to match preview cockpit (attention strip, 5 KPIs, suggestions, coverage)` |
| 12 | ✅ feito | `032eeae feat(traces): rewrite list + detail (tabs, filters, bulk flag, RAG panel)` | `feat(traces): rewrite list + detail (tabs, filters, bulk flag, RAG panel)` |
| 13 | ✅ feito | `feat(evaluations): rewrite summary + tabs + drawer` | `feat(evaluations): rewrite summary + tabs + drawer` |
| 14 | ✅ feito | `feat(modules): migrate prompts/rubrics/datasets/experiments/keys/exports to cockpit` | `feat(modules): rewrite prompts/rubrics/datasets/experiments/keys/exports with real backend` |
| 15 | ✅ feito | `feat(traces): add compare page` | `feat(traces): add compare page` |
| 16 | ✅ feito | `feat(settings): add stub settings page (project patch + members)` | `feat(settings): add stub settings page (project patch + members)` |
| 17 | ✅ feito | `c267780 feat(shortcuts): extend G+letter shortcuts (G S settings)` | `feat(shortcuts): extend G+letter shortcuts (G S settings)` |
| 18 | ✅ feito | `f88f032 chore(cleanup): remove deprecated components superseded by cockpit refactor` | `chore(cleanup): remove deprecated components (AnswerPreviewCard, CitationRefsTable, etc.)` |
| 19 | ✅ feito | `cceb908 docs(readme): replace root README per spec §10` | `docs(readme): replace root README per spec §10` |
| 20 | ✅ feito | `d1fc6d0 test(api): add edge-case unit tests for refactor endpoints` | `test: add backend unit tests for new endpoints` |
| 21 | ✅ feito | `36c08d1 test(e2e): add Playwright smoke for each refactored route` | `test(e2e): add Playwright smoke for each refactored route` |

Observações:
- Os commits 6 a 9 foram agrupados por contratos de backend reais, mantendo os endpoints planejados e testes correspondentes.
- O commit 10 também adicionou tipos em `apps/web/lib/types.ts`, além de wrappers e Server Actions.
- Commit 11 entregou a Overview alinhada ao preview (header c/ janela 24h/7d/30d, attention strip via `GET /v1/projects/{id}/attention`, 5 KPIs com sparkline, custo+volume area chart, custo por modelo, traces flagged, SDK status, sugestões com modais ligadas a Server Actions e cobertura por avaliação via `GET /v1/projects/{id}/coverage`).
- Commit 12 entregou Traces list (5 tabs, GET filters, bulk-flag client island via `bulkFlagTracesAction`, tabela 12 colunas com `last_score`) e Trace detail (4 ações funcionais via modais — flag/rerun/compare/evaluate — 5 KPIs, tabs RAG/Waterfall/Metadata/Feedback via `?tab=`, painel RAG via `GET /v1/traces/{id}/rag`).
- Commit 13 entregou Evaluations cockpit: `PageHeader` (Qualidade · Avaliações + 3 botões header com modais), 4 KPIs reais via `GET /v1/projects/{id}/evaluations/summary` (rubricas ativas, runs 7d, taxa de aprovação, custo de avaliação), 3 tabs (Ativas / Runs recentes / Pausadas) com counts, tabela densa com DistBars + threshold + Judge model + relTime, drawer (Modal) com 3 Metrics + YAML + botões Publicar/Rodar, modais "Rodar agora" / "Nova rubric" / "Publicar v{N+1}" ligados a `triggerEvaluationAction` / `createRubricAction` / `publishRubricAction` (Server Actions com `redirect_section=evaluations`). Sem botão decorativo.
- Commit 14 migrou os 6 módulos secundários (prompts/rubrics/datasets/experiments/keys/exports) para o vocabulário cockpit: todas as classes `evo-*` substituídas por `page`, `page-header`, `btn`, `card`, `table-wrap`/`t`, `module-summary`/`summary-card`, `endpoint-list`/`endpoint-row`, `tabs`, `kpi-grid`, `badge`, `empty`, `grid-detail`, `mono`, `t__muted`, `t__faint`. Removidos os botões decorativos `disabled` ("Importar" em prompts/rubrics/datasets, "Exportar relatório" em experiments, "Ações adicionais" linha-a-linha em experiments). Coluna "Score" placeholder em Prompts virou "Usado por" populada via `GET /v1/prompts/{id}/usage` (`getPromptUsage`). `tsc --noEmit` limpo e `next build` ok.
- Pendências de §14 carry-over para o commit 20 (testes) e revisão final: integração `listExports` no listing de Exports, wizard "from-traces" em Datasets, aviso de chave-expira-em-7d em Keys, e column "Em uso por" nos demais módulos onde aplicável.
- Commit 15 entregou `/o/[org]/p/[project]/traces/compare`: aceita `?left=&right=`, dispara `getTrace`x2 + `compareTraces` em paralelo, renderiza 2 `TraceCard`s (status/env/model/copyable id + 4 KPIs), 5 KPIs de diff (status, Δ duração, Δ custo, Δ tokens, Δ início) com tone bom/ruim, waterfalls lado a lado e tabela de spans agregados por `(type,name)` com Δ duração/erros/modelos. Empty state quando faltam params. Botão "Inverter" troca lados. `tsc --noEmit` limpo.
- Commit 16 entregou `/o/[org]/p/[project]/settings`: General card (form ligado a `patchProjectAction` → `PATCH /v1/projects/{id}` com name/description/default_environment), Members card (tabela via `GET /v1/organizations/{id}/members`), Billing card (link para `/o/{org}/usage`) e card "Ações reais". Adicionado wrapper `getProjects(orgId)` em `apps/web/lib/api.ts` (usa `GET /v1/projects?organization_id=`) para popular dados do projeto atual. Banners de success/error via query string (`?updated=1` / `?error=`). `tsc --noEmit` limpo, rota responde HTTP 200.
- Commit 17 adicionou item `settings` a `APP_SHELL_NAV_SECTIONS` (seção Operacao, path `/settings`, shortcut `G S`). `EvoShortcuts` consome `APP_SHELL_NAV_ITEMS`, então o atalho aciona `router.push` para `/o/{org}/p/{project}/settings` sem mudanças adicionais; Sidebar renderiza o link automaticamente. Teste `ux-polish-p6` ajustado: assert do par `id: "settings", shortcut: "G S"` (preview não atribui letra a exports). Conjunto de letras inalterado.
- Commit 18 removeu 8 componentes legados (`AnswerPreviewCard`, `CitationRefsTable`, `GroundingQualityCard`, `RAGSummaryHeader`, `RetrievalSummaryCard`, `SpanWaterfall`, `TracesFilterBar`, `KeyboardShortcuts`) — todos absorvidos por `components/ui/RagPanel`, `components/ui/Waterfall`, `components/ui/FiltersBar` e `components/EvoShortcuts`. Excluídos `tests/traces-p7.test.mjs` e `tests/traces-premium.test.mjs` (asserções do layout flat pré-refactor, obsoletas após commits 11–12). `tests/rag.test.mjs` (RAG-18) reduzido a `lib/rag.ts` + `components/ui/RagPanel.tsx`. `tests/ux-polish-p6.test.mjs` subteste de atalhos repointado para `EvoShortcuts.tsx` (contrato `prefixArmed`/`projectHref(base, target)`). `tsc --noEmit` limpo; testes RAG-* e shortcut verdes. Pendências CSS legadas (`.evo-shell` em ux-polish-p6 #5 e route-error #3) deixadas para o commit 20 (testes) por já serem pré-existentes.
- Commit 20 adicionou `apps/api/tests/test_refactor_endpoints_edge_cases.py` (15 testes) cobrindo bordas dos endpoints da Phase 8: estado vazio (`attention`, `coverage`, `sdk-status`, `exports`, `evaluation summary`), idempotência (`notifications/mark-read`), auth ausente (`attention 401`), 404 para IDs desconhecidos (`flags`, `rerun`, `prompts/{id}/usage`, `projects/{id} PATCH`, `organizations/{id}/members`), compare com mesmo trace (left==right, bloco `diff` presente), RAG endpoint em trace sem spans RAG (citations/claims vazios) e bulk-flag criando por id. Complementa `test_refactor_attention_coverage_notifications`, `test_refactor_read_model_endpoints`, `test_refactor_project_admin_endpoints` e `test_trace_actions`. Suíte completa do backend: **294 passed**.
- Commit 21 adicionou `apps/web/playwright.config.ts` + `apps/web/e2e/smoke.spec.ts` + `apps/web/e2e/README.md` cobrindo as 11 rotas refatoradas (overview, traces list/compare, evaluations, prompts, rubrics, datasets, experiments, keys, exports, settings) — para cada rota: render OK + `h1.page-header__title` esperado + ausência de error boundary. Cobre também atalho `G T`. Sessão semeada via fetch direto na API (`/auth/login` → fallback `/auth/register`) gravando JWT no cookie `evalops_session`. `testMatch` `*.spec.ts` para não colidir com `node --test`. Script `test:e2e` adicionado; `@playwright/test` declarado em devDep. Não executado no CI atual — roda local com stack viva.
- **Plano §7 concluído**: commits 1–21 todos ✅. Próximos passos pendentes (carry-over §14 + falhas pré-existentes em `ux-polish-p6` `.evo-shell`/route-error #3) seguem para fora deste plano.

---

## 8. QA visual + acceptance

### 8.1 Critérios de "idêntico ao preview"
- Sidebar com 3 seções (Projeto/Recursos/Operação), brand `EvalOps v0.7`, workspace switcher, atalhos no hover, SDK pulse animado, dot de atenção em Keys quando aplicável.
- Topbar com crumbs reais, search ⌘K, env-chip, sino com badge funcional, settings, avatar.
- Overview com attention strip, 5 KPIs com sparkline, area chart custo+volume, custo por modelo, traces com problema, saúde do SDK, próximos passos sugeridos, cobertura por avaliação, footer.
- Traces list com 5 tabs, filtros, tabela densa com 12 colunas incluindo `score`, bulk flag.
- Trace detail com 4 botões funcionais (Flagear/Reexecutar/Comparar/Avaliar), 5 KPIs, 4 tabs (RAG/Waterfall/Metadata/Feedback), RAG panel completo com claim-level grounding.
- Evaluations com 4 KPIs, 3 tabs, DistBars inline, drawer com YAML.
- Modules (prompts/rubrics/datasets/experiments/keys/exports) com dados reais (sem `PreviewPill` "módulo preservado").
- Sem botão sem funcionalidade. Sem placeholder "preview-only".

### 8.2 Smoke E2E (Playwright em `apps/web/tests/`)
Para cada rota: render OK, dado real renderiza, botão primário dispara Server Action e revalida path.

### 8.3 Acessibilidade
- Contraste ≥ 4.5:1 (mantido — paleta atual já passa)
- Foco visível em todos `.btn`, `.icon-btn`, `.tab`, `.filter-input`
- Atalhos não disparam dentro de input/textarea/select

### 8.4 Performance
- Cards e tabelas Server Components onde possível
- Client islands só para AreaChart, FiltersBar, Tabs (controlado), Modal, Copyable, Toast, NotificationsBell, WorkspaceSwitcher, SuggestionRow
- Sem libs novas (`lucide-react` cobre tudo)

---

## 9. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Endpoints novos quebram contratos existentes | Adicionar campo opcional, não remover; versionar testes |
| Migrações Alembic falham em dev local | Rodar `alembic upgrade head` em DB descartável (`test_phase11.db`); reverter com `downgrade` |
| `score` em listagem de traces deixa query lenta | Subquery com `LIMIT 1` por trace + índice composto em `evaluation_runs (trace_id, created_at desc)` |
| RAG consolidado heurística diverge do client antigo | Portar `lib/rag.ts` linha a linha para Python em `app/domain/services/rag_service.py`; teste de paridade com fixture |
| Auto-refresh em traces gasta requisição | Throttle 30s + pausa em `document.hidden` |
| Workspace switcher precisa de listar projects de outras orgs | Reusa `getMe` + cache 60s |
| Notifications crescem indefinidamente | Cleanup job já existe (Phase 7f); estender para limpar > 30d |
| `compareTracesAction` precisa de página dedicada | Criar `/traces/compare` (item 3.6.12) |

---

## 10. README — novo conteúdo

Substituir `README.md` na raiz por:

```markdown
# EvalOps Studio

LLMOps cockpit for trace observability, rubric-based evaluations, prompt & experiment
workflows, and human feedback — opinionated, dark, dense.

## Stack

- **API**: FastAPI + SQLAlchemy + Alembic (`apps/api/`)
- **Web**: Next.js 14 App Router + Server Components + Server Actions + CSS puro (`apps/web/`)
- **SDK**: `evalops-python` (`packages/sdk-python/`)
- Sem Tailwind, sem shadcn, sem CSS-in-JS. Apenas `lucide-react` no frontend.

## Fases entregues

- Phase 1: identity, orgs, projects, API keys
- Phase 2: trace ingestion + SDK Python
- Phase 3: trace dashboard (overview/list/detail)
- Phase 4: rubrics + sync evaluations
- Phase 5: prompts, datasets, experiments
- Phase 6: feedback, exports, usage/quota
- Phase 7: MVP hardening + release prep
- **Phase 8 (atual)**: refatoração interna idêntica ao preview cockpit (branch `tentativa_refactor`) — novos endpoints (attention, coverage, sdk-status, trace flags, rerun, compare, notifications, rag consolidado, evaluation summary, prompt usage, exports listing, members, project patch) e UI reescrita 1:1.

## Layout

```text
apps/
  api/                FastAPI backend
  web/                Next.js dashboard
packages/
  sdk-python/         evalops-python SDK
docs/
  plans/              planos de execução (este arquivo: refatoração_identica.md)
evalops-preview/      fonte visual do redesign (referência, não buildado)
```

## Quickstart local

### 1) API
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 2) Seed
```bash
python scripts/seed_dev.py
```

### 3) Web
```bash
cd apps/web
npm install
npm run dev
```

Abrir `http://localhost:3000`. Login com a conta seed (`dev@local`/`devpassword`).

## Testes

```bash
# Backend
cd apps/api && pytest

# Web
cd apps/web && npm run test
```

## Docs

- `docs/04-system-architecture.md`
- `docs/07-api-spec.md`
- `docs/11-dashboard-and-analytics.md`
- `docs/plans/refatoração_identica.md` (plano da refatoração atual)
- `evalops-preview/DESIGN_NOTES.md` (direção visual e decisões de UX)

## Atalhos do app

| Combo | Tela |
|---|---|
| `G O` | Visão geral |
| `G T` | Traces |
| `G E` | Avaliações |
| `G X` | Experimentos |
| `G P` | Prompts |
| `G R` | Rubricas |
| `G D` | Datasets |
| `G K` | Chaves API |
| `G S` | Settings |
| `⌘K` / `/` | Focar busca |
| `?` | Lista de atalhos |
```

---

## 11. Definition of Done

A refatoração só está concluída quando:
- [ ] Branch `tentativa_refactor` tem todos os commits da §7
- [ ] `alembic upgrade head` aplica todas migrações novas sem erro
- [ ] `pytest` no `apps/api` 100% verde, incluindo os novos testes da §4.16
- [ ] `npm run build` no `apps/web` sem erro de tipo
- [ ] Visual inspection de cada rota bate com o preview correspondente (sidebar/topbar/cards/tabs/tabela/modal/toast)
- [ ] Nenhum botão tem `disabled` decorativo nem `onClick={() => toast("planejado")}` — todo botão tem Server Action ligada
- [ ] README raiz substituído (§10)
- [ ] `docs/plans/refatoração_identica.md` (este arquivo) revisado e marcado como concluído
- [ ] PR aberto contra `main` com screenshot de cada tela
