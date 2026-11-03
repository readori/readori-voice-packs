"""Tests for integrations/cosyvoice/readori_cosyvoice_core.py (pure; no torch / cosyvoice)."""

from __future__ import annotations

import io
import json
import struct
import wave
from pathlib import Path

import pytest
from readori_cosyvoice_core import (
    DEFAULT_DIALECT_IDS,
    DIALECTS,
    RequestError,
    build_arg_parser,
    build_wav,
    check_bearer,
    config_from_args,
    cuda_visible_devices_for,
    parse_dialect_list,
    parse_speech_request,
    parse_speed,
    prompt_wav_problem,
    readori_speed_to_factor,
    sanitize_text,
    wav_header,
)

INTEGRATIONS = Path(__file__).resolve().parent.parent / "integrations"


def body(**fields: object) -> bytes:
    return json.dumps(fields, ensure_ascii=False).encode("utf-8")


def parse(**fields: object):
    return parse_speech_request(body(**fields), max_chars=600)


# ---- speed ---------------------------------------------------------------------------


def test_readori_speed_scale_is_piecewise_linear():
    assert readori_speed_to_factor(0) == pytest.approx(0.5)
    assert readori_speed_to_factor(5) == pytest.approx(1.0)
    assert readori_speed_to_factor(10) == pytest.approx(2.0)
    values = [readori_speed_to_factor(i) for i in range(11)]
    assert values == sorted(values)


def test_parse_speed_integers_are_readori_scale():
    assert parse_speed(5) == pytest.approx(1.0)
    assert parse_speed("5") == pytest.approx(1.0)
    assert parse_speed(10) == pytest.approx(2.0)
    assert parse_speed(0) == pytest.approx(0.5)


def test_parse_speed_floats_are_openai_scale():
    assert parse_speed(1.0) == pytest.approx(1.0)
    assert parse_speed("1.25") == pytest.approx(1.25)
    assert parse_speed(0.25) == pytest.approx(0.5)  # clamped to the engine band
    assert parse_speed(4.0) == pytest.approx(2.0)


def test_parse_speed_default_and_invalid():
    assert parse_speed(None) == 1.0
    assert parse_speed("") == 1.0
    for bad in (11, -1, 0.1, 4.5, True, "fast", [1], float("nan")):
        with pytest.raises(RequestError) as info:
            parse_speed(bad)
        assert info.value.status == 400


# ---- request parsing -----------------------------------------------------------------


def test_parse_minimal_request_uses_defaults():
    req = parse(input="你好")
    assert req.text == "你好"
    assert req.dialect.id == "mandarin"
    assert req.speed == 1.0
    assert req.response_format == "wav"


def test_parse_voice_is_case_insensitive_and_maps_instruct():
    req = parse(model="x", input="好少咯", voice="Cantonese", speed=5, response_format="wav")
    assert req.dialect.id == "cantonese"
    assert req.dialect.instruct == (
        "You are a helpful assistant. 请用广东话表达。<|endofprompt|>"
    )


def test_blank_voice_falls_back_to_first_enabled():
    req = parse_speech_request(
        body(input="hi", voice=""), max_chars=600, enabled=("sichuan", "mandarin")
    )
    assert req.dialect.id == "sichuan"


def test_unknown_or_disabled_voice_is_400():
    with pytest.raises(RequestError) as info:
        parse(input="hi", voice="klingon")
    assert info.value.status == 400
    assert info.value.code == "unknown_voice"
    with pytest.raises(RequestError):
        parse_speech_request(body(input="hi", voice="shandong"), max_chars=600)


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        (b"not json", 400),
        (b"[1]", 400),
        (b'{"input": 5}', 400),
        (b'{"input": "   "}', 400),
        (b'{"input": "hi", "response_format": "mp3"}', 400),
        (b'{"input": "hi", "voice": 3}', 400),
        (b"x" * (64 * 1024 + 1), 413),
    ],
)
def test_bad_requests_map_to_http_errors(raw: bytes, status: int):
    with pytest.raises(RequestError) as info:
        parse_speech_request(raw, max_chars=600)
    assert info.value.status == status
    assert info.value.to_json()["error"]["code"]


def test_input_length_limit():
    assert len(parse(input="字" * 600).text) == 600
    with pytest.raises(RequestError) as info:
        parse(input="字" * 601)
    assert info.value.status == 413
    assert info.value.code == "input_too_long"


def test_sanitize_removes_control_tokens_but_keeps_tags():
    assert sanitize_text("a<|endofprompt|>b") == "ab"
    assert sanitize_text("[breath]你好\x00\x07") == "[breath]你好"
    with pytest.raises(RequestError):
        parse(input="<|endofprompt|>")


def test_dialect_table_is_consistent():
    assert set(DEFAULT_DIALECT_IDS) <= set(DIALECTS)
    for dialect in DIALECTS.values():
        assert dialect.instruct.startswith("You are a helpful assistant.")
        assert dialect.instruct.endswith("<|endofprompt|>")
    assert DIALECTS["mandarin"].mode == "cross_lingual"
    assert DIALECTS["sichuan"].mode == "instruct2"


def test_parse_dialect_list():
    assert parse_dialect_list("Mandarin, sichuan,sichuan") == ["mandarin", "sichuan"]
    with pytest.raises(ValueError):
        parse_dialect_list("mandarin,klingon")
    with pytest.raises(ValueError):
        parse_dialect_list(" , ")


# ---- WAV -----------------------------------------------------------------------------


