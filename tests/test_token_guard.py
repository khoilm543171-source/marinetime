from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.llm.token_guard import (
    TokenBudgetBlocked,
    TokenBudgetMode,
    TokenLimits,
    assert_token_budget,
    get_token_budget_status,
)


class TokenGuardTests(unittest.TestCase):
    def test_default_limits_preserve_three_million_token_reserve(self) -> None:
        limits = TokenLimits()
        self.assertEqual(limits.closeout_daily_tokens, 5_500_000)
        self.assertEqual(limits.max_daily_tokens, 7_000_000)

    def test_allows_small_call(self) -> None:
        assert_token_budget(
            estimated_input_tokens=1000,
            requested_output_tokens=200,
            current_video_tokens=0,
            current_daily_tokens=0,
        )

    def test_blocks_call_over_video_limit(self) -> None:
        limits = TokenLimits(max_tokens_per_video=1200)
        with self.assertRaisesRegex(TokenBudgetBlocked, "MAX_TOKENS_PER_VIDEO"):
            assert_token_budget(
                estimated_input_tokens=1000,
                requested_output_tokens=300,
                current_video_tokens=0,
                current_daily_tokens=0,
                limits=limits,
            )

    def test_closeout_threshold_is_signal_not_runtime_block(self) -> None:
        status = get_token_budget_status(current_daily_tokens=5_500_000)
        self.assertEqual(status.mode, TokenBudgetMode.CLOSEOUT)
        self.assertEqual(status.tokens_until_closeout, 0)
        self.assertEqual(status.tokens_until_hard_stop, 1_500_000)

        # Closeout freezes NEW SCOPE at the workflow layer, but calls needed to
        # finish the active PR remain allowed until the 7M hard cap.
        assert_token_budget(
            estimated_input_tokens=1000,
            requested_output_tokens=200,
            current_video_tokens=0,
            current_daily_tokens=5_500_000,
        )

    def test_build_mode_below_closeout_threshold(self) -> None:
        status = get_token_budget_status(current_daily_tokens=5_499_999)
        self.assertEqual(status.mode, TokenBudgetMode.BUILD)
        self.assertEqual(status.tokens_until_closeout, 1)

    def test_hard_stop_mode_at_seven_million(self) -> None:
        status = get_token_budget_status(current_daily_tokens=7_000_000)
        self.assertEqual(status.mode, TokenBudgetMode.HARD_STOP)
        self.assertEqual(status.tokens_until_hard_stop, 0)

    def test_hard_cap_blocks_call_that_would_cross_seven_million(self) -> None:
        with self.assertRaisesRegex(TokenBudgetBlocked, "MAX_DAILY_TOKENS"):
            assert_token_budget(
                estimated_input_tokens=1,
                requested_output_tokens=1,
                current_video_tokens=0,
                current_daily_tokens=6_999_999,
            )

    def test_caller_cannot_raise_hard_cap_by_using_closeout_value(self) -> None:
        limits = TokenLimits(closeout_daily_tokens=6_900_000)
        self.assertEqual(limits.max_daily_tokens, 7_000_000)
        with self.assertRaisesRegex(TokenBudgetBlocked, "MAX_DAILY_TOKENS"):
            assert_token_budget(
                estimated_input_tokens=100,
                requested_output_tokens=100,
                current_video_tokens=0,
                current_daily_tokens=6_999_900,
                limits=limits,
            )

    def test_rejects_invalid_threshold_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "CLOSEOUT_MUST_BE_BELOW"):
            TokenLimits(closeout_daily_tokens=7_000_000, max_daily_tokens=7_000_000)

    def test_rejects_negative_counters(self) -> None:
        with self.assertRaisesRegex(ValueError, "TOKEN_COUNTER_NEGATIVE"):
            assert_token_budget(
                estimated_input_tokens=1,
                requested_output_tokens=1,
                current_video_tokens=0,
                current_daily_tokens=-1,
            )


if __name__ == "__main__":
    unittest.main()
