"""Shared RAG detection and consolidation used by trace detail and Quality Gate."""
import math

from sqlalchemy import or_, select

from app.models import Span, Trace


# Contract for "is this a RAG trace?" — kept in sync with the frontend's
# isRagTrace() in apps/web/lib/rag.ts so the list filter and the detail page
# decide on the exact same signals.
_RAG_SPAN_NAMES_EXACT: tuple[str, ...] = (
    "rag.retrieve",
    "rag.grounding.validate",
    "response.finalize",
)
_RAG_METADATA_KEYS: tuple[str, ...] = (
    "pipeline_version",
    "retrieved_count",
    "citation_count",
    "grounding_ok",
    "quality_level",
    "quality_score",
    "support_rate",
)


def rag_filter_predicate():
    """Return a SQLAlchemy filter expression selecting traces with RAG evidence.

    The predicate matches any of:
    - ``trace.name`` starts with ``rag.`` (legacy convention).
    - ``trace.metadata.is_rag`` truthy (explicit flag).
    - ``trace.metadata`` contains any of ``_RAG_METADATA_KEYS``.
    - any span belongs to ``_RAG_SPAN_NAMES_EXACT`` or has a name like
      ``rag.%``.

    Matches the contract used by the trace detail UI; keeps list and detail
    aligned.
    """
    # Note: `.as_string()` is required for cross-dialect JSON key-existence —
    # bare `Trace.metadata_json[key].isnot(None)` returns true on SQLite even
    # for absent keys (different cast pipeline). The text projection collapses
    # both backends to "string or NULL", and IS NOT NULL then matches presence.
    metadata_clauses = [
        Trace.metadata_json[key].as_string().isnot(None) for key in _RAG_METADATA_KEYS
    ]
    span_subq = (
        select(Span.trace_id)
        .where(
            or_(
                Span.name.in_(_RAG_SPAN_NAMES_EXACT),
                Span.name.ilike("rag.%"),
            )
        )
        .scalar_subquery()
    )
    return or_(
        Trace.name.ilike("rag.%"),
        Trace.metadata_json["is_rag"].as_string().in_(("true", "1")),
        *metadata_clauses,
        Trace.id.in_(span_subq),
    )


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _as_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _pick_span(spans: list[Span], name: str) -> Span | None:
    return next((span for span in spans if span.name == name), None)


def _normalize_citations(source: object) -> list[dict]:
    rows = []
    for index, item in enumerate(_as_list(source), start=1):
        if isinstance(item, str):
            rows.append({"rank": index, "title": None, "score": None, "source": None, "chunk": item})
            continue
        data = _as_dict(item)
        if not data:
            continue
        rows.append(
            {
                "rank": int(_as_number(data.get("rank") or data.get("fonte_n") or data.get("n")) or index),
                "title": _as_string(data.get("title") or data.get("doc_title")),
                "score": _as_number(data.get("score")),
                "source": _as_string(data.get("source") or data.get("doc_ref") or data.get("document_ref")),
                "chunk": _as_string(data.get("chunk") or data.get("chunk_ref") or data.get("text")),
            }
        )
    return rows


def _normalize_claims(source: object) -> list[dict]:
    rows = []
    for item in _as_list(source):
        data = _as_dict(item)
        if not data:
            continue
        text = _as_string(data.get("text") or data.get("claim"))
        if not text:
            continue
        grounded_raw = data.get("grounded")
        rows.append(
            {
                "text": text,
                "grounded": bool(grounded_raw) if isinstance(grounded_raw, bool) else bool(data.get("cite")),
                "cite": _as_string(data.get("cite") or data.get("citation") or data.get("chunk_ref")),
            }
        )
    return rows


def _normalize_claim_links(source: object) -> list[dict]:
    rows = []
    for item in _as_list(source):
        data = _as_dict(item)
        if not data:
            continue
        claim = _as_string(data.get("claim") or data.get("claim_text"))
        chunk = _as_string(data.get("chunk") or data.get("chunk_ref") or data.get("chunk_id"))
        if claim and chunk:
            rows.append({"claim": claim, "chunk": chunk, "score": _as_number(data.get("score"))})
    return rows


def _risk_from_counts(grounded: int | None, ungrounded: int | None, avg_score: float | None) -> str:
    if grounded is None and ungrounded is None and avg_score is None:
        return "unknown"
    g = grounded or 0
    u = ungrounded or 0
    total = g + u
    if total and u / total > 0.5:
        return "high"
    if avg_score is not None and avg_score < 0.5:
        return "high"
    if u > 0 or (avg_score is not None and avg_score < 0.75):
        return "medium"
    return "low"


