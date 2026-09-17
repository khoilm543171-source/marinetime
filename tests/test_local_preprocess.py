from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.local_preprocess import (
    LocalPreprocessError,
    SceneWindow,
    _coerce_paddle_payload,
    _paddle_cpu_compat_kwargs,
    _prepare_retry_output,
    _seconds_to_ms,
    build_local_evidence_pack,
    select_keyframe_timestamps,
)


class _JsonResult:
    def __init__(self, payload):
        self.json = payload


class LocalPreprocessTests(unittest.TestCase):
    def test_seconds_to_ms_rejects_invalid_or_negative_values(self) -> None:
        self.assertEqual(_seconds_to_ms(1.234), 1234)
        with self.assertRaisesRegex(LocalPreprocessError, "NEGATIVE_TIMESTAMP_SECONDS"):
            _seconds_to_ms(-0.1)
        with self.assertRaisesRegex(LocalPreprocessError, "INVALID_TIMESTAMP_SECONDS"):
            _seconds_to_ms(float("nan"))
        with self.assertRaisesRegex(LocalPreprocessError, "INVALID_TIMESTAMP_SECONDS"):
            _seconds_to_ms(None)

    def test_keyframes_use_scene_midpoints_and_preserve_coverage(self) -> None:
        scenes = [SceneWindow(index * 1000, (index + 1) * 1000) for index in range(10)]
        timestamps = select_keyframe_timestamps(scenes, duration_ms=10000, max_frames=4)
        self.assertEqual(timestamps, [500, 3500, 6500, 9500])

    def test_keyframe_fallback_uses_video_midpoint(self) -> None:
        self.assertEqual(
            select_keyframe_timestamps([], duration_ms=9000, max_frames=8),
            [4500],
        )
        self.assertEqual(
            select_keyframe_timestamps([], duration_ms=None, max_frames=8),
            [0],
        )

    def test_paddle_payload_accepts_nested_json_result(self) -> None:
        result = _JsonResult({"res": {"rec_texts": ["RPM"], "rec_scores": [0.99]}})
        self.assertEqual(
            _coerce_paddle_payload(result),
            {"rec_texts": ["RPM"], "rec_scores": [0.99]},
        )

    def test_paddle_payload_rejects_invalid_json_text(self) -> None:
        self.assertIsNone(_coerce_paddle_payload(_JsonResult("not-json")))

    def test_paddle_cpu_compat_disables_pir_and_mkldnn(self) -> None:
        previous = os.environ.get("FLAGS_enable_pir_api")
        try:
            os.environ["FLAGS_enable_pir_api"] = "1"
            kwargs = _paddle_cpu_compat_kwargs()
            self.assertEqual(os.environ["FLAGS_enable_pir_api"], "0")
            self.assertEqual(kwargs, {"enable_mkldnn": False})
        finally:
            if previous is None:
                os.environ.pop("FLAGS_enable_pir_api", None)
            else:
                os.environ["FLAGS_enable_pir_api"] = previous

    def test_retry_cleanup_removes_only_known_partial_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = root / "frames"
            frames.mkdir()
            (root / "audio.wav").write_bytes(b"partial")
            (root / "transcript_segments.json").write_text("[]", encoding="utf-8")
            (frames / "frame_001.jpg").write_bytes(b"partial")
            keep = root / "keep.txt"
            keep.write_text("keep", encoding="utf-8")

            returned = _prepare_retry_output(root)

            self.assertEqual(returned, frames)
            self.assertFalse((root / "audio.wav").exists())
            self.assertFalse((root / "transcript_segments.json").exists())
            self.assertFalse((frames / "frame_001.jpg").exists())
            self.assertTrue(keep.exists())

    def test_retry_cleanup_refuses_completed_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "evidence_pack.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(LocalPreprocessError, "OUTPUT_ALREADY_COMPLETE"):
                _prepare_retry_output(root)

    def test_builder_assigns_cross_modality_unique_ids_and_validates(self) -> None:
        pack = build_local_evidence_pack(
            source_id="VID-001",
            provenance_class="creator_experience",
            context={"equipment": "unknown"},
            transcript_segments=[{"start_ms": 0, "end_ms": 1000, "text": "Check the pump."}],
            frame_records=[{"timestamp_ms": 500, "artifact_path": "frames/frame_001.jpg"}],
            ocr_records=[{"timestamp_ms": 500, "text": "PUMP 1", "score": 0.91}],
        )

        self.assertEqual(pack["transcript_segments"][0]["evidence_id"], "SEG-001")
        self.assertEqual(pack["frames"][0]["evidence_id"], "FRAME-001")
        self.assertEqual(pack["ocr_hits"][0]["evidence_id"], "OCR-001")
        self.assertEqual(pack["preprocess_version"], "local_video_v1.1")

    def test_builder_does_not_correct_uncertain_ocr_text(self) -> None:
        uncertain = "8O bar"
        pack = build_local_evidence_pack(
            source_id="VID-002",
            provenance_class="unverified",
            context={},
            transcript_segments=[],
            frame_records=[{"timestamp_ms": 100, "artifact_path": "frames/frame_001.jpg"}],
            ocr_records=[{"timestamp_ms": 100, "text": uncertain, "score": 0.42}],
        )
        self.assertEqual(pack["ocr_hits"][0]["text"], uncertain)


if __name__ == "__main__":
    unittest.main()
