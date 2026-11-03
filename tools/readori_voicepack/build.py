"""Build a Readori voice-pack directory from an upstream sherpa-onnx model archive.

Ported from ``build-readori-offline-tts-pack-v13.py``: same detection rules and manifest
field set, now driven by ``registry/models.yaml`` presets instead of hard-coded names.
The manifest field names match ``SherpaOnnxModelManifest`` in
``TTSEnginePackageImporter.swift:32-128`` exactly; ``packId`` / ``packVersion`` are extra keys
that the app's Codable decoder ignores.
"""
from __future__ import annotations

import fnmatch
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import catalog as catalog_mod
from .archive import copy_tree, extract_archive
from .common import (
    APP_SUPPORTED_TYPES,
    ATTRIBUTION_NAME,
    CATALOG_NAME,
    COMMUNITY_NOTICE,
    MANIFEST_NAME,
    VoicePackError,
    is_todo,
    safe_relative_path,
    sha256_file,
    write_json,
)
from .lexicon_fill import (
    LEXICON_FILL_OPENCC_T2S,
    apply_lexicon_fill,
    opencc_attribution_lines,
)
from .registry import COPYLEFT_DATA_SPDX, evidence_items

KNOWN_RULE_ORDER = [
    "phone.fst", "date.fst", "number.fst", "rule.fst", "new_heteronym.fst",
    # kokoro multi-lang tarballs; order from the sherpa-onnx docs example (date, phone, number)
    "date-zh.fst", "phone-zh.fst", "number-zh.fst",
]

# Files that are never useful on-device. Presets can add more via ``preset.exclude``.
DEFAULT_EXCLUDES = (
    "test_wavs/*",
    "*/test_wavs/*",
    "*.wav",
    "*.py",
    "*.sh",
    "*.ipynb",
    ".git*",
    "__MACOSX/*",
    ".DS_Store",
)

GENERATED_NAMES = (MANIFEST_NAME, CATALOG_NAME, ATTRIBUTION_NAME)

# espeak-ng-data is GPL-3.0-or-later data. Packs that contain it must declare a matching
# license component and ship the GPL text next to it as COPYING.espeak-ng.
ESPEAK_DATA_DIRNAME = "espeak-ng-data"
ESPEAK_COPYING_NAME = "COPYING.espeak-ng"
ESPEAK_UPSTREAM_URL = "https://github.com/espeak-ng/espeak-ng"
GPL_TEXT_REPO_PATH = "registry/license-texts/GPL-3.0.txt"
PLACEHOLDER_MARKER = "READORI-PLACEHOLDER"
GPL_TEXT_MARKERS = ("GNU GENERAL PUBLIC LICENSE", "Version 3, 29 June 2007")


@dataclass
class BuildResult:
    pack_id: str
    pack_version: int
    pack_dir: Path
    manifest: dict[str, Any]
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- detection


def rel_files(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.name not in GENERATED_NAMES
    )


def first_by_basename(paths: list[str], predicate) -> str | None:
    for rel in paths:
        if predicate(PurePosixPath(rel).name.lower()):
            return rel
    return None


def detect_model(paths: list[str]) -> str | None:
    for wanted in ("model.onnx", "vits.onnx", "model.int8.onnx"):
        hit = first_by_basename(paths, lambda name, w=wanted: name == w)
        if hit:
            return hit
    candidates = [
        p
        for p in paths
        if p.lower().endswith(".onnx")
        and not any(x in PurePosixPath(p).name.lower() for x in ("vocoder", "encoder", "decoder", "speaker"))
    ]
    return candidates[0] if candidates else None


def detect_tokens(paths: list[str]) -> str | None:
    return first_by_basename(paths, lambda n: n in ("tokens.txt", "tokens.json"))


def detect_voices(paths: list[str]) -> str | None:
    return first_by_basename(paths, lambda n: n in ("voices.bin", "voices.npy"))


