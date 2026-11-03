"""Download and pin upstream model archives."""
from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .common import VoicePackError, is_plain_int, is_todo

DEFAULT_MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024 * 1024
USER_AGENT = "readori-voicepack/0.1 (+https://github.com/readori/readori-voice-packs)"


@dataclass
class FetchResult:
    path: Path
    sha256: str
    bytes: int
    pinned: bool


def archive_filename(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    if not name:
        raise VoicePackError(f"cannot derive a file name from {url}")
    return name


def cache_path(cache_dir: Path, model_id: str, url: str) -> Path:
    return cache_dir / "downloads" / model_id / archive_filename(url)


def download(
    url: str,
    destination: Path,
    *,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    retries: int = 3,
    allowed_schemes: tuple[str, ...] = ("https",),
    backoff: float = 2.0,
) -> tuple[str, int]:
    """Stream ``url`` to ``destination`` (via a .part file); return (sha256, bytes)."""
    scheme = urlparse(url).scheme.lower()
    if scheme not in allowed_schemes:
        raise VoicePackError(f"refusing to download over '{scheme}': {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        digest = hashlib.sha256()
        size = 0
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise VoicePackError(f"download exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    out.write(chunk)
            part.replace(destination)
            return digest.hexdigest(), size
        except VoicePackError:
            part.unlink(missing_ok=True)
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = exc
            part.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise VoicePackError(f"download failed after {retries} attempts: {last_error}")


class PinMismatchError(VoicePackError):
    """The downloaded archive contradicts a pinned sha256 / size in the registry."""


def check_pins(entry: dict[str, Any], sha256: str, size: int) -> bool:
    """Compare against pinned values; return True when both sha256 and bytes are pinned."""
    upstream = entry["upstream"]
    expected_sha = upstream.get("sha256")
    expected_bytes = upstream.get("bytes")
    pinned_sha = isinstance(expected_sha, str) and not is_todo(expected_sha)
    pinned_bytes = is_plain_int(expected_bytes)
    if pinned_sha and expected_sha != sha256:
        raise PinMismatchError(
            f"sha256 mismatch for {entry['id']}: registry {expected_sha}, got {sha256}"
        )
    if pinned_bytes and expected_bytes != size:
        raise PinMismatchError(
            f"size mismatch for {entry['id']}: registry {expected_bytes}, got {size}"
        )
    return pinned_sha and pinned_bytes


def verify_archive(entry: dict[str, Any], sha256: str, size: int, *, allow_unpinned: bool) -> bool:
    """Check hash / size against the registry. Returns True when the entry is pinned."""
    pinned = check_pins(entry, sha256, size)
    if not pinned:
        print(
            f"UNPINNED {entry['id']}: sha256={sha256} bytes={size}  "
            "(put these into registry/models.yaml upstream.sha256 / upstream.bytes)"
        )
        if not allow_unpinned:
            raise VoicePackError(
                f"{entry['id']} has no pinned sha256/bytes in the registry; "
                "pin it or pass --allow-unpinned"
            )
    return pinned


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size


def fetch_model(
    entry: dict[str, Any],
    cache_dir: Path,
    *,
    allow_unpinned: bool = False,
    allowed_schemes: tuple[str, ...] = ("https",),
    force: bool = False,
    retries: int = 3,
) -> FetchResult:
    url = entry["upstream"]["url"]
    target = cache_path(cache_dir, entry["id"], url)
    if target.exists() and not force:
        sha, size = _hash_file(target)
        try:
            check_pins(entry, sha, size)
        except PinMismatchError:
            print("cached file does not match the registry; downloading again")
            target.unlink()
        else:
            print(f"cache hit: {target}")
            pinned = verify_archive(entry, sha, size, allow_unpinned=allow_unpinned)
            return FetchResult(target, sha, size, pinned)
    sha, size = download(url, target, allowed_schemes=allowed_schemes, retries=retries)
    try:
        pinned = verify_archive(entry, sha, size, allow_unpinned=allow_unpinned)
    except PinMismatchError:
        target.unlink(missing_ok=True)
        raise
    print(f"fetched {target} sha256={sha} bytes={size}")
    return FetchResult(target, sha, size, pinned)
