from __future__ import annotations

import json
from pathlib import Path

import pytest
from readori_voicepack import registry as reg
from readori_voicepack.cli import main
from readori_voicepack.common import VoicePackError

from .conftest import make_entry, write_registry

REPO_ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------------- real registry


PRIORITY_1 = {
    "zh-en-melo-v1",
    "zh-aishell3-v1",
    "en-melo-v1",
    "en-kokoro-v1-0-int8-v1",
    "zh-en-kokoro-int8-v1-1",
    "en-piper-en-us-libritts-high-v1",
    "en-coqui-vctk-vits-v1",
}


def _shipped():
    registry = reg.load_registry(REPO_ROOT / "registry" / "models.yaml")
    return registry, {m["id"]: m for m in registry.models}


def test_shipped_registry_is_valid_and_catalogs_consistent():
    registry, by_id = _shipped()
    assert len(registry.models) >= 92
    for old in ("zh-aishell3-v1", "zh-en-melo-v1", "yue-cantonese-v1", "zh-en-kokoro-int8-v1-1"):
        assert old in by_id
    results = reg.evaluate_all(registry)
    assert all(r.catalog_problems == [] for r in results), "shipped catalogs must be consistent"


def test_shipped_priority_one_packs_are_buildable():
    registry, by_id = _shipped()
    results = {r.entry["id"]: r for r in reg.evaluate_all(registry)}
    assert {i for i, m in by_id.items() if m.get("priority") == 1} == PRIORITY_1
    for pack_id in PRIORITY_1:
        assert results[pack_id].buildable, (pack_id, results[pack_id].reasons)
        assert by_id[pack_id]["status"] == "approved"


def test_shipped_decisions_cantonese_and_japanese_korean_excluded():
    registry, by_id = _shipped()
    assert by_id["yue-cantonese-v1"]["status"] == "excluded"
    for model in registry.models:
        if model["status"] == "approved":
            assert model.get("voiceCatalog") != by_id["yue-cantonese-v1"]["voiceCatalog"]
            assert "yue" not in model["languages"]
    for pack_id in ("ja-none-in-tts-models", "ko-none-compliant-v1", "multi-supertonic-3-int8-v1"):
        assert by_id[pack_id]["status"] == "excluded"
        assert "OpenRAIL-M" in by_id[pack_id]["excludedReason"]


def test_shipped_approved_entries_meet_license_policy():
    registry, _ = _shipped()
    for model in registry.models:
        if model["status"] != "approved":
            continue
        lic = model["license"]
        assert lic["spdx"] in reg.ALLOWED_SPDX, model["id"]
        assert reg.evidence_urls(lic), model["id"]
        for comp in lic.get("components") or []:
            if comp["spdx"] in reg.COPYLEFT_DATA_SPDX:
                assert comp["role"] == "data", model["id"]
        has_espeak_dir = model["preset"].get("dataDir") == "espeak-ng-data"
        if has_espeak_dir:
            assert any("espeak" in c["name"] for c in lic.get("components") or []), model["id"]
        up = model["upstream"]
        if up["sha256"] != "TODO":
            assert up.get("pinnedFrom") == "github-digest", model["id"]


def test_shipped_kokoro_attribution_and_caps():
    _, by_id = _shipped()
    for pack_id in ("en-kokoro-v1-0-int8-v1", "zh-en-kokoro-int8-v1-1", "en-kokoro-v0-19-int8-v1"):
        text = by_id[pack_id]["license"]["attribution"]
        assert "Koniwa tnc" in text and "SIWIS" in text and "CC BY 3.0" in text and "CC BY 4.0" in text
    assert by_id["en-kokoro-v1-0-int8-v1"]["catalogHints"]["hiddenSids"] == list(range(28, 45))
    libritts = by_id["en-piper-en-us-libritts-high-v1"]
    assert libritts["preset"]["speakerCount"] == 512 and libritts["upstreamSpeakerCount"] == 904


def test_shipped_license_evidence_doc_and_gpl_text_exist():
    assert (REPO_ROOT / "docs" / "LICENSE_EVIDENCE.md").is_file()
    text = (REPO_ROOT / "registry" / "license-texts" / "GPL-3.0.txt").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in text and "Version 3, 29 June 2007" in text
    assert chr(13) not in text


