# EvalOps — Plano de migração do preview premium (cockpit)

Status: planejamento docs-only. Nenhuma alteração de código, backend, SDK,
schema, migrations, deploy, Oracle VM ou git foi feita por este plano.
Implementação fica para fases futuras (P0 → P6), cada uma a ser executada
via plano de implementação próprio.

Data: 2026-05-20.
Repo: `/home/rouggerxavier/dev/evalops`.
Branch base: `main`.
HEAD na auditoria: `383dc21` (`feat(web): add RAG trace detail cards`).
ZIP auditado: `segunda refatoração interna EvalOps.zip` (na raiz do repo).
Skills usadas: nenhuma (skills do agent-framework não foram disparadas;
fallback = inspeção direta + leitura do ZIP).

---

## 1. Contexto

O Claude Design produziu um preview frontend isolado (`evalops-preview/`)
com a proposta de refatoração visual interna do EvalOps: direção
**cockpit dark premium**. Não há backend, persistência, nem build no
preview — é um HTML standalone + bundle multi-arquivo (React 18 UMD +
Babel standalone, CSS puro com tokens em `:root`).

O frontend real do EvalOps em `apps/web/` (Next.js, App Router) já
expressa o mesmo conceito: shell `evo-*`, sidebar com seções
**Projeto / Recursos / Operação**, topbar com breadcrumbs, badges
semânticos, kpi grid, tabela densa, cards RAG. Tokens em
`apps/web/app/globals.css` (paleta navy `#0a1024`, primário `#3b8df5`,
mono Geist/JetBrains).

Recentemente foi entregue **UI-RAG-1** (commit `383dc21`):

- `RAGSummaryHeader`, `AnswerPreviewCard`, `RetrievalSummaryCard`,
  `GroundingQualityCard`, `CitationRefsTable`, helpers em
  `apps/web/lib/rag.ts`, fixtures e detalhe de trace já renderizando
  os cards quando `isRagTrace(detail) === true`.

O preview do ZIP **não substitui** essa entrega. Deve ser tratado como
**referência visual/UX** para evoluir o app real sem regredir as
funcionalidades já implementadas.

---

## 2. Resumo do ZIP

Caminho do ZIP: `./segunda refatoração interna EvalOps.zip`.
Extraído em: `/tmp/evalops-preview-audit/` (fora do repo).

Estrutura relevante:

```
evalops-preview/
  EvalOps Preview.html           # standalone, ~188 linhas
  README.md                      # como abrir + atalhos
  DESIGN_NOTES.md                # direção visual + recomendações (260 linhas)
  preview/
    index.html                   # entry multi-arquivo
    styles.css                   # design system (oklch, ~990 linhas)
    data.jsx                     # mocks + ENDPOINTS registry
    components.jsx               # Badge/Card/Sparkline/AreaChart/Modal/Toast
    shell.jsx                    # Sidebar/Topbar/router por hash
    app.jsx                      # wiring + atalhos G+letra
    screens/
      overview.jsx               # 5 KPIs + cost area + model breakdown +
                                 # attention strip + sugestões + cobertura
      traces.jsx                 # lista com tabs (Todos/Erros/Parciais/Lentos/RAG)
                                 # + detalhe com painel RAG completo
      evaluations.jsx            # summary 4 KPIs + tabs + DistBars + drawer YAML
      modules.jsx                # placeholders premium p/ Prompts/Rubricas/Datasets/
                                 # Experimentos/Chaves/Exports
```

Há também uma cópia duplicada em `preview/` na raiz e um diretório
`docs/` com snapshots de `07-api-spec.md`, `11-dashboard-and-analytics.md`,
`design-refactor-plan.md`, `frontend-audit.md` e `apps/web/components/`
**versões propostas** (RAG cards, Sidebar, EvoTopbar, SpanWaterfall,
TracesFilterBar, ui.tsx). Estes arquivos do ZIP NÃO devem ser copiados
direto para o repo.

Stack do preview: React 18 UMD + Babel standalone + CSS puro (`oklch`
tokens), Inter + JetBrains Mono via Google Fonts. Sem Tailwind, sem
shadcn, sem Radix.

