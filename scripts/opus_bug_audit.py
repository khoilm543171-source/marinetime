from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.config import ClaudeSettings  # noqa: E402
from marinetime.llm.client import ClaudeAPIError, ClaudeClient  # noqa: E402
from marinetime.llm.router import run_task  # noqa: E402
from marinetime.llm.token_guard import TokenBudgetBlocked  # noqa: E402
from marinetime.pilot.queue import FAILED_PREPROCESS, list_jobs  # noqa: E402


LEDGER = ROOT / "storage" / "logs" / "token_ledger.jsonl"
DEFAULT_DB = ROOT / "storage" / "marinetime.sqlite3"
DEFAULT_OUT = ROOT / "storage" / "reports" / "opus_bug_audit_latest.md"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run one guarded Opus audit over current local preprocessing failures."
    )
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--timeout-seconds",
        type=float,
        default=300.0,
        help="Read timeout for this one-shot Opus audit only; no automatic retry is performed.",
    )
    p.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Optional saved console log to include in the audit packet.",
    )
    return p


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return f"unavailable:{type(exc).__name__}"
    first = (result.stdout or result.stderr or "").splitlines()
    return first[0] if first else f"returncode={result.returncode}"


def _read_text(path: Path, *, max_chars: int = 18000) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated by audit pack]..."


def _build_packet(db_path: Path, log_path: Path | None) -> str:
    failed = [job for job in list_jobs(db_path) if job.status == FAILED_PREPROCESS]
    failed_payload = [
        {
            "source_id": job.source_id,
            "attempts": job.attempts,
            "file": job.video_path.name,
            "last_error": job.last_error,
        }
        for job in failed
    ]

    environment = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ffmpeg": _ffmpeg_version(),
        "torch": _package_version("torch"),
        "torchcodec": _package_version("torchcodec"),
        "whisperx": _package_version("whisperx"),
        "paddlepaddle": _package_version("paddlepaddle"),
        "paddleocr": _package_version("paddleocr"),
        "scenedetect": _package_version("scenedetect"),
    }

    code_files = [
        ROOT / "src" / "marinetime" / "pilot" / "local_preprocess.py",
        ROOT / "src" / "marinetime" / "pilot" / "media.py",
        ROOT / "scripts" / "run_local_queue.py",
    ]

    sections = [
        "# Runtime environment\n~~~json\n"
        + json.dumps(environment, ensure_ascii=False, indent=2)
        + "\n~~~",
        "# Failed queue jobs\n~~~json\n"
        + json.dumps(failed_payload, ensure_ascii=False, indent=2)
        + "\n~~~",
    ]

    if log_path is not None:
        if not log_path.is_file():
            raise ValueError(f"LOG_NOT_FOUND:{log_path}")
        sections.append(
            "# Optional console log\n~~~text\n"
            + _read_text(log_path, max_chars=12000)
            + "\n~~~"
        )

    for path in code_files:
        sections.append(
            f"# Repository file: {path.relative_to(ROOT).as_posix()}\n~~~python\n"
            + _read_text(path)
            + "\n~~~"
        )

    return "\n\n".join(sections)


def main() -> int:
    args = parser().parse_args()
    try:
        if args.timeout_seconds <= 0:
            raise ValueError("TIMEOUT_SECONDS_MUST_BE_POSITIVE")
        packet = _build_packet(args.db, args.log)
        settings = replace(
            ClaudeSettings.from_env(),
            timeout_seconds=args.timeout_seconds,
        )
    except ValueError as exc:
        print(f"OPUS_BUG_AUDIT_FAILED:{exc}", file=sys.stderr)
        return 2

    print("OPUS_NOTICE task=bug_audit")
    print(f"provider={settings.provider}")
    print(f"model={settings.model}")
    print(f"timeout_seconds={settings.timeout_seconds:g}")
    print("reason=explicit_user_requested_bug_audit")
    print("automatic_retry=false")
    print("This call will consume guarded Marinetime Opus quota.", flush=True)

    try:
        with ClaudeClient(settings) as client:
            result = run_task(
                client=client,
                task="bug_audit",
                dynamic_input=packet,
                video_id="BUG-AUDIT-FRAME-EXTRACT",
                max_output_tokens=2500,
                repo_root=ROOT,
                usage_log_path=LEDGER,
            )
    except (ClaudeAPIError, TokenBudgetBlocked, ValueError, TypeError) as exc:
        print(f"OPUS_BUG_AUDIT_FAILED:{exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(result.text + "\n", encoding="utf-8")

    print("OPUS_BUG_AUDIT_OK")
    print(f"model={result.model}")
    print(f"prompt_version={result.prompt_version}")
    print(f"input_tokens={result.input_tokens}")
    print(f"output_tokens={result.output_tokens}")
    print(f"artifact={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