def detect_speaker_file(paths: list[str]) -> str | None:
    return first_by_basename(paths, lambda n: n in ("speakers.txt", "speaker.txt", "speaker_ids.txt"))


def all_lexicons(paths: list[str]) -> list[str]:
    return sorted(
        p
        for p in paths
        if "lexicon" in PurePosixPath(p).name.lower()
        and PurePosixPath(p).name.lower().endswith((".txt", ".lex"))
    )


def choose_lexicons(paths: list[str], *, official_bilingual: bool = False) -> list[str]:
    found = all_lexicons(paths)
    if not found:
        return []
    if official_bilingual:
        us = first_by_basename(found, lambda n: n == "lexicon-us-en.txt")
        zh = first_by_basename(found, lambda n: n == "lexicon-zh.txt")
        if us and zh:
            return [us, zh]

    def key(rel: str) -> tuple[int, str]:
        name = PurePosixPath(rel).name.lower()
        if "us-en" in name:
            return (0, name)
        if "gb-en" in name:
            return (1, name)
        if "zh" in name:
            return (2, name)
        return (3, name)

    return sorted(found, key=key)


def detect_dir(paths: list[str], dirname: str) -> str | None:
    low = dirname.lower()
    for rel in paths:
        parts = rel.split("/")
        for i, part in enumerate(parts[:-1]):
            if part.lower() == low:
                return "/".join(parts[: i + 1])
    return None


def detect_license(paths: list[str]) -> str | None:
    return first_by_basename(paths, lambda n: n == "license" or n.startswith("license."))


# --------------------------------------------------------------------------- helpers


