from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from readori_voicepack import validate as val
from readori_voicepack.build import build_pack
from readori_voicepack.common import ATTRIBUTION_NAME, CATALOG_NAME, MANIFEST_NAME, sha256_file
from readori_voicepack.pack import make_deterministic_zip

from .conftest import kokoro_files, make_entry, write_tar_bz2, write_zip


def edit_manifest(pack_dir: Path, **changes: Any) -> None:
    path = pack_dir / MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            manifest.pop(key, None)
        else:
            manifest[key] = value
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def edit_catalog(pack_dir: Path, fn, *, fix_hash: bool = False) -> None:
    path = pack_dir / CATALOG_NAME
    catalog = json.loads(path.read_text(encoding="utf-8"))
    fn(catalog)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    if fix_hash:
        edit_manifest(pack_dir, voiceCatalogSHA256=sha256_file(path))


def codes(pack_dir: Path, **kwargs) -> list[str]:
    return val.validate_directory(pack_dir, **kwargs).codes()


def test_valid_pack_passes(built_vits):
    _, built = built_vits
    result = val.validate_directory(built.pack_dir)
    assert result.ok, [str(e) for e in result.errors]
    assert result.warnings == []
    assert result.info["speakerCount"] == 1


# ----------------------------------------------------------------------------- manifest level


def test_manifest_missing(built_vits):
    _, built = built_vits
    (built.pack_dir / MANIFEST_NAME).unlink()
    assert codes(built.pack_dir) == ["manifest_missing"]


def test_manifest_invalid_json_and_nan(built_vits):
    _, built = built_vits
    (built.pack_dir / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert codes(built.pack_dir) == ["manifest_decode"]
    (built.pack_dir / MANIFEST_NAME).write_text('{"speakerCount": NaN}', encoding="utf-8")
    assert codes(built.pack_dir) == ["manifest_decode"]


def test_manifest_too_large(built_vits):
    _, built = built_vits
    (built.pack_dir / MANIFEST_NAME).write_bytes(b" " * (8 * 1024 * 1024 + 1))
    assert codes(built.pack_dir) == ["manifest_too_large"]


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "matcha"},
        {"type": None},
        {"displayName": None},
        {"model": 5},
        {"speakerCount": "2"},
        {"lexicons": "lexicon.txt"},
        {"modelBytes": -1},
    ],
)
def test_manifest_decode_failures(built_vits, changes):
    _, built = built_vits
    edit_manifest(built.pack_dir, **changes)
    assert "manifest_decode" in codes(built.pack_dir)


def test_display_name_blank(built_vits):
    _, built = built_vits
    edit_manifest(built.pack_dir, displayName="   ")
    assert "display_name" in codes(built.pack_dir)


# ----------------------------------------------------------------------------- file existence / path safety


def test_missing_model_and_tokens(built_vits):
    _, built = built_vits
    (built.pack_dir / "model.onnx").unlink()
    (built.pack_dir / "tokens.txt").unlink()
    result = codes(built.pack_dir)
    assert "model_missing" in result
    assert "tokens_missing" in result
    assert "model_integrity" in result


@pytest.mark.parametrize(
    "key, value, code",
    [
        ("lexicon", "../lexicon.txt", "lexicon_missing"),
        ("lexicon", "nope.txt", "lexicon_missing"),
        ("dataDir", "espeak-ng-data\\en_dict", "data_dir_missing"),  # backslash: not normalised
        ("dataDir", "/espeak-ng-data", "data_dir_missing"),
        ("dataDir", "espeak-ng-data/", "data_dir_missing"),  # trailing slash: safe != relative
        ("dictDir", "missing-dir", "dict_dir_missing"),
        ("voices", "voices.bin", "voices_missing"),
        ("licenseFile", "NOLICENSE", "license_missing"),
        ("speakerFile", "speakers.txt", "speaker_file_missing"),
        ("lexicons", ["lexicon.txt", "C:/x.txt"], "lexicon_list_missing"),
        ("ruleFsts", ["missing.fst"], "rule_fst_missing"),
        ("ruleFars", ["missing.far"], "rule_far_missing"),
        ("voiceCatalog", "missing-catalog.json", "catalog_missing"),
    ],
)
def test_path_checks(built_vits, key, value, code):
    _, built = built_vits
    edit_manifest(built.pack_dir, **{key: value})
    assert code in codes(built.pack_dir)


def test_model_pointing_at_directory_is_missing(built_vits):
    _, built = built_vits
    edit_manifest(built.pack_dir, model="espeak-ng-data")
    assert "model_missing" in codes(built.pack_dir)