Observações relevantes:
- Tokens em `oklch` no preview vs HEX no `globals.css` real. Conversão
  precisa preservar contraste ≥ 4.5:1.
- `data.jsx → ENDPOINTS` mapeia 1:1 endpoints reais inferidos de
  `apps/web/lib/api.ts` e `apps/web/lib/actions.ts`. Útil como
  documentação cruzada; **não migrar como código**.
- O preview honesta ações “planejadas” via modal com `EndpointSnippet`.
  No app real, hoje, esse padrão já existe parcialmente via botões
  `disabled data-status="planned"`.

---

## 3. Diagnóstico do preview

### 3.1 Tabela de áreas

| Área do preview | Vale migrar? | Por quê | Risco | Prioridade |
|---|---|---|---|---|
| Tokens cockpit (oklch + grid sutil + vinhetas radiais) | Sim, parcial | Eleva sensação visual sem quebrar contratos. Já alinhado ao `globals.css`. | Conversão oklch→HEX pode mudar contraste; risco de regressão em landing/marketing que reusa tokens. | Alta |
| Sidebar com count em Traces + dot de atenção em Keys | Sim | Sinal útil, baixo custo. | Count exige fetch — só mostrar quando barato. | Média |
| Topbar com search global + notificações + env chip | Sim, parcial | Search já existe; env chip e notificações reforçam contexto. | Notificações sem backend viram fake. Manter chip “env: prod”, posponer bell até existir feed. | Média |
| PageHeader com eyebrow (Workspace · ACME / Observabilidade) | Sim | Microcopy de ancoragem é vitória pura. | Nenhum. | Alta |
| Overview: attention strip + sugestões operacionais + cobertura por avaliação | Sim, gradualmente | Attention strip e suggestion row dão sentido operacional. Cobertura precisa de cálculo client-side ou novo endpoint. | Inventar métrica sem fonte = fingir. Cobertura por rubrica só com `evaluation_runs / traces`. | Alta (attention) / Média (cobertura) |
| Overview: 5 KPIs (inclui `avgScore`) | Sim, com fonte real | Hoje são 4 KPIs. Adicionar score médio depende do payload do overview já trazer média ou ser calculado. | Score médio sem fonte = mock. Não inventar. | Média |
| Traces: tab “RAG” + indicador score inline | Sim | Coerente com UI-RAG-1. Tab usa `isRagTrace` server-side. | Performance: pode exigir filtro server-side novo. Começar client-side com `limit`. | Alta |
| Traces: coluna “causa” (`schema_mismatch`, `vector_db_timeout`) | Sim, se backend já expõe | Alta densidade de sinal. | Se não vier do payload, é mock. Verificar `Trace.metadata` / `error_code`. | Média |
| Trace detail: tabs RAG/Waterfall/Metadata/Feedback | Não trocar estrutura | Hoje RAG é seção dedicada acima do waterfall, já testada. Tabs trariam churn sem ganho real. | Quebrar UI-RAG-1. | Não migrar |
| Trace detail: claim×chunk cross-table | Sim, quando dados existirem | Diferencial real do produto. | Já há `GroundingQualityCard` + `CitationRefsTable`. Avaliar se a matriz cross-table cabe sem duplicar. | Média (Fase futura) |
| Evaluations: DistBars + drawer YAML | Sim, parcial | DistBars já existe inline em `evaluations/page.tsx`; extrair como componente. Drawer YAML útil. | YAML inline pode vazar conteúdo de rubrica grande; controlar tamanho. | Média |
| Módulos secundários: placeholder “preview premium” | Sim, mas com cuidado | Visual coerente. Hoje cada módulo já tem `page.tsx` próprio com endpoints reais. NÃO substituir página real por placeholder. | Apagar funcionalidade existente. | Alta vigilância |
| Modal preview de endpoint + EndpointSnippet | Não migrar como produção | Útil em ambiente de dev/admin; em produção usuária causaria ruído. | Fingir ações reais. | Migrar só atrás de flag de dev |
| Atalhos `G + letra` | Sim | Já listados na sidebar real. Implementar handler global. | Conflito com input focus — preview já cuida disso. | Média |
| Toasts event-driven (`evo:toast`) | Sim | Útil p/ feedback de actions atuais (criar rubrica, key, etc). | Nenhum grande. | Média |
| Pulse SDK status (sidebar footer) | Já existe | `evo-pulse` está no `globals.css`. Manter. | — | — |
| Vinhetas radiais + grid 56px no body | Sim, suavemente | Atmosfera sem virar wallpaper. | Pesa em telas baixas; usar `mask-image` como o preview faz. | Baixa |

