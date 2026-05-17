# EvalOps Phase 7D — SDK Dead-Letter / Replay Spec

Date: 2026-05-17
Branch inspected: `main`
HEAD inspected: `227de7e`
Scope: specification, gap analysis, and future implementation plan only. No
productive code, SDK tests, backend, frontend, schema, migration, formatter,
commit, push, merge, rebase, or amend was performed for this document.

Primary sources:

- `docs/plans/evalops-phase7-next-steps.md`
- `docs/audits/evalops-phase7-status-after-7bc.md`
- `docs/plans/evalops-phase7-execution-plan.md` as historical context only
- `packages/sdk-python/evalops/uploader.py`
- `packages/sdk-python/evalops/__init__.py`
- `packages/sdk-python/tests/test_sdk.py`
- `packages/sdk-python/README.md`
- `40cf27a fix(evalops): harden sdk execution reliability`

This spec updates the old "SDK retry + dead-letter" wording. The retry/drop
part was already materially delivered by `40cf27a`; the remaining 7D work is
only the local dead-letter/replay gap, plus recorded product decisions around
durability, retention, and privacy.

## 1. Estado atual

The SDK already has a meaningful reliability layer and it must not be rebuilt
as part of updated 7D.

Implemented today in `packages/sdk-python/evalops/uploader.py`:

- `UploaderConfig` exposes `max_retries`, `retry_backoff_s`, `timeout`,
  `max_queue`, `max_batch`, `flush_interval`, and `submit_timeout_s`.
- `BackgroundUploader.submit()` uses a bounded queue and, when the queue is
  full, attempts a direct `_send()` fallback before incrementing drops.
- `_send()` retries exceptions, HTTP `408`, HTTP `429`, and HTTP `5xx`.
- `_send()` treats other HTTP `4xx` as permanent by returning `False` without
  retry.
- `flush()` drains buffered payloads with `requeue_on_failure=False`.
- `shutdown()` stops the worker, waits using `_shutdown_join_timeout()`, and
  only calls `flush()` after the worker stops.
- `_shutdown_join_timeout()` accounts for the retry budget, request timeout,
  and exponential backoff budget.
- `dropped_count` exposes the in-memory drop counter.

Existing SDK tests cover the important behaviors from `40cf27a`:

- exception retry then success;
- HTTP `5xx` retry exhaustion;
- `flush()` drains all batches;
- final send failure returns from `flush()` and increments `dropped_count`;
- final send failure returns from `shutdown()` and increments `dropped_count`;
- `shutdown()` waits for an in-flight `_send()` before returning;
- permanent `4xx` does not retry unnecessarily;
- queue-full fallback avoids silent drop when fallback send succeeds.

Observed gaps in public docs today:

- `packages/sdk-python/README.md` documents quickstart and `flush()`, but does
  not document retry/drop behavior, dead-letter durability, replay, local file
  storage, privacy implications, or an `EVALOPS_DEAD_LETTER_DIR` override.
- `packages/sdk-python/evalops/__init__.py` exports `init`, `trace`, `span`,
  `flush`, and `instrument_openai`; it does not export any replay helper.

Explicit non-goals for updated 7D:

- Do not redo retry/drop reliability from `40cf27a`.
- Do not reopen `flush()` or `shutdown()` unless a future implementation finds
  a concrete regression directly caused by dead-letter/replay.
- Do not change backend, frontend, schema, migrations, API contracts, or
  existing trace payload semantics.
- Do not turn examples into rigid production rules; examples belong in fixtures
  and tests, while the implementation should preserve model autonomy inside
  the SDK contracts and guardrails.

## 2. Gaps reais da 7D

