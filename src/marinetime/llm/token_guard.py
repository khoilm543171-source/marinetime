from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil


MARINETIME_CLOSEOUT_DAILY_TOKENS = 5_500_000
MARINETIME_HARD_DAILY_TOKENS = 7_000_000


class TokenBudgetBlocked(RuntimeError):
    pass


class TokenBudgetMode(str, Enum):
    BUILD = "build"
    CLOSEOUT = "closeout"
    HARD_STOP = "hard_stop"


@dataclass(frozen=True)
class TokenLimits:
    max_input_tokens_per_call: int = 20_000
    max_output_tokens_per_call: int = 2_500
    max_tokens_per_video: int = 50_000
    closeout_daily_tokens: int = MARINETIME_CLOSEOUT_DAILY_TOKENS
    max_daily_tokens: int = MARINETIME_HARD_DAILY_TOKENS

    def __post_init__(self) -> None:
        if self.closeout_daily_tokens < 0:
            raise ValueError("CLOSEOUT_DAILY_TOKENS_NEGATIVE")
        if self.max_daily_tokens <= 0:
            raise ValueError("MAX_DAILY_TOKENS_NONPOSITIVE")
        if self.max_daily_tokens > MARINETIME_HARD_DAILY_TOKENS:
            raise ValueError("MAX_DAILY_TOKENS_EXCEEDS_MARINETIME_HARD_CAP")
        if self.closeout_daily_tokens >= self.max_daily_tokens:
            raise ValueError("CLOSEOUT_MUST_BE_BELOW_MAX_DAILY_TOKENS")


@dataclass(frozen=True)
class TokenBudgetStatus:
    mode: TokenBudgetMode
    current_daily_tokens: int
    closeout_daily_tokens: int
    max_daily_tokens: int
    tokens_until_closeout: int
    tokens_until_hard_stop: int


def conservative_text_token_estimate(text: str) -> int:
    """Conservative preflight estimate, not provider billing truth.

    The first real smoke pass showed the previous len/3 heuristic could
    under-estimate gateway-reported input usage enough to overshoot the
    per-video budget. Use two characters per token as a deliberately cautious
    fallback until a provider-specific tokenizer/count endpoint is wired in.
    Actual usage is still taken from the API response and ledger.
    """
    if not text:
        return 0
    return ceil(len(text) / 2)


def get_token_budget_status(
    *,
    current_daily_tokens: int,
    limits: TokenLimits = TokenLimits(),
) -> TokenBudgetStatus:
    if current_daily_tokens < 0:
        raise ValueError("CURRENT_DAILY_TOKENS_NEGATIVE")

    # Keep the project-level hard cap independent from caller configuration.
    hard_limit = min(limits.max_daily_tokens, MARINETIME_HARD_DAILY_TOKENS)
    closeout_limit = min(limits.closeout_daily_tokens, hard_limit - 1)

    if current_daily_tokens >= hard_limit:
        mode = TokenBudgetMode.HARD_STOP
    elif current_daily_tokens >= closeout_limit:
        mode = TokenBudgetMode.CLOSEOUT
    else:
        mode = TokenBudgetMode.BUILD

    return TokenBudgetStatus(
        mode=mode,
        current_daily_tokens=current_daily_tokens,
        closeout_daily_tokens=closeout_limit,
        max_daily_tokens=hard_limit,
        tokens_until_closeout=max(0, closeout_limit - current_daily_tokens),
        tokens_until_hard_stop=max(0, hard_limit - current_daily_tokens),
    )


def assert_token_budget(
    *,
    estimated_input_tokens: int,
    requested_output_tokens: int,
    current_video_tokens: int,
    current_daily_tokens: int,
    limits: TokenLimits = TokenLimits(),
) -> None:
    if min(
        estimated_input_tokens,
        requested_output_tokens,
        current_video_tokens,
        current_daily_tokens,
    ) < 0:
        raise ValueError("TOKEN_COUNTER_NEGATIVE")

    if estimated_input_tokens > limits.max_input_tokens_per_call:
        raise TokenBudgetBlocked("MAX_INPUT_TOKENS_PER_CALL")
    if requested_output_tokens > limits.max_output_tokens_per_call:
        raise TokenBudgetBlocked("MAX_OUTPUT_TOKENS_PER_CALL")

    projected = estimated_input_tokens + requested_output_tokens
    if current_video_tokens + projected > limits.max_tokens_per_video:
        raise TokenBudgetBlocked("MAX_TOKENS_PER_VIDEO")

    hard_limit = min(limits.max_daily_tokens, MARINETIME_HARD_DAILY_TOKENS)
    if current_daily_tokens + projected > hard_limit:
        raise TokenBudgetBlocked("MAX_DAILY_TOKENS")
