from __future__ import annotations

from dataclasses import dataclass


class BudgetBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetLimits:
    max_cost_per_video_usd: float = 0.50
    max_cost_per_job_usd: float = 2.00
    max_daily_cost_usd: float = 10.00
    max_auto_retries: int = 1
    max_llm_calls_per_video: int = 3


def assert_budget(
    *,
    estimated_next_call_usd: float,
    current_video_spend_usd: float,
    current_job_spend_usd: float,
    current_daily_spend_usd: float,
    llm_calls_for_video: int,
    limits: BudgetLimits = BudgetLimits(),
) -> None:
    if llm_calls_for_video + 1 > limits.max_llm_calls_per_video:
        raise BudgetBlocked("MAX_LLM_CALLS_PER_VIDEO")
    if current_video_spend_usd + estimated_next_call_usd > limits.max_cost_per_video_usd:
        raise BudgetBlocked("MAX_COST_PER_VIDEO")
    if current_job_spend_usd + estimated_next_call_usd > limits.max_cost_per_job_usd:
        raise BudgetBlocked("MAX_COST_PER_JOB")
    if current_daily_spend_usd + estimated_next_call_usd > limits.max_daily_cost_usd:
        raise BudgetBlocked("MAX_DAILY_COST")
