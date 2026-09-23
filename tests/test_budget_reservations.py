from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx

from marinetime.config import ClaudeSettings
from marinetime.llm.client import ClaudeAPIError, ClaudeClient
from marinetime.llm.router import run_task
from marinetime.llm.token_guard import TokenBudgetBlocked
from marinetime.llm.usage import UsageLedgerError, ledger_lock, load_usage_totals


def settings():
    return ClaudeSettings(api_key="test-only", base_url="https://example.test", model="test-model")


def call(client, ledger, *, video_id="RAW-001"):
    return run_task(
        client=client, task="assessment_eval", dynamic_input="small fixture",
        video_id=video_id, max_output_tokens=10, repo_root=ROOT, usage_log_path=ledger,
    )


class BudgetReservationTests(unittest.TestCase):
    def test_reservation_exists_before_call_and_settlement_counts_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "usage.jsonl"

            def handler(request):
                pending = load_usage_totals(ledger, video_id="RAW-001")
                self.assertEqual(pending.video_calls, 1)
                self.assertGreater(pending.video_tokens, 0)
                return httpx.Response(200, json={
                    "content": [{"type": "text", "text": "OK"}],
                    "usage": {"input_tokens": 12, "output_tokens": 2,
                              "cache_read_input_tokens": 4},
                })

            with ClaudeClient(settings(), transport=httpx.MockTransport(handler)) as client:
                call(client, ledger)
            total = load_usage_totals(ledger, video_id="RAW-001")
            self.assertEqual(total.video_tokens, 18)
            self.assertEqual(total.daily_tokens, 18)
            self.assertEqual(total.video_calls, 1)
            records = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([r["event"] for r in records], ["reserved", "usage"])
            self.assertEqual(records[0]["request_id"], records[1]["request_id"])
            self.assertNotIn("test-only", ledger.read_text())

    def test_three_timeouts_consume_attempts_and_block_the_fourth_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "usage.jsonl"
            calls = []

            def handler(request):
                calls.append(request)
                raise httpx.ReadTimeout("synthetic timeout")

            with ClaudeClient(settings(), transport=httpx.MockTransport(handler)) as client:
                for _ in range(3):
                    with self.assertRaises(ClaudeAPIError):
                        call(client, ledger)
                with self.assertRaisesRegex(TokenBudgetBlocked, "MAX_LLM_CALLS_PER_VIDEO"):
                    call(client, ledger)
            self.assertEqual(len(calls), 3)
            total = load_usage_totals(ledger, video_id="RAW-001")
            self.assertEqual(total.video_calls, 3)
            self.assertGreater(total.video_tokens, 0)

    def test_missing_or_invalid_usage_keeps_the_reservation(self):
        cases = (
            None, {}, {"input_tokens": 12},
            {"input_tokens": -12, "output_tokens": 2},
            {"input_tokens": True, "output_tokens": 2},
            {"input_tokens": "12", "output_tokens": 2},
            {"input_tokens": 12, "output_tokens": 2, "cache_read_input_tokens": -1},
        )
        for usage in cases:
            with self.subTest(usage=usage), tempfile.TemporaryDirectory() as tmp:
                ledger = Path(tmp) / "usage.jsonl"
                def handler(request):
                    return httpx.Response(200, json={
                        "content": [{"type": "text", "text": "OK"}], "usage": usage,
                    })
                with ClaudeClient(settings(), transport=httpx.MockTransport(handler)) as client:
                    with self.assertRaisesRegex(ClaudeAPIError, "PROVIDER_USAGE_"):
                        call(client, ledger)
                total = load_usage_totals(ledger, video_id="RAW-001")
                self.assertEqual(total.video_calls, 1)
                self.assertGreater(total.video_tokens, 0)
                self.assertEqual(len(ledger.read_text().splitlines()), 1)

    def test_busy_or_corrupt_ledger_prevents_provider_call(self):
        def never_called(request):
            self.fail("provider must not be contacted")

        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "usage.jsonl"
            with ClaudeClient(settings(), transport=httpx.MockTransport(never_called)) as client:
                with ledger_lock(ledger):
                    with self.assertRaisesRegex(UsageLedgerError, "USAGE_LEDGER_LOCKED"):
                        call(client, ledger)
                for broken in ("not-json\n", "[]\n", "{\"timestamp\":null}\n"):
                    ledger.write_text(broken)
                    with self.assertRaisesRegex(UsageLedgerError, "USAGE_LEDGER_INVALID_LINE"):
                        call(client, ledger)

    def test_old_usage_is_not_refunded_by_a_new_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "usage.jsonl"
            ledger.write_text(json.dumps({
                "timestamp": "2000-01-01T00:00:00+00:00", "video_id": "RAW-001",
                "input_tokens": 48000, "output_tokens": 2000,
            }) + "\n")
            def never_called(request):
                self.fail("lifetime video budget must block the request")
            with ClaudeClient(settings(), transport=httpx.MockTransport(never_called)) as client:
                with self.assertRaisesRegex(TokenBudgetBlocked, "MAX_TOKENS_PER_VIDEO"):
                    call(client, ledger)


if __name__ == "__main__":
    unittest.main()
