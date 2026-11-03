"""Validate a Readori voice pack the way the app importer does.

Rule sources (``TTSEnginePackageImporter.swift`` unless noted):

* archive limits           :131-137, :182, :260-276
* safe relative paths      :984-991
* manifest file checks     :733-794  (failure codes below reuse the app's names)
* model integrity          :798-821
* catalog normalisation    :856-883, ``SherpaVoiceCatalog.swift:259-270``
* Kokoro v1.1 special case :888-953

``policy=True`` adds checks that are not importer failures but that every curated Readori pack
must satisfy (license / attribution / integrity metadata declared, no engine-list look-alikes).
"""
from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import catalog as catalog_mod
from .archive import extract_raw
from .build import (
    ESPEAK_COPYING_NAME,
    ESPEAK_DATA_DIRNAME,
    ESPEAK_UPSTREAM_URL,
    GPL_TEXT_MARKERS,
    PLACEHOLDER_MARKER,
)
from .common import (
    APP_ENGINE_LIST_NAMES,
    APP_SUPPORTED_TYPES,
    ATTRIBUTION_NAME,
    CATALOG_NAME,
    MANIFEST_NAME,
    MAX_ARCHIVE_ENTRIES,
    MAX_CONFIG_BYTES,
    MAX_ZIP_BYTES,
    SHA256_RE,
    VoicePackError,
    is_manifest_path,
    is_plain_int,
    loads_strict,
    safe_relative_path,
    sha256_file,
)

# Keys that make TTSEngine.parseList(...) treat a JSON object as a network engine
# (TTSEngineParsing.swift:80-94). Compared case-insensitively without underscores.
_ENGINE_URL_KEYS = frozenset(
    {"url", "ttsurl", "endpoint", "apiurl", "requesturl", "baseurl", "host"}
)

_STR_FIELDS = (
    "dataDir",
    "lexicon",
    "voices",
    "language",
    "dictDir",
    "licenseFile",
    "sourceURL",
    "profile",
    "modelSHA256",
    "voiceCatalog",
    "voiceCatalogSHA256",
    "speakerFile",
)
_LIST_FIELDS = ("lexicons", "ruleFsts", "ruleFars")
_INT_FIELDS = ("speakerCount", "defaultSpeaker", "voiceCatalogVersion")

KOKORO_V11_MODEL_BYTES = 114_299_010


@dataclass
class Finding:
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass
class ValidationResult:
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    manifest: dict[str, Any] | None = None
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, message: str = "") -> None:
        self.errors.append(Finding(code, message or code))

    def warn(self, code: str, message: str = "") -> None:
        self.warnings.append(Finding(code, message or code))

    def codes(self) -> list[str]:
        return [f.code for f in self.errors]


# --------------------------------------------------------------------------- zip level


def validate_zip_container(path: Path, result: ValidationResult) -> bool:
    """Archive-level rules. Returns False when the ZIP cannot be inspected further."""
    size = path.stat().st_size
    result.info["zipBytes"] = size
    if size > MAX_ZIP_BYTES:
        result.error("file_too_large", f"ZIP is {size} bytes, limit {MAX_ZIP_BYTES}")
        return False
    with path.open("rb") as handle:
        magic = handle.read(4)
    if magic != b"PK\x03\x04":
        result.error("invalid_archive", "not a ZIP file (missing PK\\x03\\x04 magic)")
        return False
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        result.error("invalid_archive", str(exc))
        return False
    with zf:
        infos = zf.infolist()
        result.info["entries"] = len(infos)
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            result.error("unsafe_archive", f"{len(infos)} entries, limit {MAX_ARCHIVE_ENTRIES}")
            return False
        total = 0
        seen: dict[str, str] = {}
        ok = True
        for info in infos:
            rel = safe_relative_path(info.filename)
            if rel is None:
                result.error("unsafe_archive", f"unsafe entry path {info.filename!r}")
                ok = False
                continue
            total += info.file_size
            key = rel.lower()
            if key in seen and not info.is_dir():
                result.error("duplicate_path", f"{rel!r} collides with {seen[key]!r} (case-insensitive)")
            seen[key] = rel
        result.info["uncompressedBytes"] = total
        if total > MAX_ZIP_BYTES:
            result.error("file_too_large", f"uncompressed size {total} exceeds {MAX_ZIP_BYTES}")
            ok = False
        names = {safe_relative_path(i.filename) for i in infos}
        if MANIFEST_NAME not in names:
            nested = [n for n in names if n and n.rsplit("/", 1)[-1].lower() == MANIFEST_NAME]
            if nested:
                result.error(
                    "manifest_not_at_root",
                    f"{nested[0]!r}: manifest paths are resolved from the ZIP root; remove the wrapper folder",
                )
                ok = False
    return ok


