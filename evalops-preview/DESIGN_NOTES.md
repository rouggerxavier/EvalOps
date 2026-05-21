# EvalOps Studio — Design Notes (preview interno)

> Este documento explica a direção visual adotada, o que entrou no redesign
> inicial, o que ficou de fora, e como portar para o app real
> (`apps/web/` em `rouggerxavier/EvalOps`).

---

## 1. Direção visual

**Conceito-âncora: cockpit de observabilidade.**

Não é mais um "dashboard SaaS dark". É um console operacional para times
técnicos que precisam saber, em 5 segundos, se o app de IA está saudável,
quais traces merecem atenção, e qual ação tomar. A interface deve transmitir
calma sob pressão.

### Tokens principais

- **Base**: navy-slate frio em oklch. `--bg-0: oklch(0.145 0.012 250)`.
  Saturação intencionalmente baixa (< 0.02) para que os badges semânticos
  sobressaiam.
- **Acento único**: cobalto `#4F8CFF` — o mesmo do logo e da landing.
  Toda outra cor saturada é semântica (verde=ok, âmbar=atenção, coral=erro,
  violeta=eval, ciano=rag).
- **Hierarquia tipográfica**:
  - Inter para UI (400/500/600/700) com `letter-spacing: -0.005em` global
    e `-0.02em` em títulos.
  - JetBrains Mono para IDs, valores numéricos, paths, snippets — tudo que
    é "máquina".
- **Raio**: 4/6/8/12px (`--r-xs/sm/md/lg`). Cards usam 8px. Badges 3-4px.
  Nada acima de 12px — operacional, não fofinho.
- **Sombras**: sutilíssimas. Apenas dois lugares têm shadow real: botão
  primário (lift) e modais. Cards usam apenas borda + variação de luminância.
- **Atmosfera**:
  - Um grid sutil de 56px sobre o body (mask-image radial) — só para
    "respirar" sem virar wallpaper.
  - Duas vinhetas radiais (top/left) com a cor de acento em <20% opacidade,
    para dar leve gradiente sem virar glassmorphism.
  - Uma linha de luz vertical no canto direito da sidebar para criar bordo.
- **Pulse**: um único elemento animado em toda a UI — o dot do SDK status.
  Animação de "respiração" em 2.4s. Tudo o resto é estático.

### Anti-padrões evitados

- Sem glassmorphism genérico
- Sem blur exagerado / sem gradientes coloridos em cards
- Sem ícones desenhados que tentem parecer "produto" (todos vêm de um
  conjunto inline lucide-style mínimo, mantido como dependência zero)
- Sem emoji decorativo, exceto onde é semanticamente útil (👍/👎 em
  feedback humano, espelhando o que já existe no app real)
- Sem dado decorativo. Toda métrica exibida vem de um campo do contrato
  da API ou de um mock claramente declarado

---

## 2. Sistema de design adotado

Adotei intencionalmente os mesmos tokens / classes / nomenclatura que a
codebase já usa em `apps/web/app/globals.css`:

- Classes equivalentes às `evo-*` no codebase ficaram com prefixo curto
  (`card`, `t`, `btn`, `metric`, `badge`) para reduzir verbosidade no
  protótipo, mas o mapeamento 1:1 com o sistema atual está documentado
  abaixo em **Recomendações de implementação**.
- A sidebar usa as mesmas três seções do `Sidebar.tsx` real
  (Projeto, Recursos, Operação) e os mesmos ícones lucide.
- Os badges seguem o mesmo conjunto: `ok / warn / err / info / eval`,
  somando um novo `rag` para sinalizar traces que seguem a convenção §9
  (`isRagTrace`).
- Os tokens de cor mantêm a mesma escala semântica do `globals.css` real,
  mas em oklch para evitar bandas e ficar bem em qualquer monitor wide-gamut.

---

## 3. Telas incluídas

| Tela | Status no preview |
|---|---|
| Overview (`/`) | **Redesenhada** com 5 KPIs, gráfico de custo, breakdown de modelo, attention strip, sugestões operacionais, cobertura por avaliação |
| Traces — lista (`/traces`) | **Redesenhada** com tabs (Todos/Erros/Parciais/Lentos/RAG), filtros, tabela densa, indicação RAG/score inline |
| Traces — detalhe (`/traces/:id`) | **Redesenhada** com KPIs do trace, tabs (RAG/Waterfall/Metadata/Feedback), painel RAG completo (Resposta + Grounding + Retrieval + Citation×Claim), feedback humano preservado |
| Avaliações (`/evaluations`) | **Redesenhada** com summary (4 KPIs), tabs (Ativas/Runs/Pausadas), tabela com distribuição de scores, drawer com YAML |
| Prompts (`/prompts`) | **Placeholder premium** — preservado |
| Rubricas (`/rubrics`) | **Placeholder premium** — preservado |
| Datasets (`/datasets`) | **Placeholder premium** — preservado |
| Experimentos (`/experiments`) | **Placeholder premium** — preservado |
| Chaves API (`/keys`) | **Placeholder premium** — preservado + política de segurança visível |
| Exports (`/exports`) | **Placeholder premium** — preservado + limites do job |

