from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.config import ClaudeSettings  # noqa: E402
from marinetime.llm.client import ClaudeAPIError, ClaudeClient  # noqa: E402
from marinetime.llm.router import run_task  # noqa: E402
from marinetime.llm.token_guard import (  # noqa: E402
    TokenBudgetBlocked,
    get_token_budget_status,
)
from marinetime.llm.usage import load_usage_totals  # noqa: E402


CHECK_VIDEO_ID = "token-accounting-smoke-check"
LEDGER = ROOT / "storage" / "logs" / "token_ledger.jsonl"


def main() -> int:
    try:
        settings = ClaudeSettings.from_env()
        with ClaudeClient(settings) as client:
            result = run_task(
                client=client,
                task="assessment_eval",
                dynamic_input=(
                    "Smoke-test input only. Return the smallest valid JSON object "
                    "that indicates this is a connectivity test."
                ),
                video_id=CHECK_VIDEO_ID,
                max_output_tokens=64,
                repo_root=ROOT,
                usage_log_path=LEDGER,
            )
    except (ValueError, ClaudeAPIError, TokenBudgetBlocked) as exc:
        print(f"FAILED: {exc}")
        return 1

    totals = load_usage_totals(LEDGER, video_id=CHECK_VIDEO_ID)
    status = get_token_budget_status(current_daily_tokens=totals.daily_tokens)

    print("TOKEN_ACCOUNTING_OK")
    print(f"model={result.model}")
    print(f"input_tokens={result.input_tokens}")
    print(f"output_tokens={result.output_tokens}")
    print(f"cache_creation_input_tokens={result.cache_creation_input_tokens}")
    print(f"cache_read_input_tokens={result.cache_read_input_tokens}")
    print(f"request_guard_tokens={result.guard_tokens}")
    print(f"video_guard_tokens_lifetime={totals.video_tokens}")
    print(f"video_attempts_lifetime={totals.video_calls}")
    print(f"daily_guard_tokens_today={totals.daily_tokens}")
    print(f"daily_mode={status.mode.value}")
    print(f"tokens_until_closeout={status.tokens_until_closeout}")
    print(f"tokens_until_hard_stop={status.tokens_until_hard_stop}")
    print(f"ledger={LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
