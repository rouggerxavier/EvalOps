# EvalOps Studio — Auditoria Frontend para Refatoração

> Documento para o agente de design entender o estado atual do frontend antes de refatorar.

---

## O que é o projeto

**EvalOps Studio** é uma plataforma SaaS de observabilidade e avaliação para aplicações de IA (LLMs). Pense em Langfuse/Datadog mas focado em AI ops: tracing de chamadas LLM, avaliações automáticas com rubricas YAML (LLM-as-judge), comparação de prompts via experimentos, e exportação de datasets para fine-tune.

A audiência são desenvolvedores de backend que instrumentam agentes Python e querem dashboards sérios, não brinquedos.

---

## Stack técnica

| Camada | Tecnologia |
|---|---|
| Framework | Next.js 15 (App Router) |
| React | 18.3.1 |
| TypeScript | 5.7.2 |
| CSS | CSS puro com custom properties (zero Tailwind, zero CSS-in-JS) |
| Ícones | lucide-react 0.469 |
| 3D/WebGL | three.js 0.184 (só na landing page, para o LightPillar animado) |
| Fontes | Inter + JetBrains Mono (Google Fonts) |
| Build | Next.js padrão, sem turbopack configurado |

**Sem biblioteca de componentes externa** (sem shadcn, sem MUI, sem Radix). Tudo feito à mão com classes CSS.

---

## Estrutura de arquivos

```
apps/web/
├── app/
│   ├── layout.tsx                    # Root layout (sem providers, só html/body)
│   ├── globals.css                   # Sistema de design inteiro (~1530 linhas)
│   ├── page.tsx                      # Landing page marketing
│   ├── app/page.tsx                  # Entrypoint pós-login (redirect para workspace)
│   ├── login/page.tsx                # Página de login
│   ├── register/page.tsx             # Página de registro
│   ├── changelog/page.tsx            # Changelog público
│   ├── docs/page.tsx                 # Docs estáticas
│   └── o/[org]/p/[project]/          # App autenticado (workspace)
│       ├── layout.tsx                # Layout com Sidebar + Topbar
│       ├── page.tsx                  # Overview / dashboard principal
│       ├── traces/
│       │   ├── page.tsx              # Lista de traces
│       │   └── [trace]/page.tsx      # Detalhe de um trace
│       ├── evaluations/page.tsx      # Lista de avaliações
│       ├── rubrics/page.tsx          # Rubricas YAML
│       ├── keys/page.tsx             # API Keys
│       ├── prompts/page.tsx          # Versionamento de prompts
│       ├── datasets/page.tsx         # Datasets para experimentos
│       ├── experiments/page.tsx      # Experimentos A/B de prompt/modelo
│       └── exports/page.tsx          # Jobs de exportação JSONL
├── components/
│   ├── Sidebar.tsx                   # Sidebar do app (use client)
│   ├── UserMenu.tsx                  # Menu do usuário no topbar
│   ├── AuthRequiredPanel.tsx         # Fallback de autenticação
│   ├── AuthSidePanel.tsx             # Painel direito nas páginas de auth
│   ├── LightPillar.tsx               # Efeito Three.js da landing (use client)
│   ├── LightPillar.module.css        # CSS do Three.js canvas
│   ├── MarketingNav.tsx              # Navbar da landing/marketing
│   ├── MarketingFooter.tsx           # Footer da landing
│   └── QuickstartCard.tsx            # Card de empty state com instruções SDK
├── lib/
│   ├── api.ts                        # Todas as chamadas ao backend (fetch tipado)
│   ├── auth.ts                       # Session, cookie, login/register via API
│   ├── auth-actions.ts               # Server Actions de auth (login/register/logout)
│   ├── actions.ts                    # Server Actions de domínio (ex: criar feedback)
│   └── types.ts                      # Tipos TypeScript completos de todos os modelos
└── public/
    └── brand/
        ├── logo-evalops.svg
        └── mark-evalops.svg
```

---

## Padrões de arquitetura

### Server Components first
Todas as páginas são Server Components por padrão. Buscam dados diretamente nas funções `lib/api.ts` — sem `useEffect`, sem SWR, sem React Query. Só usa `"use client"` onde precisa de interatividade (Sidebar, UserMenu, LightPillar).

### Server Actions para mutações
Login, registro, criar feedback e logout usam Next.js Server Actions (`lib/auth-actions.ts`, `lib/actions.ts`). Os `<form action={serverAction}>` são usados diretamente.

### Autenticação
- Cookie httpOnly `evalops_session` com o bearer token JWT
- Fallback: env var `EVALOPS_DASHBOARD_BEARER_TOKEN` para dev sem login
- `getSession()` em `lib/auth.ts` chama `GET /v1/auth/session` a cada request SSR para validar o token
- Redirect para `/login` feito no `layout.tsx` do workspace com `redirect()` do Next

