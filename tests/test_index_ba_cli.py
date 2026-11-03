from __future__ import annotations

import json
from pathlib import Path

import pytest
from readori_voicepack import index as ix
from readori_voicepack.bamanifest import build_ba_manifest
from readori_voicepack.cli import main
from readori_voicepack.common import MANIFEST_NAME, VoicePackError
from readori_voicepack.pack import pack_directory

from .conftest import make_entry, vits_files, write_registry, write_tar_bz2

REPO = "readori/readori-voice-packs"


# ----------------------------------------------------------------------------- index


def _sidecar(built_vits, tmp_path, **override):
    entry, built = built_vits
    result = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry)
    return {**result.sidecar, **override}


def test_index_entry_fields_and_url(built_vits, tmp_path):
    sidecar = _sidecar(built_vits, tmp_path)
    entry = ix.entry_from_sidecar(sidecar, REPO)
    assert entry["url"] == (
        "https://github.com/readori/readori-voice-packs/releases/download/"
        "pack/zh-fake-v1/v1/zh-fake-v1-v1.zip"
    )
    assert entry["id"] == "zh-fake-v1"
    assert entry["packVersion"] == 1
    assert entry["type"] == "vits"
    assert entry["speakerCount"] == 1
    assert entry["sha256"] == sidecar["sha256"]
    assert entry["bytes"] == sidecar["bytes"]
    assert entry["license"]["spdx"] == "Apache-2.0"
    assert entry["minAppVersion"] == "1.2.0"
    assert entry["appleAssetPackId"] == "readori.voice.zh-fake-v1"
    assert entry["displayName"]["en"] == "Fake Mandarin"
    assert entry["languages"] == ["zh-CN"]
    assert "modelBytes" not in entry and "file" not in entry


def test_index_rejects_bad_repo_and_bad_sidecar(built_vits, tmp_path):
    sidecar = _sidecar(built_vits, tmp_path)
    with pytest.raises(VoicePackError, match="invalid repository"):
        ix.entry_from_sidecar(sidecar, "not a repo")
    with pytest.raises(VoicePackError, match="invalid repository"):
        ix.entry_from_sidecar(sidecar, "a/b/../c")
    with pytest.raises(VoicePackError, match="invalid sha256"):
        ix.entry_from_sidecar({**sidecar, "sha256": "xyz"}, REPO)
    broken = dict(sidecar)
    del broken["bytes"]
    with pytest.raises(VoicePackError, match="missing 'bytes'"):
        ix.entry_from_sidecar(broken, REPO)


def test_update_index_merges_sorted_and_is_stable(built_vits, tmp_path):
    index_path = tmp_path / "catalog" / "v1" / "index.json"
    side_a = _sidecar(built_vits, tmp_path)
    side_b = {**side_a, "id": "aa-other-v1", "file": "aa-other-v1-v1.zip"}
    doc = ix.update_index(index_path, [side_a, side_b], REPO)
    assert [p["id"] for p in doc["packs"]] == ["aa-other-v1", "zh-fake-v1"]
    first_bytes = index_path.read_bytes()
    ix.update_index(index_path, [side_a, side_b], REPO)
    assert index_path.read_bytes() == first_bytes  # idempotent

    newer = {**side_a, "packVersion": 2, "file": "zh-fake-v1-v2.zip", "sha256": "b" * 64}
    doc = ix.update_index(index_path, [newer], REPO)
    entry = next(p for p in doc["packs"] if p["id"] == "zh-fake-v1")
    assert entry["packVersion"] == 2
    assert entry["url"].endswith("pack/zh-fake-v1/v2/zh-fake-v1-v2.zip")

    doc = ix.update_index(index_path, [side_a], REPO)  # older version never wins
    assert next(p for p in doc["packs"] if p["id"] == "zh-fake-v1")["packVersion"] == 2
    assert len(doc["packs"]) == 2


def test_load_index_rejects_foreign_documents(tmp_path):
    path = tmp_path / "index.json"
    path.write_text('{"schemaVersion": 2, "packs": []}', encoding="utf-8")
    with pytest.raises(VoicePackError, match="not a v1 index"):
        ix.load_index(path)
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(VoicePackError, match="not valid JSON"):
        ix.load_index(path)
    assert ix.load_index(tmp_path / "missing.json") == {"schemaVersion": 1, "packs": []}


