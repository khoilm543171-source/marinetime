from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.preflight import check_local_stack  # noqa: E402


def main() -> int:
    report = check_local_stack()
    payload = {
        "raw_video_ready": report.raw_video_ready,
        "missing_required": list(report.missing_required),
        "capabilities": [
            {
                "name": item.name,
                "kind": item.kind,
                "required_for_raw_video": item.required_for_raw_video,
                "available": item.available,
                "detail": item.detail,
            }
            for item in report.capabilities
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.raw_video_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
