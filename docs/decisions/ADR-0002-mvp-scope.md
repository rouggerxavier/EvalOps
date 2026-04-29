# ADR-0002 — MVP Scope: Síncrono inline + 7 evaluators + SDK Python only

- **Status:** Accepted
- **Data:** 2026-04-29
- **Decisor:** Autor

## Contexto

O autor é solo, ~20h/semana, com janela de 6-10 semanas para um MVP que sirva de demo de portfólio com profundidade técnica suficiente para sinalizar senioridade em AI Engineering. O escopo "completo" do produto (com worker async, billing, RBAC, multi-region, SDK em 2 linguagens, drift detection) demoraria 6+ meses.

Precisamos cortar com critérios técnicos e de produto. A pergunta concreta: **o que é suficiente para Marina (AI Engineer) usar de verdade e impressionar em entrevista?**

## Opções consideradas

### Sobre execução de evaluators
- **A)** Worker async com Redis/Arq desde a semana 1.
- **B)** ✅ Síncrono inline (ou em background thread best-effort para auto-eval). Worker async como Fase 1.1.
- **C)** Sem auto-eval no MVP, só manual.

### Sobre número de evaluators
- **A)** 3 evaluators (regex, keyword, llm_judge): cobre 80% dos casos.
- **B)** ✅ 7 evaluators: regex, keyword, length_bounds, json_schema_valid, exact_match, cosine_similarity, llm_judge.
- **C)** 12+ evaluators incluindo BLEU, ROUGE, faithfulness, context_recall.

### Sobre SDK
- **A)** ✅ SDK Python only no MVP.
- **B)** Python + TypeScript no MVP.
- **C)** Sem SDK; só HTTP API.

### Sobre billing
- **A)** ✅ Mockado: schema de `plans/subscriptions/usage_counters` pronto, sem Stripe.
- **B)** Stripe real desde MVP.
- **C)** Sem billing/quotas.

## Decisão

- **Execução de evaluators:** B — Síncrono inline. Worker Arq na Fase 1.1 (semana 8).
- **Auto-eval em ingestion:** **off por default** no MVP. Quando ativado, roda em background thread best-effort (não persistente; pode perder em restart). Documentado como tradeoff.
- **Evaluators:** B — 7 evaluators cobrem regression test, eval LLM-as-judge clássico e validações estruturais.
- **SDK:** A — Python only. TS em Fase 2.
- **Billing:** A — mockado. Demonstra arquitetura sem custo de implementação Stripe.
- **Auto-instrument:** OpenAI no MVP. Anthropic e Gemini em Fase 2.

## Consequências

**Positivas:**
- Janela de implementação cabe nas 7 semanas alocadas para MVP core.
- Cada decisão é defensável em entrevista (mostra critério, não inocência).
- Schema fica preparado para Fase 1.1/2 sem refactor doloroso.

**Negativas:**
- Auto-eval inline pode parecer "amador" se ingestion travar visivelmente. Mitigação: `auto_eval_rubrics` é opt-in e default off; quem ativa entende o tradeoff.
- 7 evaluators é razoável mas não impressiona quem espera 20+. Counter: profundidade (rubric YAML, agregação, custo cap, cache) > número.
- Ausência de TS SDK significa que apps Web não logam direto. Mitigação: documentar arquitetura "frontend → backend → EvalOps" como recomendada (também é o caminho seguro por causa de keys).

## Critério de saída do MVP

Ver [`03-mvp-scope.md`](../03-mvp-scope.md) §4.

## Quando reavaliar

- Final da semana 7: se auto-eval inline causa latência visível, **prioridade máxima** virar Arq antes de qualquer outra Fase 2.
- Pedido de cliente real para TS SDK: priorizar Fase 2.
