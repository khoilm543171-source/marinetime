from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marinetime.llm.client import ClaudeClient
from marinetime.llm.router import LLMTaskResult, run_task
from marinetime.validation.safety import ValidationDecision, validate_alu

from .evidence_pack import EvidencePackSummary, validate_evidence_pack


class ALUExtractionError(ValueError):
    """Raised when model output cannot be trusted as a traceable ALU artifact."""


SUPPORTED_ALU_SCHEMA_VERSION = "1.0"
STATEMENT_TYPES = {
    "observed_fact",
    "creator_statement",
    "inferred_relationship",
    "procedure",
    "recommendation",
    "question",
    "unknown",
}
SUPPORT_LEVELS = {
    "directly_supported",
    "partially_supported",
    "context_limited",
    "unsupported",
}
EXTRACTION_RENDERING_SCOPES = {
    "source_specific",
    "context_specific",
    "general_educational",
}
CONTEXT_REQUIREMENTS = {
    "minimal",
    "equipment_specific",
    "maker_specific",
    "vessel_specific",
    "regulatory_specific",
}
CLAIM_SCOPES = set(CONTEXT_REQUIREMENTS)
PROVENANCE_CLASSES = {
    "standard",
    "maker_manual",
    "regulatory",
    "textbook",
    "onboard_heuristic",
    "creator_experience",
    "case_specific",
    "unverified",
}
VERIFICATION_STATUSES = {"unverified", "pending", "verified", "rejected"}


@dataclass(frozen=True)
class ValidatedALU:
    alu: dict[str, Any]
    decision: ValidationDecision


@dataclass(frozen=True)
class ALUExtractionResult:
    model_result: LLMTaskResult
    alus: tuple[ValidatedALU, ...]


def _require_nonempty_string(item: dict[str, Any], field: str, index: int) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ALUExtractionError(f"ALU_{index}_INVALID_{field.upper()}")
    return value.strip()


def _require_enum(
    item: dict[str, Any],
    field: str,
    allowed: set[str],
    index: int,
) -> str:
    value = item.get(field)
    if value not in allowed:
        raise ALUExtractionError(f"ALU_{index}_INVALID_{field.upper()}:{value}")
    return str(value)


def _require_object_or_null(item: dict[str, Any], field: str, index: int) -> None:
    if field not in item:
        raise ALUExtractionError(f"ALU_{index}_MISSING_{field.upper()}")
    value = item[field]
    if value is not None and not isinstance(value, dict):
        raise ALUExtractionError(f"ALU_{index}_INVALID_{field.upper()}")


def _decode_payload(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ALUExtractionError("MODEL_OUTPUT_NOT_JSON") from exc

    if isinstance(payload, dict):
        payload = payload.get("alus")
    if not isinstance(payload, list):
        raise ALUExtractionError("MODEL_OUTPUT_MUST_CONTAIN_ALUS_ARRAY")
    if not payload:
        raise ALUExtractionError("MODEL_OUTPUT_EMPTY_ALUS")
    if not all(isinstance(item, dict) for item in payload):
        raise ALUExtractionError("MODEL_OUTPUT_ALU_NOT_OBJECT")
    return payload


def parse_alu_response(
    text: str,
    evidence_pack: dict[str, Any],
) -> tuple[ValidatedALU, ...]:
    """Parse and deterministically validate one semantic extraction response.

    Model output is never silently repaired. A malformed contract, fabricated
    evidence reference, duplicate ALU id, source/provenance mismatch, operational
    scope claim, or a model trying to self-mark an extraction as verified rejects
    the extraction artifact.
    """
    summary: EvidencePackSummary = validate_evidence_pack(evidence_pack)
    candidates = _decode_payload(text)
    seen_alu_ids: set[str] = set()
    validated: list[ValidatedALU] = []

    for index, alu in enumerate(candidates):
        alu_id = _require_nonempty_string(alu, "alu_id", index)
        if alu_id in seen_alu_ids:
            raise ALUExtractionError(f"DUPLICATE_ALU_ID:{alu_id}")
        seen_alu_ids.add(alu_id)

        source_id = _require_nonempty_string(alu, "source_id", index)
        if source_id != summary.source_id:
            raise ALUExtractionError(f"ALU_{index}_SOURCE_MISMATCH")

        schema_version = _require_nonempty_string(alu, "schema_version", index)
        if schema_version != SUPPORTED_ALU_SCHEMA_VERSION:
            raise ALUExtractionError(
                f"ALU_{index}_UNSUPPORTED_SCHEMA_VERSION:{schema_version}"
            )

        _require_nonempty_string(alu, "statement", index)
        _require_enum(alu, "statement_type", STATEMENT_TYPES, index)
        _require_enum(alu, "support_level", SUPPORT_LEVELS, index)
        _require_enum(alu, "rendering_scope", EXTRACTION_RENDERING_SCOPES, index)
        _require_enum(alu, "claim_scope", CLAIM_SCOPES, index)
        _require_enum(alu, "context_requirement", CONTEXT_REQUIREMENTS, index)
        provenance = _require_enum(alu, "provenance_class", PROVENANCE_CLASSES, index)
        verification = _require_enum(
            alu, "verification_status", VERIFICATION_STATUSES, index
        )

        if provenance != summary.provenance_class:
            raise ALUExtractionError(f"ALU_{index}_PROVENANCE_MISMATCH")
        if verification != "unverified":
            raise ALUExtractionError(f"ALU_{index}_MODEL_SELF_VERIFICATION_FORBIDDEN")

        refs = alu.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ALUExtractionError(f"ALU_{index}_MISSING_EVIDENCE_REFS")
        for ref in refs:
            if not isinstance(ref, str) or ref not in summary.evidence_ids:
                raise ALUExtractionError(f"ALU_{index}_UNKNOWN_EVIDENCE_REF:{ref}")

        if not isinstance(alu.get("context"), dict):
            raise ALUExtractionError(f"ALU_{index}_INVALID_CONTEXT")

        safety = alu.get("safety")
        if not isinstance(safety, dict):
            raise ALUExtractionError(f"ALU_{index}_INVALID_SAFETY")
        if not isinstance(safety.get("safety_critical"), bool):
            raise ALUExtractionError(f"ALU_{index}_INVALID_SAFETY_CRITICAL")
        if not isinstance(safety.get("numeric_claim"), bool):
            raise ALUExtractionError(f"ALU_{index}_INVALID_NUMERIC_CLAIM")

        _require_object_or_null(alu, "numeric", index)
        _require_object_or_null(alu, "relation", index)

        validated.append(ValidatedALU(alu=alu, decision=validate_alu(alu)))

    return tuple(validated)


def extract_alus(
    *,
    client: ClaudeClient,
    evidence_pack: dict[str, Any],
    video_id: str,
    repo_root: str | Path = ".",
    usage_log_path: str | Path = "storage/logs/token_ledger.jsonl",
) -> ALUExtractionResult:
    """Run the single expensive semantic pass for one validated EvidencePack."""
    validate_evidence_pack(evidence_pack)
    dynamic_input = json.dumps(evidence_pack, ensure_ascii=False, separators=(",", ":"))
    model_result = run_task(
        client=client,
        task="alu_extract",
        dynamic_input=dynamic_input,
        video_id=video_id,
        repo_root=repo_root,
        usage_log_path=usage_log_path,
    )
    alus = parse_alu_response(model_result.text, evidence_pack)
    return ALUExtractionResult(model_result=model_result, alus=alus)
