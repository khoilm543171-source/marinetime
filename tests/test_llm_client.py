from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx

from marinetime.config import ClaudeSettings
from marinetime.llm.client import ClaudeClient


class ClaudeClientTests(unittest.TestCase):
    def test_messages_parses_text_and_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["x-api-key"], "secret")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "nghi/claude-opus-5")
            return httpx.Response(
                200,
                json={
                    "model": "nghi/claude-opus-5",
                    "content": [{"type": "text", "text": "OK"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 12, "output_tokens": 2},
                },
            )

        settings = ClaudeSettings(
            api_key="secret",
            base_url="https://example.test",
            model="nghi/claude-opus-5",
        )
        with ClaudeClient(settings, transport=httpx.MockTransport(handler)) as client:
            result = client.messages(user_text="hello", max_tokens=16)

        self.assertEqual(result.text, "OK")
        self.assertEqual(result.usage.input_tokens, 12)
        self.assertEqual(result.usage.output_tokens, 2)


if __name__ == "__main__":
    unittest.main()