### 3.2 Pontos fortes

- Direção “cockpit” coerente com o estado atual do app real.
- Tokens em `:root` com nomenclatura compatível (`--bg-0`, `--text`,
  `--accent`, `--ok`, `--warn`, `--err`, `--eval`).
- Sidebar / topbar / page-header replicam estrutura já presente em
  `apps/web/components/Sidebar.tsx` e `EvoTopbar.tsx` — alinhamento real.
- Mapeamento de endpoints reais (`data.jsx → ENDPOINTS`) é
  documentação viva: serve como cross-check ao implementar actions.
- Padrão de “honestidade” (modal de preview p/ ações planejadas)
  alinhado com o `disabled data-status="planned"` já em uso.

### 3.3 Pontos fracos / riscos

- **Dados mock**: KPI `avgScore`, cobertura por avaliação, atenção
  ranqueada, “causa” por trace — vários requerem novo endpoint ou
  cálculo. Sem dado real, viram decoração. Risco de “Cockpit Potemkin”.
- **Estrutura diferente em Trace Detail**: o preview usa tabs (RAG /
  Waterfall / Metadata / Feedback). O app real hoje usa seções
  empilhadas com RAG cards no topo. Migrar a estrutura quebraria
  UI-RAG-1, testes e fixtures sem ganho mensurável.
- **Reset de tokens**: `oklch` é maravilhoso, porém o `globals.css`
  atual também serve a páginas marketing (landing, login, register,
  changelog). Trocar tokens globais agressivamente arrisca regressão
  visual em páginas públicas.
- **Modais de preview de endpoint**: confundem em produção (parece que
  algo aconteceu mas não aconteceu). Manter padrão atual de botões
  `disabled` com `title=` é mais honesto.
- **Hardcode de mocks** em `data.jsx` (KPIS, TRACES, RUBRICS,
  EVALUATIONS, MODULES) — JAMAIS migrar como fixtures de produção.
- **Cópia duplicada do diretório `preview/`** em duas profundidades
  diferentes dentro do ZIP — atenção para não confundir caminhos.

### 3.4 O que não deve ser migrado diretamente

- Arquivos `*.jsx` do preview (são React UMD/Babel standalone).
  Reescrever como TSX dentro de `apps/web/components/`.
- `data.jsx` inteiro — substituir por fetches reais via `lib/api.ts`.
- `EvalOps Preview.html` / `preview/index.html` — bootstrap não cabe
  no Next.js.
- `apps/web/components/*.tsx` do ZIP (são versões propostas, podem
  divergir do estado pós-UI-RAG-1). Comparar campo a campo antes,
  nunca sobrescrever.
- `docs/*.md` que vieram dentro do ZIP — são snapshots; usar como
  leitura, não substituir os reais.

---

## 4. Comparação com o app real

### 4.1 Áreas principais