| Gap | Evidence | Impact | Required for 7D? | Follow-up option |
|---|---|---|---|---|
| Local dead-letter is absent | `uploader.py` only increments `_dropped` and logs warnings after final failure; no dead-letter path, writer, or file format exists. | Retry-exhausted transient failures still lose telemetry after being counted. | Yes, if SDK telemetry durability remains in Phase 7. | Formally remove dead-letter from Phase 7 and document that `dropped_count` is the final contract. |
| Manual replay is absent | `evalops.__init__` exports no replay API; no `replay_dead_letter` hit exists in SDK code. | Operators cannot manually resend locally persisted failed batches because nothing is persisted or replayable. | Yes, if dead-letter is implemented. | Keep replay internal only if no public durability contract is accepted, but then README must say there is no supported replay. |
| Public durability docs are absent | SDK README has no section for retry, drop, dead-letter, replay, retention, or local payload sensitivity. | Users may assume `flush()` guarantees remote persistence when it only drains local queue and counts final drops. | Yes, if public env/API is added. | If no public dead-letter API ships, README should still document current retry/drop limitations. |
| Format and retention policy are absent in code | No file naming, JSON schema, retention, move/delete, or cleanup behavior exists. | Inconsistent future implementation could create unreadable files, unsafe retention, or replay ambiguity. | Yes before implementation. | Initial 7D decision: one JSON file per failed batch, remove after successful replay, keep files after failed replay or until manual deletion. |
| `Retry-After` is not honored | `_send()` retries `429`, but it sleeps only `retry_backoff_s * 2**attempt`; it does not read response headers. | The SDK can retry earlier than the API asks during rate limiting. | No, unless the user explicitly makes rate-limit politeness part of 7D. | Recommended follow-up after dead-letter/replay to avoid expanding retry logic. |
| Jitter is absent | `_send()` uses deterministic exponential sleep without randomness. | Many clients could synchronize retries under outage/load. | No, unless fleet-level thundering herd risk is in scope now. | Recommended follow-up with deterministic injectable randomness in tests. |

The old execution plan mentioned retry, jitter, dead-letter, `Retry-After`, and
replay together. Updated 7D should not blindly apply that older section because
current `main` already includes the retry/drop work.

## 3. Decisões técnicas propostas

### Diretório

Proposed default path: `~/.evalops/dead/`.

Proposed override: `EVALOPS_DEAD_LETTER_DIR`.

Behavior:

- Resolve the default path at write/replay time with `Path.home()`.
- Create the directory automatically when the first dead-letter file is written.
- Do not create the directory during `evalops.init()` just because the SDK was
  imported or initialized.
- Treat an invalid/unwritable directory as a warning plus an incremented drop,
  not as a crash path.

Final 7D decision: dead-letter is enabled by default only for final transient
failures after retries are exhausted. A final transient failure means exception,
HTTP `408`, HTTP `429`, or HTTP `5xx` after the existing retry budget is
exhausted. Permanent `4xx` failures must not generate dead-letter files by
default.

### Formato

Recommended format: one JSON file per failed batch.

Rationale:

- A failed `_send()` handles a batch, so one file per batch preserves the unit
  of replay without reconstructing batches from a shared log.
- Atomic replacement is simpler and safer per file than appending to a shared
  JSONL file from a background worker.
- A single JSON object can carry versioned metadata and payload without ad hoc
  parsing.

Recommended shape:

```json
{
  "version": 1,
  "created_at": "2026-05-17T00:00:00Z",
  "api_url": "https://example.com/v1",
  "trace_count": 2,
  "failure_kind": "retry_exhausted",
  "http_status": 503,
  "traces": []
}
```

Rules:

- Do not persist API keys.
- Do not persist `Authorization`.
- Do not persist `X-EvalOps-Key`.
- Do not persist arbitrary request headers.
- Do not persist URLs with embedded credentials. If URL parsing finds username,
  password, or credential-like userinfo, omit or redact the URL.
- Treat `api_url` in the file as informational metadata only. It must not be
  trusted as the replay destination by default.
