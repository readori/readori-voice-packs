"""Pure helpers for the Readori CosyVoice server.

This module deliberately imports neither torch, numpy nor cosyvoice, so it can be unit
tested anywhere. It holds:

* the dialect table (dialect id -> upstream CosyVoice3 call mode and instruct text),
* request parsing and validation for the OpenAI-compatible ``/v1/audio/speech`` body,
* the Readori 0-10 / OpenAI float speed mapping,
* the RIFF/WAV header writer,
* CLI / environment configuration parsing.

Upstream references (verified against FunAudioLLM/CosyVoice commit 074ca6d, 2026-05-25):

* ``example.py::cosyvoice3_example`` shows ``inference_instruct2(text, instruct, prompt_wav)``
  with instruct ``"You are a helpful assistant. 请用广东话表达。<|endofprompt|>"`` and
  ``inference_cross_lingual("You are a helpful assistant.<|endofprompt|>" + text, prompt_wav)``.
* ``cosyvoice/utils/common.py::instruct_list`` (lines 28-43) holds the dialect instructs.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import struct
import wave
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# --------------------------------------------------------------------------------------
# Dialect table
# --------------------------------------------------------------------------------------

INSTRUCT_PREFIX = "You are a helpful assistant."
END_OF_PROMPT = "<|endofprompt|>"

MODE_CROSS_LINGUAL = "cross_lingual"
MODE_INSTRUCT2 = "instruct2"


@dataclass(frozen=True)
class Dialect:
    id: str
    label: str
    mode: str
    # For MODE_INSTRUCT2 this is the instruct_text. For MODE_CROSS_LINGUAL it is the prefix
    # that is put in front of the text (upstream puts the control tokens inside the text).
    instruct: str


def _instruct(phrase: str) -> str:
    return f"{INSTRUCT_PREFIX} {phrase}{END_OF_PROMPT}"


# Only dialects that the upstream README lists ("Guangdong, Minnan, Sichuan, Dongbei, Shan3xi,
# Shan1xi, Shanghai, Tianjin, Shandong, Ningxia, Gansu, etc.") and that have a matching
# instruct string in upstream cosyvoice/utils/common.py are included.
DIALECTS: dict[str, Dialect] = {
    d.id: d
    for d in (
        Dialect(
            "mandarin",
            "Mandarin / 普通话",
            MODE_CROSS_LINGUAL,
            f"{INSTRUCT_PREFIX}{END_OF_PROMPT}",
        ),
        Dialect("cantonese", "Cantonese / 粤语", MODE_INSTRUCT2, _instruct("请用广东话表达。")),
        Dialect("minnan", "Minnan / 闽南话", MODE_INSTRUCT2, _instruct("请用闽南话表达。")),
        Dialect("sichuan", "Sichuan / 四川话", MODE_INSTRUCT2, _instruct("请用四川话表达。")),
        Dialect("dongbei", "Dongbei / 东北话", MODE_INSTRUCT2, _instruct("请用东北话表达。")),
        Dialect("shanghai", "Shanghai / 上海话", MODE_INSTRUCT2, _instruct("请用上海话表达。")),
        Dialect("tianjin", "Tianjin / 天津话", MODE_INSTRUCT2, _instruct("请用天津话表达。")),
        Dialect("shandong", "Shandong / 山东话", MODE_INSTRUCT2, _instruct("请用山东话表达。")),
        Dialect("shaanxi", "Shaanxi / 陕西话", MODE_INSTRUCT2, _instruct("请用陕西话表达。")),
        Dialect("shanxi", "Shanxi / 山西话", MODE_INSTRUCT2, _instruct("请用山西话表达。")),
        Dialect("ningxia", "Ningxia / 宁夏话", MODE_INSTRUCT2, _instruct("请用宁夏话表达。")),
        Dialect("gansu", "Gansu / 甘肃话", MODE_INSTRUCT2, _instruct("请用甘肃话表达。")),
    )
}

DEFAULT_DIALECT_IDS: tuple[str, ...] = (
    "mandarin",
    "cantonese",
    "minnan",
    "sichuan",
    "dongbei",
    "shanghai",
    "tianjin",
)

# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------


class RequestError(Exception):
    """A client or server error that maps to a JSON error body and an HTTP status."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def to_json(self) -> dict[str, dict[str, str]]:
        return {"error": {"message": self.message, "type": "readori_cosyvoice", "code": self.code}}


