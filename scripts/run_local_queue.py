from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pipeline.auto_alu import run_auto_alu_threshold  # noqa: E402
from marinetime.pilot.local_preprocess import (  # noqa: E402
    LocalModelRuntime,
    preprocess_local_video,
)
from marinetime.pilot.preflight import check_local_stack  # noqa: E402
from marinetime.pilot.queue import (  # noqa: E402
    FAILED_PREPROCESS,
    QueueJob,
    list_jobs,
    requeue_failed_jobs,
    run_local_queue,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Process queued raw videos sequentially. By default, when at least 20 validated "
            "EvidencePacks are waiting without ALUs, automatically run guarded Opus ALU batches."
        )
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
    p.add_argument(
        "--auto-opus-threshold",
        type=int,
        default=20,
        help="Number of ALU-missing EvidencePacks required before automatic Opus starts.",
    )
    p.add_argument(
        "--local-only",
        action="store_true",
        help="Explicitly disable automatic Opus for this run.",
    )
    return p


def _heartbeat(stop_event: threading.Event, source_id: str, interval_seconds: int = 30) -> None:
    started = time.monotonic()
    while not stop_event.wait(interval_seconds):
        elapsed = round(time.monotonic() - started)
        print(
            f"QUEUE_JOB_RUNNING source_id={source_id} elapsed_seconds={elapsed}",
            flush=True,
        )


def _format_error(exc: Exception) -> str:
    detail = " ".join(str(exc).split())[:500]
    suffix = f":{detail}" if detail else ""
    return f"{type(exc).__name__}{suffix}"


def _print_failure_summary(db_path: Path) -> None:
    failed_jobs = [job for job in list_jobs(db_path) if job.status == FAILED_PREPROCESS]
    print("QUEUE_FAILURE_SUMMARY")
    print(f"failed_jobs={len(failed_jobs)}")
    for job in failed_jobs:
        print(
            f"failed_job source_id={job.source_id} attempts={job.attempts} "
            f"file={job.video_path.name} error={job.last_error or 'UNKNOWN'}"
        )


def main() -> int:
    args = parser().parse_args()
    if args.auto_opus_threshold <= 0:
        print("QUEUE_WORKER_FAILED:AUTO_OPUS_THRESHOLD_MUST_BE_POSITIVE", file=sys.stderr)
        return 2

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

    runtime = LocalModelRuntime(
        whisper_model=args.whisper_model,
        language=args.language,
        ocr_lang=args.ocr_lang,
        device=args.device,
        enable_mkldnn=False,
    )
    print("LOCAL_MODEL_RUNTIME reuse_across_jobs=true")
    print(f"LOCAL_MODEL_RUNTIME whisper_model={args.whisper_model} ocr_lang={args.ocr_lang}")

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
                    runtime=runtime,
                )
            except Exception as exc:
                print(
                    f"QUEUE_JOB_FAILED source_id={job.source_id} file={job.video_path.name} "
                    f"error={_format_error(exc)}",
                    file=sys.stderr,
                    flush=True,
                )
                raise
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

    print("QUEUE_WORKER_OK" if result.failed == 0 else "QUEUE_WORKER_PARTIAL_FAILURE")
    print(f"processed={result.processed}")
    print(f"ready={result.ready}")
    print(f"failed={result.failed}")
    _print_failure_summary(args.db)

    if args.local_only:
        print("OPUS_AUTO_DISABLED reason=LOCAL_ONLY")
        print("opus_calls=0")
        return 1 if result.failed else 0

    auto_result = run_auto_alu_threshold(
        evidence_root=args.evidence_root,
        repo_root=ROOT,
        usage_log_path=ROOT / "storage" / "logs" / "token_ledger.jsonl",
        threshold=args.auto_opus_threshold,
    )
    print(f"opus_calls={auto_result.attempted}")

    if result.failed > 0 or auto_result.failed > 0:
        return 1
    if auto_result.paused_reason is not None:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
