from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Capability:
    name: str
    kind: str
    required_for_raw_video: bool
    available: bool
    detail: str | None = None


@dataclass(frozen=True)
class LocalStackReport:
    capabilities: tuple[Capability, ...]

    @property
    def missing_required(self) -> tuple[str, ...]:
        return tuple(
            item.name
            for item in self.capabilities
            if item.required_for_raw_video and not item.available
        )

    @property
    def raw_video_ready(self) -> bool:
        return not self.missing_required


def _first_output_line(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (completed.stdout or completed.stderr or "").strip()
    if not output:
        return None
    return output.splitlines()[0].strip()


def _python_runtime_capability(
    version: tuple[int, int, int] | None = None,
) -> Capability:
    """Check the ML pilot runtime separately from Marinetime core Python support.

    The core package can support newer Python versions, but the current raw-video
    pilot depends on native ML wheels (WhisperX/CTranslate2/PaddlePaddle). The
    observed Windows resolver failure on Python 3.14 makes 3.11-3.13 the current
    supported pilot band. Python 3.11 is the recommended baseline because CI
    already verifies Marinetime there and it maximizes wheel compatibility.
    """
    current = version or (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    major_minor = current[:2]
    available = (3, 11) <= major_minor < (3, 14)
    return Capability(
        name="python_ml_runtime",
        kind="python_runtime",
        required_for_raw_video=True,
        available=available,
        detail=(
            f"current={current[0]}.{current[1]}.{current[2]}; "
            "pilot_supported=3.11-3.13; recommended=3.11"
        ),
    )


def _executable_capability(
    name: str,
    version_args: Iterable[str],
    *,
    required: bool,
) -> Capability:
    path = shutil.which(name)
    if path is None:
        return Capability(
            name=name,
            kind="executable",
            required_for_raw_video=required,
            available=False,
        )

    detail = _first_output_line([path, *version_args]) or path
    return Capability(
        name=name,
        kind="executable",
        required_for_raw_video=required,
        available=True,
        detail=detail,
    )


def _python_module_capability(name: str, *, required: bool) -> Capability:
    try:
        available = importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        available = False
    return Capability(
        name=name,
        kind="python_module",
        required_for_raw_video=required,
        available=available,
    )


def check_local_stack() -> LocalStackReport:
    """Inspect only; never install packages or mutate the user's machine.

    The 3-video pilot's target raw-video stack is FFmpeg/FFprobe for media,
    WhisperX for timestamped ASR, PySceneDetect for scene boundaries, and
    PaddleOCR for on-screen text. GPU tooling is useful but not required by this
    preflight because CPU execution remains a valid (slower) pilot path.
    """
    capabilities = (
        _python_runtime_capability(),
        _executable_capability("ffmpeg", ["-version"], required=True),
        _executable_capability("ffprobe", ["-version"], required=True),
        _python_module_capability("whisperx", required=True),
        _python_module_capability("scenedetect", required=True),
        _python_module_capability("paddleocr", required=True),
        _executable_capability(
            "nvidia-smi",
            [
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            required=False,
        ),
    )
    return LocalStackReport(capabilities=capabilities)
