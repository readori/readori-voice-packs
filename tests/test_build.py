from __future__ import annotations

import json

import pytest
from readori_voicepack.build import build_pack
from readori_voicepack.common import (
    ATTRIBUTION_NAME,
    CATALOG_NAME,
    MANIFEST_NAME,
    VoicePackError,
    sha256_file,
    write_json,
)
from readori_voicepack.validate import validate_directory

from .conftest import FAKE_MODEL, kokoro_files, make_entry, vits_files, write_tar_bz2

# Field names of SherpaOnnxModelManifest (TTSEnginePackageImporter.swift:32-67). The generated
# manifest may only add packId / packVersion, which the app's synthesized Codable ignores.
APP_MANIFEST_FIELDS = {
    "type", "displayName", "model", "tokens", "dataDir", "lexicon", "lexicons", "voices",
    "language", "speakerCount", "defaultSpeaker", "ruleFsts", "ruleFars", "dictDir",
    "licenseFile", "sourceURL", "profile", "modelBytes", "modelSHA256", "voiceCatalog",
    "voiceCatalogVersion", "voiceCatalogSHA256", "speakerFile",
}  # fmt: skip
EXTRA_FIELDS = {"packId", "packVersion"}


def _manifest(pack_dir):
    return json.loads((pack_dir / MANIFEST_NAME).read_text(encoding="utf-8"))


def test_manifest_fields_match_app_schema(built_vits):
    entry, result = built_vits
    manifest = _manifest(result.pack_dir)
    assert set(manifest) <= APP_MANIFEST_FIELDS | EXTRA_FIELDS
    assert EXTRA_FIELDS <= set(manifest)
    assert None not in manifest.values()
    assert manifest["type"] == "vits"
    assert manifest["displayName"] == "Fake Mandarin"
    assert manifest["model"] == "model.onnx"
    assert manifest["tokens"] == "tokens.txt"
    assert manifest["dataDir"] == "espeak-ng-data"
    assert manifest["lexicon"] == "lexicon.txt"
    assert manifest["lexicons"] == ["lexicon.txt"]
    assert manifest["language"] == "zh-CN"
    assert manifest["speakerCount"] == 1
    assert manifest["defaultSpeaker"] == 0
    assert manifest["profile"] == "vits-fake"
    assert manifest["licenseFile"] == "LICENSE"
    assert manifest["sourceURL"] == entry["upstream"]["url"]
    assert manifest["packId"] == "zh-fake-v1"
    assert manifest["packVersion"] == 1


def test_integrity_fields_are_correct(built_vits):
    _, result = built_vits
    manifest = _manifest(result.pack_dir)
    model = result.pack_dir / "model.onnx"
    assert manifest["modelBytes"] == len(FAKE_MODEL) == model.stat().st_size
    assert manifest["modelSHA256"] == sha256_file(model)
    assert manifest["voiceCatalog"] == CATALOG_NAME
    assert manifest["voiceCatalogVersion"] == 1
    assert manifest["voiceCatalogSHA256"] == sha256_file(result.pack_dir / CATALOG_NAME)


def test_excludes_and_generated_files(built_vits):
    _, result = built_vits
    files = {p.relative_to(result.pack_dir).as_posix() for p in result.pack_dir.rglob("*") if p.is_file()}
    assert "test_wavs/0.wav" not in files
    assert "helper.py" not in files
    assert {"model.onnx", "tokens.txt", "LICENSE", "README.md", ATTRIBUTION_NAME, CATALOG_NAME,
            MANIFEST_NAME} <= files  # fmt: skip
    assert not (result.pack_dir / "test_wavs").exists()


