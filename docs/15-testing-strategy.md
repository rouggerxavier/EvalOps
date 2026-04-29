# 15 — Testing Strategy

## 1. Filosofia

- **Pirâmide saudável:** muitos testes unitários, integração suficiente, E2E mínimo.
- **Eval-de-evals:** o motor de avaliação tem seus próprios testes determinísticos, com fixtures de score conhecido.
- **Test data realista:** seeds com traces parecidos com produção (não `"foo"/"bar"`).
- **CI bloqueante:** PR sem teste novo em código novo é rejeitado por convenção.

## 2. Pirâmide

```
                ┌─────────────┐
                │  E2E (poucos)│   Playwright: login → criar projeto → gerar key → ingestion → ver dashboard
                └─────────────┘
              ┌─────────────────┐
              │  Integration    │   pytest + httpx async client + Postgres efêmero (testcontainers)
              └─────────────────┘
            ┌──────────────────────┐
            │     Unit             │   pytest: services, evaluators, parsers, schemas
            └──────────────────────┘
                Property-based + fuzz onde valer (rubric YAML parser, idempotency keys)
```

Targets de cobertura (linha) por camada:
- `domain/`: ≥ 90%
- `infra/`: ≥ 70%
- `api/`: ≥ 80%
- Total ≥ 70% (NFR).

## 3. Backend (FastAPI/Python)

### 3.1 Stack
- `pytest`, `pytest-asyncio`, `pytest-cov`.
- `httpx.AsyncClient` para testar API.
- `testcontainers-python` para Postgres + Redis efêmeros (CI e local rápido).
- `respx` para mockar LLM (HTTP intercept) — evitar `unittest.mock` em chamadas reais.
- `hypothesis` para property tests de parsers e schemas.
- `factory_boy` ou Pydantic factories para fixtures.

### 3.2 Categorias de teste

**Unit (`tests/unit/`):**
- `domain/services/eval_service_test.py`: agregação de scores, fail_fast, weighted_mean.
- `domain/services/ingestion_test.py`: cálculo de custo, idempotência.
- `infra/llm/pricing_test.py`: contém todos os modelos esperados.
- `evaluators/llm_judge_test.py`: parser de saída JSON, retry on invalid.
- `evaluators/regex_match_test.py`, `keyword_presence_test.py`, etc.

**Integration (`tests/integration/`):**
- `api/traces_test.py`:
  - `test_ingest_batch_happy`
  - `test_ingest_idempotent_same_client_id`
  - `test_ingest_partial_failure_returns_per_item_errors`
  - `test_get_trace_with_spans_and_evals`
  - `test_delete_trace_lgpd`
- `api/evaluations_test.py`:
  - `test_run_rubric_persists_scores`
  - `test_run_rubric_judge_budget_exhausted_returns_error`
  - `test_re_run_returns_existing_run`
- `api/api_keys_test.py`: criação, validação, revogação, rate limit.
- `api/auth_test.py`: magic link e GitHub OAuth (mockado).
- `multitenancy_test.py`: cliente A não vê traces de cliente B em **toda** rota.

**E2E (`tests/e2e/` — Playwright):**
- Cenário completo: login → criar projeto → gerar key → curl ingestion → recarregar dashboard → ver trace.

### 3.3 Property-based / fuzz

```python
@hypothesis.given(yaml_source=rubric_yaml_strategy())
def test_rubric_parser_never_crashes(yaml_source: str):
    try:
        parse_rubric(yaml_source)
    except RubricValidationError:
        pass
```

Outros alvos:
- Idempotency keys com strings unicode estranhas.
- `client_trace_id` com whitespace, emoji, > 1024 bytes.

### 3.4 Eval-de-evals (meta-testes do engine)

`tests/evaluation/golden/`:
- 30 fixtures `(input.json, rubric.yaml, expected_score_range)` curados manualmente.
- Test garante: `score ∈ [low, high]` após rodar evaluator real (não mockado, mas com judge=`gpt-4o-mini` ou `gemini-flash`).
- Roda em **noturno** (não a cada PR), pois custa USD reais.
- Marker `@pytest.mark.live_eval`.

## 4. Frontend (Next.js)

### 4.1 Stack
- `vitest` + `@testing-library/react`.
- `playwright` para E2E.
- `msw` para mockar fetch.

### 4.2 Categorias
- **Unit/component:** componentes complexos (TraceTreeView, RubricEditor, FilterSidebar).
- **Integration:** páginas com data fetching (mock via msw).
- **E2E:** fluxos críticos com Playwright.

### 4.3 Acessibilidade
- `axe-core` em E2E para checar páginas principais.

## 5. SDK Python

### 5.1 Casos críticos
- Falha do servidor NUNCA propaga (NFR-11) — testar com `respx` retornando 5xx, 4xx, timeout.
- `disabled=True` é no-op real (sem network).
- Auto-instrument OpenAI captura tokens corretamente em `stream=True` e não-streaming.
- Background uploader respeita `flush_interval` e `max_batch`.
- Threading: stress test com 1000 traces concorrentes não perde nem duplica (em condições normais).

### 5.2 Compatibility matrix
- Python 3.9, 3.10, 3.11, 3.12 — matriz no GitHub Actions.
- `openai>=1.40`, `anthropic>=0.30`, `google-genai>=0.3` (lower bounds testados).

## 6. Performance / load

### 6.1 Targets
- `POST /v1/traces` p95 < 150ms (NFR-01).
- 200 traces/s por instância (NFR-02).

### 6.2 Ferramenta
- `k6` ou `locust`. Script em `tests/load/ingestion.js`.
- Cenário: 50 VUs ramping para 200, sustenta 5 min, relatório p50/p95/p99.

### 6.3 Quando rodar
- Manual antes de release de marco (fim de fase).
- Não bloqueante em CI (custo + flakiness).

## 7. CI

GitHub Actions com 4 jobs paralelos:

```yaml
jobs:
  lint:        # ruff, mypy, eslint, tsc
  test-api:    # pytest + cov + testcontainers
  test-web:    # vitest
  test-sdk:    # matrix py 3.9-3.12
  e2e:         # playwright (só em main e em PRs marcados com label e2e)
```

Bloqueia merge: `lint`, `test-api`, `test-web`, `test-sdk`. `e2e` é blocking só em main.

## 8. Test data / fixtures

- `tests/fixtures/traces/` com JSONs de traces realistas (3-5 fixtures cobrindo: happy, com erro, com fallback, com tool calls).
- `tests/fixtures/rubrics/` com YAMLs cobrindo cada tipo de evaluator.
- Seed dev (`scripts/seed_dev.py`): cria 1 user, 1 org, 1 project, 1 key, 50 traces sintéticos (gerados com Faker), 2 rubrics, 1 dataset.

## 9. Convenções de nome de teste

- `test_<unit>_<scenario>_<expected>`. Ex.: `test_aggregate_weighted_mean_returns_correct_value`.
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.live_eval`, `@pytest.mark.slow`.

## 10. Anti-patterns proibidos

- Mock de DB no test de service que **toca DB**. Use Postgres efêmero.
- Sleep/`time.sleep` em testes (use `freezegun` ou async wait).
- Skip permanente sem issue rastreador.
- Snapshot tests para JSON de API (frágeis); preferir asserts explícitos.
