# 09 — Evaluation Engine Spec

## 1. Filosofia

- **Rubrica como código.** Definição declarativa em YAML, versionada.
- **Composição.** Uma rubrica é uma lista de **evaluators**; o resultado final é um agregado dos scores parciais.
- **Determinismo onde possível.** Heurísticas (regex, schema, exact_match) primeiro; LLM judge só onde valor agregado justifica custo.
- **Score normalizado.** Todos os evaluators retornam `score ∈ [0,1]` e `passed: bool`. Comparação cross-rubric é viável.
- **Falha graceful.** Erro de um evaluator não derruba a run; persiste `error` no score parcial e segue.

## 2. Modelo de rubrica

### 2.1 Schema YAML oficial do MVP (validado)

O schema oficial do MVP é **prático e executável**. A unidade que roda código é o
`evaluator`; `criteria`, `critical_flags` e `output_schema` dão semântica para UI,
relatórios e prompts de judge, mas não substituem `evaluators`.

Campos desconhecidos no topo do YAML devem ser rejeitados pelo parser. A exceção
é `metadata`, reservado para anotações livres.

#### Campos obrigatórios

| Campo | Tipo | Regra |
|---|---|---|
| `slug` | string | Snake-case/kebab-case único por projeto. Identidade estável da rubrica. |
| `name` | string | Nome legível para UI/relatórios. |
| `description` | string | Objetivo da rubrica e escopo de uso. |
| `threshold` | number | `0..1`; run passa se `aggregate_score >= threshold` e não houver auto-fail. |
| `aggregate` | enum | `weighted_mean`, `mean`, `min`, `max`. |
| `evaluators` | array | Lista não vazia de evaluators executáveis. |

#### Campos opcionais do MVP

| Campo | Tipo | Default | Regra |
|---|---|---|---|
| `version` | int | versão do servidor | Apenas informativo no YAML; o DB/API é fonte da verdade. Se enviado, deve bater com a versão publicada. |
| `status` | enum | `draft` | `draft`, `active`, `archived`; usado por CLI/UI. O `current_version` do DB continua sendo fonte da versão ativa. |
| `fail_fast` | bool | `false` | Se true, qualquer evaluator com `fail_fast=true` que falhar interrompe o restante. |
| `input_resolver` / `output_resolver` | string | `auto` | Resolve o input/output principal para templates. |
| `evaluation_mode` | object | derivado | Metadata explícita para leitura humana; a execução real é inferida dos `evaluators`. |
| `judge` | object | vazio | Defaults para evaluators `llm_judge`; config local do evaluator vence. |
| `thresholds` | object | vazio | Faixas auxiliares para UI (`review`, `fail_below`, etc.); `threshold` é o corte oficial. |
| `criteria` | array | `[]` | Taxonomia de critérios de qualidade. Não executa nada sozinho. |
| `critical_flags` | array | `[]` | Taxonomia de flags críticas que evaluators podem emitir. |
| `automatic_fail_conditions` | array | `[]` | Regras simples que forçam `passed=false` quando um evaluator/flag indicar falha. |
| `cost_limits` | object | projeto | Caps locais de custo/timeout; não podem exceder o budget do projeto. |
| `output_schema` | object | schema padrão | Contrato do resultado normalizado esperado para consumo por UI/export. |
| `metadata` | object | `{}` | Livre, sem efeito na execução. |

#### Objetos aninhados

| Objeto | Campos obrigatórios | Campos opcionais | Observação |
|---|---|---|---|
| `criteria[]` | `slug`, `name`, `description`, `weight`, `scale`, `required`, `evaluator`, `pass_threshold` | `metadata` | `scale` aceita `0-1`, `0-5`, `0-10`, `pass_fail`; o engine normaliza tudo para `0..1`. |
| `evaluators[]` | `id`, `type`, `weight`, `config` | `name`, `enabled`, `criteria`, `fail_fast` | `type` deve ser um dos 7 evaluators MVP. `enabled=false` não roda nem entra na agregação. |
| `critical_flags[]` | `slug`, `description`, `severity`, `auto_fail` | `metadata` | `severity`: `low`, `medium`, `high`, `critical`. |
| `automatic_fail_conditions[]` | `slug`, `description` + `evaluator_id` ou `flag` | `metadata` | Regra simples, sem DSL complexa no MVP. |
| `output_schema` | `score`, `passed`, `criteria_results`, `flags`, `rationale` | campos extras de leitura | Contrato normalizado; não é o schema do judge. |

