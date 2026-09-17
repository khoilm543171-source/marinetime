from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from marinetime.pilot.media import MediaToolError, _parse_fraction, extract_asr_wav, probe_video


class PilotMediaTests(unittest.TestCase):
    def test_fraction_parser(self) -> None:
        self.assertAlmostEqual(_parse_fraction("30000/1001") or 0, 29.97002997, places=5)
        self.assertIsNone(_parse_fraction("0/0"))
        self.assertIsNone(_parse_fraction("bad"))

    @patch("marinetime.pilot.media._run")
    def test_probe_video_reads_duration_dimensions_fps_and_audio(self, mocked_run) -> None:
        payload = {
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "30/1"},
                {"codec_type": "audio"},
            ],
            "format": {"duration": "12.345"},
        }
        mocked_run.return_value = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            source.write_bytes(b"fake")
            result = probe_video(source)

        self.assertEqual(result.duration_ms, 12345)
        self.assertEqual(result.width, 1080)
        self.assertEqual(result.height, 1920)
        self.assertEqual(result.fps, 30.0)
        self.assertTrue(result.has_audio)

    @patch("marinetime.pilot.media._run")
    def test_probe_rejects_missing_video_stream(self, mocked_run) -> None:
        mocked_run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({"streams": [{"codec_type": "audio"}], "format": {}}), ""
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "audio.mp4"
            source.write_bytes(b"fake")
            with self.assertRaisesRegex(MediaToolError, "VIDEO_STREAM_MISSING"):
                probe_video(source)

    @patch("marinetime.pilot.media._run")
    def test_probe_rejects_non_object_payload(self, mocked_run) -> None:
        mocked_run.return_value = subprocess.CompletedProcess([], 0, "[]", "")
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            source.write_bytes(b"fake")
            with self.assertRaisesRegex(MediaToolError, "FFPROBE_PAYLOAD_INVALID"):
                probe_video(source)

    def test_extract_refuses_to_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            output = Path(temp_dir) / "clip.wav"
            source.write_bytes(b"fake")
            output.write_bytes(b"existing")
            with self.assertRaisesRegex(MediaToolError, "OUTPUT_ALREADY_EXISTS"):
                extract_asr_wav(source, output)

    @patch("marinetime.pilot.media._run")
    def test_extract_uses_mono_16khz_pcm_contract(self, mocked_run) -> None:
        def fake_run(command, *, timeout=60):
            Path(command[-1]).write_bytes(b"wav")
            return subprocess.CompletedProcess(command, 0, "", "")

        mocked_run.side_effect = fake_run
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            output = Path(temp_dir) / "audio" / "clip.wav"
            source.write_bytes(b"fake")
            result = extract_asr_wav(source, output)
            self.assertEqual(result, output)
            command = mocked_run.call_args.args[0]
            self.assertIn("-ac", command)
            self.assertIn("1", command)
            self.assertIn("-ar", command)
            self.assertIn("16000", command)
            self.assertIn("pcm_s16le", command)

    @patch("marinetime.pilot.media._run")
    def test_failed_extract_removes_new_partial_output(self, mocked_run) -> None:
        def fake_run(command, *, timeout=60):
            Path(command[-1]).write_bytes(b"partial")
            raise MediaToolError("TOOL_FAILED:ffmpeg:test")

        mocked_run.side_effect = fake_run
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            output = Path(temp_dir) / "audio" / "clip.wav"
            source.write_bytes(b"fake")
            with self.assertRaisesRegex(MediaToolError, "TOOL_FAILED"):
                extract_asr_wav(source, output)
            self.assertFalse(output.exists())

    @patch("marinetime.pilot.media._run")
    def test_empty_audio_output_is_rejected_and_removed(self, mocked_run) -> None:
        def fake_run(command, *, timeout=60):
            Path(command[-1]).write_bytes(b"")
            return subprocess.CompletedProcess(command, 0, "", "")

        mocked_run.side_effect = fake_run
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            output = Path(temp_dir) / "audio" / "clip.wav"
            source.write_bytes(b"fake")
            with self.assertRaisesRegex(MediaToolError, "AUDIO_OUTPUT_EMPTY"):
                extract_asr_wav(source, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
