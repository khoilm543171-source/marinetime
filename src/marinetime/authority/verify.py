from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


class AuthorityVerificationError(ValueError):
    """Raised when an authority-support packet cannot be built safely."""


@dataclass(frozen=True)
class AuthoritySource:
    source_id: str
    organization: str
    title: str
    source_type: str
    url: str
    published_or_adopted: str
    notes: str


@dataclass(frozen=True)
class AuthorityFinding:
    alu_id: str
    source_id: str
    statement: str
    support_status: str
    authority_refs: tuple[dict[str, str], ...]
    rationale: str


IMO_A893 = AuthoritySource(
    source_id="IMO-A893-21",
    organization="International Maritime Organization",
    title="Resolution A.893(21) — Guidelines for voyage planning",
    source_type="primary_imo_resolution",
    url=(
        "https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/"
        "IndexofIMOResolutions/AssemblyDocuments/A.893(21).pdf"
    ),
    published_or_adopted="1999-11-25",
    notes=(
        "Primary IMO voyage-planning guidance. Authority support here does not "
        "automatically convert a creator ALU into operational permission."
    ),
)

MCA_OOW_03483 = AuthoritySource(
    source_id="MCA-OOW-034-83",
    organization="UK Maritime and Coastguard Agency",
    title="Officer of the Watch Unlimited — Navigation Syllabus (034-83)",
    source_type="national_maritime_training_syllabus",
    url=(
        "https://assets.publishing.service.gov.uk/media/678e2b6eea48a571517acf4f/"
        "034-83_OOW_Navigation_Sylabus__Version_-_June_2024___002_.pdf"
    ),
    published_or_adopted="2024-06",
    notes=(
        "Official national examination syllabus. Useful as corroborating training "
        "context, but lower authority than the IMO resolution for global guidance."
    ),
)

PASSAGE_PLANNING_AUTHORITY_SOURCES = (IMO_A893, MCA_OOW_03483)

SUPPORT_DIRECT = "direct_support"
SUPPORT_PARTIAL = "partial_support"
SUPPORT_NOT_APPLICABLE = "not_applicable"
SUPPORT_UNRESOLVED = "unresolved"


def _contains(statement: str, *needles: str) -> bool:
    lower = statement.lower()
    return all(needle.lower() in lower for needle in needles)


def _ref(
    source: AuthoritySource,
    *,
    locator: str,
    support_summary: str,
) -> dict[str, str]:
    return {
        "authority_source_id": source.source_id,
        "organization": source.organization,
        "title": source.title,
        "source_type": source.source_type,
        "url": source.url,
        "locator": locator,
        "support_summary": support_summary,
    }