| Área | App real hoje | Preview propõe | Diferença | Migração recomendada |
|---|---|---|---|---|
| App shell | `evo-shell` (sidebar 232px + main) | Idem (mesma grid) | Equivalente | Refinar tokens / atmosfera (P0) |
| Sidebar | Seções Projeto / Recursos / Operação, shortcuts | Idem + count em Traces + dot Keys + pulse SDK (idem) | Acréscimo: count + dot | P1: adicionar count + dot atenção (Keys próximas de expirar) |
| Topbar | Breadcrumbs + search → /traces + bell + docs + avatar logout | Crumbs + search com ⌘K + env chip + bell com dropdown + settings | Bell dropdown, env chip, ⌘K, search global real | P1: env chip + ⌘K hint. Dropdown só com backend de notificações |
| Overview | 4 KPIs + cost area + model breakdown + problem traces | 5 KPIs + cost area + model breakdown + attention strip + suggestion row + cobertura | Adiciona attention strip + suggestions + cobertura por avaliação | P3: attention strip (server-side ranqueado quando possível) + cobertura calculada client-side com dados existentes |
| Trace list | Tabs Todos/Erros/Parciais/Lentos + filtros + auto-refresh + cursor | Tabs + tab RAG + score inline + causa + filtros estendidos | Tab RAG, score inline, coluna causa | P2: adicionar tab RAG (filtra `isRagTrace`), score inline (de eval_runs), coluna causa (de metadata.error_code) |
| Trace detail | KPI grid (5) + RAG section + Waterfall + Metadata + Feedback rail | Mesmo conteúdo via tabs (RAG/Waterfall/Metadata/Feedback) | Estrutura: tabs vs seções empilhadas | NÃO migrar tabs. Manter seções, refinar visual. Adicionar AttentionBar quando `status != ok` |
| Cards RAG (UI-RAG-1) | `RAGSummaryHeader`, `AnswerPreviewCard`, `RetrievalSummaryCard`, `GroundingQualityCard`, `CitationRefsTable` | Mesmos cards + claim×chunk cross-table | Cross-table claim×chunk | Avaliar em fase futura (UI-RAG-2). Não regredir UI-RAG-1 |
| Evaluations | Summary cards + tabs Active/Runs/Paused + DistBars inline | Mesmo + drawer YAML + 4 KPI summary + custo de avaliação | Drawer YAML + custo card | P4: extrair `DistBars`, adicionar drawer YAML controlado, KPI custo só com fonte real |
| Prompts | `prompts/page.tsx` real, com `getPrompts`, action `createPromptAction` | Placeholder premium (counts + items + endpoints) | Real é mais completo | P5: NÃO trocar página real. Aplicar estilo cockpit ao header |
| Rubricas | `rubrics/page.tsx` real, `getRubrics`, `createRubricAction`, `createRubricVersionAction` | Placeholder premium | Real é mais completo | P5: NÃO trocar. Aplicar estilo cockpit |
| Datasets | `datasets/page.tsx` real, `getDatasets`, criar / itens / build from traces | Placeholder premium | Real é mais completo | P5: NÃO trocar. Aplicar estilo cockpit |
| Experimentos | `experiments/page.tsx` real, `getExperiments`, `createExperimentAction`, `runExperimentAction` | Placeholder premium | Real é mais completo | P5: NÃO trocar. Aplicar estilo cockpit |
| Chaves API | `keys/page.tsx` real, `getApiKeys`, `createApiKeyAction`, `revokeApiKeyAction` (com `error.tsx` + `loading.tsx`) | Placeholder premium + política de segurança | Real é mais completo, mas falta micro-copy de segurança | P5: NÃO trocar página. Adicionar copy de segurança (1 banner) |
| Exports | `exports/page.tsx` real + `api/exports/[exportId]/download` route + `getExports`/`createExport` | Placeholder premium | Real é mais completo | P5: NÃO trocar. Estilo cockpit no header |
| Endpoints reais | `lib/api.ts` (32+ funções) + `lib/actions.ts` (server actions) | Registry `ENDPOINTS` em `data.jsx` | Registry serve só como doc | Não migrar. Usar como check-list ao revisar P1–P5 |
| Design tokens | `globals.css` HEX (`#0a1024`, `#3b8df5`, etc.) + `--accent-cyan` | `:root` oklch + acento cobalt `#4F8CFF` | Espaço de cor diferente; nomes compatíveis | P0: introduzir oklch vars **alias** sem remover HEX, escopadas em `.evo-shell` para não afetar marketing |

### 4.2 Funcionalidades reais que precisam ser preservadas

