from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.queue import list_jobs  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Show Marinetime local raw-video queue status.")
    p.add_argument("--db", type=Path, default=ROOT / "storage" / "marinetime.sqlite3")
    return p


def main() -> int:
    args = parser().parse_args()
    jobs = list_jobs(args.db)
    counts = Counter(job.status for job in jobs)

    print("QUEUE_STATUS")
    print(f"total={len(jobs)}")
    for status in ("PENDING", "PREPROCESSING", "EVIDENCE_READY", "FAILED_PREPROCESS"):
        print(f"{status.lower()}={counts.get(status, 0)}")

    for job in jobs:
        suffix = f" error={job.last_error}" if job.last_error else ""
        print(
            f"job={job.job_id} source_id={job.source_id} status={job.status} "
            f"stage={job.stage} attempts={job.attempts} file={job.video_path.name}{suffix}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