#### Campos fora do YAML do MVP

| Campo | Status | Motivo |
|---|---|---|
| `id` | Gerado pelo servidor | `rubrics.id` e `rubric_versions.id` são ULIDs criados pela API/DB. |
| `project_id` | Contexto da rota/API key | Rubricas são criadas em `/v1/projects/{id}/rubrics`. |
| `created_by`, `created_at` | Gerado pelo servidor | Auditabilidade vem da API, não do arquivo YAML. |
| `type: heuristic` genérico | Não aceito no MVP | O engine despacha por tipos concretos: `regex_match`, `keyword_presence`, etc. |
| `aggregate: weighted_average`, `min_score`, `all_required` | Alias/futuro | YAML usa `weighted_mean`, `min`, etc. `all_required` é modelado no MVP com `aggregate: min`, `required: true` e `automatic_fail_conditions`. |
| Custom Python evaluator | Futuro | Requer sandbox e modelo de segurança próprios. |

#### Forma canônica

`criteria` é uma taxonomia legível. `evaluators` é a lista executável. Quando um
evaluator cobre critérios específicos, ele pode declarar `criteria: [slug, ...]`.
O resultado persistido no MVP ainda é por evaluator (`evaluation_scores`); sub-scores
por critério vindos de um LLM judge ficam em `raw_output` e podem ser projetados na UI.

```yaml
slug: support-answer-quality
name: Support Answer Quality
version: 1
status: active
description: Avalia respostas do agente de suporte
threshold: 0.7        # passa run se aggregate >= 0.7
aggregate: weighted_mean   # weighted_mean | mean | min | max
fail_fast: false      # se true, primeiro evaluator com fail_fast=true que falhar pula o resto

criteria:
  - slug: relevance
    name: Relevance
    description: Responde ao que o usuário perguntou.
    weight: 2.0
    scale: 0-1
    required: true
    evaluator: llm_judge
    pass_threshold: 0.6
  - slug: safety
    name: Safety
    description: Não vaza PII, segredos ou instruções ocultas.
    weight: 1.0
    scale: pass_fail
    required: true
    evaluator: heuristic
    pass_threshold: 1.0

critical_flags:
  - slug: pii_leak
    description: Resposta vazou PII ou segredo.
    severity: critical
    auto_fail: true

automatic_fail_conditions:
  - slug: pii_leak_auto_fail
    description: Qualquer falha do evaluator no_pii_leaked reprova a run.
    evaluator_id: no_pii_leaked

evaluators:
  - id: relevance
    name: Relevance judge
    type: llm_judge
    enabled: true
    weight: 2.0
    criteria: [relevance]
    config:
      model: openai/gpt-4o-mini
      temperature: 0
      prompt: |
        You are an evaluator. Given the user question and the assistant answer,
        rate how relevant the answer is on a scale 0..1.

        User: {{ trace.input.user_message }}
        Assistant: {{ trace.output.assistant_message }}

        Respond as JSON: {"score": 0..1, "reasoning": "..."}
      output_schema:
        type: object
        properties:
          score: { type: number, minimum: 0, maximum: 1 }
          reasoning: { type: string }
        required: [score, reasoning]
      pass_threshold: 0.6

  - id: no_pii_leaked
    name: No PII leaked
    type: regex_match
    enabled: true
    weight: 1.0
    fail_fast: true
    criteria: [safety]
    config:
      target: trace.output.assistant_message
      pattern: "\\b\\d{11}\\b"           # CPF naive
      mode: must_not_match               # must_match | must_not_match
      pass_when_match: false

  - id: response_length_ok
    name: Response length OK
    type: length_bounds
    enabled: true
    weight: 0.5
    config:
      target: trace.output.assistant_message
      min_chars: 20
      max_chars: 1500

output_schema:
  score: number          # alias de aggregate_score normalizado 0..1
  passed: boolean
  criteria_results: array
  flags: array
  rationale: string
```