def validate_zip(path: Path, *, policy: bool = True) -> ValidationResult:
    result = ValidationResult()
    if not validate_zip_container(path, result):
        return result
    with tempfile.TemporaryDirectory(prefix="readori-validate-") as tmp:
        root = Path(tmp) / "pack"
        try:
            extract_raw(
                path,
                root,
                max_total_bytes=MAX_ZIP_BYTES,
                max_entries=MAX_ARCHIVE_ENTRIES,
            )
        except VoicePackError as exc:
            result.error("unsafe_archive", str(exc))
            return result
        inner = validate_directory(root, policy=policy)
    result.errors.extend(inner.errors)
    result.warnings.extend(inner.warnings)
    result.manifest = inner.manifest
    result.info.update(inner.info)
    return result


def validate_target(path: Path, *, policy: bool = True) -> ValidationResult:
    path = Path(path)
    if path.is_dir():
        return validate_directory(path, policy=policy)
    if path.is_file():
        return validate_zip(path, policy=policy)
    result = ValidationResult()
    result.error("not_found", f"{path} does not exist")
    return result


# --------------------------------------------------------------------------- manifest


def _manifest_decode_problems(manifest: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    type_value = manifest.get("type")
    if type_value not in APP_SUPPORTED_TYPES:
        problems.append(f"type must be one of {', '.join(APP_SUPPORTED_TYPES)}, got {type_value!r}")
    for key in ("displayName", "model", "tokens"):
        if not isinstance(manifest.get(key), str):
            problems.append(f"{key}: required string missing")
    for key in _STR_FIELDS:
        if manifest.get(key) is not None and not isinstance(manifest[key], str):
            problems.append(f"{key}: expected string")
    for key in _LIST_FIELDS:
        value = manifest.get(key)
        if value is not None and (
            not isinstance(value, list) or not all(isinstance(x, str) for x in value)
        ):
            problems.append(f"{key}: expected array of strings")
    for key in _INT_FIELDS:
        if manifest.get(key) is not None and not is_plain_int(manifest[key]):
            problems.append(f"{key}: expected integer")
    size = manifest.get("modelBytes")
    if size is not None and not (is_plain_int(size) and size >= 0):
        problems.append("modelBytes: expected non-negative integer")
    return problems


def _normalize_key(key: str) -> str:
    return key.replace("_", "").lower()


def effective_counts(manifest: dict[str, Any], catalog: dict[str, Any] | None) -> tuple[int, int]:
    """``normalizedVoiceCatalogManifest`` (:856-883): effective speakerCount / defaultSpeaker."""
    if catalog is None:
        count = min(512, max(1, manifest.get("speakerCount") or 1))
        return count, manifest.get("defaultSpeaker") or 0
    inferred = manifest.get("speakerCount")
    if inferred is None:
        inferred = catalog.get("speakerCount")
    if inferred is None:
        inferred = max((s.get("sid", 0) for s in catalog.get("speakers", [])), default=0) + 1
    count = min(512, max(1, inferred))
    default = manifest.get("defaultSpeaker")
    if default is None:
        default = catalog.get("defaultSpeaker")
    default = min(max(0, default or 0), count - 1)
    return count, default


def _is_kokoro_v11(manifest: dict[str, Any], count: int) -> bool:
    if manifest.get("type") != "kokoro":
        return False
    profile = (manifest.get("profile") or "").lower()
    name = (manifest.get("displayName") or "").lower()
    return (
        "v1_1" in profile
        or count == 103
        or "kokoro int8" in name
        or manifest.get("modelBytes") == KOKORO_V11_MODEL_BYTES
    )


# --------------------------------------------------------------------------- directory


def validate_directory(root: Path, *, policy: bool = True) -> ValidationResult:
    result = ValidationResult()
    root = Path(root)
    root_resolved = root.resolve()

    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        result.error("manifest_missing", f"{MANIFEST_NAME} not found at the pack root")
        return result
    if manifest_path.stat().st_size > MAX_CONFIG_BYTES:
        result.error("manifest_too_large", "manifest exceeds 8 MiB")
        return result
    try:
        manifest = loads_strict(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        result.error("manifest_decode", f"invalid manifest JSON: {exc}")
        return result
    decode = _manifest_decode_problems(manifest)
    if decode:
        for problem in decode:
            result.error("manifest_decode", problem)
        return result
    result.manifest = manifest

    # Directory-level stats (mirrors the ZIP limits for an unpacked pack).
    files = [p for p in root.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    result.info["entries"] = len(files)
    result.info["uncompressedBytes"] = total
    if len(files) > MAX_ARCHIVE_ENTRIES:
        result.error("unsafe_archive", f"{len(files)} files, limit {MAX_ARCHIVE_ENTRIES}")
    if total > MAX_ZIP_BYTES:
        result.error("file_too_large", f"pack is {total} bytes, limit {MAX_ZIP_BYTES}")
    lowered: dict[str, str] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        if safe_relative_path(rel) != rel:
            result.error("unsafe_archive", f"unsafe file name {rel!r}")
        if path.is_symlink():
            result.error("unsafe_archive", f"symlink {rel!r}")
        if rel.lower() in lowered:
            result.error("duplicate_path", f"{rel!r} collides with {lowered[rel.lower()]!r}")
        lowered[rel.lower()] = rel

    def exists(relative: str | None, *, directory_allowed: bool = False) -> bool:
        if relative is None:
            return True
        if not is_manifest_path(relative):
            return False
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            return False
        if not resolved.exists():
            return False
        return True if directory_allowed else resolved.is_file()

    if not manifest["displayName"].strip():
        result.error("display_name", "displayName is empty")
    checks: list[tuple[str, bool]] = [
        ("model_missing", exists(manifest["model"])),
        ("tokens_missing", exists(manifest["tokens"])),
        ("data_dir_missing", exists(manifest.get("dataDir"), directory_allowed=True)),
        ("lexicon_missing", exists(manifest.get("lexicon"))),
        ("voices_missing", exists(manifest.get("voices"))),
        ("dict_dir_missing", exists(manifest.get("dictDir"), directory_allowed=True)),
        ("license_missing", exists(manifest.get("licenseFile"))),
        ("catalog_missing", exists(manifest.get("voiceCatalog"))),
        ("speaker_file_missing", exists(manifest.get("speakerFile"))),
    ]
    for code, passed in checks:
        if not passed:
            result.error(code, f"{code.removesuffix('_missing')} path in the manifest does not resolve")
    for code, key in (
        ("lexicon_list_missing", "lexicons"),
        ("rule_fst_missing", "ruleFsts"),
        ("rule_far_missing", "ruleFars"),
    ):
        for rel in manifest.get(key) or []:
            if not exists(rel):
                result.error(code, f"{key} entry {rel!r} does not resolve")
    version = manifest.get("voiceCatalogVersion")
    if version is not None and version < 1:
        result.error("catalog_version", "voiceCatalogVersion must be >= 1")

    catalog = _check_catalog(root, manifest, exists, result)

    count_declared = manifest.get("speakerCount")
    if count_declared is not None and not 1 <= count_declared <= 512:
        result.error("speaker_count", f"speakerCount {count_declared} outside 1...512")
    default_declared = manifest.get("defaultSpeaker")
    if default_declared is not None:
        bound = count_declared if count_declared is not None else 1
        if default_declared < 0 or default_declared >= bound:
            result.error("default_speaker", f"defaultSpeaker {default_declared} outside 0..{bound - 1}")

    _check_model_integrity(root, manifest, result)

    count, default = effective_counts(manifest, catalog)
    result.info["speakerCount"] = count
    result.info["defaultSpeaker"] = default
    if _is_kokoro_v11(manifest, count):
        if count != 103:
            result.error(
                "kokoro_v11_override",
                "the app treats this Kokoro pack as v1.1 (profile / name / size heuristic) and "
                "forces speakerCount=103; change profile and displayName or fix speakerCount",
            )
        if manifest.get("language") != "zh-CN,en-US" or default < 3:
            result.warn(
                "kokoro_v11_normalised",
                "the app rewrites language to zh-CN,en-US and defaultSpeaker to >= 3 for Kokoro v1.1",
            )

    if policy:
        _policy_checks(root, manifest, files, result)
    return result


def _check_catalog(
    root: Path,
    manifest: dict[str, Any],
    exists,
    result: ValidationResult,
) -> dict[str, Any] | None:
    catalog_path = manifest.get("voiceCatalog")
    if catalog_path is None:
        return None
    if not is_manifest_path(catalog_path) or not exists(catalog_path):
        return None  # catalog_missing already reported
    path = root / catalog_path
    if path.stat().st_size > MAX_CONFIG_BYTES:
        result.error("catalog_decode", "catalog exceeds 8 MiB")
        return None
    try:
        catalog = loads_strict(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        result.error("catalog_decode", f"invalid catalog JSON: {exc}")
        return None
    problems = catalog_mod.decode_problems(catalog)
    if problems:
        for problem in problems[:10]:
            result.error("catalog_decode", problem)
        return None
    count, default = effective_counts(manifest, catalog)
    for problem in catalog_mod.semantic_problems(catalog, count, default, strict=False):
        result.error("catalog_semantics", problem)
    expected = (manifest.get("voiceCatalogSHA256") or "").strip().lower()
    if expected:
        if not SHA256_RE.match(expected):
            result.error("catalog_hash_format", "voiceCatalogSHA256 is not 64 lowercase hex chars")
        elif sha256_file(path) != expected:
            result.error("catalog_hash", "voiceCatalogSHA256 does not match readori-voices.json")
    return catalog


def _check_model_integrity(root: Path, manifest: dict[str, Any], result: ValidationResult) -> None:
    model = manifest["model"]
    if not is_manifest_path(model):
        result.error("model_integrity", "model path is not a safe relative path")
        return
    path = root / model
    if not path.is_file():
        result.error("model_integrity", "model file missing")
        return
    size = path.stat().st_size
    result.info["modelBytes"] = size
    if size <= 0:
        result.error("model_integrity", "model file is empty")
        return
    declared = manifest.get("modelBytes")
    if declared is not None and declared != size:
        result.error("model_integrity", f"modelBytes {declared} != actual {size}")
    expected = (manifest.get("modelSHA256") or "").strip().lower()
    if expected:
        if not SHA256_RE.match(expected):
            result.error("model_integrity", "modelSHA256 is not 64 lowercase hex chars")
        elif sha256_file(path) != expected:
            result.error("model_integrity", "modelSHA256 does not match the model file")


def _espeak_policy_checks(root: Path, files: list[Path], result: ValidationResult) -> None:
    """Packs shipping espeak-ng-data (GPL-3.0-or-later data) must carry the GPL notice."""
    has_data = any(
        part.lower() == ESPEAK_DATA_DIRNAME
        for path in files
        for part in path.relative_to(root).parts[:-1]
    )
    if not has_data:
        return
    copying = root / ESPEAK_COPYING_NAME
    text = copying.read_text(encoding="utf-8", errors="replace") if copying.is_file() else ""
    if not all(marker in text for marker in GPL_TEXT_MARKERS) or PLACEHOLDER_MARKER in text:
        result.error(
            "espeak_notice_missing",
            f"{ESPEAK_COPYING_NAME} (GPL-3.0 text) is required next to espeak-ng-data",
        )
    attribution = root / ATTRIBUTION_NAME
    notice = attribution.read_text(encoding="utf-8", errors="replace") if attribution.is_file() else ""
    if ESPEAK_UPSTREAM_URL not in notice or "GPL" not in notice:
        result.error(
            "espeak_notice_missing",
            f"{ATTRIBUTION_NAME} must name {ESPEAK_UPSTREAM_URL} and carry the GPL statement",
        )


def _policy_checks(
    root: Path, manifest: dict[str, Any], files: list[Path], result: ValidationResult
) -> None:
    if manifest.get("modelBytes") is None or not manifest.get("modelSHA256"):
        result.error("integrity_undeclared", "curated packs must declare modelBytes and modelSHA256")
    if not manifest.get("licenseFile"):
        result.error("license_undeclared", "curated packs must declare licenseFile")
    if not (root / ATTRIBUTION_NAME).is_file():
        result.error("attribution_missing", f"{ATTRIBUTION_NAME} is required")
    if manifest.get("voiceCatalog"):
        if not manifest.get("voiceCatalogSHA256"):
            result.error("catalog_hash_undeclared", "voiceCatalogSHA256 must be declared")
    else:
        result.warn("catalog_undeclared", "no voice catalog; the app will list generic 'Voice N' entries")
    if manifest.get("type") == "kokoro":
        if not manifest.get("voices"):
            result.error("kokoro_voices_required", "kokoro packs need a voices file")
        if not manifest.get("dataDir"):
            result.error("kokoro_data_dir_required", "kokoro packs need an espeak-ng-data directory")
    _espeak_policy_checks(root, files, result)
    if "packId" not in manifest or "packVersion" not in manifest:
        result.warn("pack_identity_missing", "packId / packVersion not set (needed by 'pack' / 'index')")

    for key in manifest:
        if _normalize_key(key) in _ENGINE_URL_KEYS:
            result.error(
                "manifest_looks_like_engine",
                f"top-level key {key!r} makes the app parse the manifest as a network TTS engine",
            )
    for path in files:
        name = path.name.lower()
        if name in APP_ENGINE_LIST_NAMES:
            result.warn(
                "engine_list_name",
                f"{path.relative_to(root).as_posix()}: the app parses files with this name as "
                "engine lists before importing the model",
            )
    catalog_path = root / CATALOG_NAME
    if catalog_path.is_file() and catalog_path.stat().st_size <= MAX_CONFIG_BYTES:
        try:
            catalog = loads_strict(catalog_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            catalog = None
        if isinstance(catalog, dict):
            for key in catalog:
                if _normalize_key(key) in _ENGINE_URL_KEYS:
                    result.error(
                        "catalog_looks_like_engine",
                        f"catalog top-level key {key!r} looks like a network engine definition",
                    )
