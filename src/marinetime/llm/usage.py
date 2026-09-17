from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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


def append_usage(record: UsageRecord, path: str | Path = "storage/logs/token_ledger.jsonl") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record)
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
