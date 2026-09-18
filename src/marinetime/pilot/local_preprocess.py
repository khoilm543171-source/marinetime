from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from marinetime.pilot.media import MediaToolError, extract_asr_wav, probe_video
from marinetime.pipeline.evidence_pack import validate_evidence_pack
from marinetime.pipeline.source_ingest import build_local_video_source, sha256_file


class LocalPreprocessError(RuntimeError):
    """Raised when deterministic/local preprocessing cannot produce safe artifacts."""


PREPROCESS_VERSION = "local_video_v1"


@dataclass(frozen=True)
class SceneWindow:
    start_ms: int
    end_ms: int

    @property
    def midpoint_ms(self) -> int:
        return self.start_ms + max(0, self.end_ms - self.start_ms) // 2


@dataclass
class LocalModelRuntime:
    """Lazily load local ML engines once and reuse them across a worker process."""

    whisper_model: str
    language: str | None = None
    ocr_lang: str = "en"
    device: str = "cpu"
    compute_type: str | None = None
    ocr_version: str = "PP-OCRv6"
    enable_mkldnn: bool = False
    whisper_factory: Callable[..., Any] | None = None
    ocr_factory: Callable[..., Any] | None = None
    _whisper_engine: Any | None = None
    _ocr_engine: Any | None = None

    def _get_whisper_engine(self) -> Any:
        if self._whisper_engine is None:
            factory = self.whisper_factory or create_whisperx_model
            self._whisper_engine = factory(
                model_name=self.whisper_model,
                language=self.language,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._whisper_engine

    def _get_ocr_engine(self) -> Any:
        if self._ocr_engine is None:
            factory = self.ocr_factory or create_paddle_ocr
            self._ocr_engine = factory(
                lang=self.ocr_lang,
                ocr_version=self.ocr_version,
                device="cpu",
                enable_mkldnn=self.enable_mkldnn,
            )
        return self._ocr_engine

    def transcribe(self, audio_path: str | Path, *, batch_size: int = 4) -> list[dict[str, Any]]:
        return transcribe_whisperx(
            audio_path,
            model_name=self.whisper_model,
            language=self.language,
            device=self.device,
            compute_type=self.compute_type,
            batch_size=batch_size,
            whisper_engine=self._get_whisper_engine(),
        )

    def ocr(self, frame_path: str | Path, *, min_score: float = 0.0) -> list[dict[str, Any]]:
        return ocr_frame_paddle(
            frame_path,
            lang=self.ocr_lang,
            ocr_version=self.ocr_version,
            min_score=min_score,
            device="cpu",
            enable_mkldnn=self.enable_mkldnn,
            ocr_engine=self._get_ocr_engine(),
        )


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
    except Exception as exc:
        raise LocalPreprocessError(f"SCENE_DETECTION_FAILED:{type(exc).__name__}") from exc

    scenes: list[SceneWindow] = []
    for start, end in raw_scenes:
        start_ms = _seconds_to_ms(start.get_seconds())
        end_ms = _seconds_to_ms(end.get_seconds())
        if end_ms < start_ms:
            raise LocalPreprocessError("SCENE_TIMESTAMP_RANGE_INVALID")
        scenes.append(SceneWindow(start_ms=start_ms, end_ms=end_ms))
    return scenes


def create_whisperx_model(
    *,
    model_name: str,
    language: str | None = None,
    device: str = "cpu",
    compute_type: str | None = None,
) -> Any:
    """Create one reusable WhisperX model without transcribing any source."""
    if not model_name.strip():
        raise LocalPreprocessError("WHISPER_MODEL_REQUIRED")
    try:
        import whisperx
    except ImportError as exc:
        raise LocalPreprocessError("WHISPERX_NOT_INSTALLED") from exc

    resolved_compute_type = compute_type or ("float16" if device == "cuda" else "int8")
    try:
        return whisperx.load_model(
            model_name,
            device,
            compute_type=resolved_compute_type,
            language=language,
        )
    except Exception as exc:
        detail = " ".join(str(exc).split())[:300]
        suffix = f":{detail}" if detail else ""
        raise LocalPreprocessError(
            f"WHISPERX_MODEL_LOAD_FAILED:{type(exc).__name__}{suffix}"
        ) from exc


def transcribe_whisperx(
    audio_path: str | Path,
    *,
    model_name: str,
    language: str | None = None,
    device: str = "cpu",
    compute_type: str | None = None,
    batch_size: int = 4,
    whisper_engine: Any | None = None,
) -> list[dict[str, Any]]:
    """Run one local WhisperX ASR pass and normalize segment-level evidence."""
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
        model = whisper_engine or create_whisperx_model(
            model_name=model_name,
            language=language,
            device=device,
            compute_type=compute_type,
        )
        audio = whisperx.load_audio(str(source))
        result = model.transcribe(audio, batch_size=batch_size)
    except Exception as exc:
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
        segments.append({"start_ms": start_ms, "end_ms": end_ms, "text": text.strip()})
    return segments


def _extract_frame_with_ffmpeg(
    video_path: str | Path,
    output_path: str | Path,
    *,
    timestamp_ms: int,
    codec_args: list[str],
    ffmpeg: str = "ffmpeg",
    accurate_seek: bool = False,
) -> Path:
    """Extract one source frame without fabricating or repairing visual content."""
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

    seek = f"{timestamp_ms / 1000:.3f}"
    if accurate_seek:
        command = [ffmpeg, "-i", str(source), "-ss", seek]
    else:
        command = [ffmpeg, "-ss", seek, "-i", str(source)]

    try:
        result = _run(
            [
                *command,
                "-frames:v",
                "1",
                *codec_args,
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
        stderr_lines = [
            line.strip()
            for line in (result.stderr or "").splitlines()
            if line.strip()
        ]
        detail = " | ".join(stderr_lines[-8:])[:1200]
        suffix = f":{detail}" if detail else ""
        raise LocalPreprocessError(
            "FRAME_OUTPUT_MISSING"
            f":timestamp_ms={timestamp_ms}"
            f":accurate_seek={str(accurate_seek).lower()}"
            f":output={output.name}"
            f"{suffix}"
        )
    return output


def extract_frame_jpeg(
    video_path: str | Path,
    output_path: str | Path,
    *,
    timestamp_ms: int,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """Extract a JPEG frame with explicit MJPEG settings for Windows FFmpeg."""
    return _extract_frame_with_ffmpeg(
        video_path,
        output_path,
        timestamp_ms=timestamp_ms,
        ffmpeg=ffmpeg,
        codec_args=[
            "-c:v",
            "mjpeg",
            "-pix_fmt",
            "yuvj420p",
            "-threads",
            "1",
            "-q:v",
            "2",
        ],
    )


def extract_frame_png(
    video_path: str | Path,
    output_path: str | Path,
    *,
    timestamp_ms: int,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """Lossless fallback when the local MJPEG encoder rejects a valid decoded frame."""
    return _extract_frame_with_ffmpeg(
        video_path,
        output_path,
        timestamp_ms=timestamp_ms,
        ffmpeg=ffmpeg,
        codec_args=["-c:v", "png", "-compression_level", "3"],
        accurate_seek=True,
    )


def extract_frame_image(
    video_path: str | Path,
    output_stem: str | Path,
    *,
    timestamp_ms: int,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """Prefer JPEG and retry as PNG only for an MJPEG encoder failure.

    This is a codec fallback, not an error-ignore path. If PNG extraction also
    fails, the source still fails preprocessing.
    """
    stem = Path(output_stem)
    jpeg_path = stem.with_suffix(".jpg")
    try:
        return extract_frame_jpeg(
            video_path,
            jpeg_path,
            timestamp_ms=timestamp_ms,
            ffmpeg=ffmpeg,
        )
    except LocalPreprocessError as exc:
        detail = str(exc).lower()
        mjpeg_failure = "mjpeg" in detail and (
            "invalid argument" in detail or "nothing was written" in detail
        )
        empty_jpeg_output = "frame_output_missing" in detail
        if not (mjpeg_failure or empty_jpeg_output):
            raise

    png_path = stem.with_suffix(".png")
    return extract_frame_png(
        video_path,
        png_path,
        timestamp_ms=timestamp_ms,
        ffmpeg=ffmpeg,
    )


def extract_frame_image_with_timestamp_fallback(
    video_path: str | Path,
    output_stem: str | Path,
    *,
    timestamp_ms: int,
    ffmpeg: str = "ffmpeg",
) -> tuple[Path, int, str | None]:
    """Extract a real source frame and expose any timestamp fallback explicitly."""
    try:
        image_path = extract_frame_image(
            video_path,
            output_stem,
            timestamp_ms=timestamp_ms,
            ffmpeg=ffmpeg,
        )
        return image_path, timestamp_ms, None
    except LocalPreprocessError as exc:
        if not str(exc).startswith("FRAME_OUTPUT_MISSING"):
            raise

    if timestamp_ms == 0:
        raise LocalPreprocessError(
            "FRAME_OUTPUT_MISSING_AT_FALLBACK_TIMESTAMP:timestamp_ms=0"
        )

    fallback_stem = Path(output_stem).with_name(
        f"{Path(output_stem).name}_fallback_000000000"
    )
    try:
        image_path = extract_frame_png(
            video_path,
            fallback_stem.with_suffix(".png"),
            timestamp_ms=0,
            ffmpeg=ffmpeg,
        )
    except LocalPreprocessError as exc:
        raise LocalPreprocessError(
            "FRAME_OUTPUT_MISSING_AT_REQUESTED_AND_FALLBACK_TIMESTAMP:"
            f"requested_timestamp_ms={timestamp_ms}:fallback_timestamp_ms=0:{exc}"
        ) from exc

    return image_path, 0, "NO_FRAME_AT_REQUESTED_TIMESTAMP"


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


def create_paddle_ocr(
    *,
    lang: str = "en",
    ocr_version: str = "PP-OCRv6",
    device: str = "cpu",
    enable_mkldnn: bool = False,
) -> Any:
    """Create one reusable PaddleOCR engine."""
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise LocalPreprocessError("PADDLEOCR_NOT_INSTALLED") from exc

    try:
        return PaddleOCR(
            lang=lang,
            ocr_version=ocr_version,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
            enable_mkldnn=enable_mkldnn,
        )
    except Exception as exc:
        detail = " ".join(str(exc).split())[:300]
        suffix = f":{detail}" if detail else ""
        raise LocalPreprocessError(
            f"PADDLEOCR_MODEL_LOAD_FAILED:{type(exc).__name__}{suffix}"
        ) from exc


def ocr_frame_paddle(
    frame_path: str | Path,
    *,
    lang: str = "en",
    ocr_version: str = "PP-OCRv6",
    min_score: float = 0.0,
    device: str = "cpu",
    enable_mkldnn: bool = False,
    ocr_engine: Any | None = None,
) -> list[dict[str, Any]]:
    """Run local PaddleOCR while preserving source text exactly.

    The pilot defaults to CPU with oneDNN/MKLDNN disabled because PaddleOCR's
    default static CPU engine enables it, and that path can raise
    NotImplementedError on some native Windows CPU/model combinations.
    """
    source = Path(frame_path)
    if not source.is_file():
        raise LocalPreprocessError("FRAME_FILE_NOT_FOUND")
    try:
        ocr = ocr_engine or create_paddle_ocr(
            lang=lang,
            ocr_version=ocr_version,
            device=device,
            enable_mkldnn=enable_mkldnn,
        )
        results = ocr.predict(str(source), text_rec_score_thresh=min_score)
    except Exception as exc:
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


def transcribe_video_audio(
    *,
    video_path: str | Path,
    output_dir: str | Path,
    has_audio: bool,
    whisper_model: str,
    language: str | None = None,
    device: str = "cpu",
    runtime: LocalModelRuntime | None = None,
) -> list[dict[str, Any]]:
    """Transcribe only when the probed source actually contains an audio stream."""
    if not has_audio:
        return []

    audio_path = extract_asr_wav(video_path, Path(output_dir) / "audio.wav")
    if runtime is None:
        return transcribe_whisperx(
            audio_path,
            model_name=whisper_model,
            language=language,
            device=device,
        )
    return runtime.transcribe(audio_path)


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
    runtime: LocalModelRuntime | None = None,
) -> dict[str, Any]:
    """Run the first local raw-video pilot pass and persist traceable artifacts."""
    video = Path(video_path)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    frames_dir = root / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    source_record = build_local_video_source(
        path=video,
        source_id=source_id,
        provenance_class=provenance_class,
    )
    probe = probe_video(video)
    transcript = transcribe_video_audio(
        video_path=video,
        output_dir=root,
        has_audio=probe.has_audio,
        whisper_model=whisper_model,
        language=language,
        device=device,
        runtime=runtime,
    )

    scenes = detect_scenes(video)
    timestamps = select_keyframe_timestamps(
        scenes,
        duration_ms=probe.duration_ms,
        max_frames=max_frames,
    )

    frame_records: list[dict[str, Any]] = []
    ocr_records: list[dict[str, Any]] = []
    for frame_index, timestamp_ms in enumerate(timestamps, start=1):
        frame_path, actual_timestamp_ms, timestamp_fallback_reason = (
            extract_frame_image_with_timestamp_fallback(
                video,
                frames_dir / f"frame_{frame_index:03d}",
                timestamp_ms=timestamp_ms,
            )
        )
        relative_path = frame_path.relative_to(root).as_posix()
        frame_record: dict[str, Any] = {
            "timestamp_ms": actual_timestamp_ms,
            "requested_timestamp_ms": timestamp_ms,
            "artifact_path": relative_path,
            "content_hash": f"sha256:{sha256_file(frame_path)}",
        }
        if timestamp_fallback_reason is not None:
            frame_record["timestamp_fallback_reason"] = timestamp_fallback_reason
        frame_records.append(frame_record)
        ocr_hits = (
            runtime.ocr(frame_path)
            if runtime is not None
            else ocr_frame_paddle(
                frame_path,
                lang=ocr_lang,
                device="cpu",
                enable_mkldnn=False,
            )
        )
        for hit in ocr_hits:
            ocr_records.append({
                "timestamp_ms": actual_timestamp_ms,
                "text": hit["text"],
                "score": hit.get("score"),
                "polygon": hit.get("polygon"),
                "frame_artifact_path": relative_path,
            })

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
        "device": device,
    }

    _write_json_atomic(root / "source.json", source_record)
    _write_json_atomic(root / "preprocess_metadata.json", metadata)
    _write_json_atomic(root / "evidence_pack.json", pack)
    return pack


def _write_json_atomic(path: Path, payload: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
