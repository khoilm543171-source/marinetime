from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.config import ClaudeSettings  # noqa: E402
from marinetime.llm.client import ClaudeAPIError, ClaudeClient  # noqa: E402
from marinetime.llm.token_guard import TokenBudgetBlocked  # noqa: E402
from marinetime.pipeline.alu_extract import ALUExtractionError, extract_alus  # noqa: E402
from marinetime.pipeline.evidence_pack import EvidencePackError  # noqa: E402


SMOKE_VIDEO_ID = "alu-extraction-smoke-check"
LEDGER = ROOT / "storage" / "logs" / "token_ledger.jsonl"
EXPECTED_PROVENANCE = "creator_experience"


def smoke_pack() -> dict:
    return {
        "schema_version": "1.0",
        "source_id": "SMOKE-VID-001",
        "provenance_class": EXPECTED_PROVENANCE,
        "context": {
            "equipment": "centrifugal pump",
            "maker": "unknown",
            "model": "unknown",
            "vessel_type": "unknown",
        },
        "transcript_segments": [
            {
                "evidence_id": "SEG-001",
                "start_ms": 0,
                "end_ms": 2500,
                "text": "The creator says: This is the centrifugal pump used in the cooling-water line.",
            }
        ],
        "ocr_hits": [],
        "frames": [],
        "preprocess_version": "synthetic-smoke-v1",
    }


def _assert_live_invariants(result) -> str | None:
    if not result.alus:
        return "NO_ALUS_RETURNED"
    if not any(item.decision.accepted_for_education for item in result.alus):
        return "NO_EDUCATIONAL_ALU_ACCEPTED"

    for item in result.alus:
        alu = item.alu
        if alu.get("provenance_class") != EXPECTED_PROVENANCE:
            return "PROVENANCE_CHANGED"
        if alu.get("verification_status") != "unverified":
            return "MODEL_SELF_VERIFIED"
        if alu.get("rendering_scope") == "authoritative_operational":
            return "MODEL_CLAIMED_OPERATIONAL_SCOPE"
        if item.decision.accepted_for_operational_use:
            return "UNVERIFIED_ALU_BECAME_OPERATIONAL"
    return None


def main() -> int:
    try:
        settings = ClaudeSettings.from_env()
        with ClaudeClient(settings) as client:
            result = extract_alus(
                client=client,
                evidence_pack=smoke_pack(),
                video_id=SMOKE_VIDEO_ID,
                repo_root=ROOT,
                usage_log_path=LEDGER,
            )
    except (
        ValueError,
        ClaudeAPIError,
        TokenBudgetBlocked,
        EvidencePackError,
        ALUExtractionError,
    ) as exc:
        print(f"FAILED: {exc}")
        return 1

    invariant_error = _assert_live_invariants(result)
    if invariant_error:
        print(f"FAILED: {invariant_error}")
        return 1

    print("ALU_EXTRACTION_OK")
    print(f"model={result.model_result.model}")
    print(f"prompt_version={result.model_result.prompt_version}")
    print(f"input_tokens={result.model_result.input_tokens}")
    print(f"output_tokens={result.model_result.output_tokens}")
    print(f"alu_count={len(result.alus)}")
    for item in result.alus:
        alu = item.alu
        print(
            "alu="
            f"{alu['alu_id']} refs={alu['evidence_refs']} "
            f"provenance={alu['provenance_class']} "
            f"verification={alu['verification_status']} "
            f"claim_scope={alu['claim_scope']} "
            f"education={item.decision.accepted_for_education} "
            f"operation={item.decision.accepted_for_operational_use} "
            f"reasons={list(item.decision.reasons)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
