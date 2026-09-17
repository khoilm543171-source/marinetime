from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.llm.router import run_task
from marinetime.llm.token_guard import TokenBudgetBlocked
from marinetime.llm.usage import UsageRecord, append_usage


class _ClientMustNotBeCalled:
    def messages(self, **kwargs):  # pragma: no cover - failure path only
        raise AssertionError("provider call must not occur after hard stop")


class RouterBudgetTests(unittest.TestCase):
    def test_runtime_counters_cannot_be_overridden_by_caller(self) -> None:
        parameters = inspect.signature(run_task).parameters
        self.assertNotIn("current_daily_tokens", parameters)
        self.assertNotIn("current_video_tokens", parameters)

    def test_router_reads_ledger_and_blocks_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "token_ledger.jsonl"
            append_usage(
                UsageRecord(
                    task="prior_task",
                    prompt_version="v1",
                    model="fake-model",
                    input_tokens=7_000_000,
                    output_tokens=0,
                    video_id="video-1",
                ),
                path=ledger,
            )

            with self.assertRaisesRegex(TokenBudgetBlocked, "MAX_DAILY_TOKENS"):
                run_task(
                    client=_ClientMustNotBeCalled(),
                    task="assessment_eval",
                    dynamic_input="small deterministic test input",
                    video_id="video-2",
                    max_output_tokens=1,
                    repo_root=ROOT,
                    usage_log_path=ledger,
                )


if __name__ == "__main__":
    unittest.main()