def classify_passage_planning_claim(
    *,
    alu_id: str,
    source_id: str,
    statement: str,
) -> AuthorityFinding:
    """Map a source claim to researched official support without mutating the ALU.

    This verifier is intentionally conservative. "Direct support" means the core
    proposition is explicitly represented in the cited official material. Partial
    support means the official source supports only part of the creator wording or
    the principle behind it. Unsupported details are never silently promoted.
    """
    text = " ".join(statement.split()).strip()
    if not text:
        raise AuthorityVerificationError("EMPTY_AUTHORITY_TARGET_STATEMENT")

    if _contains(text, "four stages", "appraisal", "planning", "execution", "monitoring"):
        return AuthorityFinding(
            alu_id=alu_id,
            source_id=source_id,
            statement=text,
            support_status=SUPPORT_DIRECT,
            authority_refs=(
                _ref(
                    IMO_A893,
                    locator="Annex 1.3",
                    support_summary=(
                        "Defines voyage/passage planning as appraisal, detailed berth-to-berth "
                        "planning, execution, and monitoring."
                    ),
                ),
                _ref(
                    MCA_OOW_03483,
                    locator="Navigation syllabus, item 1(a)",
                    support_summary=(
                        "Requires candidates to explain appraisal, planning, execution, and "
                        "monitoring as the stages of a passage plan."
                    ),
                ),
            ),
            rationale=(
                "The official sources explicitly identify the same four-stage framework."
            ),
        )

    if "interview" in text.lower() or "checklist" in text.lower():
        return AuthorityFinding(
            alu_id=alu_id,
            source_id=source_id,
            statement=text,
            support_status=SUPPORT_NOT_APPLICABLE,
            authority_refs=(),
            rationale=(
                "This is interview/communication advice rather than a navigational procedure "
                "claim, so authority verification is not applicable at this stage."
            ),
        )

    if _contains(text, "appraisal") and (
        "collect" in text.lower() or "information" in text.lower()
    ):
        return AuthorityFinding(
            alu_id=alu_id,
            source_id=source_id,
            statement=text,
            support_status=SUPPORT_PARTIAL,
            authority_refs=(
                _ref(
                    IMO_A893,
                    locator="Annex 2.1 and 2.2",
                    support_summary=(
                        "Requires consideration of all relevant voyage information, including "
                        "up-to-date charts, navigational warnings, tide information, port "
                        "information, and other voyage-specific data."
                    ),
                ),
            ),
            rationale=(
                "The official guidance supports the appraisal principle and several listed "
                "information types, but does not reproduce every creator-listed item in the "
                "same stage or wording."
            ),
        )

    if _contains(text, "during planning") or _contains(text, "berth-to-berth"):
        return AuthorityFinding(
            alu_id=alu_id,
            source_id=source_id,
            statement=text,
            support_status=SUPPORT_PARTIAL,
            authority_refs=(
                _ref(
                    IMO_A893,
                    locator="Annex 3.1–3.4",
                    support_summary=(
                        "Requires a detailed berth-to-berth plan, plotting the intended route, "
                        "identifying dangers, considering under-keel clearance, course-alteration "
                        "points, position-fixing methods, contingencies, and master approval."
                    ),
                ),
            ),
            rationale=(
                "The official resolution strongly supports the core planning framework, but "
                "does not explicitly verify every creator term such as XTD, abort points, route "
                "validation wording, or the 'most economical route' phrasing."
            ),
        )

    if _contains(text, "execution") and (
        "approved plan" in text.lower() or "follows" in text.lower()
    ):
        return AuthorityFinding(
            alu_id=alu_id,
            source_id=source_id,
            statement=text,
            support_status=SUPPORT_PARTIAL,
            authority_refs=(
                _ref(
                    IMO_A893,
                    locator="Annex 3.4 and 4.1",
                    support_summary=(
                        "Requires master approval before commencement and execution in accordance "
                        "with the finalized plan or properly made changes."
                    ),
                ),
            ),
            rationale=(
                "The execution principle is supported, while 'after proper discussion' is not "
                "the wording used by the official resolution."
            ),
        )

    if "gps" in text.lower() or "position-fixing method" in text.lower():
        return AuthorityFinding(
            alu_id=alu_id,
            source_id=source_id,
            statement=text,
            support_status=SUPPORT_PARTIAL,
            authority_refs=(
                _ref(
                    IMO_A893,
                    locator="Annex 3.2.6",
                    support_summary=(
                        "Requires planned position-fixing methods and frequency, including primary "
                        "and secondary options where reliability is important."
                    ),
                ),
            ),
            rationale=(
                "The official source supports redundancy in position fixing, but it does not "
                "state the creator's exact absolute wording 'never GPS alone'."
            ),
        )

    if _contains(text, "monitoring") and (
        "position" in text.lower() or "progress" in text.lower()
    ):
        return AuthorityFinding(
            alu_id=alu_id,
            source_id=source_id,
            statement=text,
            support_status=SUPPORT_PARTIAL,
            authority_refs=(
                _ref(
                    IMO_A893,
                    locator="Annex 5.1–5.2 and 3.2.6",
                    support_summary=(
                        "Requires close and continuous monitoring of progress against the plan "
                        "and plans for primary and secondary position-fixing methods."
                    ),
                ),
                _ref(
                    MCA_OOW_03483,
                    locator="Navigation syllabus, items 1(a) and 2(c)",
                    support_summary=(
                        "Requires knowledge of executing/monitoring a passage plan and identifying "
                        "charted objects suitable for position fixing."
                    ),
                ),
            ),
            rationale=(
                "Continuous monitoring and redundant position fixing are supported, but the exact "
                "creator wording about radar-and-visual cross-checking is not fully reproduced."
            ),
        )

    return AuthorityFinding(
        alu_id=alu_id,
        source_id=source_id,
        statement=text,
        support_status=SUPPORT_UNRESOLVED,
        authority_refs=(),
        rationale=(
            "No deterministic passage-planning authority rule matched this statement. "
            "Leave it unresolved rather than inferring support."
        ),
    )


def verify_passage_planning_items(
    items: Iterable[dict[str, Any]],
    *,
    source_id: str,
) -> tuple[AuthorityFinding, ...]:
    findings: list[AuthorityFinding] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise AuthorityVerificationError(f"AUTHORITY_ITEM_{index}_NOT_OBJECT")
        alu_id = item.get("alu_id")
        statement = item.get("statement")
        if not isinstance(alu_id, str) or not alu_id.strip():
            raise AuthorityVerificationError(f"AUTHORITY_ITEM_{index}_MISSING_ALU_ID")
        if not isinstance(statement, str) or not statement.strip():
            raise AuthorityVerificationError(f"AUTHORITY_ITEM_{index}_MISSING_STATEMENT")
        findings.append(
            classify_passage_planning_claim(
                alu_id=alu_id,
                source_id=source_id,
                statement=statement,
            )
        )
    return tuple(findings)


