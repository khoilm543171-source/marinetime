from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marinetime.config import ClaudeSettings
from marinetime.llm.client import ClaudeAPIError, ClaudeClient
from marinetime.llm.prompt_registry import load_prompt
from marinetime.llm.token_guard import (
    TokenBudgetBlocked,
    TokenBudgetMode,
    TokenLimits,
    assert_token_budget,
    conservative_text_token_estimate,
    get_token_budget_status,
)
from marinetime.llm.usage import load_usage_totals
from marinetime.pipeline.alu_extract import (
    ALUExtractionError,
    ALUExtractionResult,
    build_bounded_semantic_evidence_view,
    extract_alus,
)
from marinetime.pipeline.evidence_pack import EvidencePackError, validate_evidence_pack


@dataclass(frozen=True)
class AutoALUCandidate:
    source_id: str
    evidence_path: Path
    output_path: Path
    created_order: tuple[float, str]


@dataclass(frozen=True)
class AutoALURunResult:
    eligible: int
    selected: int
    attempted: int
    succeeded: int
    failed: int
    waiting_after: int
    triggered: bool
    paused_reason: str | None = None
    skipped: int = 0


GLOBAL_BUDGET_PAUSE_REASONS = {
    "MARINETIME_DAILY_HARD_STOP",
    "MARINETIME_CLOSEOUT_MODE",
    "MARINETIME_CLOSEOUT_WOULD_BE_REACHED",
    "MAX_DAILY_TOKENS",
    "MAX_OUTPUT_TOKENS_PER_CALL",
}


def is_global_budget_pause(reason: str) -> bool:
    return reason in GLOBAL_BUDGET_PAUSE_REASONS


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return payload


def _valid_alu_artifact(path: Path, source_id: str) -> bool:
    if not path.is_file():
        return False
    try:
        payload = _load_json_object(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        payload.get("source_id") == source_id
        and isinstance(payload.get("alus"), list)
        and bool(payload["alus"])
    )


def discover_auto_alu_candidates(evidence_root: str | Path) -> list[AutoALUCandidate]:
    """Find validated EvidencePacks that do not yet have a completed ALU artifact."""
    root = Path(evidence_root)
    if not root.exists():
        return []

    candidates: list[AutoALUCandidate] = []
    for evidence_path in root.glob("*/evidence_pack.json"):
        if not evidence_path.is_file():
            continue
        try:
            pack = _load_json_object(evidence_path)
            summary = validate_evidence_pack(pack)
        except (OSError, ValueError, json.JSONDecodeError, EvidencePackError):
            continue

        output_path = evidence_path.parent / "alus.json"
        if _valid_alu_artifact(output_path, summary.source_id):
            continue

        try:
            modified = evidence_path.stat().st_mtime
        except OSError:
            modified = 0.0
        candidates.append(
            AutoALUCandidate(
                source_id=summary.source_id,
                evidence_path=evidence_path,
                output_path=output_path,
                created_order=(modified, summary.source_id),
            )
        )

    return sorted(candidates, key=lambda item: item.created_order)


