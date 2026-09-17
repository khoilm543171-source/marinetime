from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MediaToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoProbe:
    duration_ms: int | None
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool


def _run(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MediaToolError(f"TOOL_NOT_FOUND:{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError(f"TOOL_TIMEOUT:{command[0]}") from exc
    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()
        detail = stderr[-1][:300] if stderr else "unknown error"
        raise MediaToolError(f"TOOL_FAILED:{command[0]}:{detail}")
    return result


def _parse_fraction(value: Any) -> float | None:
    if not isinstance(value, str) or not value or value == "0/0":
        return None
    try:
        numerator, denominator = value.split("/", 1)
        denominator_float = float(denominator)
        if denominator_float == 0:
            return None
        return float(numerator) / denominator_float
    except (TypeError, ValueError):
        return None


def probe_video(path: str | Path, *, ffprobe: str = "ffprobe") -> VideoProbe:
    source = Path(path)
    if not source.is_file():
        raise MediaToolError("MEDIA_FILE_NOT_FOUND")

    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,avg_frame_rate",
            "-of",
            "json",
            str(source),
        ]
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaToolError("FFPROBE_INVALID_JSON") from exc

    if not isinstance(payload, dict):
        raise MediaToolError("FFPROBE_PAYLOAD_INVALID")

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise MediaToolError("FFPROBE_STREAMS_MISSING")
    video_stream = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise MediaToolError("VIDEO_STREAM_MISSING")

    duration_ms: int | None = None
    format_payload = payload.get("format")
    duration_raw = format_payload.get("duration") if isinstance(format_payload, dict) else None
    try:
        if duration_raw is not None:
            duration_ms = max(0, round(float(duration_raw) * 1000))
    except (TypeError, ValueError):
        duration_ms = None

    width = video_stream.get("width") if isinstance(video_stream.get("width"), int) else None
    height = video_stream.get("height") if isinstance(video_stream.get("height"), int) else None
    fps = _parse_fraction(video_stream.get("avg_frame_rate"))
    has_audio = any(
        isinstance(item, dict) and item.get("codec_type") == "audio" for item in streams
    )
    return VideoProbe(
        duration_ms=duration_ms,
        width=width,
        height=height,
        fps=fps,
        has_audio=has_audio,
    )


def extract_asr_wav(
    source_path: str | Path,
    output_path: str | Path,
    *,
    ffmpeg: str = "ffmpeg",
    overwrite: bool = False,
) -> Path:
    """Extract deterministic mono 16 kHz PCM audio for ASR.

    A failed FFmpeg invocation must not leave a newly-created partial WAV that a
    later run could mistake for a completed artifact. Existing outputs are never
    removed unless the caller explicitly requested overwrite.
    """
    source = Path(source_path)
    output = Path(output_path)
    if not source.is_file():
        raise MediaToolError("MEDIA_FILE_NOT_FOUND")
    existed_before = output.exists()
    if existed_before and not overwrite:
        raise MediaToolError("OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        _run(
            [
                ffmpeg,
                "-y" if overwrite else "-n",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output),
            ],
            timeout=300,
        )
    except MediaToolError:
        if not existed_before and output.exists():
            output.unlink(missing_ok=True)
        raise

    if not output.is_file():
        raise MediaToolError("AUDIO_OUTPUT_MISSING")
    if output.stat().st_size <= 0:
        if not existed_before:
            output.unlink(missing_ok=True)
        raise MediaToolError("AUDIO_OUTPUT_EMPTY")
    return output
