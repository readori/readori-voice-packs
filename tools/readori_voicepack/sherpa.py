"""Thin wrapper around the sherpa-onnx Python API (optional dependency).

The configuration mirrors what the app does in ``SherpaOnnxTTSClient.loadSynthesizerIfNeeded``
(:196-290): vits gets lexicon / data_dir / dict_dir and noise_scale 0.667, noise_scale_w 0.8,
length_scale 1.0; kokoro gets voices / lexicon list / data_dir and length_scale 1.0; both use
max_num_sentences 1 and silence_scale 0.2 on the CPU provider.

Python keyword names follow sherpa-onnx 1.13.x. Optional tuning keywords are dropped when the
installed version rejects them, so a different 1.x release still synthesises with defaults.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .common import VoicePackError

SHERPA_PIN = "1.13.6"


class SherpaUnavailable(VoicePackError):
    """sherpa-onnx is not installed."""


class Synthesizer(Protocol):
    def generate(self, text: str, sid: int = 0, speed: float = 1.0) -> Any: ...


def import_sherpa():
    try:
        import sherpa_onnx
    except ImportError as exc:
        raise SherpaUnavailable(
            "sherpa-onnx is not installed. Install the audio extras: "
            f"pip install -e .[audio]  (pins sherpa-onnx=={SHERPA_PIN})"
        ) from exc
    return sherpa_onnx


def _path(root: Path, rel: str | None) -> str:
    return str((root / rel).resolve()) if rel else ""


def _construct(cls, required: dict[str, Any], optional: dict[str, Any]):
    try:
        return cls(**required, **optional)
    except TypeError:
        return cls(**required)


def load_synthesizer(root: Path, manifest: dict[str, Any], *, threads: int = 1) -> Synthesizer:
    sherpa = import_sherpa()
    model_type = manifest["type"]
    if model_type == "vits":
        vits = _construct(
            sherpa.OfflineTtsVitsModelConfig,
            {
                "model": _path(root, manifest.get("model")),
                "lexicon": _path(root, manifest.get("lexicon")),
                "tokens": _path(root, manifest.get("tokens")),
                "data_dir": _path(root, manifest.get("dataDir")),
            },
            {
                "dict_dir": _path(root, manifest.get("dictDir")),
                "noise_scale": 0.667,
                "noise_scale_w": 0.8,
                "length_scale": 1.0,
            },
        )
        model_config = sherpa.OfflineTtsModelConfig(
            vits=vits, num_threads=threads, debug=False, provider="cpu"
        )
    elif model_type == "kokoro":
        lexicons = manifest.get("lexicons") or (
            [manifest["lexicon"]] if manifest.get("lexicon") else []
        )
        kokoro = _construct(
            sherpa.OfflineTtsKokoroModelConfig,
            {
                "model": _path(root, manifest.get("model")),
                "voices": _path(root, manifest.get("voices")),
                "tokens": _path(root, manifest.get("tokens")),
                "data_dir": _path(root, manifest.get("dataDir")),
                "lexicon": ",".join(_path(root, x) for x in lexicons if x),
            },
            {"length_scale": 1.0},
        )
        model_config = sherpa.OfflineTtsModelConfig(
            kokoro=kokoro, num_threads=threads, debug=False, provider="cpu"
        )
    else:
        raise VoicePackError(f"unsupported model type: {model_type}")

    config = _construct(
        sherpa.OfflineTtsConfig,
        {
            "model": model_config,
            "rule_fsts": ",".join(_path(root, x) for x in (manifest.get("ruleFsts") or [])),
            "rule_fars": ",".join(_path(root, x) for x in (manifest.get("ruleFars") or [])),
            "max_num_sentences": 1,
        },
        {"silence_scale": 0.2},
    )
    if hasattr(config, "validate") and not config.validate():
        raise VoicePackError("sherpa-onnx rejected the model configuration")
    return sherpa.OfflineTts(config)


def generate(tts: Synthesizer, text: str, sid: int, speed: float = 1.0) -> tuple[np.ndarray, int]:
    audio = tts.generate(text=text, sid=sid, speed=speed)
    samples = np.asarray(audio.samples, dtype=np.float32)
    return samples, int(audio.sample_rate)


def check_audio(samples: np.ndarray, sample_rate: int) -> list[str]:
    """Smoke criteria: non-empty, finite, 0.3-30 s long and not silent."""
    problems: list[str] = []
    if samples.size == 0:
        return ["no samples produced"]
    if sample_rate <= 0:
        return [f"invalid sample rate {sample_rate}"]
    if not bool(np.all(np.isfinite(samples))):
        problems.append("samples contain NaN or Inf")
        return problems
    duration = samples.size / sample_rate
    if duration < 0.3 or duration > 30.0:
        problems.append(f"duration {duration:.2f}s outside 0.3-30s")
    peak = float(np.max(np.abs(samples)))
    if math.isnan(peak) or peak < 1e-4:
        problems.append("output is silent (peak < 1e-4)")
    return problems