| Funcionalidade real | Onde existe hoje | Como preview representa | Recomendação de preservação |
|---|---|---|---|
| Navegação `/o/[org]/p/[project]/...` | `Sidebar.tsx` + `EvoTopbar.tsx` + Next App Router | Sidebar análoga via hash router | Manter rotas reais. Sidebar nunca vira hash router |
| Links de módulos secundários reais | `prompts/`, `rubrics/`, `datasets/`, `experiments/`, `keys/`, `exports/` (todos com `page.tsx`) | Placeholders | NUNCA substituir `page.tsx` real por placeholder |
| Filtros de Traces server-side | `TracesFilterBar` + searchParams (`status`, `environment`, `name`, `tab`, `cursor`) | Filtros client-side | Manter server-side. Preview só inspira UX |
| Auto-refresh 30s em Traces | `TracesAutoRefresh` (pausado quando há cursor) | Texto “auto-refresh a cada 30s” | Manter como está; não trocar por websocket nem polling diferente |
| Paginação cursor | `next_cursor` em `TraceListResponse` | Não cobre | Preservar paginação atual |
| RAG cards no detalhe | `RAGSummaryHeader`, `AnswerPreviewCard`, `RetrievalSummaryCard`, `GroundingQualityCard`, `CitationRefsTable` | Tabs RAG diferente | Manter cards e seção atual. Tabs do preview = não migrar |
| `isRagTrace` toggle | `lib/rag.ts` decide se mostra seção | Sempre mostra para mock RAG | Não regredir |
| Form de feedback humano | `<form action={createTraceFeedbackAction}>` no detalhe | Não cobre (mostra lista) | Manter form server action |
| Botões “planned” disabled | Flag, Reexecutar, Comparar | Modal preview com EndpointSnippet | Manter `disabled data-status="planned"` (mais honesto que modal) |
| Server actions em todos os módulos | `actions.ts`: api-keys, rubricas, evals, prompts, datasets, experiments, exports, feedback | Tudo modalizado | Não trocar por modal-preview |
| Auth gating | `AuthRequiredPanel` em todas as `page.tsx` | Não cobre | Manter |
| Exports download via route handler | `api/exports/[exportId]/download/route.ts` | Não cobre | Manter |

---

## 5. Plano de migração em fases

Cada fase deve ser entregue por um plano de implementação dedicado.
Nenhuma fase abaixo está implementada por este documento.

### Fase P0 — Tokens visuais cockpit (foundational)

- **Objetivo**: introduzir variáveis cockpit (oklch + vinhetas radiais
  + grid sutil) **escopadas em `.evo-shell`** sem alterar tokens
  globais que servem páginas marketing.
- **Arquivos prováveis**:
  - `apps/web/app/globals.css` — adicionar bloco `.evo-shell { ... }`
    com `--bg-0`, `--accent-soft`, `--accent-rim`, `--border-subtle`
    (aliasing dos atuais HEX quando possível).
  - opcional: novo `apps/web/app/cockpit-tokens.css` importado só pelo
    layout do `/o/[org]/p/[project]`.
- **Riscos**: bandas de cor em wide-gamut; regressão em marketing se
  tokens escaparem do escopo.
- **Testes**: visual smoke (Overview + Traces + Trace detail) em
  Chromium + Firefox; verificar landing/login/changelog inalterados.
- **Critérios de aceite**:
  - Nenhuma regressão visual em rotas públicas.
  - Contraste de texto principal ≥ 4.5:1.
  - Atmosfera radial visível, sem virar wallpaper.
- **Precisa review antes de commit?** Sim, review obrigatório (mexe em
  CSS global compartilhado).

### Fase P1 — AppShell premium

- **Objetivo**: refinar `Sidebar` + `EvoTopbar` + breadcrumbs:
  - count opcional ao lado de “Traces”;
  - dot de atenção ao lado de “Chaves API” quando houver key próxima
    de expirar (só se backend já expõe — caso contrário, omitir);
  - env chip no topbar (`env: prod`);
  - `⌘K` hint no campo de busca;
  - eyebrow “Workspace · {org}” no PageHeader.
- **Arquivos prováveis**:
  - `apps/web/components/Sidebar.tsx`
  - `apps/web/components/EvoTopbar.tsx`
  - `apps/web/components/PageHeader.tsx` (extrair de
    `apps/web/app/o/[org]/p/[project]/page.tsx` se vier a ser reusado)
  - `apps/web/app/globals.css` (apenas adições escopadas)
