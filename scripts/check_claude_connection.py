from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.config import ClaudeSettings  # noqa: E402
from marinetime.llm.client import ClaudeClient, ClaudeAPIError  # noqa: E402


def main() -> int:
    try:
        settings = ClaudeSettings.from_env()
        with ClaudeClient(settings) as client:
            response = client.messages(
                system="You are a connectivity check. Follow the requested output exactly.",
                user_text="Reply exactly: MARINETIME_OK",
                max_tokens=16,
                temperature=0.0,
            )
    except (ValueError, ClaudeAPIError) as exc:
        print(f"FAILED: {exc}")
        return 1

    print("CONNECTED")
    print(f"provider={settings.provider}")
    print(f"model={response.model}")
    print(f"response={response.text}")
    print(f"input_tokens={response.usage.input_tokens}")
    print(f"output_tokens={response.usage.output_tokens}")
    if response.usage.cache_read_input_tokens or response.usage.cache_creation_input_tokens:
        print(f"cache_read_input_tokens={response.usage.cache_read_input_tokens}")
        print(f"cache_creation_input_tokens={response.usage.cache_creation_input_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
