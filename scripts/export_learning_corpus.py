from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Export only Marinetime learning JSON artifacts (EvidencePack + ALU) "
            "into one portable ZIP for backup/course processing. No audio/frames."
        )
    )
    p.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "storage" / "evidence",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "storage" / "exports" / "marinetime_learning_corpus.zip",
    )
    return p


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parser().parse_args()
    evidence_root = args.evidence_root
    out = args.out

    if not evidence_root.exists():
        print(f"EXPORT_FAILED:EVIDENCE_ROOT_NOT_FOUND:{evidence_root}", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    missing_alus: list[str] = []
    files_to_add: list[tuple[Path, str]] = []

    for evidence_path in sorted(evidence_root.glob("*/evidence_pack.json")):
        source_id = evidence_path.parent.name
        try:
            evidence = _load_json(evidence_path)
        except Exception as exc:
            print(
                f"EXPORT_FAILED source_id={source_id} "
                f"error={type(exc).__name__}:{exc}",
                file=sys.stderr,
            )
            return 2

        if evidence.get("source_id") != source_id:
            print(
                f"EXPORT_FAILED source_id={source_id} error=EVIDENCE_SOURCE_ID_MISMATCH",
                file=sys.stderr,
            )
            return 2

        evidence_arc = f"evidence/{source_id}/evidence_pack.json"
        files_to_add.append((evidence_path, evidence_arc))

        alu_path = evidence_path.parent / "alus.json"
        alu_record: dict[str, Any] | None = None
        if alu_path.is_file():
            try:
                alu = _load_json(alu_path)
            except Exception as exc:
                print(
                    f"EXPORT_FAILED source_id={source_id} "
                    f"error={type(exc).__name__}:{exc}",
                    file=sys.stderr,
                )
                return 2
            if alu.get("source_id") != source_id:
                print(
                    f"EXPORT_FAILED source_id={source_id} error=ALU_SOURCE_ID_MISMATCH",
                    file=sys.stderr,
                )
                return 2
            entries = alu.get("alus")
            if not isinstance(entries, list) or not entries:
                print(
                    f"EXPORT_FAILED source_id={source_id} error=ALUS_NOT_NONEMPTY_LIST",
                    file=sys.stderr,
                )
                return 2
            alu_arc = f"evidence/{source_id}/alus.json"
            files_to_add.append((alu_path, alu_arc))
            alu_record = {
                "path": alu_arc,
                "sha256": _sha256(alu_path),
                "bytes": alu_path.stat().st_size,
                "alu_count": len(entries),
                "model": alu.get("model"),
                "prompt_version": alu.get("prompt_version"),
            }
        else:
            missing_alus.append(source_id)

        records.append(
            {
                "source_id": source_id,
                "evidence": {
                    "path": evidence_arc,
                    "sha256": _sha256(evidence_path),
                    "bytes": evidence_path.stat().st_size,
                },
                "alu": alu_record,
            }
        )

    if not records:
        print("EXPORT_FAILED:NO_EVIDENCE_PACKS", file=sys.stderr)
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_scope": "learning-json-only",
        "evidence_packs": len(records),
        "alus_completed": sum(1 for item in records if item["alu"] is not None),
        "missing_alus": missing_alus,
        "total_alu_items": sum(
            int(item["alu"]["alu_count"])
            for item in records
            if item["alu"] is not None
        ),
        "sources": records,
    }

    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        for path, arcname in files_to_add:
            archive.write(path, arcname)

    tmp.replace(out)

    print("LEARNING_CORPUS_EXPORT_OK")
    print(f"output={out}")
    print(f"evidence_packs={manifest['evidence_packs']}")
    print(f"alus_completed={manifest['alus_completed']}")
    print(f"missing_alus={len(missing_alus)}")
    print(f"total_alu_items={manifest['total_alu_items']}")
    print(f"zip_bytes={out.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
