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

## Fase 1 — P0 segurança/configuração (re-implementação 2026-05-14)

### Status
✅ **Re-implementada** (commit desta sessão). Fases 1+2 antigas estavam ausentes
no checkout; descoberta documentada na seção "Pendências de baseline" abaixo.
Fase 1 foi refeita nesta sessão; **Fase 2 continua ausente** e bloqueia Fase 4.

### Gaps fechados
- **G-02** — raw API key não vaza em URL. Fluxo agora usa cookie HttpOnly de
  uso único (`apps/web/lib/flash.ts`). `createApiKeyAction` redireciona com
  apenas `?created=1`; `keys/page.tsx` consome o flash via
  `consumeApiKeyFlash()` e o cookie é apagado na leitura.
- **G-03** — fallback bearer só em dev com `EVALOPS_DEV_MODE=1`. Implementado
  em `apps/web/lib/auth.ts` via helper `isDevMode()` de
  `apps/web/lib/config.ts`. Em prod, fallback é ignorado mesmo com env
  presente. `EVALOPS_DEV_MODE` precisa ser literalmente `"1"`.
- **G-04** — `EVALOPS_API_BASE_URL` validado em produção:
  `apps/web/lib/config.ts:getApiBaseUrl()` throws `ApiBaseUrlError` em prod
  quando ausente/vazio/localhost/127.0.0.1. Em dev, defaulta para
  `http://localhost:8000/v1` como antes. Páginas marketing (`/docs`,
  dashboard) capturam o erro e renderizam placeholder `#` para não quebrar
  build local — fail-loud real fica em `lib/api.ts`/`lib/auth.ts` que são os
  caminhos de chamada real à API.
- **G-17** — body size limit + spans cap. Middleware em `apps/api/app/main.py`
  retorna 413 quando body > `EVALOPS_MAX_BODY_BYTES` (default 8 MB). Ingest
  em `routes.py` retorna 422 com `detail.error="too_many_spans"` quando trace
  excede `EVALOPS_MAX_SPANS_PER_TRACE` (default 500). Defaults e getters em
  `apps/api/app/config.py`.

### Arquivos alterados
- `apps/api/app/config.py` (novo) — getters lazy de env.
- `apps/api/app/main.py` — middleware `body_size_limit`.
- `apps/api/app/api/routes.py` — pre-check de spans cap em `POST /v1/traces`.
- `apps/api/tests/test_phase8_p0_security.py` (novo) — 5 testes G-17.
- `apps/web/lib/config.ts` (novo) — `getApiBaseUrl`, `isDevMode`,
  `isProduction`, `ApiBaseUrlError`.
- `apps/web/lib/flash.ts` (novo) — flash cookie one-shot.
- `apps/web/lib/auth.ts` — `hasFallbackToken` gated, base URL lazy.
- `apps/web/lib/api.ts` — base URL lazy via `getApiBaseUrl()`.
- `apps/web/lib/actions.ts` — `createApiKeyAction` usa flash cookie.
- `apps/web/app/o/[org]/p/[project]/keys/page.tsx` — consome flash.
- `apps/web/app/docs/page.tsx` + `apps/web/app/o/[org]/p/[project]/page.tsx`
  — `apiRoot()` lazy com fallback `#` para não quebrar build local.
- `apps/web/tests/security.test.mjs` (novo) — 13 testes G-02/G-03/G-04
  (`node --test`).

### Como o fluxo de API key one-shot funciona
1. Usuário submete form em `/o/<org>/p/<proj>/keys`.
2. `createApiKeyAction` chama `POST /v1/projects/:id/api-keys`.
3. Sucesso: `setApiKeyFlash({ key, prefix })` grava cookie `evalops_api_key_flash`
   com `HttpOnly`, `SameSite=lax`, `Secure` (em prod), `Max-Age=60s`.
4. `redirect(path + "?created=1")` — URL **nunca** contém o segredo.
5. `keys/page.tsx` chama `consumeApiKeyFlash()` apenas se `qp.created` —
   cookie é lido e imediatamente apagado (set com `Max-Age=0`).
6. Refresh da página sem o cookie não exibe o segredo. Phishing-style URLs
   com `?key=...` não funcionam mais (page não lê `qp.key`).

### Como fallback bearer foi bloqueado em produção
- `isDevMode()` retorna `false` se `NODE_ENV === "production"` mesmo com env
  setada.
