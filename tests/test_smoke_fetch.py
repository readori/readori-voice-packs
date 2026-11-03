from __future__ import annotations

import hashlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from readori_voicepack import fetch as fe
from readori_voicepack import sherpa
from readori_voicepack import smoke as sm
from readori_voicepack.common import VoicePackError
from readori_voicepack.samples import audit_text, smoke_text

from .conftest import make_entry

# ----------------------------------------------------------------------------- smoke criteria


def _audio(seconds=1.0, sr=16000, amp=0.3):
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr


def test_check_audio_accepts_good_audio():
    assert sherpa.check_audio(*_audio()) == []
    assert sherpa.check_audio(*_audio(seconds=0.3)) == []
    assert sherpa.check_audio(*_audio(seconds=29.9)) == []


@pytest.mark.parametrize(
    "samples, rate, needle",
    [
        (np.zeros(0, dtype=np.float32), 16000, "no samples"),
        (np.ones(100, dtype=np.float32), 0, "sample rate"),
        (np.array([0.1, np.nan, 0.2], dtype=np.float32), 16000, "NaN"),
        (np.array([0.1, np.inf], dtype=np.float32), 16000, "NaN or Inf"),
        (_audio(seconds=0.1)[0], 16000, "duration"),
        (_audio(seconds=31)[0], 16000, "duration"),
        (np.zeros(16000, dtype=np.float32), 16000, "silent"),
    ],
)
def test_check_audio_rejects(samples, rate, needle):
    assert any(needle in p for p in sherpa.check_audio(samples, rate))


class FakeTts:
    def __init__(self, samples, rate=16000):
        self.samples, self.rate, self.calls = samples, rate, []

    def generate(self, text, sid=0, speed=1.0):
        self.calls.append((text, sid))
        return SimpleNamespace(samples=self.samples, sample_rate=self.rate)


def test_run_smoke_uses_default_speaker_and_language_text(built_vits):
    _, built = built_vits
    fake = FakeTts(_audio()[0])
    result = sm.run_smoke(built.pack_dir, factory=lambda root, manifest: fake)
    assert result.ok
    assert fake.calls == [(smoke_text("zh-CN"), 0)]
    assert result.samples == 16000
    assert result.duration == pytest.approx(1.0)


def test_run_smoke_reports_problems_and_overrides(built_vits):
    _, built = built_vits
    fake = FakeTts(np.zeros(100, dtype=np.float32))
    result = sm.run_smoke(
        built.pack_dir, text="custom", sid=0, factory=lambda root, manifest: fake
    )
    assert not result.ok
    assert fake.calls == [("custom", 0)]
    assert sm.run_smoke(
        built.pack_dir, sample_text="preset text", factory=lambda r, m: FakeTts(_audio()[0])
    ).text == "preset text"


def test_run_smoke_without_sherpa_is_a_clear_error(built_vits, monkeypatch):
    _, built = built_vits
    monkeypatch.setitem(sys.modules, "sherpa_onnx", None)
    with pytest.raises(VoicePackError, match=r"pip install -e \.\[audio\]"):
        sm.run_smoke(built.pack_dir)


def test_run_smoke_missing_manifest(tmp_path):
    with pytest.raises(VoicePackError, match="not found"):
        sm.run_smoke(tmp_path)


def test_sample_texts_by_language():
    assert "公园" in smoke_text("zh-CN,en-US")
    assert "fox" in smoke_text("en-US")
    assert "fox" in smoke_text(None)
    assert "fox" in smoke_text("xx")  # unknown language falls back to English
    assert smoke_text("zh", "override") == "override"
    assert audit_text("zh-CN").startswith("夜色渐深")
    assert audit_text("ja-JP")
    assert audit_text("de") == smoke_text("de")


# ----------------------------------------------------------------------------- fetch (file:// only)


@pytest.fixture
def served(tmp_path):
    source = tmp_path / "src" / "vits-fake.tar.bz2"
    source.parent.mkdir()
    source.write_bytes(b"fake archive payload" * 100)
    return source


def _entry(source, **upstream):
    base = {"url": source.as_uri(), "sha256": "TODO", "bytes": "TODO"}
    base.update(upstream)
    return make_entry(upstream=base) | {"upstream": base}