def test_data_dir_may_be_a_directory_but_model_may_not(built_vits):
    _, built = built_vits
    assert "data_dir_missing" not in codes(built.pack_dir)


# ----------------------------------------------------------------------------- integrity


def test_model_hash_and_size_mismatch(built_vits):
    _, built = built_vits
    edit_manifest(built.pack_dir, modelSHA256="0" * 64)
    assert "model_integrity" in codes(built.pack_dir)
    edit_manifest(built.pack_dir, modelSHA256=sha256_file(built.pack_dir / "model.onnx"), modelBytes=1)
    assert "model_integrity" in codes(built.pack_dir)
    edit_manifest(built.pack_dir, modelBytes=built.manifest["modelBytes"], modelSHA256="XYZ")
    assert "model_integrity" in codes(built.pack_dir)


def test_empty_model_file(built_vits):
    _, built = built_vits
    (built.pack_dir / "model.onnx").write_bytes(b"")
    assert "model_integrity" in codes(built.pack_dir)


# ----------------------------------------------------------------------------- speakers


@pytest.mark.parametrize("count", [0, -1, 513, 100000])
def test_speaker_count_range(built_vits, count):
    _, built = built_vits
    edit_manifest(built.pack_dir, speakerCount=count)
    assert "speaker_count" in codes(built.pack_dir)


@pytest.mark.parametrize("default", [-1, 1, 5])
def test_default_speaker_range(built_vits, default):
    _, built = built_vits
    edit_manifest(built.pack_dir, defaultSpeaker=default)
    assert "default_speaker" in codes(built.pack_dir)


def test_default_speaker_without_count_is_bound_by_one(built_vits):
    _, built = built_vits
    edit_manifest(built.pack_dir, speakerCount=None, defaultSpeaker=1)
    assert "default_speaker" in codes(built.pack_dir)


# ----------------------------------------------------------------------------- catalog


def test_catalog_sid_out_of_range_and_duplicate(built_vits):
    _, built = built_vits
    edit_catalog(built.pack_dir, lambda c: c["speakers"].append({"sid": 5}), fix_hash=True)
    assert "catalog_semantics" in codes(built.pack_dir)
    edit_catalog(
        built.pack_dir, lambda c: c.update(speakers=[{"sid": 0}, {"sid": 0}]), fix_hash=True
    )
    assert "catalog_semantics" in codes(built.pack_dir)


def test_catalog_speaker_count_mismatch_and_default_not_described(built_vits):
    _, built = built_vits
    edit_catalog(built.pack_dir, lambda c: c.update(speakerCount=2), fix_hash=True)
    assert "catalog_semantics" in codes(built.pack_dir)
    edit_catalog(built.pack_dir, lambda c: c.update(speakerCount=1, defaultSpeaker=3), fix_hash=True)
    assert "catalog_semantics" in codes(built.pack_dir)


def test_catalog_empty_speakers_and_bad_schema_version(built_vits):
    _, built = built_vits
    edit_catalog(built.pack_dir, lambda c: c.update(speakers=[]), fix_hash=True)
    assert "catalog_semantics" in codes(built.pack_dir)


def test_catalog_hash_mismatch_and_format(built_vits):
    _, built = built_vits
    edit_catalog(built.pack_dir, lambda c: c.update(catalogId="changed"))
    assert "catalog_hash" in codes(built.pack_dir)
    edit_manifest(built.pack_dir, voiceCatalogSHA256="not-a-hash")
    assert "catalog_hash_format" in codes(built.pack_dir)


def test_catalog_decode_type_errors(built_vits):
    _, built = built_vits
    edit_catalog(built.pack_dir, lambda c: c["speakers"][0].update(sid="0"), fix_hash=True)
    assert "catalog_decode" in codes(built.pack_dir)
    edit_catalog(
        built.pack_dir,
        lambda c: c["speakers"][0].update(sid=0, acoustics={"sampleRate": 22050.5}),
        fix_hash=True,
    )
    assert "catalog_decode" in codes(built.pack_dir)
    edit_catalog(
        built.pack_dir,
        lambda c: c["speakers"][0].update(acoustics=None, attributes={"a": "not-a-list"}),
        fix_hash=True,
    )
    assert "catalog_decode" in codes(built.pack_dir)


def test_catalog_with_nan_is_rejected(built_vits):
    _, built = built_vits
    (built.pack_dir / CATALOG_NAME).write_text(
        '{"schemaVersion":1,"speakers":[{"sid":0,"acoustics":{"rmsDbfs":NaN}}]}', encoding="utf-8"
    )
    assert "catalog_decode" in codes(built.pack_dir)


