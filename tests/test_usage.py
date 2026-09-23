from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.llm.usage import UsageLedgerError, UsageRecord, append_usage, load_usage_totals


class UsageLedgerTests(unittest.TestCase):
    def test_append_and_load_actual_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "token_ledger.jsonl"
            append_usage(
                UsageRecord(
                    task="alu_extract",
                    prompt_version="v1",
                    model="nghi/claude-opus-5",
                    input_tokens=100,
                    output_tokens=20,
                    cache_creation_input_tokens=10,
                    cache_read_input_tokens=5,
                    video_id="video-1",
                ),
                path=ledger,
            )

            totals = load_usage_totals(ledger, video_id="video-1")
            self.assertEqual(totals.daily_tokens, 135)
            self.assertEqual(totals.video_tokens, 135)

            payload = json.loads(ledger.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["guard_tokens"], 135)
            self.assertNotIn("api_key", payload)

    def test_reader_recomputes_guard_tokens_from_provider_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "token_ledger.jsonl"
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_creation_input_tokens": 10,
                "cache_read_input_tokens": 5,
                "guard_tokens": -999999,
                "video_id": "video-1",
            }
            ledger.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            totals = load_usage_totals(ledger, video_id="video-1")
            self.assertEqual(totals.daily_tokens, 135)
            self.assertEqual(totals.video_tokens, 135)

    def test_negative_provider_counter_blocks_budget_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "token_ledger.jsonl"
            valid = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "input_tokens": 100,
                "output_tokens": 20,
                "video_id": "video-1",
            }
            invalid_negative = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "input_tokens": -1_000_000,
                "output_tokens": 0,
                "video_id": "video-1",
            }
            ledger.write_text(
                json.dumps(valid) + "\n" + json.dumps(invalid_negative) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(UsageLedgerError, "USAGE_LEDGER_INVALID_LINE:2"):
                load_usage_totals(ledger, video_id="video-1")

    def test_video_budget_and_attempts_survive_a_new_utc_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "token_ledger.jsonl"
            ledger.write_text(
                json.dumps(
                    {
                        "timestamp": "2000-01-01T00:00:00+00:00",
                        "input_tokens": 999,
                        "output_tokens": 1,
                        "video_id": "video-1",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            totals = load_usage_totals(
                ledger,
                video_id="video-1",
                day=datetime.now(timezone.utc).date(),
            )
            self.assertEqual(totals.daily_tokens, 0)
            self.assertEqual(totals.video_tokens, 1000)
            self.assertEqual(totals.video_calls, 1)


if __name__ == "__main__":
    unittest.main()
