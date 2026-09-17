from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from marinetime.config import ClaudeSettings


class ClaudeAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaudeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ClaudeResponse:
    text: str
    model: str
    stop_reason: str | None
    usage: ClaudeUsage
    raw: dict[str, Any]


class ClaudeClient:
    """Small Anthropic-Messages-compatible client.

    Secrets stay in process environment/.env and are never written to logs here.
    No automatic semantic retries are performed by this client.
    """

    def __init__(
        self,
        settings: ClaudeSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._client = httpx.Client(
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ClaudeClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def messages(
        self,
        *,
        user_text: str,
        max_tokens: int,
        system: str | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> ClaudeResponse:
        payload: dict[str, Any] = {
            "model": model or self.settings.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_text}],
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature

        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": self.settings.anthropic_version,
            "content-type": "application/json",
        }
        url = f"{self.settings.base_url}/v1/messages"

        try:
            response = self._client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ClaudeAPIError(f"Claude transport error: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            # Do not echo request headers or secrets. Keep only a bounded provider message.
            detail = response.text[:500].replace(self.settings.api_key, "[REDACTED]")
            raise ClaudeAPIError(f"Claude API HTTP {response.status_code}: {detail}")

        try:
            data = response.json()
        except ValueError as exc:
            raise ClaudeAPIError("Claude API returned non-JSON content.") from exc

        content = data.get("content") or []
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        usage_raw = data.get("usage") or {}
        usage = ClaudeUsage(
            input_tokens=int(usage_raw.get("input_tokens", 0) or 0),
            output_tokens=int(usage_raw.get("output_tokens", 0) or 0),
            cache_creation_input_tokens=int(
                usage_raw.get("cache_creation_input_tokens", 0) or 0
            ),
            cache_read_input_tokens=int(usage_raw.get("cache_read_input_tokens", 0) or 0),
        )
        return ClaudeResponse(
            text="".join(text_parts).strip(),
            model=str(data.get("model") or payload["model"]),
            stop_reason=data.get("stop_reason"),
            usage=usage,
            raw=data,
        )
