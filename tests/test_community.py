"""Community tier: licence UNKNOWN is accepted, known-prohibited and game-character voices are not."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from readori_voicepack import index as ix
from readori_voicepack import registry as reg
from readori_voicepack.bamanifest import build_ba_manifest
from readori_voicepack.build import build_pack
from readori_voicepack.cli import main
from readori_voicepack.common import (
    ATTRIBUTION_NAME,
    COMMUNITY_NOTICE,
    VoicePackError,
)
from readori_voicepack.pack import pack_directory

from .conftest import make_entry, merge, vits_files, write_registry, write_tar_bz2

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO = "readori/readori-voice-packs"
NOTICE_REL = "registry/license-texts/COMMUNITY-NOTICE.txt"

COMMUNITY_IDS = {
    "yue-cantonese-v1",
    "zh-vits-zh-ll-v1",
    "zh-vits-zh-hf-fanchen-c-v1",
    "zh-vits-zh-hf-fanchen-zhihuilaozhe-v1",
    "zh-vits-zh-hf-fanchen-zhihuilaozhe-new-v1",
    "zh-vits-zh-hf-fanchen-unity-v1",
    "zh-vits-zh-hf-fanchen-wnj-v1",
    "zh-piper-huayan-medium-v1",
}
GAME_CHARACTER_IDS = {
    f"zh-vits-zh-hf-{name}-v1"
    for name in ("theresa", "eula", "keqing", "bronya", "doom", "echo", "abyssinvoker", "zenyatta")
}
KNOWN_NON_COMMERCIAL_IDS = {"zh-piper-xiao-ya-medium-v1", "zh-piper-chaowen-medium-v1", "zh-nan-mms-v1"}


def community_entry(**override):
    base = make_entry(
        id="zh-comm-v1",
        status="community",
        communityNote="Licence unverified; collected from the community.",
        license={
            "spdx": "UNKNOWN",
            "url": "TODO",
            "evidence": "TODO",
            "commercialUse": "unknown",
            "redistribution": "unknown",
            "textFile": NOTICE_REL,
            "dataset": {"name": "undisclosed", "spdx": "undisclosed", "commercialUse": "unknown"},
        },
    )
    return merge(base, override)


# ----------------------------------------------------------------------------- schema and gate


def test_community_entry_with_unknown_licence_passes_the_gate():
    entry = community_entry()
    assert reg.validate_entry_schema(entry, 0) == []
    assert reg.evaluate_gate(entry) == []
    assert reg.evaluate_gate(entry, require_pinned=False, for_publish=True) == []


def test_community_requires_note_but_not_excluded_reason():
    entry = community_entry()
    assert "excludedReason" not in entry
    del entry["communityNote"]
    assert any("communityNote" in e for e in reg.validate_entry_schema(entry, 0))
    entry["communityNote"] = "  "
    assert any("communityNote" in e for e in reg.validate_entry_schema(entry, 0))


def test_game_character_flag_must_be_boolean():
    assert any(
        "gameCharacterVoice" in e
        for e in reg.validate_entry_schema(community_entry(gameCharacterVoice="yes"), 0)
    )


@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"license": {"commercialUse": False}}, "commercialUse"),
        ({"license": {"redistribution": False}}, "redistribution"),
        ({"license": {"spdx": "CC-BY-NC-4.0"}}, "non-commercial"),
        ({"license": {"spdx": "Research use only"}}, "non-commercial"),
        ({"license": {"dataset": {"commercialUse": False}}}, "dataset"),
        ({"license": {"dataset": {"spdx": "CC-BY-NC-SA-4.0"}}}, "dataset license"),
        ({"gameCharacterVoice": True}, "game-character"),
        ({"upstream": {"url": "TODO"}}, "upstream.url"),
        ({"upstream": {"url": "http://insecure.invalid/x.tar.bz2"}}, "upstream.url"),
        ({"type": "matcha", "appSupported": False}, "not supported by the app"),
        ({"preset": {"speakerCount": None}}, "speakerCount"),
    ],
)
def test_community_gate_rejections(override, needle):
    reasons = reg.evaluate_gate(community_entry(**override))
    assert any(needle in r for r in reasons), reasons


def test_community_gate_keeps_component_and_publish_rules():
    entry = community_entry()
    entry["license"]["components"] = [
        {
            "name": "espeak-ng-data",
            "spdx": "GPL-3.0-or-later",
            "url": "TODO",
            "sourceURL": "https://github.com/espeak-ng/espeak-ng",
            "role": "data",
        }
    ]
    assert any("espeak-ng-data" in r and "url" in r for r in reg.evaluate_gate(entry))
    entry = community_entry(minAppVersion="TODO")
    assert reg.evaluate_gate(entry) == []
    assert any("minAppVersion" in r for r in reg.evaluate_gate(entry, for_publish=True))
    assert any("pinned" in r for r in reg.evaluate_gate(community_entry(), require_pinned=True))


def test_game_character_flag_blocks_approved_entries_too():
    reasons = reg.evaluate_gate(make_entry(gameCharacterVoice=True))
    assert any("game-character" in r for r in reasons)


def test_other_statuses_still_blocked():
    for status in ("candidate", "excluded"):
        reasons = reg.evaluate_gate(community_entry(status=status))
        assert any("must be 'approved'" in r for r in reasons)


# ----------------------------------------------------------------------------- selection


def _results(tmp_path, entries):
    return reg.evaluate_all(reg.load_registry(write_registry(tmp_path, entries)))


def test_all_approved_and_all_community_are_disjoint(tmp_path):
    results = _results(
        tmp_path,
        [make_entry(), community_entry(), community_entry(id="zh-comm-bad-v1", gameCharacterVoice=True)],
    )
    approved = [r.entry["id"] for r in reg.select_packs(results, "all-approved")]
    community = [r.entry["id"] for r in reg.select_packs(results, "all-community")]
    assert approved == ["zh-fake-v1"]
    assert community == ["zh-comm-v1"]  # the game-character entry is blocked
    mixed = [r.entry["id"] for r in reg.select_packs(results, "zh-fake-v1,zh-comm-v1")]
    assert mixed == ["zh-fake-v1", "zh-comm-v1"]
    with pytest.raises(VoicePackError, match="blocked by the license gate"):
        reg.select_packs(results, "zh-comm-bad-v1")


def test_cli_select_all_community_matrix(tmp_path, capsys):
    path = write_registry(tmp_path, [make_entry(), community_entry()])
    assert main(["registry-check", "--registry", str(path), "--matrix", "--select", "all-community"]) == 0
    out = capsys.readouterr()
    assert [p["id"] for p in json.loads(out.out)["include"]] == ["zh-comm-v1"]
    assert "community=1" in out.err
    # without --select the matrix stays approved-only
    assert main(["registry-check", "--registry", str(path), "--matrix"]) == 0
    assert [p["id"] for p in json.loads(capsys.readouterr().out)["include"]] == ["zh-fake-v1"]


# ----------------------------------------------------------------------------- build, sidecar, index


@pytest.fixture
def built_community(tmp_path):
    notice = tmp_path / NOTICE_REL
    notice.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / NOTICE_REL, notice)
    archive = write_tar_bz2(tmp_path / "vits-comm.tar.bz2", vits_files(license_file=False))
    entry = community_entry()
    result = build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)
    return entry, result


def test_community_build_uses_notice_and_never_claims_a_licence(built_community, tmp_path):
    entry, result = built_community
    pack = result.pack_dir
    assert (pack / "LICENSE").read_text(encoding="utf-8").startswith(COMMUNITY_NOTICE["en"])
    text = (pack / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert text.startswith(f"{COMMUNITY_NOTICE['en']}\n{COMMUNITY_NOTICE['zh-Hans']}\n")
    assert "Licence: not verified (community tier)" in text
    assert entry["upstream"]["url"] in text
    assert "Model license:" not in text
    assert "UNKNOWN" not in text
    assert "distributed under the terms of that license" not in text


def test_community_build_without_license_text_fails(tmp_path):
    archive = write_tar_bz2(tmp_path / "vits-comm.tar.bz2", vits_files(license_file=False))
    entry = community_entry()
    del entry["license"]["textFile"]
    with pytest.raises(VoicePackError, match="no LICENSE file"):
        build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)


def test_official_attribution_is_unchanged(built_vits):
    _, result = built_vits
    text = (result.pack_dir / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert COMMUNITY_NOTICE["en"] not in text
    assert "Model license: Apache-2.0" in text


def test_community_sidecar_tier_and_labels(built_community, tmp_path):
    entry, built = built_community
    sidecar = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry).sidecar
    assert sidecar["tier"] == "community"
    assert sidecar["recommended"] is False
    assert sidecar["notice"] == COMMUNITY_NOTICE
    assert sidecar["license"]["verified"] is False
    assert "appleAssetPackId" not in sidecar


def test_official_sidecar_tier_and_labels(built_vits, tmp_path):
    entry, built = built_vits
    sidecar = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry).sidecar
    assert sidecar["tier"] == "official"
    assert sidecar["recommended"] is True
    assert "notice" not in sidecar
    assert sidecar["license"]["verified"] is True
    assert sidecar["appleAssetPackId"] == "readori.voice.zh-fake-v1"


def test_notice_texts_are_fixed():
    assert COMMUNITY_NOTICE == {
        "en": "Collected from the community, not recommended by Readori. "
        "Add at your own discretion; the licence is not verified.",
        "zh-Hans": "社区收集，Readori 不推荐。由用户自行添加使用，许可证未经核实。",
        "zh-Hant": "社群收集，Readori 不推薦。由使用者自行加入使用，授權未經核實。",
    }


def test_index_copies_community_fields(built_community, tmp_path):
    entry, built = built_community
    sidecar = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry).sidecar
    item = ix.entry_from_sidecar(sidecar, REPO)
    assert item["tier"] == "community"
    assert item["recommended"] is False
    assert item["notice"] == COMMUNITY_NOTICE
    assert item["license"]["verified"] is False
    assert "appleAssetPackId" not in item
    assert item["url"].startswith("https://github.com/readori/readori-voice-packs/releases/download/")


def test_index_official_and_old_sidecar_defaults(built_vits, tmp_path):
    entry, built = built_vits
    sidecar = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry).sidecar
    item = ix.entry_from_sidecar(sidecar, REPO)
    assert (item["tier"], item["recommended"]) == ("official", True)
    assert "notice" not in item
    old = {k: v for k, v in sidecar.items() if k not in ("tier", "recommended", "notice")}
    item = ix.entry_from_sidecar(old, REPO)
    assert (item["tier"], item["recommended"]) == ("official", True)
    assert "notice" not in item
    assert ix.load_index(tmp_path / "missing.json")["schemaVersion"] == 1  # still v1


# ----------------------------------------------------------------------------- ba-manifest


def test_ba_manifest_refuses_community_by_entry_and_sidecar(built_community):
    entry, built = built_community
    with pytest.raises(VoicePackError, match="community-tier"):
        build_ba_manifest(built.pack_dir, entry=entry)
    with pytest.raises(VoicePackError, match="community-tier"):
        build_ba_manifest(built.pack_dir, sidecar={"tier": "community"})
    # an official sidecar is fine
    assert build_ba_manifest(built.pack_dir, sidecar={"tier": "official"})["assetPackID"]


def test_ba_manifest_cli_refuses_community(built_community, tmp_path, capsys):
    entry, built = built_community
    registry = write_registry(tmp_path, [entry])
    out = tmp_path / "ba"
    code = main(["ba-manifest", str(built.pack_dir), "--registry", str(registry), "--out", str(out)])
    assert code == 1
    assert "community-tier" in capsys.readouterr().err
    assert not out.exists()

    sidecar = tmp_path / "x.zip.json"
    sidecar.write_text(json.dumps({"tier": "community"}), encoding="utf-8")
    missing_registry = tmp_path / "nope.yaml"
    code = main(
        ["ba-manifest", str(built.pack_dir), "--registry", str(missing_registry),
         "--sidecar", str(sidecar), "--out", str(out)]  # fmt: skip
    )
    assert code == 1
    assert not out.exists()
    assert main(["ba-manifest", str(built.pack_dir), "--sidecar", str(tmp_path / "gone.json")]) == 1


# ----------------------------------------------------------------------------- shipped registry


def _shipped():
    registry = reg.load_registry(REPO_ROOT / "registry" / "models.yaml")
    return registry, {m["id"]: m for m in registry.models}


def test_shipped_community_ids_are_community_and_never_approved_or_game():
    _, by_id = _shipped()
    for pack_id in COMMUNITY_IDS:
        entry = by_id[pack_id]
        assert entry["status"] == "community", pack_id
        assert entry["communityNote"].strip()
        assert "excludedReason" not in entry
        assert entry["license"]["textFile"] == NOTICE_REL
        assert entry["minAppVersion"] == "1.1.2"
        assert entry.get("gameCharacterVoice") is not True
        assert entry["license"]["commercialUse"] != False  # noqa: E712 - tri-state, False is meaningful
        assert entry["license"]["spdx"].upper() == "UNKNOWN"


def test_shipped_game_and_non_commercial_are_neither_community_nor_approved():
    _, by_id = _shipped()
    results = {r.entry["id"]: r for r in reg.evaluate_all(_shipped()[0])}
    for pack_id in GAME_CHARACTER_IDS:
        assert by_id[pack_id]["gameCharacterVoice"] is True
        assert by_id[pack_id]["status"] not in ("community", "approved")
        assert not results[pack_id].buildable
    for pack_id in KNOWN_NON_COMMERCIAL_IDS:
        assert by_id[pack_id]["status"] not in ("community", "approved"), pack_id
        assert not results[pack_id].buildable


def test_shipped_game_voices_stay_blocked_even_if_status_is_flipped():
    _, by_id = _shipped()
    for pack_id in GAME_CHARACTER_IDS:
        flipped = {**by_id[pack_id], "status": "community", "communityNote": "x"}
        assert any("game-character" in r for r in reg.evaluate_gate(flipped)), pack_id
    for pack_id in ("zh-piper-xiao-ya-medium-v1", "zh-piper-chaowen-medium-v1"):
        flipped = {**by_id[pack_id], "status": "community", "communityNote": "x"}
        assert reg.evaluate_gate(flipped), pack_id  # known non-commercial stays rejected


def test_shipped_community_notice_text():
    text = (REPO_ROOT / NOTICE_REL).read_text(encoding="utf-8")
    assert text.startswith(f"{COMMUNITY_NOTICE['en']}\n{COMMUNITY_NOTICE['zh-Hans']}\n")
    for needle in ("not verified", "as is", "issue", "未核实", "移除"):
        assert needle in text


def test_shipped_all_approved_excludes_community():
    registry, by_id = _shipped()
    results = reg.evaluate_all(registry)
    approved = {r.entry["id"] for r in reg.select_packs(results, "all-approved")}
    community = {r.entry["id"] for r in reg.select_packs(results, "all-community")}
    assert not approved & COMMUNITY_IDS
    assert community <= COMMUNITY_IDS and community
    assert all(by_id[i]["status"] == "approved" for i in approved)