### URL do backend
`EVALOPS_API_BASE_URL` (default: `http://localhost:8000/v1`). Toda chamada passa por `lib/api.ts` com autenticação via `authHeaders()`.

### Roteamento
URL pattern: `/o/[org-slug]/p/[project-slug]/[section]`
- `[org]` e `[project]` são slugs legíveis (ex: `/o/acme/p/docops-agent`)
- A função `resolveProject(orgSlug, projectSlug)` converte para UUIDs internos via `GET /v1/resolve`

---

## Sistema de design (globals.css)

O arquivo tem ~1530 linhas divididas em seções:

### Tokens CSS (`:root`)
```
Superfícies:  --surface-0 a --surface-4 (escuro: #060a18 → #1a2547)
Bordas:       --border-subtle/default/strong/focus
Texto:        --fg-1 a --fg-4, --fg-disabled
Primário:     --primary-50 a --primary-700, --primary-glow
Accent:       --accent-cyan, --accent-cyan-soft
Semântico:    --success/warning/danger/info (+ soft + border variants)
Séries chart: --series-1 a --series-6
Tipografia:   --font-sans/mono, --text-2xs a --text-4xl
Espaçamento:  --space-1 a --space-12 (base 4px)
Raios:        --radius-xs a --radius-pill
Sombras:      --shadow-xs a --shadow-lg, --shadow-glow-*
Animação:     --ease-standard/out, --duration-fast/normal/slow
```

### Seções do CSS
1. **Tokens** — variáveis raiz
2. **Reset + Base** — box-sizing, body, links
3. **App shell** — `.app` grid 240px sidebar + 1fr
4. **Sidebar** — `.sidebar`, `.workspace`, `.nav`, `.nav__item`
5. **Topbar** — `.topbar`, `.project-picker`, `.env-pill`, `.search`
6. **Main canvas** — `.main`, `.page-header`, `.layout` (1fr + 320px rail)
7. **KPI Cards** — `.kpi-grid`, `.card`, `.kpi`, `.kpi__value`, `.kpi__sparkline`
8. **Charts** — `.chart-row`, `.chart-head`, `.legend-dot`
9. **Tabela de traces** — `.t-table`, `.badge`, `.score-cell`, `.score-bar`
10. **Rail direito** — `.rail`, `.rubric-row`, `.flag-row`, `.donut-row`
11. **Footer** — `.app-footer`
12. **Classes de compat** — `.container`, `.panel`, `.row`, `.grid-4`, `.grid-2`, `.kpi-compat` ← legado
13. **Marketing/Landing** — `.mk-shell`, `.hero`, `.feature-grid`, `.steps`, `.snippet`, etc.
14. **Auth pages** — `.auth-shell`, `.auth-grid`, `.auth-pane`, `.auth-field`, etc.
15. **Media queries** — breakpoints em 1180px e 880px

---

## Estado atual de cada página

### ✅ Polidas e consistentes com o design system

| Página | Notas |
|---|---|
| `app/page.tsx` (Landing) | Completa: LightPillar 3D, hero, feature grid, code snippet, steps, CTA, footer |
| `login/page.tsx` | Layout auth-grid 2 colunas, formulário com Server Action |
| `register/page.tsx` | Equivalente ao login, mesma estrutura |
| `o/[org]/p/[project]/page.tsx` | Dashboard mais polido: KPI cards com sparklines SVG, charts SVG, tabela, rail com donut |
| `components/Sidebar.tsx` | Totalmente alinhada ao design system |

### ⚠️ Páginas funcionais mas com estilo legado / inconsistente

| Página | Problema |
|---|---|
| `traces/page.tsx` | Usa `.container`, `.panel`, `.row` (compat). Texto PT-BR misturado. Sem design system novo. |
| `traces/[trace]/page.tsx` | Igual acima + strings com encoding quebrado (`DuraÃ§Ã£o`, `ComentÃ¡rio`) = UTF-8 mal salvo |
| `evaluations/page.tsx` | Provavelmente no mesmo estado (não lida, mas segue o padrão das outras) |
| `rubrics/page.tsx` | Idem |
| `keys/page.tsx` | Idem |
| `prompts/page.tsx` | Idem |
| `datasets/page.tsx` | Idem |
| `experiments/page.tsx` | Idem |
| `exports/page.tsx` | Idem |
| `components/AuthRequiredPanel.tsx` | Usa classes compat (`.container`, `.panel`). Texto PT-BR. |

---

## Problemas específicos a corrigir na refatoração

