from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = ROOT / "storage" / "evidence"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Deep local audit of EvidencePack and ALU artifacts using only the Python "
            "standard library. No provider/API dependencies are imported."
        )
    )
    p.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    p.add_argument("--verbose", action="store_true")
    return p


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return None, "JSON_ROOT_NOT_OBJECT"
    return payload, None


def _evidence_ids(pack: dict[str, Any]) -> tuple[set[str], list[str]]:
    ids: set[str] = set()
    errors: list[str] = []
    for collection in ("transcript_segments", "ocr_hits", "frames"):
        items = pack.get(collection)
        if not isinstance(items, list):
            errors.append(f"{collection}:NOT_LIST")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{collection}[{index}]:NOT_OBJECT")
                continue
            evidence_id = item.get("evidence_id")
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                errors.append(f"{collection}[{index}]:MISSING_EVIDENCE_ID")
                continue
            if evidence_id in ids:
                errors.append(f"DUPLICATE_EVIDENCE_ID:{evidence_id}")
            ids.add(evidence_id)
    return ids, errors


def _usage_total(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    total = 0
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        value = usage.get(key, 0)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            total += value
    return total


def main() -> int:
    args = parser().parse_args()
    root = args.evidence_root

    evidence_files = sorted(root.glob("*/evidence_pack.json")) if root.exists() else []
    alu_files = sorted(root.glob("*/alus.json")) if root.exists() else []

    missing_alus: list[str] = []
    invalid_evidence: list[str] = []
    invalid_alus: list[str] = []
    valid_evidence = 0
    valid_alus = 0
    total_alu_items = 0
    provider_backed = 0
    zero_usage = 0
    model_counts: Counter[str] = Counter()
    prompt_counts: Counter[str] = Counter()
    usage_tokens = 0

    for evidence_path in evidence_files:
        folder_source = evidence_path.parent.name
        pack, load_error = _load_json(evidence_path)
        if load_error or pack is None:
            invalid_evidence.append(f"{folder_source}:{load_error}")
            continue

        source_id = pack.get("source_id")
        if source_id != folder_source:
            invalid_evidence.append(
                f"{folder_source}:SOURCE_ID_MISMATCH:{source_id!r}"
            )
            continue

        required = (
            "schema_version",
            "provenance_class",
            "context",
            "transcript_segments",
            "ocr_hits",
            "frames",
            "preprocess_version",
        )
        missing = [key for key in required if key not in pack]
        if missing:
            invalid_evidence.append(
                f"{folder_source}:MISSING_TOP_LEVEL:{','.join(missing)}"
            )
            continue

        evidence_ids, evidence_errors = _evidence_ids(pack)
        if not evidence_ids:
            evidence_errors.append("NO_EVIDENCE_IDS")
        if evidence_errors:
            invalid_evidence.append(
                f"{folder_source}:" + "|".join(evidence_errors[:10])
            )
            continue

        valid_evidence += 1
        alu_path = evidence_path.parent / "alus.json"
        if not alu_path.is_file():
            missing_alus.append(folder_source)
            continue

        artifact, alu_load_error = _load_json(alu_path)
        if alu_load_error or artifact is None:
            invalid_alus.append(f"{folder_source}:{alu_load_error}")
            continue

        artifact_errors: list[str] = []
        if artifact.get("source_id") != folder_source:
            artifact_errors.append(
                f"SOURCE_ID_MISMATCH:{artifact.get('source_id')!r}"
            )

        entries = artifact.get("alus")
        if not isinstance(entries, list) or not entries:
            artifact_errors.append("ALUS_NOT_NONEMPTY_LIST")
            entries = []

        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                artifact_errors.append(f"ENTRY_{index}:NOT_OBJECT")
                continue
            alu = entry.get("alu")
            decision = entry.get("decision")
            if not isinstance(alu, dict):
                artifact_errors.append(f"ENTRY_{index}:ALU_NOT_OBJECT")
                continue
            if not isinstance(decision, dict):
                artifact_errors.append(f"ENTRY_{index}:DECISION_NOT_OBJECT")

            if alu.get("source_id") != folder_source:
                artifact_errors.append(
                    f"ENTRY_{index}:ALU_SOURCE_MISMATCH:{alu.get('source_id')!r}"
                )

            alu_id = alu.get("alu_id")
            if not isinstance(alu_id, str) or not alu_id.strip():
                artifact_errors.append(f"ENTRY_{index}:MISSING_ALU_ID")

            statement = alu.get("statement")
            if not isinstance(statement, str) or not statement.strip():
                artifact_errors.append(f"ENTRY_{index}:MISSING_STATEMENT")

            refs = alu.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                artifact_errors.append(f"ENTRY_{index}:MISSING_EVIDENCE_REFS")
            else:
                unknown = [
                    ref for ref in refs
                    if not isinstance(ref, str) or ref not in evidence_ids
                ]
                if unknown:
                    artifact_errors.append(
                        f"ENTRY_{index}:UNKNOWN_EVIDENCE_REFS:{unknown[:5]!r}"
                    )

            safety = alu.get("safety")
            if not isinstance(safety, dict):
                artifact_errors.append(f"ENTRY_{index}:SAFETY_NOT_OBJECT")

        if artifact_errors:
            invalid_alus.append(
                f"{folder_source}:" + "|".join(artifact_errors[:15])
            )
            continue

        valid_alus += 1
        total_alu_items += len(entries)
        model = str(artifact.get("model") or "UNKNOWN")
        prompt = str(artifact.get("prompt_version") or "UNKNOWN")
        model_counts[model] += 1
        prompt_counts[prompt] += 1
        artifact_usage = _usage_total(artifact.get("usage"))
        usage_tokens += artifact_usage
        if artifact_usage > 0:
            provider_backed += 1
        else:
            zero_usage += 1

    orphan_alus = [
        path.parent.name
        for path in alu_files
        if not (path.parent / "evidence_pack.json").is_file()
    ]

    print("LOCAL_ARTIFACT_AUDIT")
    print(f"evidence_files={len(evidence_files)}")
    print(f"valid_evidence={valid_evidence}")
    print(f"invalid_evidence={len(invalid_evidence)}")
    print(f"alu_files={len(alu_files)}")
    print(f"valid_alus={valid_alus}")
    print(f"invalid_alus={len(invalid_alus)}")
    print(f"missing_alus={len(missing_alus)}")
    print(f"orphan_alus={len(orphan_alus)}")
    print(f"total_alu_items={total_alu_items}")
    print(f"provider_backed_artifacts={provider_backed}")
    print(f"zero_usage_artifacts={zero_usage}")
    print(f"recorded_usage_tokens={usage_tokens}")

    print("MODELS")
    for model, count in sorted(model_counts.items()):
        print(f"model={model} count={count}")

    print("PROMPTS")
    for prompt, count in sorted(prompt_counts.items()):
        print(f"prompt={prompt} count={count}")

    if missing_alus:
        print("MISSING_ALUS")
        for source_id in missing_alus:
            print(f"missing={source_id}")

    if invalid_evidence:
        print("INVALID_EVIDENCE")
        for item in invalid_evidence:
            print(f"invalid_evidence_item={item}")

    if invalid_alus:
        print("INVALID_ALUS")
        for item in invalid_alus:
            print(f"invalid_alu_item={item}")

    if orphan_alus:
        print("ORPHAN_ALUS")
        for source_id in orphan_alus:
            print(f"orphan={source_id}")

    if args.verbose:
        print("VALID_SOURCES")
        for evidence_path in evidence_files:
            source_id = evidence_path.parent.name
            alu_path = evidence_path.parent / "alus.json"
            print(
                f"source={source_id} evidence={evidence_path.is_file()} "
                f"alu={alu_path.is_file()}"
            )

    passed = (
        len(evidence_files) == valid_evidence
        and len(alu_files) == valid_alus
        and not invalid_evidence
        and not invalid_alus
        and not orphan_alus
    )
    print(f"audit_passed={'true' if passed else 'false'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
