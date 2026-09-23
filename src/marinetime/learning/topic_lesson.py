from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marinetime.authority.verify import VERIFICATION_METHOD, is_exact_four_stage_claim


class TopicLessonError(ValueError):
    """Raised when a topic lesson cannot be built without weakening provenance."""


@dataclass(frozen=True)
class TopicLesson:
    payload: dict[str, Any]


PASSAGE_STAGE_ORDER = ("appraisal", "planning", "execution", "monitoring")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _finding_key(finding: dict[str, Any]) -> tuple[str, str]:
    return (_norm(finding.get("source_id")), _norm(finding.get("alu_id")))


def _occurrence_key(item: dict[str, Any]) -> tuple[str, str]:
    return (_norm(item.get("source_id")), _norm(item.get("alu_id")))


def _stage_for(statement: str) -> str | None:
    lower = statement.lower()
    if "appraisal" in lower:
        return "appraisal"
    if "during planning" in lower or "berth-to-berth" in lower:
        return "planning"
    if "execution" in lower:
        return "execution"
    if "monitoring" in lower or "gps" in lower or "position-fixing" in lower:
        return "monitoring"
    return None


def _authority_refs(finding: dict[str, Any]) -> list[dict[str, str]]:
    refs = finding.get("authority_refs")
    if not isinstance(refs, list):
        return []
    cleaned: list[dict[str, str]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        authority_source_id = _norm(ref.get("authority_source_id"))
        locator = _norm(ref.get("locator"))
        support_summary = _norm(ref.get("support_summary"))
        if authority_source_id and locator and support_summary:
            cleaned.append(
                {
                    "authority_source_id": authority_source_id,
                    "locator": locator,
                    "support_summary": support_summary,
                    "organization": _norm(ref.get("organization")),
                    "title": _norm(ref.get("title")),
                    "url": _norm(ref.get("url")),
                }
            )
    return cleaned


def _topic_claim_index(topic_packet: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for claim in topic_packet.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        for occurrence in claim.get("occurrences") or []:
            if not isinstance(occurrence, dict):
                continue
            key = _occurrence_key(occurrence)
            if all(key):
                index[key] = claim
    return index


def _require_artifacts(
    topic_packet: dict[str, Any],
    authority_review: dict[str, Any],
) -> None:
    if topic_packet.get("artifact_type") != "topic_packet":
        raise TopicLessonError("TOPIC_PACKET_REQUIRED")
    if authority_review.get("artifact_type") != "authority_review":
        raise TopicLessonError("AUTHORITY_REVIEW_REQUIRED")
    topic_id = _norm(topic_packet.get("topic_id"))
    if not topic_id:
        raise TopicLessonError("TOPIC_ID_REQUIRED")
    if topic_id != _norm(authority_review.get("topic_id")):
        raise TopicLessonError("TOPIC_AUTHORITY_ID_MISMATCH")
    if topic_id != "passage-planning":
        raise TopicLessonError(f"UNSUPPORTED_TOPIC_LESSON:{topic_id}")
    if authority_review.get("verification_method") != VERIFICATION_METHOD:
        raise TopicLessonError("AUTHORITY_REVIEW_REBUILD_REQUIRED")


def build_topic_lesson(
    *,
    topic_packet: dict[str, Any],
    authority_review: dict[str, Any],
) -> TopicLesson:
    _require_artifacts(topic_packet, authority_review)
    topic_id = _norm(topic_packet["topic_id"])
    claim_index = _topic_claim_index(topic_packet)

    findings = authority_review.get("findings")
    if not isinstance(findings, list) or not findings:
        raise TopicLessonError("AUTHORITY_FINDINGS_REQUIRED")

    direct_or_partial: list[dict[str, Any]] = []
    creator_insights: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        key = _finding_key(finding)
        claim = claim_index.get(key)
        statement = _norm(finding.get("statement"))
        status = _norm(finding.get("support_status"))
        if status == "direct_support" and not is_exact_four_stage_claim(statement):
            raise TopicLessonError("DIRECT_SUPPORT_PROPOSITION_MISMATCH")
        base = {
            "source_id": key[0],
            "alu_id": key[1],
            "topic_claim_id": _norm((claim or {}).get("topic_claim_id")),
            "source_statement": statement,
            "support_status": status,
            "rationale": _norm(finding.get("rationale")),
            "authority_refs": _authority_refs(finding),
        }

        if status in {"direct_support", "partial_support"}:
            direct_or_partial.append(base)
        elif status == "not_applicable":
            creator_insights.append(base)
        else:
            unresolved.append(base)

    stages: dict[str, dict[str, Any]] = {
        stage: {
            "stage": stage,
            "title": stage.title(),
            "official_core": [],
            "creator_layer": [],
        }
        for stage in PASSAGE_STAGE_ORDER
    }
    framework: list[dict[str, Any]] = []

    for item in direct_or_partial:
        statement = item["source_statement"]
        if "four stages" in statement.lower():
            framework.append(item)
            continue
        stage = _stage_for(statement)
        if stage is None:
            continue
        refs = item["authority_refs"]
        official_core = {
            "support_status": item["support_status"],
            "official_support": [
                {
                    "authority_source_id": ref["authority_source_id"],
                    "locator": ref["locator"],
                    "support_summary": ref["support_summary"],
                }
                for ref in refs
            ],
            "source_trace": {
                "source_id": item["source_id"],
                "alu_id": item["alu_id"],
                "topic_claim_id": item["topic_claim_id"],
            },
        }
        stages[stage]["official_core"].append(official_core)

        if item["support_status"] == "partial_support":
            stages[stage]["creator_layer"].append(
                {
                    "statement": statement,
                    "why_separate": item["rationale"],
                    "source_trace": official_core["source_trace"],
                }
            )

    if not framework:
        raise TopicLessonError("PASSAGE_FRAMEWORK_AUTHORITY_SUPPORT_MISSING")

    framework_refs: list[dict[str, str]] = []
    for item in framework:
        framework_refs.extend(
            {
                "authority_source_id": ref["authority_source_id"],
                "locator": ref["locator"],
                "support_summary": ref["support_summary"],
            }
            for ref in item["authority_refs"]
        )

    mental_model = [
        _norm(item)
        for item in topic_packet.get("mental_model") or []
        if _norm(item)
    ]

    learning_objectives = [
        {
            "objective_id": "LO-01",
            "text": "List the four passage-planning stages in the correct order.",
            "assessment_ids": ["Q-01", "ORAL-01"],
        },
        {
            "objective_id": "LO-02",
            "text": "Explain the purpose and source-supported work associated with appraisal, planning, execution, and monitoring.",
            "assessment_ids": ["Q-02", "Q-03", "Q-04", "Q-05", "ORAL-01"],
        },
        {
            "objective_id": "LO-03",
            "text": "Distinguish an officially supported principle from creator-specific wording that remains only partially supported.",
            "assessment_ids": ["Q-06"],
        },
        {
            "objective_id": "LO-04",
            "text": "Give a 60–90 second interview answer that explains the four stages rather than only reciting their names.",
            "assessment_ids": ["ORAL-01"],
        },
    ]

    q_map = {
        "appraisal": (
            "During appraisal, what information or preparation does the official support in this lesson require you to consider?",
            "Use the Appraisal official-core support summaries; do not add creator-only details unless you label them separately.",
        ),
        "planning": (
            "What does the official support in this lesson require during planning before the voyage is executed?",
            "Use the Planning official-core support summaries and keep partially supported creator wording separate.",
        ),
        "execution": (
            "What does the official support in this lesson say about executing the finalized passage plan?",
            "Use the Execution official-core support summary.",
        ),
        "monitoring": (
            "How should progress and position-fixing be treated during monitoring according to the official support collected here?",
            "Use the Monitoring official-core support summaries; do not turn 'never GPS alone' into an official quote.",
        ),
    }

    retrieval: list[dict[str, Any]] = [
        {
            "assessment_id": "Q-01",
            "type": "retrieval",
            "prompt": "Without looking back, list the four passage-planning stages in order.",
            "answer_key": "Appraisal → Planning → Execution → Monitoring.",
            "grounding": {
                "framework_authority_refs": framework_refs,
            },
        }
    ]

    assessment_number = 2
    for stage in PASSAGE_STAGE_ORDER:
        block = stages[stage]
        if not block["official_core"]:
            continue
        prompt, answer_instruction = q_map[stage]
        retrieval.append(
            {
                "assessment_id": f"Q-{assessment_number:02d}",
                "type": "retrieval",
                "stage": stage,
                "prompt": prompt,
                "answer_key_instruction": answer_instruction,
                "grounding": {
                    "official_core": block["official_core"],
                    "creator_layer": block["creator_layer"],
                },
            }
        )
        assessment_number += 1

    retrieval.append(
        {
            "assessment_id": "Q-06",
            "type": "boundary_check",
            "prompt": (
                "Why should the phrase 'never rely on GPS alone' remain creator wording "
                "instead of being presented as a direct IMO quotation?"
            ),
            "answer_key": (
                "The authority review supports redundancy through primary and secondary "
                "position-fixing options, but it does not reproduce that exact absolute wording."
            ),
            "grounding": {
                "matching_findings": [
                    item
                    for item in direct_or_partial
                    if "gps" in item["source_statement"].lower()
                    or "position-fixing method" in item["source_statement"].lower()
                ]
            },
        }
    )

    interview_tip = creator_insights[0] if creator_insights else None
    oral_exam = {
        "assessment_id": "ORAL-01",
        "question": "How do you make a passage plan?",
        "time_target_seconds": [60, 90],
        "answer_structure": [
            "Name the four stages in order.",
            "Explain appraisal using the source-supported information-gathering principle.",
            "Explain planning using the officially supported berth-to-berth planning principles.",
            "Explain execution of the finalized/approved plan.",
            "Explain continuous monitoring and position-fixing redundancy.",
        ],
        "creator_interview_tip": (
            interview_tip["source_statement"] if interview_tip is not None else None
        ),
        "rubric": [
            {
                "criterion": "stage_order",
                "pass_condition": "Names appraisal, planning, execution, monitoring in order.",
            },
            {
                "criterion": "stage_explanation",
                "pass_condition": "Explains what happens in each stage instead of only listing labels.",
            },
            {
                "criterion": "authority_boundary",
                "pass_condition": "Does not present partially supported creator wording as an official quotation or procedure.",
            },
            {
                "criterion": "source_discipline",
                "pass_condition": "Does not add unsupported facts beyond the lesson evidence.",
            },
        ],
    }

    payload = {
        "schema_version": "1.0",
        "artifact_type": "topic_lesson",
        "topic_id": topic_id,
        "title": "Passage Planning — Learn, Explain, and Answer in an Interview",
        "source_count": int(topic_packet.get("source_count") or 0),
        "source_ids": list(topic_packet.get("source_ids") or []),
        "learning_objectives": learning_objectives,
        "mental_model": mental_model,
        "framework": {
            "stage_order": list(PASSAGE_STAGE_ORDER),
            "authority_refs": framework_refs,
        },
        "stage_lessons": [stages[stage] for stage in PASSAGE_STAGE_ORDER],
        "creator_insights": creator_insights,
        "unresolved_items": unresolved,
        "assessment": {
            "retrieval_practice": retrieval,
            "oral_exam": oral_exam,
        },
        "trust_boundary": {
            "authority_review_method": authority_review.get("verification_method"),
            "direct_support_count": int(
                (authority_review.get("counts") or {}).get("direct_support", 0)
            ),
            "partial_support_count": int(
                (authority_review.get("counts") or {}).get("partial_support", 0)
            ),
            "not_applicable_count": int(
                (authority_review.get("counts") or {}).get("not_applicable", 0)
            ),
            "unresolved_count": int(
                (authority_review.get("counts") or {}).get("unresolved", 0)
            ),
            "operational_permission": False,
            "note": (
                "This topic lesson may teach officially supported principles while preserving "
                "creator-specific wording separately. It does not grant operational permission."
            ),
        },
    }
    return TopicLesson(payload=payload)


def validate_topic_lesson(lesson: TopicLesson) -> dict[str, Any]:
    payload = lesson.payload
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "passed": passed, "detail": detail})

    check(
        "TOPIC_ID",
        payload.get("topic_id") == "passage-planning",
        "Topic lesson must remain bound to passage-planning.",
    )
    check(
        "NO_OPERATIONAL_PERMISSION",
        (payload.get("trust_boundary") or {}).get("operational_permission") is False,
        "Topic lesson must never grant operational permission.",
    )

    stage_lessons = payload.get("stage_lessons") or []
    check(
        "FOUR_STAGE_STRUCTURE",
        [item.get("stage") for item in stage_lessons] == list(PASSAGE_STAGE_ORDER),
        "Lesson must preserve Appraisal → Planning → Execution → Monitoring.",
    )

    authority_missing = []
    for stage in stage_lessons:
        for core in stage.get("official_core") or []:
            if not core.get("official_support"):
                authority_missing.append(stage.get("stage"))
            if core.get("support_status") not in {"direct_support", "partial_support"}:
                authority_missing.append(stage.get("stage"))
    check(
        "OFFICIAL_CORE_HAS_AUTHORITY",
        not authority_missing,
        "Every official-core block must have direct/partial authority support.",
    )

    creator_promoted = []
    for stage in stage_lessons:
        for creator in stage.get("creator_layer") or []:
            if not creator.get("why_separate"):
                creator_promoted.append(stage.get("stage"))
    check(
        "CREATOR_LAYER_STAYS_SEPARATE",
        not creator_promoted,
        "Partially supported creator wording must include an explicit separation reason.",
    )

    assessment = payload.get("assessment") or {}
    retrieval = assessment.get("retrieval_practice") or []
    check(
        "ASSESSMENT_COUNT",
        len(retrieval) >= 5,
        "Topic lesson should contain at least five retrieval/boundary checks.",
    )
    check(
        "ORAL_RUBRIC",
        len((assessment.get("oral_exam") or {}).get("rubric") or []) >= 4,
        "Oral assessment requires an explicit multi-criterion rubric.",
    )

    unresolved = payload.get("unresolved_items") or []
    unresolved_in_core = False
    unresolved_keys = {
        (_norm(item.get("source_id")), _norm(item.get("alu_id")))
        for item in unresolved
    }
    for stage in stage_lessons:
        for core in stage.get("official_core") or []:
            trace = core.get("source_trace") or {}
            if (_norm(trace.get("source_id")), _norm(trace.get("alu_id"))) in unresolved_keys:
                unresolved_in_core = True
    check(
        "UNRESOLVED_WITHHELD_FROM_OFFICIAL_CORE",
        not unresolved_in_core,
        "Unresolved authority findings must not appear as official core.",
    )

    passed = all(item["passed"] for item in checks)
    return {
        "schema_version": "1.0",
        "artifact_type": "topic_lesson_qa",
        "topic_id": payload.get("topic_id"),
        "passed": passed,
        "checks": checks,
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for item in checks if item["passed"]),
            "failed": sum(1 for item in checks if not item["passed"]),
        },
    }


