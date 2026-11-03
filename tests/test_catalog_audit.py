from __future__ import annotations

import json
import math
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from readori_voicepack import audit as aud
from readori_voicepack import catalog as cat
from readori_voicepack import validate as val
from readori_voicepack.common import CATALOG_NAME, MANIFEST_NAME, VoicePackError, sha256_file

from .conftest import make_entry, vits_files, write_tar_bz2

# ----------------------------------------------------------------------------- catalog


def test_init_catalog_contains_only_supplied_facts():
    catalog = cat.init_catalog(
        catalog_id="x.y.v1",
        speaker_count=3,
        default_speaker=1,
        profile="p",
        language="zh-CN,en-US",
        speaker_names=["a", "b", "c"],
    )
    assert catalog["speakerCount"] == 3
    assert catalog["defaultSpeaker"] == 1
    assert catalog["language"] == "zh-CN,en-US"
    assert [s["sourceSpeakerId"] for s in catalog["speakers"]] == ["a", "b", "c"]
    assert all(s["languages"] == ["zh-CN", "en-US"] for s in catalog["speakers"])
    for speaker in catalog["speakers"]:
        assert set(speaker) <= {"sid", "analysisTags", "sourceSpeakerId", "languages", "language"}
        assert "gender" not in speaker and "accent" not in speaker
    assert cat.decode_problems(catalog) == []
    assert cat.semantic_problems(catalog, 3, 1) == []


def test_init_catalog_single_language_uses_language_key():
    catalog = cat.init_catalog(catalog_id="x", speaker_count=1, language="yue")
    assert catalog["speakers"][0]["language"] == "yue"
    assert "languages" not in catalog["speakers"][0]
    assert "modelProfile" not in catalog


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"speaker_count": 0}, "1...512"),
        ({"speaker_count": 513}, "1...512"),
        ({"speaker_count": 2, "default_speaker": 2}, "within"),
        ({"speaker_count": 2, "speaker_names": ["only-one"]}, "expected 2"),
    ],
)
def test_init_catalog_validation(kwargs, match):
    with pytest.raises(VoicePackError, match=match):
        cat.init_catalog(catalog_id="x", **kwargs)


def test_semantic_problems_app_rules():
    good = {"schemaVersion": 1, "speakerCount": 2, "defaultSpeaker": 1,
            "speakers": [{"sid": 0}, {"sid": 1}]}  # fmt: skip
    assert cat.semantic_problems(good, 2, 1) == []
    assert cat.semantic_problems({"speakers": []}, 2, 0)
    assert cat.semantic_problems({"speakers": [{"sid": 2}]}, 2, 0)  # out of range
    assert cat.semantic_problems({"speakers": [{"sid": -1}]}, 2, 0)
    assert cat.semantic_problems({"speakers": [{"sid": 0}, {"sid": 0}]}, 2, 0)  # duplicate
    assert cat.semantic_problems({"speakerCount": 3, "speakers": [{"sid": 0}]}, 2, 0)
    assert cat.semantic_problems({"defaultSpeaker": 1, "speakers": [{"sid": 0}]}, 2, 0)
    assert cat.semantic_problems({"schemaVersion": 0, "speakers": [{"sid": 0}]}, 2, 0)


def test_semantic_strict_adds_builder_consistency():
    catalog = {"defaultSpeaker": 1, "speakers": [{"sid": 0}, {"sid": 1}]}
    assert cat.semantic_problems(catalog, 2, 0, strict=False) == []
    assert any("defaultSpeaker" in p for p in cat.semantic_problems(catalog, 2, 0, strict=True))


def test_decode_problems_match_swift_types():
    assert cat.decode_problems([]) == ["catalog: expected JSON object"]
    assert cat.decode_problems({}) == ["speakers: required array missing"]
    assert any("sid" in p for p in cat.decode_problems({"speakers": [{"name": "x"}]}))
    assert cat.decode_problems({"speakers": [{"sid": True}]})  # bool is not an Int
    assert cat.decode_problems({"speakers": [{"sid": 0, "gender": 1}]})
    assert cat.decode_problems({"speakers": [{"sid": 0, "displayName": 5}]})
    assert cat.decode_problems({"speakers": [{"sid": 0, "tags": ["a", 1]}]})
    assert cat.decode_problems({"speakers": [{"sid": 0, "acoustics": {"durationSec": "x"}}]})
    assert cat.decode_problems({"speakerCount": "2", "speakers": [{"sid": 0}]})
    ok = {"speakers": [{"sid": 0, "displayName": {"zh": "z"}, "acoustics": {"medianF0Hz": 245.0,
          "sampleRate": 22050}, "attributes": {"k": ["v"]}, "gender": None}]}  # fmt: skip
    assert cat.decode_problems(ok) == []


