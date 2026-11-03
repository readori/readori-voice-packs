"""Shared fixtures: tiny fake sherpa-onnx models (fake .onnx bytes), no network."""
from __future__ import annotations

import copy
import io
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from readori_voicepack.build import build_pack
from readori_voicepack.common import sha256_file

FAKE_MODEL = b"fake-onnx-model-bytes-" * 128
FAKE_VOICES = b"fake-voices-bin" * 32
LICENSE_TEXT = b"Apache License\nVersion 2.0, January 2004\n(fixture text)\n"
GPL_TEXT = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n(fixture text)\n"
ESPEAK_COMPONENT = {
    "name": "espeak-ng-data",
    "spdx": "GPL-3.0-or-later",
    "url": "https://www.gnu.org/licenses/gpl-3.0.txt",
    "sourceURL": "https://github.com/espeak-ng/espeak-ng",
    "role": "data",
}


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def make_entry(**override: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "zh-fake-v1",
        "packVersion": 1,
        "displayName": {"en": "Fake Mandarin", "zh-Hans": "测试普通话", "zh-Hant": "測試普通話"},
        "languages": ["zh-CN"],
        "type": "vits",
        "appSupported": True,
        "upstream": {
            "url": "https://example.invalid/tts-models/vits-fake.tar.bz2",
            "sha256": "TODO",
            "bytes": "TODO",
        },
        "license": {
            "spdx": "Apache-2.0",
            "url": "https://example.invalid/LICENSE",
            "evidence": [
                {"url": "https://example.invalid/README.md", "note": "states Apache-2.0"},
            ],
            "components": [dict(ESPEAK_COMPONENT)],
            "commercialUse": True,
            "redistribution": True,
            "author": "Fixture Author",
            "dataset": {
                "name": "Fixture dataset",
                "spdx": "Apache-2.0",
                "url": "https://example.invalid/data",
                "commercialUse": True,
            },
        },
        "preset": {"speakerCount": 1, "defaultSpeaker": 0, "profile": "vits-fake", "language": "zh-CN"},
        "minAppVersion": "1.2.0",
        "status": "approved",
    }
    return merge(base, override)


def vits_files(*, license_file: bool = True, speakers: int | None = None) -> dict[str, bytes]:
    files = {
        "model.onnx": FAKE_MODEL,
        "tokens.txt": b"a 0\nb 1\n",
        "lexicon.txt": b"a a\n",
        "espeak-ng-data/en_dict": b"dict",
        "README.md": b"upstream readme",
        "test_wavs/0.wav": b"RIFFxxxx",
        "helper.py": b"print('hi')",
    }
    if license_file:
        files["LICENSE"] = LICENSE_TEXT
    if speakers:
        files["speakers.txt"] = "\n".join(f"spk{i}" for i in range(speakers)).encode() + b"\n"
    return files


def kokoro_files() -> dict[str, bytes]:
    return {
        "model.int8.onnx": FAKE_MODEL,
        "voices.bin": FAKE_VOICES,
        "tokens.txt": b"a 0\n",
        "espeak-ng-data/en_dict": b"dict",
        "lexicon-us-en.txt": b"a a\n",
        "lexicon-zh.txt": b"b b\n",
        "lexicon-gb-en.txt": b"c c\n",
        "LICENSE": LICENSE_TEXT,
    }


def write_tar_bz2(path: Path, files: dict[str, bytes], wrapper: str | None = "vits-fake") -> Path:
    with tarfile.open(path, "w:bz2") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{wrapper}/{name}" if wrapper else name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def write_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def write_registry(root: Path, entries: list[dict[str, Any]]) -> Path:
    (root / "registry").mkdir(parents=True, exist_ok=True)
    path = root / "registry" / "models.yaml"
    path.write_text(
        yaml.safe_dump({"schemaVersion": 1, "models": entries}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture(autouse=True)
def gpl_text(tmp_path: Path) -> Path:
    """Repository copy of the GPL-3.0 text (fixture content) used for espeak-ng-data packs."""
    path = tmp_path / "registry" / "license-texts" / "GPL-3.0.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(GPL_TEXT, encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def vits_archive(tmp_path: Path) -> Path:
    return write_tar_bz2(tmp_path / "vits-fake.tar.bz2", vits_files())


@pytest.fixture
def built_vits(tmp_path: Path, vits_archive: Path):
    entry = make_entry()
    result = build_pack(
        entry,
        vits_archive,
        tmp_path / "out",
        repo_root=tmp_path,
        archive_sha256=sha256_file(vits_archive),
    )
    return entry, result