def render_topic_lesson(lesson: TopicLesson) -> str:
    p = lesson.payload
    lines: list[str] = [
        f"# {p['title']}",
        "",
        f"- **Sources combined:** {p['source_count']}",
        "- **Operational permission:** no",
        "",
        "> Officially supported principles and creator-specific wording are shown separately.",
        "",
        "## Learning goals",
        "",
    ]
    for item in p["learning_objectives"]:
        lines.append(f"- **{item['objective_id']}:** {item['text']}")

    lines.extend(["", "## Mental model", ""])
    for item in p["mental_model"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Official framework", ""])
    lines.append("**Appraisal → Planning → Execution → Monitoring**")
    for ref in p["framework"]["authority_refs"]:
        lines.append(
            f"- {ref['authority_source_id']} · {ref['locator']} — {ref['support_summary']}"
        )

    lines.extend(["", "## Learn each stage", ""])
    for block in p["stage_lessons"]:
        lines.extend([f"### {block['title']}", ""])
        for core in block["official_core"]:
            lines.append(f"- **Authority status:** {core['support_status']}")
            for ref in core["official_support"]:
                lines.append(
                    f"  - {ref['authority_source_id']} · {ref['locator']} — "
                    f"{ref['support_summary']}"
                )
        if block["creator_layer"]:
            lines.extend(["", "**Creator layer — keep separate:**"])
            for creator in block["creator_layer"]:
                lines.append(f"- {creator['statement']}")
                lines.append(f"  - Why separate: {creator['why_separate']}")
        lines.append("")

    if p["creator_insights"]:
        lines.extend(["## Creator insight for the interview", ""])
        for item in p["creator_insights"]:
            lines.append(f"- {item['source_statement']}")
            lines.append(f"  - Authority classification: {item['support_status']}")
            lines.append(f"  - Why: {item['rationale']}")
        lines.append("")

    lines.extend(["## Retrieval practice", ""])
    for item in p["assessment"]["retrieval_practice"]:
        lines.append(f"### {item['assessment_id']}")
        lines.append("")
        lines.append(item["prompt"])
        lines.append("")

    oral = p["assessment"]["oral_exam"]
    lines.extend(
        [
            "## Oral interview practice",
            "",
            f"**Question:** {oral['question']}",
            "",
            f"**Target:** {oral['time_target_seconds'][0]}–{oral['time_target_seconds'][1]} seconds",
            "",
            "Use this structure:",
        ]
    )
    for step in oral["answer_structure"]:
        lines.append(f"- {step}")
    if oral.get("creator_interview_tip"):
        lines.extend(["", f"**Creator interview tip:** {oral['creator_interview_tip']}"])

    lines.extend(["", "### Oral self-check", ""])
    for item in oral["rubric"]:
        lines.append(f"- **{item['criterion']}:** {item['pass_condition']}")

    lines.extend(["", "## Trust boundary", ""])
    trust = p["trust_boundary"]
    lines.extend(
        [
            f"- Direct official support: {trust['direct_support_count']}",
            f"- Partial official support: {trust['partial_support_count']}",
            f"- Creator/interview advice not requiring navigation authority check: {trust['not_applicable_count']}",
            f"- Unresolved authority items: {trust['unresolved_count']}",
            f"- {trust['note']}",
            "",
        ]
    )
    return "\n".join(lines)


def render_qa_report(report: dict[str, Any]) -> str:
    lines = [
        "# Topic Lesson — QA Report",
        "",
        f"- **Topic:** {report.get('topic_id')}",
        f"- **Passed:** {'yes' if report.get('passed') else 'no'}",
        f"- **Checks:** {report.get('summary', {}).get('checks', 0)}",
        f"- **Failed:** {report.get('summary', {}).get('failed', 0)}",
        "",
        "## Checks",
        "",
    ]
    for item in report.get("checks") or []:
        mark = "PASS" if item.get("passed") else "FAIL"
        lines.append(f"- **{mark} · {item.get('check_id')}:** {item.get('detail')}")
    lines.append("")
    return "\n".join(lines)


def write_topic_lesson_artifacts(
    lesson: TopicLesson,
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    lesson_json = root / "topic_lesson.json"
    lesson_md = root / "topic_lesson.md"
    qa_json = root / "topic_lesson_qa.json"
    qa_md = root / "topic_lesson_qa.md"

    report = validate_topic_lesson(lesson)
    if not report["passed"]:
        failed = [
            item["check_id"]
            for item in report["checks"]
            if not item["passed"]
        ]
        raise TopicLessonError("TOPIC_LESSON_QA_FAILED:" + ",".join(failed))

    artifacts = (
        (lesson_json, json.dumps(lesson.payload, ensure_ascii=False, indent=2)),
        (lesson_md, render_topic_lesson(lesson)),
        (qa_json, json.dumps(report, ensure_ascii=False, indent=2)),
        (qa_md, render_qa_report(report)),
    )
    for path, text in artifacts:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)

    return lesson_json, lesson_md, qa_json, qa_md
