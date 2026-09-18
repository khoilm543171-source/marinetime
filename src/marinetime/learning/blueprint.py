from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cards import SourceLearningCard


class LessonBlueprintError(ValueError):
    """Raised when a learner-facing lesson blueprint cannot be built safely."""


@dataclass(frozen=True)
class LearningObjective:
    objective_id: str
    text: str
    alu_ids: tuple[str, ...]


@dataclass(frozen=True)
class LessonBlueprint:
    schema_version: str
    source_id: str
    original_title: str
    display_title: str
    provenance_class: str
    learning_objectives: tuple[LearningObjective, ...]
    key_items: tuple[dict[str, Any], ...]
    quick_check: tuple[dict[str, str], ...]
    oral_exam_prompt: str
    authoritative_verification_required: bool
    warnings: tuple[str, ...]


_TIKTOK_SUFFIX_PATTERNS = (
    re.compile(r"\s+do\s+.+?\s+tạo với bản nhạc\s+.*$", re.IGNORECASE),
    re.compile(r"\s+created with\s+.+?\s+sound\s+.*$", re.IGNORECASE),
)


def clean_display_title(title: str, *, limit: int = 110) -> str:
    """Remove common platform boilerplate while preserving the original elsewhere."""
    value = " ".join(title.split()).strip(" -")
    for pattern in _TIKTOK_SUFFIX_PATTERNS:
        value = pattern.sub("", value).strip(" -")
    value = re.sub(r"\s{2,}", " ", value)
    if len(value) > limit:
        value = value[: max(0, limit - 1)].rstrip(" -–—,:;") + "…"
    return value or title.strip()


def _objective_text(statement: str, statement_type: str | None) -> str:
    lowered = statement.strip()
    if statement_type == "procedure":
        return f"Describe the procedure represented by this source: {lowered}"
    if statement_type == "recommendation":
        return f"Explain the recommendation and the reasoning represented in the source: {lowered}"
    if statement_type == "question":
        return f"Answer the source question using only supported evidence: {lowered}"
    return f"Explain in your own words: {lowered}"


def _question_for(item: dict[str, Any], number: int) -> dict[str, str]:
    statement = str(item.get("statement", "")).strip()
    statement_type = item.get("statement_type")
    if statement_type == "recommendation":
        prompt = f"What does the creator recommend in key idea {number}, and what problem is it intended to address?"
    elif statement_type == "procedure":
        prompt = f"Without looking back, describe the procedure or sequence in key idea {number}."
    elif statement_type == "question":
        prompt = f"Answer key idea {number} from the evidence available in this source."
    elif statement_type == "inferred_relationship":
        prompt = f"Explain the relationship described in key idea {number}. What evidence supports it?"
    else:
        prompt = f"Explain key idea {number} in your own words without reading the statement."
    return {
        "question_id": f"Q-{number:02d}",
        "prompt": prompt,
        "answer_anchor": statement,
        "alu_id": str(item.get("alu_id", "")),
    }


def build_lesson_blueprint(card: SourceLearningCard) -> LessonBlueprint:
    if not card.educational_items:
        raise LessonBlueprintError("NO_EDUCATIONAL_ITEMS")

    key_items = tuple(card.educational_items[:8])
    objectives = tuple(
        LearningObjective(
            objective_id=f"LO-{index:02d}",
            text=_objective_text(
                str(item.get("statement", "")),
                item.get("statement_type"),
            ),
            alu_ids=(str(item.get("alu_id")),),
        )
        for index, item in enumerate(key_items[:4], start=1)
    )
    quick_check = tuple(
        _question_for(item, index)
        for index, item in enumerate(key_items[:5], start=1)
    )

    checklist = "; ".join(
        str(item.get("statement", "")).strip()
        for item in key_items[:3]
        if str(item.get("statement", "")).strip()
    )
    oral_exam_prompt = (
        f"Explain '{clean_display_title(card.title)}' in 60–90 seconds without reading notes. "
        f"Your answer should cover these evidence-backed ideas: {checklist}"
    )

    authoritative_required = (
        card.provenance_class not in {"standard", "maker_manual", "regulatory"}
        or any(bool(item.get("safety_critical")) for item in key_items)
        or any(bool(item.get("numeric_claim")) for item in key_items)
    )

    return LessonBlueprint(
        schema_version="1.0",
        source_id=card.source_id,
        original_title=card.title,
        display_title=clean_display_title(card.title),
        provenance_class=card.provenance_class,
        learning_objectives=objectives,
        key_items=key_items,
        quick_check=quick_check,
        oral_exam_prompt=oral_exam_prompt,
        authoritative_verification_required=authoritative_required,
        warnings=card.warnings,
    )