#### Versionamento de rubricas

- `slug` identifica a rubrica dentro do projeto.
- `version` no YAML é opcional e serve para revisão humana/CLI; a versão canônica é `rubric_versions.version`, criada pela API.
- `POST /v1/projects/{id}/rubrics { yaml_source }` cria `version=1`.
- `POST /v1/rubrics/{id}/versions { yaml_source, changelog? }` cria `version=n+1`.
- `RubricVersion` é imutável. Editar uma rubrica sempre cria nova versão.
- `Rubric.current_version` aponta a versão ativa; runs já iniciadas ficam presas ao `rubric_version` carregado no início.
- Mapeamento para DB no MVP: `rubrics` denormaliza `slug`, `description`, `threshold` e `current_version`; o YAML completo (`name`, `status`, `criteria`, `critical_flags`, `output_schema`, etc.) fica em `rubric_versions.parsed_spec`; `evaluators` normaliza apenas evaluators habilitados e executáveis.

#### Relação entre campos

- `criteria` define **o que importa** do ponto de vista de produto.
- `evaluators` define **como medir**. Heurísticas determinísticas e `llm_judge` podem coexistir na mesma rubrica.
- `threshold` aplica-se ao score agregado final.
- `aggregate` calcula `aggregate_score` a partir dos scores dos evaluators habilitados.
- `critical_flags` nomeia falhas graves; evaluators podem emiti-las em `raw_output`.
- `automatic_fail_conditions` transforma uma falha crítica em `passed=false`, mesmo quando o score agregado passa.
- `output_schema` descreve o resultado normalizado esperado; para `llm_judge`, o schema enforceable continua sendo `evaluators[].config.output_schema`.

### 2.2 Variáveis disponíveis em templates Jinja2

| Variável | Descrição |
|---|---|
| `trace` | Objeto trace inteiro (pydantic dump) |
| `trace.input` | Input principal (resolvido como `messages_in[-1].content` do primeiro `llm_call`, ou `metadata.input`) |
| `trace.output` | Output principal (resolvido como `messages_out[0].content` do último `llm_call`) |
| `trace.spans` | Lista de spans |
| `trace.tags`, `trace.user_ref`, `trace.metadata` | Acesso direto |
| `expected` | Em modo experiment com dataset, traz `dataset_item.expected_output` |
| `var.*` | Variáveis customizadas passadas no run |

> **Resolver de input/output** é configurável por rubrica via `input_resolver` / `output_resolver` (`auto`, `last_assistant`, `concat_assistants`, `from_metadata.<key>`). Default `auto`.

## 3. Evaluators (MVP)

### 3.1 `regex_match`
```yaml
type: regex_match
config:
  target: trace.output.assistant_message
  pattern: "..."
  mode: must_match | must_not_match
  flags: [i, m, s]   # opcionais
```
- `score = 1.0` se pass, `0.0` caso contrário.

### 3.2 `keyword_presence`
```yaml
type: keyword_presence
config:
  target: trace.output.assistant_message
  keywords: ["pedido", "rastrear", "código"]
  require: any | all | none
```
- `score = matched / total` quando `require: all`; binário em `any/none`.

### 3.3 `length_bounds`
```yaml
type: length_bounds
config:
  target: trace.output.assistant_message
  unit: chars | words | tokens   # default chars
  min: 20
  max: 1500
```
- `score = 1.0` dentro dos bounds; degrade linear até 0 fora dos bounds + tolerância de 20%.

### 3.4 `json_schema_valid`
```yaml
type: json_schema_valid
config:
  target: trace.output.assistant_message     # texto que deve ser JSON
  schema: { ... JSON Schema ... }
  parse_mode: strict | extract_first   # extract_first acha o 1º JSON em texto
```