- Recognize that trace payloads themselves can contain sensitive data,
  including PII or user-provided secrets. The SDK cannot reliably redact all
  application payloads without changing trace semantics.
- Include a `version` field so future replay can reject or migrate unknown
  formats explicitly.
- Include enough metadata for safe replay and debugging, but not enough to
  recreate secret-bearing config.

Rejected for initial 7D:

- Shared JSONL append file: harder to atomically update and remove successfully
  replayed batches.
- Batch-per-line JSONL: acceptable later, but it adds partial-file replay and
  compaction decisions that are not needed for first 7D.
- Remote bucket or database persistence: outside SDK-local scope.

### Escrita

Future implementation should add a small writer with these properties:

- Write to a tempfile in the target directory, flush and close it, then use
  `os.replace()` into the final filename.
- Use a filename that is unique without relying on payload content, for example
  UTC timestamp plus random hex or UUID.
- Never include payload content, token, or API key in logs.
- If directory creation, serialization, tempfile write, or `os.replace()` fails,
  log a safe warning and return. The caller must still complete `flush()` or
  `shutdown()` within the existing bounded behavior.
- The writer should run only on final failure paths. It must not add another
  retry loop around filesystem writes.

### Replay

Final 7D decision: `replay_dead_letter(...)` is a public exported SDK API and
must be documented in `packages/sdk-python/README.md` during implementation.

Proposed public API:

```python
evalops.replay_dead_letter(path: str | Path | None = None, *, api_url: str | None = None, api_key: str | None = None) -> ReplayResult
```

The exact dataclass names can be chosen during implementation, but the return
must be structured and testable. Recommended fields:

- `attempted_files`
- `replayed_files`
- `failed_files`
- `skipped_files`
- `removed_files`
- `errors`, with safe file-level error summaries that do not include payloads
  or secrets

Behavior:

- `path=None` means the configured/default dead-letter directory.
- `path` may be either a single file or a directory.
- Directory replay should process only recognized dead-letter JSON files.
- `api_key` must come from the explicit argument or current initialized tracer
  config. It must not be read from the dead-letter file.
- `api_url` must come from the explicit argument or current initialized tracer
  config by default. It must not come from the dead-letter file by default.
- `api_url` in the file may exist only as informational metadata for debugging.
  Do not trust host, scheme, or path from the file as replay destination.
- A future `trust_file_api_url=True` mode is explicitly out of scope for initial
  7D. If it is ever added, it must be opt-in, strongly validated, and reviewed
  as a security-sensitive feature.
- On success, remove the dead-letter file only after the remote send succeeds.
- On failure, keep the original file in place.
- Invalid or unknown-version files should be skipped with a safe error result.
- Tests must mock HTTP; no replay test should use real network.

Moving successful replay files to `.sent` or another archive is a follow-up,
not part of initial 7D, because it creates retention and cleanup duties.

### 4xx permanente

Final 7D decision: permanent `4xx` failures other than `408` and `429` should
not write dead-letter by default.

Rationale:

- Permanent `4xx` usually means invalid payload, authentication failure,
  authorization failure, or request too large.
- Persisting those payloads locally by default can retain data that is unlikely
  to ever be accepted without code/config changes.
- Auth failures must not cause secret-bearing config to be persisted; even
  though the proposed format omits API keys, the trace payload may still be
  sensitive.
- This matches the historical plan's conservative stance that `422` should not
  retry and should not dead-letter.

Required test: a permanent `401` or `422` should make one HTTP attempt, not
retry, increment drop count through the existing final failure path, and not
create a dead-letter file.

Optional future API: allow an explicit opt-in flag for permanent-4xx
dead-letter only if debugging rejected payloads becomes a real support need.

### Retry-After / jitter

Current state:

- `Retry-After` is not parsed or honored.
- Jitter is not present.
- `retry_backoff_s` and exponential retry are present.

Final 7D decision:

