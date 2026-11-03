"""Per-speaker acoustic audit (port of ``readori-tts-voice-audit-v13.py``).

Every speaker of the pack catalog synthesises the same text; RMS, peak, integrated loudness,
median F0 and spectral centroid are measured and written back to ``readori-voices.json``
(``acoustics`` / ``analysisTags``). Only measurements are written: gender, accent and age are
never guessed. The derived label rules are unchanged from v13 so audited catalogs stay
comparable.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import catalog as catalog_mod
from .common import (
    CATALOG_NAME,
    MANIFEST_NAME,
    VoicePackError,
    loads_strict,
    sha256_file,
    write_json,
)
from .samples import audit_text
from .sherpa import Synthesizer, generate, load_synthesizer

AUDIT_SOURCE = "Readori objective audit; labels are derived, not official dataset metadata"


def rms_db(x: np.ndarray) -> float:
    v = float(np.sqrt(np.mean(np.square(x), dtype=np.float64))) if len(x) else 0.0
    return 20 * math.log10(max(v, 1e-12))


def peak_db(x: np.ndarray) -> float:
    return 20 * math.log10(max(float(np.max(np.abs(x))) if len(x) else 0.0, 1e-12))


def spectral_centroid(x: np.ndarray, sr: int) -> float | None:
    if len(x) < 32:
        return None
    w = np.hanning(len(x))
    mag = np.abs(np.fft.rfft(x * w))
    den = float(mag.sum())
    if den <= 0:
        return None
    return float((np.fft.rfftfreq(len(x), 1 / sr) * mag).sum() / den)


def estimate_f0(x: np.ndarray, sr: int) -> float | None:
    """Dependency-light median autocorrelation F0 (coarse low / medium / high grouping only)."""
    frame = max(256, int(sr * 0.04))
    hop = max(128, int(sr * 0.02))
    vals: list[float] = []
    lo = max(1, int(sr / 400))
    hi = max(lo + 1, int(sr / 60))
    for i in range(0, max(0, len(x) - frame), hop):
        y = np.asarray(x[i : i + frame], dtype=np.float64)
        y = y - y.mean()
        if np.sqrt(np.mean(y * y)) < 0.005:
            continue
        ac = np.correlate(y, y, mode="full")[frame - 1 :]
        h = min(hi, len(ac) - 1)
        if h <= lo:
            continue
        lag = lo + int(np.argmax(ac[lo : h + 1]))
        if ac[0] > 0 and ac[lag] / ac[0] > 0.25:
            vals.append(sr / lag)
    return float(np.median(vals)) if vals else None


def labels(metrics: dict[str, Any]) -> list[str]:
    """v13 label rules (unchanged)."""
    tags: list[str] = []
    f0 = metrics.get("medianF0Hz")
    rms = metrics.get("rmsDbfs")
    cent = metrics.get("spectralCentroidHz")
    if rms is not None:
        tags.append("偏轻" if rms < -26 else "洪亮" if rms > -17 else "标准响度")
    if f0 is not None:
        tags.append("低音" if f0 < 145 else "高音" if f0 > 210 else "中音")
    if cent is not None:
        tags.append("偏温暖" if cent < 1800 else "偏清亮" if cent > 2600 else "自然")
    return tags


def measure(x: np.ndarray, sr: int, loudness_meter_factory=None) -> dict[str, Any]:
    duration = len(x) / sr if sr else 0
    met: dict[str, Any] = {
        "sampleRate": sr,
        "durationSec": round(duration, 4),
        "rmsDbfs": round(rms_db(x), 3),
        "peakDbfs": round(peak_db(x), 3),
        "medianF0Hz": None,
        "spectralCentroidHz": None,
        "integratedLufs": None,
    }
    f0 = estimate_f0(x, sr)
    cent = spectral_centroid(x, sr)
    if f0:
        met["medianF0Hz"] = round(f0, 2)
    if cent:
        met["spectralCentroidHz"] = round(cent, 2)
    if loudness_meter_factory is not None and duration >= 0.4:
        try:
            met["integratedLufs"] = round(
                float(loudness_meter_factory(sr).integrated_loudness(x.astype(np.float64))), 3
            )
        except Exception:  # pyloudnorm raises on very short / silent input
            pass
    return met


def apply_metrics(speaker: dict[str, Any], met: dict[str, Any]) -> None:
    speaker["acoustics"] = met
    speaker["analysisTags"] = labels(met)
    speaker["acousticAnalysisSource"] = AUDIT_SOURCE


@dataclass
class AuditResult:
    audited: int = 0
    skipped: list[int] = field(default_factory=list)
    unusable_sids: list[int] = field(default_factory=list)  # sids removed from the catalog
    catalog_sha256: str = ""
    problems: list[str] = field(default_factory=list)


def _loudness_factory():
    try:
        import pyloudnorm as pyln
    except ImportError:
        return None
    return pyln.Meter


def run_audit(
    pack_dir: Path,
    *,
    text: str | None = None,
    speed: float = 1.0,
    threads: int = 1,
    max_speakers: int | None = None,
    factory: Callable[[Path, dict[str, Any]], Synthesizer] | None = None,
    loudness_factory=None,
    keep_wavs: Path | None = None,
    drop_unusable: bool = True,
    progress: Callable[[str], None] | None = None,
) -> AuditResult:
    manifest_path = pack_dir / MANIFEST_NAME
    catalog_path = pack_dir / CATALOG_NAME
    if not manifest_path.is_file():
        raise VoicePackError(f"{MANIFEST_NAME} not found in {pack_dir}")
    if not catalog_path.is_file():
        raise VoicePackError("readori-voices.json missing; run 'build' or 'catalog-init' first")
    manifest = loads_strict(manifest_path.read_text(encoding="utf-8"))
    catalog = catalog_mod.load_catalog_file(catalog_path)

    tts = (factory or (lambda root, m: load_synthesizer(root, m, threads=threads)))(
        pack_dir, manifest
    )
    meter = loudness_factory if loudness_factory is not None else _loudness_factory()
    sentence = audit_text(manifest.get("language"), text)
    speakers = catalog["speakers"]
    selected = speakers if max_speakers is None else speakers[:max_speakers]

    writer = None
    if keep_wavs is not None:
        try:
            import soundfile as sf
        except ImportError as exc:
            raise VoicePackError("--keep-wavs needs soundfile (pip install -e .[audio])") from exc
        keep_wavs.mkdir(parents=True, exist_ok=True)
        writer = sf

    result = AuditResult()
    for index, speaker in enumerate(selected, start=1):
        sid = int(speaker["sid"])
        samples, rate = generate(tts, sentence, sid, speed)
        if samples.size == 0 or rate <= 0 or not bool(np.all(np.isfinite(samples))):
            result.skipped.append(sid)
            result.problems.append(f"sid {sid}: unusable audio (empty / NaN / bad sample rate)")
            continue
        apply_metrics(speaker, measure(samples, rate, meter))
        result.audited += 1
        if writer is not None and keep_wavs is not None:
            writer.write(keep_wavs / f"{sid:03d}.wav", samples, rate)
        if progress:
            progress(f"[{index}/{len(selected)}] sid={sid} {speaker.get('analysisTags')}")

    if drop_unusable and result.skipped:
        default = int(manifest.get("defaultSpeaker", 0))
        if default in result.skipped:
            raise VoicePackError(f"default speaker {default} produced unusable audio")
        catalog["speakers"] = [s for s in speakers if int(s["sid"]) not in result.skipped]
        result.unusable_sids = sorted(result.skipped)

    problems = catalog_mod.decode_problems(catalog)
    problems += catalog_mod.semantic_problems(
        catalog,
        int(manifest.get("speakerCount", 1)),
        int(manifest.get("defaultSpeaker", 0)),
        strict=True,
    )
    if problems:
        raise VoicePackError("audited catalog is inconsistent: " + "; ".join(problems[:5]))

    write_json(catalog_path, catalog)
    manifest["voiceCatalogSHA256"] = sha256_file(catalog_path)
    write_json(manifest_path, manifest)
    result.catalog_sha256 = manifest["voiceCatalogSHA256"]
    return result