Cada placeholder mostra:
1. uma badge `módulo preservado` no header,
2. resumo numérico (counts),
3. lista de itens reais (mocks anonimizados que refletem o que o módulo guarda),
4. coluna lateral com **os endpoints reais que o módulo usa hoje**.

---

## 4. Decisões de UX que merecem destaque

### 4.1 — "Onde estou? O que faço agora?"
Em todas as telas o **eyebrow** (Workspace · ACME / Observabilidade /
Qualidade / Operação) ancora o usuário em qual área do produto está.
Combina com a **attention strip** no Overview, que responde explicitamente
"o que precisa de atenção AGORA".

### 4.2 — Sugestões operacionais
O card "Próximos passos sugeridos" no Overview transforma sinais
(traces RAG sem score, experimento configurado, erros nos últimos 7d)
em **ações reais**. Cada uma abre o modal de preview do endpoint que
seria chamado.

### 4.3 — Cobertura por avaliação
Card no Overview que mostra **% de traces cobertos por cada rubrica**.
Não existe hoje no app real, mas é trivial calcular (`evaluation_runs /
traces` no mesmo `environment`). É a métrica mais útil que falta — sem
ela, o time não sabe que avaliação está deixando de rodar.

### 4.4 — RAG como cidadão de primeira classe
Trace detail tem aba RAG própria, com:
- header com 4 stats RAG (docs / score médio / claims grounded / risco)
- card de Resposta com extração de entidades como tags
- card de Grounding & Qualidade com **claim-level analysis** (verde/vermelho
  por claim individual + citação por claim)
- tabela cruzada Claim × Chunk

A claim-level analysis é o diferencial que separa este preview de qualquer
dashboard genérico LLMops. Mapeia direto para `grounding_quality` do
contrato §9 atual.

### 4.5 — Honestidade sobre o que é real
Toda ação que não tem backend ativo no preview abre um **modal de preview**
mostrando exatamente o endpoint que seria chamado. Botões que correspondem
a features planejadas (rerun, compare) abrem o mesmo modal mas com nota
"planejado". Nada é fingido como real.

### 4.6 — Responsividade mínima
Grids colapsam de 5→2 cols (KPIs), 1.5fr/1fr → 1col (overview), e a sidebar
some abaixo de 760px. Suficiente para notebook 13"/15".

### 4.7 — Atalhos `G + letra`
Mantidos do codebase real, expostos ao lado de cada item de sidebar.
Detalhe pequeno mas reforça "ferramenta para times técnicos".

---

## 5. Endpoints reais representados

Mapeados em `data.jsx → ENDPOINTS`. Todos foram inferidos de
`apps/web/lib/api.ts` e `apps/web/lib/actions.ts` do repo.

| Área | Endpoint | Status atual |
|---|---|---|
| Overview | `GET /v1/projects/{id}/overview` | **ativo** |
| Traces | `GET /v1/traces`, `GET /v1/traces/{id}` | **ativo** |
| Traces | `POST /v1/traces/{id}/feedback` | **ativo** |
| Traces | `POST /v1/traces/{id}/flags`, `POST /v1/traces/{id}/rerun`, `POST /v1/traces/compare` | **planejado** — preview-only |
| Avaliações | `GET /v1/projects/{id}/evaluations`, `POST /v1/evaluations` | **ativo** |
| Rubricas | `GET /v1/projects/{id}/rubrics`, `POST /v1/rubrics`, `POST /v1/rubrics/{id}/publish` | **ativo** |
| Prompts | `GET /v1/projects/{id}/prompts`, `POST /v1/prompts` | **ativo** |
| Datasets | `GET /v1/projects/{id}/datasets`, `POST /v1/datasets` | **ativo** |
| Experimentos | `GET /v1/projects/{id}/experiments`, `POST /v1/experiments` | listagem ativa; criação **planejada** |
| Chaves API | `GET /v1/projects/{id}/api-keys`, `POST /v1/api-keys`, `DELETE /v1/api-keys/{id}` | **ativo** |
| Exports | `GET /v1/projects/{id}/exports`, `POST /v1/exports`, `GET /v1/exports/{id}/download` | **ativo** |

---

## 6. O que ficou de fora do redesign inicial

- **Páginas públicas** (landing, login, register, docs, changelog) — preview
  é só do app autenticado. Landing já passou por refatoração recente no repo.
