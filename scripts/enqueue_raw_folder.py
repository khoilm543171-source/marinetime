from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.queue import enqueue_raw_folder  # noqa: E402
from marinetime.pilot.queue_reconcile import (  # noqa: E402
    reconcile_queue_with_existing_evidence,
)


def _context(value: str) -> dict:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("--context-json must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("--context-json must decode to an object")
    return payload


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scan a raw-video folder and add unseen videos to the durable local queue."
    )
    p.add_argument("--input", type=Path, default=ROOT / "storage" / "raw")
    p.add_argument("--db", type=Path, default=ROOT / "storage" / "marinetime.sqlite3")
    p.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "storage" / "evidence",
        help="Existing evidence tree used to adopt videos that were processed before the queue existed.",
    )
    p.add_argument(
        "--provenance",
        default="creator_experience",
        choices=(
            "standard",
            "maker_manual",
            "regulatory",
            "textbook",
            "onboard_heuristic",
            "creator_experience",
            "case_specific",
            "unverified",
        ),
    )
    p.add_argument("--context-json", type=_context, default={})
    p.add_argument("--recursive", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        result = enqueue_raw_folder(
            input_dir=args.input,
            db_path=args.db,
            provenance_class=args.provenance,
            context=args.context_json,
            recursive=args.recursive,
        )
        reconcile = reconcile_queue_with_existing_evidence(
            db_path=args.db,
            evidence_root=args.evidence_root,
        )
    except ValueError as exc:
        print(f"QUEUE_ENQUEUE_FAILED:{exc}", file=sys.stderr)
        return 1

    print("QUEUE_ENQUEUE_OK")
    print(f"discovered={result.discovered}")
    print(f"enqueued={result.enqueued}")
    print(f"skipped_existing={result.skipped_existing}")
    print(f"adopted_existing_evidence={reconcile.adopted_jobs}")
    print(f"existing_artifacts_scanned={reconcile.scanned_artifacts}")
    print(f"invalid_existing_artifacts={reconcile.skipped_invalid_artifacts}")
    print(f"existing_identity_conflicts={reconcile.skipped_conflicts}")
    print(f"db={args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