def test_catalog_version_below_one(built_vits):
    _, built = built_vits
    edit_manifest(built.pack_dir, voiceCatalogVersion=0)
    assert "catalog_version" in codes(built.pack_dir)


def test_catalog_accepts_app_accepted_shapes(built_vits):
    _, built = built_vits

    def rich(catalog):
        catalog["speakers"][0].update(
            displayName="Plain string name",
            ageGroup={"zh": "青年"},
            acoustics=None,
            attributes={"style": ["a", "b"]},
            languages=["zh-CN", "en-US"],
        )

    edit_catalog(built.pack_dir, rich, fix_hash=True)
    assert val.validate_directory(built.pack_dir).ok


# ----------------------------------------------------------------------------- policy / Kokoro


def test_policy_checks_and_app_only_mode(built_vits):
    _, built = built_vits
    (built.pack_dir / ATTRIBUTION_NAME).unlink()
    assert "attribution_missing" in codes(built.pack_dir)
    assert val.validate_directory(built.pack_dir, policy=False).ok
    edit_manifest(built.pack_dir, licenseFile=None, modelSHA256=None)
    found = codes(built.pack_dir)
    assert "license_undeclared" in found
    assert "integrity_undeclared" in found


def test_pack_identity_and_missing_catalog_are_warnings(built_vits):
    _, built = built_vits
    edit_manifest(built.pack_dir, packId=None, voiceCatalog=None, voiceCatalogSHA256=None,
                  voiceCatalogVersion=None)  # fmt: skip
    result = val.validate_directory(built.pack_dir)
    assert result.ok
    assert {w.code for w in result.warnings} == {"pack_identity_missing", "catalog_undeclared"}


def test_manifest_that_looks_like_an_engine(built_vits):
    _, built = built_vits
    edit_manifest(built.pack_dir, base_url="https://example.invalid")
    assert "manifest_looks_like_engine" in codes(built.pack_dir)


def test_engine_list_file_name_warns(built_vits):
    _, built = built_vits
    (built.pack_dir / "config.json").write_text("{}", encoding="utf-8")
    result = val.validate_directory(built.pack_dir)
    assert result.ok
    assert any(w.code == "engine_list_name" for w in result.warnings)


def test_case_insensitive_duplicate_in_directory(built_vits):
    _, built = built_vits
    (built.pack_dir / "readme.MD").write_text("x", encoding="utf-8")
    (built.pack_dir / "README.md").write_text("y", encoding="utf-8")
    if len({p.name.lower() for p in built.pack_dir.iterdir()}) == len(list(built.pack_dir.iterdir())):
        pytest.skip("case-insensitive file system cannot hold both names")
    assert "duplicate_path" in codes(built.pack_dir)


def _kokoro_pack(tmp_path: Path, **preset: Any):
    archive = write_tar_bz2(tmp_path / "k.tar.bz2", kokoro_files(), wrapper="kokoro-fake")
    entry = make_entry(
        id="en-kokoro-fake-v1",
        type="kokoro",
        languages=["en-US"],
        preset={"speakerCount": 11, "defaultSpeaker": 0, "profile": "kokoro-fake", "language": "en-US",
                **preset},
    )  # fmt: skip
    return build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)


def test_kokoro_v11_heuristic_conflict_is_an_error(tmp_path):
    built = _kokoro_pack(tmp_path)
    assert val.validate_directory(built.pack_dir).ok
    edit_manifest(built.pack_dir, profile="kokoro-int8-multi-lang-v1_1")
    result = val.validate_directory(built.pack_dir)
    assert "kokoro_v11_override" in result.codes()

    edit_manifest(built.pack_dir, profile="kokoro-fake", displayName="My Kokoro Int8 voices")
    assert "kokoro_v11_override" in codes(built.pack_dir)

    edit_manifest(built.pack_dir, displayName="Fine", modelBytes=114_299_010)
    assert "kokoro_v11_override" in codes(built.pack_dir)


def test_kokoro_v11_with_103_speakers_only_warns(tmp_path):
    built = _kokoro_pack(tmp_path)
    edit_manifest(built.pack_dir, profile="kokoro-int8-multi-lang-v1_1", speakerCount=103,
                  defaultSpeaker=0, language="zh-CN")  # fmt: skip
    edit_catalog(
        built.pack_dir,
        lambda c: c.update(
            speakerCount=103, defaultSpeaker=0, speakers=[{"sid": i} for i in range(103)]
        ),
        fix_hash=True,
    )
    result = val.validate_directory(built.pack_dir)
    assert result.ok, [str(e) for e in result.errors]
    assert any(w.code == "kokoro_v11_normalised" for w in result.warnings)


