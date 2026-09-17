from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.config import ClaudeSettings  # noqa: E402
from marinetime.llm.client import ClaudeAPIError, ClaudeClient  # noqa: E402
from marinetime.llm.token_guard import TokenBudgetBlocked  # noqa: E402
from marinetime.pipeline.alu_extract import (  # noqa: E402
    ALUExtractionError,
    ALUExtractionResult,
    extract_alus,
)
from marinetime.pipeline.evidence_pack import EvidencePackError, validate_evidence_pack  # noqa: E402


LEDGER = ROOT / "storage" / "logs" / "token_ledger.jsonl"


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"INPUT_NOT_FOUND:{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"INPUT_NOT_JSON:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("INPUT_MUST_BE_JSON_OBJECT")
    return payload


def _build_output(result: ALUExtractionResult, evidence_pack: dict[str, Any]) -> dict[str, Any]:
    model = result.model_result
    return {
        "schema_version": "1.0",
        "source_id": evidence_pack["source_id"],
        "model": model.model,
        "prompt_version": model.prompt_version,
        "usage": {
            "input_tokens": model.input_tokens,
            "output_tokens": model.output_tokens,
            "cache_creation_input_tokens": model.cache_creation_input_tokens,
            "cache_read_input_tokens": model.cache_read_input_tokens,
            "guard_tokens": model.guard_tokens,
        },
        "alus": [
            {
                "alu": item.alu,
                "decision": {
                    "accepted_for_reference": item.decision.accepted_for_reference,
                    "accepted_for_education": item.decision.accepted_for_education,
                    "accepted_for_operational_use": item.decision.accepted_for_operational_use,
                    "reasons": list(item.decision.reasons),
                },
            }
            for item in result.alus
        ],
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run one guarded Opus semantic pass over a validated local EvidencePack."
    )
    p.add_argument("--evidence", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        evidence_pack = _load_json_object(args.evidence)
        summary = validate_evidence_pack(evidence_pack)
    except (ValueError, EvidencePackError) as exc:
        print(f"ALU_REAL_FAILED:{exc}", file=sys.stderr)
        return 2

    print("OPUS_ALU_EXTRACTION_START")
    print(f"source_id={summary.source_id}")

    try:
        settings = ClaudeSettings.from_env()
        with ClaudeClient(settings) as client:
            result = extract_alus(
                client=client,
                evidence_pack=evidence_pack,
                repo_root=ROOT,
                usage_log_path=LEDGER,
            )
    except (
        ValueError,
        TypeError,
        ClaudeAPIError,
        TokenBudgetBlocked,
        EvidencePackError,
        ALUExtractionError,
    ) as exc:
        print(f"ALU_REAL_FAILED:{exc}", file=sys.stderr)
        return 1

    artifact = _build_output(result, evidence_pack)
    _write_json_atomic(args.out, artifact)

    educational = sum(
        1 for item in result.alus if item.decision.accepted_for_education
    )
    operational = sum(
        1 for item in result.alus if item.decision.accepted_for_operational_use
    )

    print("ALU_REAL_OK")
    print(f"source_id={summary.source_id}")
    print(f"model={result.model_result.model}")
    print(f"prompt_version={result.model_result.prompt_version}")
    print(f"input_tokens={result.model_result.input_tokens}")
    print(f"output_tokens={result.model_result.output_tokens}")
    print(f"alu_count={len(result.alus)}")
    print(f"accepted_for_education={educational}")
    print(f"accepted_for_operational_use={operational}")
    print(f"artifact={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
