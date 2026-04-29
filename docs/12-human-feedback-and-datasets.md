# 12 — Human Feedback & Datasets

## 1. Por que isso importa

Feedback humano é o que **calibra** os autoavaliadores e **vira combustível** para fine-tuning, few-shot e DPO. Sem pipeline para coletar e exportar, qualquer eval automático fica sem chão.

## 2. Fontes de feedback

| Fonte | Como entra | Latência |
|---|---|---|
| **End-user (👍/👎)** | Frontend do app cliente chama `evalops.feedback(...)` ou `POST /v1/traces/{id}/feedback` | imediata |
| **Reviewer interno** | Dashboard EvalOps, fila de revisão | manual |
| **Auto-flagging** | Trace com score < 0.5 OU erro OU thumbs down → entra na fila de revisão | sistema |
| **Anotação em batch** | Reviewer abre dataset e anota items para criar golden-set | manual |

## 3. Modelo de feedback

```json
{
  "trace_id": "tr_01HX...",
  "source": "end_user",
  "thumbs": "down",
  "rating": null,
  "comment": "respondeu errado o horário da loja",
  "tags": ["alucinacao", "horario"],
  "corrected_response": null,
  "user_ref": "u_anon_a1b2"
}
```

Para reviewers internos:
```json
{
  "trace_id": "tr_01HX...",
  "source": "reviewer",
  "rating": 2,
  "thumbs": "down",
  "comment": "Esquece o contexto do usuário",
  "tags": ["context_loss"],
  "corrected_response": "Resposta ideal: ...",
  "reviewer_id": "usr_..."
}
```

Ver [`examples/human-feedback-example.json`](examples/human-feedback-example.json).

## 4. Endpoints

```
POST /v1/traces/{id}/feedback         # criar
GET  /v1/traces/{id}/feedback         # listar
POST /v1/traces/search/needs-review   # fila de revisão (filtros: score<X, sem feedback, etc)
```

## 5. SDK helpers

```python
# Em backend (após receber thumbs do frontend do app cliente):
evalops.feedback(
    trace_id=trace_id,
    source="end_user",
    thumbs="down",
    comment=comment,
    tags=["misinformation"],
    user_ref=hash(user_id),
)
```

JS pequeno opcional (`@evalops/web`, futuro):
```js
import { feedback } from "@evalops/web";
await feedback({ traceId, thumbs: "up" });   // dispara para o backend do app, não direto para EvalOps
```
**Importante:** SDKs web NUNCA carregam API key. Cliente web → backend cliente → EvalOps.

## 6. Review Queue (UI)

Tela `/o/{org}/p/{project}/review` (Recomendado, MVP-light):
- Fila de traces flagged: ordenação configurável (score asc, thumbs down primeiro, sem feedback).
- View focada: input + output + raw JSON + form de feedback à direita.
- Atalhos `j/k` para próximo, `1-5` para rating, `t` para tag rápida.
- "Approve as golden" → adiciona a um dataset escolhido.

## 7. Datasets

### 7.1 Tipos
- **Golden set / regression:** pares (input, expected) curados para regression test.
- **Eval set:** amostras representativas para experiments (sem expected; rubrica julga).
- **Fine-tuning set:** export de pares (input, ideal_output) baseado em feedback positivo + corrections.
- **DPO/RLHF set (Futuro):** pares (chosen, rejected) baseados em feedback negativo + correction.

### 7.2 Construção
1. **Manual:** UI ou API `POST /v1/datasets/{id}/items`.
2. **From traces:** filtros (score range, tags, date) → cria items espelhando inputs/outputs do trace.
3. **From feedback:** filtros sobre feedback (rating ≥ 4, thumbs up) → cria items.
4. **Upload:** JSONL upload (Futuro).

### 7.3 Schema de DatasetItem
```json
{
  "id": "di_01HX...",
  "input": {
    "messages": [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "..."}
    ],
    "context": { "kb_docs": ["..."], "user_profile": "..." }
  },
  "expected_output": {
    "assistant_message": "...",
    "intent": "track_order"
  },
  "metadata": { "source_trace_id": "tr_...", "tags": ["high_value"] }
}
```

`expected_output` é livre (depende da rubrica que vai usar). Convenção: `assistant_message` para texto único; `intent`, `entities`, `tool_calls` para casos estruturados.

## 8. Export

### 8.1 Endpoint
`POST /v1/exports { project_id, filters, format }`

### 8.2 Formatos suportados (MVP)

#### `jsonl_chat` (default — compatível OpenAI fine-tuning)
```jsonl
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
{"messages": [...]}
```

#### `jsonl_dpo` (Futuro — pares chosen/rejected)
```jsonl
{"prompt": "...", "chosen": "...", "rejected": "..."}
```

#### `csv` (para análise no Sheets/Excel)

### 8.3 Compatibilidade HuggingFace
JSONL chat carrega direto:
```python
from datasets import load_dataset
ds = load_dataset("json", data_files="export.jsonl", split="train")
```

### 8.4 Filtros de export
```json
{
  "from": "2026-04-01", "to": "2026-04-30",
  "score_range": [0.7, 1.0],
  "thumbs": "up",
  "tags_any": ["resolved"],
  "tags_none": ["pii_leaked"],
  "models": ["openai/gpt-4o-mini"],
  "deduplicate_by": "input_hash",
  "limit": 5000
}
```

### 8.5 Export job lifecycle
```
[create export_job status=queued, return id]
[worker picks up]
[server-side cursor query, stream to NDJSON file in /tmp]
[gzip → upload to R2]
[generate signed URL TTL 24h]
[update job: status=ready, url, row_count, size_bytes]
```

Falha → `status=error` com error.message. Cliente faz polling `GET /v1/exports/{id}` ou recebe webhook (Futuro).

## 9. Privacidade no export

- Se projeto tem `redaction_enabled=true`, redaction (Presidio) roda **em export** (não duplicada em ingestion). Trade-off: armazena raw, exporta limpo.
- Filtro `redact_pii: true` força redaction independente da config do projeto.
- `user_ref` é mantido como hash; nunca exporta email/telefone do end-user.

## 10. Casos de uso âncora

### UC — Aurora: gerar fine-tuning set mensal
1. Reviewer interno passa 30 min/semana na fila de revisão; corrige respostas.
2. Final do mês: `POST /v1/exports { filters: { has_corrected_response: true, from: "2026-04-01" } }`.
3. Output JSONL com 200 pares ideais.
4. Upload no fine-tuning da OpenAI/Gemini.

### UC — DocOps: golden set a partir de produção
1. Sample 100 traces aleatórios da semana.
2. Reviewer marca como golden + define `expected_output.summary_ideal`.
3. `POST /v1/datasets/{id}/build-from-traces` com filtros.
4. Cria experiment "regression-summary" usando esse dataset.

## 11. Open questions

- **[Decisão pendente]** Anotação multi-rater + agreement? Recomendação: **não** no MVP; 1 rater por item.
- **[Decisão pendente]** Versionamento de datasets (snapshots imutáveis)? Recomendação: **sim**, opt-in via `POST /v1/datasets/{id}/snapshot` retornando ID congelado para uso em experiments — implementar logo após MVP.
- **[Decisão pendente]** Suporte a Argilla/Label Studio export? Recomendação: **Futuro**.
