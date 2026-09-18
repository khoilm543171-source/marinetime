from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.catalog.creator import load_creator_registry  # noqa: E402
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
    p.add_argument(
        "--creator-id",
        default=None,
        help="Deterministic creator ID for this import batch; must exist in config/creators.json.",
    )
    p.add_argument(
        "--batch-id",
        default=None,
        help="Stable import batch ID recorded on every discovered source.",
    )
    p.add_argument(
        "--creator-registry",
        type=Path,
        default=ROOT / "config" / "creators.json",
    )
    p.add_argument("--recursive", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    context = dict(args.context_json)
    try:
        if args.creator_id is not None:
            registry = load_creator_registry(args.creator_registry)
            known_ids = {entry.creator_id for entry in registry}
            if args.creator_id not in known_ids:
                raise ValueError(f"UNKNOWN_CREATOR_ID:{args.creator_id}")
            existing_creator = context.get("creator_id")
            if existing_creator not in (None, args.creator_id):
                raise ValueError("CONTEXT_CREATOR_CONFLICT")
            context["creator_id"] = args.creator_id

        if args.batch_id is not None:
            batch_id = args.batch_id.strip()
            if not batch_id:
                raise ValueError("BATCH_ID_EMPTY")
            batches = context.get("import_batches", [])
            if not isinstance(batches, list):
                raise ValueError("CONTEXT_IMPORT_BATCHES_NOT_LIST")
            if batch_id not in batches:
                batches = [*batches, batch_id]
            context["import_batches"] = batches

        result = enqueue_raw_folder(
            input_dir=args.input,
            db_path=args.db,
            provenance_class=args.provenance,
            context=context,
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
    print(f"updated_existing_metadata={result.updated_existing_metadata}")
    print(f"metadata_conflicts={result.metadata_conflicts}")
    if args.creator_id:
        print(f"creator_id={args.creator_id}")
    if args.batch_id:
        print(f"batch_id={args.batch_id}")
    print(f"adopted_existing_evidence={reconcile.adopted_jobs}")
    print(f"existing_artifacts_scanned={reconcile.scanned_artifacts}")
    print(f"invalid_existing_artifacts={reconcile.skipped_invalid_artifacts}")
    print(f"existing_identity_conflicts={reconcile.skipped_conflicts}")
    print(f"db={args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