- Do not include `Retry-After` or jitter in the initial dead-letter/replay PR.
- Record them as follow-ups unless a critical discovery during implementation
  makes rate-limit politeness or fleet thundering-herd mitigation necessary in
  the same PR.
- If they enter scope, keep them narrow and testable:
  - parse numeric `Retry-After` seconds for `429`;
  - cap sleep to a bounded maximum;
  - keep tests deterministic by monkeypatching sleep and randomness;
  - update `_shutdown_join_timeout()` if new sleep math changes the retry
    budget.

## 4. Segurança e privacidade

Dead-letter changes the SDK from "drops after final failure" to "persists failed
payload locally". That is a material privacy and operational change.

Risks:

- Trace payloads can contain PII, user prompts, model outputs, business data,
  or secrets supplied by application code.
- Dead-letter files persist data after process exit.
- Replay can resend old data that the user may no longer expect to transmit.
- Replay can duplicate traces or ingest if the backend accepts repeated payloads.
  Initial 7D makes no exactly-once delivery promise; dedupe depends on an
  explicit backend/idempotency contract if one exists.
- Local file permissions depend on the host OS, user account, filesystem, and
  deployment environment.
- Logs can accidentally leak payloads if implementation logs exceptions or file
  contents carelessly.

Guardrails:

- Never log trace payloads.
- Never log API keys, `Authorization`, or `X-EvalOps-Key`.
- Never persist API keys or secret headers.
- Never persist URL userinfo or credential-bearing URLs.
- Use safe warning messages with counts, file paths, and failure type only.
- README must state that dead-letter files may contain sensitive trace payloads.
- README must document the default location and override.
- README must warn that replay may transmit old data and may duplicate traces or
  ingest; operators should review old payloads before replaying them.
- Do not add backend/frontend/schema changes to solve local SDK retention.

Suggested local permission posture:

- Create directories/files using normal user permissions and document that
  operators should secure the directory according to their environment.
- If implementation sets mode explicitly, prefer owner-only permissions where
  portable, but do not pretend this is a complete security boundary on all
  platforms.

## 5. Plano de implementação futura

Likely files:

- `packages/sdk-python/evalops/uploader.py`
- `packages/sdk-python/evalops/__init__.py`, if replay is public
- `packages/sdk-python/tests/test_sdk.py`
- `packages/sdk-python/README.md`
- `docs/plans/evalops-phase7d-sdk-dead-letter-spec.md`

Steps for a future implementation prompt:

1. Add dead-letter config/path resolution without changing existing public SDK
   calls.
2. Add an atomic dead-letter writer with a versioned one-JSON-file-per-batch
   format.
3. Connect the writer only to final transient failure/drop paths, preserving
   existing retry/drop behavior and bounded `flush()`/`shutdown()`.
4. Add replay support that reads dead-letter files, resubmits with explicit or
   current SDK credentials and destination config, ignores file `api_url` as a
   destination by default, and removes files only after success.
5. Export `replay_dead_letter(...)` from `packages/sdk-python/evalops/__init__.py`.
6. Update `packages/sdk-python/README.md` with retry/drop, dead-letter path,
   replay usage, privacy warnings, and duplicate-ingest warning.
7. Add focused SDK tests using `tmp_path`, monkeypatching, and no real network.
8. Run targeted validations for the SDK; do not run global formatters.
9. Require code review before commit, then commit/push from a dedicated branch
   only after approval.

Implementation constraints:

- Preserve current `init`, `trace`, `span`, `flush`, and `instrument_openai`
  behavior.
- Preserve `dropped_count`.
- Preserve current retry policy for exceptions, `408`, `429`, and `5xx`.
- Preserve permanent-4xx no-retry behavior.
- Do not hardcode fixture payloads as production rules.
- Do not change backend, frontend, schemas, migrations, or deployment files.

## 6. Testes obrigatórios futuros

Required tests for the future 7D implementation:

