"""Price per million tokens, in US dollars, for the models enrich.py can use.

These numbers are an ESTIMATE, copied by hand from the providers' public price pages on
PRICES_AS_OF. Prices change and free tiers cost nothing, so treat the result as "what this
would cost on a paid plan", never as a bill.

A model that is not in the table has no cost: estimate_cost returns None, which becomes a
blank cell. It never returns 0 for an unknown model, because 0 would look like "free".
Gemini models are left out until their current prices are copied from the Google AI pricing
page, so Gemini rows show tokens but a blank cost.
"""

PRICES_AS_OF = "2026-11-23"

# model: (input USD per 1M tokens, output USD per 1M tokens)
PRICE_PER_MILLION = {
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
}


def estimate_cost(model, input_tokens, output_tokens):
    """Estimated USD for one call, or None when the model or a token count is unknown."""
    prices = PRICE_PER_MILLION.get(model)
    if prices is None or input_tokens is None or output_tokens is None:
        return None
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