def test_attribution_file_content(built_vits):
    entry, result = built_vits
    text = (result.pack_dir / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert "Fake Mandarin" in text
    assert "Apache-2.0" in text
    assert entry["upstream"]["url"] in text
    assert "Fixture Author" in text
    assert "Fixture dataset" in text
    assert "Modifications by Readori" in text
    assert "LICENSE" in text
    assert "2026" not in text  # deterministic: no timestamps are embedded


def test_built_pack_passes_validation(built_vits):
    _, result = built_vits
    check = validate_directory(result.pack_dir)
    assert check.ok, [str(e) for e in check.errors]


def test_generated_catalog_has_only_facts(built_vits):
    _, result = built_vits
    catalog = json.loads((result.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    assert catalog["speakerCount"] == 1
    assert catalog["speakers"] == [{"sid": 0, "analysisTags": [], "language": "zh-CN"}]
    for key in ("gender", "accent", "ageGroup"):
        assert key not in catalog["speakers"][0]


def test_build_is_repeatable(tmp_path, vits_archive):
    entry = make_entry()
    first = build_pack(entry, vits_archive, tmp_path / "a", repo_root=tmp_path)
    second = build_pack(entry, vits_archive, tmp_path / "b", repo_root=tmp_path)
    assert (first.pack_dir / MANIFEST_NAME).read_bytes() == (second.pack_dir / MANIFEST_NAME).read_bytes()
    assert (first.pack_dir / ATTRIBUTION_NAME).read_bytes() == (second.pack_dir / ATTRIBUTION_NAME).read_bytes()


def test_multi_speaker_with_speaker_file_and_repo_catalog(tmp_path):
    archive = write_tar_bz2(tmp_path / "m.tar.bz2", vits_files(speakers=3))
    catalog = {
        "schemaVersion": 1,
        "catalogId": "fixture.multi",
        "speakerCount": 3,
        "defaultSpeaker": 1,
        "speakers": [{"sid": i, "sourceSpeakerId": f"spk{i}", "gender": "female"} for i in range(3)],
    }
    write_json(tmp_path / "registry" / "voice-catalogs" / "multi.json", catalog)
    entry = make_entry(
        id="zh-multi-v1",
        preset={"speakerCount": 3, "defaultSpeaker": 1},
        voiceCatalog="registry/voice-catalogs/multi.json",
    )
    result = build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)
    manifest = result.manifest
    assert manifest["speakerCount"] == 3
    assert manifest["defaultSpeaker"] == 1
    assert manifest["speakerFile"] == "speakers.txt"
    assert validate_directory(result.pack_dir).ok


def test_generated_catalog_uses_speaker_names(tmp_path):
    archive = write_tar_bz2(tmp_path / "m.tar.bz2", vits_files(speakers=2))
    entry = make_entry(id="zh-two-v1", preset={"speakerCount": 2})
    result = build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)
    catalog = json.loads((result.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    assert [s["sourceSpeakerId"] for s in catalog["speakers"]] == ["spk0", "spk1"]


def test_speaker_file_count_mismatch_rejected(tmp_path):
    archive = write_tar_bz2(tmp_path / "m.tar.bz2", vits_files(speakers=3))
    entry = make_entry(preset={"speakerCount": 2})
    with pytest.raises(VoicePackError, match="speaker count mismatch"):
        build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)


def test_catalog_inconsistent_with_pack_rejected(tmp_path, vits_archive):
    write_json(
        tmp_path / "registry" / "voice-catalogs" / "bad.json",
        {"schemaVersion": 1, "speakerCount": 5, "speakers": [{"sid": 0}]},
    )
    entry = make_entry(voiceCatalog="registry/voice-catalogs/bad.json")
    with pytest.raises(VoicePackError, match="inconsistent"):
        build_pack(entry, vits_archive, tmp_path / "out", repo_root=tmp_path)


def test_missing_license_requires_text_file(tmp_path):
    archive = write_tar_bz2(tmp_path / "nl.tar.bz2", vits_files(license_file=False))
    with pytest.raises(VoicePackError, match="no LICENSE file"):
        build_pack(make_entry(), archive, tmp_path / "out", repo_root=tmp_path)

    (tmp_path / "registry" / "licenses").mkdir(parents=True)
    (tmp_path / "registry" / "licenses" / "apache.txt").write_text("Apache text", encoding="utf-8")
    entry = make_entry(license={"textFile": "registry/licenses/apache.txt"})
    result = build_pack(entry, archive, tmp_path / "out2", repo_root=tmp_path)
    assert result.manifest["licenseFile"] == "LICENSE"
    assert (result.pack_dir / "LICENSE").read_text(encoding="utf-8") == "Apache text"


def test_missing_model_or_tokens(tmp_path):
    files = vits_files()
    del files["model.onnx"]
    archive = write_tar_bz2(tmp_path / "nm.tar.bz2", files)
    with pytest.raises(VoicePackError, match="model / tokens not found"):
        build_pack(make_entry(), archive, tmp_path / "out", repo_root=tmp_path)


def test_upstream_generated_files_are_replaced(tmp_path):
    files = vits_files()
    files[MANIFEST_NAME] = b'{"type": "vits", "url": "https://evil.invalid"}'
    files[ATTRIBUTION_NAME] = b"upstream-written attribution"
    archive = write_tar_bz2(tmp_path / "u.tar.bz2", files)
    result = build_pack(make_entry(), archive, tmp_path / "out", repo_root=tmp_path)
    assert "evil.invalid" not in (result.pack_dir / MANIFEST_NAME).read_text(encoding="utf-8")
    assert "upstream-written" not in (result.pack_dir / ATTRIBUTION_NAME).read_text(encoding="utf-8")


def test_case_colliding_names_rejected(tmp_path):
    files = vits_files()
    files["Tokens.txt"] = b"dup"
    archive = write_tar_bz2(tmp_path / "c.tar.bz2", files)
    with pytest.raises(VoicePackError, match="differing only by case"):
        build_pack(make_entry(), archive, tmp_path / "out", repo_root=tmp_path)


def test_preset_force_none_and_explicit_rules(tmp_path):
    files = vits_files()
    files.update({"dict/jieba.dict": b"d", "date.fst": b"1", "phone.fst": b"2", "number.fst": b"3"})
    archive = write_tar_bz2(tmp_path / "p.tar.bz2", files)
    auto = build_pack(make_entry(), archive, tmp_path / "auto", repo_root=tmp_path)
    assert auto.manifest["dictDir"] == "dict"
    assert auto.manifest["ruleFsts"] == ["phone.fst", "date.fst", "number.fst"]  # v13 order

    entry = make_entry(preset={"dictDir": None, "ruleFsts": ["date.fst", "phone.fst", "number.fst"]})
    forced = build_pack(entry, archive, tmp_path / "forced", repo_root=tmp_path)
    assert "dictDir" not in forced.manifest
    assert forced.manifest["ruleFsts"] == ["date.fst", "phone.fst", "number.fst"]


def test_preset_path_must_exist(tmp_path, vits_archive):
    entry = make_entry(preset={"model": "nope.onnx"})
    with pytest.raises(VoicePackError, match="preset model not found"):
        build_pack(entry, vits_archive, tmp_path / "out", repo_root=tmp_path)


def test_display_language_selection(tmp_path, vits_archive):
    result = build_pack(
        make_entry(), vits_archive, tmp_path / "out", repo_root=tmp_path, display_lang="zh-Hans"
    )
    assert result.manifest["displayName"] == "测试普通话"
    with pytest.raises(VoicePackError, match="unknown display language"):
        build_pack(make_entry(), vits_archive, tmp_path / "o2", repo_root=tmp_path, display_lang="fr")


def test_kokoro_build_lexicon_order_and_requirements(tmp_path):
    archive = write_tar_bz2(tmp_path / "k.tar.bz2", kokoro_files(), wrapper="kokoro-fake")
    entry = make_entry(
        id="en-kokoro-fake-v1",
        type="kokoro",
        languages=["en-US"],
        preset={
            "speakerCount": 11,
            "defaultSpeaker": 0,
            "profile": "kokoro-fake",
            "language": "en-US",
            "officialBilingualLexicons": True,
        },
    )
    result = build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)
    manifest = result.manifest
    assert manifest["type"] == "kokoro"
    assert manifest["model"] == "model.int8.onnx"
    assert manifest["voices"] == "voices.bin"
    assert manifest["lexicons"] == ["lexicon-us-en.txt", "lexicon-zh.txt"]
    assert manifest["lexicon"] == "lexicon-us-en.txt"
    assert validate_directory(result.pack_dir).ok

    no_voices = kokoro_files()
    del no_voices["voices.bin"]
    archive2 = write_tar_bz2(tmp_path / "k2.tar.bz2", no_voices, wrapper="kokoro-fake")
    with pytest.raises(VoicePackError, match="voices"):
        build_pack(entry, archive2, tmp_path / "out2", repo_root=tmp_path)


def test_unsupported_type_refused(tmp_path, vits_archive):
    entry = make_entry(type="matcha", appSupported=False)
    with pytest.raises(VoicePackError, match="not supported by the app"):
        build_pack(entry, vits_archive, tmp_path / "out", repo_root=tmp_path)