def test_cli_registry_check_exit_code_zero_and_report(capsys):
    code = main(["registry-check", "--registry", str(REPO_ROOT / "registry" / "models.yaml")])
    out = capsys.readouterr().out
    assert code == 0
    assert "buildable" in out and "BLOCKED" in out


# ----------------------------------------------------------------------------- schema


def test_schema_accepts_fixture_entry():
    assert reg.validate_registry_doc({"schemaVersion": 1, "models": [make_entry()]}) == []


@pytest.mark.parametrize(
    "override, needle",
    [
        ({"id": "Bad_ID"}, "id must match"),
        ({"languages": []}, "languages"),
        ({"languages": ["not a tag!"]}, "invalid language tag"),
        ({"type": "matcha"}, "appSupported must be false"),
        ({"type": "weird"}, "type must be one of"),
        ({"status": "maybe"}, "status must be one of"),
        ({"status": "excluded"}, "excludedReason"),
        ({"packVersion": 0}, "packVersion"),
        ({"minAppVersion": "latest"}, "minAppVersion"),
        ({"upstream": {"url": "http://insecure/x.tar.bz2"}}, "upstream.url"),
        ({"upstream": {"sha256": "ABC"}}, "upstream.sha256"),
        ({"license": {"commercialUse": "yes"}}, "commercialUse"),
        ({"preset": {"bogus": 1}}, "unknown preset keys"),
        ({"preset": {"model": "../escape.onnx"}}, "preset.model"),
        ({"preset": {"speakerCount": 600}}, "speakerCount"),
        ({"preset": {"speakerCount": 2, "defaultSpeaker": 2}}, "defaultSpeaker"),
        ({"voiceCatalog": "/abs/path.json"}, "voiceCatalog"),
    ],
)
def test_schema_rejects(override, needle):
    errors = reg.validate_registry_doc({"schemaVersion": 1, "models": [make_entry(**override)]})
    assert any(needle in e for e in errors), errors


def test_schema_requires_all_three_display_names():
    entry = make_entry()
    del entry["displayName"]["zh-Hant"]
    errors = reg.validate_registry_doc({"schemaVersion": 1, "models": [entry]})
    assert any("displayName.zh-Hant" in e for e in errors)


def test_schema_rejects_duplicate_ids_and_bad_top_level():
    doc = {"schemaVersion": 1, "models": [make_entry(), make_entry()]}
    assert any("duplicate id" in e for e in reg.validate_registry_doc(doc))
    assert reg.validate_registry_doc({"schemaVersion": 2, "models": [make_entry()]})
    assert reg.validate_registry_doc({"schemaVersion": 1, "models": []})
    assert reg.validate_registry_doc([])


def test_load_registry_reports_schema_errors(tmp_path):
    path = write_registry(tmp_path, [make_entry(id="BAD")])
    with pytest.raises(VoicePackError, match="schema errors"):
        reg.load_registry(path)


# ----------------------------------------------------------------------------- license gate


@pytest.mark.parametrize(
    "spdx",
    ["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"],
)
def test_gate_passes_allowed_licenses(spdx):
    entry = make_entry(license={"spdx": spdx, "attribution": "Credit: Fixture Author"})
    assert reg.evaluate_gate(entry) == []


@pytest.mark.parametrize(
    "spdx, needle",
    [
        ("TODO", "unknown"),
        ("unknown", "unknown"),
        ("", "unknown"),
        ("CC-BY-NC-4.0", "non-commercial"),
        ("CC-BY-NC-SA-4.0", "non-commercial"),
        ("LicenseRef-research-only", "non-commercial"),
        ("GPL-3.0-only", "allow list"),
        ("Proprietary", "allow list"),
    ],
)
def test_gate_rejects_bad_licenses(spdx, needle):
    reasons = reg.evaluate_gate(make_entry(license={"spdx": spdx}))
    assert any(needle in r for r in reasons), reasons


@pytest.mark.parametrize("field", ["commercialUse", "redistribution"])
@pytest.mark.parametrize("value", ["unknown", False])
def test_gate_requires_explicit_true(field, value):
    reasons = reg.evaluate_gate(make_entry(license={field: value}))
    assert any(field in r for r in reasons)


