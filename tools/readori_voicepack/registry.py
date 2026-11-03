"""registry/models.yaml loading, schema validation and the license gate."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import catalog as catalog_mod
from .common import (
    APP_SUPPORTED_TYPES,
    ID_RE,
    SHA256_RE,
    VoicePackError,
    is_plain_int,
    is_todo,
    safe_relative_path,
)
from .lexicon_fill import LEXICON_FILL_VALUES

# Licenses that may be published. CC-BY-* additionally require an attribution text.
ALLOWED_SPDX = (
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC0-1.0",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
)
ATTRIBUTION_REQUIRED_SPDX = ("CC-BY-4.0", "CC-BY-SA-4.0")
# Training-data licenses that may appear on top of the model licenses above.
DATASET_ALLOWED_SPDX = ALLOWED_SPDX + ("CC-BY-3.0", "Unlicense")
# Copyleft licenses accepted ONLY for components with role=data (e.g. espeak-ng-data). Such a
# component ships as separate data files together with its full license text and source link.
COPYLEFT_DATA_SPDX = ("GPL-3.0-or-later", "GPL-3.0-only")
COMPONENT_ROLES = ("data", "code")
URL_RE = re.compile(r"https://[^\s)\]>\"']+")

STATUSES = ("candidate", "approved", "community", "excluded")
# Non-commercial / research-only wording in a license or dataset spdx text.
NC_SPDX_RE = re.compile(r"(^|[-_ ])NC([-_ ]|$)|non-?commercial|research", re.IGNORECASE)
KNOWN_TYPES = ("vits", "kokoro", "matcha", "kitten", "zipvoice", "pocket", "supertonic", "other")
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
VERSION_RE = re.compile(r"^\d+(\.\d+){1,2}$")
DISPLAY_LANGS = ("en", "zh-Hans", "zh-Hant")

PRESET_PATH_KEYS = ("model", "tokens", "lexicon", "dataDir", "dictDir", "voices", "speakerFile")
PRESET_LIST_KEYS = ("lexicons", "ruleFsts", "ruleFars")
PRESET_KEYS = frozenset(
    PRESET_PATH_KEYS
    + PRESET_LIST_KEYS
    + (
        "officialBilingualLexicons",
        "speakerCount",
        "defaultSpeaker",
        "profile",
        "language",
        "exclude",
        "sampleText",
        "sampleRate",  # informational only, never copied into the manifest
        "lexiconFill",  # optional lexicon post-processing, see lexicon_fill.py
    )
)

PINNED_PLACEHOLDER = "TODO"


@dataclass
class Registry:
    path: Path
    root: Path  # repository root (parent of the registry/ directory)
    doc: dict[str, Any]
    models: list[dict[str, Any]] = field(default_factory=list)

    def by_id(self, model_id: str) -> dict[str, Any]:
        for entry in self.models:
            if entry["id"] == model_id:
                return entry
        raise VoicePackError(f"unknown model id: {model_id}")

    def resolve(self, relative: str) -> Path:
        return self.root / relative


# --------------------------------------------------------------------------- schema


def _err(errors: list[str], where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def _is_tri(value: Any) -> bool:
    return value is True or value is False or value == "unknown"


def _is_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def validate_entry_schema(entry: Any, index: int) -> list[str]:
    errors: list[str] = []
    where = f"models[{index}]"
    if not isinstance(entry, dict):
        return [f"{where}: expected mapping"]
    where = f"models[{index}]({entry.get('id', '?')})"

    model_id = entry.get("id")
    if not isinstance(model_id, str) or not ID_RE.match(model_id) or len(model_id) > 64:
        _err(errors, where, "id must match [a-z0-9]+(-[a-z0-9]+)* and be <= 64 chars")

    display = entry.get("displayName")
    if not isinstance(display, dict):
        _err(errors, where, "displayName must be a mapping with en, zh-Hans, zh-Hant")
    else:
        for lang in DISPLAY_LANGS:
            if not _is_str(display.get(lang)):
                _err(errors, where, f"displayName.{lang} must be a non-empty string")

    languages = entry.get("languages")
    if not isinstance(languages, list) or not languages:
        _err(errors, where, "languages must be a non-empty list of BCP-47 tags")
    else:
        for tag in languages:
            if not isinstance(tag, str) or not LANGUAGE_RE.match(tag):
                _err(errors, where, f"invalid language tag {tag!r}")

    model_type = entry.get("type")
    if not isinstance(model_type, str) or model_type not in KNOWN_TYPES:
        _err(errors, where, f"type must be one of {', '.join(KNOWN_TYPES)}")
    app_supported = entry.get("appSupported", model_type in APP_SUPPORTED_TYPES)
    if not isinstance(app_supported, bool):
        _err(errors, where, "appSupported must be boolean")
    elif app_supported and model_type not in APP_SUPPORTED_TYPES:
        _err(errors, where, f"type {model_type!r} is not supported by the app; appSupported must be false")

    pack_version = entry.get("packVersion", 1)
    if not is_plain_int(pack_version) or pack_version < 1:
        _err(errors, where, "packVersion must be an integer >= 1")

    status = entry.get("status")
    if status not in STATUSES:
        _err(errors, where, f"status must be one of {', '.join(STATUSES)}")
    if status == "excluded" and not _is_str(entry.get("excludedReason")):
        _err(errors, where, "excluded entries need excludedReason")
    if status == "community" and not _is_str(entry.get("communityNote")):
        _err(
            errors,
            where,
            "community entries need communityNote (why it is community; licence not verified)",
        )
    game_flag = entry.get("gameCharacterVoice")
    if game_flag is not None and not isinstance(game_flag, bool):
        _err(errors, where, "gameCharacterVoice must be boolean")

    priority = entry.get("priority")
    if priority is not None and not (is_plain_int(priority) and 1 <= priority <= 3):
        _err(errors, where, "priority must be an integer 1..3")
    upstream_count = entry.get("upstreamSpeakerCount")
    if upstream_count is not None and not (is_plain_int(upstream_count) and upstream_count > 0):
        _err(errors, where, "upstreamSpeakerCount must be a positive integer")
    hints = entry.get("catalogHints")
    if hints is not None:
        _validate_catalog_hints(hints, where, errors)
    for key in ("notes", "excludedReason", "communityNote"):
        if entry.get(key) is not None and not isinstance(entry[key], str):
            _err(errors, where, f"{key} must be a string")

    min_app = entry.get("minAppVersion")
    if not isinstance(min_app, str) or not (is_todo(min_app) or VERSION_RE.match(min_app)):
        _err(errors, where, "minAppVersion must be 'x.y[.z]' or TODO")

    _validate_upstream(entry.get("upstream"), where, errors)
    _validate_license(entry.get("license"), where, errors)
    _validate_preset(entry.get("preset"), where, errors)
    _cross_check_hints(entry, where, errors)

    catalog_path = entry.get("voiceCatalog")
    if catalog_path is not None and (
        not isinstance(catalog_path, str) or safe_relative_path(catalog_path) != catalog_path
    ):
        _err(errors, where, "voiceCatalog must be a safe repository-relative path")
    return errors


def _validate_catalog_hints(hints: Any, where: str, errors: list[str]) -> None:
    if not isinstance(hints, dict):
        _err(errors, where, "catalogHints must be a mapping")
        return
    unknown = sorted(set(hints) - {"hiddenSids", "speakerNames"})
    if unknown:
        _err(errors, where, f"unknown catalogHints keys: {', '.join(unknown)}")
    hidden = hints.get("hiddenSids")
    if hidden is not None and (
        not isinstance(hidden, list) or any(not (is_plain_int(v) and v >= 0) for v in hidden)
    ):
        _err(errors, where, "catalogHints.hiddenSids must be a list of non-negative integers")
    names = hints.get("speakerNames")
    if names is not None and (not isinstance(names, list) or any(not _is_str(v) for v in names)):
        _err(errors, where, "catalogHints.speakerNames must be a list of non-empty strings (index = sid)")


def _cross_check_hints(entry: dict[str, Any], where: str, errors: list[str]) -> None:
    hints = entry.get("catalogHints")
    preset = entry.get("preset")
    if not isinstance(hints, dict) or not isinstance(preset, dict):
        return
    count = preset.get("speakerCount")
    if not is_plain_int(count):
        return
    names = hints.get("speakerNames")
    if isinstance(names, list) and len(names) != count:
        _err(errors, where, f"catalogHints.speakerNames has {len(names)} names, speakerCount is {count}")
    hidden = hints.get("hiddenSids")
    if isinstance(hidden, list) and all(is_plain_int(v) for v in hidden):
        if any(v >= count for v in hidden):
            _err(errors, where, "catalogHints.hiddenSids must be < preset.speakerCount")
        if len(set(hidden)) >= count:
            _err(errors, where, "catalogHints.hiddenSids hides every speaker")
        default = preset.get("defaultSpeaker", 0)
        if default in hidden:
            _err(errors, where, "preset.defaultSpeaker must not be in catalogHints.hiddenSids")


def evidence_items(lic: dict[str, Any]) -> list[Any]:
    evidence = lic.get("evidence")
    if isinstance(evidence, list):
        return evidence
    return [evidence] if evidence is not None else []


def evidence_urls(lic: dict[str, Any]) -> list[str]:
    """https URLs found in ``license.evidence`` (string, list of strings or list of mappings)."""
    urls: list[str] = []
    for item in evidence_items(lic):
        if isinstance(item, dict):
            candidates = [item.get("url")]
        elif isinstance(item, str):
            candidates = URL_RE.findall(item)
        else:
            candidates = []
        urls.extend(c for c in candidates if isinstance(c, str) and c.startswith("https://"))
    return urls


def _validate_upstream(upstream: Any, where: str, errors: list[str]) -> None:
    if not isinstance(upstream, dict):
        _err(errors, where, "upstream must be a mapping")
        return
    url = upstream.get("url")
    if not isinstance(url, str) or not (is_todo(url) or url.startswith("https://")):
        _err(errors, where, "upstream.url must be an https URL or TODO")
    sha = upstream.get("sha256")
    if not isinstance(sha, str) or not (is_todo(sha) or SHA256_RE.match(sha)):
        _err(errors, where, "upstream.sha256 must be 64 lowercase hex chars or TODO")
    size = upstream.get("bytes")
    if not (is_todo(size) or (is_plain_int(size) and size > 0)):
        _err(errors, where, "upstream.bytes must be a positive integer or TODO")
    pinned_from = upstream.get("pinnedFrom")
    if pinned_from is not None and pinned_from not in ("github-digest", "checksum-txt", "manual"):
        _err(errors, where, "upstream.pinnedFrom must be github-digest, checksum-txt or manual")
    homepage = upstream.get("homepage")
    if homepage is not None and not (isinstance(homepage, str) and homepage.startswith("https://")):
        _err(errors, where, "upstream.homepage must be an https URL")


def _validate_license(lic: Any, where: str, errors: list[str]) -> None:
    if not isinstance(lic, dict):
        _err(errors, where, "license must be a mapping")
        return
    for key in ("spdx", "url"):
        if not isinstance(lic.get(key), str) or not lic[key].strip():
            _err(errors, where, f"license.{key} must be a non-empty string (or TODO)")
    evidence = lic.get("evidence")
    if isinstance(evidence, list):
        if not evidence or any(
            not (_is_str(i) or (isinstance(i, dict) and _is_str(i.get("url")))) for i in evidence
        ):
            _err(errors, where, "license.evidence list items must be strings or mappings with url")
    elif not _is_str(evidence):
        _err(errors, where, "license.evidence must be a non-empty string, a list, or TODO")
    _validate_components(lic.get("components"), where, errors)
    for key in ("commercialUse", "redistribution"):
        if not _is_tri(lic.get(key)):
            _err(errors, where, f"license.{key} must be true, false or 'unknown'")
    for key in ("attribution", "author", "textFile"):
        if key in lic and lic[key] is not None and not isinstance(lic[key], str):
            _err(errors, where, f"license.{key} must be a string")
    text_file = lic.get("textFile")
    if isinstance(text_file, str) and safe_relative_path(text_file) != text_file:
        _err(errors, where, "license.textFile must be a safe repository-relative path")
    dataset = lic.get("dataset")
    if dataset is not None:
        if not isinstance(dataset, dict):
            _err(errors, where, "license.dataset must be a mapping")
        else:
            for key in ("name", "spdx"):
                if not isinstance(dataset.get(key), str) or not dataset[key].strip():
                    _err(errors, where, f"license.dataset.{key} must be a non-empty string")
            if not _is_tri(dataset.get("commercialUse")):
                _err(errors, where, "license.dataset.commercialUse must be true, false or 'unknown'")
            parts = dataset.get("parts")
            if parts is not None:
                if not isinstance(parts, list) or not parts:
                    _err(errors, where, "license.dataset.parts must be a non-empty list")
                else:
                    for part in parts:
                        if not (
                            isinstance(part, dict) and _is_str(part.get("name")) and _is_str(part.get("spdx"))
                        ):
                            _err(errors, where, "license.dataset.parts items need name and spdx")


def _validate_components(components: Any, where: str, errors: list[str]) -> None:
    if components is None:
        return
    if not isinstance(components, list):
        _err(errors, where, "license.components must be a list")
        return
    for i, comp in enumerate(components):
        label = f"license.components[{i}]"
        if not isinstance(comp, dict):
            _err(errors, where, f"{label} must be a mapping")
            continue
        for key in ("name", "spdx", "url", "sourceURL"):
            if not _is_str(comp.get(key)):
                _err(errors, where, f"{label}.{key} must be a non-empty string")
        if comp.get("role") not in COMPONENT_ROLES:
            _err(errors, where, f"{label}.role must be one of {', '.join(COMPONENT_ROLES)}")
        for key in ("url", "sourceURL"):
            value = comp.get(key)
            if isinstance(value, str) and not value.startswith("https://"):
                _err(errors, where, f"{label}.{key} must be an https URL")


def _validate_preset(preset: Any, where: str, errors: list[str]) -> None:
    if not isinstance(preset, dict):
        _err(errors, where, "preset must be a mapping")
        return
    unknown = sorted(set(preset) - PRESET_KEYS)
    if unknown:
        _err(errors, where, f"unknown preset keys: {', '.join(unknown)}")
    for key in PRESET_PATH_KEYS:
        if key in preset and preset[key] is not None:
            value = preset[key]
            if not isinstance(value, str) or not (is_todo(value) or safe_relative_path(value) == value):
                _err(errors, where, f"preset.{key} must be a normalised relative path, TODO or null")
    for key in PRESET_LIST_KEYS:
        if key in preset and preset[key] is not None:
            value = preset[key]
            if not isinstance(value, list) or any(
                not isinstance(v, str) or not (is_todo(v) or safe_relative_path(v) == v) for v in value
            ):
                _err(errors, where, f"preset.{key} must be a list of normalised relative paths")
    count = preset.get("speakerCount")
    if count is not None and not (is_plain_int(count) and 1 <= count <= 512):
        _err(errors, where, "preset.speakerCount must be an integer in 1..512")
    default = preset.get("defaultSpeaker")
    if default is not None:
        if not is_plain_int(default) or default < 0:
            _err(errors, where, "preset.defaultSpeaker must be a non-negative integer")
        elif is_plain_int(count) and default >= count:
            _err(errors, where, "preset.defaultSpeaker must be < preset.speakerCount")
    for key in ("profile", "language", "sampleText"):
        if key in preset and preset[key] is not None and not isinstance(preset[key], str):
            _err(errors, where, f"preset.{key} must be a string")
    if "exclude" in preset and (
        not isinstance(preset["exclude"], list) or any(not isinstance(v, str) for v in preset["exclude"])
    ):
        _err(errors, where, "preset.exclude must be a list of glob strings")
    if "officialBilingualLexicons" in preset and not isinstance(preset["officialBilingualLexicons"], bool):
        _err(errors, where, "preset.officialBilingualLexicons must be boolean")
    if "lexiconFill" in preset and preset["lexiconFill"] not in LEXICON_FILL_VALUES:
        _err(
            errors,
            where,
            f"preset.lexiconFill must be one of: {', '.join(LEXICON_FILL_VALUES)}",
        )


def validate_registry_doc(doc: Any) -> list[str]:
    if not isinstance(doc, dict):
        return ["registry: top level must be a mapping"]
    errors: list[str] = []
    if doc.get("schemaVersion") != 1:
        errors.append("registry: schemaVersion must be 1")
    models = doc.get("models")
    if not isinstance(models, list) or not models:
        errors.append("registry: models must be a non-empty list")
        return errors
    seen: set[str] = set()
    for index, entry in enumerate(models):
        errors.extend(validate_entry_schema(entry, index))
        model_id = entry.get("id") if isinstance(entry, dict) else None
        if isinstance(model_id, str):
            if model_id in seen:
                errors.append(f"registry: duplicate id {model_id!r}")
            seen.add(model_id)
    return errors


def load_registry(path: Path, root: Path | None = None) -> Registry:
    path = Path(path)
    if not path.is_file():
        raise VoicePackError(f"registry not found: {path}")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise VoicePackError(f"registry is not valid YAML: {exc}") from exc
    errors = validate_registry_doc(doc)
    if errors:
        raise VoicePackError("registry schema errors:\n  " + "\n  ".join(errors))
    repo_root = Path(root) if root is not None else path.resolve().parent.parent
    return Registry(path=path, root=repo_root, doc=doc, models=list(doc["models"]))


# --------------------------------------------------------------------------- gate


def is_pinned(entry: dict[str, Any]) -> bool:
    upstream = entry["upstream"]
    return bool(
        isinstance(upstream.get("sha256"), str)
        and SHA256_RE.match(upstream["sha256"])
        and is_plain_int(upstream.get("bytes"))
    )


def app_supported(entry: dict[str, Any]) -> bool:
    return bool(entry.get("appSupported", entry["type"] in APP_SUPPORTED_TYPES))


def _component_reasons(lic: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for comp in lic.get("components") or []:
        name = comp.get("name", "?")
        spdx = comp.get("spdx") if isinstance(comp.get("spdx"), str) else ""
        role = comp.get("role")
        if not spdx or is_todo(spdx) or spdx.lower() in ("unknown", "unlicensed", "none"):
            reasons.append(f"component '{name}' license is unknown")
        elif NC_SPDX_RE.search(spdx):
            reasons.append(f"component '{name}' license '{spdx}' is non-commercial / research-only")
        elif spdx in COPYLEFT_DATA_SPDX:
            if role != "data":
                reasons.append(
                    f"component '{name}': {spdx} is only accepted for role=data components (got {role!r})"
                )
        elif spdx not in ALLOWED_SPDX:
            reasons.append(f"component '{name}' license '{spdx}' is not in the allow list")
        for key in ("url", "sourceURL"):
            value = comp.get(key)
            if not isinstance(value, str) or is_todo(value) or not value.startswith("https://"):
                reasons.append(f"component '{name}' {key} must be an https URL")
    return reasons


def _dataset_reasons(dataset: Any) -> list[str]:
    if not isinstance(dataset, dict):
        return ["license.dataset (training-data license) is not recorded"]
    reasons: list[str] = []
    d_spdx = dataset.get("spdx")
    commercial_ok = dataset.get("commercialUse") is True
    if d_spdx in ("none", "undisclosed"):
        if not _is_str(dataset.get("note")):
            reasons.append(f"license.dataset.spdx '{d_spdx}' requires a note")
        if d_spdx == "undisclosed":
            commercial_ok = dataset.get("commercialUse") in (True, "unknown")
    elif d_spdx == "mixed":
        parts = dataset.get("parts")
        if not isinstance(parts, list) or not parts:
            reasons.append("license.dataset.spdx 'mixed' requires parts")
        else:
            for part in parts:
                p_spdx = part.get("spdx") if isinstance(part, dict) else None
                if p_spdx not in DATASET_ALLOWED_SPDX and p_spdx != "undisclosed":
                    reasons.append(f"dataset part license '{p_spdx}' is not in the allow list")
        if not _is_str(dataset.get("note")):
            reasons.append("license.dataset.spdx 'mixed' requires a note")
    elif d_spdx not in DATASET_ALLOWED_SPDX:
        reasons.append(f"dataset license '{d_spdx}' is not in the allow list")
    if not commercial_ok:
        reasons.append("license.dataset.commercialUse must be true")
    return reasons


def _evaluate_community(
    entry: dict[str, Any], *, require_pinned: bool, for_publish: bool
) -> list[str]:
    """Gate for the community tier (licence UNKNOWN is accepted, known-prohibited is not).

    Community packs are published as GitHub Release assets only. What is still refused: a
    licence or training-data licence that is known non-commercial / research-only, an explicit
    commercialUse / redistribution ``false``, and game-character voices.
    """
    reasons: list[str] = []
    if entry.get("gameCharacterVoice") is True:
        reasons.append("game-character voices are never accepted (not even in the community tier)")
    if not app_supported(entry):
        reasons.append(f"type '{entry.get('type')}' is not supported by the app (vits/kokoro only)")

    lic = entry.get("license") or {}
    if lic.get("commercialUse") is False:
        reasons.append("license.commercialUse is False: known non-commercial models are never accepted")
    if lic.get("redistribution") is False:
        reasons.append("license.redistribution is False: models that forbid redistribution are never accepted")
    spdx = lic.get("spdx")
    spdx_text = spdx.strip() if isinstance(spdx, str) else ""
    if spdx_text and NC_SPDX_RE.search(spdx_text):
        reasons.append(f"license '{spdx_text}' is non-commercial / research-only")
    dataset = lic.get("dataset")
    if isinstance(dataset, dict):
        if dataset.get("commercialUse") is False:
            reasons.append("license.dataset.commercialUse is False: non-commercial training data")
        d_spdx = dataset.get("spdx")
        if isinstance(d_spdx, str) and NC_SPDX_RE.search(d_spdx):
            reasons.append(f"dataset license '{d_spdx}' is non-commercial / research-only")
        for part in dataset.get("parts") or []:
            p_spdx = part.get("spdx") if isinstance(part, dict) else None
            if isinstance(p_spdx, str) and NC_SPDX_RE.search(p_spdx):
                reasons.append(f"dataset part license '{p_spdx}' is non-commercial / research-only")
    reasons.extend(_component_reasons(lic))

    upstream = entry.get("upstream") or {}
    up_url = upstream.get("url")
    if not isinstance(up_url, str) or is_todo(up_url) or not up_url.startswith("https://"):
        reasons.append("upstream.url must be an https URL")
    if for_publish and is_todo(entry.get("minAppVersion")):
        reasons.append("minAppVersion is TODO (required for publishing)")
    preset = entry.get("preset") or {}
    if not is_plain_int(preset.get("speakerCount")):
        reasons.append("preset.speakerCount must be set for community entries")
    if require_pinned and not is_pinned(entry):
        reasons.append("upstream.sha256 / upstream.bytes are not pinned")
    return reasons


def evaluate_gate(
    entry: dict[str, Any], *, require_pinned: bool = False, for_publish: bool = False
) -> list[str]:
    """Return the reasons why ``entry`` may not be built (empty list means buildable).

    ``for_publish`` additionally requires a concrete ``minAppVersion`` (a build does not).
    """
    status = entry.get("status")
    if status == "community":
        return _evaluate_community(entry, require_pinned=require_pinned, for_publish=for_publish)
    reasons: list[str] = []
    if status != "approved":
        reasons.append(f"status is '{status}', must be 'approved' (or 'community' for the community tier)")
    if entry.get("gameCharacterVoice") is True:
        reasons.append("game-character voices are never accepted")
    if not app_supported(entry):
        reasons.append(f"type '{entry.get('type')}' is not supported by the app (vits/kokoro only)")

    lic = entry.get("license") or {}
    spdx = lic.get("spdx")
    spdx_text = spdx.strip() if isinstance(spdx, str) else ""
    if not spdx_text or is_todo(spdx_text) or spdx_text.lower() in ("unknown", "unlicensed", "none"):
        reasons.append("license.spdx is unknown")
    elif NC_SPDX_RE.search(spdx_text):
        reasons.append(f"license '{spdx_text}' is non-commercial / research-only")
    elif spdx_text not in ALLOWED_SPDX:
        reasons.append(f"license '{spdx_text}' is not in the allow list ({', '.join(ALLOWED_SPDX)})")

    if lic.get("commercialUse") is not True:
        reasons.append(f"license.commercialUse is {lic.get('commercialUse')!r}, must be true")
    if lic.get("redistribution") is not True:
        reasons.append(f"license.redistribution is {lic.get('redistribution')!r}, must be true")

    if any(is_todo(item) for item in evidence_items(lic)):
        reasons.append("license.evidence is TODO")
    elif not evidence_urls(lic):
        reasons.append("license.evidence must contain at least one https link")
    url = lic.get("url")
    if not isinstance(url, str) or is_todo(url) or not url.startswith("https://"):
        reasons.append("license.url must be an https URL")
    if spdx_text in ATTRIBUTION_REQUIRED_SPDX and not _is_str(lic.get("attribution")):
        reasons.append(f"{spdx_text} requires license.attribution text")

    reasons.extend(_dataset_reasons(lic.get("dataset")))
    reasons.extend(_component_reasons(lic))

    upstream = entry.get("upstream") or {}
    up_url = upstream.get("url")
    if not isinstance(up_url, str) or is_todo(up_url) or not up_url.startswith("https://"):
        reasons.append("upstream.url must be an https URL")
    if for_publish and is_todo(entry.get("minAppVersion")):
        reasons.append("minAppVersion is TODO (required for publishing)")
    preset = entry.get("preset") or {}
    if not is_plain_int(preset.get("speakerCount")):
        reasons.append("preset.speakerCount must be set for approved entries")
    if require_pinned and not is_pinned(entry):
        reasons.append("upstream.sha256 / upstream.bytes are not pinned")
    return reasons


def check_voice_catalog(registry: Registry, entry: dict[str, Any]) -> list[str]:
    """Verify the repository catalog referenced by an entry decodes and is consistent."""
    rel = entry.get("voiceCatalog")
    if rel is None:
        return []
    path = registry.resolve(rel)
    try:
        catalog = catalog_mod.load_catalog_file(path)
    except VoicePackError as exc:
        return [str(exc)]
    preset = entry["preset"]
    count = preset.get("speakerCount")
    if not is_plain_int(count):
        return []
    default = preset.get("defaultSpeaker", 0)
    return catalog_mod.semantic_problems(catalog, count, default, strict=True)


# --------------------------------------------------------------------------- selection


@dataclass
class GateResult:
    entry: dict[str, Any]
    reasons: list[str]
    catalog_problems: list[str]

    @property
    def buildable(self) -> bool:
        return not self.reasons and not self.catalog_problems


def evaluate_all(
    registry: Registry, *, require_pinned: bool = False, for_publish: bool = False
) -> list[GateResult]:
    return [
        GateResult(
            entry=entry,
            reasons=evaluate_gate(entry, require_pinned=require_pinned, for_publish=for_publish),
            catalog_problems=check_voice_catalog(registry, entry),
        )
        for entry in registry.models
    ]


SELECT_ID_RE = re.compile(r"^[a-z0-9-]+$")


def select_packs(results: list[GateResult], spec: str) -> list[GateResult]:
    """Resolve ``all-approved`` / ``all-community`` or a comma-separated id list.

    ``all-approved`` returns only buildable status=approved entries, ``all-community`` only
    buildable status=community entries. An explicit id list may mix both tiers.
    """
    spec = spec.strip()
    if spec == "all-approved":
        return [r for r in results if r.buildable and r.entry.get("status") == "approved"]
    if spec == "all-community":
        return [r for r in results if r.buildable and r.entry.get("status") == "community"]
    ids = [part.strip() for part in spec.split(",") if part.strip()]
    if not ids:
        raise VoicePackError("empty pack selection")
    by_id = {r.entry["id"]: r for r in results}
    selected: list[GateResult] = []
    for pack_id in ids:
        if not SELECT_ID_RE.match(pack_id):
            raise VoicePackError(f"invalid pack id in selection: {pack_id!r}")
        result = by_id.get(pack_id)
        if result is None:
            raise VoicePackError(f"unknown pack id: {pack_id}")
        if not result.buildable:
            problems = "; ".join(result.reasons + result.catalog_problems)
            raise VoicePackError(f"pack {pack_id} is blocked by the license gate: {problems}")
        if result not in selected:
            selected.append(result)
    return selected


def matrix_for(selected: list[GateResult]) -> dict[str, Any]:
    return {
        "include": [
            {
                "id": r.entry["id"],
                "packVersion": r.entry.get("packVersion", 1),
                "type": r.entry["type"],
            }
            for r in selected
        ]
    }


def require_buildable(
    registry: Registry, model_id: str, *, require_pinned: bool = False, for_publish: bool = False
) -> dict[str, Any]:
    """Gate used by fetch / build: raise unless the entry passes the license gate."""
    entry = registry.by_id(model_id)
    reasons = evaluate_gate(
        entry, require_pinned=require_pinned, for_publish=for_publish
    ) + check_voice_catalog(registry, entry)
    if reasons:
        raise VoicePackError(
            f"{model_id} is blocked by the license gate:\n  - " + "\n  - ".join(reasons)
        )
    return entry
