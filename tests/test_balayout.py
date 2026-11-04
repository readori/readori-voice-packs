from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from readori_voicepack import balayout as bl
from readori_voicepack.cli import main
from readori_voicepack.common import VoicePackError

PREFIX = bl.RELEASE_URL_PREFIX


def _entry(pack_id: str, data: bytes, *, apple: str | None = "default", **extra) -> dict:
    version = extra.pop("packVersion", 1)
    entry = {
        "id": pack_id,
        "packVersion": version,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "url": f"{PREFIX}pack/{pack_id}/v{version}/{pack_id}-v{version}.zip",
        **extra,
    }
    if apple == "default":
        entry["appleAssetPackId"] = f"readori.voice.{pack_id}"
    elif apple is not None:
        entry["appleAssetPackId"] = apple
    return entry


@pytest.fixture
def world(tmp_path):
    """An index with two Apple packs, one without appleAssetPackId, one community pack."""
    blobs = {
        "zh-a-v1": b"zip-bytes-a" * 50,
        "en-b-v1": b"zip-bytes-b" * 70,
        "zh-none-v1": b"zip-bytes-n" * 10,
        "yue-comm-v1": b"zip-bytes-c" * 20,
    }
    zips = tmp_path / "zips"
    zips.mkdir()
    for pack_id, data in blobs.items():
        (zips / f"{pack_id}-v1.zip").write_bytes(data)
    index = {
        "schemaVersion": 1,
        "packs": [
            _entry("en-b-v1", blobs["en-b-v1"]),
            _entry("yue-comm-v1", blobs["yue-comm-v1"], apple=None, tier="community"),
            _entry("zh-a-v1", blobs["zh-a-v1"]),
            _entry("zh-none-v1", blobs["zh-none-v1"], apple=None),
        ],
    }
    return index, zips, blobs, tmp_path / "out"


def test_layout_paths_and_bytes(world):
    index, zips, blobs, out = world
    results = bl.build_layout(index, zips, out)
    assert [r.plan.pack_id for r in results] == ["en-b-v1", "zh-a-v1"]
    for r in results:
        pid = r.plan.pack_id
        asset = f"readori.voice.{pid}"
        assert r.pack_root == out / asset
        assert r.zip_path == out / asset / pid / f"{pid}.zip"
        assert r.zip_path.read_bytes() == blobs[pid]
        assert r.manifest_path == out / f"{asset}.manifest.json"
        # the pack root only holds the packId folder with the single ZIP (shared namespace prefix)
        files = sorted(
            p.relative_to(r.pack_root).as_posix() for p in r.pack_root.rglob("*") if p.is_file()
        )
        assert files == [f"{pid}/{pid}.zip"]


def test_skips_null_apple_id_and_community(world):
    index, zips, _, out = world
    bl.build_layout(index, zips, out)
    assert sorted(p.name for p in out.iterdir() if p.is_dir()) == [
        "readori.voice.en-b-v1",
        "readori.voice.zh-a-v1",
    ]
    # community pack stays out even if somebody gave it an appleAssetPackId
    for entry in index["packs"]:
        if entry["id"] == "yue-comm-v1":
            entry["appleAssetPackId"] = "readori.voice.yue-comm-v1"
    assert [p.pack_id for p in bl.plan_entries(index)] == ["en-b-v1", "zh-a-v1"]


def test_explicit_ids_must_be_eligible(world):
    index, zips, _, out = world
    with pytest.raises(VoicePackError, match="no appleAssetPackId"):
        bl.build_layout(index, zips, out, pack_ids=["zh-none-v1"])
    with pytest.raises(VoicePackError, match="community tier"):
        bl.plan_entries(index, ["yue-comm-v1"])
    with pytest.raises(VoicePackError, match="not in the index"):
        bl.plan_entries(index, ["nope-v1"])
    results = bl.build_layout(index, zips, out, pack_ids=["zh-a-v1"])
    assert [r.plan.pack_id for r in results] == ["zh-a-v1"]
    assert not (out / "readori.voice.en-b-v1").exists()


def test_nothing_to_lay_out_fails(world):
    index, zips, _, out = world
    index["packs"] = [p for p in index["packs"] if "appleAssetPackId" not in p]
    with pytest.raises(VoicePackError, match="nothing to lay out"):
        bl.build_layout(index, zips, out)


def test_sha_mismatch_fails_and_leaves_nothing(world):
    index, zips, _, out = world
    (zips / "zh-a-v1-v1.zip").write_bytes(b"x" * len(b"zip-bytes-a" * 50))  # same size, other bytes
    with pytest.raises(VoicePackError, match="sha256"):
        bl.build_layout(index, zips, out, pack_ids=["zh-a-v1"])
    assert not (out / "readori.voice.zh-a-v1").exists()
    assert not (out / "readori.voice.zh-a-v1.manifest.json").exists()


def test_bytes_mismatch_fails(world):
    index, zips, _, out = world
    for entry in index["packs"]:
        if entry["id"] == "en-b-v1":
            entry["bytes"] += 1
    with pytest.raises(VoicePackError, match="bytes"):
        bl.build_layout(index, zips, out, pack_ids=["en-b-v1"])


def test_missing_zip_and_nested_cache_dir(world):
    index, zips, _, out = world
    (zips / "zh-a-v1-v1.zip").rename(zips / "elsewhere.zip")
    with pytest.raises(VoicePackError, match="not found"):
        bl.build_layout(index, zips, out, pack_ids=["zh-a-v1"])
    nested = zips / "pack-zh-a-v1"
    nested.mkdir()
    (zips / "elsewhere.zip").rename(nested / "zh-a-v1-v1.zip")  # download-artifact style folder
    assert bl.build_layout(index, zips, out, pack_ids=["zh-a-v1"])[0].zip_path.is_file()


