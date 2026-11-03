"""GPL data components (espeak-ng-data), evidence links, dataset variants and catalog hints."""
from __future__ import annotations

import json

import pytest
from readori_voicepack import registry as reg
from readori_voicepack.build import ESPEAK_COPYING_NAME, ESPEAK_UPSTREAM_URL, build_pack
from readori_voicepack.cli import main
from readori_voicepack.common import ATTRIBUTION_NAME, CATALOG_NAME, VoicePackError
from readori_voicepack.validate import validate_directory

from .conftest import (
    ESPEAK_COMPONENT,
    GPL_TEXT,
    make_entry,
    vits_files,
    write_registry,
    write_tar_bz2,
)


def _build(tmp_path, entry, files=None, wrapper="vits-fake"):
    archive = write_tar_bz2(tmp_path / "up.tar.bz2", files or vits_files(), wrapper=wrapper)
    return build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)


# ----------------------------------------------------------------------------- gate


def test_gpl_data_component_passes_gate():
    assert reg.evaluate_gate(make_entry()) == []


@pytest.mark.parametrize("spdx", ["GPL-3.0-or-later", "GPL-3.0-only"])
def test_gpl_data_component_both_variants_allowed(spdx):
    comp = dict(ESPEAK_COMPONENT, spdx=spdx)
    entry = make_entry()
    entry["license"]["components"] = [comp]
    assert reg.evaluate_gate(entry) == []


def test_gpl_as_main_license_rejected():
    for spdx in ("GPL-3.0-or-later", "GPL-3.0-only", "GPL-2.0-only", "AGPL-3.0-only", "LGPL-3.0-only"):
        reasons = reg.evaluate_gate(make_entry(license={"spdx": spdx}))
        assert any("allow list" in r for r in reasons), spdx


def test_gpl_as_code_component_rejected():
    entry = make_entry()
    entry["license"]["components"] = [dict(ESPEAK_COMPONENT, role="code")]
    reasons = reg.evaluate_gate(entry)
    assert any("only accepted for role=data" in r for r in reasons)


def test_other_copyleft_or_nc_component_rejected():
    for spdx in ("GPL-2.0-only", "AGPL-3.0-only", "CC-BY-NC-4.0", "TODO", "unknown"):
        entry = make_entry()
        entry["license"]["components"] = [dict(ESPEAK_COMPONENT, spdx=spdx)]
        assert reg.evaluate_gate(entry), spdx


def test_component_schema_requires_fields():
    entry = make_entry()
    del entry["license"]["components"][0]["sourceURL"]
    entry["license"]["components"][0]["role"] = "plugin"
    errors = reg.validate_entry_schema(entry, 0)
    assert any("sourceURL" in e for e in errors)
    assert any("role" in e for e in errors)


def test_component_urls_must_be_https_for_gate():
    entry = make_entry()
    entry["license"]["components"][0]["sourceURL"] = "TODO"
    assert any("sourceURL" in r for r in reg.evaluate_gate(entry))


# ----------------------------------------------------------------------------- evidence


def test_evidence_requires_a_link_for_approved():
    reasons = reg.evaluate_gate(make_entry(license={"evidence": "the README says Apache-2.0"}))
    assert any("https link" in r for r in reasons)
    assert reg.evaluate_gate(make_entry(license={"evidence": "see https://example.invalid/a"})) == []
    assert reg.evaluate_gate(make_entry(license={"evidence": ["https://example.invalid/a", "note"]})) == []
    assert any(
        "evidence" in r for r in reg.evaluate_gate(make_entry(license={"evidence": [{"note": "x", "url": "TODO"}]}))
    )


def test_evidence_list_schema():
    errors = reg.validate_entry_schema(make_entry(license={"evidence": []}), 0)
    assert any("evidence" in e for e in errors)
    errors = reg.validate_entry_schema(make_entry(license={"evidence": [{"note": "no url"}]}), 0)
    assert any("evidence" in e for e in errors)


# ----------------------------------------------------------------------------- dataset


def test_dataset_cc_by_3_and_unlicense_allowed():
    for spdx in ("CC-BY-3.0", "Unlicense"):
        entry = make_entry(license={"dataset": {"spdx": spdx}})
        assert reg.evaluate_gate(entry) == [], spdx