- **Riscos**: rotas reais quebrarem; count exigir fetch extra;
  notificações virarem fake.
- **Testes**: navegação por todos os módulos secundários; verificar
  active state continua correto; sem chamadas extras quando count não
  está disponível.
- **Critérios de aceite**:
  - Todas as rotas reais continuam funcionando.
  - Nenhum módulo secundário sumiu da sidebar.
  - Topbar não introduz ação fake.
- **Precisa review antes de commit?** Sim.

### Fase P2 — Traces premium

- **Objetivo**: aplicar visual cockpit à lista de Traces e ao detalhe,
  **sem** mudar estrutura do detalhe (continua seções empilhadas, RAG
  no topo).
  - lista: tab “RAG” (`isRagTrace`), coluna score inline (a partir de
    `evaluation_runs` quando disponível), coluna causa (a partir de
    `metadata.error_code` quando existir), badge `rag` na linha;
  - detalhe: AttentionBar quando `status !== "ok"`, polimento de KPI
    grid, manter cards RAG inalterados, manter form de feedback.
- **Arquivos prováveis**:
  - `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
  - `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`
  - `apps/web/components/TracesFilterBar.tsx`
  - `apps/web/components/Sidebar.tsx` (badge `rag` se reusar)
  - eventualmente novo `apps/web/components/AttentionBar.tsx`
- **Riscos**: regredir UI-RAG-1; quebrar auto-refresh; tab RAG exigir
  filtro server-side novo (se necessário, abrir P2.5).
- **Testes**: rodar testes de RAG existentes em `apps/web/tests/`;
  verificar paginação e auto-refresh; verificar tab RAG filtra
  corretamente.
- **Critérios de aceite**:
  - UI-RAG-1 inalterada visualmente onde já está.
  - Auto-refresh e cursor funcionam.
  - Tab RAG abre sem erro mesmo com 0 traces RAG.
- **Precisa review antes de commit?** Sim, obrigatório (toca em
  área coberta por UI-RAG-1).

### Fase P3 — Overview premium

- **Objetivo**: evoluir Overview com:
  - AttentionStrip honesto (só quando há traces flagged reais);
  - SuggestionRow (próximos passos sugeridos) só com base em sinais
    reais já calculáveis no servidor (ex.: “1 experimento configurado
    sem rodar”);
  - cobertura por avaliação (cálculo client-side
    `evaluation_runs / traces` por rubrica no mesmo `environment`);
  - opcionalmente 5º KPI `avgScore` — só se o overview API já trouxer
    ou se for trivial calcular sem fetch extra.
- **Arquivos prováveis**:
  - `apps/web/app/o/[org]/p/[project]/page.tsx`
  - novo `apps/web/components/AttentionStrip.tsx`
  - novo `apps/web/components/SuggestionRow.tsx`
  - novo `apps/web/components/CoverageBars.tsx`
- **Riscos**: inventar métrica sem fonte; coverage sem dados =
  “Cockpit Potemkin”.
- **Testes**: snapshot do payload `getOverview`; estados vazios
  (zero traces, zero rubricas).
- **Critérios de aceite**:
  - Toda métrica exibida tem fonte real do payload ou do client-calc.
  - Empty states honestos (sem placeholder mock).
- **Precisa review antes de commit?** Sim.

### Fase P4 — Evaluations premium

- **Objetivo**: redesenhar lista/cards de avaliações:
  - summary cards (4 KPIs) com fontes reais (`runs7d`, `pass_rate`,
    `cost_usd` se vier do backend);
  - extrair `DistBars` em `apps/web/components/DistBars.tsx`;
  - drawer YAML para visualizar rubrica (read-only) usando
    `getRubricVersions`;
  - empty states / CTAs claros (“Criar rubrica”, “Rodar agora”).
- **Arquivos prováveis**:
  - `apps/web/app/o/[org]/p/[project]/evaluations/page.tsx`
  - `apps/web/components/DistBars.tsx`
  - novo `apps/web/components/RubricDrawer.tsx`
- **Riscos**: KPI `custo de avaliação` sem fonte real; vazar conteúdo
  longo de rubrica.
- **Testes**: rubrica grande, sem rubricas, sem runs.
- **Critérios de aceite**:
  - DistBars reutilizado, sem código inline.
  - Drawer YAML não quebra layout em rubricas grandes.
  - Endpoints reais (`getProjectEvaluations`, `getRubrics`,
    `triggerEvaluationAction`) preservados.
- **Precisa review antes de commit?** Sim.

### Fase P5 — Módulos secundários (estilo, não substituição)

- **Objetivo**: aplicar shell cockpit (PageHeader com eyebrow + cards)
  às páginas Prompts / Rubricas / Datasets / Experimentos / Chaves /
  Exports **sem** trocar a página real por placeholder. Adicionar
  apenas:
  - eyebrow “Recursos” / “Operação”;
  - subtitle descritiva;
  - placeholders premium **somente** onde já é parcial (ex.: criação
    de experimento marcada como `planned`).
- **Arquivos prováveis**: cada `page.tsx` dos módulos acima.
- **Riscos**: apagar funcionalidade existente; introduzir mock.
- **Testes**: smoke de cada módulo (listar, criar, revogar/publicar).
- **Critérios de aceite**:
  - Todas as actions reais continuam funcionando.
  - Nenhuma rota desaparece.
  - Placeholders só em fluxos já marcados como planned.
- **Precisa review antes de commit?** Sim.

### Fase P6 — UX polish

- **Objetivo**: loading/skeletons consistentes, error boundaries
  honestos, atalhos `G + letra` globais, responsividade notebook/mobile
  validada, microcopy revisada, acessibilidade auditada (foco visível,
  contraste, dupla codificação de status).
- **Arquivos prováveis**:
  - `apps/web/app/o/[org]/p/[project]/.../loading.tsx` e `.../error.tsx`
    (alguns já existem em datasets/exports/keys);
  - novo `apps/web/components/KeyboardShortcuts.tsx`;
  - `apps/web/app/globals.css` (apenas refinos).
- **Riscos**: conflito de atalhos com input focus; over-skeleton.
- **Testes**: lighthouse a11y; axe; navegação só com teclado.
- **Critérios de aceite**:
  - `G + letra` ignora foco em input/textarea/select.
  - Estados de carregamento padronizados.
  - Sem erros de contraste relevantes.
- **Precisa review antes de commit?** Sim.

---

## 6. Primeira implementação recomendada

### 6.1 Avaliação das opções

- **Opção A — Shell only (P0 + P1)**: baixo risco, ganho perceptível,
  mas isolado. Sem feedback de produto.
- **Opção B — Shell + Overview (P0 + P1 + P3)**: alto impacto visual
  (cockpit aparece em 5s), mas Overview tem mais decisões dependentes
  de fonte real (cobertura, attention, 5º KPI) — risco de inventar
  métrica.
- **Opção C — Shell + Traces (P0 + P1 + P2)**: cobre o fluxo real
  hoje (DocOps → EvalOps → trace RAG). UI-RAG-1 acabou de entrar e
  Traces é onde o time gasta tempo. Risco está bem mapeado (não mexer
  na estrutura do detalhe).

### 6.2 Recomendação

**Opção C — Shell + Traces (P0 + P1 + P2)**.

**Motivo**:
1. O fluxo de uso real hoje é **DocOps → EvalOps → traces RAG**, e o
   detalhe RAG é a entrega mais recente (`383dc21`). Investir polish
   exatamente onde a atenção está reforça a percepção de evolução.
2. P2 é a fase com mais risco regressivo (toca em UI-RAG-1). Atacar
   primeiro, com review obrigatório, garante que o restante do
   redesign não introduz divergência depois.
3. Overview (P3) depende de decisões de fonte de dados que ainda
   precisam ser discutidas (cobertura, attention ranqueado). Não
   bloquear o início do redesign por essa discussão.

**Arquivos prováveis tocados em C**:
- `apps/web/app/globals.css` (escopado em `.evo-shell`)
- `apps/web/components/Sidebar.tsx`
- `apps/web/components/EvoTopbar.tsx`
- `apps/web/app/o/[org]/p/[project]/layout.tsx` (sem mudança estrutural)
- `apps/web/app/o/[org]/p/[project]/page.tsx` (eyebrow + tokens, sem
  novos cards ainda)
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`
- `apps/web/components/TracesFilterBar.tsx`
- novo `apps/web/components/AttentionBar.tsx`
- novo `apps/web/components/PageHeader.tsx` (opcional, se reuso compensar)

