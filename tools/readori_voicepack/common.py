"""Shared constants and helpers.

The limits and path rules below mirror the Readori app importer
(``TTSEnginePackageImporter.swift``) so that a pack accepted here is accepted by the app.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

MANIFEST_NAME = "readori-tts-model.json"
CATALOG_NAME = "readori-voices.json"
ATTRIBUTION_NAME = "readori-attribution.txt"

# TTSEnginePackageImporter.swift:131-137
MAX_ZIP_BYTES = 1_500 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_CONFIG_BYTES = 8 * 1024 * 1024

# SherpaOnnxModelManifest.ModelType (TTSEnginePackageImporter.swift:33)
APP_SUPPORTED_TYPES = ("vits", "kokoro")

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

ZIP_FIXED_DATE_TIME = (2026, 1, 1, 0, 0, 0)

# File names the app parses as community TTS engine lists before trying a neural model
# (TTSEnginePackageImporter.swift:286-289). A model pack should not ship these.
APP_ENGINE_LIST_NAMES = frozenset(
    {
        "tts.json",
        "httptts.json",
        "list.json",
        "engines.json",
        "voices.json",
        "config.json",
        "presets.json",
    }
)


class VoicePackError(Exception):
    """Fatal, user-facing error (CLI prints the message and exits with 1)."""


def safe_relative_path(raw: str) -> str | None:
    """Port of ``safeRelativePath`` (TTSEnginePackageImporter.swift:984).

    Returns the normalised path, or ``None`` when the path is unsafe.
    """
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or "\0" in normalized:
        return None
    parts = [p for p in normalized.split("/") if p != ""]
    if not parts:
        return None
    if any(p in (".", "..") or ":" in p for p in parts):
        return None
    return "/".join(parts)


def is_manifest_path(raw: str | None) -> bool:
    """True when ``raw`` is already a normalised safe relative path.

    The app's ``exists()`` helper requires ``safe == relative`` (no backslashes, no
    doubled or trailing slashes).
    """
    return raw is not None and safe_relative_path(raw) == raw


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON number: {name}")


def loads_strict(text: str | bytes) -> Any:
    """json.loads that rejects NaN / Infinity (Foundation's JSONDecoder rejects them)."""
    return json.loads(text, parse_constant=_reject_constant)


def dumps_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_pretty(value), encoding="utf-8", newline="\n")


def is_todo(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper().startswith("TODO")


def is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def first_language_subtag(language: str | None) -> str:
    if not language:
        return "en"
    first = language.split(",")[0].strip()
    return first.split("-")[0].lower() or "en"
