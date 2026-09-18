from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.catalog.creator import load_creator_registry, resolve_creator  # noqa: E402
from marinetime.pilot.queue import list_jobs  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build a non-destructive source-to-creator catalog from the local queue."
    )
    p.add_argument("--db", type=Path, default=ROOT / "storage" / "marinetime.sqlite3")
    p.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "config" / "creators.json",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT / "storage" / "catalog" / "source_creators.json",
    )
    return p


def main() -> int:
    args = parser().parse_args()
    registry = load_creator_registry(args.registry)
    jobs = list_jobs(args.db)

    records = []
    counts: dict[str, int] = {}
    for job in jobs:
        explicit_creator = job.context.get("creator_id")
        resolution = resolve_creator(
            registry=registry,
            explicit_creator_id=explicit_creator if isinstance(explicit_creator, str) else None,
            filename=job.video_path.name,
        )
        counts[resolution.creator_id] = counts.get(resolution.creator_id, 0) + 1
        records.append(
            {
                "source_id": job.source_id,
                "video_filename": job.video_path.name,
                "creator_id": resolution.creator_id,
                "display_name": resolution.display_name,
                "resolution_source": resolution.source,
                "confidence": resolution.confidence,
                "matched_value": resolution.matched_value,
                "import_batches": [
                    value
                    for value in job.context.get("import_batches", [])
                    if isinstance(value, str)
                ]
                if isinstance(job.context.get("import_batches", []), list)
                else [],
            }
        )

    payload = {
        "schema_version": "1.0",
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(args.output)

    print("CREATOR_CATALOG_OK")
    print(f"total={len(records)}")
    for creator_id in sorted(counts):
        print(f"creator={creator_id} count={counts[creator_id]}")
    print(f"artifact={args.output}")
    print("opus_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
