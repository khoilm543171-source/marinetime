from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.llm.token_guard import TokenBudgetBlocked, TokenLimits, assert_token_budget


class TokenGuardTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