### 3.5 `exact_match`
```yaml
type: exact_match
config:
  target: trace.output.assistant_message
  expected: "{{ expected.assistant_message }}"
  normalize: [lowercase, strip, collapse_spaces]
```

### 3.6 `cosine_similarity`
```yaml
type: cosine_similarity
config:
  target_a: trace.output.assistant_message
  target_b: "{{ expected.assistant_message }}"
  embedding:
    provider: openai
    model: text-embedding-3-small
  pass_threshold: 0.85
```

### 3.7 `llm_judge`
```yaml
type: llm_judge
config:
  model: openai/gpt-4o-mini
  temperature: 0
  prompt: |
    {{ trace.input }} → {{ trace.output }}
    Avalie 0..1.
  output_schema: { ... JSON Schema strict ... }
  retry_on_invalid: 1     # 1 retry com "respond ONLY in JSON"
  pass_threshold: 0.7
  cost_cap_usd: 0.01      # aborta se custo estimado > cap
```

Implementação chama `litellm.completion` com `response_format={"type": "json_schema", "json_schema": ...}` quando suportado pelo provider; fallback para parsing tolerante (extract first JSON).

## 4. Run lifecycle

```
[create EvaluationRun status=queued]
        │
        ▼
[load rubric_version + evaluators]
        │
        ▼
[for each evaluator (em ordem)]
        ├─ build inputs (resolve Jinja)
        ├─ execute (com timeout 30s)
        ├─ persist EvaluationScore parcial
        └─ se evaluator.fail_fast e !passed: break
        │
        ▼
[aggregate scores → run.aggregate_score]
        │
        ▼
[apply automatic_fail_conditions / critical flags]
        │
        ▼
[run.passed = aggregate >= rubric.threshold AND no auto-fail]
        │
        ▼
[status=completed]
```

Em erro de evaluator individual:
- `EvaluationScore.score = 0`, `passed=false`, `raw_output={"error": "..."}`.
- Run continua (não fail_fast).
- `EvaluationRun.status = completed` se ao menos 1 score foi computado, com flag `partial_failure: true` em metadata.
- `EvaluationRun.status = error` apenas se TODOS os evaluators falharam ou erro de carregamento da rubric.

## 5. Agregação

```python
def aggregate(scores: list[Score], weights: dict[str, float], method: str) -> float:
    if method == "weighted_mean":
        total_w = sum(weights[s.evaluator_id] for s in scores)
        return sum(s.score * weights[s.evaluator_id] for s in scores) / max(total_w, 1e-9)
    if method == "mean":
        return mean(s.score for s in scores)
    if method == "min":
        return min(s.score for s in scores)
    if method == "max":
        return max(s.score for s in scores)
```

Depois da agregação, `automatic_fail_conditions` pode forçar `passed=false` sem
alterar `aggregate_score`. Isso preserva a métrica numérica para análise, mas
bloqueia runs com falhas críticas como PII, segredo vazado ou regra de negócio
violada.

## 6. Triggering

| Trigger | Como |
|---|---|
| **Manual via API** | `POST /v1/evaluations/run { trace_id, rubric_id }` |
| **Manual via UI** | Botão "Run rubric" no detalhe do trace |
| **Auto em ingestion** | `Project.auto_eval_rubrics` lista os slugs; ingestion enfileira após persistir trace |
| **Schedule** (Futuro) | Cron interno → roda rubric sobre últimas N horas de traces |
| **Experiment** | ExperimentService chama EvalService para cada (variant × dataset_item) |

## 7. Custos & guardrails

- Cada evaluator declara `cost_cap_usd`. `IngestionService` rejeita rubric publish se algum cap > 0.10 sem confirmação.
- `Project.monthly_judge_budget_usd` (default $20 no MVP) é checado **antes** de disparar `llm_judge`. Excedido → run é criada com `status=error`, code `judge_budget_exhausted`.
- Cache de `llm_judge`: hash de `(model, prompt_resolved, target_content)` → resposta. TTL 7 dias. Reduz custo em re-evals.

