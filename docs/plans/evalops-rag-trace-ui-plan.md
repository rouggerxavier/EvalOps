# EvalOps — Plano de melhoria de UI para traces RAG ricos

Status: planejamento docs-only. Nenhuma alteração de código, backend, SDK,
schema, migrations ou deploy é proposta aqui. Implementação fica para fases
futuras (UI-RAG-1, UI-RAG-2, UI-RAG-3), cada uma a ser executada via plano
de implementação próprio.

Data: 2026-05-20.
Repo: `/home/rouggerxavier/dev/evalops`.
Branch base: `main`.
HEAD na auditoria: `e74b9e8`.

---

## 1. Contexto

EvalOps é um observability/eval layer genérico para aplicações de IA. Já
recebe e persiste traces ricos via o contrato definido em
`docs/08-tracing-and-events-spec.md`, incluindo a convenção opcional de
RAG documentada em `§9 — Recommended RAG trace convention` (spans
`rag.retrieve`, `rag.context.build`, `llm.generate`,
`rag.grounding.validate`, `response.finalize`, mais payloads e eventos
sugeridos).

Em dogfood real um app RAG externo (DocOps) começou a emitir traces que
seguem essa convenção. EvalOps **armazena e expõe** todos os campos
corretamente via API (ver §3), mas a UI de detalhe de trace ainda
renderiza a maior parte do conteúdo RAG como JSON cru, sem destacar
respostas, citações, grounding ou qualidade.

DocOps é tratado neste plano apenas como **fixture de contrato RAG
genérico**. O EvalOps deve continuar agnóstico para qualquer pipeline
RAG (LangChain, LlamaIndex, custom) que adote a convenção §9. Nenhuma
referência hardcoded a DocOps deve aparecer no produto.

Objetivo deste plano:

1. Mapear como a UI atual renderiza o detalhe de um trace.
2. Identificar quais dados RAG já chegam no payload mas estão escondidos
   em JSON cru.
3. Propor uma sequência de fases incrementais (UI-RAG-1/2/3) para evoluir
   a UI sem mudar contrato, backend, SDK ou schema.

---

## 2. Diagnóstico da UI atual

Arquivos auditados (somente leitura):

- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx` — página de
  detalhe do trace.
- `apps/web/components/SpanWaterfall.tsx` — waterfall + painel de span
  selecionado.
- `apps/web/lib/types.ts` — `Trace`, `TraceSpan`, `TraceDetailResponse`.
- `apps/web/lib/api.ts` — `getTrace(traceId)` → `GET /traces/:id`.
- `apps/api/app/api/routes.py` — `GET /traces/{trace_id}` (linhas
  229–300), retorna `{ trace, spans, events_count, feedback }`.

O que a página de detalhe entrega hoje:

- **Header**: nome, status, environment, `redacted`, id do trace,
  `service`, `created_at`, `user_ref`.
- **Botões Flagear / Reexecutar / Comparar**: presentes no DOM mas
  `disabled` com `data-status="planned"` e tooltip "em breve" — são
  placeholders. Nenhum endpoint conectado.
- **KPI grid (5 colunas)**: duração, tokens entrada, tokens saída,
  custo, spans/eventos. Tokens e custo vêm de
  `t.total_tokens_in/out/total_cost_usd`, que ficam 0 quando o emissor
  não envia `tokens_*`/`cost_usd` por span.
- **Waterfall** (`SpanWaterfall`): renderiza árvore de spans com chip de
  tipo (`llm`/`retrieval`/`tool`/`function`/`root`/`default`) e barras
  proporcionais. Ao selecionar um span, mostra:
  - subtítulo: type · provider · model · duração · tokens.
  - cartão "Input" e cartão "Output/Erro": ambos renderizam `input`,
    `output` ou `error` direto como `JSON.stringify(value, null, 2)`
    dentro de `<pre>` (componente local `JsonView`).
  - **Eventos do span não são renderizados** (o componente ignora
    `span.events` mesmo o tipo TS já incluir).
- **Metadata do trace**: renderizada como `<pre>JSON.stringify(t.metadata, null, 2)</pre>`
  num cartão, sem destaque para chaves RAG (`citation_count`,
  `grounding_ok`, `quality_level`, `quality_score`, `pipeline_version`,
  `model`).
- **Rail de feedback humano**: form + histórico funcionais.

Onde os dados RAG ricos aparecem hoje:

| Dado RAG | Onde aparece na UI atual |
|---|---|
| `metadata.pipeline_version`, `metadata.model`, `metadata.citation_count`, `metadata.grounding_ok`, `metadata.quality_level`, `metadata.quality_score` | Cartão "Metadata do trace" como JSON cru |
| `rag.retrieve.output` (retrieved_count, doc_refs, chunk_refs, scores, truncated, limit, total_available) | "Output" do span `rag.retrieve` como JSON cru |
| `rag.grounding.validate.output` (citation_refs, grounding_ok, quality_*, retry_count, repair_count, unsupported_claim_count) | "Output" do span `rag.grounding.validate` como JSON cru |
| `response.finalize.output.answer_preview`, `has_answer`, `source_count` | "Output" do span `response.finalize` como JSON cru |
| `events` por span | Não renderizado |
| Latência por etapa | Apenas barra no waterfall; nenhum sumário |
| Tokens / cost | KPI mostra zero se emissor não envia `tokens_*` |

Resumo da dor: o backend já entrega tudo; o gargalo é puramente
**visual/produto**.

---

## 3. Dados RAG disponíveis hoje no payload

Confirmado lendo `routes.py:229–300` e `lib/types.ts`. Todos os campos
abaixo já chegam no `TraceDetailResponse` quando o emissor segue a
convenção §9 de `docs/08-tracing-and-events-spec.md`.

- `trace.metadata`: livre — recebe rollups RAG (`pipeline_version`,
  `model`, `retrieved_count`, `citation_count`, `grounding_ok`,
  `quality_level`, `quality_score`, `strict_grounding`, `has_answer`).
- `trace.tags`, `trace.environment`, `trace.service`, `trace.status`,
  `trace.duration_ms`: já formatados.
- `spans[].type` / `name`: `retrieval`, `tool_call`, `chain`,
  `llm_call`; `name` segue convenção (`rag.retrieve`,
  `rag.grounding.validate`, `response.finalize`, `llm.generate`,
  `rag.context.build`).
- `spans[].input` / `spans[].output` / `spans[].metadata` / `spans[].error`:
  JSON livre — carregam todos os campos D0/D1/D2 (chunk_refs, doc_refs,
  scores, truncated, citation_refs, grounding_ok, quality_*,
  unsupported_claim_count, answer_preview, has_answer, source_count,
  retry_count, repair_count, strict_grounding).
- `spans[].provider` / `model` / `tokens_in` / `tokens_out` /
  `cost_usd`: top-level, opcionais.
- `spans[].messages_in` / `messages_out` / `tools` /
  `prompt_version_ref` / `fallback_from_span_id`: **retornados pelo
  backend** (ver `routes.py:257–263`) mas **ausentes no tipo TS**
  `TraceSpan` em `apps/web/lib/types.ts:37–62`. UI ignora hoje.
- `spans[].events`: já no tipo TS, retornados pelo backend, mas
  `SpanWaterfall` não renderiza.
- `events_count` no topo do payload.
- `feedback`: lista de `HumanFeedback`.

Conclusão importante: **nenhuma mudança de backend, schema ou SDK é
necessária para UI-RAG-1 e UI-RAG-2**. UI-RAG-3 pode exigir novos
endpoints (replay, compare, dataset-from-trace), tratados separadamente.

---

## 4. Tabela RAG — dado × payload × UI hoje × problema × componente alvo

| Dado RAG | Está no payload? | UI mostra hoje? | Problema UX | Melhor componente alvo |
|---|---|---|---|---|
| `answer_preview` | sim (`response.finalize.output` ou rollup em metadata) | dentro de JSON cru do span output | Resposta é o dado mais valioso e fica escondida em `<pre>` | `AnswerPreviewCard` |
| `model` | sim (`trace.metadata.model` e/ou top-level do span `llm.generate`) | em JSON cru | Sem identificação visual; difícil filtrar mentalmente | Chip no `RAGSummaryHeader` |
| `pipeline_version` | sim (`trace.metadata.pipeline_version`) | em JSON cru | Versão do pipeline invisível p/ análise temporal | Chip no `RAGSummaryHeader` |
| `retrieved_count` | sim (rag.retrieve.output + rollup metadata) | em JSON cru | Sem leitura rápida da recall | KPI compacto no `RetrievalSummaryCard` |
| `doc_refs` | sim (rag.retrieve.output) | em JSON cru | Hashes sem agrupamento por documento | Lista deduplicada no `RetrievalSummaryCard` |
| `chunk_refs` | sim (rag.retrieve.output) | em JSON cru | Lista longa de hashes ilegível | Tabela colapsável + count badge |
| `limit` / `total_available` / `truncated` | sim | em JSON cru | Truncamento invisível, gera dúvida sobre recall | Badge "truncado" + texto contextual |
| `scores.retrieval_mode` | sim | em JSON cru | Modo (dense/hybrid/bm25) escondido | Tag pequena no `RetrievalSummaryCard` |
| `citation_count` | sim (rollup metadata + grounding.validate output) | em JSON cru | Indicador-chave de qualidade RAG perdido | KPI no `GroundingQualityCard` |
| `citation_refs` (fonte_n, chunk_ref, doc_ref) | sim (grounding.validate.output) | em JSON cru | Vínculo resposta↔fonte invisível | `CitationRefsCard/Table` |
| `grounding_ok` | sim | em JSON cru | Booleano-chave de aceitação não é destacado | Badge ok/falha no `GroundingQualityCard` |
| `quality_level` (low/medium/high) | sim | em JSON cru | Selo de qualidade não visível | Badge colorido no header e card |
| `quality_score` | sim | em JSON cru | Score numérico não comparável de relance | Métrica no `GroundingQualityCard` |
| `quality_reason_codes` | sim (array) | em JSON cru | Motivos não escaneáveis | Badges no `GroundingQualityCard` |
| `quality_components` | sim (objeto) | em JSON cru | Componentes do score escondidos | Mini barra/lista compacta |
| `retry_count` / `repair_count` | sim (grounding.validate.output) | em JSON cru | Custo escondido de retries de grounding | Métricas secundárias |
| `unsupported_claim_count` | sim | em JSON cru | Sinal forte de risco escondido | Métrica/aviso no `GroundingQualityCard` |
| `tokens_*` / `cost_usd` | sim quando enviados | KPI mostra zero | Confunde quando emissor ainda não captura `usage` | KPI já existe + nota "não enviado" |
| `events` por span | sim no payload | não renderizado | Eventos como `retrieval.empty`, `grounding.failed` ignorados | Timeline pequena dentro do painel de span |
| Latência por etapa | sim (barra no waterfall) | só visual no waterfall | Soma e gargalo por etapa não resumidos | Pequeno sumário no `RAGSummaryHeader` ou tooltips |

Campos do span retornados pelo backend mas ausentes no tipo TS
(`messages_in`, `messages_out`, `tools`, `prompt_version_ref`,
`fallback_from_span_id`): considerar incluir no tipo durante UI-RAG-1
para alimentar cards e abrir uso futuro. Mudança limitada a
`apps/web/lib/types.ts`.

---

## 5. Diagnóstico — o que funciona, o que falha, gaps

### 5.1 Já funciona

- Listagem e auto-refresh de traces (`traces/page.tsx` +
  `traces-auto-refresh.tsx`).
- Endpoint `GET /traces/:id` traz spans, eventos contados, feedback.
- Waterfall calcula offset/width a partir de `started_at` e
  `duration_ms` corretamente (`SpanWaterfall.tsx:44`).
- Status, environment, redacted, user_ref já tratados no header.
- Feedback humano (form + histórico) funcional e conectado a action
  real.
- Estilo (cards, badges, KPI grid) já segue o design system novo
  (`evo-card`, `evo-kpi-grid`, `evo-badge`).

### 5.2 Funciona, mas crua/difícil

- `trace.metadata` é um único `<pre>` rolando até 240px — perfeito para
  debug, péssimo para storytelling RAG.
- `span.input`/`span.output` no painel selecionado são renderizados em
  `<pre>` (`SpanWaterfall.tsx:56–67`) sem destacar `answer_preview`,
  `citation_refs`, `quality_*` etc.
- Sem botão de copiar JSON; sem colapsar; sem busca dentro do JSON.
- Tabs ou sumário "Overview vs Spans vs Raw" não existem: tudo na
  mesma tela.
- KPI tokens/cost = 0 sem nenhuma anotação de "não enviado pelo
  emissor".
- Botões Flagear / Reexecutar / Comparar ocupam espaço visual de ação
  primária mas são placeholders confessos.

### 5.3 Tem no payload e não aparece

- `span.events` — ignorado pelo waterfall.
- `messages_in`/`messages_out`/`tools`/`prompt_version_ref` —
  retornados pelo backend, fora do tipo TS, ignorados pela UI.
- Rollups RAG no `trace.metadata` (citation_count, grounding_ok,
  quality_level, quality_score) — só aparecem como linhas em JSON.

### 5.4 Depende de backend/API?

- UI-RAG-1: **não**. Backend entrega tudo. Mudanças só em
  `apps/web/lib/types.ts` (opcional, para tipar campos extras) e em
  `apps/web/components/*` + `apps/web/app/o/.../traces/[trace]/page.tsx`.
- UI-RAG-2: **não**, é polish e UX.
- UI-RAG-3: **sim**, exige endpoints novos (replay, compare,
  dataset-from-trace, flag persistente). Fora do escopo deste plano,
  apenas referenciado como direção.

### 5.5 Genérico, não hardcoded para DocOps

- Cards devem ler campos pela convenção §9, com **detecção
  defensiva**: se o span/campo não existir, o card simplesmente não
  renderiza (degrada com gracioso).
- Nada de string `"docops"` no produto. DocOps entra apenas como
  fixture em `apps/web/tests/fixtures/` e como exemplo em
  `docs/examples/` se ainda não houver.
- Se nenhum span RAG for detectado, a UI mantém comportamento
  atual (waterfall + cartões genéricos) — fallback obrigatório.

---

## 6. Proposta — fases incrementais

### Fase UI-RAG-1 — Cards RAG no trace detail (frontend-only)

Objetivo: destacar os dados RAG mais valiosos sem mudar nada de
backend.

Escopo de componentes novos (sugeridos em `apps/web/components/`):

- `RAGSummaryHeader.tsx`
  - Chips: `model`, `pipeline_version`, `quality_level`,
    `quality_score`, `citation_count`, `retrieved_count`,
    `grounding_ok`.
  - Aparece **só** se a heurística detectar trace RAG (presença de
    span com `name` em `{rag.retrieve, rag.grounding.validate,
    response.finalize}` ou rollups em `trace.metadata`).
- `AnswerPreviewCard.tsx`
  - Lê `response.finalize.output.answer_preview` (fallback:
    rollup em metadata).
  - Mostra `has_answer`, `source_count`.
  - Badge "truncado" se houver flag `_truncated=true` em metadata do
    span ou no preview.
  - Botão "Copiar preview".
- `RetrievalSummaryCard.tsx`
  - Lê `rag.retrieve.output`.
  - KPIs compactos: `retrieved_count`, `limit`, `total_available`,
    `truncated`, `scores.retrieval_mode`.
  - Tabela colapsável de `chunk_refs` (hash curto + score) e
    `doc_refs` deduplicados (hash curto + contagem de chunks).
- `GroundingQualityCard.tsx`
  - Lê `rag.grounding.validate.output` com fallback para
    `trace.metadata`.
  - Badge `grounding_ok`, badge `quality_level`, numérico
    `quality_score`.
  - Métricas secundárias: `unsupported_claim_count`, `retry_count`,
    `repair_count`, `strict_grounding`.
  - Lista de `quality_reason_codes` como badges.
  - Render compacto de `quality_components` (chave → score 0..1, mini
    barra).
- `CitationRefsTable.tsx`
  - Lê `citation_refs`.
  - Colunas: `fonte_n`, `chunk_ref` (truncado), `doc_ref` (truncado).
  - Nada de conteúdo bruto.
- Helper `lib/rag.ts` (sugerido)
  - `isRAGTrace(detail)` — heurística baseada em nomes de spans + chaves
    em metadata.
  - `findSpan(detail, name)` — utilitário.
  - `safeGet(obj, path)` — leitura defensiva.

Arquivos prováveis a tocar:

- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx` (montagem
  dos cards quando `isRAGTrace(detail)`).
- `apps/web/components/RAGSummaryHeader.tsx` (novo).
- `apps/web/components/AnswerPreviewCard.tsx` (novo).
- `apps/web/components/RetrievalSummaryCard.tsx` (novo).
- `apps/web/components/GroundingQualityCard.tsx` (novo).
- `apps/web/components/CitationRefsTable.tsx` (novo).
- `apps/web/lib/rag.ts` (novo, ~80 linhas).
- `apps/web/lib/types.ts` (opcional: estender `TraceSpan` com
  `messages_in`, `messages_out`, `tools`, `prompt_version_ref`,
  `fallback_from_span_id`).
- `apps/web/app/globals.css` ou módulo CSS dedicado: tokens p/ chips
  novos (quality low/medium/high), se necessário.

Complexidade: **média-baixa**. Cinco componentes pequenos, todos lendo
JSON existente. Sem lógica nova de fetching.

Risco: **baixo**.
- Risco: ler caminho que não existe e quebrar — mitigado por
  `safeGet`/`isRAGTrace`.
- Risco: poluição visual quando trace não-RAG — mitigado por
  fallback (nada renderiza).
- Risco: regressão em trace detail genérico — mitigado por testes
  source-level com fixture não-RAG.

Testes (a serem escritos durante a implementação, não agora):

- Fixture genérica `apps/web/tests/fixtures/rag-trace.json` (basear
  no exemplo real DocOps anonimizado).
- Fixture `non-rag-trace.json`.
- Fixture `rag-trace-truncated.json` (truncated=true).
- Fixture `rag-trace-no-grounding.json` (D0/D1 sem
  rag.grounding.validate).
- Fixture `rag-trace-zero-tokens.json`.
- Testes source-level em `apps/web/tests/` (Node script ou Vitest
  conforme padrão local): asserir que cada card renderiza/oculta
  corretamente e que JSON cru deixou de aparecer para os campos
  cobertos.

Critérios de aceite UI-RAG-1:

- Trace RAG com fixture canônica D2 mostra: header com chips,
  AnswerPreviewCard com preview legível, RetrievalSummaryCard com
  contagens, GroundingQualityCard com badges, CitationRefsTable com
  fonte_n/chunk_ref/doc_ref.
- Trace sem campos RAG não mostra nenhum dos novos cards (fallback).
- `trace.metadata` JSON cru continua disponível em algum lugar
  (cartão atual ou aba "Raw"), sem perda de informação.
- Nenhuma referência hardcoded a DocOps em código.
- Build TS sem novos erros.
- Sem mudança em backend, SDK, schema, migrations, Docker, VM,
  deploy.

### Fase UI-RAG-2 — Polish UX

Objetivo: levar a UX de trace detail a um padrão profissional, ainda
sem novos endpoints.

Itens:

- **Tabs no detalhe**: `Overview` (header + cards RAG + waterfall) /
  `Spans` (waterfall + painel) / `Raw JSON` (trace.metadata +
  span.metadata + span.input/output sob `<pre>` colapsáveis).
- **JsonView reutilizável** (`apps/web/components/JsonView.tsx`):
  colapsável por nó, botão copiar, busca; substitui o `JsonView` local
  do `SpanWaterfall` e o `<pre>` do `[trace]/page.tsx`.
- **Truncamento controlado** no JsonView: cortar arrays > N itens com
  expand.
- **CopyButton genérico** (já existe `CopyTextButton.tsx` —
  generalizar para JSON / valor primitivo).
- **Eventos por span**: renderizar `span.events` como timeline pequena
  dentro do painel de span (tipo + occurred_at + payload colapsável).
- **Empty states**:
  - "Nenhum span capturado" (já existe; revisar copy).
  - "Sem rollups RAG neste trace" no header quando não-RAG.
  - "Tokens/cost = 0 — emissor não enviou `usage`" no KPI quando
    aplicável.
  - "Latência por etapa em 0ms — emissor ainda não instrumenta tempo
    por sub-etapa" quando span.duration_ms = 0.
- **Badges de status** unificados em `evo-badge` (já parcial).
- **Densidade**: revisar gap entre cards para evitar empilhamento
  vertical longo em desktop.

Arquivos prováveis:

- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx` (tabs +
  empty states + montagem condicional).
- `apps/web/components/SpanWaterfall.tsx` (renderizar events; usar
  JsonView novo).
- `apps/web/components/JsonView.tsx` (novo, substitui local).
- `apps/web/components/CopyTextButton.tsx` (estender).
- CSS: tabs, empty states, timeline de events.

Complexidade: **média**. Tabs alteram layout principal; JsonView
reutilizável merece testes.

Risco: **médio**.
- Risco: tabs quebrarem fluxo de leitura linear — mitigar com
  default em "Overview" e atalho de teclado.
- Risco: regressão em traces antigos ao trocar render JSON —
  mitigar mantendo aba "Raw JSON" 1:1 com payload.

Testes:

- Source-level por componente JsonView (copy, colapso, busca).
- Fixture com `events` populados.
- Fixture com tokens/cost zero.
- Snapshot light de cada tab.

Critérios de aceite UI-RAG-2:

- Tabs Overview/Spans/Raw funcionam e preservam acesso ao JSON.
- Copy button funciona em qualquer nó.
- `span.events` aparece quando presente.
- Empty states explicam a causa, não escondem o dado.

### Fase UI-RAG-3 — Produto (cross-cutting, exige backend)

Objetivo: transformar trace rico em ação de avaliação/dataset/regressão.

Itens (cada um merece plano próprio antes de execução):

- **Create dataset item from trace**: botão em trace detail abre
  modal que mapeia `rag.retrieve.input.query` → `input`,
  `response.finalize.output.answer_preview` → `expected_output` (ou
  vazio), com seleção de dataset destino. Backend: estender
  `POST /datasets/{id}/items` ou novo `POST /datasets/{id}/items/from-trace`.
- **Flag manual com motivo**: substituir botão Flagear placeholder.
  Backend: armazenar flag/tag no trace (campo dedicado ou
  `trace.tags.flag.*`).
- **Compare traces**: selecionar 2 traces e renderizar diff side-by-side
  de KPIs + cards RAG. Pode ser frontend-only inicialmente.
- **Reexecutar trace**: requer hook no app emissor (não trivial,
  fora do contrato atual do EvalOps). Possivelmente substituído por
  "criar experimento a partir desta trace".
- **Evaluator/Rubric RAG nativo**: usar `quality_*`, `grounding_ok`,
  `citation_count` para alimentar evaluators automáticos via
  `evaluation-engine`. Backend.

Complexidade: **alta**. Cada item é um épico.
Risco: **médio-alto**, dependente do backend.
Critérios de aceite: definidos no plano específico de cada item.

Arquivos prováveis (apenas direção, não exaustivo):

- `apps/api/app/api/routes.py`, `routes_evaluations.py`, novo
  `routes_traces_actions.py`.
- `apps/api/app/domain/services/` (novos services).
- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`
  (ativar botões).
- `apps/web/lib/api.ts` (novos clients).
- `packages/sdk-python` — provavelmente não precisa mudar.

---

## 7. Lente UI/UX Pro Max

### 7.1 Layout desktop

- Manter grid principal: Header → KPI grid → (RAG header opcional) →
  Cards RAG em duas colunas (Answer + Retrieval à esquerda; Grounding
  + Citations à direita) → Waterfall → Bottom grid.
- Limite de largura: cards RAG não devem competir com waterfall em
  largura; preferir grade 2x2 acima do waterfall.

### 7.2 Mobile

- Cards RAG empilham verticalmente.
- Waterfall: scroll horizontal pré-existente em telas estreitas.
- Tabela de citation_refs colapsa para lista compacta.

### 7.3 Densidade

- Header já está denso; chips RAG devem ser pequenos (height 20px,
  fonte 11px).
- Cards RAG: padding interno consistente com `evo-card__body`.

### 7.4 Hierarquia visual

- Primeira fixação visual: AnswerPreviewCard (resposta é o produto).
- Segunda: GroundingQualityCard (qualidade da resposta).
- Terceira: RetrievalSummaryCard / Citations (origem da resposta).
- Waterfall fica abaixo, como detalhe técnico.

### 7.5 Legibilidade de refs/hash

- Sempre truncar hashes longos (mostrar primeiros 8 chars + "…")
  com tooltip do valor completo + copy.
- Nunca colocar hash inteiro no meio de uma frase descritiva.

### 7.6 Poluição visual

- Detecção `isRAGTrace` é o filtro principal: se falso, **nada novo
  aparece**. Trace genérico continua igual.
- Para traces parciais (só D0/D1, sem grounding), só os cards
  aplicáveis renderizam.

### 7.7 Fallback para não-RAG

- Obrigatório: nenhum componente RAG quebra ou ocupa espaço quando os
  campos não existem.
- Trace clássico (chamada LLM única, sem retrieval) → UI atual,
  inalterada.

### 7.8 JSON útil ≠ UI confusa

- Regra prática: para cada campo RAG promovido a card, **remover o
  mesmo dado do JSON cru visível por padrão** seria UX hostil para
  debug. Solução: manter JSON cru disponível em aba "Raw" (UI-RAG-2),
  não na tela principal.

---

## 8. Testes recomendados (futuros)

Quando UI-RAG-1 for implementado, criar:

- `apps/web/tests/fixtures/rag-trace.json` — fixture canônica D2
  (anonimizada do DocOps).
- `apps/web/tests/fixtures/rag-trace-d1.json` — D0+D1, sem
  rag.grounding.validate.
- `apps/web/tests/fixtures/rag-trace-truncated.json` — truncated=true,
  total_available > limit.
- `apps/web/tests/fixtures/rag-trace-zero-tokens.json` — tokens/cost
  ausentes ou zero.
- `apps/web/tests/fixtures/non-rag-trace.json` — chamada LLM simples.
- Testes em `apps/web/tests/` (Node test runner / Vitest conforme
  padrão local) por card:
  - render condicional via `isRAGTrace`.
  - render correto de `answer_preview`, contagens, badges.
  - oculta cards quando dados ausentes.
  - sem string "docops" no DOM (regression guard).
- Build/test já existentes (`apps/web/tests/security.test.mjs`) devem
  continuar passando.

Para UI-RAG-2:

- Snapshot por tab (Overview/Spans/Raw).
- Eventos por span renderizados na timeline.
- Copy button confirma `navigator.clipboard.writeText` chamado com
  valor esperado.

Para UI-RAG-3: testes definidos por épico.

Nenhum teste deve ser rodado nesta fase de auditoria.

---

## 9. Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Cards RAG acoplam ao formato de payload do DocOps | média | alto (perde genericidade) | Ler somente chaves da convenção §9; sem string DocOps em código; fixtures como contrato. |
| Detecção `isRAGTrace` retorna falso positivo em pipelines não-RAG | baixa | médio | Heurística baseada em **dois sinais** (nome de span + rollup metadata) com AND/OR explicitado e testado. |
| Aba "Raw JSON" se tornar lixeira difícil de auditar | média | médio | Manter `<pre>` linear com copy, sem perder fidelidade ao payload. |
| Tokens/cost zero confundem usuário | alta | médio | Anotação explícita "emissor não enviou `usage`" em UI-RAG-2. |
| Render de `messages_in/out` muito grande quebra layout | média | médio | Truncar em UI-RAG-2 (≥256 chars → collapse). |
| Componentes novos quebram tema dark/light | baixa | médio | Usar apenas tokens CSS existentes (`--text`, `--text-muted`, `--accent`, etc.). |
| Plano UI-RAG-3 escorrega para UI-RAG-1/2 e expande escopo | média | alto | Cada item de UI-RAG-3 só entra com plano próprio (architecture-decision / implementation-planner). |

---

## 10. Próximos passos

1. **Recomendado**: implementar UI-RAG-1 como próxima entrega.
   Frontend-only, baixo risco, alto valor visual, sem dependência de
   backend/SDK.
2. Antes da implementação:
   - Capturar 1–2 fixtures reais do dogfood (DocOps) **anonimizadas**
     (hashes opacos, sem PII) e versionar como contrato de teste.
   - Confirmar que a convenção §9 cobre todos os campos da fixture
     (caso falte algo, atualizar §9 antes — sem mudar schema).
3. Em sequência: UI-RAG-2 (UX polish).
4. UI-RAG-3 entra na roadmap de produto pós-MVP, com plano próprio
   por épico (dataset-from-trace, flag persistente, compare, replay,
   evaluator RAG nativo).

---

## 11. Não objetivos

- Não implementar nada agora.
- Não mudar backend, SDK, schema, migrations, deploy.
- Não rodar Docker/VM.
- Não hardcodar DocOps.
- Não criar feature flag específica para DocOps.
- Não bloquear ingestão de traces que não seguem §9.

---

## 12. Referências

- `docs/08-tracing-and-events-spec.md` (§9 — Recommended RAG trace
  convention).
- `docs/audits/evalops-current-state-audit-2026-05-19.md` — estado
  atual do produto e Phase 7.
- `docs/frontend-audit.md` — snapshot frontend (histórico).
- `docs/design-refactor-plan.md` — backlog de design.
- Código auditado:
  - `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`
  - `apps/web/components/SpanWaterfall.tsx`
  - `apps/web/lib/types.ts`
  - `apps/web/lib/api.ts`
  - `apps/api/app/api/routes.py` (endpoint `GET /traces/{trace_id}`)
