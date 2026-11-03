"""``build-local``: self-built packs (tier local), isolated from official publishing."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from readori_voicepack import fetch as fetch_mod
from readori_voicepack import index as ix
from readori_voicepack import local as local_mod
from readori_voicepack.bamanifest import build_ba_manifest
from readori_voicepack.build import build_pack
from readori_voicepack.cli import main
from readori_voicepack.common import (
    ATTRIBUTION_NAME,
    LOCAL_ATTRIBUTION_ZH,
    MANIFEST_NAME,
    TIER_LOCAL,
    VoicePackError,
    sha256_file,
)
from readori_voicepack.pack import LocalMeta, pack_directory
from readori_voicepack.validate import validate_target

from .conftest import (
    kokoro_files,
    make_entry,
    merge,
    vits_files,
    write_registry,
    write_tar_bz2,
    write_zip,
)

REGISTRY_URL = "https://example.invalid/tts-models/vits-fake.tar.bz2"
NEUTRAL_URL = "https://example.invalid/models/vits-neutral-zh.tar.bz2"
ACCEPT = "--accept-upstream-license"


@pytest.fixture
def local_args(tmp_path: Path):
    """Common CLI arguments: output dir, no real registry, no smoke (sherpa is optional)."""
    out = tmp_path / "local-out"
    return ["--out", str(out), "--registry", str(tmp_path / "none.yaml"), "--skip-smoke"], out


def _sidecar(out: Path, pack_id: str) -> dict:
    return json.loads((out / f"{pack_id}-v1.zip.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- accept flag


def test_refuses_without_accept_flag(vits_archive, local_args, capsys):
    args, out = local_args
    assert main(["build-local", str(vits_archive), *args]) == 1
    err = capsys.readouterr().err
    assert "--accept-upstream-license" in err
    assert "does not review or distribute" in err
    assert not out.exists()


def test_refusal_happens_before_any_download(monkeypatch, local_args, capsys):
    def boom(*_a, **_k):
        raise AssertionError("must not download")

    monkeypatch.setattr(fetch_mod, "download", boom)
    args, _ = local_args
    assert main(["build-local", NEUTRAL_URL, *args]) == 1
    assert "--accept-upstream-license" in capsys.readouterr().err


# ----------------------------------------------------------------------------- local archives


def test_builds_vits_from_local_archive(vits_archive, local_args, capsys):
    args, out = local_args
    assert main(["build-local", str(vits_archive), ACCEPT, *args, "--language", "zh-CN"]) == 0
    text = capsys.readouterr().out
    assert "tier local" in text and "skipped (--skip-smoke)" in text

    pack_id = "local-vits-fake"
    zip_path = out / f"{pack_id}-v1.zip"
    assert validate_target(zip_path, policy=True).ok
    assert validate_target(out / pack_id, policy=True).ok

    manifest = json.loads((out / pack_id / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["type"] == "vits"
    assert manifest["packId"] == pack_id
    assert manifest["language"] == "zh-CN"
    assert manifest["licenseFile"] == "LICENSE"
    assert manifest["sourceURL"] == "vits-fake.tar.bz2"  # file name only, no local path

    sidecar = _sidecar(out, pack_id)
    assert sidecar["tier"] == TIER_LOCAL
    assert sidecar["recommended"] is False
    assert sidecar["license"] == {"verified": False, "selfBuilt": True}
    assert "appleAssetPackId" not in sidecar
    assert sidecar["languages"] == ["zh-CN"]
    assert sidecar["sha256"] == sha256_file(zip_path)

    # LICENSE is the upstream text as-is; GPL text for espeak-ng-data comes from the repo copy.
    assert (out / pack_id / "LICENSE").read_bytes().startswith(b"Apache License")
    assert (out / pack_id / "COPYING.espeak-ng").is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert {"LICENSE", ATTRIBUTION_NAME, MANIFEST_NAME, "model.onnx"} <= names
    assert not any(n.endswith((".py", ".wav")) for n in names)


def test_attribution_text_and_first_lines(vits_archive, local_args):
    args, out = local_args
    assert main(["build-local", str(vits_archive), ACCEPT, *args]) == 0
    lines = (out / "local-vits-fake" / ATTRIBUTION_NAME).read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "Self-built by the user from vits-fake.tar.bz2. Readori did not review, build or "
        "distribute this pack; the user is responsible for complying with the upstream licence."
    )
    assert lines[1] == "用户自行构建，Readori 未审核、未构建、未分发；上游许可证由用户自行遵守。"
    assert lines[1] == LOCAL_ATTRIBUTION_ZH
    assert lines[3] == "Upstream licence file in this pack: LICENSE"


def test_espeak_pack_carries_gpl_text_and_statement(vits_archive, local_args):
    args, out = local_args
    assert main(["build-local", str(vits_archive), ACCEPT, *args]) == 0
    pack = out / "local-vits-fake"
    assert "GNU GENERAL PUBLIC LICENSE" in (pack / "COPYING.espeak-ng").read_text(encoding="utf-8")
    text = (pack / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert "https://github.com/espeak-ng/espeak-ng" in text and "GPL" in text


def test_builds_kokoro_from_zip_and_autodetects_type(tmp_path, local_args, capsys):
    archive = write_zip(tmp_path / "kokoro-fake.zip", {f"kokoro-fake/{k}": v for k, v in kokoro_files().items()})
    args, out = local_args
    assert main(
        ["build-local", str(archive), ACCEPT, *args, "--speaker-count", "3", "--default-speaker", "1",
         "--name", "my-kokoro", "--display-name", "My Kokoro"]
    ) == 0
    manifest = json.loads((out / "my-kokoro" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["type"] == "kokoro"
    assert manifest["speakerCount"] == 3 and manifest["defaultSpeaker"] == 1
    assert manifest["displayName"] == "My Kokoro"
    assert manifest["voices"] == "voices.bin"
    sidecar = _sidecar(out, "my-kokoro")
    assert sidecar["tier"] == "local" and sidecar["type"] == "kokoro"
    assert sidecar["displayName"] == {"en": "My Kokoro"}
    assert validate_target(out / "my-kokoro-v1.zip", policy=True).ok


def test_archive_without_license_uses_attribution_as_license_file(tmp_path, local_args):
    files = vits_files(license_file=False)
    archive = write_tar_bz2(tmp_path / "vits-nolic.tar.bz2", files, wrapper="vits-nolic")
    args, out = local_args
    assert main(["build-local", str(archive), ACCEPT, *args]) == 0
    manifest = json.loads((out / "local-vits-nolic" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["licenseFile"] == ATTRIBUTION_NAME
    text = (out / "local-vits-nolic" / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert "contains no LICENSE or COPYING file" in text


def test_copying_file_is_kept_and_named(tmp_path, local_args):
    files = vits_files(license_file=False)
    files["COPYING"] = b"upstream copying text"
    archive = write_tar_bz2(tmp_path / "vits-copying.tar.bz2", files, wrapper="vits-copying")
    args, out = local_args
    assert main(["build-local", str(archive), ACCEPT, *args]) == 0
    pack = out / "local-vits-copying"
    assert (pack / "COPYING").read_bytes() == b"upstream copying text"
    lines = (pack / ATTRIBUTION_NAME).read_text(encoding="utf-8").splitlines()
    assert lines[3] == "Upstream licence file in this pack: COPYING"


def test_build_is_deterministic(vits_archive, tmp_path):
    shas = []
    for name in ("a", "b"):
        out = tmp_path / name
        code = main(["build-local", str(vits_archive), ACCEPT, "--out", str(out), "--skip-smoke",
                     "--registry", str(tmp_path / "none.yaml")])
        assert code == 0
        shas.append(_sidecar(out, "local-vits-fake")["sha256"])
    assert shas[0] == shas[1]


def test_bad_options_fail_cleanly(vits_archive, local_args, capsys):
    args, _ = local_args
    assert main(["build-local", str(vits_archive), ACCEPT, *args, "--name", "Bad Name"]) == 1
    assert "invalid pack id" in capsys.readouterr().err
    assert main(["build-local", str(vits_archive), ACCEPT, *args, "--language", "not a tag"]) == 1
    assert main(["build-local", str(vits_archive.parent / "missing.tar.bz2"), ACCEPT, *args]) == 1
    assert "not found" in capsys.readouterr().err
    assert main(["build-local", str(vits_archive), ACCEPT, *args, "--sha256", "xyz"]) == 1


# ----------------------------------------------------------------------------- sha256


def test_sha256_is_verified_and_printed(vits_archive, local_args, capsys):
    args, out = local_args
    good = sha256_file(vits_archive)
    assert main(["build-local", str(vits_archive), ACCEPT, *args, "--sha256", good.upper()]) == 0
    assert f"sha256: {good}" in capsys.readouterr().out

    bad = "0" * 64
    assert main(["build-local", str(vits_archive), ACCEPT, *args, "--sha256", bad, "--name", "other"]) == 1
    assert "sha256 mismatch" in capsys.readouterr().err
    assert not (out / "other").exists()


# ----------------------------------------------------------------------------- URL source


def _fake_download(archive: Path, calls: list):
    def download(url, destination, **kwargs):
        calls.append((url, destination.name, kwargs))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read_bytes())
        return sha256_file(archive), archive.stat().st_size

    return download


def test_url_source_downloads_via_fetch_helper(tmp_path, monkeypatch, local_args, capsys):
    archive = write_tar_bz2(tmp_path / "src.tar.bz2", vits_files(), wrapper="vits-neutral-zh")
    calls: list = []
    monkeypatch.setattr(fetch_mod, "download", _fake_download(archive, calls))
    args, out = local_args
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert main(["build-local", NEUTRAL_URL, ACCEPT, *args, "--sha256", expected]) == 0
    assert calls[0][0] == NEUTRAL_URL and calls[0][1] == "vits-neutral-zh.tar.bz2"
    assert calls[0][2]["max_bytes"] == fetch_mod.DEFAULT_MAX_DOWNLOAD_BYTES
    text = capsys.readouterr().out
    assert f"sha256: {expected}" in text
    # language guessed from the "zh" token in the file name
    manifest = json.loads((out / "local-vits-neutral-zh" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["language"] == "zh-CN"
    assert manifest["sourceURL"] == NEUTRAL_URL
    first = (out / "local-vits-neutral-zh" / ATTRIBUTION_NAME).read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith(f"Self-built by the user from {NEUTRAL_URL}. Readori did not review")


def test_url_source_sha_mismatch_fails(tmp_path, monkeypatch, local_args, capsys):
    archive = write_tar_bz2(tmp_path / "src.tar.bz2", vits_files(), wrapper="vits-neutral-zh")
    monkeypatch.setattr(fetch_mod, "download", _fake_download(archive, []))
    args, out = local_args
    assert main(["build-local", NEUTRAL_URL, ACCEPT, *args, "--sha256", "f" * 64]) == 1
    assert "sha256 mismatch" in capsys.readouterr().err
    assert not (out / "local-vits-neutral-zh").exists()


def test_plain_http_url_is_refused_without_network(local_args, capsys):
    args, _ = local_args
    assert main(["build-local", "http://example.invalid/vits-x.tar.bz2", ACCEPT, *args]) == 1
    assert "refusing to download" in capsys.readouterr().err


# ----------------------------------------------------------------------------- registry info


def _registry(tmp_path: Path, **override) -> Path:
    return write_registry(tmp_path, [make_entry(**override)])


def test_registry_match_prints_info_and_does_not_block(vits_archive, tmp_path, capsys):
    registry = _registry(
        tmp_path,
        status="excluded",
        excludedReason="SECRET-REASON-DETAIL",
        license={"spdx": "CC-BY-NC-4.0", "commercialUse": False, "redistribution": False},
    )
    out = tmp_path / "out"
    code = main(["build-local", str(vits_archive), ACCEPT, "--out", str(out), "--skip-smoke",
                 "--registry", str(registry)])
    assert code == 0
    text = capsys.readouterr()
    assert "registry: excluded, licence CC-BY-NC-4.0 (non-commercial)" in text.out
    assert "SECRET-REASON-DETAIL" not in text.out + text.err
    assert (out / "local-vits-fake-v1.zip").is_file()


def test_registry_info_variants(tmp_path):
    registry = _registry(tmp_path)  # approved, Apache-2.0, upstream url .../vits-fake.tar.bz2
    assert local_mod.registry_info(REGISTRY_URL, registry) == "registry: approved, licence Apache-2.0"
    assert local_mod.registry_info("C:/somewhere/vits-fake.tar.bz2", registry) == (
        "registry: approved, licence Apache-2.0"
    )
    assert local_mod.registry_info(NEUTRAL_URL, registry) is None
    assert local_mod.registry_info(NEUTRAL_URL, tmp_path / "missing.yaml") is None
    community = write_registry(
        tmp_path / "c",
        [make_entry(status="community", communityNote="x",
                    license=merge({}, {"spdx": "UNKNOWN", "url": "TODO", "evidence": "TODO",
                                       "commercialUse": "unknown", "redistribution": "unknown",
                                       "textFile": "registry/license-texts/COMMUNITY-NOTICE.txt",
                                       "dataset": {"name": "undisclosed", "spdx": "undisclosed",
                                                   "commercialUse": "unknown"}}))],
    )
    assert local_mod.registry_info(REGISTRY_URL, community) == "registry: community, licence not verified"


def test_broken_registry_never_blocks(vits_archive, tmp_path, capsys):
    bad = tmp_path / "registry" / "models.yaml"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("not: [valid", encoding="utf-8")
    code = main(["build-local", str(vits_archive), ACCEPT, "--out", str(tmp_path / "o"),
                 "--skip-smoke", "--registry", str(bad)])
    assert code == 0


# ----------------------------------------------------------------------------- smoke


def test_smoke_runs_when_available_and_failure_blocks(vits_archive, tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    calls = []

    def ok(pack_dir):
        calls.append(pack_dir.name)
        return SimpleNamespace(ok=True, problems=[], duration=1.5, sid=0)

    monkeypatch.setattr(local_mod, "run_smoke", ok)
    reg = str(tmp_path / "none.yaml")
    assert main(["build-local", str(vits_archive), ACCEPT, "--out", str(tmp_path / "a"), "--registry", reg]) == 0
    assert calls == ["local-vits-fake"] and "passed" in capsys.readouterr().out

    monkeypatch.setattr(
        local_mod, "run_smoke", lambda d: SimpleNamespace(ok=False, problems=["silent audio"], duration=0, sid=0)
    )
    assert main(["build-local", str(vits_archive), ACCEPT, "--out", str(tmp_path / "b"), "--registry", reg]) == 1
    assert "smoke test failed" in capsys.readouterr().err
    assert not (tmp_path / "b" / "local-vits-fake-v1.zip").exists()


def test_smoke_is_skipped_when_sherpa_is_missing(vits_archive, tmp_path, monkeypatch, capsys):
    from readori_voicepack.sherpa import SherpaUnavailable

    def missing(_pack_dir):
        raise SherpaUnavailable("sherpa-onnx is not installed")

    monkeypatch.setattr(local_mod, "run_smoke", missing)
    code = main(["build-local", str(vits_archive), ACCEPT, "--out", str(tmp_path / "a"),
                 "--registry", str(tmp_path / "none.yaml")])
    assert code == 0
    assert "skipped (sherpa-onnx is not installed" in capsys.readouterr().out


# ----------------------------------------------------------------------------- isolation


def _local_sidecar(vits_archive, tmp_path, capsys):
    out = tmp_path / "dist-local"
    assert main(["build-local", str(vits_archive), ACCEPT, "--out", str(out), "--skip-smoke",
                 "--registry", str(tmp_path / "none.yaml")]) == 0
    capsys.readouterr()
    return out, _sidecar(out, "local-vits-fake")


def test_index_refuses_local_sidecars(vits_archive, tmp_path, capsys):
    out, sidecar = _local_sidecar(vits_archive, tmp_path, capsys)
    with pytest.raises(VoicePackError, match="self-built"):
        ix.entry_from_sidecar(sidecar, "readori/readori-voice-packs")
    index_path = tmp_path / "catalog" / "v1" / "index.json"
    with pytest.raises(VoicePackError, match="local"):
        ix.update_index(index_path, ix.find_sidecars(out), "readori/readori-voice-packs")
    assert not index_path.exists()
    assert main(["index", "--sidecars", str(out), "--repo", "readori/readori-voice-packs",
                 "--index", str(index_path)]) == 1
    assert not index_path.exists()


def test_ba_manifest_refuses_local_packs(vits_archive, tmp_path, capsys):
    out, sidecar = _local_sidecar(vits_archive, tmp_path, capsys)
    pack_dir = out / "local-vits-fake"
    # via sidecar tier (no registry entry)
    with pytest.raises(VoicePackError, match="self-built"):
        build_ba_manifest(pack_dir, sidecar=sidecar)
    # even if the attribution notice were gone, the sidecar tier alone refuses
    (pack_dir / ATTRIBUTION_NAME).unlink()
    with pytest.raises(VoicePackError, match="local"):
        build_ba_manifest(pack_dir, sidecar={"tier": "local"})
    # a registry entry does not override a local sidecar
    with pytest.raises(VoicePackError, match="local"):
        build_ba_manifest(pack_dir, entry=make_entry(), sidecar={"tier": "local"})
    sidecar_path = out / "local-vits-fake-v1.zip.json"
    assert main(["ba-manifest", str(pack_dir), "--sidecar", str(sidecar_path),
                 "--out", str(tmp_path / "ba")]) == 1
    assert not (tmp_path / "ba").exists()


def test_ba_manifest_refuses_self_built_directory_without_sidecar(vits_archive, tmp_path, capsys):
    out, _ = _local_sidecar(vits_archive, tmp_path, capsys)
    with pytest.raises(VoicePackError, match="self-built"):
        build_ba_manifest(out / "local-vits-fake")


def test_pack_command_cannot_label_registry_pack_as_local(built_vits, tmp_path):
    entry, built = built_vits
    with pytest.raises(VoicePackError, match="registry pack cannot be packed as a local"):
        pack_directory(built.pack_dir, tmp_path / "d", entry=entry, local=LocalMeta("x", ["en"]))
    # the CLI never passes ``local``: a registry pack keeps its official sidecar
    result = pack_directory(built.pack_dir, tmp_path / "d", entry=entry)
    assert result.sidecar["tier"] == "official"
    assert result.sidecar["recommended"] is True


def test_pack_command_refuses_self_built_directory(vits_archive, tmp_path, capsys):
    out, _ = _local_sidecar(vits_archive, tmp_path, capsys)
    with pytest.raises(VoicePackError, match="self-built"):
        pack_directory(out / "local-vits-fake", tmp_path / "x")
    assert main(["pack", str(out / "local-vits-fake"), "--registry", str(tmp_path / "none.yaml"),
                 "--out", str(tmp_path / "x")]) == 1
    assert not (tmp_path / "x").exists()


def test_official_and_community_behaviour_unchanged(built_vits, tmp_path):
    entry, built = built_vits
    result = pack_directory(built.pack_dir, tmp_path / "dist", entry=entry)
    side = result.sidecar
    assert side["tier"] == "official" and side["appleAssetPackId"] == "readori.voice.zh-fake-v1"
    assert ix.entry_from_sidecar(side, "readori/readori-voice-packs")["tier"] == "official"
    assert build_ba_manifest(built.pack_dir, entry=entry)["assetPackID"] == "readori.voice.zh-fake-v1"


def test_registry_build_is_unaffected_by_shared_core(tmp_path, vits_archive):
    """build_pack (registry) and build-local share assemble_pack; layout output must agree."""
    entry = make_entry()
    reg_pack = build_pack(entry, vits_archive, tmp_path / "reg", repo_root=tmp_path)
    out = tmp_path / "loc"
    assert main(["build-local", str(vits_archive), ACCEPT, "--out", str(out), "--skip-smoke",
                 "--language", "zh-CN", "--registry", str(tmp_path / "none.yaml")]) == 0
    loc = json.loads((out / "local-vits-fake" / MANIFEST_NAME).read_text(encoding="utf-8"))
    for key in ("type", "model", "tokens", "dataDir", "lexicon", "modelSHA256", "modelBytes"):
        assert loc[key] == reg_pack.manifest[key]
