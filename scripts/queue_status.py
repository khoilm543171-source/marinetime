from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.queue import list_jobs  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Show Marinetime local raw-video and ALU status.")
    p.add_argument("--db", type=Path, default=ROOT / "storage" / "marinetime.sqlite3")
    p.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "storage" / "evidence",
    )
    p.add_argument(
        "--summary-only",
        action="store_true",
        help="Print queue/evidence/ALU counts without listing every queue job.",
    )
    return p


def _valid_alu_file(path: Path, source_id: str) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("source_id") == source_id
        and isinstance(payload.get("alus"), list)
        and bool(payload["alus"])
    )


def _alu_status(evidence_root: Path) -> tuple[int, int, list[str]]:
    evidence_count = 0
    completed = 0
    waiting: list[str] = []
    if not evidence_root.exists():
        return evidence_count, completed, waiting

    for evidence_path in sorted(evidence_root.glob("*/evidence_pack.json")):
        if not evidence_path.is_file():
            continue
        try:
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        source_id = payload.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            continue
        evidence_count += 1
        alu_path = evidence_path.parent / "alus.json"
        if _valid_alu_file(alu_path, source_id):
            completed += 1
        else:
            waiting.append(source_id)

    return evidence_count, completed, waiting


def main() -> int:
    args = parser().parse_args()
    jobs = list_jobs(args.db)
    counts = Counter(job.status for job in jobs)

    print("QUEUE_STATUS")
    print(f"total={len(jobs)}")
    for status in ("PENDING", "PREPROCESSING", "EVIDENCE_READY", "FAILED_PREPROCESS"):
        print(f"{status.lower()}={counts.get(status, 0)}")

    evidence_count, alu_completed, alu_waiting = _alu_status(args.evidence_root)
    print("ALU_STATUS")
    print(f"evidence_packs={evidence_count}")
    print(f"alus_completed={alu_completed}")
    print(f"missing_alus={len(alu_waiting)}")

    if args.summary_only:
        return 0

    for job in jobs:
        suffix = f" error={job.last_error}" if job.last_error else ""
        print(
            f"job={job.job_id} source_id={job.source_id} status={job.status} "
            f"stage={job.stage} attempts={job.attempts} file={job.video_path.name}{suffix}"
        )

    for source_id in alu_waiting:
        print(f"alu_waiting={source_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
