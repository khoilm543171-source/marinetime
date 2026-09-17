import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from marinetime.budget.guard import BudgetBlocked, assert_budget


class BudgetGuardTests(unittest.TestCase):
    def test_blocks_video_budget(self):
        with self.assertRaises(BudgetBlocked):
            assert_budget(
                estimated_next_call_usd=0.20,
                current_video_spend_usd=0.40,
                current_job_spend_usd=0.40,
                current_daily_spend_usd=0.40,
                llm_calls_for_video=1,
            )

    def test_allows_small_call(self):
        assert_budget(
            estimated_next_call_usd=0.05,
            current_video_spend_usd=0.10,
            current_job_spend_usd=0.10,
            current_daily_spend_usd=0.10,
            llm_calls_for_video=1,
        )


if __name__ == "__main__":
    unittest.main()
