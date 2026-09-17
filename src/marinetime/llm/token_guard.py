from __future__ import annotations

from dataclasses import dataclass
from math import ceil


class TokenBudgetBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenLimits:
    max_input_tokens_per_call: int = 20_000
    max_output_tokens_per_call: int = 2_500
    max_tokens_per_video: int = 50_000
    max_daily_tokens: int = 9_000_000


def conservative_text_token_estimate(text: str) -> int:
    """Conservative preflight estimate, not provider billing truth.

    This prevents obvious runaway calls before a provider-specific token counter
    is wired in. Actual usage must be taken from the API response.
    """
    if not text:
        return 0
    return ceil(len(text) / 3)


def assert_token_budget(
    *,
    estimated_input_tokens: int,
    requested_output_tokens: int,
    current_video_tokens: int,
    current_daily_tokens: int,
    limits: TokenLimits = TokenLimits(),
) -> None:
    if estimated_input_tokens > limits.max_input_tokens_per_call:
        raise TokenBudgetBlocked("MAX_INPUT_TOKENS_PER_CALL")
    if requested_output_tokens > limits.max_output_tokens_per_call:
        raise TokenBudgetBlocked("MAX_OUTPUT_TOKENS_PER_CALL")

    projected = estimated_input_tokens + requested_output_tokens
    if current_video_tokens + projected > limits.max_tokens_per_video:
        raise TokenBudgetBlocked("MAX_TOKENS_PER_VIDEO")
    if current_daily_tokens + projected > limits.max_daily_tokens:
        raise TokenBudgetBlocked("MAX_DAILY_TOKENS")
