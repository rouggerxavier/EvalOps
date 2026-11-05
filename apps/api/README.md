# EvalOps API

FastAPI backend for EvalOps Studio.

## Implemented scope

- Identity and tenancy: users, orgs, projects, memberships
- API keys: create/list/revoke with hashed storage
- Tracing: ingest/list/detail/delete
- Analytics overview
- Rubrics and evaluations (sync)
- Prompts, datasets, experiments
- Human feedback and JSONL exports
- Usage counters and mock quotas

## Run locally

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -c requirements.lock -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

After changing dependencies, regenerate the versions pinned by `requirements.lock`:

```bash
uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -o requirements.lock
```

## Measuring an agent

Rubric evaluators must point to a known path (`trace.output.text`,
`trace.conversation.transcript`, `trace.metadata.*`). An evaluator with nothing to
read, or that fails to run, records an `error`, stays out of the score and leaves
the verdict empty instead of failing the answer. Runs with an error, or partial
runs, can be evaluated again; what they spent stays in the judge budget.

The judge model picks the provider by prefix, with the key in the environment:
`openai/` (`OPENAI_API_KEY`), `openrouter/` (`OPENROUTER_API_KEY`), `gemini/`
(`GEMINI_API_KEY`), `groq/` (`GROQ_API_KEY`). Its cost is an estimate from text
length, and a model outside the price table uses a high fallback price, so set
`cost_cap_usd` in the evaluator config. `repeats` (1 to 5) calls the judge several
times and records the spread in `stddev`. A judge that returns `"flags": ["slug"]`
triggers `critical_flags` with `auto_fail` and `automatic_fail_conditions` on `flag`.

With Redis and the worker running, evaluate many traces and read the results:

```text
POST /v1/projects/{id}/evaluations/batch        {"rubric_id": "...", "batch": "bateria-1"}
GET  /v1/projects/{id}/rubrics/{rubric_id}/report?window=30d&batch=bateria-1
```

Both accept a member's token or `X-EvalOps-Key`. The batch route needs a key
created with the `evaluate` scope, which is never a default; the report needs `read`.

Every organization starts on the `free` plan (1000 traces and 500 evaluations per
month). Operators change one organization's limits with:

```bash
python scripts/set_org_limits.py --org my-org --traces 100000 --evals 20000
```

Health and docs:

- `GET /health/liveness`
- `GET /health/readiness`
- `GET /docs`

## Test

```bash
pytest -q
```

Phase-based suites:

- `tests/test_phase1_identity_access.py`
- `tests/test_phase2_tracing.py`
- `tests/test_phase3_analytics.py`
- `tests/test_phase4_rubrics_eval.py`
- `tests/test_phase5_prompts_datasets_experiments.py`
- `tests/test_phase6_feedback_export_usage.py`
- `tests/test_phase7_e2e_mvp_flow.py`

## Release smoke

```bash
python scripts/smoke_hosted.py --base-url http://localhost:8000
```

## Juiz local por CLI (`cli:claude`, `cli:codex`)

Usa as CLIs `claude` e `codex` já logadas na máquina como `llm_judge`, na cota do seu plano, sem chave de API.
É para uso pessoal e local: nunca em produto hospedado nem em Docker de produção. Para gate contínuo, use um provider HTTP pago.
Os termos dos planos não foram verificados; confira se o seu uso é permitido.

Para ligar, nos processos da API e do worker:

```bash
APP_ENV=local
EVALOPS_CLI_JUDGE_ENABLED=1
EVALOPS_CLI_JUDGE_TIMEOUT_SECONDS=120   # opcional
EVALOPS_CLI_JUDGE_LOCK_WAIT_SECONDS=150 # opcional
```

Escolha o juiz na tela de Rubricas ou fixe o modelo no YAML. O modelo é obrigatório:

```yaml
config:
  model: cli:claude/claude-sonnet-5-5
  prompt: "Avalie de 0 a 1 e responda só com JSON {\"score\": <n>}: {{ trace.output.assistant_message }}"
```

Comportamento:

- **Bloqueio:** sem a env ou fora de `APP_ENV=local`, nada é executado e a opção fica indisponível na tela.
- **Isolamento:** prompt por stdin, sem shell, em diretório temporário vazio, com ambiente em allowlist. Por isso `ANTHROPIC_API_KEY` e `OPENAI_API_KEY` não chegam à CLI.
- **Claude:** `--tools ""`, `--safe-mode`, `--strict-mcp-config`.
- **Codex: desabilitado.** Na versão 0.163.0, `apply_patch` não tem como ser desligado (`include_apply_patch_tool` é ignorado) e não dá para ler a lista de ferramentas oferecidas. Toda chamada retorna `cli_judge_tools_not_disabled` sem executar. O código fica pronto (`_TOOLS_CANNOT_BE_DISABLED` em `cli_judge.py`) para quando houver como provar o isolamento; a última barreira rejeita a nota com `cli_judge_tool_used` se aparecer item de ferramenta.
- **Serial:** um lock de arquivo faz API e workers `arq` esperarem na mesma fila. Quem passa do limite recebe `cli_judge_busy`.
- **Não mediu:** timeout, rate limit, CLI ausente, login expirado e saída inválida viram `error`, nunca reprovação. A saída da CLI não é gravada, só um código estável.
- **Custo:** `cost_usd` fica `NULL` (migration `0009`), a tela mostra "—" e o orçamento do juiz não é consumido nem bloqueia.
- **Rastreio:** `raw_output.judge_cli` guarda provider, modelo e versão da CLI em cada nota.

Limites:

- `temperature` é ignorada.
- Experimentos e replay recusam `cli:*`: experimentos contam falha de avaliador como nota 0.
- A tela não sabe se o login expirou, pois verificar gastaria cota. Isso aparece ao avaliar.
- Uma rubrica com `repeats` ou retentativas pode passar do `job_timeout` de 300s do `arq`.
- O total de custo do relatório de rubrica soma só custos conhecidos.
- Não mande conversa real de cliente: o texto sai para o provedor da CLI.
