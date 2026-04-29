# ADR-0003 — Evaluation Strategy: Rubric YAML + LLM-as-judge + heurísticas determinísticas

- **Status:** Accepted
- **Data:** 2026-04-29

## Contexto

A camada de avaliação é o **diferencial do produto**. Mal projetada, vira "logging com cores".

Decisões críticas:
1. **Como definir** uma rubrica? UI? código? YAML?
2. **Quais evaluators** suportar?
3. Como **agregar** múltiplos scores?
4. Como **calibrar** o judge LLM?
5. Quem **paga** (em USD) pelo eval — e como controlar?

## Opções consideradas

### 1. Definição da rubrica

| Opção | Prós | Contras |
|---|---|---|
| **YAML versionado em arquivo** ✅ | Diff em git, code review, automação CI | Curva inicial pequena para PMs |
| Form/UI no-code | Acessível a PMs | Stateful, sem versionamento ergonômico, vira spaghetti |
| Python custom code | Máxima flexibilidade | Sandbox, segurança, complexidade |
| JSON estruturado | Programático | Ilegível para humanos vs YAML |

### 2. Catálogo de evaluators

Considerados todos os do estado da arte (2026):
- LLM-as-judge (G-Eval, faithfulness, relevance, helpfulness, harmlessness)
- Heurísticas (regex, keywords, length, exact match, JSON schema)
- Reference-based (BLEU, ROUGE, METEOR — para tradução/sumarização específicas)
- Embedding-based (cosine similarity, retrieval precision)
- Behavioral (no PII, no toxic content, no jailbreak)

**Decisão MVP:** 7 evaluators core (3 heurísticas estruturais + 2 textuais + 1 embedding + 1 LLM judge). Cobertura 80% dos casos reais sem inflar surface area.

### 3. Agregação

| Método | Quando |
|---|---|
| `weighted_mean` ✅ default | Caso geral; permite priorizar evaluators críticos |
| `min` | Se "qualquer falha = falha" (segurança) |
| `max` | Raro |
| `mean` | Se todos os pesos iguais |
| Custom Python | Futuro |

### 4. Calibração do judge

Problema clássico: LLM judge dá 0.85 onde humano dá 0.6.

**Estratégia:**
- **Templates de prompt cuidadosos** com escala explícita (0..1) e exemplos.
- **`output_schema` strict** para forçar JSON estruturado.
- **`temperature=0`** sempre.
- **Cache** para reduzir custo de re-eval (hash determinístico).
- **Meta-eval** (Fase 2): comparar judge vs humano via `human_feedback` para calibrar.

### 5. Custo

- Cada evaluator declara `cost_cap_usd` (default 0.005).
- Project-level `monthly_judge_budget_usd` (default 20).
- Cache obrigatório quando `cost_cap_usd > 0.01`.
- Fallback gracioso: se budget exhausted, run ainda registra status de erro mas não desabilita o sistema.

## Decisão

- **Definição:** YAML versionado, parsed e validado server-side. Schema strict com Pydantic. Editor Monaco no dashboard com validate inline.
- **Catálogo no MVP:** `regex_match`, `keyword_presence`, `length_bounds`, `json_schema_valid`, `exact_match`, `cosine_similarity`, `llm_judge`. Reference-based metrics em Fase 2 (caso de uso restrito a tradução/sumarização).
- **Agregação:** `weighted_mean` default, com suporte a `mean`, `min`, `max`. Custom Python em Fase 2.
- **Templating:** Jinja2 dentro de `prompt:`. Variáveis `trace.*`, `expected.*`, `var.*`.
- **Resolver de input/output:** modo `auto` extrai `messages_in[-1].content` / `messages_out[0].content` do primeiro/último `llm_call`. Override por rubrica via `input_resolver` / `output_resolver`.
- **Cache de judge:** Redis, hash de `(model, prompt_resolved, target_content)`, TTL 7 dias. **Obrigatório** para evaluators com cap > 0.01.
- **Budget:** cap por evaluator + budget mensal por projeto.
- **Status de run:** `completed` mesmo com falhas parciais (desde que ≥ 1 score válido); `error` apenas em falha total.
- **Calibração:** apenas via templates + temperature=0 no MVP. Meta-eval em Fase 2.

## Consequências

**Positivas:**
- Rubrica como código → versionamento natural, code review, CI/CD-friendly.
- 7 evaluators é leve de manter, cobre maioria dos casos.
- `weighted_mean` é familiar e flexível.
- Budget+cache evita conta caríssima em dev.

**Negativas:**
- PMs sem familiaridade com YAML ficam dependentes de eng.
- Sem reference-based metrics no MVP, alguns casos (tradução, RAG faithfulness com referência) precisam de llm_judge mais caro.
- Cache pode mascarar bugs em rubric dev (TTL longo). Mitigação: flag `--no-cache` em CLI.

## Quando reavaliar

- Cliente real pedir reference-based metric: adicionar BLEU/ROUGE em Fase 2.
- Calibração ruim em dados reais: implementar meta-eval UI.
- PM-driven team: investir em UI no-code de rubrica em Fase 3.