**Critérios de aceite consolidados para C**:
- Tokens cockpit não vazam para rotas públicas.
- Sidebar mantém todas as rotas reais; nenhum módulo some.
- Topbar mantém logout / docs / search; bell sem dropdown fake.
- Lista de Traces: nova tab RAG aparece e filtra corretamente
  (mesmo com zero RAG).
- Detalhe de Trace: RAG cards UI-RAG-1 inalterados; AttentionBar só
  quando `status !== "ok"`.
- Auto-refresh e paginação por cursor preservados.
- Form de feedback humano continua funcionando.
- Testes RAG existentes em `apps/web/tests/` permanecem verdes.
- Botões “planned” continuam `disabled` (sem modal preview).

---

## 7. Riscos transversais

- **Cockpit Potemkin**: cada métrica nova exige fonte real. Sem fonte,
  omitir.
- **Token leakage**: alterações em `:root` afetam landing/login/docs.
  Escope toda mudança nova em `.evo-shell` ou em arquivo CSS dedicado
  importado só pelo layout autenticado.
- **UI-RAG-1 regression**: trace detail tem cards já testados.
  Qualquer toque em `[trace]/page.tsx` exige rodar a suíte de RAG.
- **Mock contamination**: nenhum valor de `data.jsx` do preview pode
  acabar em `lib/`, em `tests/fixtures/`, ou em qualquer página real.