def test_manifest_fill_overrides_ours_and_keeps_unknown_template_fields(world):
    index, zips, _, out = world
    template = {
        "assetPackID": "",
        "downloadPolicy": {"essential": {"installationEventTypes": ["firstInstallation"]}},
        "fileSelectors": [{"directory": "Path/To/Directory"}],
        "platforms": ["macOS"],
        "futureKey": {"nested": [1, 2, 3]},
        "schemaVersion": 7,
    }
    frozen = copy.deepcopy(template)
    result = bl.build_layout(index, zips, out, template=template, pack_ids=["en-b-v1"])[0]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["assetPackID"] == "readori.voice.en-b-v1"
    assert manifest["downloadPolicy"] == {"onDemand": {}}
    assert manifest["fileSelectors"] == [{"file": "en-b-v1/en-b-v1.zip"}]
    assert manifest["platforms"] == ["iOS"]
    assert manifest["futureKey"] == {"nested": [1, 2, 3]}
    assert manifest["schemaVersion"] == 7
    assert template == frozen  # the template object is not mutated


def test_default_template_manifest_shape(world):
    index, zips, _, out = world
    result = bl.build_layout(index, zips, out, pack_ids=["zh-a-v1"])[0]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert set(manifest) == {"assetPackID", "downloadPolicy", "fileSelectors", "platforms"}


def test_packid_prefix_and_unsafe_ids_rejected(world):
    index, zips, _, out = world
    plan = bl.plan_entries(index, ["zh-a-v1"])[0]
    assert plan.inner_path == "zh-a-v1/zh-a-v1.zip"
    for bad in ("../evil", "a/b", "x..y", "-lead", ""):
        broken = copy.deepcopy(index)
        for entry in broken["packs"]:
            if entry["id"] == "zh-a-v1":
                entry["appleAssetPackId"] = bad
        with pytest.raises(VoicePackError, match="appleAssetPackId"):
            bl.plan_entries(broken, ["zh-a-v1"])
    broken = copy.deepcopy(index)
    broken["packs"][0]["id"] = "../x"
    with pytest.raises(VoicePackError, match="invalid id"):
        bl.plan_entries(broken)


def test_url_must_be_the_release_download_prefix(world):
    index, _, _, _ = world
    for entry in index["packs"]:
        if entry["id"] == "zh-a-v1":
            entry["url"] = "https://evil.example/pack/zh-a-v1/v1/zh-a-v1-v1.zip"
    with pytest.raises(VoicePackError, match="url must be"):
        bl.plan_entries(index, ["zh-a-v1"])


def test_duplicate_asset_pack_ids_rejected(world):
    index, _, _, _ = world
    for entry in index["packs"]:
        entry["appleAssetPackId"] = "readori.voice.same" if entry.get("appleAssetPackId") else None
    index["packs"] = [{k: v for k, v in e.items() if v is not None} for e in index["packs"]]
    with pytest.raises(VoicePackError, match="share one appleAssetPackId"):
        bl.plan_entries(index)


def test_hardlink_option_falls_back_to_a_verified_copy(world):
    index, zips, blobs, out = world
    result = bl.build_layout(index, zips, out, pack_ids=["zh-a-v1"], hardlink=True)[0]
    assert result.zip_path.read_bytes() == blobs["zh-a-v1"]


def test_load_template(tmp_path):
    assert bl.load_template(None)["platforms"] == ["iOS"]
    path = tmp_path / "t.json"
    path.write_text("[1]", encoding="utf-8")
    with pytest.raises(VoicePackError, match="not a JSON object"):
        bl.load_template(path)
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(VoicePackError, match="not valid JSON"):
        bl.load_template(path)
    with pytest.raises(VoicePackError, match="not found"):
        bl.load_template(tmp_path / "none.json")


def _write_index(tmp_path: Path, index: dict) -> Path:
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    return path


def test_cli_plan_and_layout(world, capsys):
    index, zips, _, out = world
    index_path = _write_index(out.parent, index)
    assert main(["ba-layout", "--index", str(index_path), "--plan"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert [p["id"] for p in plan] == ["en-b-v1", "zh-a-v1"]
    assert plan[0]["url"].startswith(PREFIX) and len(plan[0]["sha256"]) == 64

    template = out.parent / "template.json"
    template.write_text(json.dumps({"assetPackID": "", "extra": True}), encoding="utf-8")
    code = main(["ba-layout", "--index", str(index_path), "--zips", str(zips), "--out", str(out),
                 "--template", str(template), "--pack-ids", "zh-a-v1"])  # fmt: skip
    assert code == 0
    assert "package from:" in capsys.readouterr().out
    manifest = json.loads((out / "readori.voice.zh-a-v1.manifest.json").read_text(encoding="utf-8"))
    assert manifest["extra"] is True


def test_cli_failures(world, capsys):
    index, zips, _, out = world
    index_path = _write_index(out.parent, index)
    assert main(["ba-layout", "--index", str(index_path)]) == 1
    assert "--zips and --out are required" in capsys.readouterr().err
    assert main(["ba-layout", "--index", str(out.parent / "none.json"), "--plan"]) == 1
    assert "index not found" in capsys.readouterr().err
    (zips / "zh-a-v1-v1.zip").write_bytes(b"corrupt")
    assert (
        main(["ba-layout", "--index", str(index_path), "--zips", str(zips), "--out", str(out)]) == 1
    )
    assert "the index says" in capsys.readouterr().err