- Retry-exhausted transient failure writes one dead-letter file.
- `EVALOPS_DEAD_LETTER_DIR` overrides the default directory.
- Replay reads a dead-letter file, resends it, and removes the file on success.
- Replay keeps the file when resend fails.
- A dead-letter file adulterated with a malicious `api_url` does not change the
  replay destination by default; replay uses explicit `api_url` or current SDK
  config.
- Dead-letter write errors do not hang or crash `flush()`/`shutdown()`.
- `flush()` and `shutdown()` remain bounded.
- Existing retry/drop tests continue passing.
- Logs do not include payload, token, API key, `Authorization`, or
  `X-EvalOps-Key`.
- Permanent `4xx` policy is covered, including no retry and no default
  dead-letter file.
- If `Retry-After` enters scope, tests cover numeric `Retry-After` on `429`
  with monkeypatched sleep.
- If jitter enters scope, tests cover deterministic jitter by monkeypatching
  randomness and by updating shutdown budget expectations if needed.
- No test uses real network for dead-letter or replay.
- `tmp_path` is used for all dead-letter filesystem tests.
- README documentation warns that replay can duplicate traces/ingest and does
  not promise exactly-once delivery.

Suggested command after implementation:

```bash
cd packages/sdk-python && python -m pytest tests -q --tb=short
```

For this documentation-only pass, pytest is intentionally not run.

## 7. Critérios de aceite da 7D

7D is complete only when:

- Local dead-letter is implemented, or formally removed from Phase 7 with a
  written rationale.
- Manual replay is implemented and documented, or formally removed from Phase 7
  with a written rationale.
- The permanent `4xx` versus transient-failure policy is explicit and tested.
- Replay ignores file `api_url` as a destination by default and uses explicit
  `api_url` or current SDK config.
- README is updated for the public env var, public replay API, public durability
  behavior, sensitive local payload risk, and duplicate-ingest risk.
- SDK tests pass.
- Existing retry/drop reliability from `40cf27a` remains intact.
- Code review is approved.
- Commit and push happen from a dedicated implementation branch, not from this
  documentation-only pass.

## 8. Decisões registradas e follow-ups

Resolved for initial 7D:

- Dead-letter is enabled by default only for final transient failures:
  exceptions, HTTP `408`, HTTP `429`, and HTTP `5xx` after retries are
  exhausted.
- Permanent `4xx` failures do not generate dead-letter files by default.
- `replay_dead_letter(...)` is a public exported SDK API.
- Successful replay removes the dead-letter file in initial 7D.
- The dead-letter file `api_url` is informational metadata only and is not
  trusted as the replay destination by default.

Non-blocking follow-up decisions:

- Should `Retry-After` be included in the implementation PR?
  - Recommended answer: no, unless rate-limit politeness is explicitly needed
    now.
- Should jitter be included in the implementation PR?
  - Recommended answer: no, unless fleet-scale synchronized retries are a
    current concern.
- Should there be automatic retention cleanup?
  - Recommended answer: no for initial 7D; document manual deletion and remove
    files after successful replay.
- Should successful replays be archived under `.sent`?
  - Recommended answer: no for initial 7D; keep as retention follow-up.
- Should replay ever support `trust_file_api_url=True`?
  - Recommended answer: no for initial 7D. If needed later, it must be explicit
    opt-in with strong validation and security review.

## 9. Próximo prompt recomendado

The blocking product/security decisions for initial 7D are now recorded in this
spec. Recommended next implementation prompt:

```text
Você está no EvalOps em main. Implemente apenas a 7D atualizada conforme
docs/plans/evalops-phase7d-sdk-dead-letter-spec.md. Preserve o retry/drop já
entregue em 40cf27a, não refaça flush/shutdown, não altere backend/frontend/
schema/migrations, adicione testes focados sem rede real, atualize README se
exportar replay/env pública, rode apenas validações SDK e não faça commit/push.
```
