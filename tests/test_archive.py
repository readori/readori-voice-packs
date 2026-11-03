from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from readori_voicepack import archive as arc
from readori_voicepack.common import VoicePackError

from .conftest import vits_files, write_tar_bz2, write_zip


def _tar_with(path: Path, members: list[tarfile.TarInfo], data: bytes = b"x") -> Path:
    with tarfile.open(path, "w:bz2") as tf:
        for info in members:
            tf.addfile(info, io.BytesIO(data) if info.isfile() else None)
    return path


def _file_member(name: str, size: int = 1) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    return info


def test_extract_strips_single_wrapper(tmp_path, vits_archive):
    root = arc.extract_archive(vits_archive, tmp_path / "x")
    assert (root / "model.onnx").is_file()
    assert (root / "espeak-ng-data" / "en_dict").is_file()


def test_extract_keeps_flat_layout(tmp_path):
    flat = write_tar_bz2(tmp_path / "flat.tar.bz2", vits_files(), wrapper=None)
    root = arc.extract_archive(flat, tmp_path / "x")
    assert root == tmp_path / "x"
    assert (root / "model.onnx").is_file()


@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "a/../../evil.txt", "/abs/evil.txt", "C:/evil.txt", "dir\\..\\evil.txt"],
)
def test_tar_path_traversal_rejected(tmp_path, name):
    archive = _tar_with(tmp_path / "evil.tar.bz2", [_file_member(name)])
    with pytest.raises(VoicePackError, match="unsafe tar member"):
        arc.extract_archive(archive, tmp_path / "x")
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.parametrize("name", ["../evil.txt", "ok/../../evil.txt", "/abs.txt", "C:/x.txt"])
def test_zip_path_traversal_rejected(tmp_path, name):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, b"x")
    with pytest.raises(VoicePackError, match="unsafe ZIP member"):
        arc.extract_archive(archive, tmp_path / "x")


def test_tar_symlink_and_hardlink_rejected(tmp_path):
    link = tarfile.TarInfo("m/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    archive = _tar_with(tmp_path / "l.tar.bz2", [link])
    with pytest.raises(VoicePackError, match="links are not allowed"):
        arc.extract_archive(archive, tmp_path / "x")
    hard = tarfile.TarInfo("m/hard")
    hard.type = tarfile.LNKTYPE
    hard.linkname = "m/other"
    archive = _tar_with(tmp_path / "h.tar.bz2", [hard])
    with pytest.raises(VoicePackError, match="links are not allowed"):
        arc.extract_archive(archive, tmp_path / "y")


def test_tar_special_file_rejected(tmp_path):
    fifo = tarfile.TarInfo("m/fifo")
    fifo.type = tarfile.FIFOTYPE
    archive = _tar_with(tmp_path / "f.tar.bz2", [fifo])
    with pytest.raises(VoicePackError, match="special files"):
        arc.extract_archive(archive, tmp_path / "x")


def test_zip_symlink_rejected(tmp_path):
    archive = tmp_path / "s.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo("m/link")
        info.create_system = 3
        info.external_attr = (0o120777) << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(VoicePackError, match="links are not allowed"):
        arc.extract_archive(archive, tmp_path / "x")


def test_size_and_entry_limits(tmp_path, vits_archive):
    with pytest.raises(VoicePackError, match="expands beyond"):
        arc.extract_archive(vits_archive, tmp_path / "x", max_total_bytes=100)
    with pytest.raises(VoicePackError, match="more than 2 entries"):
        arc.extract_archive(vits_archive, tmp_path / "y", max_entries=2)
    zip_path = write_zip(tmp_path / "big.zip", {"a.bin": b"0" * 1000})
    with pytest.raises(VoicePackError, match="expands beyond"):
        arc.extract_archive(zip_path, tmp_path / "z", max_total_bytes=10)


def test_unsupported_archive_type(tmp_path):
    other = tmp_path / "model.7z"
    other.write_bytes(b"x")
    with pytest.raises(VoicePackError, match="unsupported archive type"):
        arc.extract_archive(other, tmp_path / "x")


def test_corrupt_archives(tmp_path):
    bad_tar = tmp_path / "bad.tar.bz2"
    bad_tar.write_bytes(b"not a tarball")
    with pytest.raises(VoicePackError, match="cannot open tar"):
        arc.extract_archive(bad_tar, tmp_path / "x")
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    with pytest.raises(VoicePackError, match="cannot open zip"):
        arc.extract_archive(bad_zip, tmp_path / "y")
