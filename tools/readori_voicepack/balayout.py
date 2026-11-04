"""Apple-hosted asset pack layout for ``xcrun ba-package`` (Background Assets, iOS 26+).

Every official voice pack in ``catalog/v1/index.json`` that has an ``appleAssetPackId`` becomes
one Apple asset pack whose only content is the byte-identical GitHub Release ZIP::

    <out>/<assetPackId>/<packId>/<packId>.zip     the Release ZIP (sha256 and bytes re-checked)
    <out>/<assetPackId>.manifest.json             ba-package manifest filled from a template

All asset packs of an app share one file namespace, hence the ``<packId>/`` prefix inside the
pack. ``ba-package`` must be run from ``<out>/<assetPackId>`` so the manifest's relative file
selector (``<packId>/<packId>.zip``) resolves.

Manifest shape. The macOS job fills the real template printed by ``xcrun ba-package template``
(unknown keys are kept); ``DEFAULT_TEMPLATE`` is only the fallback for offline use and tests. It
mirrors Apple's documented template: ``assetPackID``, ``downloadPolicy`` (``essential`` /
``prefetch`` with ``installationEventTypes``, or ``onDemand``), ``fileSelectors`` (``file`` or
``directory`` entries) and ``platforms``. Only the four keys set in ``fill_manifest`` are ours.

This module only prepares files. It never talks to Apple and never uploads anything.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import (
    ID_RE,
    SHA256_RE,
    TIER_COMMUNITY,
    TIER_LOCAL,
    VoicePackError,
    loads_strict,
    sha256_file,
    write_json,
)

RELEASE_URL_PREFIX = "https://github.com/readori/readori-voice-packs/releases/download/"
ASSET_PACK_ID_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")
MANIFEST_SUFFIX = ".manifest.json"

DEFAULT_TEMPLATE: dict[str, Any] = {
    "assetPackID": "",
    "downloadPolicy": {
        "essential": {"installationEventTypes": ["firstInstallation", "subsequentUpdate"]}
    },
    "fileSelectors": [{"directory": "Path/To/Directory"}, {"file": "Path/To/File"}],
    "platforms": ["iOS"],
}


@dataclass(frozen=True)
class AssetPackPlan:
    pack_id: str
    asset_pack_id: str
    pack_version: int
    url: str
    file_name: str
    sha256: str
    bytes: int

    @property
    def inner_path(self) -> str:
        """Path of the ZIP inside the asset pack (shared namespace, so prefixed with the id)."""
        return f"{self.pack_id}/{self.pack_id}.zip"

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.pack_id,
            "assetPackId": self.asset_pack_id,
            "packVersion": self.pack_version,
            "url": self.url,
            "file": self.file_name,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


@dataclass(frozen=True)
class LayoutResult:
    plan: AssetPackPlan
    pack_root: Path  # run ba-package from here
    zip_path: Path
    manifest_path: Path


def _plan_one(entry: dict[str, Any]) -> AssetPackPlan:
    pack_id = entry.get("id")
    if not isinstance(pack_id, str) or not ID_RE.match(pack_id):
        raise VoicePackError(f"index entry has an invalid id: {pack_id!r}")
    asset_id = entry.get("appleAssetPackId")
    if not isinstance(asset_id, str) or not ASSET_PACK_ID_RE.match(asset_id) or ".." in asset_id:
        raise VoicePackError(f"{pack_id}: invalid appleAssetPackId {asset_id!r}")
    version = entry.get("packVersion")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise VoicePackError(f"{pack_id}: invalid packVersion {version!r}")
    sha = entry.get("sha256")
    if not isinstance(sha, str) or not SHA256_RE.match(sha):
        raise VoicePackError(f"{pack_id}: invalid sha256 in the index")
    size = entry.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise VoicePackError(f"{pack_id}: invalid bytes in the index")
    file_name = f"{pack_id}-v{version}.zip"
    url = entry.get("url")
    expected = f"{RELEASE_URL_PREFIX}pack/{pack_id}/v{version}/{file_name}"
    if url != expected:
        raise VoicePackError(f"{pack_id}: url must be {expected}, got {url!r}")
    return AssetPackPlan(pack_id, asset_id, version, url, file_name, sha, size)


def plan_entries(
    index_doc: dict[str, Any], pack_ids: list[str] | None = None
) -> list[AssetPackPlan]:
    """Select the index entries that become Apple asset packs (sorted by pack id).

    Entries without ``appleAssetPackId`` and community / local tier entries are skipped. Naming one
    of them explicitly in ``pack_ids`` is an error, as is an unknown id.
    """
    packs = index_doc.get("packs")
    if not isinstance(packs, list):
        raise VoicePackError("index has no 'packs' list")
    by_id = {p.get("id"): p for p in packs if isinstance(p, dict)}
    wanted = list(dict.fromkeys(pack_ids)) if pack_ids else None

    def eligible(entry: dict[str, Any]) -> str | None:
        """None when the entry may become an asset pack, else the reason it may not."""
        if entry.get("tier") in (TIER_COMMUNITY, TIER_LOCAL):
            return f"{entry.get('tier')} tier (GitHub Releases only)"
        if entry.get("appleAssetPackId") is None:
            return "no appleAssetPackId"
        return None

    if wanted is not None:
        for pack_id in wanted:
            if pack_id not in by_id:
                raise VoicePackError(f"pack id not in the index: {pack_id}")
            reason = eligible(by_id[pack_id])
            if reason:
                raise VoicePackError(f"{pack_id} cannot become an Apple asset pack: {reason}")
        entries = [by_id[i] for i in wanted]
    else:
        entries = [p for p in packs if isinstance(p, dict) and eligible(p) is None]
    plans = sorted((_plan_one(e) for e in entries), key=lambda p: p.pack_id)
    asset_ids = [p.asset_pack_id for p in plans]
    if len(asset_ids) != len(set(asset_ids)):
        raise VoicePackError("two index entries share one appleAssetPackId")
    return plans


def find_zip(zips_dir: Path, file_name: str) -> Path:
    direct = zips_dir / file_name
    if direct.is_file():
        return direct
    matches = sorted(p for p in zips_dir.rglob(file_name) if p.is_file())
    if not matches:
        raise VoicePackError(f"Release ZIP not found under {zips_dir}: {file_name}")
    if len(matches) > 1:
        raise VoicePackError(f"several files named {file_name} under {zips_dir}")
    return matches[0]


def _verify(path: Path, plan: AssetPackPlan, what: str) -> None:
    size = path.stat().st_size
    if size != plan.bytes:
        raise VoicePackError(
            f"{plan.pack_id}: {what} has {size} bytes, the index says {plan.bytes}"
        )
    digest = sha256_file(path)
    if digest != plan.sha256:
        raise VoicePackError(
            f"{plan.pack_id}: {what} sha256 {digest} does not match the index ({plan.sha256})"
        )


def fill_manifest(template: dict[str, Any], plan: AssetPackPlan) -> dict[str, Any]:
    """Put our values into ``template``; every other key of the template is kept untouched."""
    if not isinstance(template, dict):
        raise VoicePackError("ba-package template must be a JSON object")
    manifest = copy.deepcopy(template)
    manifest["assetPackID"] = plan.asset_pack_id
    manifest["downloadPolicy"] = {"onDemand": {}}  # the user picks a voice pack; never automatic
    manifest["fileSelectors"] = [{"file": plan.inner_path}]
    manifest["platforms"] = ["iOS"]
    return manifest


def load_template(path: Path | None) -> dict[str, Any]:
    if path is None:
        return copy.deepcopy(DEFAULT_TEMPLATE)
    if not path.is_file():
        raise VoicePackError(f"template not found: {path}")
    try:
        template = loads_strict(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise VoicePackError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(template, dict):
        raise VoicePackError(f"{path} is not a JSON object")
    return template


def layout_pack(
    plan: AssetPackPlan,
    zips_dir: Path,
    out_dir: Path,
    template: dict[str, Any],
    *,
    hardlink: bool = False,
) -> LayoutResult:
    source = find_zip(zips_dir, plan.file_name)
    _verify(source, plan, f"source {source.name}")  # fail before anything is written
    pack_root = out_dir / plan.asset_pack_id
    target = pack_root / plan.pack_id / f"{plan.pack_id}.zip"
    if pack_root.exists():
        shutil.rmtree(pack_root)
    target.parent.mkdir(parents=True)
    try:
        linked = False
        if hardlink:
            try:
                os.link(source, target)
                linked = True
            except OSError:
                linked = False
        if not linked:
            shutil.copyfile(source, target)
        _verify(target, plan, f"staged {target.name}")
    except BaseException:
        shutil.rmtree(pack_root, ignore_errors=True)
        raise
    manifest_path = out_dir / f"{plan.asset_pack_id}{MANIFEST_SUFFIX}"
    write_json(manifest_path, fill_manifest(template, plan))
    return LayoutResult(plan, pack_root, target, manifest_path)


def build_layout(
    index_doc: dict[str, Any],
    zips_dir: Path,
    out_dir: Path,
    *,
    template: dict[str, Any] | None = None,
    pack_ids: list[str] | None = None,
    hardlink: bool = False,
) -> list[LayoutResult]:
    plans = plan_entries(index_doc, pack_ids)
    if not plans:
        raise VoicePackError("no index entry has an appleAssetPackId: nothing to lay out")
    if not zips_dir.is_dir():
        raise VoicePackError(f"ZIP directory not found: {zips_dir}")
    tmpl = template if template is not None else copy.deepcopy(DEFAULT_TEMPLATE)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [layout_pack(p, zips_dir, out_dir, tmpl, hardlink=hardlink) for p in plans]
