from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.local_preprocess import LocalPreprocessError, preprocess_local_video  # noqa: E402
from marinetime.pilot.preflight import check_local_stack  # noqa: E402


def _context(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("--context-json must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("--context-json must decode to an object")
    return parsed


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build a traceable local EvidencePack from one pilot video. No Opus/API call."
    )
    p.add_argument("--video", required=True, type=Path)
    p.add_argument("--source-id", required=True)
    p.add_argument(
        "--provenance",
        required=True,
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
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--context-json", type=_context, default={})
    p.add_argument("--whisper-model", default="small")
    p.add_argument("--language", default=None)
    p.add_argument("--ocr-lang", default="en")
    p.add_argument("--max-frames", type=int, default=8)
    p.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    return p


def main() -> int:
    args = parser().parse_args()
    report = check_local_stack()
    if not report.raw_video_ready:
        print(
            "LOCAL_STACK_NOT_READY:" + ",".join(report.missing_required),
            file=sys.stderr,
        )
        return 2

    try:
        pack = preprocess_local_video(
            video_path=args.video,
            output_dir=args.out,
            source_id=args.source_id,
            provenance_class=args.provenance,
            context=args.context_json,
            whisper_model=args.whisper_model,
            language=args.language,
            ocr_lang=args.ocr_lang,
            max_frames=args.max_frames,
            device=args.device,
        )
    except (LocalPreprocessError, ValueError) as exc:
        print(f"PILOT_PREPROCESS_FAILED:{exc}", file=sys.stderr)
        return 1

    print("PILOT_PREPROCESS_OK")
    print(f"source_id={pack['source_id']}")
    print(f"transcript_segments={len(pack['transcript_segments'])}")
    print(f"frames={len(pack['frames'])}")
    print(f"ocr_hits={len(pack['ocr_hits'])}")
    print(f"evidence_pack={args.out / 'evidence_pack.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
