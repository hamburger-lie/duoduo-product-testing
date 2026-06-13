from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class AIUsage:
    """Token usage and estimated model cost for one AI call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_yuan: Decimal = Decimal("0.0000")

    @property
    def total_tokens(self) -> int:
        """Return total token count."""

        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class AITextResult:
    """Text response plus usage metadata."""

    content: str
    usage: AIUsage


def estimate_cost_yuan(
    usage: AIUsage,
    *,
    input_price_per_1k: Decimal,
    output_price_per_1k: Decimal,
) -> Decimal:
    """Estimate yuan cost from per-1K input and output token prices."""

    raw = (
        Decimal(usage.input_tokens) / Decimal(1000) * input_price_per_1k
        + Decimal(usage.output_tokens) / Decimal(1000) * output_price_per_1k
    )
    return raw.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