# --------------------------------------------------------------------------------------
# Speed
# --------------------------------------------------------------------------------------

OPENAI_SPEED_MIN = 0.25
OPENAI_SPEED_MAX = 4.0
# CosyVoice applies speed by interpolating the mel spectrogram; keep it in a sane band.
ENGINE_SPEED_MIN = 0.5
ENGINE_SPEED_MAX = 2.0
READORI_SPEED_MAX = 10
READORI_SPEED_NEUTRAL = 5

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


def readori_speed_to_factor(level: int) -> float:
    """Map Readori's 0-10 integer ({{speakSpeed}}) to a speed factor.

    Piecewise linear: 0 -> 0.5, 5 -> 1.0, 10 -> 2.0. (A single straight line from 0.5 to 2.0
    would put 5 at 1.25, so the two halves have different slopes to keep 5 neutral.)
    """
    if not 0 <= level <= READORI_SPEED_MAX:
        raise ValueError("Readori speed must be an integer from 0 to 10")
    if level <= READORI_SPEED_NEUTRAL:
        return 0.5 + 0.1 * level
    return 1.0 + 0.2 * (level - READORI_SPEED_NEUTRAL)


def parse_speed(value: object) -> float:
    """Return the engine speed factor for an OpenAI float or a Readori 0-10 integer.

    * JSON integers and digit-only strings (``5``, ``"5"``) are the Readori scale (0-10).
    * JSON floats and decimal strings (``1.25``, ``"1.0"``) are the OpenAI scale (0.25-4.0).
    * ``None`` or an empty string means 1.0.
    """
    if value is None or value == "":
        return 1.0
    if isinstance(value, bool):
        raise RequestError(400, "invalid_speed", "speed must be a number")
    if isinstance(value, int):
        return _readori(value)
    if isinstance(value, float):
        return _openai(value)
    if isinstance(value, str):
        text = value.strip()
        if _INT_RE.match(text):
            return _readori(int(text))
        if _FLOAT_RE.match(text):
            return _openai(float(text))
    raise RequestError(400, "invalid_speed", "speed must be a number")


def _readori(level: int) -> float:
    if not 0 <= level <= READORI_SPEED_MAX:
        raise RequestError(
            400,
            "invalid_speed",
            "integer speed is the Readori scale and must be 0-10; "
            "send a decimal such as 1.0 for the OpenAI scale (0.25-4.0)",
        )
    return readori_speed_to_factor(level)


def _openai(factor: float) -> float:
    if factor != factor or not OPENAI_SPEED_MIN <= factor <= OPENAI_SPEED_MAX:
        raise RequestError(400, "invalid_speed", "speed must be between 0.25 and 4.0")
    return min(ENGINE_SPEED_MAX, max(ENGINE_SPEED_MIN, factor))


# --------------------------------------------------------------------------------------
# Request parsing
# --------------------------------------------------------------------------------------

MAX_BODY_BYTES = 64 * 1024
SUPPORTED_FORMATS = ("wav",)

_CONTROL_TOKEN_RE = re.compile(r"<\|[^|>]*\|>")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    dialect: Dialect
    speed: float
    response_format: str


