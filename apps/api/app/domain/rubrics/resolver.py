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


def _message_text(span: Span) -> str:
    for msg in span.messages_out or []:
        if isinstance(msg, dict) and msg.get("content"):
            return str(msg["content"])
    return ""


def _output_field(span: Span, keys: tuple[str, ...]) -> str:
    if isinstance(span.output, dict):
        for key in keys:
            value = span.output.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _resolve_output(trace: Trace, spans: list[Span], llm_spans: list[Span]) -> str:
    """Final answer: newest LLM text, then metadata, then what the SDK's ``set_io`` recorded."""
    # Newest first: an agent's last call may hold only tool calls, without text.
    newest_first = list(reversed(llm_spans))
    for span in newest_first:
        text = _message_text(span)
        if text:
            return text
    if isinstance(trace.metadata_json, dict) and trace.metadata_json.get("output"):
        return str(trace.metadata_json["output"])
    for span in newest_first:
        text = _output_field(span, ("text", "content", "answer"))
        if text:
            return text
    for span in spans:
        if span.parent_span_id is None:
            text = _output_field(span, ("result",))
            if text:
                return text
    return ""


def build_trace_context(trace: Trace, spans: list[Span]) -> dict:
    """Build the Jinja2/dotpath context dict for a trace + its spans."""
    llm_spans = [s for s in spans if s.type == "llm_call"]

    # Resolve primary input: last message_in of first llm_call, or metadata.input
    input_text = ""
    if llm_spans and llm_spans[0].messages_in:
        msgs_in = llm_spans[0].messages_in
        last_msg = msgs_in[-1] if msgs_in else {}
        if isinstance(last_msg, dict):
            input_text = str(last_msg.get("content") or "")
    if not input_text and isinstance(trace.metadata_json, dict):
        input_text = str(trace.metadata_json.get("input", ""))

    output_text = _resolve_output(trace, spans, llm_spans)

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
