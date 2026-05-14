# Baseline de Validação — EvalOps

Documento de snapshot dos comandos de validação e resultados executados em cada fase
do roadmap (`docs/plans/evalops-remediation-roadmap.md`).

> **Nota de recriação (2026-05-14)**: este arquivo foi reconstruído após perda de
> commit em PC anterior. O conteúdo aqui registra a validação da **Fase 3**
> conforme o estado atual do código no branch `main`. Snapshots das Fases 0, 1 e
> 2 — se necessários — devem ser reconstituídos a partir do histórico
> (`git log --oneline`) e dos próprios testes `test_phase8_p0_security.py` /
> `test_phase9_auth_hardening.py`, que **não estão presentes** neste checkout
> (ver "Pendências de baseline" abaixo).

---

## Workaround SQLite (obrigatório em todas as execuções backend)

A suíte completa `pytest apps/api/tests -q` apresenta falhas intermitentes por
**SQLite database is locked** quando rodada sem reset do arquivo entre arquivos
de teste. Workaround obrigatório:

```bash
cd apps/api && rm -f evalops.db* && python -m pytest <alvos> -q --tb=short -p no:warnings
```

Sempre apagar `evalops.db*` antes de cada invocação do `pytest`. Executar
arquivos em grupos pequenos (≤ 8 arquivos por chamada) para mitigar o lock.
A suíte completa em uma única chamada **ainda não é confiável** — esta
limitação fica registrada como dívida até a Fase 6 (G-25, Postgres em prod) ou
Fase 7 (isolamento de DB por worker / fixtures).

---

## Fase 3 — Experiments reais (validação 2026-05-14)

### Status
✅ **Concluída** (commits `da11b2c`, `72a9923`, `1c57ae0`).

### Evidências de implementação no código

- `apps/api/app/domain/services/experiment_service.py` (novo, 384 LOC).
  - `validate_variants()` — garante nomes únicos e `baseline_variant ∈ variants`.
  - `_resolve_prompt_version()` — aceita id, `slug@version` ou slug
    (resolve para `current_version`).
  - `_synthesize_variant_output()` — renderiza template Jinja com
    `{user_message, ...}` e anexa `[model=... params=...]` para garantir
    divergência mesmo sem `prompt_version_ref`.
  - `execute_experiment()` — para cada item × variant: resolve template →
    sintetiza output → roda rubric sobre output sintetizado → agrega métricas
    (`pass_rate`, `avg_score`, `avg_latency_ms`, `total_cost_usd`,
    `avg_cost_usd_per_item`) → compara contra baseline → checa
    `pass_criteria`. Formato de resposta (`by_variant`, `comparisons`,
    `criteria_failures`, `run_metadata`) preservado.
- `apps/api/app/api/routes_phase5.py` — agora importa
  `execute_experiment` e `validate_variants`; rota `POST /experiments/{id}/run`
  delega ao service e captura `ExperimentValidationError` como `422`.
- `apps/api/tests/test_phase5_prompts_datasets_experiments.py` — cobre
  variants divergentes, variants idênticas (delta zero) e validação de
  baseline (commit `72a9923`).
- `docs/plans/evalops-remediation-roadmap.md` — linha de status da Fase 3
  marcada como `✅ Concluída (2026-05-14)`.

### Frontend
Não houve alteração em `apps/web` na Fase 3. **Não foi necessário rodar build
frontend** (`npx tsc --noEmit && npm run build && npm run test` dispensado).

### Comando primário da Fase 3

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```

**Resultado**: `8 passed in 8.81s` ✅

### Regressão das Fases 1 e 2

> ⚠️ Os arquivos `tests/test_phase8_p0_security.py` e
> `tests/test_phase9_auth_hardening.py` referenciados no roadmap como evidência
> das Fases 1 e 2 **não estão presentes** neste checkout. Provavelmente foram
> commitados no PC anterior e ainda não chegaram a `main`. A regressão foi
> rodada com os arquivos existentes:

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py -q --tb=short -p no:warnings
```

**Resultado**: `10 passed in 7.32s` ✅ (4 arquivos / 10 testes — ausência de
phase8/phase9 registrada como pendência).

### Validação adicional

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```

**Resultado**: `5 passed in 6.14s` ✅

### Resumo de execução

| Suíte | Arquivos | Testes | Resultado | Tempo |
|---|---|---|---|---|
| Fase 3 primária | 1 | 8 | ✅ pass | 8.81s |
| Regressão Fases 1 e 2 (parcial) | 4 | 10 | ✅ pass | 7.32s |
| Validação adicional (Fases 3/6/7) | 3 | 5 | ✅ pass | 6.14s |
| **Total executado** | **8** | **23** | **✅ pass** | **~22s** |

### Riscos remanescentes

1. **Phase 3 não exercita LLM real**: o output sintetizado é determinístico
   (`render + [model=... params=...]`). Comparações A/B refletem diferença de
   *config*, não de *qualidade de modelo*. Execução com LLM real fica para
   Fase 7 (worker assíncrono) — fora de escopo do MVP.
2. **`prompt_version_ref` ausente**: variants sem ref usam template-default
   `{{ user_message }}`. Continua produzindo divergência se `model` ou `params`
   diferem, mas variants com tudo idêntico produzem score idêntico (já
   coberto por teste).
3. **`pass_criteria` sem range checks**: valores absurdos (`min_pass_rate=2.0`)
   silenciosamente falham toda variant. Sem validação na criação. Follow-up
   sugerido para Fase 5 (contratos).
4. **SQLite lock em suíte completa** (ver workaround acima): a suíte
   completa em uma única invocação ainda não é confiável; rodar em grupos.
   Solução estrutural depende da Fase 6 (Postgres em prod) ou Fase 7
   (fixtures isoladas por arquivo).
5. **Sem cobertura concorrente**: dois runs simultâneos do mesmo experiment
   não foram testados. Item de risco apenas se múltiplos workers entrarem em
   produção (não é o caso do MVP single-worker).

### Pendências de baseline

- Recuperar / recriar `tests/test_phase8_p0_security.py` (Fase 1) e
  `tests/test_phase9_auth_hardening.py` (Fase 2). O roadmap aponta 5/5 e
  13/13 testes respectivamente — não foi possível validar nesta sessão.
- Considerar incluir nas próximas execuções de regressão um comando
  consolidado da Fase 1 (G-02, G-03, G-04, G-17) e Fase 2 (G-01, G-13, G-15,
  G-16) assim que os arquivos estiverem no branch.

### Pode avançar para Fase 4?

✅ **Sim, do ponto de vista da Fase 3**: implementação presente, testes verdes,
contrato de resposta preservado, sem regressão nas suítes adjacentes.

⚠️ **Ressalva**: antes de iniciar a Fase 4 vale recuperar os testes
`test_phase8` e `test_phase9` ausentes — caso contrário a matriz de regressão
da Fase 4 também ficará incompleta. Não é bloqueante para a Fase 3, mas é
bloqueante para garantir que as Fases 1 e 2 continuam verdes durante o
desenvolvimento da Fase 4.
