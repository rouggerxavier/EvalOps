# 11 — Dashboard & Analytics

Dashboard em Next.js 15 (App Router) + Tailwind + shadcn/ui + Recharts.

## 1. Princípios de UX

- **Time-to-insight ≤ 30s.** Da home até "ah, esse modelo está custando 3x mais que o outro" em meia dúzia de cliques.
- **Drill-down sempre.** Toda métrica tem caminho claro até o trace individual.
- **Filtros persistentes na URL.** Para compartilhar links de análise (`?from=...&model=gpt-4o-mini&min_score=0.7`).
- **Empty state educa.** Sem traces? Mostra snippet de instrumentação com a key real.
- **Densidade alta com hierarquia clara.** Este é um produto para engenheiros, não para CMOs.

## 2. Mapa de telas

```
/login
/onboarding             — primeira org/projeto
/o/[org]                — overview da org
  /                     — projetos
  /settings             — billing, members, plano

/o/[org]/p/[project]    — overview do projeto (default landing)
  /traces               — listagem
    /[trace]            — detalhe
  /evaluations          — runs
    /[run]              — detalhe
  /rubrics              — rubricas
    /[slug]             — versões + diff
  /experiments          — experiments
    /[id]/runs/[run]    — detalhe
  /prompts              — prompts versionados
    /[slug]
  /datasets
    /[slug]
  /exports
  /api-keys
  /settings             — auto-eval, retention, redaction
```

## 3. Telas detalhadas (MVP)

### 3.1 Project Overview (`/o/{org}/p/{project}`)

**Cabeçalho:**
- Nome do projeto + dropdown de environment (dev/staging/prod) + range picker.

**KPIs (cards):**
1. Traces (último período) — número grande + sparkline.
2. Custo USD — total + sparkline + breakdown por modelo (tooltip).
3. Latência p95 — número + sparkline.
4. Score médio — número + delta vs período anterior.
5. % Erro — número + sparkline.

**Charts:**
- "Custo por dia" (stacked bar por modelo).
- "Score médio por modelo" (linha).
- "Latência p50/p95/p99 por dia" (multi-line).

**Listagem:**
- "Últimos 10 traces flagged" (score < threshold OU erro). Click → trace detail.

### 3.2 Traces list (`/traces`)

- Filtros (sidebar): date range, status, model, score range, tag, service, search por nome/conteúdo.
- Tabela paginada cursor (50/página): `created_at`, `name`, `model`, `tokens_in/out`, `cost_usd`, `latency_ms`, `score`, `feedback`, `tags`.
- Coluna "score" colorida (green ≥ threshold, yellow ≥ 0.5, red < 0.5).
- Bulk: selecionar e "Run rubric on selected", "Add to dataset", "Export".
- Atalho `g t` → traces.

### 3.3 Trace detail (`/traces/{id}`)

Layout em 3 colunas (lg) ou stacked (sm):

**Coluna esquerda (árvore):**
- Árvore de spans com ícones por tipo, status, duration. Click → seleciona.

**Coluna central (conteúdo do span selecionado):**
- Tabs: `Messages`, `Tools`, `Output`, `Raw JSON`.
- Mensagens em formato chat com syntax highlighting.
- Diff opcional: `messages_in` rendered vs original prompt template.

**Coluna direita (metadata + evals + feedback):**
- Cost breakdown.
- Lista de evaluations (com score, expand para ver `reasoning` do judge).
- Feedback humano.
- Botões: "Run rubric...", "Add to dataset", "Copy as cURL", "Delete trace".

**Atalho:** `j/k` para navegar entre traces na lista filtrada (preserva filtros via URL).

### 3.4 Rubric editor (`/rubrics/{slug}`)

- Lista de versões com timeline.
- Editor Monaco para YAML com schema-aware autocompletion (json-schema do rubric format).
- Botão "Validate" → server valida e retorna issues inline.
- Botão "Test on trace..." → modal seleciona trace recente, dry-run, mostra scores.
- "Push" cria nova versão se conteúdo mudou.

