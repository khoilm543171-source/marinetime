# Windows 3-video pilot setup

This setup is intentionally manual and staged. Do not let an agent silently install heavy media/ML dependencies on the user's machine.

## 1. FFmpeg + FFprobe

Preferred Windows path when `winget` is available:

```powershell
winget install --id Gyan.FFmpeg -e
```

Then open a new PowerShell window and verify:

```powershell
ffmpeg -version
ffprobe -version
```

If the package ID is unavailable on the machine, install an official/reputable FFmpeg Windows build manually and add its `bin` directory to `PATH` instead of guessing a different package.

## 2. Python packages

Use the Marinetime virtual environment and install packages one stage at a time so failures are attributable:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "scenedetect[opencv]"
python -m pip install whisperx
python -m pip install paddlepaddle paddleocr
```

Do not pin arbitrary versions just to make installation pass. If one stage fails, stop there and capture the exact error before changing Python, CUDA, Torch, or package versions.

## 3. GPU check

GPU acceleration is optional for the 3-video pilot. After WhisperX installs, inspect Torch rather than assuming that an NVIDIA driver means CUDA is usable from Python:

```powershell
python -c "import torch; print('cuda=', torch.cuda.is_available()); print('device=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

CPU remains a valid fallback for the pilot, only slower.

## 4. Re-run Marinetime preflight

```powershell
python scripts/check_pilot_local_stack.py
```

Expected target:

```json
{
  "raw_video_ready": true,
  "missing_required": []
}
```

The preflight is read-only and never installs packages.

## Guardrails

- no Opus/provider call is needed for setup;
- never paste API keys into install commands or logs;
- do not change the project Python version or CUDA/Torch stack merely to silence one package error without first recording the failure;
- do not treat GPU availability as a requirement for pilot correctness;
- raw video processing begins only after FFmpeg/FFprobe, WhisperX, PySceneDetect, and PaddleOCR are all detected.
