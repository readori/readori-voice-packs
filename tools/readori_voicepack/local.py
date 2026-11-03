"""``build-local``: turn an upstream sherpa-onnx archive into a ZIP the user imports by hand.

This is a neutral "build it yourself" path. The user fetches the archive from upstream, accepts
the upstream licence on their own responsibility and imports the resulting ZIP in the app.
Readori does not review, build or distribute these packs, so the registry licence gate is not
involved and the result is labelled ``tier: local``. Local packs never enter the release index
(``index`` refuses them) and are never turned into Apple asset packs (``ba-manifest`` refuses them).
"""
from __future__ import annotations

import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from . import fetch as fetch_mod
from .build import (
    ESPEAK_DATA_DIRNAME,
    Assembled,
    assemble_pack,
    espeak_attribution_lines,
    has_espeak_data,
    write_espeak_copying,
    write_manifest,
)
from .common import (
    ATTRIBUTION_NAME,
    ID_RE,
    LOCAL_ATTRIBUTION_EN,
    LOCAL_ATTRIBUTION_ZH,
    SHA256_RE,
    VoicePackError,
    sha256_file,
)
from .pack import LocalMeta, PackResult, pack_directory
from .registry import NC_SPDX_RE, load_registry
from .sherpa import SherpaUnavailable
from .smoke import run_smoke
from .validate import validate_directory

DEFAULT_LOCAL_OUT = Path("build/local")
LOCAL_ID_PREFIX = "local-"
ARCHIVE_SUFFIXES = (".tar.bz2", ".tbz2", ".tar.gz", ".tgz", ".tar", ".zip")
ACCEPT_REQUIRED_MESSAGE = (
    "build-local needs --accept-upstream-license. You fetch the model from its upstream source "
    "and must read and accept the upstream licence yourself. Readori does not review or "
    "distribute self-built packs."
)

# Language guess from the archive name when --language is not given (first matching token wins).
_NAME_LANGUAGES = {
    "zh": "zh-CN", "yue": "yue", "cantonese": "yue", "en": "en-US", "ja": "ja-JP", "ko": "ko-KR",
    "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "ru": "ru-RU",
}
_DEFAULT_LANGUAGE = "en-US"
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")

Progress = Callable[[str], None]


@dataclass
class LocalOptions:
    source: str
    out_dir: Path = DEFAULT_LOCAL_OUT
    accept_upstream_license: bool = False
    name: str | None = None
    model_type: str | None = None
    language: str | None = None
    speaker_count: int | None = None
    default_speaker: int | None = None
    display_name: str | None = None
    sha256: str | None = None
    skip_smoke: bool = False
    registry_path: Path = Path("registry/models.yaml")


@dataclass
class LocalResult:
    pack: PackResult
    pack_dir: Path
    pack_id: str
    archive_sha256: str
    manifest: dict[str, Any]
    registry_info: str | None
    smoke: str
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- source handling


def is_url(source: str) -> bool:
    return "://" in source


def source_file_name(source: str) -> str:
    """File name of the archive: last URL path segment, or the local file name."""
    if is_url(source):
        return fetch_mod.archive_filename(source)
    name = Path(source).name
    if not name:
        raise VoicePackError(f"cannot derive an archive name from {source!r}")
    return name


def source_label(source: str) -> str:
    """What the attribution names as origin: the URL, or only the file name (no local paths)."""
    return source if is_url(source) else source_file_name(source)


def archive_stem(name: str) -> str:
    lowered = name.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return name