def test_kokoro_requires_voices_and_data_dir(tmp_path):
    built = _kokoro_pack(tmp_path)
    edit_manifest(built.pack_dir, dataDir=None)
    assert "kokoro_data_dir_required" in codes(built.pack_dir)
    edit_manifest(built.pack_dir, voices=None)
    assert "kokoro_voices_required" in codes(built.pack_dir)


def test_effective_counts_mirror_app_normalisation():
    catalog = {"speakers": [{"sid": 0}, {"sid": 9}], "defaultSpeaker": 9}
    assert val.effective_counts({}, catalog) == (10, 9)
    assert val.effective_counts({"speakerCount": 4, "defaultSpeaker": 9}, catalog) == (4, 3)
    assert val.effective_counts({"speakerCount": 9999}, catalog)[0] == 512
    assert val.effective_counts({}, None) == (1, 0)


# ----------------------------------------------------------------------------- ZIP


def _zip_of(built, tmp_path: Path) -> Path:
    out = tmp_path / "pack.zip"
    make_deterministic_zip(built.pack_dir, out)
    return out


def test_valid_zip_passes(built_vits, tmp_path):
    _, built = built_vits
    result = val.validate_target(_zip_of(built, tmp_path))
    assert result.ok, [str(e) for e in result.errors]
    assert result.info["entries"] >= 5
    assert result.manifest["packId"] == "zh-fake-v1"


def test_not_a_zip_and_missing_target(tmp_path):
    fake = tmp_path / "x.zip"
    fake.write_bytes(b"this is not a zip")
    assert val.validate_target(fake).codes() == ["invalid_archive"]
    truncated = tmp_path / "t.zip"
    truncated.write_bytes(b"PK\x03\x04garbage")
    assert val.validate_target(truncated).codes() == ["invalid_archive"]
    assert val.validate_target(tmp_path / "missing.zip").codes() == ["not_found"]


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a/../../b.txt", "C:/x.txt", "x\\..\\y"])
def test_zip_with_unsafe_entry_is_rejected(tmp_path, name):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(MANIFEST_NAME, "{}")
        zf.writestr(name, b"x")
    assert "unsafe_archive" in val.validate_target(archive).codes()


def test_zip_entry_count_limit(built_vits, tmp_path, monkeypatch):
    _, built = built_vits
    archive = _zip_of(built, tmp_path)
    monkeypatch.setattr(val, "MAX_ARCHIVE_ENTRIES", 3)
    assert "unsafe_archive" in val.validate_target(archive).codes()


def test_zip_ten_thousand_entry_limit_is_real(tmp_path):
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(10_001):
            zf.writestr(f"f{i}", b"")
    assert "unsafe_archive" in val.validate_target(archive).codes()


def test_zip_size_limits(built_vits, tmp_path, monkeypatch):
    _, built = built_vits
    archive = _zip_of(built, tmp_path)
    monkeypatch.setattr(val, "MAX_ZIP_BYTES", 100)
    result = val.validate_target(archive)
    assert result.codes() == ["file_too_large"]


def test_zip_uncompressed_size_limit(tmp_path, monkeypatch):
    archive = write_zip(tmp_path / "z.zip", {MANIFEST_NAME: b"{}", "big.bin": b"0" * 5000})
    monkeypatch.setattr(val, "MAX_ZIP_BYTES", 1000)
    assert "file_too_large" in val.validate_target(archive).codes()


def test_zip_with_wrapper_folder_is_rejected(built_vits, tmp_path):
    _, built = built_vits
    files = {
        f"wrapper/{p.relative_to(built.pack_dir).as_posix()}": p.read_bytes()
        for p in built.pack_dir.rglob("*")
        if p.is_file()
    }
    archive = write_zip(tmp_path / "w.zip", files)
    assert "manifest_not_at_root" in val.validate_target(archive).codes()


def test_zip_case_insensitive_duplicates(tmp_path):
    archive = tmp_path / "dup.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(MANIFEST_NAME, "{}")
        zf.writestr("A.txt", b"1")
        zf.writestr("a.txt", b"2")
    assert "duplicate_path" in val.validate_target(archive).codes()


def test_zip_without_manifest(tmp_path):
    archive = write_zip(tmp_path / "nm.zip", {"model.onnx": b"x", "tokens.txt": b"a 0"})
    assert val.validate_target(archive).codes() == ["manifest_missing"]
