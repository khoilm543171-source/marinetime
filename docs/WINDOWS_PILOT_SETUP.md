# Windows 3-video pilot setup

This setup is intentionally manual and staged. Do not let an agent silently install heavy media/ML dependencies on the user's machine.

## 0. Python runtime for the ML pilot

Marinetime core supports Python 3.11+, but the raw-video ML stack has narrower native-wheel compatibility. The observed Windows install failure on Python 3.14 came from WhisperX/CTranslate2 and PaddlePaddle wheel availability, not from Marinetime code.

For the 3-video pilot, use Python 3.11 as the recommended baseline. Python 3.11 is also the version used by Marinetime CI. The current preflight treats Python 3.11-3.13 as the supported pilot band and rejects Python 3.14 for raw-video readiness.

Keep an existing Python 3.14 environment intact while testing the compatible environment. On Windows:

```powershell
winget install --id Python.Python.3.11 -e
```

Open a new PowerShell window and verify the launcher can see it:

```powershell
py -0p
py -3.11 --version
```

Create a separate pilot environment first:

```powershell
cd C:\Users\khoil\marinetime
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
python --version
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

Do not delete the existing `.venv` until the 3.11 pilot environment is proven working.

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

With the Python 3.11 pilot environment active, install packages one stage at a time so failures are attributable:

```powershell
python -m pip install scenedetect opencv-python
python -m pip install whisperx
python -m pip install paddlepaddle paddleocr
```

Do not pin arbitrary package versions just to make installation pass. If one stage fails, stop there and capture the exact error before changing CUDA, Torch, or package versions.

## 3. GPU check

GPU acceleration is optional for the 3-video pilot. After WhisperX installs, inspect Torch rather than assuming that an NVIDIA driver means CUDA is usable from Python:

```powershell
python -c "import torch; print('cuda=', torch.cuda.is_available()); print('device=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

CPU remains a valid fallback for the pilot, only slower. Do not reinstall Torch for CUDA until the base CPU-compatible stack imports cleanly.

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
- keep the Python 3.14 environment until the replacement environment is verified;
- do not change CUDA/Torch merely to silence one package error without first recording the failure;
- do not treat GPU availability as a requirement for pilot correctness;
- raw video processing begins only after the Python ML runtime, FFmpeg/FFprobe, WhisperX, PySceneDetect, and PaddleOCR are all detected.