- `hasFallbackToken()` = `isDevMode() && Boolean(FALLBACK_TOKEN)`.
- `getAuthToken()` em `auth.ts` ignora `FALLBACK_TOKEN` quando `!isDevMode()`.
- Resultado: prod só aceita JWT de sessão real, nunca `EVALOPS_DASHBOARD_BEARER_TOKEN`.

### Como base URL é validada em produção
- `getApiBaseUrl()` em `config.ts`:
  - em prod, sem env ou env vazia → `ApiBaseUrlError("missing")`.
  - em prod, URL com hostname `localhost`/`127.0.0.1` → `ApiBaseUrlError("localhost")`.
  - em dev, defaulta para `http://localhost:8000/v1`.
- Chamado dentro de `api.ts`/`auth.ts` per-request → fail-loud em runtime.
- `/docs` e `/o/[org]/p/[project]/page.tsx` envolvem em try/catch → href
  vira `#` para não quebrar `next build` local sem env.
- **Trade-off documentado**: `next build` com `NODE_ENV=production` mas sem
  `EVALOPS_API_BASE_URL` continuará compilando (placeholder), mas qualquer
  chamada real à API em runtime vai falhar com mensagem clara. Para
  garantir falha de build em pipeline CI, validar env em script `prebuild`.

### Como body size limit e spans cap funcionam
- Middleware `body_size_limit` em `main.py`:
  - lê `Content-Length`; se presente e maior que `max_body_bytes()` → 413
    sem ler body.
  - se ausente ou indeterminado (chunked), buffera body e mede tamanho.
  - retorna `{"detail": "payload_too_large", "limit_bytes": <int>}` com 413.
  - **Limitação documentada**: chunked upload com `Content-Length` ausente
    é buferizado in-memory — recomenda-se cap adicional no reverse proxy
    em prod.
- Spans cap em `routes.py:ingest_traces`:
  - antes de qualquer persistência, itera `payload.traces` e levanta
    `HTTPException(422)` quando `len(trace.spans) > max_spans_per_trace()`.
  - payload de erro: `{"error": "too_many_spans", "trace_index", "client_trace_id", "spans", "limit"}`.

### Comandos executados e resultados

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 6.31s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py -q --tb=short -p no:warnings
```
**Resultado**: `10 passed in 7.56s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```
**Resultado**: `8 passed in 8.32s` ✅ (Fase 3 não regrediu).

### Frontend — validação não executada nesta sessão

`npx tsc --noEmit && npm run build && npm run test` **não executou** porque
**Node.js não está instalado nesta máquina**. As mudanças TS foram revisadas
manualmente e os testes em `apps/web/tests/security.test.mjs` cobrem a
lógica canônica via re-implementação em JS plano (documentado no header do
arquivo).

**Risco assumido**: erro de tipo TS ou falha de build poderia escapar até
o próximo PC com Node disponível. Recomendado: rodar
`npx tsc --noEmit && npm run build && npm run test` no PC que tem Node
antes de mergear / fazer deploy de qualquer ambiente real.

### Riscos remanescentes (Fase 1)

1. **Frontend não validado por compilador**: trade-off acima.
2. **`next build` local não falha** em prod-NODE_ENV sem env. Decisão
   intencional para não quebrar dev/CI sem env; chamada real à API
   continua falhando loud. Adicionar gate em CI explicitamente se quiser
   fail-build.
3. **Middleware buffera body sem Content-Length**: cap adicional no
   reverse proxy recomendado em prod.
4. **Flash cookie TTL 60s**: usuário muito lento perde o segredo. Aceitável
   pelo trade-off (one-shot). Pode ser ajustado.
5. **`/docs` e dashboard com `apiRoot()=#`** quando env inválida: silenciosamente
   renderiza links broken. Bandeira de UX, não de segurança.

### Fase 2 — continua ausente e bloqueia Fase 4

G-01 (rate limit API key), G-13 (rate limit /login), G-15 (logout server-side),
G-16 (audit `auth.failed_login`) **não estão implementados** neste checkout.
Roadmap antigo (`1c57ae0`) afirmava conclusão sem evidência no código. Não
foi escopo desta sessão refazer Fase 2. **Não é seguro avançar para Fase 4
até Fase 2 ser refeita** (pré-requisito de hardening de auth + audit base).

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
