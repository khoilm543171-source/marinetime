from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class UsageRecord:
    task: str
    prompt_version: str
    model: str
    input_tokens: int
    output_tokens: int
    video_id: str | None = None
    success: bool = True
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def guard_tokens(self) -> int:
        """Conservative token footprint used by Marinetime's safety budget.

        Keep cache counters separate in the ledger because gateway billing/quota
        semantics may differ. For the local guard we count all reported token
        classes so a provider-specific discount can never silently weaken the
        kill-switch.
        """
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


@dataclass(frozen=True)
class UsageTotals:
    daily_tokens: int = 0
    video_tokens: int = 0


def append_usage(
    record: UsageRecord,
    path: str | Path = "storage/logs/token_ledger.jsonl",
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record)
    payload["guard_tokens"] = record.guard_tokens
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_usage_totals(
    path: str | Path = "storage/logs/token_ledger.jsonl",
    *,
    video_id: str | None = None,
    day: date | None = None,
) -> UsageTotals:
    """Read actual provider usage already recorded for the current UTC day.

    Malformed ledger lines are ignored rather than breaking a job. The ledger
    is observability data, not an authority for source/evidence claims.
    """
    target = Path(path)
    if not target.exists():
        return UsageTotals()

    selected_day = day or datetime.now(timezone.utc).date()
    daily_tokens = 0
    video_tokens = 0

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            timestamp = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue

        if timestamp.astimezone(timezone.utc).date() != selected_day:
            continue

        guard_tokens = int(
            payload.get(
                "guard_tokens",
                int(payload.get("input_tokens", 0) or 0)
                + int(payload.get("output_tokens", 0) or 0)
                + int(payload.get("cache_creation_input_tokens", 0) or 0)
                + int(payload.get("cache_read_input_tokens", 0) or 0),
            )
            or 0
        )
        daily_tokens += guard_tokens
        if video_id is not None and payload.get("video_id") == video_id:
            video_tokens += guard_tokens

    return UsageTotals(daily_tokens=daily_tokens, video_tokens=video_tokens)