def test_dataset_undisclosed_needs_note_and_allows_unknown_commercial():
    ok = make_entry(license={"dataset": {"spdx": "undisclosed", "commercialUse": "unknown", "note": "n"}})
    assert reg.evaluate_gate(ok) == []
    no_note = make_entry(license={"dataset": {"spdx": "undisclosed", "commercialUse": "unknown"}})
    assert any("note" in r for r in reg.evaluate_gate(no_note))
    # unknown commercial use is NOT acceptable for a disclosed dataset license
    disclosed = make_entry(license={"dataset": {"spdx": "CC-BY-4.0", "commercialUse": "unknown"}})
    assert any("commercialUse" in r for r in reg.evaluate_gate(disclosed))


def test_dataset_mixed_parts_are_checked():
    parts = [
        {"name": "Koniwa tnc", "spdx": "CC-BY-3.0", "url": "https://github.com/koniwa/koniwa"},
        {"name": "SIWIS", "spdx": "CC-BY-4.0"},
    ]
    entry = make_entry(license={"dataset": {"spdx": "mixed", "parts": parts, "note": "n"}})
    assert reg.evaluate_gate(entry) == []
    bad = make_entry(
        license={"dataset": {"spdx": "mixed", "parts": [{"name": "x", "spdx": "CC-BY-NC-4.0"}], "note": "n"}}
    )
    assert any("dataset part" in r for r in reg.evaluate_gate(bad))
    no_parts = make_entry(license={"dataset": {"spdx": "mixed", "note": "n"}})
    assert any("parts" in r for r in reg.evaluate_gate(no_parts))


