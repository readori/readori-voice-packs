"""Deterministic ZIP packaging and release sidecar metadata."""
from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import (
    COMMUNITY_NOTICE,
    MANIFEST_NAME,
    MAX_ARCHIVE_ENTRIES,
    MAX_ZIP_BYTES,
    TIER_COMMUNITY,
    TIER_LOCAL,
    TIER_OFFICIAL,
    ZIP_FIXED_DATE_TIME,
    VoicePackError,
    is_self_built_dir,
    loads_strict,
    safe_relative_path,
    sha256_file,
    write_json,
)
from .registry import ATTRIBUTION_REQUIRED_SPDX
from .validate import validate_directory

_JUNK = (".DS_Store", "Thumbs.db")


@dataclass
class PackResult:
    zip_path: Path
    sidecar_path: Path
    sha256: str
    bytes: int
    entries: int
    sidecar: dict[str, Any]


@dataclass
class LocalMeta:
    """Sidecar facts for a self-built pack (there is no registry entry)."""

    display_name: str
    languages: list[str]


def apple_asset_pack_id(pack_id: str) -> str:
    """Background Assets asset-pack ID for a voice pack (naming rule pending macOS check)."""
    return f"readori.voice.{pack_id}"


def archive_name(pack_id: str, pack_version: int) -> str:
    return f"{pack_id}-v{pack_version}.zip"


def _collect(src_dir: Path) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for path in src_dir.rglob("*"):
        if path.is_symlink():
            raise VoicePackError(f"symlink in pack directory: {path}")
        if not path.is_file() or path.name in _JUNK:
            continue
        rel = path.relative_to(src_dir).as_posix()
        if safe_relative_path(rel) != rel:
            raise VoicePackError(f"unsafe output path: {rel!r}")
        items.append((rel, path))
    # Sort by UTF-8 bytes so the order does not depend on locale or platform.
    items.sort(key=lambda item: item[0].encode("utf-8"))
    return items


def make_deterministic_zip(src_dir: Path, out_zip: Path) -> tuple[str, int, int]:
    """Write ``src_dir`` as a ZIP with fixed timestamps / permissions and sorted entries.

    No directory entries and no wrapper folder: the manifest sits at the ZIP root, which is
    where the app importer resolves manifest paths from. Returns (sha256, bytes, entries).
    """
    items = _collect(src_dir)
    if len(items) > MAX_ARCHIVE_ENTRIES:
        raise VoicePackError(f"pack has {len(items)} files, limit {MAX_ARCHIVE_ENTRIES}")
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_zip.with_name(out_zip.name + ".part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel, path in items:
            info = zipfile.ZipInfo(rel, date_time=ZIP_FIXED_DATE_TIME)
            info.create_system = 3  # fixed: do not depend on the build platform
            info.external_attr = (0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = 6  # same as ZipFile(compresslevel=6); fixed explicitly
            info.flag_bits |= 0x800  # UTF-8 names
            with path.open("rb") as src, zf.open(info, "w", force_zip64=False) as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    size = tmp.stat().st_size
    if size > MAX_ZIP_BYTES:
        tmp.unlink()
        raise VoicePackError(f"ZIP is {size} bytes, limit {MAX_ZIP_BYTES}")
    tmp.replace(out_zip)
    return sha256_file(out_zip), size, len(items)


def build_sidecar(
    manifest: dict[str, Any],
    *,
    file_name: str,
    sha256: str,
    size: int,
    entry: dict[str, Any] | None,
    local: LocalMeta | None = None,
) -> dict[str, Any]:
    pack_id = manifest["packId"]
    sidecar: dict[str, Any] = {
        "schemaVersion": 1,
        "id": pack_id,
        "packVersion": manifest["packVersion"],
        "file": file_name,
        "bytes": size,
        "sha256": sha256,
        "type": manifest["type"],
        "speakerCount": manifest.get("speakerCount", 1),
        "defaultSpeaker": manifest.get("defaultSpeaker", 0),
        "modelBytes": manifest.get("modelBytes"),
    }
    community = entry is not None and entry.get("status") == "community"
    if not community and local is None:
        # Community and self-built packs are never offered as Apple-hosted asset packs.
        sidecar["appleAssetPackId"] = apple_asset_pack_id(pack_id)
    if local is not None:
        sidecar["tier"] = TIER_LOCAL
        sidecar["recommended"] = False
        sidecar["displayName"] = {"en": local.display_name}
        sidecar["languages"] = list(local.languages)
        sidecar["license"] = {"verified": False, "selfBuilt": True}
    if entry is not None:
        lic = entry["license"]
        sidecar["tier"] = TIER_COMMUNITY if community else TIER_OFFICIAL
        sidecar["recommended"] = not community
        if community:
            sidecar["notice"] = dict(COMMUNITY_NOTICE)
        sidecar["displayName"] = dict(entry["displayName"])
        sidecar["languages"] = list(entry["languages"])
        sidecar["minAppVersion"] = entry["minAppVersion"]
        sidecar["license"] = {
            "spdx": lic["spdx"],
            "url": lic["url"],
            "attributionRequired": lic["spdx"] in ATTRIBUTION_REQUIRED_SPDX,
            "verified": not community,
        }
    return {k: v for k, v in sidecar.items() if v is not None}


def pack_directory(
    pack_dir: Path,
    out_dir: Path,
    *,
    entry: dict[str, Any] | None = None,
    local: LocalMeta | None = None,
) -> PackResult:
    """``local`` is only passed by ``build-local``; registry packs can never become local."""
    if local is not None and entry is not None:
        raise VoicePackError("a registry pack cannot be packed as a local (self-built) pack")
    if local is None and is_self_built_dir(pack_dir):
        raise VoicePackError(
            f"{pack_dir} is a self-built pack; 'pack' is only for registry packs "
            "(use 'build-local' to build a self-built ZIP)"
        )
    manifest_path = pack_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise VoicePackError(f"{MANIFEST_NAME} not found in {pack_dir}")
    manifest = loads_strict(manifest_path.read_text(encoding="utf-8"))
    if "packId" not in manifest or "packVersion" not in manifest:
        raise VoicePackError("manifest has no packId / packVersion; build the pack with 'build'")
    result = validate_directory(pack_dir, policy=True)
    if not result.ok:
        raise VoicePackError(
            "refusing to pack an invalid directory:\n  " + "\n  ".join(str(e) for e in result.errors)
        )
    name = archive_name(manifest["packId"], manifest["packVersion"])
    zip_path = out_dir / name
    sha, size, entries = make_deterministic_zip(pack_dir, zip_path)
    sidecar = build_sidecar(
        manifest, file_name=name, sha256=sha, size=size, entry=entry, local=local
    )
    sidecar_path = out_dir / f"{name}.json"
    write_json(sidecar_path, sidecar)
    return PackResult(zip_path, sidecar_path, sha, size, entries, sidecar)
