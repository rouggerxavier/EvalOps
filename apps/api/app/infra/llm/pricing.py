from decimal import Decimal


PRICING_PER_1K = {
    ("openai", "gpt-4o-mini"): (Decimal("0.00015"), Decimal("0.00060")),
    ("openai", "gpt-4.1"): (Decimal("0.00500"), Decimal("0.01500")),
    ("gemini", "gemini-2.5-flash"): (Decimal("0.00015"), Decimal("0.00060")),
    ("gemini", "gemini-2.5-pro"): (Decimal("0.00125"), Decimal("0.00500")),
    ("groq", "llama-3.3-70b"): (Decimal("0.00059"), Decimal("0.00079")),
}


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
