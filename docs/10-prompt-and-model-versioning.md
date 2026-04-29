# 10 — Prompt & Model Versioning

## 1. Por que versionar

- **Reprodutibilidade.** Saber qual prompt+modelo gerou cada resposta é pré-requisito de qualquer análise séria.
- **A/B controlado.** Sem versão, não dá pra comparar.
- **Rollback.** Quando a v6 piorar a qualidade, voltar à v5 deve ser trivial.
- **Auditoria.** Compliance e investigação de incidentes precisam de histórico.

## 2. Modelo

### 2.1 Prompt
- Identificado por `slug` único no projeto (`support-answer-system`).
- Tem 1+ `prompt_version` (imutáveis).
- Tem `current_version: int` apontando para versão "ativa" (default).

### 2.2 PromptVersion
```yaml
prompt:
  slug: support-answer-system
  version: 5
  template: |
    You are a helpful support agent for Aurora.
    Always answer in {{ language }}.
    Use these tools when needed: {{ tools_summary }}.
    User: {{ user_message }}
  variables:
    language:
      type: string
      default: "Portuguese"
      required: false
    tools_summary:
      type: string
      required: true
    user_message:
      type: string
      required: true
  metadata:
    model_default: openai/gpt-4o-mini
    temperature_default: 0.2
    notes: "Versão depois do refactor de tools (PR #142)"
  changelog: "Reorganizado bloco de instruções; adicionado bullet 'sem inventar preços'."
```

### 2.3 Como o trace referencia
- Span `llm_call` tem `prompt_version_id` (FK).
- Span pode também armazenar o `messages_in` resolvido (para reprodução).
- Resolução: SDK envia `prompt_version_ref: "support-answer-system@5"` ou `prompt_version_ref: "support-answer-system@latest"` no momento da chamada; servidor resolve para ID concreto.

## 3. Workflow

### 3.1 Criar prompt
1. Dev escreve `prompts/support-answer-system.yaml` no repo da aplicação cliente.
2. CLI: `evalops prompts push prompts/support-answer-system.yaml`
3. Servidor cria nova versão se conteúdo mudou (hash do template diferente); retorna número.

### 3.2 Usar no código
```python
prompt = evalops.prompts.get("support-answer-system", version="latest")
# OU pin para versão específica:
prompt = evalops.prompts.get("support-answer-system", version=5)

rendered = prompt.render(
    language="pt-BR",
    tools_summary="...",
    user_message=user_msg,
)
response = openai.chat.completions.create(
    model=prompt.metadata["model_default"],
    messages=rendered,
)
# auto-instrument já liga prompt_version_id ao span
```

### 3.3 Diff visual no dashboard

- Tela `Prompts/{slug}/v5 vs v4`: side-by-side com highlighting (lib `react-diff-viewer-continued`).
- Mostra: template diff, variáveis adicionadas/removidas, metadata changes, changelog.

### 3.4 Rollback
- "Promote v4 to current" → cria nova versão (v6) idêntica a v4 com changelog `"Rollback to v4 due to regression in metric X"`.
- **Não** deleta v5. Histórico imutável.

## 4. Experiments (comparação controlada)

### 4.1 Definição

```yaml
experiment:
  name: q2-model-comparison
  dataset: support-real-week-of-2026-04-15  # 200 dataset_items
  rubric: support-answer-quality            # avalia cada saída
  variants:
    - name: control
      prompt_version: support-answer-system@5
      model: openai/gpt-4o-mini
      params: { temperature: 0.2 }
    - name: cheaper
      prompt_version: support-answer-system@5
      model: groq/llama-3.3-70b
      params: { temperature: 0.2 }
    - name: better
      prompt_version: support-answer-system@6
      model: openai/gpt-4.1
      params: { temperature: 0.2 }
  baseline_variant: control
  pass_criteria:
    min_pass_rate: 0.90
    no_regression_vs: control     # nenhum variant pode ter pass_rate < control - 0.02
    max_avg_cost_usd_per_item: 0.01
```

### 4.2 Run lifecycle

```
[ExperimentRun.status = running]
   ├─ for each variant:
   │    └─ for each dataset_item:
   │         ├─ render prompt with item.input
   │         ├─ chama LLM (model, params do variant)
   │         ├─ persiste como trace (tag=experiment, experiment_run_id, variant)
   │         └─ roda rubrica → score
   ├─ agrega métricas por variant
   ├─ aplica pass_criteria
   └─ status=completed; passed=bool
```

Concorrência: cada (variant × item) é uma task no worker. Limite `max_concurrent` (default 5) por experimento para não estourar rate-limit do provider.

### 4.3 Resultado

```json
{
  "run_id": "exr_01HX...",
  "status": "completed",
  "passed": false,
  "by_variant": {
    "control": { "pass_rate": 0.94, "avg_score": 0.81, "avg_latency_ms": 720, "total_cost_usd": 0.42 },
    "cheaper": { "pass_rate": 0.81, "avg_score": 0.72, "avg_latency_ms": 380, "total_cost_usd": 0.05 },
    "better":  { "pass_rate": 0.97, "avg_score": 0.88, "avg_latency_ms": 1100, "total_cost_usd": 1.85 }
  },
  "comparisons": {
    "cheaper_vs_control": { "delta_pass_rate": -0.13, "delta_cost": -0.37, "regression": true },
    "better_vs_control":  { "delta_pass_rate": +0.03, "delta_cost": +1.43, "regression": false }
  },
  "criteria_failures": ["cheaper.pass_rate < control.pass_rate - 0.02"]
}
```

## 5. Regression em CI

### 5.1 Pipeline GitHub Actions

```yaml
- name: Run regression suite
  env:
    EVALOPS_API_KEY: ${{ secrets.EVALOPS_KEY }}
  run: |
    npx -y evalops experiment run regression-prod \
       --variant current.prompt_version=$(git rev-parse HEAD) \
       --fail-on-regression \
       --report-format markdown > regression.md
- uses: marocchino/sticky-pull-request-comment@v2
  with: { path: regression.md }
```

### 5.2 Critérios de bloqueio
- `pass_rate < threshold`
- regressão > N pontos vs último run da branch principal
- custo médio/exemplo > limite

## 6. Versionamento de modelo (do lado do cliente)

EvalOps **não** hosta modelos. Mas:
- A `prompt_version.metadata.model_default` documenta qual modelo é "esperado".
- Spans gravam `model` real usado.
- Dashboard tem aba "Drift de modelo": compara `model` nos spans recentes com `metadata.model_default` do prompt → mostra divergências.

## 7. Boas práticas (parte da doc do produto)

- Não versionar prompts em strings espalhadas pelo código. Centralizar em `prompts/*.yaml` ou via UI do EvalOps.
- Sempre incrementar versão para mudanças semânticas; mudanças puramente cosméticas (whitespace) podem ficar em mesma versão.
- Adicionar `changelog` curto em toda nova versão.
- Pinar versão em produção; `@latest` é OK em dev/staging.
- Rodar experiment antes de promover nova versão para "current".

## 8. Open questions

- **[Decisão pendente]** Suportar prompts em **JSON Schema** (input/output validation embutido) ou puro Jinja? Recomendação: Jinja no MVP; schema-driven é Futuro.
- **[Decisão pendente]** Compatibilidade com **LangSmith** prompt format? Recomendação: importer de `.langchain` em Futuro.
- **[Decisão pendente]** Editor visual de prompt no dashboard? Recomendação: read-only no MVP (push via CLI). Editor é Futuro.
