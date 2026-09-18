from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.catalog.creator import (  # noqa: E402
    load_creator_registry,
    normalize_creator_text,
    resolve_creator,
)


class CreatorCatalogTests(unittest.TestCase):
    def _registry(self, root: Path):
        path = root / "creators.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "creators": [
                        {
                            "creator_id": "nguyen-chi-hieu",
                            "display_name": "Nguyễn Chí Hiếu",
                            "aliases": [
                                "Nguyen Chi Hieu",
                                "@nguyenchihieuofficialtv",
                            ],
                            "platform_ids": {
                                "youtube": ["@nguyenchihieuofficialtv"]
                            },
                        },
                        {
                            "creator_id": "abc",
                            "display_name": "ABC",
                            "aliases": ["abc creator"],
                            "platform_ids": {"youtube": ["UC-ABC"]},
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return load_creator_registry(path)

    def test_normalization_handles_vietnamese_diacritics(self) -> None:
        self.assertEqual(
            normalize_creator_text("Nguyễn Chí Hiếu"),
            normalize_creator_text("Nguyen Chi Hieu"),
        )

    def test_platform_identifier_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = self._registry(Path(tmp))
            result = resolve_creator(
                registry=registry,
                filename="ABC - title.mp4",
                uploader_id="@nguyenchihieuofficialtv",
            )
            self.assertEqual(result.creator_id, "nguyen-chi-hieu")
            self.assertEqual(result.source, "platform_id")
            self.assertTrue(result.is_deterministic)

    def test_filename_prefix_resolves_known_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = self._registry(Path(tmp))
            result = resolve_creator(
                registry=registry,
                filename="Nguyễn Chí Hiếu - Tuần đầu trên tàu.mp4",
            )
            self.assertEqual(result.creator_id, "nguyen-chi-hieu")
            self.assertEqual(result.source, "filename_prefix")
            self.assertTrue(result.is_deterministic)

    def test_filename_middle_match_does_not_claim_creator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = self._registry(Path(tmp))
            result = resolve_creator(
                registry=registry,
                filename="Phỏng vấn Nguyễn Chí Hiếu.mp4",
            )
            self.assertEqual(result.creator_id, "unknown")

    def test_ocr_only_match_is_candidate_not_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = self._registry(Path(tmp))
            result = resolve_creator(
                registry=registry,
                filename="video_001.mp4",
                ocr_texts=["Nguyễn Chí Hiếu", "Ship officer"],
            )
            self.assertEqual(result.creator_id, "nguyen-chi-hieu")
            self.assertEqual(result.source, "ocr_candidate")
            self.assertEqual(result.confidence, "candidate")
            self.assertFalse(result.is_deterministic)

    def test_unresolved_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = self._registry(Path(tmp))
            result = resolve_creator(
                registry=registry,
                filename="random.mp4",
            )
            self.assertEqual(result.creator_id, "unknown")
            self.assertEqual(result.confidence, "unknown")


if __name__ == "__main__":
    unittest.main()
