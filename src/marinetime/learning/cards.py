from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marinetime.pipeline.alu_extract import ALUExtractionError, validate_alu_candidates
from marinetime.pipeline.evidence_pack import validate_evidence_pack


class LearningCardError(ValueError):
    """Raised when a source-level learning card cannot be built safely."""


@dataclass(frozen=True)
class SourceLearningCard:
    source_id: str
    title: str
    creator_id: str | None
    provenance_class: str
    educational_items: tuple[dict[str, Any], ...]
    withheld_items: int
    evidence_anchors: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LearningCardError("JSON_OBJECT_REQUIRED")
    return payload


def _fmt_ms(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return "unknown"
    total = int(round(value / 1000))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _bounded_text(value: Any, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _evidence_lookup(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for collection in ("transcript_segments", "ocr_hits", "frames"):
        for item in pack.get(collection, []):
            evidence_id = item.get("evidence_id")
            if isinstance(evidence_id, str):
                lookup[evidence_id] = item
    return lookup


def _anchor_for(ref: str, item: dict[str, Any]) -> str:
    if "start_ms" in item and "end_ms" in item:
        stamp = f"{_fmt_ms(item.get('start_ms'))}–{_fmt_ms(item.get('end_ms'))}"
        text = _bounded_text(item.get("text"))
        return f"{ref} · transcript {stamp}" + (f" · {text}" if text else "")
    if "text" in item:
        stamp = _fmt_ms(item.get("timestamp_ms"))
        text = _bounded_text(item.get("text"), limit=120)
        return f"{ref} · OCR {stamp}" + (f" · {text}" if text else "")
    stamp = _fmt_ms(item.get("timestamp_ms"))
    requested = item.get("requested_timestamp_ms")
    fallback = item.get("timestamp_fallback_reason")
    note = f"{ref} · frame {stamp}"
    if fallback and requested is not None:
        note += f" · requested {_fmt_ms(requested)} · fallback={fallback}"
    return note


def _provenance_warning(provenance: str) -> str | None:
    if provenance == "creator_experience":
        return "Creator experience: useful for learning, but not automatically a standard, maker instruction, or shipboard procedure."
    if provenance == "onboard_heuristic":
        return "Onboard heuristic: treat as experience-based guidance unless verified against an authoritative source."
    if provenance == "case_specific":
        return "Case-specific source: do not generalize beyond the documented context without verification."
    if provenance == "unverified":
        return "Unverified source: use for reference only where the deterministic education gate permits it."
    return None


def build_source_learning_card(
    *,
    evidence_pack: dict[str, Any],
    alu_artifact: dict[str, Any],
    title: str | None = None,
) -> SourceLearningCard:
    summary = validate_evidence_pack(evidence_pack)
    if alu_artifact.get("schema_version") != "1.0":
        raise LearningCardError("UNSUPPORTED_ALU_ARTIFACT_SCHEMA")
    if alu_artifact.get("source_id") != summary.source_id:
        raise LearningCardError("ALU_SOURCE_MISMATCH")
    entries = alu_artifact.get("alus")
    if not isinstance(entries, list) or not entries:
        raise LearningCardError("ALU_ARTIFACT_EMPTY")

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("alu"), dict):
            raise LearningCardError(f"ALU_ENTRY_{index}_INVALID")
        decision = entry.get("decision")
        if not isinstance(decision, dict) or any(
            type(decision.get(field)) is not bool
            for field in (
                "accepted_for_reference", "accepted_for_education", "accepted_for_operational_use"
            )
        ):
            raise LearningCardError(f"ALU_ENTRY_{index}_INVALID_DECISION")
    try:
        validated = validate_alu_candidates([entry["alu"] for entry in entries], evidence_pack)
    except ALUExtractionError as exc:
        raise LearningCardError(f"ALU_ARTIFACT_INVALID:{exc}") from exc

    evidence = _evidence_lookup(evidence_pack)
    educational: list[dict[str, Any]] = []
    anchors: dict[str, tuple[str, ...]] = {}
    warnings: list[str] = []
    withheld = 0

    for index, (entry, current) in enumerate(zip(entries, validated, strict=True)):
        if not isinstance(entry, dict):
            raise LearningCardError(f"ALU_ENTRY_{index}_NOT_OBJECT")
        alu = entry.get("alu")
        decision = entry.get("decision")
        if not isinstance(alu, dict) or not isinstance(decision, dict):
            raise LearningCardError(f"ALU_ENTRY_{index}_INVALID")
        alu_id = alu.get("alu_id")
        if not isinstance(alu_id, str) or not alu_id.strip():
            raise LearningCardError(f"ALU_ENTRY_{index}_MISSING_ID")

        if not decision["accepted_for_education"] or not current.decision.accepted_for_education:
            withheld += 1
            reasons = current.decision.reasons or ("STORED_EDUCATION_WITHHELD",)
            warnings.append(f"{alu_id}: withheld: {','.join(reasons)}")
            continue

        refs = alu.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise LearningCardError(f"ALU_ENTRY_{index}_MISSING_EVIDENCE")
        unknown = [ref for ref in refs if ref not in evidence]
        if unknown:
            raise LearningCardError(
                f"ALU_ENTRY_{index}_UNKNOWN_EVIDENCE:{','.join(map(str, unknown))}"
            )

        educational.append(
            {
                "alu_id": alu_id,
                "statement": str(alu.get("statement", "")).strip(),
                "statement_type": alu.get("statement_type"),
                "support_level": alu.get("support_level"),
                "rendering_scope": alu.get("rendering_scope"),
                "evidence_refs": list(refs),
                "safety_critical": bool((alu.get("safety") or {}).get("safety_critical")),
                "numeric_claim": bool((alu.get("safety") or {}).get("numeric_claim")),
                "decision_reasons": list(current.decision.reasons),
            }
        )
        anchors[alu_id] = tuple(_anchor_for(ref, evidence[ref]) for ref in refs)

        if alu.get("support_level") != "directly_supported":
            warnings.append(
                f"{alu_id}: support level is {alu.get('support_level')}; keep the statement context-limited."
            )
        if (alu.get("safety") or {}).get("safety_critical"):
            warnings.append(
                f"{alu_id}: safety-critical content; this card is educational, not operational permission."
            )
        if (alu.get("safety") or {}).get("numeric_claim"):
            warnings.append(
                f"{alu_id}: numeric claim present; verify units, conditions, and source evidence before use."
            )

    provenance_warning = _provenance_warning(summary.provenance_class)
    if provenance_warning:
        warnings.insert(0, provenance_warning)

    context = evidence_pack.get("context") or {}
    creator_id = context.get("creator_id")
    if not isinstance(creator_id, str) or not creator_id.strip():
        creator_id = None

    resolved_title = title.strip() if isinstance(title, str) and title.strip() else summary.source_id
    return SourceLearningCard(
        source_id=summary.source_id,
        title=resolved_title,
        creator_id=creator_id,
        provenance_class=summary.provenance_class,
        educational_items=tuple(educational),
        withheld_items=withheld,
        evidence_anchors=anchors,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def card_to_json(card: SourceLearningCard) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "source_learning_card_preview",
        "source_id": card.source_id,
        "title": card.title,
        "creator_id": card.creator_id,
        "provenance_class": card.provenance_class,
        "educational_items": list(card.educational_items),
        "withheld_items": card.withheld_items,
        "evidence_anchors": {
            key: list(value) for key, value in card.evidence_anchors.items()
        },
        "warnings": list(card.warnings),
        "scope_note": (
            "Source-level preview only. It has not yet been cross-source synthesized "
            "or converted into an authoritative operational lesson."
        ),
    }


def render_card_markdown(card: SourceLearningCard) -> str:
    lines: list[str] = [
        f"# {card.title}",
        "",
        f"- **Source ID:** {card.source_id}",
        f"- **Provenance:** {card.provenance_class}",
    ]
    if card.creator_id:
        lines.append(f"- **Creator:** {card.creator_id}")
    lines.extend(
        [
            f"- **Educational ALUs:** {len(card.educational_items)}",
            f"- **Withheld by education gate:** {card.withheld_items}",
            "",
            "> Source-level preview. This is not yet a cross-source lesson and is not operational permission.",
            "",
            "## What this source can teach",
            "",
        ]
    )

    if not card.educational_items:
        lines.append("_No ALU passed the educational gate for this source._")
    else:
        for number, item in enumerate(card.educational_items, start=1):
            lines.extend(
                [
                    f"### {number}. {item['statement']}",
                    "",
                    f"- Type: {item['statement_type']}",
                    f"- Support: {item['support_level']}",
                    f"- Scope: {item['rendering_scope']}",
                ]
            )
            flags: list[str] = []
            if item["safety_critical"]:
                flags.append("safety-critical")
            if item["numeric_claim"]:
                flags.append("numeric")
            if flags:
                lines.append("- Flags: " + ", ".join(flags))
            lines.append("- Evidence:")
            for anchor in card.evidence_anchors.get(item["alu_id"], ()):
                lines.append(f"  - {anchor}")
            lines.append("")

    lines.extend(["## Limits before you trust it", ""])
    if card.warnings:
        for warning in card.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No additional source-level warnings were generated.")
    lines.extend(["", "## Active recall", ""])

    for number, item in enumerate(card.educational_items[:3], start=1):
        lines.append(
            f"{number}. Hide the section above and explain this idea in your own words: **{item['statement']}**"
        )
    if card.educational_items:
        lines.append(
            f"{min(4, len(card.educational_items[:3]) + 1)}. Which parts come directly from evidence, and which parts still need verification before operational use?"
        )
    else:
        lines.append("1. Why did this source fail to produce an education-approved learning item?")

    lines.extend(
        [
            "",
            "## Next stage",
            "",
            "This preview should later feed: Topic Packet → Instructional Designer → Lesson → Quiz/Oral Exam → Evidence QA.",
            "",
        ]
    )
    return "\n".join(lines)


def write_card_artifacts(
    card: SourceLearningCard,
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "learning_card.json"
    md_path = root / "learning_card.md"

    json_temp = json_path.with_suffix(".json.tmp")
    json_temp.write_text(
        json.dumps(card_to_json(card), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_temp.replace(json_path)

    md_temp = md_path.with_suffix(".md.tmp")
    md_temp.write_text(render_card_markdown(card), encoding="utf-8")
    md_temp.replace(md_path)
    return json_path, md_path