def test_attribution_lists_dataset_parts_and_components(tmp_path):
    parts = [
        {
            "name": "Koniwa tnc",
            "spdx": "CC-BY-3.0",
            "url": "https://github.com/koniwa/koniwa",
            "attribution": "Koniwa tnc, CC BY 3.0",
        },
        {"name": "SIWIS", "spdx": "CC-BY-4.0", "attribution": "SIWIS database, CC BY 4.0"},
    ]
    entry = make_entry(license={"dataset": {"spdx": "mixed", "parts": parts, "note": "n"}})
    result = _build(tmp_path, entry)
    text = (result.pack_dir / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert "Koniwa tnc, CC BY 3.0" in text and "SIWIS database, CC BY 4.0" in text
    assert "Component: espeak-ng-data" in text


# ----------------------------------------------------------------------------- minAppVersion


def test_min_app_version_todo_blocks_only_publishing():
    entry = make_entry(minAppVersion="TODO")
    assert reg.evaluate_gate(entry) == []
    assert any("minAppVersion" in r for r in reg.evaluate_gate(entry, for_publish=True))
    assert reg.evaluate_gate(make_entry(), for_publish=True) == []


def test_cli_for_publish_flag(tmp_path, capsys):
    path = write_registry(tmp_path, [make_entry(minAppVersion="TODO")])
    assert main(["registry-check", "--registry", str(path), "--select", "all-approved"]) == 0
    capsys.readouterr()
    code = main(["registry-check", "--registry", str(path), "--select", "zh-fake-v1", "--for-publish"])
    assert code == 1
    assert "minAppVersion" in capsys.readouterr().err


# ----------------------------------------------------------------------------- build / GPL text


def test_build_writes_copying_and_gpl_attribution(tmp_path):
    result = _build(tmp_path, make_entry())
    copying = result.pack_dir / ESPEAK_COPYING_NAME
    assert copying.read_text(encoding="utf-8") == GPL_TEXT
    text = (result.pack_dir / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert ESPEAK_UPSTREAM_URL in text and "GPL-3.0-or-later" in text
    assert validate_directory(result.pack_dir).ok


def test_build_prefers_copying_from_upstream_espeak_data(tmp_path):
    upstream_gpl = GPL_TEXT + "(from upstream tarball)\n"
    files = vits_files()
    files["espeak-ng-data/COPYING"] = upstream_gpl.encode()
    result = _build(tmp_path, make_entry(), files)
    assert (result.pack_dir / ESPEAK_COPYING_NAME).read_text(encoding="utf-8") == upstream_gpl
    assert any("upstream" in n for n in result.notes)


def test_build_fails_without_any_gpl_text(tmp_path):
    (tmp_path / "registry" / "license-texts" / "GPL-3.0.txt").unlink()
    with pytest.raises(VoicePackError, match="no GPL-3.0 text"):
        _build(tmp_path, make_entry())


def test_build_fails_when_repo_gpl_text_is_placeholder(tmp_path):
    path = tmp_path / "registry" / "license-texts" / "GPL-3.0.txt"
    path.write_text("READORI-PLACEHOLDER: replace with GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007", "utf-8")
    with pytest.raises(VoicePackError, match="no GPL-3.0 text"):
        _build(tmp_path, make_entry())


def test_build_fails_when_espeak_component_not_declared(tmp_path):
    entry = make_entry()
    entry["license"]["components"] = []
    with pytest.raises(VoicePackError, match="declares no license.components"):
        _build(tmp_path, entry)


def test_pack_without_espeak_data_needs_no_gpl_text(tmp_path):
    files = {k: v for k, v in vits_files().items() if not k.startswith("espeak-ng-data")}
    entry = make_entry()
    entry["license"]["components"] = []
    entry["preset"]["dataDir"] = None
    (tmp_path / "registry" / "license-texts" / "GPL-3.0.txt").unlink()
    result = _build(tmp_path, entry, files)
    assert not (result.pack_dir / ESPEAK_COPYING_NAME).exists()
    assert validate_directory(result.pack_dir).ok


def test_validator_flags_missing_espeak_notice(tmp_path):
    result = _build(tmp_path, make_entry())
    (result.pack_dir / ESPEAK_COPYING_NAME).unlink()
    assert "espeak_notice_missing" in validate_directory(result.pack_dir).codes()
    result = _build(tmp_path, make_entry())
    attribution = result.pack_dir / ATTRIBUTION_NAME
    attribution.write_text("no notice", encoding="utf-8")
    assert "espeak_notice_missing" in validate_directory(result.pack_dir).codes()


# ----------------------------------------------------------------------------- preset TODO


def test_todo_preset_values_are_auto_detected(tmp_path):
    entry = make_entry()
    entry["preset"].update(
        {"model": "TODO", "tokens": "TODO verify", "lexicon": "TODO", "dataDir": "TODO", "ruleFsts": ["TODO"]}
    )
    assert reg.validate_entry_schema(entry, 0) == []
    result = _build(tmp_path, entry)
    manifest = result.manifest
    assert manifest["model"] == "model.onnx" and manifest["tokens"] == "tokens.txt"
    assert manifest["dataDir"] == "espeak-ng-data"
    assert manifest["lexicon"] == "lexicon.txt"
    assert "ruleFsts" not in manifest


def test_non_todo_garbage_preset_still_rejected():
    entry = make_entry()
    entry["preset"]["model"] = "../model.onnx"
    assert reg.validate_entry_schema(entry, 0)


# ----------------------------------------------------------------------------- catalog hints


def test_hidden_sids_are_left_out_of_generated_catalog(tmp_path):
    files = vits_files(speakers=5)
    entry = make_entry(preset={"speakerCount": 5}, catalogHints={"hiddenSids": [3, 4]})
    result = _build(tmp_path, entry, files)
    catalog = json.loads((result.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    assert [s["sid"] for s in catalog["speakers"]] == [0, 1, 2]
    assert catalog["speakerCount"] == 5 and result.manifest["speakerCount"] == 5
    assert validate_directory(result.pack_dir).ok


def test_hidden_default_speaker_rejected(tmp_path):
    entry = make_entry(preset={"speakerCount": 5, "defaultSpeaker": 3}, catalogHints={"hiddenSids": [3]})
    with pytest.raises(VoicePackError, match="hidden"):
        _build(tmp_path, entry, vits_files(speakers=5))


def test_speaker_names_hint_fills_source_ids(tmp_path):
    entry = make_entry(preset={"speakerCount": 2}, catalogHints={"speakerNames": ["af", "am"]})
    result = _build(tmp_path, entry)
    catalog = json.loads((result.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    assert [s["sourceSpeakerId"] for s in catalog["speakers"]] == ["af", "am"]
    bad = make_entry(preset={"speakerCount": 3}, catalogHints={"speakerNames": ["af", "am"]})
    with pytest.raises(VoicePackError, match="speakerNames"):
        _build(tmp_path, bad)


def test_catalog_hints_schema():
    assert reg.validate_entry_schema(make_entry(catalogHints={"hiddenSids": [-1]}), 0)
    assert reg.validate_entry_schema(make_entry(catalogHints={"other": 1}), 0)
    assert reg.validate_entry_schema(make_entry(catalogHints={"speakerNames": [""]}), 0)


def test_priority_and_new_types_schema():
    assert reg.validate_entry_schema(make_entry(priority=1), 0) == []
    assert reg.validate_entry_schema(make_entry(priority=0), 0)
    st = make_entry(type="supertonic", appSupported=False, status="excluded", excludedReason="x")
    assert reg.validate_entry_schema(st, 0) == []
    assert any("supertonic" in r for r in reg.evaluate_gate(st)) or reg.evaluate_gate(st)