def finding_to_json(finding: AuthorityFinding) -> dict[str, Any]:
    return {
        "alu_id": finding.alu_id,
        "source_id": finding.source_id,
        "statement": finding.statement,
        "support_status": finding.support_status,
        "authority_refs": list(finding.authority_refs),
        "rationale": finding.rationale,
        "promotion_note": (
            "Authority support is evidence for review only. It does not mutate the original "
            "ALU verification_status or grant operational permission."
        ),
    }


def build_authority_review(
    *,
    topic_id: str,
    targets: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    if topic_id != "passage-planning":
        raise AuthorityVerificationError(f"UNSUPPORTED_AUTHORITY_TOPIC:{topic_id}")

    findings: list[dict[str, Any]] = []
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise AuthorityVerificationError(f"AUTHORITY_TARGET_{index}_NOT_OBJECT")
        source_id = target.get("source_id")
        alu_id = target.get("alu_id")
        statement = target.get("statement")
        if not isinstance(source_id, str) or not source_id.strip():
            raise AuthorityVerificationError(f"AUTHORITY_TARGET_{index}_MISSING_SOURCE_ID")
        if not isinstance(alu_id, str) or not alu_id.strip():
            raise AuthorityVerificationError(f"AUTHORITY_TARGET_{index}_MISSING_ALU_ID")
        if not isinstance(statement, str) or not statement.strip():
            raise AuthorityVerificationError(f"AUTHORITY_TARGET_{index}_MISSING_STATEMENT")

        finding = classify_passage_planning_claim(
            alu_id=alu_id.strip(),
            source_id=source_id.strip(),
            statement=statement,
        )
        findings.append(finding_to_json(finding))

    counts = {
        SUPPORT_DIRECT: 0,
        SUPPORT_PARTIAL: 0,
        SUPPORT_NOT_APPLICABLE: 0,
        SUPPORT_UNRESOLVED: 0,
    }
    for finding in findings:
        status = finding["support_status"]
        counts[status] = counts.get(status, 0) + 1

    return {
        "schema_version": "1.0",
        "artifact_type": "authority_review",
        "topic_id": topic_id,
        "verification_method": "curated_official_source_rules_v1",
        "authority_sources": [
            {
                "source_id": source.source_id,
                "organization": source.organization,
                "title": source.title,
                "source_type": source.source_type,
                "url": source.url,
                "published_or_adopted": source.published_or_adopted,
                "notes": source.notes,
            }
            for source in PASSAGE_PLANNING_AUTHORITY_SOURCES
        ],
        "findings": findings,
        "counts": counts,
        "promotion_note": (
            "This review does not mutate ALU verification_status, rendering_scope, "
            "or operational eligibility. Promotion requires a separate deterministic gate."
        ),
    }


def render_authority_review(review: dict[str, Any]) -> str:
    if review.get("artifact_type") != "authority_review":
        raise AuthorityVerificationError("INVALID_AUTHORITY_REVIEW_ARTIFACT")

    counts = review.get("counts") or {}
    lines: list[str] = [
        "# Passage Planning — Authority Review",
        "",
        f"- **Method:** {review.get('verification_method')}",
        f"- **Direct support:** {counts.get(SUPPORT_DIRECT, 0)}",
        f"- **Partial support:** {counts.get(SUPPORT_PARTIAL, 0)}",
        f"- **Not applicable:** {counts.get(SUPPORT_NOT_APPLICABLE, 0)}",
        f"- **Unresolved:** {counts.get(SUPPORT_UNRESOLVED, 0)}",
        "",
        "> Authority support does not automatically grant operational permission.",
        "",
        "## Official sources",
        "",
    ]
    for source in review.get("authority_sources") or []:
        lines.extend(
            [
                f"### {source['source_id']} — {source['title']}",
                "",
                f"- Organization: {source['organization']}",
                f"- Type: {source['source_type']}",
                f"- URL: {source['url']}",
                "",
            ]
        )

    lines.extend(["## Findings", ""])
    for finding in review.get("findings") or []:
        lines.extend(
            [
                f"### {finding['source_id']} / {finding['alu_id']}",
                "",
                f"**Source claim:** {finding['statement']}",
                "",
                f"- **Authority support:** {finding['support_status']}",
                f"- **Why:** {finding['rationale']}",
            ]
        )
        refs = finding.get("authority_refs") or []
        if refs:
            lines.append("- **Official support:**")
            for ref in refs:
                lines.append(
                    f"  - {ref['authority_source_id']} · {ref['locator']} — "
                    f"{ref['support_summary']}"
                )
        else:
            lines.append("- **Official support:** none attached by this rule.")
        lines.append("")

    lines.extend(
        [
            "## Gate status",
            "",
            "- Original ALUs remain unchanged.",
            "- Creator statements remain creator statements.",
            "- Direct/partial official support may be used by the next Instructional Designer stage, but not as automatic operational authorization.",
            "",
        ]
    )
    return "\n".join(lines)