def test_load_catalog_file_errors(tmp_path):
    with pytest.raises(VoicePackError, match="not found"):
        cat.load_catalog_file(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(VoicePackError, match="invalid voice catalog JSON"):
        cat.load_catalog_file(bad)
    nan = tmp_path / "nan.json"
    nan.write_text('{"speakers":[{"sid":0,"acoustics":{"rmsDbfs":NaN}}]}', encoding="utf-8")
    with pytest.raises(VoicePackError, match="non-finite"):
        cat.load_catalog_file(nan)
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (8 * 1024 * 1024 + 1))
    with pytest.raises(VoicePackError, match="exceeds"):
        cat.load_catalog_file(big)
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"speakers":[{"sid":"0"}]}', encoding="utf-8")
    with pytest.raises(VoicePackError, match="not decodable"):
        cat.load_catalog_file(wrong)


def test_read_speaker_names(tmp_path):
    path = tmp_path / "s.txt"
    path.write_text("a\n\n  b  \nc\n", encoding="utf-8")
    assert cat.read_speaker_names(path) == ["a", "b", "c"]


# ----------------------------------------------------------------------------- audit maths


def _sine(freq: float, sr: int = 16000, seconds: float = 1.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * math.pi * freq * t)).astype(np.float32)


def test_rms_peak_and_centroid():
    x = _sine(1000)
    assert aud.rms_db(x) == pytest.approx(20 * math.log10(0.3 / math.sqrt(2)), abs=0.1)
    assert aud.peak_db(x) == pytest.approx(20 * math.log10(0.3), abs=0.1)
    assert aud.spectral_centroid(x, 16000) == pytest.approx(1000, abs=30)
    assert aud.spectral_centroid(np.zeros(10, dtype=np.float32), 16000) is None
    assert aud.spectral_centroid(np.zeros(1000, dtype=np.float32), 16000) is None
    assert aud.rms_db(np.zeros(0, dtype=np.float32)) == pytest.approx(-240.0)


def test_f0_estimate_on_sine():
    assert aud.estimate_f0(_sine(200), 16000) == pytest.approx(200, rel=0.03)
    assert aud.estimate_f0(np.zeros(16000, dtype=np.float32), 16000) is None


@pytest.mark.parametrize(
    "metrics, expected",
    [
        ({"rmsDbfs": -30, "medianF0Hz": 120, "spectralCentroidHz": 1500}, ["偏轻", "低音", "偏温暖"]),
        ({"rmsDbfs": -10, "medianF0Hz": 250, "spectralCentroidHz": 3000}, ["洪亮", "高音", "偏清亮"]),
        ({"rmsDbfs": -20, "medianF0Hz": 180, "spectralCentroidHz": 2000}, ["标准响度", "中音", "自然"]),
        ({"rmsDbfs": -26, "medianF0Hz": 145, "spectralCentroidHz": 1800}, ["标准响度", "中音", "自然"]),
        ({"rmsDbfs": -17, "medianF0Hz": 210, "spectralCentroidHz": 2600}, ["标准响度", "中音", "自然"]),
        ({"rmsDbfs": None, "medianF0Hz": None, "spectralCentroidHz": None}, []),
        ({"rmsDbfs": -20}, ["标准响度"]),
    ],
)
def test_v13_label_rules_unchanged(metrics, expected):
    assert aud.labels(metrics) == expected


def test_measure_shape_and_lufs_factory():
    x = _sine(200, seconds=1.0)

    class Meter:
        def __init__(self, rate):
            self.rate = rate

        def integrated_loudness(self, data):
            return -23.123456

    met = aud.measure(x, 16000, Meter)
    assert set(met) == {"sampleRate", "durationSec", "rmsDbfs", "peakDbfs", "medianF0Hz",
                        "spectralCentroidHz", "integratedLufs"}  # fmt: skip
    assert met["sampleRate"] == 16000
    assert met["durationSec"] == 1.0
    assert met["integratedLufs"] == -23.123
    assert aud.measure(x, 16000, None)["integratedLufs"] is None


# ----------------------------------------------------------------------------- audit run


class FakeTts:
    """Deterministic fake synthesizer: each sid is a sine at a different pitch."""

    def __init__(self, bad_sids=()):
        self.calls: list[tuple[str, int]] = []
        self.bad = set(bad_sids)

    def generate(self, text, sid=0, speed=1.0):
        self.calls.append((text, sid))
        if sid in self.bad:
            samples = np.full(8000, np.nan, dtype=np.float32)
        else:
            samples = _sine(120 + 40 * sid, seconds=1.0)
        return SimpleNamespace(samples=samples, sample_rate=16000)


@pytest.fixture
def multi_pack(tmp_path):
    from readori_voicepack.build import build_pack

    archive = write_tar_bz2(tmp_path / "m.tar.bz2", vits_files(speakers=3))
    entry = make_entry(id="zh-multi-v1", preset={"speakerCount": 3})
    return build_pack(entry, archive, tmp_path / "out", repo_root=tmp_path)


