from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.llm.token_guard import conservative_text_token_estimate


class ConservativeTokenEstimateTests(unittest.TestCase):
    def test_empty_text_is_zero(self) -> None:
        self.assertEqual(conservative_text_token_estimate(""), 0)

    def test_uses_two_characters_per_token_ceiling(self) -> None:
        self.assertEqual(conservative_text_token_estimate("abcd"), 2)
        self.assertEqual(conservative_text_token_estimate("abcde"), 3)

    def test_smoke_observation_would_have_had_more_headroom(self) -> None:
        # A 35,001-character prompt previously estimated to 11,667 tokens with
        # len/3. The cautious len/2 fallback now reserves 17,501 tokens, which
        # is above the 16,680 input tokens observed on the first real smoke pass.
        text = "x" * 35_001
        self.assertEqual(conservative_text_token_estimate(text), 17_501)
        self.assertGreaterEqual(conservative_text_token_estimate(text), 16_680)


if __name__ == "__main__":
    unittest.main()
