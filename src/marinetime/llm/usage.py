from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .token_guard import TokenBudgetBlocked


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
    video_calls: int = 0


class UsageLedgerError(TokenBudgetBlocked):
    """An unreadable or busy ledger must never reset the provider budget."""


@contextmanager
def ledger_lock(path: str | Path):
    """Serialize read/check/reserve across local processes, including Windows.

    Only ledger I/O holds this lock, never the network request. A crash can leave
    the lock file behind: fail closed until an operator confirms no writer is
    active and removes that lock. Do not guess based on age.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise UsageLedgerError("USAGE_LEDGER_LOCKED") from exc
    try:
        os.close(descriptor)
        yield
    finally:
        lock_path.unlink()


def append_usage(
    record: UsageRecord,
    path: str | Path = "storage/logs/token_ledger.jsonl",
    *,
    event: str = "usage",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> None:
    """Append a durable reservation or settlement; caller holds ledger_lock."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record)
    payload.update(
        schema_version="2.0",
        event=event,
        request_id=request_id,
        guard_tokens=record.guard_tokens,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
    )
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_records(target: Path) -> list[dict]:
    legacy: list[dict] = []
    requests: dict[str, dict] = {}
    for number, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ValueError("object required")
            timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("UTC offset required")
            tokens = []
            for field in (
                "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"
            ):
                value = payload.get(field, 0) if field.startswith("cache_") else payload[field]
                if type(value) is not int or value < 0:
                    raise ValueError("invalid counter")
                tokens.append(value)
            payload["_tokens"] = sum(tokens)
            payload["_day"] = timestamp.astimezone(timezone.utc).date()

            event = payload.get("event", "usage")
            request_id = payload.get("request_id")
            if event == "usage" and request_id is None:
                # Existing pre-v2 records are standalone completed attempts.
                legacy.append(payload)
            elif event == "reserved":
                if not isinstance(request_id, str) or not request_id or request_id in requests:
                    raise ValueError("invalid reservation")
                requests[request_id] = payload
            elif event == "usage":
                previous = requests.get(request_id)
                if previous is None or previous.get("event") != "reserved":
                    raise ValueError("unmatched settlement")
                for field in ("video_id", "task", "prompt_version", "timestamp"):
                    if previous.get(field) != payload.get(field):
                        raise ValueError("settlement identity mismatch")
                requests[request_id] = payload
            else:
                raise ValueError("unknown event")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise UsageLedgerError(f"USAGE_LEDGER_INVALID_LINE:{number}") from exc
    return legacy + list(requests.values())


def load_usage_totals(
    path: str | Path = "storage/logs/token_ledger.jsonl",
    *,
    video_id: str | None = None,
    day: date | None = None,
) -> UsageTotals:
    """Daily tokens use request-start UTC day; video totals span all days.

    Completed requests replace their reservation, so they count once. A timeout,
    invalid usage response or process crash leaves its conservative reservation
    charged. Corrupt records block further calls rather than disappearing.
    """
    target = Path(path)
    if not target.exists():
        return UsageTotals()
    try:
        records = _read_records(target)
    except (OSError, UnicodeError) as exc:
        raise UsageLedgerError("USAGE_LEDGER_UNREADABLE") from exc
    selected_day = day or datetime.now(timezone.utc).date()
    daily_tokens = sum(item["_tokens"] for item in records if item["_day"] == selected_day)
    video_records = [item for item in records if video_id is not None and item.get("video_id") == video_id]
    return UsageTotals(
        daily_tokens=daily_tokens,
        video_tokens=sum(item["_tokens"] for item in video_records),
        video_calls=len(video_records),
    )
