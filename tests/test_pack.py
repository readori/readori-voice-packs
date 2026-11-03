from __future__ import annotations

import hashlib
import os
import shutil
import zipfile

import pytest
from readori_voicepack import validate as val
from readori_voicepack.common import MANIFEST_NAME, ZIP_FIXED_DATE_TIME, VoicePackError
from readori_voicepack.pack import (
    apple_asset_pack_id,
    archive_name,
    make_deterministic_zip,
    pack_directory,
)

from .conftest import make_entry


def test_zip_is_deterministic_across_runs_and_mtimes(built_vits, tmp_path):
    _, built = built_vits
    first = tmp_path / "one" / "p.zip"
    sha1, _, _ = make_deterministic_zip(built.pack_dir, first)

    copy = tmp_path / "copy"
    shutil.copytree(built.pack_dir, copy)
    for i, path in enumerate(sorted(copy.rglob("*"))):
        os.utime(path, (1_000_000_000 + i * 977, 1_000_000_000 + i * 977))
    second = tmp_path / "two" / "p.zip"
    sha2, _, _ = make_deterministic_zip(copy, second)

    assert sha1 == sha2
    assert first.read_bytes() == second.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest() == sha1


def test_zip_layout(built_vits, tmp_path):
    _, built = built_vits
    out = tmp_path / "p.zip"
    _, size, entries = make_deterministic_zip(built.pack_dir, out)
    assert size == out.stat().st_size
    with zipfile.ZipFile(out) as zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        assert len(infos) == entries
        assert MANIFEST_NAME in names  # at the root, no wrapper folder
        assert names == sorted(names, key=lambda n: n.encode("utf-8"))
        assert not any(n.endswith("/") for n in names), "no directory entries"
        assert all(i.date_time == ZIP_FIXED_DATE_TIME for i in infos)
        assert all(i.create_system == 3 for i in infos)
        assert all((i.external_attr >> 16) == 0o100644 for i in infos)
        assert zf.testzip() is None


def test_zip_ignores_junk_and_refuses_symlinks(built_vits, tmp_path):
    _, built = built_vits
    (built.pack_dir / ".DS_Store").write_bytes(b"junk")
    out = tmp_path / "p.zip"
    make_deterministic_zip(built.pack_dir, out)
    with zipfile.ZipFile(out) as zf:
        assert ".DS_Store" not in zf.namelist()
    link = built.pack_dir / "link"
    try:
        link.symlink_to(built.pack_dir / "tokens.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    with pytest.raises(VoicePackError, match="symlink"):
        make_deterministic_zip(built.pack_dir, tmp_path / "q.zip")


def test_zip_entry_limit_and_size_limit(built_vits, tmp_path, monkeypatch):
    _, built = built_vits
    from readori_voicepack import pack as pack_mod

    monkeypatch.setattr(pack_mod, "MAX_ARCHIVE_ENTRIES", 2)
    with pytest.raises(VoicePackError, match="limit"):
        make_deterministic_zip(built.pack_dir, tmp_path / "a.zip")
    monkeypatch.setattr(pack_mod, "MAX_ARCHIVE_ENTRIES", 10_000)
    monkeypatch.setattr(pack_mod, "MAX_ZIP_BYTES", 10)
    with pytest.raises(VoicePackError, match="limit"):
        make_deterministic_zip(built.pack_dir, tmp_path / "b.zip")
    assert not (tmp_path / "b.zip").exists()


def test_pack_directory_writes_zip_and_sidecar(built_vits, tmp_path):
    entry, built = built_vits
    result = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry)
    assert result.zip_path.name == archive_name("zh-fake-v1", 1) == "zh-fake-v1-v1.zip"
    assert result.sidecar_path.name == "zh-fake-v1-v1.zip.json"
    sidecar = result.sidecar
    assert sidecar["sha256"] == result.sha256 == hashlib.sha256(result.zip_path.read_bytes()).hexdigest()
    assert sidecar["bytes"] == result.zip_path.stat().st_size
    assert sidecar["id"] == "zh-fake-v1"
    assert sidecar["packVersion"] == 1
    assert sidecar["type"] == "vits"
    assert sidecar["speakerCount"] == 1
    assert sidecar["appleAssetPackId"] == apple_asset_pack_id("zh-fake-v1") == "readori.voice.zh-fake-v1"
    assert sidecar["license"] == {
        "spdx": "Apache-2.0",
        "url": "https://example.invalid/LICENSE",
        "attributionRequired": False,
    }
    assert sidecar["displayName"]["zh-Hans"] == "测试普通话"
    assert sidecar["languages"] == ["zh-CN"]
    assert val.validate_target(result.zip_path).ok


def test_pack_without_registry_entry_has_minimal_sidecar(built_vits, tmp_path):
    _, built = built_vits
    result = pack_directory(built.pack_dir, tmp_path / "dist")
    assert "license" not in result.sidecar
    assert result.sidecar["id"] == "zh-fake-v1"


def test_pack_refuses_invalid_directory_and_missing_identity(built_vits, tmp_path):
    _, built = built_vits
    (built.pack_dir / "tokens.txt").unlink()
    with pytest.raises(VoicePackError, match="invalid directory"):
        pack_directory(built.pack_dir, tmp_path / "dist")
    with pytest.raises(VoicePackError, match="not found"):
        pack_directory(tmp_path / "nowhere", tmp_path / "dist")


def test_pack_refuses_manifest_without_identity(built_vits, tmp_path):
    _, built = built_vits
    import json

    path = built.pack_dir / MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["packVersion"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(VoicePackError, match="packId / packVersion"):
        pack_directory(built.pack_dir, tmp_path / "dist")


def test_cc_by_sidecar_marks_attribution_required(tmp_path, vits_archive):
    from readori_voicepack.build import build_pack

    entry = make_entry(license={"spdx": "CC-BY-4.0", "attribution": "Credit X"})
    built = build_pack(entry, vits_archive, tmp_path / "out", repo_root=tmp_path)
    result = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry)
    assert result.sidecar["license"]["attributionRequired"] is True
    assert "Credit X" in (built.pack_dir / "readori-attribution.txt").read_text(encoding="utf-8")
