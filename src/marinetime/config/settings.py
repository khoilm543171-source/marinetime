from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader to avoid another runtime dependency.

    Existing environment variables win over file values.
    """
    file_path = Path(path)
    if not file_path.exists():
        return
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class ClaudeSettings:
    api_key: str
    base_url: str
    model: str
    anthropic_version: str = "2023-06-01"
    timeout_seconds: float = 90.0
    provider: str = "nghimmo"

    @classmethod
    def from_env(cls, *, load_file: bool = True) -> "ClaudeSettings":
        if load_file:
            load_dotenv()

        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("NGHIMMO_API_KEY") or ""
        base_url = (
            os.getenv("CLAUDE_BASE_URL")
            or os.getenv("NGHIMMO_BASE_URL")
            or "https://api.nghimmo.com"
        )
        model = os.getenv("CLAUDE_MODEL") or os.getenv("OPUS_MODEL") or ""
        provider = os.getenv("CLAUDE_PROVIDER", "nghimmo")
        version = os.getenv("CLAUDE_ANTHROPIC_VERSION", "2023-06-01")
        timeout = float(os.getenv("CLAUDE_TIMEOUT_SECONDS", "90"))

        if not api_key:
            raise ValueError("Missing CLAUDE_API_KEY (or NGHIMMO_API_KEY).")
        if not model:
            raise ValueError("Missing CLAUDE_MODEL (or OPUS_MODEL).")

        return cls(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model,
            anthropic_version=version,
            timeout_seconds=timeout,
            provider=provider,
        )