def sanitize_text(text: str) -> str:
    """Remove model control tokens (``<|...|>``) and control characters from user text.

    Without this, a book could contain ``<|endofprompt|>`` and change how the model reads the
    prompt. Square-bracket tags such as ``[breath]`` are left alone.
    """
    text = _CONTROL_TOKEN_RE.sub("", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    return text.strip()


def parse_dialect_list(value: str, *, known: Mapping[str, Dialect] = DIALECTS) -> list[str]:
    ids: list[str] = []
    for part in value.split(","):
        item = part.strip().lower()
        if not item:
            continue
        if item not in known:
            raise ValueError(f"unknown dialect id: {item!r} (known: {', '.join(sorted(known))})")
        if item not in ids:
            ids.append(item)
    if not ids:
        raise ValueError("at least one dialect must be enabled")
    return ids


def parse_speech_request(
    raw: bytes,
    *,
    max_chars: int,
    enabled: Sequence[str] = DEFAULT_DIALECT_IDS,
) -> SpeechRequest:
    """Parse and validate an OpenAI-compatible speech request body.

    Raises ``RequestError`` (with an HTTP status) for anything invalid.
    """
    if len(raw) > MAX_BODY_BYTES:
        raise RequestError(413, "body_too_large", "request body is too large")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RequestError(400, "invalid_json", "request body must be UTF-8 JSON") from exc
    if not isinstance(body, dict):
        raise RequestError(400, "invalid_json", "request body must be a JSON object")

    text = body.get("input")
    if not isinstance(text, str):
        raise RequestError(400, "missing_input", "'input' must be a string")
    text = sanitize_text(text)
    if not text:
        raise RequestError(400, "empty_input", "'input' is empty")
    if len(text) > max_chars:
        raise RequestError(
            413, "input_too_long", f"'input' is {len(text)} characters; the limit is {max_chars}"
        )

    voice = body.get("voice")
    if voice is None or (isinstance(voice, str) and not voice.strip()):
        voice_id = enabled[0]
    elif isinstance(voice, str):
        voice_id = voice.strip().lower()
    else:
        raise RequestError(400, "invalid_voice", "'voice' must be a string")
    if voice_id not in enabled or voice_id not in DIALECTS:
        raise RequestError(
            400,
            "unknown_voice",
            f"unknown voice {voice_id!r}; available: {', '.join(enabled)}",
        )

    fmt = body.get("response_format")
    fmt = "wav" if fmt is None or fmt == "" else str(fmt).lower()
    if fmt not in SUPPORTED_FORMATS:
        raise RequestError(
            400, "unsupported_format", "only response_format 'wav' is supported by this server"
        )

    speed = parse_speed(body.get("speed"))
    return SpeechRequest(text=text, dialect=DIALECTS[voice_id], speed=speed, response_format=fmt)


# --------------------------------------------------------------------------------------
# WAV
# --------------------------------------------------------------------------------------


def wav_header(data_len: int, sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    """Return a 44-byte canonical RIFF/WAVE (PCM) header for ``data_len`` bytes of audio."""
    if data_len < 0 or data_len > 0xFFFFFFFF - 36:
        raise ValueError("audio data length out of range for a WAV file")
    if sample_rate <= 0 or channels <= 0 or bits not in (8, 16, 24, 32):
        raise ValueError("invalid WAV format parameters")
    block_align = channels * bits // 8
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_len)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, sample_rate * block_align,
                      block_align, bits)
        + b"data"
        + struct.pack("<I", data_len)
    )