def test_shipped_index_is_a_valid_empty_index():
    doc = ix.load_index(Path(__file__).resolve().parent.parent / "catalog" / "v1" / "index.json")
    assert doc == {"schemaVersion": 1, "packs": []}


def test_find_sidecars(built_vits, tmp_path):
    _sidecar(built_vits, tmp_path)
    found = ix.find_sidecars(tmp_path / "dist")
    assert [s["id"] for s in found] == ["zh-fake-v1"]
    (tmp_path / "dist" / "broken.zip.json").write_text("{", encoding="utf-8")
    with pytest.raises(VoicePackError, match="not valid JSON"):
        ix.find_sidecars(tmp_path / "dist")


# ----------------------------------------------------------------------------- Background Assets draft


def test_ba_manifest_draft_shape(built_vits):
    _, built = built_vits
    manifest = build_ba_manifest(built.pack_dir)
    assert manifest["assetPackID"] == "readori.voice.zh-fake-v1"
    assert manifest["downloadPolicy"] == {"onDemand": {}}
    assert manifest["platforms"] == ["iOS"]
    selectors = [s["file"] for s in manifest["fileSelectors"]]
    assert selectors == sorted(selectors)
    assert MANIFEST_NAME in selectors and "model.onnx" in selectors
    assert all(set(s) == {"file"} for s in manifest["fileSelectors"])