def default_pack_id(source: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", archive_stem(source_file_name(source)).lower()).strip("-")
    if not slug:
        raise VoicePackError("cannot derive a pack id from the source name; pass --name")
    return f"{LOCAL_ID_PREFIX}{slug}"


def guess_language(source: str) -> str | None:
    for token in re.split(r"[^a-z0-9]+", archive_stem(source_file_name(source)).lower()):
        if token in _NAME_LANGUAGES:
            return _NAME_LANGUAGES[token]
    return None


def acquire_archive(
    source: str, work_dir: Path, *, expected_sha256: str | None, progress: Progress
) -> tuple[Path, str, int]:
    """Download (https only, size capped) or locate the archive; return (path, sha256, bytes)."""
    if is_url(source):
        target = work_dir / source_file_name(source)
        progress(f"downloading {source}")
        sha, size = fetch_mod.download(
            source, target, max_bytes=fetch_mod.DEFAULT_MAX_DOWNLOAD_BYTES
        )
        archive = target
    else:
        archive = Path(source)
        if not archive.is_file():
            raise VoicePackError(f"source archive not found: {archive}")
        sha, size = sha256_file(archive), archive.stat().st_size
    progress(f"sha256: {sha}")
    progress(f"bytes:  {size}")
    if expected_sha256 is not None and sha != expected_sha256:
        raise VoicePackError(f"sha256 mismatch: expected {expected_sha256}, got {sha}")
    return archive, sha, size


def normalize_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    wanted = value.strip().lower()
    if not SHA256_RE.match(wanted):
        raise VoicePackError("--sha256 must be 64 hex characters")
    return wanted


# --------------------------------------------------------------------------- registry note


def registry_info(source: str, registry_path: Path) -> str | None:
    """One informational line when the source is a known registry asset. Never blocks a build.

    Only status and a short licence summary are shown; no registry reasons are exposed.
    """
    registry_path = Path(registry_path)
    if not registry_path.is_file():
        return None
    try:
        registry = load_registry(registry_path)
        name = source_file_name(source)
    except VoicePackError:
        return None
    for entry in registry.models:
        upstream = entry["upstream"]
        if source == upstream.get("url") or name in (
            upstream.get("assetName"),
            PurePosixPath(unquote(urlparse(str(upstream.get("url", ""))).path)).name,
        ):
            return f"registry: {entry['status']}, licence {_licence_summary(entry)}"
    return None


def _licence_summary(entry: dict[str, Any]) -> str:
    lic = entry.get("license") or {}
    spdx = str(lic.get("spdx", "")).split(" (")[0].strip()
    if entry.get("status") == "community" or spdx.upper() in ("", "UNKNOWN", "TODO"):
        return "not verified"
    non_commercial = lic.get("commercialUse") is False or bool(NC_SPDX_RE.search(spdx))
    return f"{spdx} (non-commercial)" if non_commercial else spdx


# --------------------------------------------------------------------------- pack content


def pick_license_file(paths: list[str]) -> str | None:
    """Upstream LICENSE / COPYING file at the shallowest level (not inside espeak-ng-data)."""
    candidates = []
    for rel in paths:
        parts = rel.split("/")
        if any(part.lower() == ESPEAK_DATA_DIRNAME for part in parts[:-1]):
            continue
        base = parts[-1].lower()
        if base.startswith(("license", "licence", "copying")):
            candidates.append((len(parts), rel))
    return min(candidates)[1] if candidates else None


def render_local_attribution(
    asm: Assembled,
    *,
    source: str,
    archive_sha256: str,
    license_file: str | None,
    display_name: str,
    has_espeak: bool,
) -> str:
    lines = [
        LOCAL_ATTRIBUTION_EN.format(source=source_label(source)),
        LOCAL_ATTRIBUTION_ZH,
        "",
    ]
    if license_file:
        lines.append(f"Upstream licence file in this pack: {license_file}")
    else:
        lines.append("The upstream archive contains no LICENSE or COPYING file.")
    lines += [
        "Licence: not verified by Readori (self-built pack)",
        "",
        f"Pack: {display_name}   Pack id: {asm.pack_id}   Pack version: {asm.pack_version}",
        f"Upstream archive SHA-256: {archive_sha256}",
        "Built with: readori_voicepack build-local",
    ]
    if has_espeak:
        lines += espeak_attribution_lines()
    lines += [
        "",
        "Changes made while building",
        "  - Repackaged as a ZIP for the Readori app (file selection, manifest, voice catalog).",
        "  - Removed test audio and helper scripts.",
        "  - Model weights and token files are unchanged from the upstream archive.",
        "",
    ]
    return "\n".join(lines)


def split_languages(language: str) -> list[str]:
    return [part.strip() for part in language.split(",") if part.strip()]


def _local_entry(options: LocalOptions, pack_id: str, language: str) -> dict[str, Any]:
    preset: dict[str, Any] = {"language": language}
    if options.speaker_count is not None:
        preset["speakerCount"] = options.speaker_count
    if options.default_speaker is not None:
        preset["defaultSpeaker"] = options.default_speaker
    return {
        "id": pack_id,
        "packVersion": 1,
        "type": options.model_type,
        "languages": split_languages(language),
        "preset": preset,
    }


# --------------------------------------------------------------------------- build


def _check_options(options: LocalOptions) -> tuple[str, str | None]:
    """Validate user input before any download; return (pack id, normalised sha256)."""
    if not options.accept_upstream_license:
        raise VoicePackError(ACCEPT_REQUIRED_MESSAGE)
    if options.model_type not in (None, "vits", "kokoro"):
        raise VoicePackError("--type must be vits or kokoro (the app supports only these)")
    if options.language is not None and not all(
        _LANGUAGE_RE.match(part.strip()) for part in options.language.split(",")
    ):
        raise VoicePackError("--language must be comma-separated BCP-47 tags, e.g. en-US")
    pack_id = options.name or default_pack_id(options.source)
    if not ID_RE.match(pack_id):
        raise VoicePackError(
            f"invalid pack id {pack_id!r}: use lowercase letters, digits and single hyphens"
        )
    return pack_id, normalize_sha256(options.sha256)


def _run_smoke(pack_dir: Path, skipped: bool) -> str:
    if skipped:
        return "skipped (--skip-smoke)"
    try:
        result = run_smoke(pack_dir)
    except SherpaUnavailable:
        return "skipped (sherpa-onnx is not installed; pip install -e .[audio])"
    if not result.ok:
        raise VoicePackError("smoke test failed: " + "; ".join(result.problems))
    return f"passed ({result.duration:.2f}s of audio, speaker {result.sid})"


def build_local(options: LocalOptions, *, progress: Progress = lambda _msg: None) -> LocalResult:
    pack_id, expected_sha = _check_options(options)
    info = registry_info(options.source, options.registry_path)
    if info:
        progress(info)
    notes: list[str] = []
    root = repo_root_for(options.registry_path)
    with tempfile.TemporaryDirectory(prefix="readori-local-") as tmp:
        archive, archive_sha, _size = acquire_archive(
            options.source, Path(tmp), expected_sha256=expected_sha, progress=progress
        )
        language = options.language or guess_language(options.source)
        if language is None:
            language = _DEFAULT_LANGUAGE
            notes.append(f"language defaulted to {language}; pass --language to set it")
        asm = assemble_pack(
            _local_entry(options, pack_id, language),
            archive,
            options.out_dir,
            repo_root=root,
        )
    notes += asm.notes
    if asm.speaker_count == 1 and options.speaker_count is None and asm.model_type == "kokoro":
        notes.append("speaker count defaulted to 1; pass --speaker-count for multi-voice models")

    license_file = pick_license_file(asm.paths)
    has_espeak = has_espeak_data(asm.pack_dir, asm.paths)
    if has_espeak:
        notes.append(write_espeak_copying(asm.pack_dir, asm.paths, root))
    if license_file is None:
        notes.append("upstream archive has no LICENSE / COPYING file")
    display_name = options.display_name or archive_stem(source_file_name(options.source))
    (asm.pack_dir / ATTRIBUTION_NAME).write_text(
        render_local_attribution(
            asm,
            source=options.source,
            archive_sha256=archive_sha,
            license_file=license_file,
            display_name=display_name,
            has_espeak=has_espeak,
        ),
        encoding="utf-8",
        newline="\n",
    )
    manifest = write_manifest(
        asm,
        display_name=display_name,
        source_url=source_label(options.source),
        # Without an upstream licence file the attribution notice stands in (the importer and
        # the validator both need a resolvable licenseFile).
        license_file=license_file or ATTRIBUTION_NAME,
    )

    check = validate_directory(asm.pack_dir, policy=True)
    notes += [f"warning: {w}" for w in check.warnings]
    if not check.ok:
        raise VoicePackError(
            "built pack failed validation:\n  " + "\n  ".join(str(e) for e in check.errors)
        )
    smoke = _run_smoke(asm.pack_dir, options.skip_smoke)
    pack = pack_directory(
        asm.pack_dir,
        options.out_dir,
        local=LocalMeta(display_name=display_name, languages=split_languages(language)),
    )
    return LocalResult(
        pack=pack,
        pack_dir=asm.pack_dir,
        pack_id=asm.pack_id,
        archive_sha256=archive_sha,
        manifest=manifest,
        registry_info=info,
        smoke=smoke,
        notes=notes,
    )


def repo_root_for(registry_path: Path) -> Path:
    """Repository root used to find registry/license-texts/GPL-3.0.txt (espeak-ng-data packs)."""
    registry_path = Path(registry_path)
    if registry_path.is_file():
        return registry_path.resolve().parent.parent
    return Path(__file__).resolve().parents[2]
