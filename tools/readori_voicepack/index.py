"""catalog/v1/index.json maintenance."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import SHA256_RE, VoicePackError, loads_strict, write_json

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DEFAULT_INDEX = Path("catalog/v1/index.json")


def release_tag(pack_id: str, pack_version: int) -> str:
    return f"pack/{pack_id}/v{pack_version}"


def download_url(repo: str, pack_id: str, pack_version: int, file_name: str) -> str:
    if not REPO_RE.match(repo):
        raise VoicePackError(f"invalid repository slug: {repo!r}")
    return f"https://github.com/{repo}/releases/download/{release_tag(pack_id, pack_version)}/{file_name}"


def entry_from_sidecar(sidecar: dict[str, Any], repo: str) -> dict[str, Any]:
    for key in ("id", "packVersion", "file", "bytes", "sha256", "type", "speakerCount"):
        if key not in sidecar:
            raise VoicePackError(f"sidecar is missing '{key}'")
    if not SHA256_RE.match(sidecar["sha256"]):
        raise VoicePackError(f"sidecar for {sidecar['id']} has an invalid sha256")
    entry: dict[str, Any] = {
        "id": sidecar["id"],
        "packVersion": sidecar["packVersion"],
        "displayName": sidecar.get("displayName"),
        "languages": sidecar.get("languages"),
        "type": sidecar["type"],
        "speakerCount": sidecar["speakerCount"],
        "bytes": sidecar["bytes"],
        "sha256": sidecar["sha256"],
        "url": download_url(repo, sidecar["id"], sidecar["packVersion"], sidecar["file"]),
        "license": sidecar.get("license"),
        "minAppVersion": sidecar.get("minAppVersion"),
        "appleAssetPackId": sidecar.get("appleAssetPackId"),
    }
    return {k: v for k, v in entry.items() if v is not None}


def load_index(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schemaVersion": 1, "packs": []}
    try:
        doc = loads_strict(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise VoicePackError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 1 or not isinstance(doc.get("packs"), list):
        raise VoicePackError(f"{path} is not a v1 index")
    return doc


def merge_entries(doc: dict[str, Any], new_entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {p["id"]: p for p in doc["packs"]}
    for entry in new_entries:
        existing = by_id.get(entry["id"])
        if existing is not None and existing["packVersion"] > entry["packVersion"]:
            continue  # never move the index back to an older pack version
        by_id[entry["id"]] = entry
    return {"schemaVersion": 1, "packs": [by_id[k] for k in sorted(by_id)]}


def update_index(index_path: Path, sidecars: list[dict[str, Any]], repo: str) -> dict[str, Any]:
    doc = load_index(index_path)
    merged = merge_entries(doc, [entry_from_sidecar(s, repo) for s in sidecars])
    write_json(index_path, merged)
    return merged


def find_sidecars(directory: Path) -> list[dict[str, Any]]:
    sidecars: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*.zip.json")):
        try:
            sidecars.append(loads_strict(path.read_text(encoding="utf-8")))
        except ValueError as exc:
            raise VoicePackError(f"{path} is not valid JSON: {exc}") from exc
    return sidecars