- **Rubrics em detalhe** — exibido como item mas o editor YAML completo não
  foi redesenhado (apenas o drawer com snapshot do YAML).
- **Experimentos em detalhe** — comparação visual entre prompts/modelos não
  está aqui; o módulo é preservado com lista e endpoints.
- **Settings / faturamento / membros / convites** — fora de escopo da
  refatoração interna nesta fase.
- **Onboarding / empty state do primeiro projeto** — coberto parcialmente
  no empty state da lista de Traces (com snippet do SDK).

---

## 7. Recomendações para implementação no app real

### 7.1 Plano de migração sugerido
1. **Porte os tokens** do `:root` em `preview/styles.css` para
   `apps/web/app/globals.css`, mantendo os nomes das CSS variables atuais
   (`--text`, `--text-muted`, `--accent`, `--ok`, etc).
2. **Substitua o background do body** pelo combo radial + grid sutil.
3. **Aplique a refatoração de Sidebar e Topbar** antes de qualquer página —
   isso já melhora a sensação geral.
4. **Refatore Overview** primeiro (página de maior impacto, traz a sensação
   de "cockpit" imediatamente).
5. **Refatore Traces list → Traces detail (RAG)** em sequência — eles
   compartilham componentes (StatusBadge, ScoreCell, Copyable, Waterfall).
6. **Refatore Avaliações** por último, pois é o que tem menos divergência
   visual hoje.

### 7.2 Componentes a criar em `apps/web/components/ui/`
Estes não existem hoje no repo e fariam falta:

- `PreviewPill` — chip dashed para indicar áreas preservadas/planejadas
- `AttentionStrip` — banner de "algo precisa de atenção" no overview
- `SuggestionRow` — card clicável de próxima ação sugerida
- `ScoreCell` — score numérico + barra colorida por threshold
- `DistBars` — distribuição de scores compacta (6 buckets) — já existe
  inline em `evaluations/page.tsx`; extrair
- `ClaimRow` — linha de claim-level grounding
- `EndpointSnippet` — útil em dev/debug e telas de admin
- `ToastHost` — toast event-driven, custom event `evo:toast`
- `CrumbsBar` — breadcrumbs do topbar com workspace/project/section

### 7.3 Backend / endpoints que o redesign sugere adicionar
Não são exigidos, mas tornariam o cockpit muito mais útil:

- `GET /v1/projects/{id}/overview/coverage` — % de traces com run por rubrica
  (hoje precisa ser computado no client)
- `GET /v1/projects/{id}/overview/attention` — lista canônica do que precisa
  de atenção (erros, scores baixos, ungrounded, custo anômalo) já ranqueada
  no servidor
- `GET /v1/traces/{id}/rag` — endpoint dedicado para a estrutura RAG
  consolidada (hoje os helpers em `lib/rag.ts` reconstroem do trace+spans)
- `POST /v1/traces/{id}/rerun` e `POST /v1/traces/compare` — já marcados
  como planejados

### 7.4 Microcopy — sugestões
A microcopy em **PT-BR** foi mantida (o app está em PT-BR; o
`design-refactor-plan.md` propõe migração futura para inglês). Sugestões:

- "Atenção" em vez de "parcial" para status `partial` (testado no preview)
- "Reexecutar" e "Comparar" em vez de "Replay" / "Diff" — termos mais claros
- "Workspace · ACME / Aurora Support" como eyebrow universal — ancora bem
- "schema_mismatch" / "vector_db_timeout" como **causa** (nova coluna),
  separado de `status` — alta densidade de sinal por linha

### 7.5 Acessibilidade
Cores semânticas têm contraste ≥ 4.5:1 contra `--bg-0` no preview.
Estados ativos têm dupla codificação (cor + dot + barra de acento à esquerda).
Atalhos `G + letra` funcionam em qualquer foco fora de input/textarea/select.

---

## 8. Convenções para futura iteração

- **Densidade > respiração** nesta UI. Pad horizontal de cards é 16px,
  não 24px+. Linhas de tabela são 32-36px de altura. Não cresça isso.
- **Mono para tudo que é máquina**: IDs, paths, valores numéricos
  com unidade, timestamps absolutos. Sans-serif para tudo que é prosa
  (títulos, descrições, microcopy de empty state).
- **Quando em dúvida, esconda chrome**. Botões secundários: `btn--ghost`.
  Bordas: `--border-subtle`, não `--border`. O cockpit deve sumir e
  deixar os dados em primeiro plano.
- **Status colorido só onde importa**. Não pinte tudo de verde "porque deu
  certo". Status `ok` é o estado default e merece zero atenção visual.

---

Direção pronta para virar referência. Sugiro começar pela aplicação dos
tokens em `globals.css` e pela refatoração de Overview, que dá o tom para
o resto.
