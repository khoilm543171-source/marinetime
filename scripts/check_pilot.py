from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / "config" / "budget.yaml",
    ROOT / "prompts" / "alu_extraction_v1.txt",
    ROOT / "schemas" / "source.schema.json",
    ROOT / "schemas" / "evidence.schema.json",
    ROOT / "schemas" / "alu.schema.json",
    ROOT / "schemas" / "lesson.schema.json",
    ROOT / "src" / "marinetime" / "validation" / "safety.py",
    ROOT / "src" / "marinetime" / "budget" / "guard.py",
]

missing = [str(p.relative_to(ROOT)) for p in REQUIRED if not p.exists()]
if missing:
    raise SystemExit("Missing required pilot files:\n- " + "\n- ".join(missing))
print("Marinetime 3-video pilot scaffold: OK")