def select_threshold_batch(
    candidates: list[AutoALUCandidate],
    *,
    threshold: int = 20,
) -> list[AutoALUCandidate]:
    """Select complete threshold-sized groups, leaving a partial group waiting."""
    if threshold <= 0:
        raise ValueError("AUTO_ALU_THRESHOLD_MUST_BE_POSITIVE")
    complete_count = (len(candidates) // threshold) * threshold
    return candidates[:complete_count]


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


def _preflight_candidate(
    *,
    evidence_pack: dict[str, Any],
    source_id: str,
    repo_root: Path,
    usage_log_path: Path,
    limits: TokenLimits,
) -> tuple[int, int, int, dict[str, Any], bool]:
    spec, system_prompt = load_prompt("alu_extract", repo_root=repo_root)
    max_dynamic_chars = max(
        1,
        (limits.max_input_tokens_per_call * 2) - len(system_prompt) - 2,
    )
    semantic_view, compacted = build_bounded_semantic_evidence_view(
        evidence_pack,
        max_dynamic_chars=max_dynamic_chars,
    )
    dynamic_input = json.dumps(semantic_view, ensure_ascii=False, separators=(",", ":"))
    estimated_input = conservative_text_token_estimate(system_prompt + "\n" + dynamic_input)
    totals = load_usage_totals(usage_log_path, video_id=source_id)
    projected = estimated_input + spec.default_max_output_tokens

    budget = get_token_budget_status(
        current_daily_tokens=totals.daily_tokens,
        limits=limits,
    )
    if budget.mode is TokenBudgetMode.HARD_STOP:
        raise TokenBudgetBlocked("MARINETIME_DAILY_HARD_STOP")
    if budget.mode is TokenBudgetMode.CLOSEOUT:
        raise TokenBudgetBlocked("MARINETIME_CLOSEOUT_MODE")
    if totals.daily_tokens + projected >= budget.closeout_daily_tokens:
        raise TokenBudgetBlocked("MARINETIME_CLOSEOUT_WOULD_BE_REACHED")

    assert_token_budget(
        estimated_input_tokens=estimated_input,
        requested_output_tokens=spec.default_max_output_tokens,
        current_video_tokens=totals.video_tokens,
        current_daily_tokens=totals.daily_tokens,
        limits=limits,
    )
    return (
        estimated_input,
        spec.default_max_output_tokens,
        totals.daily_tokens,
        semantic_view,
        compacted,
    )


def run_auto_alu_threshold(
    *,
    evidence_root: str | Path,
    repo_root: str | Path,
    usage_log_path: str | Path,
    threshold: int = 20,
    limits: TokenLimits = TokenLimits(),
    drain: bool = False,
) -> AutoALURunResult:
    """Automatically extract ALUs once a full threshold-sized backlog exists.

    This function is the only provider-backed part of the local worker flow. It
    prints a notice before the first provider attempt, processes only complete
    threshold-sized groups, skips already completed ALU artifacts, and stops
    before Marinetime's daily closeout boundary.
    """
    root = Path(evidence_root)
    repo = Path(repo_root)
    ledger = Path(usage_log_path)
    candidates = discover_auto_alu_candidates(root)
    selected = list(candidates) if drain else select_threshold_batch(candidates, threshold=threshold)

    if not selected:
        print("OPUS_AUTO_WAITING")
        print(f"eligible_without_alus={len(candidates)}")
        print(f"threshold={threshold}")
        print(f"needed={max(0, threshold - len(candidates))}")
        return AutoALURunResult(
            eligible=len(candidates),
            selected=0,
            attempted=0,
            succeeded=0,
            failed=0,
            waiting_after=len(candidates),
            triggered=False,
        )

    print("OPUS_AUTO_TRIGGERED")
    print(f"eligible_without_alus={len(candidates)}")
    print(f"threshold={threshold}")
    print(f"selected={len(selected)}")
    print("OPUS_NOTICE provider_quota_will_be_used=true")
    print(
        "OPUS_NOTICE mode="
        + ("manual_backlog_drain" if drain else "automatic_threshold_batch")
    )

    attempted = 0
    succeeded = 0
    failed = 0
    skipped = 0
    paused_reason: str | None = None

    try:
        settings = ClaudeSettings.from_env()
    except ValueError as exc:
        reason = f"SETTINGS:{exc}"
        print(f"OPUS_AUTO_PAUSED reason={reason}")
        return AutoALURunResult(
            eligible=len(candidates),
            selected=len(selected),
            attempted=0,
            succeeded=0,
            failed=0,
            waiting_after=len(candidates),
            triggered=True,
            paused_reason=reason,
        )

    with ClaudeClient(settings) as client:
        for index, candidate in enumerate(selected, start=1):
            try:
                evidence_pack = _load_json_object(candidate.evidence_path)
                validate_evidence_pack(evidence_pack)
                (
                    estimated_input,
                    requested_output,
                    daily_before,
                    semantic_view,
                    compacted,
                ) = _preflight_candidate(
                    evidence_pack=evidence_pack,
                    source_id=candidate.source_id,
                    repo_root=repo,
                    usage_log_path=ledger,
                    limits=limits,
                )
            except TokenBudgetBlocked as exc:
                reason = str(exc)
                if is_global_budget_pause(reason):
                    paused_reason = reason
                    print(
                        f"OPUS_AUTO_PAUSED source_id={candidate.source_id} reason={paused_reason}"
                    )
                    break
                skipped += 1
                print(
                    f"OPUS_AUTO_SKIPPED source_id={candidate.source_id} reason={reason}"
                )
                continue
            except (
                OSError,
                ValueError,
                json.JSONDecodeError,
                EvidencePackError,
                ALUExtractionError,
            ) as exc:
                failed += 1
                print(
                    f"OPUS_AUTO_FAILED source_id={candidate.source_id} "
                    f"error={type(exc).__name__}:{' '.join(str(exc).split())[:300]}"
                )
                continue

            print(
                f"OPUS_AUTO_START index={index}/{len(selected)} source_id={candidate.source_id} "
                f"estimated_input_tokens={estimated_input} requested_output_tokens={requested_output} "
                f"daily_tokens_before={daily_before} compacted={str(compacted).lower()}"
            )
            attempted += 1
            try:
                result = extract_alus(
                    client=client,
                    evidence_pack=evidence_pack,
                    repo_root=repo,
                    usage_log_path=ledger,
                    semantic_view=semantic_view,
                )
                artifact = _build_output(result, evidence_pack)
                _write_json_atomic(candidate.output_path, artifact)
            except TokenBudgetBlocked as exc:
                reason = str(exc)
                if is_global_budget_pause(reason):
                    paused_reason = reason
                    print(
                        f"OPUS_AUTO_PAUSED source_id={candidate.source_id} reason={paused_reason}"
                    )
                    break
                skipped += 1
                print(
                    f"OPUS_AUTO_SKIPPED source_id={candidate.source_id} reason={reason}"
                )
                continue
            except (
                ValueError,
                TypeError,
                ClaudeAPIError,
                EvidencePackError,
                ALUExtractionError,
            ) as exc:
                failed += 1
                print(
                    f"OPUS_AUTO_FAILED source_id={candidate.source_id} "
                    f"error={type(exc).__name__}:{' '.join(str(exc).split())[:300]}"
                )
                continue

            succeeded += 1
            print(
                f"OPUS_AUTO_OK source_id={candidate.source_id} "
                f"alu_count={len(result.alus)} input_tokens={result.model_result.input_tokens} "
                f"output_tokens={result.model_result.output_tokens} artifact={candidate.output_path}"
            )

    remaining = len(discover_auto_alu_candidates(root))
    print("OPUS_AUTO_SUMMARY")
    print(f"attempted={attempted}")
    print(f"succeeded={succeeded}")
    print(f"failed={failed}")
    print(f"skipped={skipped}")
    print(f"waiting_after={remaining}")
    if paused_reason:
        print(f"paused_reason={paused_reason}")

    return AutoALURunResult(
        eligible=len(candidates),
        selected=len(selected),
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        waiting_after=remaining,
        triggered=True,
        paused_reason=paused_reason,
        skipped=skipped,
    )
