from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pipeline.auto_alu import run_auto_alu_threshold  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Drain the current ALU backlog immediately, including a partial group. "
            "Use only when provider quota/time is intentionally available."
        )
    )
    p.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "storage" / "evidence",
    )
    return p


def main() -> int:
    args = parser().parse_args()
    result = run_auto_alu_threshold(
        evidence_root=args.evidence_root,
        repo_root=ROOT,
        usage_log_path=ROOT / "storage" / "logs" / "token_ledger.jsonl",
        threshold=20,
        drain=True,
    )
    print(f"opus_calls={result.attempted}")
    print(f"skipped={result.skipped}")

    if result.paused_reason is not None:
        return 3
    if result.failed > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