def build_wav(pcm16: bytes, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap little-endian signed 16-bit PCM bytes in a WAV container."""
    return wav_header(len(pcm16), sample_rate, channels, 16) + pcm16


def prompt_wav_problem(path: str) -> str | None:
    """Return a human-readable problem with the prompt wav, or None if it looks usable.

    Upstream ``load_wav`` asserts that audio which needs resampling is at least 16 kHz, so a
    lower sample rate is reported. Files the stdlib ``wave`` module cannot read (for example
    float WAV) are not rejected here; upstream decides at load time.
    """
    if not os.path.isfile(path):
        return f"prompt wav not found: {path}"
    if os.path.getsize(path) == 0:
        return f"prompt wav is empty: {path}"
    try:
        with wave.open(path, "rb") as handle:
            rate = handle.getframerate()
            frames = handle.getnframes()
    except (wave.Error, EOFError):
        return None
    if rate < 16000:
        return f"prompt wav sample rate is {rate} Hz; CosyVoice needs at least 16000 Hz"
    if frames == 0:
        return "prompt wav contains no audio"
    return None


# --------------------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------------------


def check_bearer(header_value: str | None, token: str | None) -> bool:
    """True if no token is configured, or the Authorization header carries the token."""
    if not token:
        return True
    if not header_value:
        return False
    scheme, _, presented = header_value.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(presented.strip().encode("utf-8"), token.encode("utf-8"))


# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ServerConfig:
    cosyvoice_dir: str
    model_dir: str
    prompt_wav: str
    host: str
    port: int
    token: str | None
    max_chars: int
    device: str
    dialects: tuple[str, ...]
    queue_timeout: float


def _env(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    return value if value not in (None, "") else default


def build_arg_parser(env: Mapping[str, str] | None = None) -> argparse.ArgumentParser:
    """CLI parser; every flag falls back to a READORI_COSYVOICE_* environment variable."""
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(
        description="Self-hosted CosyVoice3 dialect TTS server for the Readori app."
    )
    parser.add_argument(
        "--cosyvoice-dir",
        default=_env(env, "READORI_COSYVOICE_DIR", "CosyVoice"),
        help="path of your CosyVoice git checkout (added to sys.path) [READORI_COSYVOICE_DIR]",
    )
    parser.add_argument(
        "--model-dir",
        default=_env(env, "READORI_COSYVOICE_MODEL_DIR", "pretrained_models/Fun-CosyVoice3-0.5B"),
        help="Fun-CosyVoice3-0.5B-2512 model directory [READORI_COSYVOICE_MODEL_DIR]",
    )
    parser.add_argument(
        "--prompt-wav",
        default=_env(env, "READORI_COSYVOICE_PROMPT_WAV", ""),
        help="reference wav of a voice you own or have consent to use "
        "[READORI_COSYVOICE_PROMPT_WAV] (required)",
    )
    parser.add_argument("--host", default=_env(env, "READORI_COSYVOICE_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(_env(env, "READORI_COSYVOICE_PORT", "9880"))
    )
    parser.add_argument(
        "--token",
        default=_env(env, "READORI_COSYVOICE_TOKEN", ""),
        help="optional bearer token; the Readori app only sends it over HTTPS "
        "[READORI_COSYVOICE_TOKEN]",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=int(_env(env, "READORI_COSYVOICE_MAX_CHARS", "600")),
        help="maximum characters per request [READORI_COSYVOICE_MAX_CHARS]",
    )
    parser.add_argument(
        "--device",
        default=_env(env, "READORI_COSYVOICE_DEVICE", "auto"),
        help="auto, cpu, cuda or cuda:N (selected through CUDA_VISIBLE_DEVICES, because the "
        "upstream constructor has no device argument) [READORI_COSYVOICE_DEVICE]",
    )
    parser.add_argument(
        "--dialects",
        default=_env(env, "READORI_COSYVOICE_DIALECTS", ",".join(DEFAULT_DIALECT_IDS)),
        help=f"comma separated dialect ids; known: {', '.join(DIALECTS)} "
        "[READORI_COSYVOICE_DIALECTS]",
    )
    parser.add_argument(
        "--queue-timeout",
        type=float,
        default=float(_env(env, "READORI_COSYVOICE_QUEUE_TIMEOUT", "20")),
        help="seconds a request waits for the single synthesis slot before 503",
    )
    return parser


_DEVICE_RE = re.compile(r"^(auto|cpu|cuda(:\d+)?)$")


def config_from_args(args: argparse.Namespace) -> ServerConfig:
    """Validate parsed arguments. Raises ``ValueError`` with a readable message."""
    if not args.prompt_wav:
        raise ValueError(
            "a prompt wav is required: pass --prompt-wav or set READORI_COSYVOICE_PROMPT_WAV "
            "(use your own voice, or one you have rights and consent to use)"
        )
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be 1-65535")
    if not 1 <= args.max_chars <= 5000:
        raise ValueError("max chars must be 1-5000")
    device = str(args.device).strip().lower()
    if not _DEVICE_RE.match(device):
        raise ValueError("device must be auto, cpu, cuda or cuda:N")
    return ServerConfig(
        cosyvoice_dir=args.cosyvoice_dir,
        model_dir=args.model_dir,
        prompt_wav=args.prompt_wav,
        host=args.host,
        port=args.port,
        token=args.token or None,
        max_chars=args.max_chars,
        device=device,
        dialects=tuple(parse_dialect_list(args.dialects)),
        queue_timeout=max(0.0, args.queue_timeout),
    )


def cuda_visible_devices_for(device: str) -> str | None:
    """Value for CUDA_VISIBLE_DEVICES for a --device choice, or None to leave it alone."""
    if device == "cpu":
        return ""
    if device.startswith("cuda:"):
        return device.split(":", 1)[1]
    return None
