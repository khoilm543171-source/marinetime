from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from marinetime.pilot.media import MediaToolError, extract_asr_wav, probe_video
from marinetime.pipeline.evidence_pack import validate_evidence_pack
from marinetime.pipeline.source_ingest import build_local_video_source, sha256_file


class LocalPreprocessError(RuntimeError):
    """Raised when deterministic/local preprocessing cannot produce safe artifacts."""


PREPROCESS_VERSION = "local_video_v1.1"


@dataclass(frozen=True)
class SceneWindow:
    start_ms: int
    end_ms: int

    @property
    def midpoint_ms(self) -> int:
        return self.start_ms + max(0, self.end_ms - self.start_ms) // 2


def _seconds_to_ms(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LocalPreprocessError("INVALID_TIMESTAMP_SECONDS")
    if value < 0:
        raise LocalPreprocessError("NEGATIVE_TIMESTAMP_SECONDS")
    return round(float(value) * 1000)


def _select_evenly(items: list[int], limit: int) -> list[int]:
    """Deterministically preserve coverage when there are more scenes than frame slots."""
    if limit <= 0:
        raise ValueError("FRAME_LIMIT_MUST_BE_POSITIVE")
    if len(items) <= limit:
        return items
    if limit == 1:
        return [items[len(items) // 2]]

    indexes = [round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)]
    selected: list[int] = []
    for index in indexes:
        value = items[index]
        if not selected or selected[-1] != value:
            selected.append(value)
    return selected


def select_keyframe_timestamps(
    scenes: Iterable[SceneWindow],
    *,
    duration_ms: int | None,
    max_frames: int = 8,
) -> list[int]:
    """Select scene-midpoint keyframes with deterministic fallback and de-duplication."""
    candidates = sorted({scene.midpoint_ms for scene in scenes if scene.end_ms >= scene.start_ms})
    if not candidates:
        if duration_ms is None or duration_ms <= 0:
            candidates = [0]
        else:
            candidates = [duration_ms // 2]
    return _select_evenly(candidates, max_frames)


def detect_scenes(video_path: str | Path, *, threshold: float = 27.0) -> list[SceneWindow]:
    """Detect scene windows lazily so CI does not need PySceneDetect installed."""
    source = Path(video_path)
    if not source.is_file():
        raise LocalPreprocessError("VIDEO_FILE_NOT_FOUND")
    try:
        from scenedetect import ContentDetector, detect
    except ImportError as exc:
        raise LocalPreprocessError("SCENEDETECT_NOT_INSTALLED") from exc

    try:
        raw_scenes = detect(str(source), ContentDetector(threshold=threshold))
    except Exception as exc:  # third-party boundary
        raise LocalPreprocessError(f"SCENE_DETECTION_FAILED:{type(exc).__name__}") from exc

    scenes: list[SceneWindow] = []
    for start, end in raw_scenes:
        start_ms = _seconds_to_ms(start.get_seconds())
        end_ms = _seconds_to_ms(end.get_seconds())
        if end_ms < start_ms:
            raise LocalPreprocessError("SCENE_TIMESTAMP_RANGE_INVALID")
        scenes.append(SceneWindow(start_ms=start_ms, end_ms=end_ms))
    return scenes


def transcribe_whisperx(
    audio_path: str | Path,
    *,
    model_name: str,
    language: str | None = None,
    device: str = "cpu",
    compute_type: str | None = None,
    batch_size: int = 4,
) -> list[dict[str, Any]]:
    """Run one local WhisperX ASR pass and normalize segment-level evidence.

    Alignment/diarization are deliberately out of this first pilot slice. Segment timestamps
    remain directly attributable to WhisperX output and are not repaired or guessed.
    """
    source = Path(audio_path)
    if not source.is_file():
        raise LocalPreprocessError("AUDIO_FILE_NOT_FOUND")
    if not model_name.strip():
        raise LocalPreprocessError("WHISPER_MODEL_REQUIRED")
    if batch_size <= 0:
        raise LocalPreprocessError("INVALID_ASR_BATCH_SIZE")

    try:
        import whisperx
    except ImportError as exc:
        raise LocalPreprocessError("WHISPERX_NOT_INSTALLED") from exc

    if compute_type is None:
        compute_type = "float16" if device == "cuda" else "int8"

    try:
        model = whisperx.load_model(
            model_name,
            device,
            compute_type=compute_type,
            language=language,
        )
        audio = whisperx.load_audio(str(source))
        result = model.transcribe(audio, batch_size=batch_size)
    except Exception as exc:  # model/runtime/network cache boundary
        raise LocalPreprocessError(f"WHISPERX_TRANSCRIBE_FAILED:{type(exc).__name__}") from exc

    raw_segments = result.get("segments") if isinstance(result, dict) else None
    if not isinstance(raw_segments, list):
        raise LocalPreprocessError("WHISPERX_SEGMENTS_MISSING")

    segments: list[dict[str, Any]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            raise LocalPreprocessError("WHISPERX_SEGMENT_NOT_OBJECT")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        start_ms = _seconds_to_ms(item.get("start"))
        end_ms = _seconds_to_ms(item.get("end"))
        if end_ms < start_ms:
            raise LocalPreprocessError("WHISPERX_SEGMENT_RANGE_INVALID")
        segments.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text.strip(),
            }
        )
    return segments


def extract_frame_jpeg(
    video_path: str | Path,
    output_path: str | Path,
    *,
    timestamp_ms: int,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """Extract one source frame with FFmpeg; never synthesize visual evidence."""
    from marinetime.pilot.media import _run

    source = Path(video_path)
    output = Path(output_path)
    if not source.is_file():
        raise LocalPreprocessError("VIDEO_FILE_NOT_FOUND")
    if timestamp_ms < 0:
        raise LocalPreprocessError("NEGATIVE_FRAME_TIMESTAMP")
    if output.exists():
        raise LocalPreprocessError("FRAME_OUTPUT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        _run(
            [
                ffmpeg,
                "-ss",
                f"{timestamp_ms / 1000:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-y",
                str(output),
            ],
            timeout=120,
        )
    except MediaToolError as exc:
        output.unlink(missing_ok=True)
        raise LocalPreprocessError(str(exc)) from exc
    if not output.is_file() or output.stat().st_size <= 0:
        output.unlink(missing_ok=True)
        raise LocalPreprocessError("FRAME_OUTPUT_MISSING")
    return output


def _coerce_paddle_payload(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        payload = result
    else:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return None
    if not isinstance(payload, dict):
        return None
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _paddle_cpu_compat_kwargs() -> dict[str, Any]:
    """Apply the Paddle 3.3.x CPU workaround before importing PaddleOCR.

    PaddleOCR/PaddleX CPU inference can force the PIR/oneDNN path and raise
    ConvertPirAttribute2RuntimeAttribute NotImplementedError. The upstream
    workaround is to disable PIR before import and disable MKL-DNN inference.
    """
    os.environ["FLAGS_enable_pir_api"] = "0"
    return {"enable_mkldnn": False}


def ocr_frame_paddle(
    frame_path: str | Path,
    *,
    lang: str = "en",
    ocr_version: str = "PP-OCRv6",
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Run local PaddleOCR and preserve text, score, and polygons without correction."""
    source = Path(frame_path)
    if not source.is_file():
        raise LocalPreprocessError("FRAME_FILE_NOT_FOUND")

    compat_kwargs = _paddle_cpu_compat_kwargs()
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise LocalPreprocessError("PADDLEOCR_NOT_INSTALLED") from exc

    try:
        ocr = PaddleOCR(
            lang=lang,
            ocr_version=ocr_version,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            **compat_kwargs,
        )
        results = ocr.predict(str(source), text_rec_score_thresh=min_score)
    except Exception as exc:  # third-party model/runtime boundary
        detail = " ".join(str(exc).split())[:300]
        suffix = f":{detail}" if detail else ""
        raise LocalPreprocessError(
            f"PADDLEOCR_FAILED:{type(exc).__name__}{suffix}"
        ) from exc

    hits: list[dict[str, Any]] = []
    for result in results:
        payload = _coerce_paddle_payload(result)
        if payload is None:
            continue
        texts = payload.get("rec_texts")
        scores = payload.get("rec_scores")
        polys = payload.get("rec_polys")
        if not isinstance(texts, (list, tuple)):
            continue
        for index, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                continue
            score = None
            if scores is not None:
                try:
                    score = float(scores[index])
                except (IndexError, TypeError, ValueError):
                    score = None
            polygon = None
            if polys is not None:
                try:
                    raw_polygon = polys[index]
                    polygon = raw_polygon.tolist() if hasattr(raw_polygon, "tolist") else raw_polygon
                except (IndexError, TypeError):
                    polygon = None
            hits.append({"text": text.strip(), "score": score, "polygon": polygon})
    return hits


def build_local_evidence_pack(
    *,
    source_id: str,
    provenance_class: str,
    context: dict[str, Any],
    transcript_segments: list[dict[str, Any]],
    frame_records: list[dict[str, Any]],
    ocr_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assign deterministic evidence ids and validate the resulting EvidencePack."""
    transcript = [
        {"evidence_id": f"SEG-{index:03d}", **item}
        for index, item in enumerate(transcript_segments, start=1)
    ]
    frames = [
        {"evidence_id": f"FRAME-{index:03d}", **item}
        for index, item in enumerate(frame_records, start=1)
    ]
    ocr_hits = [
        {"evidence_id": f"OCR-{index:03d}", **item}
        for index, item in enumerate(ocr_records, start=1)
    ]
    pack: dict[str, Any] = {
        "schema_version": "1.0",
        "source_id": source_id,
        "provenance_class": provenance_class,
        "context": context,
        "transcript_segments": transcript,
        "ocr_hits": ocr_hits,
        "frames": frames,
        "preprocess_version": PREPROCESS_VERSION,
    }
    validate_evidence_pack(pack)
    return pack


def _prepare_retry_output(root: Path) -> Path:
    """Clear only known partial artifacts while protecting a completed pack."""
    if (root / "evidence_pack.json").exists():
        raise LocalPreprocessError("OUTPUT_ALREADY_COMPLETE")
    root.mkdir(parents=True, exist_ok=True)
    (root / "audio.wav").unlink(missing_ok=True)
    (root / "transcript_segments.json").unlink(missing_ok=True)
    frames_dir = root / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in frames_dir.glob("frame_*.jpg"):
        frame.unlink(missing_ok=True)
    return frames_dir


def preprocess_local_video(
    *,
    video_path: str | Path,
    output_dir: str | Path,
    source_id: str,
    provenance_class: str,
    context: dict[str, Any] | None,
    whisper_model: str,
    language: str | None = None,
    ocr_lang: str = "en",
    max_frames: int = 8,
    device: str = "cpu",
) -> dict[str, Any]:
    """Run the first local raw-video pilot pass and persist traceable artifacts.

    No LLM/provider call occurs here. Any model downloads are local WhisperX/PaddleOCR model
    assets handled by their libraries on first use.
    """
    video = Path(video_path)
    root = Path(output_dir)
    frames_dir = _prepare_retry_output(root)

    source_record = build_local_video_source(
        path=video,
        source_id=source_id,
        provenance_class=provenance_class,
    )
    probe = probe_video(video)
    audio_path = extract_asr_wav(video, root / "audio.wav")
    transcript = transcribe_whisperx(
        audio_path,
        model_name=whisper_model,
        language=language,
        device=device,
    )
    _write_json_atomic(root / "transcript_segments.json", transcript)

    scenes = detect_scenes(video)
    timestamps = select_keyframe_timestamps(
        scenes,
        duration_ms=probe.duration_ms,
        max_frames=max_frames,
    )

    frame_records: list[dict[str, Any]] = []
    ocr_records: list[dict[str, Any]] = []
    for frame_index, timestamp_ms in enumerate(timestamps, start=1):
        frame_path = extract_frame_jpeg(
            video,
            frames_dir / f"frame_{frame_index:03d}.jpg",
            timestamp_ms=timestamp_ms,
        )
        relative_path = frame_path.relative_to(root).as_posix()
        frame_records.append(
            {
                "timestamp_ms": timestamp_ms,
                "artifact_path": relative_path,
                "content_hash": f"sha256:{sha256_file(frame_path)}",
            }
        )
        for hit in ocr_frame_paddle(frame_path, lang=ocr_lang):
            ocr_records.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "text": hit["text"],
                    "score": hit.get("score"),
                    "polygon": hit.get("polygon"),
                    "frame_artifact_path": relative_path,
                }
            )

    pack = build_local_evidence_pack(
        source_id=source_id,
        provenance_class=provenance_class,
        context=context or {},
        transcript_segments=transcript,
        frame_records=frame_records,
        ocr_records=ocr_records,
    )

    metadata = {
        "source": source_record,
        "probe": {
            "duration_ms": probe.duration_ms,
            "width": probe.width,
            "height": probe.height,
            "fps": probe.fps,
            "has_audio": probe.has_audio,
        },
        "whisper_model": whisper_model,
        "language": language,
        "ocr_lang": ocr_lang,
        "ocr_version": "PP-OCRv6",
        "device": device,
        "paddle_cpu_compat": {
            "FLAGS_enable_pir_api": "0",
            "enable_mkldnn": False,
        },
    }

    _write_json_atomic(root / "source.json", source_record)
    _write_json_atomic(root / "preprocess_metadata.json", metadata)
    _write_json_atomic(root / "evidence_pack.json", pack)
    return pack


def _write_json_atomic(path: Path, payload: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