def _risk_from_support_rate(support_rate: float, avg_score: float | None) -> str:
    if support_rate < 0.5 or (avg_score is not None and avg_score < 0.5):
        return "high"
    if support_rate < 0.85 or (avg_score is not None and avg_score < 0.75):
        return "medium"
    return "low"


def _first_number(*values: object) -> float | None:
    return next((number for value in values if (number := _as_number(value)) is not None), None)


def consolidate_rag(trace: Trace, spans: list[Span]) -> dict:
    if getattr(trace, "redacted", False):
        return {
            "retrieved_docs": 0,
            "avg_score": None,
            "grounded_claims": None,
            "ungrounded_claims": None,
            "support_rate": None,
            "claims_unavailable": True,
            "hallucination_risk": "unknown",
            "answer_preview": None,
            "citations": [],
            "claims": [],
            "claim_to_chunk": [],
            "redacted": True,
        }
    retrieve = _pick_span(spans, "rag.retrieve")
    grounding = _pick_span(spans, "rag.grounding.validate")
    finalize = _pick_span(spans, "response.finalize")
    generate = _pick_span(spans, "llm.generate")

    meta = _as_dict(trace.metadata_json)
    retrieve_out = _as_dict(retrieve.output if retrieve else None)
    grounding_out = _as_dict(grounding.output if grounding else None)
    finalize_out = _as_dict(finalize.output if finalize else None)
    generate_out = _as_dict(generate.output if generate else None)

    citations = (
        _normalize_citations(retrieve_out.get("citations"))
        or _normalize_citations(retrieve_out.get("chunk_refs"))
        or _normalize_citations(grounding_out.get("citations"))
        or _normalize_citations(finalize_out.get("citations"))
        or _normalize_citations(meta.get("citations"))
    )
    claims = (
        _normalize_claims(grounding_out.get("claims"))
        or _normalize_claims(finalize_out.get("claims"))
        or _normalize_claims(meta.get("claims"))
    )
    claim_to_chunk = (
        _normalize_claim_links(grounding_out.get("claim_to_chunk"))
        or _normalize_claim_links(finalize_out.get("claim_to_chunk"))
        or _normalize_claim_links(meta.get("claim_to_chunk"))
    )

    score_values = [row["score"] for row in citations if row.get("score") is not None]
    score_values.extend(row["score"] for row in claim_to_chunk if row.get("score") is not None)
    quality_score = _first_number(grounding_out.get("quality_score"), finalize_out.get("quality_score"), meta.get("quality_score"))
    if quality_score is not None:
        score_values.append(quality_score)
    avg_score = round(sum(score_values) / len(score_values), 4) if score_values else None

    grounded: int | None = sum(1 for claim in claims if claim["grounded"]) if claims else None
    ungrounded: int | None = sum(1 for claim in claims if not claim["grounded"]) if claims else None
    support_rate = _first_number(grounding_out.get("support_rate"), finalize_out.get("support_rate"), meta.get("support_rate"))
    claims_unavailable = False
    if not claims:
        unsupported_raw = _first_number(grounding_out.get("unsupported_claim_count"), meta.get("unsupported_claim_count"))
        if support_rate is not None or unsupported_raw is not None:
            claims_unavailable = True
        if support_rate is not None:
            risk = _risk_from_support_rate(float(support_rate), avg_score)
        else:
            risk = _risk_from_counts(None, None, avg_score)
    else:
        risk = _risk_from_counts(grounded, ungrounded, avg_score)

    answer_preview = (
        _as_string(finalize_out.get("answer_preview") or finalize_out.get("answer"))
        or _as_string(generate_out.get("answer_preview") or generate_out.get("answer"))
        or _as_string(meta.get("answer_preview"))
    )
    retrieved_docs = int(
        _as_number(retrieve_out.get("retrieved_count") or meta.get("retrieved_count"))
        or len(citations)
    )
    return {
        "retrieved_docs": retrieved_docs,
        "avg_score": avg_score,
        "grounded_claims": grounded,
        "ungrounded_claims": ungrounded,
        "support_rate": float(support_rate) if support_rate is not None else None,
        "claims_unavailable": claims_unavailable,
        "hallucination_risk": risk,
        "answer_preview": answer_preview,
        "citations": citations,
        "claims": claims,
        "claim_to_chunk": claim_to_chunk,
    }