### 3.5 Experiments

- **Listagem:** nome, dataset, rubric, último run (status, passed, pass_rate).
- **Run detalhado:** tabela `variant × dataset_item` com score, custo, latência. Heatmap colorido.
- **Comparação:** chart de barras por variant para `pass_rate`, `avg_score`, `total_cost_usd`. Highlight regression.
- **CTA:** "Run again" / "Promote variant X to current prompt".

### 3.6 Prompts

- Listagem: prompts do projeto.
- Detalhe: timeline de versões; diff entre 2 selecionadas.
- "Open in playground" (Futuro).

### 3.7 Datasets

- Listagem: nome, fonte, # items, criado em.
- Detalhe: tabela paginada de items, filtro, "Add from traces" (filtros), "Export".

### 3.8 API Keys (`/api-keys`)

- Listagem (sem expor key): prefix, name, env, scopes, last_used, created_at, status.
- "Create new" → modal mostra key uma vez com warning + copy button.
- "Revoke" com confirm.

### 3.9 Settings

- Project: name, slug, environments, retention, redaction toggle.
- Auto-eval: lista de rubricas + "rodar em ingestion sim/não".
- Members: convidar (email), role.
- Org/Billing: plano atual, uso do mês (mockado), histórico.

## 4. Componentes shadcn/ui usados

- `Card`, `Tabs`, `Sheet`, `Dialog`, `Command` (cmd+k), `DataTable` (com tanstack-table), `Form`, `Toast`.
- Charts: Recharts (`LineChart`, `BarChart`, `AreaChart`) com wrappers custom em `components/charts/`.
- Editor YAML: `@monaco-editor/react`.
- Diff: `react-diff-viewer-continued`.

## 5. Estado & data fetching

- Server Components fazem fetch inicial (lista de projetos, overview).
- Client Components com `swr` ou `@tanstack/react-query` para listagens com filtros (URL como source of truth).
- Mutations via Server Actions (Auth.js sessão → API key interna do BFF → API).
- Cache: `swr` revalidate on focus desativado em telas de drill-down (resultados não mudam).

## 6. Performance

- LCP < 2s (NFR-04). Server rendering das primeiras 50 linhas, hydrate o resto.
- Tabelas com virtualização (`react-virtuoso`) quando > 200 linhas.
- Charts com `<Suspense>` + skeleton.
- Dados agregados (overview) cacheados em Redis 60s.

## 7. Empty states / onboarding inline

Cada tela importante tem empty state que ensina o próximo passo:

- **Sem traces:** card "Comece em 3 linhas" com snippet Python copy-pasteable.
- **Sem rubrica:** "Crie sua primeira rubrica" com botão para template default (`default-llm-helpfulness`).
- **Sem experiment:** "Compare 2 modelos lado a lado" com modal pre-preenchido.

## 8. Acessibilidade & i18n

- WCAG AA: contraste, focus rings, aria-labels.
- Dark mode default (este é produto de eng).
- i18n: **out of scope MVP**. Strings em pt-BR no MVP de portfólio (com plano de migrar para EN antes de público).

## 9. Telemetria do próprio dashboard

- Page views via Plausible (privacy-friendly) — opcional, sem cookies.
- Errors capturados pelo Sentry frontend com source maps.

## 10. Mockups / wireframes

> Mockups visuais ficam fora deste documento — recomenda-se montagem em Figma na etapa de UI design. Os layouts acima são suficientes para começar a implementar com componentes shadcn padrão.

## 11. Open questions

- **[Decisão pendente]** Real-time updates (WebSocket/SSE) na trace list? Recomendação: **não** no MVP; refresh manual ou polling 10s.
- **[Decisão pendente]** Onboarding interativo (tour) na primeira sessão? Recomendação: **não** — empty states inline são suficientes.
