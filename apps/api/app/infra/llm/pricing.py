import math
from decimal import Decimal


PRICING_PER_1K = {
    ("openai", "gpt-4o-mini"): (Decimal("0.00015"), Decimal("0.00060")),
    ("openai", "gpt-4.1"): (Decimal("0.00200"), Decimal("0.00800")),
    ("gemini", "gemini-2.5-flash"): (Decimal("0.00030"), Decimal("0.00250")),
    ("gemini", "gemini-2.5-pro"): (Decimal("0.00125"), Decimal("0.01000")),
}

# Fix-7B.5 (A-08): conservative fallback used when an llm_judge config names a
# provider/model absent from PRICING_PER_1K. Returning Decimal("0") for unknown
# models (compute_cost_usd's behaviour) would silently zero-cost every judge
# call and let the cost cap / monthly judge budget be bypassed. The fallback is
# deliberately above every tier in the table so an unpriced model errs toward
# blocking, never toward a free pass.
DEFAULT_JUDGE_PER_1K = (Decimal("0.00500"), Decimal("0.01500"))

# Heuristic chars-per-token. Token usage is not exposed by the synchronous
# call_llm contract (it returns only text), so judge cost is *estimated*
# deterministically from text length: same prompt + same response => same cost.
_CHARS_PER_TOKEN = 4


def split_provider_model(model: str | None) -> tuple[str, str]:
    """Parse an llm_judge ``model`` string into ``(provider, model_name)``.

    Accepts ``"openai/gpt-4o-mini"`` (provider prefix) or a bare model name,
    in which case the provider defaults to ``"openai"``.
    """
    if not model:
        return "openai", ""
    if "/" in model:
        provider, _, name = model.partition("/")
        return (provider.strip() or "openai"), name.strip()
    return "openai", model.strip()


def estimate_tokens(text: str | None) -> int:
    """Conservative deterministic token estimate (rounds up, min 1 for non-empty)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


def estimate_judge_cost_usd(
    model: str | None,
    prompt_text: str,
    response_text: str = "",
    *,
    assumed_output_tokens: int = 0,
) -> Decimal:
    """Estimate the USD cost of a single llm_judge invocation.

    ``response_text`` (post-call) takes precedence; pre-call, pass
    ``assumed_output_tokens`` to budget the unknown completion conservatively.
    Unknown provider/model falls back to ``DEFAULT_JUDGE_PER_1K`` (never 0).
    """
    provider, model_name = split_provider_model(model)
    prompt_per_1k, completion_per_1k = PRICING_PER_1K.get(
        (provider, model_name), DEFAULT_JUDGE_PER_1K
    )
    tokens_in = estimate_tokens(prompt_text)
    tokens_out = (
        estimate_tokens(response_text)
        if response_text
        else max(0, int(assumed_output_tokens))
    )
    return (
        Decimal(tokens_in) / Decimal(1000) * prompt_per_1k
        + Decimal(tokens_out) / Decimal(1000) * completion_per_1k
    )


def compute_cost_usd(
    provider: str | None,
    model: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
) -> Decimal:
    if not provider or not model:
        return Decimal("0")
    pricing = PRICING_PER_1K.get((provider, model))
    if pricing is None:
        return Decimal("0")
    prompt_per_1k, completion_per_1k = pricing
    in_tokens = Decimal(tokens_in or 0)
    out_tokens = Decimal(tokens_out or 0)
    return (in_tokens / Decimal(1000) * prompt_per_1k) + (out_tokens / Decimal(1000) * completion_per_1k)
