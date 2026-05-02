"""Optional lip-sync dubbing using Wav2Lip.

Lip-sync is GPU-heavy (Wav2Lip needs ~6 GB VRAM for reasonable speed). The
default free HuggingFace Space runs on CPU, where Wav2Lip would be unusably
slow — so this module is gated behind ``USE_LIPSYNC=1`` AND the presence of a
CUDA-capable GPU. When either is missing we log a warning and ask callers to
fall back to plain audio replacement.

To enable: upgrade the HF Space to a GPU tier (e.g. T4 small), set
``USE_LIPSYNC=1`` in the Space's environment, and make sure the Wav2Lip
checkpoint is downloadable (or pre-bake it into the Docker image under
``/models/wav2lip.pth`` and set ``LIPSYNC_CHECKPOINT`` to that path).

The actual Wav2Lip invocation shells out to the upstream repo's
``inference.py`` so we don't have to pin torch internals — you install the
package via ``pip install wav2lip`` on the GPU image and the CLI becomes
available as ``wav2lip-inference``.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Return True only when the operator opted in AND a GPU is available."""
    if os.environ.get("USE_LIPSYNC", "").strip() not in {"1", "true", "yes"}:
        return False
    try:
        import torch  # noqa: WPS433 — deferred so CPU-only deployments don't pay the import cost
    except Exception:  # noqa: BLE001
        log.info("USE_LIPSYNC=1 but torch is not installed; lip-sync disabled")
        return False
    if not torch.cuda.is_available():
        log.info("USE_LIPSYNC=1 but no CUDA GPU visible; lip-sync disabled")
        return False
    return True


def _checkpoint_path() -> str | None:
    path = os.environ.get("LIPSYNC_CHECKPOINT")
    if path and Path(path).is_file():
        return path
    # Common fallback locations on a GPU Space snapshot
    for candidate in ("/models/wav2lip.pth", "/app/models/wav2lip.pth"):
        if Path(candidate).is_file():
            return candidate
    return None


def apply_lipsync(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
) -> str:
    """Run Wav2Lip against the given video + audio. Raises on failure so
    the caller can decide whether to fall back to plain audio replacement.
    """
    if not is_enabled():
        raise RuntimeError("Lip-sync not enabled (USE_LIPSYNC=1 + CUDA required)")

    ckpt = _checkpoint_path()
    if not ckpt:
        raise RuntimeError(
            "LIPSYNC_CHECKPOINT not set and no /models/wav2lip.pth found. "
            "Download from https://github.com/Rudrabha/Wav2Lip and mount it."
        )

    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    binary = shutil.which("wav2lip-inference") or shutil.which("inference.py")
    if binary is None:
        # Fall back to `python -m wav2lip.inference` if the package is installed
        # as a library rather than exposing a CLI.
        cmd = [
            "python",
            "-m",
            "wav2lip.inference",
        ]
    else:
        cmd = [binary]
    cmd += [
        "--checkpoint_path",
        ckpt,
        "--face",
        str(video_path),
        "--audio",
        str(audio_path),
        "--outfile",
        str(output_path),
        "--resize_factor",
        os.environ.get("LIPSYNC_RESIZE", "1"),
        "--pads",
        "0",
        "10",
        "0",
        "0",
    ]
    log.info("Running lip-sync: %s", " ".join(cmd))
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"wav2lip failed (exit={res.returncode}): {res.stderr[-2000:]}"
        )
    if not output_path.is_file():
        raise RuntimeError("wav2lip completed but output file is missing")
    return str(output_path)