def test_audit_writes_metrics_and_keeps_pack_valid(multi_pack):
    fake = FakeTts()
    result = aud.run_audit(multi_pack.pack_dir, factory=lambda root, m: fake)
    assert result.audited == 3
    assert [sid for _, sid in fake.calls] == [0, 1, 2]
    assert len({text for text, _ in fake.calls}) == 1, "every sid synthesises the same text"

    catalog = json.loads((multi_pack.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    for speaker in catalog["speakers"]:
        assert speaker["acoustics"]["sampleRate"] == 16000
        assert speaker["analysisTags"]
        assert speaker["acousticAnalysisSource"].startswith("Readori objective audit")
        assert "gender" not in speaker  # measurements only
    assert catalog["speakers"][0]["acoustics"]["medianF0Hz"] == pytest.approx(120, rel=0.05)
    assert catalog["speakers"][2]["acoustics"]["medianF0Hz"] == pytest.approx(200, rel=0.05)

    manifest = json.loads((multi_pack.pack_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["voiceCatalogSHA256"] == sha256_file(multi_pack.pack_dir / CATALOG_NAME)
    assert result.catalog_sha256 == manifest["voiceCatalogSHA256"]
    check = val.validate_directory(multi_pack.pack_dir)
    assert check.ok, [str(e) for e in check.errors]


def test_audit_max_speakers_limits_work(multi_pack):
    fake = FakeTts()
    result = aud.run_audit(multi_pack.pack_dir, max_speakers=2, factory=lambda root, m: fake)
    assert result.audited == 2
    assert [sid for _, sid in fake.calls] == [0, 1]
    catalog = json.loads((multi_pack.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    assert "acoustics" in catalog["speakers"][1]
    assert "acoustics" not in catalog["speakers"][2]
    assert val.validate_directory(multi_pack.pack_dir).ok


def test_audit_custom_text_and_language_default(multi_pack):
    fake = FakeTts()
    aud.run_audit(multi_pack.pack_dir, text="hello there", max_speakers=1, factory=lambda r, m: fake)
    assert fake.calls == [("hello there", 0)]
    fake2 = FakeTts()
    aud.run_audit(multi_pack.pack_dir, max_speakers=1, factory=lambda r, m: fake2)
    assert fake2.calls[0][0].startswith("夜色渐深")  # zh default text from v13


def test_audit_drops_nan_speaker_by_default(multi_pack):
    result = aud.run_audit(multi_pack.pack_dir, factory=lambda r, m: FakeTts(bad_sids={1}))
    assert result.skipped == [1]
    assert result.unusable_sids == [1]
    assert result.audited == 2
    catalog = json.loads((multi_pack.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    # partial catalog is valid for the app; speakerCount stays the manifest count
    assert [s["sid"] for s in catalog["speakers"]] == [0, 2]
    assert catalog["speakerCount"] == 3
    manifest = json.loads((multi_pack.pack_dir / "readori-tts-model.json").read_text(encoding="utf-8"))
    assert manifest["speakerCount"] == 3
    assert val.validate_directory(multi_pack.pack_dir).ok


def test_audit_keep_unusable_leaves_speaker_in_catalog(multi_pack):
    result = aud.run_audit(
        multi_pack.pack_dir, factory=lambda r, m: FakeTts(bad_sids={1}), drop_unusable=False
    )
    assert result.skipped == [1] and result.unusable_sids == []
    catalog = json.loads((multi_pack.pack_dir / CATALOG_NAME).read_text(encoding="utf-8"))
    assert [s["sid"] for s in catalog["speakers"]] == [0, 1, 2]
    assert "acoustics" not in catalog["speakers"][1]


def test_audit_refuses_to_drop_default_speaker(multi_pack):
    with pytest.raises(VoicePackError, match="default speaker"):
        aud.run_audit(multi_pack.pack_dir, factory=lambda r, m: FakeTts(bad_sids={0}))


def test_audit_requires_catalog_and_manifest(multi_pack, tmp_path):
    (multi_pack.pack_dir / CATALOG_NAME).unlink()
    with pytest.raises(VoicePackError, match="readori-voices.json missing"):
        aud.run_audit(multi_pack.pack_dir, factory=lambda r, m: FakeTts())
    with pytest.raises(VoicePackError, match="not found"):
        aud.run_audit(tmp_path / "nowhere", factory=lambda r, m: FakeTts())


def test_audit_without_sherpa_gives_clear_error(multi_pack, monkeypatch):
    monkeypatch.setitem(sys.modules, "sherpa_onnx", None)
    with pytest.raises(VoicePackError, match="sherpa-onnx is not installed"):
        aud.run_audit(multi_pack.pack_dir)
