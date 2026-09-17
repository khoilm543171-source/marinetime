from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.local_preprocess import preprocess_local_video  # noqa: E402
from marinetime.pilot.preflight import check_local_stack  # noqa: E402
from marinetime.pilot.queue import (  # noqa: E402
    QueueJob,
    requeue_failed_jobs,
    run_local_queue,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Process queued raw videos sequentially with local tools only. No Opus/API call."
    )
    p.add_argument("--db", type=Path, default=ROOT / "storage" / "marinetime.sqlite3")
    p.add_argument(
        "--evidence-root", type=Path, default=ROOT / "storage" / "evidence"
    )
    p.add_argument("--whisper-model", default="small")
    p.add_argument("--language", default=None)
    p.add_argument("--ocr-lang", default="en")
    p.add_argument("--max-frames", type=int, default=8)
    p.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--retry-failed", action="store_true")
    return p


def _heartbeat(stop_event: threading.Event, source_id: str, interval_seconds: int = 30) -> None:
    started = time.monotonic()
    while not stop_event.wait(interval_seconds):
        elapsed = round(time.monotonic() - started)
        print(
            f"QUEUE_JOB_RUNNING source_id={source_id} elapsed_seconds={elapsed}",
            flush=True,
        )


def main() -> int:
    args = parser().parse_args()
    report = check_local_stack()
    if not report.raw_video_ready:
        print(
            "LOCAL_STACK_NOT_READY:" + ",".join(report.missing_required),
            file=sys.stderr,
        )
        return 2

    if args.retry_failed:
        count = requeue_failed_jobs(args.db)
        print(f"QUEUE_REQUEUED_FAILED count={count}")

    def processor(job: QueueJob, output_dir: Path) -> object:
        print(
            f"QUEUE_JOB_START source_id={job.source_id} file={job.video_path.name}",
            flush=True,
        )
        stop_event = threading.Event()
        heartbeat = threading.Thread(
            target=_heartbeat,
            args=(stop_event, job.source_id),
            daemon=True,
        )
        heartbeat.start()
        try:
            pack = preprocess_local_video(
                video_path=job.video_path,
                output_dir=output_dir,
                source_id=job.source_id,
                provenance_class=job.provenance_class,
                context=job.context,
                whisper_model=args.whisper_model,
                language=args.language,
                ocr_lang=args.ocr_lang,
                max_frames=args.max_frames,
                device=args.device,
            )
        finally:
            stop_event.set()
            heartbeat.join(timeout=1)
        print(
            f"QUEUE_JOB_EVIDENCE_READY source_id={job.source_id}",
            flush=True,
        )
        return pack

    try:
        result = run_local_queue(
            db_path=args.db,
            evidence_root=args.evidence_root,
            processor=processor,
            limit=args.limit,
        )
    except ValueError as exc:
        print(f"QUEUE_WORKER_FAILED:{exc}", file=sys.stderr)
        return 1

    print("QUEUE_WORKER_OK")
    print(f"processed={result.processed}")
    print(f"ready={result.ready}")
    print(f"failed={result.failed}")
    print("opus_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
