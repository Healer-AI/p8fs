"""Token usage calculator for LLM cost estimation."""


class TokenUsageCalculator:
    """Calculate estimated costs for different providers and models."""

    # Pricing per 1K tokens (as of January 2025)
    PRICING = {
        "openai": {
            "gpt-4": {"prompt": 0.03, "completion": 0.06},
            "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
            "gpt-3.5-turbo": {"prompt": 0.001, "completion": 0.002},
        },
        "anthropic": {
            "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
            "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
            "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        },
    }

    @classmethod
    def calculate_cost(
        cls, provider: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Calculate estimated cost in USD."""
        provider_pricing = cls.PRICING.get(provider.lower())
        if not provider_pricing:
            return 0.0

        model_pricing = provider_pricing.get(model.lower())
        if not model_pricing:
            # Try to find similar model
            for model_key in provider_pricing:
                if model_key in model.lower():
                    model_pricing = provider_pricing[model_key]
                    break
            else:
                return 0.0

        prompt_cost = (prompt_tokens / 1000) * model_pricing["prompt"]
        completion_cost = (completion_tokens / 1000) * model_pricing["completion"]

        return prompt_cost + completion_cost