def _matches(rel: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(rel, pattern):
        return True
    return "/" not in pattern and fnmatch.fnmatchcase(PurePosixPath(rel).name, pattern)


def apply_excludes(root: Path, patterns: tuple[str, ...] | list[str]) -> list[str]:
    removed: list[str] = []
    for path in sorted(root.rglob("*"), reverse=True):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and any(_matches(rel, pat) for pat in patterns):
            path.unlink()
            removed.append(rel)
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()
    return sorted(removed)


def _preset_has(preset: dict[str, Any], key: str) -> bool:
    """A preset key counts as set unless it is missing or a TODO placeholder.

    TODO placeholders (research drafts) mean "auto-detect from the real archive".
    """
    if key not in preset:
        return False
    value = preset[key]
    if is_todo(value):
        return False
    if isinstance(value, list) and any(is_todo(v) for v in value):
        return False
    return True


def espeak_component(entry: dict[str, Any]) -> dict[str, Any] | None:
    for comp in (entry.get("license") or {}).get("components") or []:
        name = str(comp.get("name", "")).lower()
        if "espeak" in name and comp.get("role") == "data" and comp.get("spdx") in COPYLEFT_DATA_SPDX:
            return comp
    return None


def has_espeak_data(pack_dir: Path, paths: list[str]) -> bool:
    return any(
        part.lower() == ESPEAK_DATA_DIRNAME for rel in paths for part in rel.split("/")[:-1]
    ) or (pack_dir / ESPEAK_DATA_DIRNAME).is_dir()


def _looks_like_gpl3(text: str) -> bool:
    return PLACEHOLDER_MARKER not in text and all(marker in text for marker in GPL_TEXT_MARKERS)


def resolve_espeak_copying(pack_dir: Path, paths: list[str], repo_root: Path) -> tuple[str, str]:
    """Find the GPL-3.0 text for espeak-ng-data: upstream tarball first, then the repo copy.

    Returns ``(text, source)``; raises when neither holds a real GPL-3.0 text.
    """
    candidates = [
        rel
        for rel in paths
        if PurePosixPath(rel).name.upper() in ("COPYING", "COPYING.TXT", "LICENSE-GPL", "COPYING.GPL")
        and any(part.lower() == ESPEAK_DATA_DIRNAME for part in rel.split("/")[:-1] + [""])
    ]
    candidates += [rel for rel in paths if PurePosixPath(rel).name.upper() == "COPYING.ESPEAK-NG"]
    for rel in candidates:
        text = (pack_dir / rel).read_text(encoding="utf-8", errors="replace")
        if _looks_like_gpl3(text):
            return text, f"upstream:{rel}"
    repo_copy = repo_root / GPL_TEXT_REPO_PATH
    if repo_copy.is_file():
        text = repo_copy.read_text(encoding="utf-8", errors="replace")
        if _looks_like_gpl3(text):
            return text, f"repo:{GPL_TEXT_REPO_PATH}"
    raise VoicePackError(
        f"pack contains {ESPEAK_DATA_DIRNAME} (GPL-3.0-or-later data) but no GPL-3.0 text was found: "
        f"neither the upstream archive nor {GPL_TEXT_REPO_PATH} (missing or still a placeholder)"
    )


def _require_file(root: Path, rel: str | None, what: str) -> None:
    if rel is None:
        return
    if safe_relative_path(rel) != rel or not (root / rel).is_file():
        raise VoicePackError(f"preset {what} not found in upstream archive: {rel}")


def _require_dir(root: Path, rel: str | None, what: str) -> None:
    if rel is None:
        return
    if safe_relative_path(rel) != rel or not (root / rel).is_dir():
        raise VoicePackError(f"preset {what} directory not found in upstream archive: {rel}")


def espeak_attribution_lines() -> list[str]:
    """GPL statement for packs that contain espeak-ng-data (also used by self-built packs)."""
    return [
        "",
        "espeak-ng-data (GPL-3.0-or-later)",
        f"  This pack contains the espeak-ng-data directory from {ESPEAK_UPSTREAM_URL}.",
        "  espeak-ng-data is licensed under the GNU General Public License, version 3 or",
        "  (at your option) any later version. It is shipped here as separate, unmodified data",
        f"  files; the full license text is included as {ESPEAK_COPYING_NAME}. The corresponding",
        f"  source is available at {ESPEAK_UPSTREAM_URL}. The GPL applies to these data files only,",
        "  not to the model weights or to the Readori app.",
    ]


def write_espeak_copying(pack_dir: Path, paths: list[str], repo_root: Path) -> str:
    """Write ``COPYING.espeak-ng`` into the pack and return the note describing its source."""
    copying_text, copying_source = resolve_espeak_copying(pack_dir, paths, repo_root)
    (pack_dir / ESPEAK_COPYING_NAME).write_text(copying_text, encoding="utf-8", newline="\n")
    return f"{ESPEAK_COPYING_NAME} taken from {copying_source}"


def render_attribution(
    entry: dict[str, Any],
    *,
    pack_version: int,
    archive_sha256: str | None,
    license_file: str,
    has_espeak: bool = False,
    lexicon_fill: tuple[int, int] | None = None,
) -> str:
    lic = entry["license"]
    upstream = entry["upstream"]
    names = entry["displayName"]
    community = entry.get("status") == "community"
    lines: list[str] = []
    if community:
        lines += [COMMUNITY_NOTICE["en"], COMMUNITY_NOTICE["zh-Hans"], ""]
    lines += [
        f"Readori offline voice pack: {names['en']}",
        f"Pack id: {entry['id']}   Pack version: {pack_version}",
        "",
        "Model",
        f"  Upstream archive: {upstream['url']}",
        f"  Upstream archive SHA-256: {archive_sha256 or 'not recorded'}",
        f"  Source page: {upstream.get('homepage') or upstream['url']}",
    ]
    if lic.get("author"):
        lines.append(f"  Author / rights holder: {lic['author']}")
    if community:
        # Community tier: never state or imply a licence; only say it is not verified.
        lines += [
            "",
            "License",
            "  Licence: not verified (community tier)",
            f"  Source: {upstream.get('homepage') or upstream['url']}",
        ]
    else:
        lines += [
            "",
            "License",
            f"  Model license: {lic['spdx']}  ({lic['url']})",
        ]
        for item in evidence_items(lic):
            text = item.get("url") if isinstance(item, dict) else item
            lines.append(f"  Evidence: {text}")
    dataset = lic.get("dataset")
    if isinstance(dataset, dict):
        spdx = dataset.get("spdx")
        extra = f"  ({dataset['url']})" if dataset.get("url") else ""
        lines.append(f"  Training data: {dataset.get('name')} - {spdx}{extra}")
        for part in dataset.get("parts") or []:
            url = f"  ({part['url']})" if part.get("url") else ""
            lines.append(f"    - {part.get('name')}: {part.get('spdx')}{url}")
            if part.get("attribution"):
                lines.append(f"      {part['attribution']}")
        if dataset.get("note"):
            lines.append(f"  Training data note: {dataset['note']}")
    if lic.get("attribution"):
        lines += ["", "Attribution", f"  {lic['attribution']}"]
    for comp in lic.get("components") or []:
        lines += ["", f"Component: {comp.get('name')}"]
        lines.append(f"  License: {comp.get('spdx')}  ({comp.get('url')})")
        lines.append(f"  Source: {comp.get('sourceURL')}")
    if has_espeak:
        lines += espeak_attribution_lines()
    lines += [
        "",
        "Modifications by Readori",
        "  - Repackaged for the Readori app (ZIP layout, file selection).",
        "  - Added readori-tts-model.json and readori-voices.json (metadata only) and this file.",
        "  - Removed test audio and helper scripts.",
    ]
    if lexicon_fill is not None:
        lines += opencc_attribution_lines(*lexicon_fill)
    lines += [
        "  - Model weights and token files are unchanged from the upstream archive.",
        "",
    ]
    if community:
        lines += [
            f"{license_file} in this pack is the community notice (or the file shipped by the",
            "upstream archive). Readori has not verified the licence of the model or its training",
            "data. The model is provided as is, without warranty.",
            "",
        ]
    else:
        lines += [
            f"The upstream license text is included in this pack as {license_file}.",
            "The model is distributed under the terms of that license, not under the license of the",
            "Readori packaging tools.",
            "",
        ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- build


@dataclass
class Assembled:
    """Everything known about a pack directory once files, layout and catalog are in place.

    The license / attribution step and the manifest are the only parts that differ between
    registry builds (``build_pack``) and self-built packs (``local.build_local_pack``).
    """

    pack_id: str
    pack_version: int
    pack_dir: Path
    model_type: str
    paths: list[str]
    model: str
    tokens: str
    voices: str | None
    speaker_file: str | None
    data_dir: str | None
    dict_dir: str | None
    lexicons: list[str]
    lexicon: str | None
    rule_fsts: list[str]
    rule_fars: list[str]
    speaker_count: int
    default_speaker: int
    language: str
    profile: str | None
    catalog: dict[str, Any] | None
    notes: list[str] = field(default_factory=list)


def assemble_pack(
    entry: dict[str, Any],
    archive: Path,
    out_dir: Path,
    *,
    repo_root: Path,
    generate_catalog: bool = True,
) -> Assembled:
    """Extract the archive, detect the layout from the preset and write the voice catalog.

    ``entry`` needs ``id``, ``languages``, ``preset`` and ``type`` (``None`` = detect from the archive);
    optional: ``packVersion``, ``catalogHints``, ``voiceCatalog``. Licence handling is left to the caller.
    """
    model_type = entry.get("type")  # None: detect from the archive (self-built packs)
    if model_type is not None and model_type not in APP_SUPPORTED_TYPES:
        raise VoicePackError(f"type {model_type!r} is not supported by the app")
    preset = entry["preset"]
    pack_id = entry["id"]
    pack_version = int(entry.get("packVersion", 1))
    notes: list[str] = []

    pack_dir = out_dir / pack_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)

    with tempfile.TemporaryDirectory(prefix="readori-build-") as tmp:
        payload = extract_archive(archive, Path(tmp) / "extract")
        copy_tree(payload, pack_dir)

    # Upstream archives are untrusted: drop anything that would collide with generated files.
    for name in GENERATED_NAMES:
        for stray in list(pack_dir.rglob(name)):
            stray.unlink()
            notes.append(f"removed upstream file {stray.relative_to(pack_dir).as_posix()}")
    excludes = tuple(DEFAULT_EXCLUDES) + tuple(preset.get("exclude") or ())
    removed = apply_excludes(pack_dir, excludes)
    if removed:
        notes.append(f"excluded {len(removed)} files (test audio / scripts / preset.exclude)")

    paths = rel_files(pack_dir)
    lowered = [p.lower() for p in paths]
    if len(set(lowered)) != len(lowered):
        raise VoicePackError("upstream archive has file names differing only by case")

    if model_type is None:
        model_type = "kokoro" if detect_voices(paths) else "vits"
        notes.append(f"model type detected from the archive: {model_type}")

    # --- layout -------------------------------------------------------------
    model = preset["model"] if _preset_has(preset, "model") and preset["model"] else detect_model(paths)
    tokens = preset["tokens"] if _preset_has(preset, "tokens") and preset["tokens"] else detect_tokens(paths)
    if not model or not tokens:
        raise VoicePackError("model / tokens not found in upstream archive")
    _require_file(pack_dir, model, "model")
    _require_file(pack_dir, tokens, "tokens")

    voices = preset["voices"] if _preset_has(preset, "voices") else detect_voices(paths)
    speaker_file = (
        preset["speakerFile"] if _preset_has(preset, "speakerFile") else detect_speaker_file(paths)
    )
    data_dir = preset["dataDir"] if _preset_has(preset, "dataDir") else detect_dir(paths, ESPEAK_DATA_DIRNAME)
    dict_dir = preset["dictDir"] if _preset_has(preset, "dictDir") else detect_dir(paths, "dict")
    _require_file(pack_dir, voices, "voices")
    _require_file(pack_dir, speaker_file, "speakerFile")
    _require_dir(pack_dir, data_dir, "dataDir")
    _require_dir(pack_dir, dict_dir, "dictDir")

    if _preset_has(preset, "lexicons"):
        lexicons = list(preset["lexicons"] or [])
    else:
        lexicons = choose_lexicons(
            paths, official_bilingual=bool(preset.get("officialBilingualLexicons"))
        )
    for lex in lexicons:
        _require_file(pack_dir, lex, "lexicons")
    if _preset_has(preset, "lexicon"):
        lexicon = preset["lexicon"]
        _require_file(pack_dir, lexicon, "lexicon")
    else:
        lexicon = lexicons[0] if lexicons else None

    if _preset_has(preset, "ruleFsts"):
        rule_fsts = list(preset["ruleFsts"] or [])
    else:
        rule_fsts = []
        for wanted in KNOWN_RULE_ORDER:
            hit = first_by_basename(paths, lambda n, w=wanted: n == w)
            if hit and hit not in rule_fsts:
                rule_fsts.append(hit)
    if _preset_has(preset, "ruleFars"):
        rule_fars = list(preset["ruleFars"] or [])
    else:
        rule_fars = [p for p in paths if p.lower().endswith(".far")]
    for rel in rule_fsts + rule_fars:
        _require_file(pack_dir, rel, "ruleFsts/ruleFars")

    if model_type == "kokoro" and not voices:
        raise VoicePackError("kokoro packs require a voices file (voices.bin / voices.npy)")

    # --- speakers + catalog -----------------------------------------------------
    speaker_names: list[str] | None = None
    if speaker_file:
        speaker_names = catalog_mod.read_speaker_names(pack_dir / speaker_file)
    hints = entry.get("catalogHints") or {}
    hint_names = hints.get("speakerNames")
    hidden_sids = list(hints.get("hiddenSids") or [])

    catalog: dict[str, Any] | None = None
    catalog_rel = entry.get("voiceCatalog")
    if catalog_rel:
        catalog = catalog_mod.load_catalog_file(repo_root / catalog_rel)

    raw_count = preset.get("speakerCount")
    if raw_count is None and catalog is not None:
        raw_count = catalog.get("speakerCount")
    if raw_count is None and speaker_names:
        raw_count = len(speaker_names)
    speaker_count = int(raw_count if raw_count is not None else 1)
    default_speaker = int(preset.get("defaultSpeaker", (catalog or {}).get("defaultSpeaker", 0)))
    if not 1 <= speaker_count <= 512:
        raise VoicePackError("speakerCount must be between 1 and 512")
    if not 0 <= default_speaker < speaker_count:
        raise VoicePackError("defaultSpeaker must be within the speaker range")
    if speaker_names is not None and len(speaker_names) != speaker_count:
        raise VoicePackError(
            f"speaker count mismatch: manifest={speaker_count}, {speaker_file}={len(speaker_names)}"
        )
    if hint_names is not None:
        if len(hint_names) != speaker_count:
            raise VoicePackError(
                f"catalogHints.speakerNames has {len(hint_names)} names, expected {speaker_count}"
            )
        speaker_names = speaker_names or list(hint_names)

    language = preset.get("language") or ",".join(entry["languages"])
    profile = preset.get("profile") or (catalog or {}).get("modelProfile")

    if catalog is None and generate_catalog:
        catalog = catalog_mod.init_catalog(
            catalog_id=f"readori.{pack_id}",
            speaker_count=speaker_count,
            default_speaker=default_speaker,
            profile=profile,
            language=language,
            speaker_names=speaker_names,
            hidden_sids=hidden_sids,
        )
        notes.append("generated minimal voice catalog (facts only)")
        if hidden_sids:
            notes.append(f"catalog omits {len(hidden_sids)} hidden sids (speakerCount unchanged)")
    if catalog is not None:
        problems = catalog_mod.semantic_problems(catalog, speaker_count, default_speaker, strict=True)
        if problems:
            raise VoicePackError("voice catalog inconsistent with pack: " + "; ".join(problems))
        catalog_mod.write_catalog(pack_dir / CATALOG_NAME, catalog)

    return Assembled(
        pack_id=pack_id,
        pack_version=pack_version,
        pack_dir=pack_dir,
        model_type=model_type,
        paths=paths,
        model=model,
        tokens=tokens,
        voices=voices,
        speaker_file=speaker_file,
        data_dir=data_dir,
        dict_dir=dict_dir,
        lexicons=lexicons,
        lexicon=lexicon,
        rule_fsts=rule_fsts,
        rule_fars=rule_fars,
        speaker_count=speaker_count,
        default_speaker=default_speaker,
        language=language,
        profile=profile,
        catalog=catalog,
        notes=notes,
    )


def write_manifest(
    asm: Assembled, *, display_name: str, source_url: str, license_file: str
) -> dict[str, Any]:
    """Write ``readori-tts-model.json`` (field names mirror the app's SherpaOnnxModelManifest)."""
    pack_dir = asm.pack_dir
    model_path = pack_dir / asm.model
    manifest: dict[str, Any] = {
        "type": asm.model_type,
        "displayName": display_name,
        "model": asm.model,
        "tokens": asm.tokens,
        "dataDir": asm.data_dir,
        "lexicon": asm.lexicon,
        "lexicons": asm.lexicons or None,
        "voices": asm.voices,
        "language": asm.language,
        "speakerCount": asm.speaker_count,
        "defaultSpeaker": asm.default_speaker,
        "ruleFsts": asm.rule_fsts or None,
        "ruleFars": asm.rule_fars or None,
        "dictDir": asm.dict_dir,
        "licenseFile": license_file,
        "sourceURL": source_url,
        "profile": asm.profile,
        "modelBytes": model_path.stat().st_size,
        "modelSHA256": sha256_file(model_path),
        "speakerFile": asm.speaker_file,
    }
    if asm.catalog is not None:
        manifest["voiceCatalog"] = CATALOG_NAME
        manifest["voiceCatalogVersion"] = int(asm.catalog.get("schemaVersion", 1))
        manifest["voiceCatalogSHA256"] = sha256_file(pack_dir / CATALOG_NAME)
    manifest["packId"] = asm.pack_id
    manifest["packVersion"] = asm.pack_version
    manifest = {k: v for k, v in manifest.items() if v is not None}
    write_json(pack_dir / MANIFEST_NAME, manifest)
    return manifest


def build_pack(
    entry: dict[str, Any],
    archive: Path,
    out_dir: Path,
    *,
    repo_root: Path,
    archive_sha256: str | None = None,
    display_lang: str = "en",
    generate_catalog: bool = True,
) -> BuildResult:
    if display_lang not in entry["displayName"]:
        raise VoicePackError(f"unknown display language {display_lang!r}")
    asm = assemble_pack(
        entry, archive, out_dir, repo_root=repo_root, generate_catalog=generate_catalog
    )
    pack_dir, paths, notes = asm.pack_dir, asm.paths, asm.notes
    pack_version = asm.pack_version

    # --- optional lexicon post-processing (before manifest / hashes) -----------------
    lexicon_fill: tuple[int, int] | None = None
    fill_mode = entry["preset"].get("lexiconFill") if _preset_has(entry["preset"], "lexiconFill") else None
    if fill_mode is not None:
        if fill_mode != LEXICON_FILL_OPENCC_T2S:
            raise VoicePackError(f"unknown preset.lexiconFill value: {fill_mode!r}")
        lexicon_rels = list(asm.lexicons) + ([asm.lexicon] if asm.lexicon else [])
        if lexicon_rels:
            filled, dropped, fill_note = apply_lexicon_fill(
                pack_dir, lexicon_rels, asm.tokens, repo_root=repo_root
            )
            notes.append(fill_note)
            if filled or dropped:
                lexicon_fill = (filled, dropped)

    # --- license ------------------------------------------------------------------
    license_file = detect_license(paths)
    lic = entry["license"]
    if license_file is None:
        text_rel = lic.get("textFile")
        if not text_rel:
            raise VoicePackError(
                "upstream archive has no LICENSE file and registry license.textFile is not set"
            )
        text_path = repo_root / text_rel
        if not text_path.is_file():
            raise VoicePackError(f"license.textFile not found: {text_rel}")
        shutil.copyfile(text_path, pack_dir / "LICENSE")
        license_file = "LICENSE"
        notes.append("LICENSE taken from registry license.textFile")
    has_espeak = has_espeak_data(pack_dir, paths)
    if has_espeak:
        if espeak_component(entry) is None:
            raise VoicePackError(
                f"pack contains {ESPEAK_DATA_DIRNAME} (GPL-3.0-or-later data) but the registry entry "
                "declares no license.components item with role=data for espeak-ng-data"
            )
        notes.append(write_espeak_copying(pack_dir, paths, repo_root))
    (pack_dir / ATTRIBUTION_NAME).write_text(
        render_attribution(
            entry,
            pack_version=pack_version,
            archive_sha256=archive_sha256,
            license_file=license_file,
            has_espeak=has_espeak,
            lexicon_fill=lexicon_fill,
        ),
        encoding="utf-8",
        newline="\n",
    )

    manifest = write_manifest(
        asm,
        display_name=entry["displayName"][display_lang],
        source_url=entry["upstream"].get("homepage") or entry["upstream"]["url"],
        license_file=license_file,
    )
    return BuildResult(
        pack_id=asm.pack_id,
        pack_version=pack_version,
        pack_dir=pack_dir,
        manifest=manifest,
        notes=notes,
    )
