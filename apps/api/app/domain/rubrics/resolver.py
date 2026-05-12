"""Resolve trace input/output context for evaluator templates."""
from __future__ import annotations

from app.models import Span, Trace


def _span_to_dict(span: Span) -> dict:
    return {
        "id": span.id,
        "type": span.type,
        "name": span.name,
        "status": span.status,
        "provider": span.provider,
        "model": span.model,
        "messages_in": span.messages_in,
        "messages_out": span.messages_out,
        "tokens_in": span.tokens_in,
        "tokens_out": span.tokens_out,
        "cost_usd": float(span.cost_usd) if span.cost_usd is not None else None,
        "input": span.input,
        "output": span.output,
        "error": span.error,
        "metadata": span.metadata_json,
    }


def build_trace_context(trace: Trace, spans: list[Span]) -> dict:
    """Build the Jinja2/dotpath context dict for a trace + its spans."""
    llm_spans = [s for s in spans if s.type == "llm_call"]

    # Resolve primary input: last message_in of first llm_call, or metadata.input
    input_text = ""
    if llm_spans and llm_spans[0].messages_in:
        msgs_in = llm_spans[0].messages_in
        last_msg = msgs_in[-1] if msgs_in else {}
        if isinstance(last_msg, dict):
            input_text = str(last_msg.get("content", ""))
    if not input_text and isinstance(trace.metadata_json, dict):
        input_text = str(trace.metadata_json.get("input", ""))

    # Resolve primary output: first message_out of last llm_call, or metadata.output
    output_text = ""
    if llm_spans and llm_spans[-1].messages_out:
        msgs_out = llm_spans[-1].messages_out
        first_msg = msgs_out[0] if msgs_out else {}
        if isinstance(first_msg, dict):
            output_text = str(first_msg.get("content", ""))
    if not output_text and isinstance(trace.metadata_json, dict):
        output_text = str(trace.metadata_json.get("output", ""))

    return {
        "trace": {
            "id": trace.id,
            "name": trace.name,
            "status": trace.status,
            "tags": trace.tags,
            "user_ref": trace.user_ref,
            "metadata": trace.metadata_json,
            "spans": [_span_to_dict(s) for s in spans],
            "input": {
                "user_message": input_text,
                "text": input_text,
            },
            "output": {
                "assistant_message": output_text,
                "text": output_text,
            },
        }
    }


def resolve_dotpath(path: str, context: dict) -> str:
    """Navigate a dotpath like 'trace.output.assistant_message' in the context dict."""
    parts = path.split(".")
    current: object = context
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, "")
        else:
            current = getattr(current, part, "")
        if current is None:
            return ""
    return str(current) if current is not None else ""
