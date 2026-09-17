# 3-video pilot protocol

## Video selection
Choose exactly:
1. a clear technical explanation;
2. a blurry/ambiguous video containing OCR or numeric risk;
3. a creator heuristic/practical case.

## Local raw-video preflight
Before selecting or processing files, run:

```powershell
python scripts/check_pilot_local_stack.py
```

The check is read-only: it does not install packages or change the machine. Full raw-video pilot readiness currently requires FFmpeg, FFprobe, WhisperX, PySceneDetect (`scenedetect`), and PaddleOCR. `nvidia-smi` is reported when present but GPU availability is not a hard requirement for the pilot.

On native Windows, follow [`WINDOWS_PILOT_SETUP.md`](WINDOWS_PILOT_SETUP.md) when capabilities are missing. Install the stack deliberately and in stages; do not auto-install heavy dependencies from an agent.

## First local preprocess pass
The first raw-video pass is local only. It performs source hashing, FFprobe inspection, 16 kHz audio extraction, WhisperX segment transcription, scene detection, source-frame extraction, PaddleOCR, EvidencePack construction, and deterministic EvidencePack validation. It does **not** call Opus or any other LLM provider.

Example for a creator/practical video:

```powershell
python scripts/preprocess_pilot_video.py `
  --video "C:\path\to\video.mp4" `
  --source-id "PILOT-VID-001" `
  --provenance creator_experience `
  --out "storage\evidence\PILOT-VID-001" `
  --whisper-model small `
  --device cpu
```

`source_id` and provenance are explicit inputs. Do not infer them from a filename. The default Whisper model for this pilot command is `small`, but it is a CLI parameter rather than a schema invariant. First use may download local WhisperX/PaddleOCR model assets. Use a fresh output directory for each attempt so stale partial artifacts cannot be mistaken for evidence.

The current first-pass keyframe policy uses scene midpoints, keeps at most 8 frames with deterministic coverage, and falls back to the video midpoint when no scene boundary is returned. Evidence frames are always extracted from the source video; generated images are never evidence.

## Required artifacts per video
- Source record
- Job manifest record
- EvidencePack
- ALU array
- Validation decisions
- Token/cost ledger

## Pilot learning outputs
Across the three videos generate:
- one bilingual lesson;
- one visual-identification question;
- one oral-exam question;
- one constructed-response troubleshooting scenario;
- one FeedbackReport path.

## Acceptance criteria
- Every accepted ALU has valid evidence refs.
- Unsupported claims never become educational facts.
- Creator experience never becomes authoritative procedure.
- Ambiguous numeric evidence is preserved as uncertain, never guessed/corrected.
- Each factual lesson section maps to ALU refs.
- Safety validator and budget guard tests pass.
- No unchanged source is reprocessed.
- Any reprocessing is targeted before full-source reprocessing.

## Learning-value check
For at least one topic compare:
1. raw-video session -> assessment;
2. Marinetime lesson -> same-format assessment;
3. delayed review after 2-3 days.

Track recall, visual identification, oral explanation, troubleshooting reasoning, time spent, and confidence vs correctness.