def test_gate_rejects_unapproved_status_and_unsupported_type():
    assert reg.evaluate_gate(make_entry(status="candidate"))
    assert reg.evaluate_gate(make_entry(status="excluded", excludedReason="NC"))
    reasons = reg.evaluate_gate(make_entry(type="matcha", appSupported=False))
    assert any("not supported by the app" in r for r in reasons)


def test_gate_cc_by_requires_attribution():
    reasons = reg.evaluate_gate(make_entry(license={"spdx": "CC-BY-4.0"}))
    assert any("attribution" in r for r in reasons)


def test_gate_requires_dataset_license_and_evidence():
    entry = make_entry()
    del entry["license"]["dataset"]
    assert any("dataset" in r for r in reg.evaluate_gate(entry))
    assert any("dataset" in r for r in reg.evaluate_gate(make_entry(license={"dataset": {"spdx": "CC-BY-NC-4.0"}})))
    assert any("evidence" in r for r in reg.evaluate_gate(make_entry(license={"evidence": "TODO"})))
    assert any("license.url" in r for r in reg.evaluate_gate(make_entry(license={"url": "TODO"})))


def test_gate_todo_placeholders_block():
    assert reg.evaluate_gate(make_entry(upstream={"url": "TODO"}))
    assert reg.evaluate_gate(make_entry(license={"evidence": "TODO"}))
    # minAppVersion TODO only blocks publishing, see test_gpl_components.py


def test_gate_pinning_is_optional_unless_required():
    entry = make_entry()
    assert reg.evaluate_gate(entry) == []
    assert any("pinned" in r for r in reg.evaluate_gate(entry, require_pinned=True))
    pinned = make_entry(upstream={"sha256": "a" * 64, "bytes": 123})
    assert reg.evaluate_gate(pinned, require_pinned=True) == []


# ----------------------------------------------------------------------------- selection


def _results(tmp_path, entries):
    registry = reg.load_registry(write_registry(tmp_path, entries))
    return reg.evaluate_all(registry)


def test_select_all_approved_and_matrix(tmp_path):
    results = _results(tmp_path, [make_entry(), make_entry(id="zh-other-v1", status="candidate")])
    selected = reg.select_packs(results, "all-approved")
    assert [r.entry["id"] for r in selected] == ["zh-fake-v1"]
    assert reg.matrix_for(selected) == {
        "include": [{"id": "zh-fake-v1", "packVersion": 1, "type": "vits"}]
    }


def test_select_explicit_ids_and_failures(tmp_path):
    results = _results(tmp_path, [make_entry(), make_entry(id="zh-other-v1", status="candidate")])
    assert [r.entry["id"] for r in reg.select_packs(results, "zh-fake-v1")] == ["zh-fake-v1"]
    with pytest.raises(VoicePackError, match="blocked by the license gate"):
        reg.select_packs(results, "zh-fake-v1,zh-other-v1")
    with pytest.raises(VoicePackError, match="unknown pack id"):
        reg.select_packs(results, "nope")
    with pytest.raises(VoicePackError, match="invalid pack id"):
        reg.select_packs(results, "zh-fake-v1;rm -rf /")
    with pytest.raises(VoicePackError, match="empty"):
        reg.select_packs(results, " , ")


def test_cli_matrix_output_is_pure_json(tmp_path, capsys):
    path = write_registry(tmp_path, [make_entry(), make_entry(id="zh-other-v1", status="candidate")])
    code = main(["registry-check", "--registry", str(path), "--matrix", "--select", "all-approved"])
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["include"][0]["id"] == "zh-fake-v1"
    assert "BLOCKED" in captured.err


def test_cli_select_blocked_pack_fails(tmp_path, capsys):
    path = write_registry(tmp_path, [make_entry(status="candidate")])
    code = main(["registry-check", "--registry", str(path), "--select", "zh-fake-v1"])
    assert code == 1
    assert "blocked by the license gate" in capsys.readouterr().err


def test_require_buildable_blocks_candidate(tmp_path):
    registry = reg.load_registry(write_registry(tmp_path, [make_entry(status="candidate")]))
    with pytest.raises(VoicePackError, match="blocked by the license gate"):
        reg.require_buildable(registry, "zh-fake-v1")
