"""Safe extraction of upstream archives (.tar.bz2 / .tar.gz / .tar / .zip).

Upstream archives are untrusted data: every member path is checked with the same rule as the
app importer, links and special files are rejected, and entry count / size are bounded.
"""
from __future__ import annotations

import shutil
import stat
import tarfile
import zipfile
from pathlib import Path

from .common import VoicePackError, safe_relative_path

# Upstream archives may be larger than a finished pack (test audio, scripts are dropped later).
DEFAULT_MAX_UPSTREAM_BYTES = 4 * 1024 * 1024 * 1024
DEFAULT_MAX_UPSTREAM_ENTRIES = 50_000

_JUNK_NAMES = ("__MACOSX", ".DS_Store")
_COPY_CHUNK = 1024 * 1024


def _inside(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _remember(seen: set[str], rel: str) -> None:
    """Reject names that collide on case-insensitive file systems (APFS default)."""
    key = rel.lower()
    if key in seen:
        raise VoicePackError(f"archive has paths differing only by case: {rel!r}")
    seen.add(key)


def _member_rel(name: str, allow_dot_prefix: bool) -> str | None:
    """Return the safe relative path for an archive member, ``""`` for a bare ``./`` root entry.

    Upstream tarballs created with ``tar -C dir .`` name members ``./vits-foo/...``. Only that
    leading ``./`` is dropped (and only for upstream archives); the rest of the path still has
    to pass the app importer rule, so ``./../x`` is rejected as before.
    """
    if allow_dot_prefix:
        normalized = name.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized in ("", "."):
            return ""
        name = normalized
    return safe_relative_path(name)


def _copy_bounded(src, dst_path: Path, budget: int) -> int:
    """Copy at most ``budget`` bytes; raise if the stream is larger (lying size headers)."""
    written = 0
    with dst_path.open("wb") as out:
        while True:
            chunk = src.read(_COPY_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > budget:
                raise VoicePackError("archive member exceeds the declared size budget")
            out.write(chunk)
    return written


def extract_archive(
    archive: Path,
    destination: Path,
    *,
    max_total_bytes: int = DEFAULT_MAX_UPSTREAM_BYTES,
    max_entries: int = DEFAULT_MAX_UPSTREAM_ENTRIES,
) -> Path:
    """Extract ``archive`` into ``destination`` and return the payload root."""
    extract_raw(
        archive,
        destination,
        max_total_bytes=max_total_bytes,
        max_entries=max_entries,
        allow_dot_prefix=True,
    )
    return choose_payload_root(destination)


def extract_raw(
    archive: Path,
    destination: Path,
    *,
    max_total_bytes: int = DEFAULT_MAX_UPSTREAM_BYTES,
    max_entries: int = DEFAULT_MAX_UPSTREAM_ENTRIES,
    allow_dot_prefix: bool = False,
) -> None:
    """Extract without stripping a wrapper directory (used to validate finished packs).

    ``allow_dot_prefix`` accepts a leading ``./`` on member names; only upstream archives set it.
    """
    destination.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        _extract_zip(archive, destination, max_total_bytes, max_entries, allow_dot_prefix)
    elif name.endswith((".tar.bz2", ".tbz2", ".tar.gz", ".tgz", ".tar")):
        _extract_tar(archive, destination, max_total_bytes, max_entries, allow_dot_prefix)
    else:
        raise VoicePackError(f"unsupported archive type: {archive.name}")


def _extract_tar(
    archive: Path, destination: Path, max_total: int, max_entries: int, allow_dot_prefix: bool
) -> None:
    total = 0
    count = 0
    seen: set[str] = set()
    try:
        tf = tarfile.open(archive, "r:*")
    except (tarfile.TarError, OSError) as exc:
        raise VoicePackError(f"cannot open tar archive {archive.name}: {exc}") from exc
    with tf:
        for member in tf:
            count += 1
            if count > max_entries:
                raise VoicePackError(f"archive has more than {max_entries} entries")
            rel = _member_rel(member.name, allow_dot_prefix)
            if rel is None:
                raise VoicePackError(f"unsafe tar member: {member.name!r}")
            if rel == "":
                if member.isdir():
                    continue
                raise VoicePackError(f"unsafe tar member: {member.name!r}")
            if member.issym() or member.islnk():
                raise VoicePackError(f"links are not allowed in model archives: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise VoicePackError(f"special files are not allowed: {member.name!r}")
            target = destination / rel
            if not _inside(destination, target):
                raise VoicePackError(f"tar member escapes destination: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            _remember(seen, rel)
            total += member.size
            if total > max_total:
                raise VoicePackError(f"archive expands beyond {max_total} bytes")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                raise VoicePackError(f"cannot read tar member: {member.name!r}")
            with src:
                _copy_bounded(src, target, member.size)


def _extract_zip(
    archive: Path, destination: Path, max_total: int, max_entries: int, allow_dot_prefix: bool
) -> None:
    total = 0
    seen: set[str] = set()
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        raise VoicePackError(f"cannot open zip archive {archive.name}: {exc}") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > max_entries:
            raise VoicePackError(f"archive has more than {max_entries} entries")
        for info in infos:
            rel = _member_rel(info.filename, allow_dot_prefix)
            if rel is None:
                raise VoicePackError(f"unsafe ZIP member: {info.filename!r}")
            if rel == "":
                if info.is_dir():
                    continue
                raise VoicePackError(f"unsafe ZIP member: {info.filename!r}")
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise VoicePackError(f"links are not allowed in model archives: {info.filename!r}")
            target = destination / rel
            if not _inside(destination, target):
                raise VoicePackError(f"ZIP member escapes destination: {info.filename!r}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            _remember(seen, rel)
            total += info.file_size
            if total > max_total:
                raise VoicePackError(f"archive expands beyond {max_total} bytes")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src:
                _copy_bounded(src, target, info.file_size)


def choose_payload_root(root: Path) -> Path:
    """Strip a single wrapper directory (``vits-foo/``) like the v13 builder does."""
    children = [p for p in root.iterdir() if p.name not in _JUNK_NAMES]
    dirs = [p for p in children if p.is_dir()]
    files = [p for p in children if p.is_file()]
    return dirs[0] if len(dirs) == 1 and not files else root


def copy_tree(src: Path, dst: Path) -> None:
    """Copy regular files only (no symlinks), creating ``dst``."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for path in sorted(src.rglob("*")):
        if path.is_symlink():
            raise VoicePackError(f"symlink in payload: {path}")
        rel = path.relative_to(src)
        if path.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst / rel)
