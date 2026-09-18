from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class TopicPacketError(ValueError):
    """Raised when lesson blueprints cannot be safely combined into a topic packet."""


@dataclass(frozen=True)
class TopicClaim:
    topic_claim_id: str
    statement: str
    statement_type: str | None
    support_level: str | None
    safety_critical: bool
    numeric_claim: bool
    occurrences: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class TopicPacket:
    schema_version: str
    topic_id: str
    display_title: str
    source_ids: tuple[str, ...]
    source_titles: tuple[str, ...]
    mental_model: tuple[str, ...]
    claims: tuple[TopicClaim, ...]
    authority_targets: tuple[dict[str, str], ...]
    source_count: int


_CREATOR_PREFIXES = (
    "the creator states that ",
    "the creator reports that ",
    "the creator describes ",
    "the creator recommends ",
    "the creator states ",
    "the creator reports ",
)


def _normalize_claim_text(value: str) -> str:
    text = " ".join(value.split()).strip().lower()
    for prefix in _CREATOR_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _slug(value: str) -> str:
    asciiish = value.lower()
    asciiish = re.sub(r"[^a-z0-9]+", "-", asciiish)
    return asciiish.strip("-") or "topic"


def classify_blueprint_topic(blueprint: dict[str, Any]) -> tuple[str, str]:
    title = str(blueprint.get("display_title") or "")
    haystack = " ".join(
        [
            title,
            " ".join(str(item) for item in blueprint.get("mental_model") or []),
            " ".join(
                str(item.get("statement", ""))
                for item in blueprint.get("key_items") or []
                if isinstance(item, dict)
            ),
        ]
    ).lower()

    if (
        "passage planning" in haystack
        and "appraisal" in haystack
        and "monitoring" in haystack
    ):
        return "passage-planning", "Passage Planning"

    return _slug(title), title.strip() or "Untitled Topic"


def build_topic_packet(
    blueprints: Iterable[dict[str, Any]],
    *,
    topic_id: str,
    display_title: str,
) -> TopicPacket:
    selected: list[dict[str, Any]] = []
    for index, blueprint in enumerate(blueprints):
        if not isinstance(blueprint, dict):
            raise TopicPacketError(f"BLUEPRINT_{index}_NOT_OBJECT")
        blueprint_topic_id, _ = classify_blueprint_topic(blueprint)
        if blueprint_topic_id == topic_id:
            selected.append(blueprint)

    if not selected:
        raise TopicPacketError(f"NO_BLUEPRINTS_FOR_TOPIC:{topic_id}")

    source_ids: list[str] = []
    source_titles: list[str] = []
    mental_model: list[str] = []
    grouped: dict[str, dict[str, Any]] = {}
    authority_targets: list[dict[str, str]] = []

    for blueprint in selected:
        source_id = blueprint.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise TopicPacketError("BLUEPRINT_MISSING_SOURCE_ID")
        source_id = source_id.strip()
        if source_id not in source_ids:
            source_ids.append(source_id)

        source_title = str(
            blueprint.get("display_title")
            or blueprint.get("original_title")
            or source_id
        ).strip()
        if source_title and source_title not in source_titles:
            source_titles.append(source_title)

        for item in blueprint.get("mental_model") or []:
            line = " ".join(str(item).split()).strip()
            if line and line not in mental_model:
                mental_model.append(line)

        raw_authority_targets = {
            str(value)
            for value in (blueprint.get("authority_targets") or [])
            if isinstance(value, str) and value.strip()
        }

        for item in blueprint.get("key_items") or []:
            if not isinstance(item, dict):
                continue
            alu_id = item.get("alu_id")
            statement = item.get("statement")
            if not isinstance(alu_id, str) or not alu_id.strip():
                continue
            if not isinstance(statement, str) or not statement.strip():
                continue

            key = _normalize_claim_text(statement)
            if not key:
                continue
            occurrence = {"source_id": source_id, "alu_id": alu_id.strip()}
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = {
                    "statement": " ".join(statement.split()).strip(),
                    "statement_type": item.get("statement_type"),
                    "support_level": item.get("support_level"),
                    "safety_critical": bool(item.get("safety_critical")),
                    "numeric_claim": bool(item.get("numeric_claim")),
                    "occurrences": [occurrence],
                }
            else:
                if occurrence not in existing["occurrences"]:
                    existing["occurrences"].append(occurrence)
                existing["safety_critical"] = bool(
                    existing["safety_critical"] or item.get("safety_critical")
                )
                existing["numeric_claim"] = bool(
                    existing["numeric_claim"] or item.get("numeric_claim")
                )
                if (
                    existing.get("support_level") != "directly_supported"
                    and item.get("support_level") == "directly_supported"
                ):
                    existing["support_level"] = "directly_supported"

            if alu_id in raw_authority_targets:
                target = {
                    "source_id": source_id,
                    "alu_id": alu_id,
                    "statement": " ".join(statement.split()).strip(),
                }
                if target not in authority_targets:
                    authority_targets.append(target)

    claims = tuple(
        TopicClaim(
            topic_claim_id=f"TC-{index:03d}",
            statement=value["statement"],
            statement_type=value.get("statement_type"),
            support_level=value.get("support_level"),
            safety_critical=bool(value.get("safety_critical")),
            numeric_claim=bool(value.get("numeric_claim")),
            occurrences=tuple(value["occurrences"]),
        )
        for index, (_, value) in enumerate(sorted(grouped.items()), start=1)
    )

    if not claims:
        raise TopicPacketError("TOPIC_PACKET_HAS_NO_CLAIMS")

    return TopicPacket(
        schema_version="1.0",
        topic_id=topic_id,
        display_title=display_title,
        source_ids=tuple(source_ids),
        source_titles=tuple(source_titles),
        mental_model=tuple(mental_model),
        claims=claims,
        authority_targets=tuple(authority_targets),
        source_count=len(source_ids),
    )


