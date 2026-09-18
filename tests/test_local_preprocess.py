from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.local_preprocess import (
    LocalModelRuntime,
    LocalPreprocessError,
    SceneWindow,
    _coerce_paddle_payload,
    _extract_frame_with_ffmpeg,
    _seconds_to_ms,
    build_local_evidence_pack,
    extract_frame_image,
    extract_frame_image_with_timestamp_fallback,
    select_keyframe_timestamps,
    transcribe_video_audio,
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
        self.assertEqual(pack["preprocess_version"], "local_video_v1")

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


    def test_local_model_runtime_reuses_each_engine_once(self) -> None:
        calls = {"whisper": 0, "ocr": 0}
        whisper_engine = object()
        ocr_engine = object()

        def whisper_factory(**kwargs):
            calls["whisper"] += 1
            self.assertEqual(kwargs["model_name"], "small")
            return whisper_engine

        def ocr_factory(**kwargs):
            calls["ocr"] += 1
            self.assertEqual(kwargs["lang"], "en")
            return ocr_engine

        runtime = LocalModelRuntime(
            whisper_model="small",
            ocr_lang="en",
            whisper_factory=whisper_factory,
            ocr_factory=ocr_factory,
        )

        self.assertIs(runtime._get_whisper_engine(), whisper_engine)
        self.assertIs(runtime._get_whisper_engine(), whisper_engine)
        self.assertIs(runtime._get_ocr_engine(), ocr_engine)
        self.assertIs(runtime._get_ocr_engine(), ocr_engine)
        self.assertEqual(calls, {"whisper": 1, "ocr": 1})


    @patch("marinetime.pilot.local_preprocess.extract_asr_wav")
    def test_no_audio_video_skips_asr_extraction(self, mocked_extract) -> None:
        result = transcribe_video_audio(
            video_path="silent.mp4",
            output_dir="evidence",
            has_audio=False,
            whisper_model="small",
        )
        self.assertEqual(result, [])
        mocked_extract.assert_not_called()


    @patch("marinetime.pilot.local_preprocess.extract_frame_png")
    @patch("marinetime.pilot.local_preprocess.extract_frame_jpeg")
    def test_frame_extraction_falls_back_to_png_for_mjpeg_encoder_error(
        self,
        mocked_jpeg,
        mocked_png,
    ) -> None:
        mocked_jpeg.side_effect = LocalPreprocessError(
            "TOOL_FAILED:ffmpeg:[vost#0:0/mjpeg] Invalid argument | Nothing was written"
        )
        mocked_png.return_value = Path("frame_001.png")

        result = extract_frame_image(
            "video.mp4",
            "frames/frame_001",
            timestamp_ms=1000,
        )

        self.assertEqual(result, Path("frame_001.png"))
        mocked_png.assert_called_once()

    @patch("marinetime.pilot.local_preprocess.extract_frame_png")
    @patch("marinetime.pilot.local_preprocess.extract_frame_jpeg")
    def test_frame_extraction_does_not_hide_non_mjpeg_failure(
        self,
        mocked_jpeg,
        mocked_png,
    ) -> None:
        mocked_jpeg.side_effect = LocalPreprocessError(
            "TOOL_FAILED:ffmpeg:Invalid data found when processing input"
        )

        with self.assertRaisesRegex(LocalPreprocessError, "Invalid data"):
            extract_frame_image(
                "video.mp4",
                "frames/frame_001",
                timestamp_ms=1000,
            )
        mocked_png.assert_not_called()


    @patch("marinetime.pilot.local_preprocess.extract_frame_png")
    @patch("marinetime.pilot.local_preprocess.extract_frame_jpeg")
    def test_frame_extraction_falls_back_when_jpeg_returns_no_frame(
        self,
        mocked_jpeg,
        mocked_png,
    ) -> None:
        mocked_jpeg.side_effect = LocalPreprocessError("FRAME_OUTPUT_MISSING")
        mocked_png.return_value = Path("frame_001.png")

        result = extract_frame_image(
            "video.mp4",
            "frames/frame_001",
            timestamp_ms=1000,
        )

        self.assertEqual(result, Path("frame_001.png"))
        mocked_png.assert_called_once()


    @patch("marinetime.pilot.media._run")
    def test_successful_ffmpeg_without_frame_keeps_diagnostics(self, mocked_run) -> None:
        import subprocess
        import tempfile

        mocked_run.return_value = subprocess.CompletedProcess(
            ["ffmpeg"],
            0,
            "",
            "frame=0\nOutput file is empty, nothing was encoded\n",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "video.mp4"
            output = root / "frame.jpg"
            source.write_bytes(b"video")
            with self.assertRaises(LocalPreprocessError) as caught:
                _extract_frame_with_ffmpeg(
                    source,
                    output,
                    timestamp_ms=15000,
                    codec_args=["-c:v", "mjpeg"],
                )

        message = str(caught.exception)
        self.assertTrue(message.startswith("FRAME_OUTPUT_MISSING"))
        self.assertIn("timestamp_ms=15000", message)
        self.assertIn("accurate_seek=false", message)
        self.assertIn("nothing was encoded", message.lower())

    @patch("marinetime.pilot.local_preprocess.extract_frame_png")
    @patch("marinetime.pilot.local_preprocess.extract_frame_image")
    def test_timestamp_fallback_records_actual_zero_timestamp(
        self,
        mocked_image,
        mocked_png,
    ) -> None:
        mocked_image.side_effect = LocalPreprocessError(
            "FRAME_OUTPUT_MISSING:timestamp_ms=15000"
        )
        mocked_png.return_value = Path("frame_001_fallback_000000000.png")

        path, actual_timestamp, reason = extract_frame_image_with_timestamp_fallback(
            "video.mp4",
            "frames/frame_001",
            timestamp_ms=15000,
        )

        self.assertEqual(path, Path("frame_001_fallback_000000000.png"))
        self.assertEqual(actual_timestamp, 0)
        self.assertEqual(reason, "NO_FRAME_AT_REQUESTED_TIMESTAMP")
        mocked_png.assert_called_once()

    @patch("marinetime.pilot.local_preprocess.extract_frame_png")
    @patch("marinetime.pilot.local_preprocess.extract_frame_image")
    def test_timestamp_fallback_preserves_failure_when_zero_also_fails(
        self,
        mocked_image,
        mocked_png,
    ) -> None:
        mocked_image.side_effect = LocalPreprocessError("FRAME_OUTPUT_MISSING")
        mocked_png.side_effect = LocalPreprocessError(
            "FRAME_OUTPUT_MISSING:timestamp_ms=0"
        )

        with self.assertRaisesRegex(
            LocalPreprocessError,
            "FRAME_OUTPUT_MISSING_AT_REQUESTED_AND_FALLBACK_TIMESTAMP",
        ):
            extract_frame_image_with_timestamp_fallback(
                "video.mp4",
                "frames/frame_001",
                timestamp_ms=15000,
            )


if __name__ == "__main__":
    unittest.main()