- **Action surface**: server actions em `actions.ts` são o ponto de
  contato com backend; nenhum botão deve passar a abrir “modal
  preview” em vez de chamar a action real.
- **Caminho do ZIP duplicado**: o ZIP contém `evalops-preview/` e
  também `preview/` na raiz. Tratar apenas `evalops-preview/` como
  canônico em revisões futuras.

---

## 8. Critérios de aceite globais do plano

Este documento (não a implementação) está completo quando:

- [x] ZIP foi extraído fora do repo (`/tmp/evalops-preview-audit/`).
- [x] README + DESIGN_NOTES do ZIP lidos integralmente.
- [x] Estrutura do preview mapeada.
- [x] Frontend real mapeado (rotas, sidebar, topbar, RAG cards, api).
- [x] Tabelas de diagnóstico e comparação preenchidas.
- [x] Funcionalidades reais a preservar listadas.
- [x] Plano em fases P0–P6 com objetivo, arquivos, riscos, testes,
      critérios de aceite e necessidade de review.
- [x] Primeira fase recomendada com justificativa.
- [x] Documento criado em `docs/plans/`.
- [x] Nenhum arquivo do ZIP foi copiado para `apps/web/`.
- [x] Nenhum commit / push / `git add` feito.

---

## 9. Próximo prompt sugerido (NÃO executar agora)

> Implementar **Fase P0 + P1 + P2** descritas em
> `docs/plans/evalops-premium-preview-migration-plan.md`
> (Shell cockpit + Traces premium), preservando UI-RAG-1.
>
> Restrições:
> - Não alterar backend, schema, migrations, SDK ou deploy.
> - Não tocar Oracle VM.
> - Não usar mocks do ZIP; toda métrica precisa de fonte real.
> - Tokens cockpit devem ser **escopados em `.evo-shell`** para não
>   afetar páginas públicas (landing/login/changelog/docs).
> - Tab “RAG” na lista de Traces deve aparecer mesmo com zero traces
>   RAG (sem erro).
> - Não mudar estrutura do trace detail (continua seções empilhadas,
>   cards RAG no topo).
> - Manter botões “planned” como `disabled data-status="planned"`,
>   não trocar por modal-preview.
> - Rodar testes RAG existentes em `apps/web/tests/` antes de
>   considerar concluída a fase P2.
> - Criar plano de implementação dedicado antes de editar código.