def topic_packet_to_json(packet: TopicPacket) -> dict[str, Any]:
    return {
        "schema_version": packet.schema_version,
        "artifact_type": "topic_packet",
        "topic_id": packet.topic_id,
        "display_title": packet.display_title,
        "source_count": packet.source_count,
        "source_ids": list(packet.source_ids),
        "source_titles": list(packet.source_titles),
        "mental_model": list(packet.mental_model),
        "claims": [
            {
                "topic_claim_id": claim.topic_claim_id,
                "statement": claim.statement,
                "statement_type": claim.statement_type,
                "support_level": claim.support_level,
                "safety_critical": claim.safety_critical,
                "numeric_claim": claim.numeric_claim,
                "occurrences": list(claim.occurrences),
                "source_support_count": len(
                    {item["source_id"] for item in claim.occurrences}
                ),
            }
            for claim in packet.claims
        ],
        "authority_targets": list(packet.authority_targets),
        "scope_note": (
            "Deterministic cross-source aggregation only. Claim deduplication does not "
            "establish truth or authority."
        ),
    }


def render_topic_packet(packet: TopicPacket) -> str:
    lines: list[str] = [
        f"# {packet.display_title} — Topic Packet",
        "",
        f"- **Sources combined:** {packet.source_count}",
        f"- **Distinct source-grounded claims:** {len(packet.claims)}",
        f"- **Authority targets:** {len(packet.authority_targets)}",
        "",
        "> Cross-source aggregation only. Repetition across sources is not proof.",
        "",
        "## Mental model",
        "",
    ]
    if packet.mental_model:
        for item in packet.mental_model:
            lines.append(f"- {item}")
    else:
        lines.append("- No shared mental model was available.")

    lines.extend(["", "## Combined source claims", ""])
    for claim in packet.claims:
        support_count = len({item["source_id"] for item in claim.occurrences})
        flags: list[str] = []
        if claim.safety_critical:
            flags.append("safety-critical")
        if claim.numeric_claim:
            flags.append("numeric")
        lines.extend(
            [
                f"### {claim.topic_claim_id}",
                "",
                claim.statement,
                "",
                f"- Source support count: {support_count}",
                f"- Support level: {claim.support_level}",
            ]
        )
        if flags:
            lines.append("- Flags: " + ", ".join(flags))
        lines.append("- Occurrences:")
        for occurrence in claim.occurrences:
            lines.append(
                f"  - {occurrence['source_id']} / {occurrence['alu_id']}"
            )
        lines.append("")

    lines.extend(
        [
            "## Authority queue",
            "",
        ]
    )
    if packet.authority_targets:
        for target in packet.authority_targets:
            lines.append(
                f"- {target['source_id']} / {target['alu_id']} — {target['statement']}"
            )
    else:
        lines.append("- No authority targets were queued.")

    lines.extend(
        [
            "",
            "## Next stage",
            "",
            "Authority Verifier → Instructional Designer → topic lesson → assessment QA.",
            "",
        ]
    )
    return "\n".join(lines)


def write_topic_packet(
    packet: TopicPacket,
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "topic_packet.json"
    md_path = root / "topic_packet.md"

    json_temp = json_path.with_suffix(".json.tmp")
    json_temp.write_text(
        json.dumps(topic_packet_to_json(packet), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_temp.replace(json_path)

    md_temp = md_path.with_suffix(".md.tmp")
    md_temp.write_text(render_topic_packet(packet), encoding="utf-8")
    md_temp.replace(md_path)
    return json_path, md_path
