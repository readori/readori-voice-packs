"""Voice catalog (``readori-voices.json``) helpers.

Ported from ``init-readori-voice-catalog-v13.py`` and aligned with the app decoder
``SherpaVoiceCatalog.swift`` (types at :6-153, semantics at :259-270).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    MAX_CONFIG_BYTES,
    VoicePackError,
    is_number,
    is_plain_int,
    loads_strict,
    write_json,
)

_TOP_FIELDS = {
    "schemaVersion": "int",
    "catalogId": "str",
    "modelProfile": "str",
    "language": "str",
    "speakerCount": "int",
    "defaultSpeaker": "int",
}

_ENTRY_FIELDS = {
    "sourceSpeakerId": "str",
    "name": "str",
    "displayName": "loc",
    "language": "str",
    "languages": "strlist",
    "gender": "str",
    "genderSource": "str",
    "ageGroupCode": "str",
    "ageGroup": "loc",
    "accent": "str",
    "accentLabel": "loc",
    "metadataSource": "str",
    "acoustics": "acoustics",
    "analysisTags": "strlist",
    "tags": "strlist",
    "style": "str",
    "styles": "strlist",
    "attributes": "attrs",
}

_ACOUSTICS_FIELDS = {
    "sampleRate": "int",
    "durationSec": "num",
    "rmsDbfs": "num",
    "peakDbfs": "num",
    "medianF0Hz": "num",
    "spectralCentroidHz": "num",
    "integratedLufs": "num",
    "pitchClass": "str",
    "loudnessClass": "str",
    "brightness": "str",
    "speakingRate": "num",
}


def _check_kind(kind: str, value: Any, where: str, problems: list[str]) -> None:
    if value is None:  # Swift decodeIfPresent treats null as nil
        return
    if kind == "str":
        if not isinstance(value, str):
            problems.append(f"{where}: expected string")
    elif kind == "int":
        if not is_plain_int(value):
            problems.append(f"{where}: expected integer")
    elif kind == "num":
        if not is_number(value):
            problems.append(f"{where}: expected number")
    elif kind == "strlist":
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            problems.append(f"{where}: expected array of strings")
    elif kind == "loc":
        if isinstance(value, str):
            return
        if not isinstance(value, dict):
            problems.append(f"{where}: expected string or {{zh,en}} object")
            return
        for key in ("zh", "en"):
            if value.get(key) is not None and not isinstance(value[key], str):
                problems.append(f"{where}.{key}: expected string")
    elif kind == "attrs":
        if not isinstance(value, dict):
            problems.append(f"{where}: expected object of string arrays")
            return
        for key, item in value.items():
            if not isinstance(item, list) or not all(isinstance(x, str) for x in item):
                problems.append(f"{where}.{key}: expected array of strings")
    elif kind == "acoustics":
        if not isinstance(value, dict):
            problems.append(f"{where}: expected object")
            return
        for key, sub in _ACOUSTICS_FIELDS.items():
            if key in value:
                _check_kind(sub, value[key], f"{where}.{key}", problems)


def decode_problems(catalog: Any) -> list[str]:
    """Structural check equivalent to ``JSONDecoder().decode(SherpaVoiceCatalog.self)``."""
    problems: list[str] = []
    if not isinstance(catalog, dict):
        return ["catalog: expected JSON object"]
    for key, kind in _TOP_FIELDS.items():
        if key in catalog:
            _check_kind(kind, catalog[key], key, problems)
    speakers = catalog.get("speakers")
    if not isinstance(speakers, list):
        problems.append("speakers: required array missing")
        return problems
    for index, item in enumerate(speakers):
        where = f"speakers[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{where}: expected object")
            continue
        if not is_plain_int(item.get("sid")):
            problems.append(f"{where}.sid: required integer missing")
        for key, kind in _ENTRY_FIELDS.items():
            if key in item:
                _check_kind(kind, item[key], f"{where}.{key}", problems)
    return problems


def semantic_problems(
    catalog: dict[str, Any],
    speaker_count: int,
    default_speaker: int,
    *,
    strict: bool = True,
) -> list[str]:
    """App semantics (``validateVoiceCatalog``) plus, in strict mode, builder consistency."""
    problems: list[str] = []
    speakers = catalog.get("speakers") or []
    if not speakers:
        problems.append("catalog has no speakers")
        return problems
    version = catalog.get("schemaVersion")
    if version is not None and version < 1:
        problems.append("catalog schemaVersion must be >= 1")
    max_count = min(512, max(1, speaker_count))
    seen: set[int] = set()
    for item in speakers:
        sid = item.get("sid")
        if not is_plain_int(sid) or sid < 0 or sid >= max_count:
            problems.append(f"catalog sid {sid!r} outside 0..{max_count - 1}")
        elif sid in seen:
            problems.append(f"catalog sid {sid} duplicated")
        else:
            seen.add(sid)
    declared = catalog.get("speakerCount")
    if declared is not None and declared != max_count:
        problems.append(f"catalog speakerCount {declared} != package speakerCount {max_count}")
    declared_default = catalog.get("defaultSpeaker")
    if declared_default is not None and declared_default not in seen:
        problems.append(f"catalog defaultSpeaker {declared_default} is not a described sid")
    if strict:
        if declared_default is not None and declared_default != default_speaker:
            problems.append(
                f"catalog defaultSpeaker {declared_default} != package defaultSpeaker "
                f"{default_speaker}"
            )
        if default_speaker not in seen and len(seen) == max_count:
            problems.append("catalog does not contain package defaultSpeaker")
    return problems


def load_catalog_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise VoicePackError(f"voice catalog not found: {path}")
    if path.stat().st_size > MAX_CONFIG_BYTES:
        raise VoicePackError(f"voice catalog exceeds {MAX_CONFIG_BYTES} bytes: {path}")
    try:
        catalog = loads_strict(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise VoicePackError(f"invalid voice catalog JSON ({path}): {exc}") from exc
    problems = decode_problems(catalog)
    if problems:
        raise VoicePackError(f"voice catalog {path} is not decodable by the app: {problems[:5]}")
    return catalog


def init_catalog(
    *,
    catalog_id: str,
    speaker_count: int,
    default_speaker: int = 0,
    profile: str | None = None,
    language: str | None = None,
    speaker_names: list[str] | None = None,
    hidden_sids: list[int] | None = None,
) -> dict[str, Any]:
    """Create a catalog that only contains facts supplied by the caller.

    ``hidden_sids`` are left out of the catalog (partial catalogs are valid for the app,
    ``SherpaVoiceCatalog.swift:259-270``); ``speakerCount`` stays the manifest count.

    Gender / accent / style are never inferred (port of init-readori-voice-catalog-v13.py).
    """
    if not 1 <= speaker_count <= 512:
        raise VoicePackError("speaker count must be 1...512")
    if not 0 <= default_speaker < speaker_count:
        raise VoicePackError("default speaker must be within the speaker range")
    names = [n.strip() for n in (speaker_names or []) if n.strip()]
    if names and len(names) != speaker_count:
        raise VoicePackError(
            f"speaker file contains {len(names)} names, expected {speaker_count}"
        )
    langs = [x.strip() for x in (language or "").split(",") if x.strip()]
    hidden = {int(x) for x in (hidden_sids or [])}
    if default_speaker in hidden:
        raise VoicePackError("default speaker must not be a hidden sid")
    if len(hidden) >= speaker_count:
        raise VoicePackError("hidden sids leave no speaker in the catalog")
    speakers: list[dict[str, Any]] = []
    for sid in range(speaker_count):
        if sid in hidden:
            continue
        item: dict[str, Any] = {"sid": sid, "analysisTags": []}
        if names:
            item["sourceSpeakerId"] = names[sid]
        if len(langs) == 1:
            item["language"] = langs[0]
        elif langs:
            item["languages"] = list(langs)
        speakers.append(item)
    catalog: dict[str, Any] = {
        "schemaVersion": 1,
        "catalogId": catalog_id,
        "modelProfile": profile,
        "language": language,
        "speakerCount": speaker_count,
        "defaultSpeaker": default_speaker,
        "speakers": speakers,
    }
    return {k: v for k, v in catalog.items() if v is not None}


def read_speaker_names(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_catalog(path: Path, catalog: dict[str, Any]) -> None:
    write_json(path, catalog)
