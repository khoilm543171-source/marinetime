from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pipeline.source_ingest import (
    SourceIngestError,
    build_local_video_source,
    sha256_file,
)


class SourceIngestTests(unittest.TestCase):
    def test_sha256_matches_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            source.write_bytes(b"marine-video-bytes")
            self.assertEqual(
                sha256_file(source),
                hashlib.sha256(b"marine-video-bytes").hexdigest(),
            )

    def test_build_video_source_preserves_explicit_identity_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            source.write_bytes(b"abc")
            record = build_local_video_source(
                path=source,
                source_id="PILOT-CLEAR-001",
                provenance_class="creator_experience",
            )

            self.assertEqual(record["schema_version"], "1.0")
            self.assertEqual(record["source_id"], "PILOT-CLEAR-001")
            self.assertEqual(record["media_type"], "video")
            self.assertEqual(record["provenance_class"], "creator_experience")
            self.assertTrue(record["content_hash"].startswith("sha256:"))
            self.assertNotIn(str(source), record.values())

    def test_missing_file_is_rejected(self) -> None:
        with self.assertRaisesRegex(SourceIngestError, "SOURCE_FILE_NOT_FOUND"):
            build_local_video_source(
                path="missing-video.mp4",
                source_id="VID-001",
                provenance_class="unverified",
            )

    def test_provenance_is_not_inferred_or_silently_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "maker-training-video.mp4"
            source.write_bytes(b"abc")
            with self.assertRaisesRegex(SourceIngestError, "INVALID_PROVENANCE_CLASS"):
                build_local_video_source(
                    path=source,
                    source_id="VID-001",
                    provenance_class="probably-maker-manual",
                )


if __name__ == "__main__":
    unittest.main()
