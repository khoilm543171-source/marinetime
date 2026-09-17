from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from marinetime.llm.client import ClaudeClient, ClaudeResponse
from marinetime.llm.prompt_registry import load_prompt
from marinetime.llm.token_guard import (
    TokenLimits,
    assert_token_budget,
    conservative_text_token_estimate,
)
from marinetime.llm.usage import UsageRecord, append_usage, load_usage_totals


@dataclass(frozen=True)
class LLMTaskResult:
    text: str
    model: str
    task: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def guard_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


def run_task(
    *,
    client: ClaudeClient,
    task: str,
    dynamic_input: str,
    video_id: str | None = None,
    current_video_tokens: int | None = None,
    current_daily_tokens: int | None = None,
    max_output_tokens: int | None = None,
    repo_root: str | Path = ".",
    token_limits: TokenLimits = TokenLimits(),
    usage_log_path: str | Path = "storage/logs/token_ledger.jsonl",
) -> LLMTaskResult:
    spec, system_prompt = load_prompt(task, repo_root=repo_root)
    output_limit = max_output_tokens or spec.default_max_output_tokens

    # Prefer actual usage already observed from provider responses. Explicit
    # counters remain available for deterministic tests and controlled callers.
    if current_video_tokens is None or current_daily_tokens is None:
        totals = load_usage_totals(usage_log_path, video_id=video_id)
        if current_video_tokens is None:
            current_video_tokens = totals.video_tokens
        if current_daily_tokens is None:
            current_daily_tokens = totals.daily_tokens

    estimated_input = conservative_text_token_estimate(system_prompt + "\n" + dynamic_input)
    assert_token_budget(
        estimated_input_tokens=estimated_input,
        requested_output_tokens=output_limit,
        current_video_tokens=current_video_tokens,
        current_daily_tokens=current_daily_tokens,
        limits=token_limits,
    )

    response: ClaudeResponse = client.messages(
        system=system_prompt,
        user_text=dynamic_input,
        max_tokens=output_limit,
        temperature=0.0,
    )

    usage_record = UsageRecord(
        task=task,
        prompt_version=spec.version,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_creation_input_tokens=response.usage.cache_creation_input_tokens,
        cache_read_input_tokens=response.usage.cache_read_input_tokens,
        video_id=video_id,
        success=True,
    )
    append_usage(usage_record, path=usage_log_path)

    return LLMTaskResult(
        text=response.text,
        model=response.model,
        task=task,
        prompt_version=spec.version,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_creation_input_tokens=response.usage.cache_creation_input_tokens,
        cache_read_input_tokens=response.usage.cache_read_input_tokens,
    )