def test_download_refuses_non_https_by_default(served, tmp_path):
    with pytest.raises(VoicePackError, match="refusing to download over 'file'"):
        fe.download(served.as_uri(), tmp_path / "dl" / "x")
    with pytest.raises(VoicePackError, match="refusing"):
        fe.download("http://example.invalid/x", tmp_path / "dl" / "y")


def test_download_returns_hash_and_size(served, tmp_path):
    sha, size = fe.download(served.as_uri(), tmp_path / "dl" / "x", allowed_schemes=("file",))
    assert size == served.stat().st_size
    assert sha == hashlib.sha256(served.read_bytes()).hexdigest()
    assert not (tmp_path / "dl" / "x.part").exists()


def test_download_enforces_max_bytes(served, tmp_path):
    with pytest.raises(VoicePackError, match="exceeds"):
        fe.download(served.as_uri(), tmp_path / "dl" / "x", allowed_schemes=("file",), max_bytes=10)
    assert not (tmp_path / "dl" / "x.part").exists()
    assert not (tmp_path / "dl" / "x").exists()


def test_download_missing_source_fails_after_retries(tmp_path):
    missing = (tmp_path / "missing.bin").as_uri()
    with pytest.raises(VoicePackError, match="failed after 2 attempts"):
        fe.download(missing, tmp_path / "dl" / "x", allowed_schemes=("file",), retries=2, backoff=0)


def test_fetch_pinned_success_and_cache_hit(served, tmp_path, capsys):
    digest = hashlib.sha256(served.read_bytes()).hexdigest()
    entry = _entry(served, sha256=digest, bytes=served.stat().st_size)
    cache = tmp_path / "cache"
    first = fe.fetch_model(entry, cache, allowed_schemes=("file",))
    assert first.pinned and first.sha256 == digest
    assert first.path == fe.cache_path(cache, entry["id"], entry["upstream"]["url"])
    served.unlink()  # the second call must not need the source
    second = fe.fetch_model(entry, cache, allowed_schemes=("file",))
    assert second.sha256 == digest
    assert "cache hit" in capsys.readouterr().out


def test_fetch_sha_mismatch_fails_and_removes_file(served, tmp_path):
    entry = _entry(served, sha256="0" * 64, bytes=served.stat().st_size)
    with pytest.raises(VoicePackError, match="sha256 mismatch"):
        fe.fetch_model(entry, tmp_path / "cache", allowed_schemes=("file",))
    assert not fe.cache_path(tmp_path / "cache", entry["id"], entry["upstream"]["url"]).exists()


def test_fetch_size_mismatch_fails(served, tmp_path):
    digest = hashlib.sha256(served.read_bytes()).hexdigest()
    entry = _entry(served, sha256=digest, bytes=1)
    with pytest.raises(VoicePackError, match="size mismatch"):
        fe.fetch_model(entry, tmp_path / "cache", allowed_schemes=("file",))


def test_fetch_unpinned_prints_hash_and_requires_flag(served, tmp_path, capsys):
    entry = _entry(served)
    cache = tmp_path / "cache"
    with pytest.raises(VoicePackError, match="--allow-unpinned"):
        fe.fetch_model(entry, cache, allowed_schemes=("file",))
    out = capsys.readouterr().out
    digest = hashlib.sha256(served.read_bytes()).hexdigest()
    assert f"sha256={digest}" in out
    assert f"bytes={served.stat().st_size}" in out

    ok = fe.fetch_model(entry, cache, allow_unpinned=True, allowed_schemes=("file",))
    assert not ok.pinned and ok.sha256 == digest


def test_fetch_stale_cache_is_replaced(served, tmp_path):
    digest = hashlib.sha256(served.read_bytes()).hexdigest()
    entry = _entry(served, sha256=digest, bytes=served.stat().st_size)
    cache = tmp_path / "cache"
    target = fe.cache_path(cache, entry["id"], entry["upstream"]["url"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"corrupted")
    result = fe.fetch_model(entry, cache, allowed_schemes=("file",))
    assert result.sha256 == digest
    assert target.read_bytes() == served.read_bytes()


def test_archive_filename():
    assert fe.archive_filename("https://h/a/b/vits-x.tar.bz2?x=1") == "vits-x.tar.bz2"
    with pytest.raises(VoicePackError):
        fe.archive_filename("https://h/")