def test_wav_header_layout():
    header = wav_header(1000, 24000)
    assert len(header) == 44
    assert header[:4] == b"RIFF"
    assert header[8:16] == b"WAVEfmt "
    assert struct.unpack("<I", header[4:8])[0] == 36 + 1000
    fmt = struct.unpack("<IHHIIHH", header[16:36])
    assert fmt == (16, 1, 1, 24000, 48000, 2, 16)
    assert header[36:40] == b"data"
    assert struct.unpack("<I", header[40:44])[0] == 1000


def test_build_wav_is_readable_by_stdlib():
    pcm = struct.pack("<4h", 0, 1000, -1000, 32767)
    data = build_wav(pcm, 24000)
    with wave.open(io.BytesIO(data), "rb") as handle:
        assert handle.getframerate() == 24000
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getnframes() == 4
        assert handle.readframes(4) == pcm


def test_wav_header_rejects_bad_values():
    with pytest.raises(ValueError):
        wav_header(-1, 24000)
    with pytest.raises(ValueError):
        wav_header(10, 0)


# ---- auth ----------------------------------------------------------------------------


def test_check_bearer():
    assert check_bearer(None, None)
    assert check_bearer("anything", "")
    assert check_bearer("Bearer s3cret", "s3cret")
    assert check_bearer("bearer s3cret", "s3cret")
    assert not check_bearer(None, "s3cret")
    assert not check_bearer("Bearer wrong", "s3cret")
    assert not check_bearer("Basic s3cret", "s3cret")


# ---- config --------------------------------------------------------------------------


def make_args(env: dict[str, str], argv: list[str] | None = None):
    return build_arg_parser(env).parse_args(argv or [])


def test_config_defaults_and_env(tmp_path: Path):
    wav = tmp_path / "p.wav"
    env = {"READORI_COSYVOICE_PROMPT_WAV": str(wav), "READORI_COSYVOICE_PORT": "9999"}
    cfg = config_from_args(make_args(env))
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9999
    assert cfg.max_chars == 600
    assert cfg.token is None
    assert cfg.dialects == DEFAULT_DIALECT_IDS
    cfg = config_from_args(make_args(env, ["--port", "9880", "--token", "t", "--device", "cuda:1"]))
    assert (cfg.port, cfg.token, cfg.device) == (9880, "t", "cuda:1")


def test_config_requires_prompt_wav_and_valid_values():
    with pytest.raises(ValueError, match="prompt wav"):
        config_from_args(make_args({}))
    with pytest.raises(ValueError):
        config_from_args(make_args({}, ["--prompt-wav", "a.wav", "--device", "tpu"]))
    with pytest.raises(ValueError):
        config_from_args(make_args({}, ["--prompt-wav", "a.wav", "--max-chars", "0"]))


def test_cuda_visible_devices_for():
    assert cuda_visible_devices_for("cpu") == ""
    assert cuda_visible_devices_for("cuda:2") == "2"
    assert cuda_visible_devices_for("cuda") is None
    assert cuda_visible_devices_for("auto") is None


def test_prompt_wav_problem(tmp_path: Path):
    assert "not found" in (prompt_wav_problem(str(tmp_path / "missing.wav")) or "")
    good = tmp_path / "good.wav"
    with wave.open(str(good), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 100)
    assert prompt_wav_problem(str(good)) is None
    slow = tmp_path / "slow.wav"
    with wave.open(str(slow), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 100)
    assert "16000" in (prompt_wav_problem(str(slow)) or "")


# ---- engine templates ----------------------------------------------------------------


def _engines() -> list[dict]:
    return json.loads((INTEGRATIONS / "cosyvoice" / "readori-engines.json").read_text("utf-8"))


def test_engine_files_match_the_readori_contract():
    engines = _engines()
    assert len(engines) == len({e["name"] for e in engines})
    for engine in engines:
        assert engine["url"].startswith("http://192.168.1.10:9880/v1/audio/speech,{")
        assert "authorization" not in engine.get("header", "").lower()  # no secrets over http
        url, _, options = engine["url"].partition(",{")
        sent = json.loads("{" + options)
        assert sent["method"] == "POST"
        assert sent["body"]["input"] == "{{speakText}}"
        assert sent["body"]["speed"] == "{{speakSpeed}}"
        assert sent["body"]["voice"] in {"{{voice}}", *DIALECTS}
        json.loads(engine["header"])
    baked = [json.loads("{" + e["url"].partition(",{")[2])["body"]["voice"] for e in engines[:-1]]
    assert baked == list(DEFAULT_DIALECT_IDS)
    picker = engines[-1]
    assert picker["voices"] and set(picker["voices"]) <= set(DIALECTS)
    single = json.loads((INTEGRATIONS / "cosyvoice" / "readori-engine-sichuan.json").read_text("utf-8"))
    assert "sichuan" in single["url"]


def test_azure_engine_template():
    engine = json.loads((INTEGRATIONS / "microsoft" / "readori-engine-azure.json").read_text("utf-8"))
    assert engine["url"].startswith("https://<region>.tts.speech.microsoft.com/cognitiveservices/v1,{")
    headers = json.loads(engine["header"])
    assert headers["Ocp-Apim-Subscription-Key"] == "<YOUR_KEY>"
    assert headers["Content-Type"] == "application/ssml+xml"
    assert headers["X-Microsoft-OutputFormat"] == "audio-24khz-48kbitrate-mono-mp3"
    sent = json.loads("{" + engine["url"].partition(",{")[2])
    assert sent["method"] == "POST"
    ssml = sent["body"]
    assert "name='{{voice}}'" in ssml
    assert "{{String(speakText).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}" in ssml
    assert "{{(speakSpeed - 5) * 10}}%" in ssml
    assert "zh-HK-HiuMaanNeural" in engine["voices"]
    assert "zh-CN-sichuan-YunxiNeural" in engine["voices"]
    assert len(engine["voices"]) == len(set(engine["voices"]))
