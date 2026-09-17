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
TRUNCATION_STOP_REASONS = {"max_tokens", "max_output_tokens", "length"}


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


def _is_unknown_context_value(value: Any) -> bool:
    return value in (None, "", "unknown", [])


def _validate_context_boundary(
    alu_context: dict[str, Any],
    evidence_context: dict[str, Any],
    index: int,
) -> None:
    """Prevent the model from promoting unknown source context into known facts."""
    for key, value in alu_context.items():
        if _is_unknown_context_value(value):
            continue
        source_value = evidence_context.get(key)
        if _is_unknown_context_value(source_value):
            raise ALUExtractionError(f"ALU_{index}_CONTEXT_PROMOTION_FORBIDDEN:{key}")
        if value != source_value:
            raise ALUExtractionError(f"ALU_{index}_CONTEXT_MISMATCH:{key}")


def build_semantic_evidence_view(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    """Project a validated EvidencePack into the minimal text needed by Opus.

    Geometry, hashes and artifact paths remain in the canonical EvidencePack and
    are recoverable by stable evidence_id. They are not semantic input and can
    consume a large token budget (especially OCR polygons), so they are omitted
    from the model-facing view without changing provenance or traceability.
    """
    validate_evidence_pack(evidence_pack)

    transcripts = [
        {
            "evidence_id": item["evidence_id"],
            "start_ms": item["start_ms"],
            "end_ms": item["end_ms"],
            "text": item["text"],
        }
        for item in evidence_pack["transcript_segments"]
    ]

    ocr_hits: list[dict[str, Any]] = []
    for item in evidence_pack["ocr_hits"]:
        compact: dict[str, Any] = {
            "evidence_id": item["evidence_id"],
            "timestamp_ms": item["timestamp_ms"],
            "text": item["text"],
        }
        score = item.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            compact["score"] = score
        ocr_hits.append(compact)

    frames = [
        {"evidence_id": item["evidence_id"], "timestamp_ms": item["timestamp_ms"]}
        for item in evidence_pack["frames"]
    ]

    return {
        "schema_version": evidence_pack["schema_version"],
        "source_id": evidence_pack["source_id"],
        "provenance_class": evidence_pack["provenance_class"],
        "context": evidence_pack["context"],
        "transcript_segments": transcripts,
        "ocr_hits": ocr_hits,
        "frames": frames,
        "preprocess_version": evidence_pack["preprocess_version"],
    }


def _decode_payload(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        raise ALUExtractionError("MODEL_OUTPUT_EMPTY")
    if stripped.startswith("```"):
        raise ALUExtractionError("MODEL_OUTPUT_WRAPPED_IN_MARKDOWN")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ALUExtractionError("MODEL_OUTPUT_NOT_JSON") from exc

    if not isinstance(payload, dict):
        raise ALUExtractionError("MODEL_OUTPUT_MUST_BE_OBJECT_WITH_ALUS")
    candidates = payload.get("alus")
    if not isinstance(candidates, list):
        raise ALUExtractionError("MODEL_OUTPUT_MUST_CONTAIN_ALUS_ARRAY")
    if not candidates:
        raise ALUExtractionError("MODEL_OUTPUT_EMPTY_ALUS")
    if not all(isinstance(item, dict) for item in candidates):
        raise ALUExtractionError("MODEL_OUTPUT_ALU_NOT_OBJECT")
    return candidates


def parse_alu_response(
    text: str,
    evidence_pack: dict[str, Any],
) -> tuple[ValidatedALU, ...]:
    """Parse and deterministically validate one semantic extraction response."""
    summary: EvidencePackSummary = validate_evidence_pack(evidence_pack)
    candidates = _decode_payload(text)
    evidence_context = evidence_pack["context"]
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
        seen_refs: set[str] = set()
        for ref in refs:
            if not isinstance(ref, str) or ref not in summary.evidence_ids:
                raise ALUExtractionError(f"ALU_{index}_UNKNOWN_EVIDENCE_REF:{ref}")
            if ref in seen_refs:
                raise ALUExtractionError(f"ALU_{index}_DUPLICATE_EVIDENCE_REF:{ref}")
            seen_refs.add(ref)

        alu_context = alu.get("context")
        if not isinstance(alu_context, dict):
            raise ALUExtractionError(f"ALU_{index}_INVALID_CONTEXT")
        _validate_context_boundary(alu_context, evidence_context, index)

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
    repo_root: str | Path = ".",
    usage_log_path: str | Path = "storage/logs/token_ledger.jsonl",
) -> ALUExtractionResult:
    """Run one semantic pass, with budget accounting bound to source identity."""
    summary = validate_evidence_pack(evidence_pack)
    semantic_view = build_semantic_evidence_view(evidence_pack)
    dynamic_input = json.dumps(semantic_view, ensure_ascii=False, separators=(",", ":"))
    model_result = run_task(
        client=client,
        task="alu_extract",
        dynamic_input=dynamic_input,
        video_id=summary.source_id,
        repo_root=repo_root,
        usage_log_path=usage_log_path,
    )
    if model_result.stop_reason in TRUNCATION_STOP_REASONS:
        raise ALUExtractionError(f"MODEL_OUTPUT_TRUNCATED:{model_result.stop_reason}")
    alus = parse_alu_response(model_result.text, evidence_pack)
    return ALUExtractionResult(model_result=model_result, alus=alus)