def test_ba_manifest_requires_pack_identity(built_vits):
    _, built = built_vits
    path = built.pack_dir / MANIFEST_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["packId"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(VoicePackError, match="no packId"):
        build_ba_manifest(built.pack_dir)


# ----------------------------------------------------------------------------- CLI end to end


@pytest.fixture
def cli_repo(tmp_path):
    """A registry with one approved fixture model plus a local upstream archive."""
    (tmp_path / "upstream").mkdir()
    archive = write_tar_bz2(tmp_path / "upstream" / "vits-fake.tar.bz2", vits_files(speakers=2))
    registry = write_registry(
        tmp_path,
        [
            make_entry(id="zh-fake-v1", preset={"speakerCount": 2}),
            make_entry(id="zh-blocked-v1", status="candidate"),
        ],
    )
    return tmp_path, registry, archive


def test_cli_end_to_end_build_validate_pack_index(cli_repo, capsys, monkeypatch):
    tmp_path, registry, archive = cli_repo
    build_dir = tmp_path / "build"
    dist = tmp_path / "dist"
    reg = ["--registry", str(registry)]

    assert main(["registry-check", *reg, "--select", "zh-fake-v1"]) == 0

    # upstream is unpinned in the fixture registry: refuse without --allow-unpinned
    assert main(["build", "zh-fake-v1", *reg, "--archive", str(archive), "--out", str(build_dir)]) == 1
    assert "pin it or pass --allow-unpinned" in capsys.readouterr().err

    assert main(["build", "zh-fake-v1", *reg, "--archive", str(archive), "--out", str(build_dir),
                 "--allow-unpinned"]) == 0  # fmt: skip
    out = capsys.readouterr().out
    assert "speakers:      2 (default 0)" in out
    pack_dir = build_dir / "zh-fake-v1"
    assert (pack_dir / MANIFEST_NAME).is_file()

    assert main(["validate", str(pack_dir)]) == 0
    assert "RESULT: PASS" in capsys.readouterr().out

    assert main(["pack", str(pack_dir), *reg, "--out", str(dist)]) == 0
    packed = capsys.readouterr().out
    zip_path = dist / "zh-fake-v1-v1.zip"
    assert zip_path.is_file()
    sha = next(line.split()[-1] for line in packed.splitlines() if line.startswith("sha256:"))
    assert len(sha) == 64

    assert main(["validate", str(zip_path)]) == 0
    capsys.readouterr()

    index_path = tmp_path / "catalog" / "v1" / "index.json"
    assert main(["index", "--sidecars", str(dist), "--repo", REPO, "--index", str(index_path)]) == 0
    doc = json.loads(index_path.read_text(encoding="utf-8"))
    assert doc["packs"][0]["sha256"] == sha
    assert doc["packs"][0]["speakerCount"] == 2

    assert main(["ba-manifest", str(pack_dir), "--out", str(tmp_path / "ba")]) == 0
    assert (tmp_path / "ba" / "readori.voice.zh-fake-v1.manifest.json").is_file()
    assert (tmp_path / "ba" / "readori.voice.zh-fake-v1.manifest.NOTES.txt").is_file()


def test_cli_blocked_pack_cannot_be_fetched_or_built(cli_repo, capsys):
    tmp_path, registry, archive = cli_repo
    reg = ["--registry", str(registry)]
    assert main(["fetch", "zh-blocked-v1", *reg, "--cache", str(tmp_path / "c")]) == 1
    assert "blocked by the license gate" in capsys.readouterr().err
    assert main(["build", "zh-blocked-v1", *reg, "--archive", str(archive), "--allow-unpinned"]) == 1
    assert "blocked by the license gate" in capsys.readouterr().err
    assert not (tmp_path / "build" / "packs" / "zh-blocked-v1").exists()


def test_cli_build_without_fetch_gives_hint(cli_repo, capsys):
    tmp_path, registry, _ = cli_repo
    code = main(["build", "zh-fake-v1", "--registry", str(registry), "--cache", str(tmp_path / "c"),
                 "--allow-unpinned"])  # fmt: skip
    assert code == 1
    assert "run 'fetch zh-fake-v1' first" in capsys.readouterr().err


def test_cli_validate_failure_exit_code(built_vits, capsys):
    _, built = built_vits
    (built.pack_dir / "tokens.txt").unlink()
    assert main(["validate", str(built.pack_dir)]) == 1
    out = capsys.readouterr().out
    assert "FAIL  tokens_missing" in out
    assert "RESULT: FAIL" in out


def test_cli_catalog_init(tmp_path, capsys):
    out = tmp_path / "voices.json"
    names = tmp_path / "names.txt"
    names.write_text("a\nb\n", encoding="utf-8")
    code = main(["catalog-init", "--speaker-count", "2", "--catalog-id", "x.y", "--language", "yue",
                 "--speaker-file", str(names), "--output", str(out)])  # fmt: skip
    assert code == 0
    catalog = json.loads(out.read_text(encoding="utf-8"))
    assert catalog["speakers"][1]["sourceSpeakerId"] == "b"
    assert main(["catalog-init", "--output", str(out)]) == 1  # missing required arguments
    assert "required" in capsys.readouterr().err


def test_cli_catalog_init_from_registry(cli_repo):
    tmp_path, registry, _ = cli_repo
    out = tmp_path / "v.json"
    assert main(["catalog-init", "--registry", str(registry), "--from-registry", "zh-fake-v1",
                 "--output", str(out)]) == 0  # fmt: skip
    catalog = json.loads(out.read_text(encoding="utf-8"))
    assert catalog["catalogId"] == "readori.zh-fake-v1"
    assert catalog["speakerCount"] == 2
    assert catalog["modelProfile"] == "vits-fake"


def test_cli_audit_skips_single_speaker_packs(built_vits, capsys):
    _, built = built_vits
    assert main(["audit", str(built.pack_dir), "--min-speakers", "2"]) == 0
    assert "audit skipped" in capsys.readouterr().out


def test_cli_smoke_and_audit_without_sherpa_fail_cleanly(built_vits, capsys, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "sherpa_onnx", None)
    _, built = built_vits
    assert main(["smoke", str(built.pack_dir)]) == 1
    assert "sherpa-onnx is not installed" in capsys.readouterr().err
    assert main(["audit", str(built.pack_dir)]) == 1
    assert "sherpa-onnx is not installed" in capsys.readouterr().err


def test_cli_registry_json_report(cli_repo, capsys):
    _, registry, _ = cli_repo
    assert main(["registry-check", "--registry", str(registry), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    by_id = {r["id"]: r for r in report}
    assert by_id["zh-fake-v1"]["buildable"] is True
    assert by_id["zh-fake-v1"]["pinned"] is False
    assert by_id["zh-blocked-v1"]["buildable"] is False
    assert main(["registry-check", "--registry", str(registry), "--require-pinned", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["buildable"] is False


def test_cli_missing_registry(tmp_path, capsys):
    assert main(["registry-check", "--registry", str(tmp_path / "none.yaml")]) == 1
    assert "registry not found" in capsys.readouterr().err
