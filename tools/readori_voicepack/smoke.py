"""Smoke synthesis: one sentence with the pack's default speaker."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import MANIFEST_NAME, VoicePackError, loads_strict
from .samples import smoke_text
from .sherpa import Synthesizer, check_audio, generate, load_synthesizer


@dataclass
class SmokeResult:
    sid: int
    text: str
    sample_rate: int = 0
    samples: int = 0
    duration: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def run_smoke(
    pack_dir: Path,
    *,
    text: str | None = None,
    sid: int | None = None,
    sample_text: str | None = None,
    factory: Callable[[Path, dict[str, Any]], Synthesizer] | None = None,
) -> SmokeResult:
    """``factory`` lets tests inject a fake synthesizer; the default loads sherpa-onnx."""
    manifest_path = pack_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise VoicePackError(f"{MANIFEST_NAME} not found in {pack_dir}")
    manifest = loads_strict(manifest_path.read_text(encoding="utf-8"))
    chosen_sid = sid if sid is not None else int(manifest.get("defaultSpeaker", 0))
    chosen_text = text or smoke_text(manifest.get("language"), sample_text)
    tts = (factory or (lambda root, m: load_synthesizer(root, m)))(pack_dir, manifest)
    samples, rate = generate(tts, chosen_text, chosen_sid)
    result = SmokeResult(
        sid=chosen_sid,
        text=chosen_text,
        sample_rate=rate,
        samples=int(samples.size),
        duration=(samples.size / rate) if rate > 0 else 0.0,
        problems=check_audio(samples, rate),
    )
    return result