## 8. Regression test suite

Implementação em cima de **Experiments** sem entidade nova:

```yaml
# Definido no projeto via API ou CLI
experiment:
  name: regression-prod
  dataset: golden-set-q2
  variants:
    - name: current
      prompt_version: support-answer-system@latest
      model: openai/gpt-4o-mini
  rubric: support-answer-quality
  pass_criteria:
    min_pass_rate: 0.95
    no_regression_vs: previous_run
    max_avg_cost_usd: 0.005
```

CLI:
```bash
$ evalops experiment run regression-prod \
    --variant current.prompt_version=$GIT_SHA \
    --fail-on-regression
```
- Exit code 0 / 1.
- Imprime tabela markdown que pode ser pasted em PR.

## 9. Meta-eval (avaliação dos avaliadores) — Recomendado / Futuro

Para verificar que `llm_judge` está calibrado:

- Coletar pares (trace, score_judge, score_humano) — usa `human_feedback`.
- Calcular **agreement** (Cohen's kappa, Pearson correlation, ou simply MAE).
- Dashboard mostra "judge calibration": ex. judge dá 0.85 quando humano dá 0.6 → over-confident.

> Implementação: notebook + script offline no MVP; UI dedicada como Futuro.

## 10. Validação de rubric YAML no push

Esquema strict (Pydantic) verificando:
- `slug` snake-case.
- `id`, `project_id`, `created_at`, `created_by` ausentes no YAML.
- `name` e `description` não vazios.
- `evaluators` não vazio.
- `enabled=false` exclui evaluator da execução e da agregação.
- `weight` > 0 quando `aggregate=weighted_mean`.
- `criteria[].slug` únicos; referências em `evaluators[].criteria` apontam para critérios existentes.
- `critical_flags[].slug` únicos; `automatic_fail_conditions` referencia evaluator ou flag existente.
- `model` em `llm_judge` está na pricing table.
- `prompt` em `llm_judge` faz parse de Jinja2 sem erro de sintaxe.
- `cost_cap_usd` ≤ projeto limit.

Erro de validação → 422 com lista de issues.

## 11. Pseudo-código de execução

```python
async def run_evaluation(trace_id: str, rubric_id: str) -> EvaluationRun:
    trace = await traces.get_with_spans(trace_id)
    version = await rubrics.get_current_version(rubric_id)
    run = await evaluation_runs.create(trace_id, rubric_id, version.version, status="running")
    scores = []
    try:
        for ev in version.evaluators:
            if not ev.enabled:
                continue
            inputs = await resolver.resolve(trace, ev.config, vars=run.vars)
            try:
                result = await EVALUATOR_REGISTRY[ev.type].run(inputs, ev.config)
                score = await scores_repo.create(run.id, ev.id, result.score, result.passed,
                                                  reasoning=result.reasoning, raw=result.raw,
                                                  cost=result.cost, latency_ms=result.latency)
                scores.append(score)
                if ev.fail_fast and not result.passed:
                    break
            except Exception as e:
                await scores_repo.create_error(run.id, ev.id, error=str(e))
        agg = aggregate([s for s in scores if not s.error], weights, version.aggregate_method)
        auto_failed = automatic_failures_match(version.automatic_fail_conditions, scores)
        await runs_repo.complete(run.id, agg, (agg >= version.threshold) and not auto_failed)
    except Exception as e:
        await runs_repo.fail(run.id, str(e))
    return run
```

## 12. Casos de borda

| Caso | Comportamento |
|---|---|
| Trace sem `messages_out` (status=error) | Resolver retorna string vazia; `length_bounds` falha com 0; `llm_judge` recebe string vazia |
| Rubric atualizada durante run | Run é tied a `rubric_version` no início; mudanças não afetam run em curso |
| LLM judge retorna JSON inválido após retry | `score=0`, `passed=false`, `raw_output.parse_error=true` |
| Trace deletado durante run async | Run cancelada com status=`error`, code=`trace_deleted` |