### 1. Strings PT-BR com encoding quebrado
Em `traces/[trace]/page.tsx` e `traces/page.tsx`, vários strings têm encoding corrompido:
- `"DuraÃ§Ã£o"` → deve ser `"Duração"`  
- `"ComentÃ¡rio"` → `"Comentário"`
- `"comeÃ§ar"` → `"começar"`

O app é PT-BR ou EN? A landing e o overview são EN, as telas internas são PT-BR quebrado. Decisão: unificar em inglês (padrão do produto).

### 2. Dois "estilos" coexistindo
- **Estilo novo**: `.card`, `.kpi-grid`, `.badge`, `.t-table`, `.page-header` (usado no overview)
- **Estilo legado**: `.container`, `.panel`, `.row`, `.grid-4` (usado nas sub-páginas)

Todas as páginas internas precisam migrar para o estilo novo.

### 3. globals.css monolítico
1530 linhas em um arquivo é difícil de manter. Candidato a ser dividido em:
- `design-tokens.css`
- `base.css`
- `layout-app.css` (sidebar, topbar, main)
- `components.css` (cards, badges, tables, etc.)
- `marketing.css` (landing, auth)

### 4. Nenhum componente de tabela reutilizável
A tabela de traces no `overview/page.tsx` usa `.t-table` com design correto. As outras páginas usam `<table>` nua. Candidato a extrair um componente `<DataTable>`.

### 5. Inline styles espalhados
Várias páginas usam `style={{ color: "var(--fg-3)", fontSize: 12 }}` inline em vez de classes. Sujos e difíceis de manter.

### 6. Topbar não funcional
O topbar em `o/[org]/p/[project]/layout.tsx` tem um seletor de datas ("Last 7 days") e seletor de ambiente ("Prod") hardcoded. Precisam ser funcionais.

### 7. Sidebar footer cards hardcoded
O "SDK Python — Healthy / Last seen: 1m ago" no footer da sidebar é estático/fake.

---

## Fluxo de dados resumido

```
Browser → Next.js Server Component
          → lib/api.ts (fetch com Bearer token do cookie)
          → FastAPI backend em localhost:8000/v1
          → Postgres

Mutações → <form action={serverAction}> ou
           fetch no Server Component
```

**Não há estado global do lado cliente.** Tudo é SSR puro. Quando uma mutação acontece (ex: criar feedback), o Server Action redireciona de volta para a mesma página com `?feedback=1` para mostrar confirmação.

---

## Modelos de dados (lib/types.ts)

Tipos completos definidos para todas as entidades:

- `Trace` — trace raiz (id, name, status, duration_ms, tokens, cost_usd, tags, metadata)
- `TraceDetailResponse` — trace + spans + events + feedback
- `OverviewResponse` — KPIs + cost_by_day + model_breakdown + recent_flagged
- `Rubric` + `RubricVersion` — rubrica com versão YAML
- `EvaluationRun` + `EvaluationScore` — resultado de uma avaliação
- `Prompt` + `PromptVersion` — prompt versionado
- `Dataset` + `DatasetItem` — dataset de itens input/output
- `Experiment` + `ExperimentRun` — experimento com variantes e resultados
- `HumanFeedback` — thumbs + rating + comment + correction
- `ExportJob` — job de exportação JSONL
- `ApiKey` + `ApiKeyCreateResponse` — API keys do projeto
- `OrgSubscription` + `OrgUsage` — billing e uso mensal

---

## Variáveis de ambiente relevantes

```env
EVALOPS_API_BASE_URL=http://localhost:8000/v1
EVALOPS_DASHBOARD_BEARER_TOKEN=evk_dev_...   # fallback sem login (dev)
```

---

## Resumo para o refactor

**O que está bem feito e deve ser preservado:**
- Design tokens no CSS (excelente base, dark-mode first)
- Landing page (completa, polida, Three.js funcionando)
- Login/Register (clean)
- Overview dashboard (melhor página do app, usar como referência)
- Sidebar (bem estruturada)
- `lib/api.ts` e `lib/types.ts` (não tocar)
- Padrão Server Components + Server Actions (não mudar para client-side)

**O que precisa ser refatorado:**
1. Todas as páginas do workspace (traces, evaluations, rubrics, keys, prompts, datasets, experiments, exports) precisam ser migradas do estilo legado para o design system novo — usando `.card`, `.page-header`, `.t-table`, `.badge` etc.
2. Corrigir encoding UTF-8 quebrado em trace detail e trace list
3. Unificar idioma para inglês em toda a interface
4. Extrair componentes reutilizáveis: `<DataTable>`, `<PageHeader>`, `<EmptyState>`
5. Opcionalmente dividir `globals.css` em arquivos menores

**Referência de estilo:** `app/o/[org]/p/[project]/page.tsx` (overview) é a implementação mais completa e deve guiar as outras páginas.