def blueprint_to_json(blueprint: LessonBlueprint) -> dict[str, Any]:
    return {
        "schema_version": blueprint.schema_version,
        "artifact_type": "source_lesson_blueprint_preview",
        "source_id": blueprint.source_id,
        "original_title": blueprint.original_title,
        "display_title": blueprint.display_title,
        "provenance_class": blueprint.provenance_class,
        "learning_objectives": [
            {
                "objective_id": item.objective_id,
                "text": item.text,
                "alu_ids": list(item.alu_ids),
            }
            for item in blueprint.learning_objectives
        ],
        "key_items": list(blueprint.key_items),
        "quick_check": list(blueprint.quick_check),
        "oral_exam_prompt": blueprint.oral_exam_prompt,
        "authoritative_verification_required": blueprint.authoritative_verification_required,
        "warnings": list(blueprint.warnings),
        "scope_note": (
            "Single-source instructional preview. No cross-source synthesis or "
            "authoritative verification has been performed."
        ),
    }


def render_lesson_preview(
    blueprint: LessonBlueprint,
    *,
    evidence_anchors: dict[str, tuple[str, ...]],
) -> str:
    lines: list[str] = [
        f"# {blueprint.display_title}",
        "",
        "> Lesson preview built only from education-approved ALUs. "
        "It is not operational permission.",
        "",
        "## Learning goal",
        "",
        "After this preview, you should be able to:",
    ]
    for objective in blueprint.learning_objectives:
        lines.append(f"- **{objective.objective_id}:** {objective.text}")

    lines.extend(["", "## Big picture", ""])
    for index, item in enumerate(blueprint.key_items, start=1):
        lines.append(f"{index}. {item['statement']}")

    lines.extend(["", "## Key ideas", ""])
    for index, item in enumerate(blueprint.key_items, start=1):
        lines.extend(
            [
                f"### {index}. {item['statement']}",
                "",
                f"- **Support:** {item.get('support_level')}",
                f"- **Type:** {item.get('statement_type')}",
            ]
        )
        flags: list[str] = []
        if item.get("safety_critical"):
            flags.append("safety-critical")
        if item.get("numeric_claim"):
            flags.append("numeric")
        if flags:
            lines.append("- **Flags:** " + ", ".join(flags))

        lines.extend(
            [
                "",
                "<details>",
                "<summary>Show evidence</summary>",
                "",
            ]
        )
        anchors = evidence_anchors.get(str(item.get("alu_id")), ())
        if anchors:
            for anchor in anchors:
                lines.append(f"- {anchor}")
        else:
            lines.append("- No evidence anchor available.")
        lines.extend(["", "</details>", ""])

    lines.extend(
        [
            "## Oral interview practice",
            "",
            blueprint.oral_exam_prompt,
            "",
            "### Self-check",
            "",
            "- Did I explain the idea instead of only naming keywords?",
            "- Did I avoid adding facts that are not in the evidence?",
            "- Did I distinguish creator experience from authoritative procedure?",
            "",
            "## Quick check",
            "",
        ]
    )
    for item in blueprint.quick_check:
        lines.append(f"{item['question_id']}. {item['prompt']}")

    lines.extend(["", "## Trust boundary", ""])
    if blueprint.authoritative_verification_required:
        lines.append(
            "- **Authoritative verification required:** yes. This source-level lesson "
            "must not be promoted to operational guidance until higher-authority evidence "
            "supports the relevant claims."
        )
    else:
        lines.append(
            "- **Authoritative verification required:** no additional source-class promotion "
            "is implied by this preview; existing validation still applies."
        )
    for warning in blueprint.warnings:
        lines.append(f"- {warning}")

    lines.extend(
        [
            "",
            "## Next stage",
            "",
            "Cross-source Topic Packet → Instructional Designer → authoritative verification "
            "where needed → assessment QA.",
            "",
        ]
    )
    return "\n".join(lines)


def write_lesson_preview(
    blueprint: LessonBlueprint,
    *,
    evidence_anchors: dict[str, tuple[str, ...]],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "lesson_blueprint.json"
    md_path = root / "lesson_preview.md"

    json_temp = json_path.with_suffix(".json.tmp")
    json_temp.write_text(
        json.dumps(blueprint_to_json(blueprint), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_temp.replace(json_path)

    md_temp = md_path.with_suffix(".md.tmp")
    md_temp.write_text(
        render_lesson_preview(blueprint, evidence_anchors=evidence_anchors),
        encoding="utf-8",
    )
    md_temp.replace(md_path)
    return json_path, md_path
