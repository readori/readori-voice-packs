"""Self-hosted CosyVoice3 dialect TTS server for the Readori app.

An OpenAI-compatible ``POST /v1/audio/speech`` endpoint that returns ``audio/wav``. It imports
the official CosyVoice Python package from your own checkout; no CosyVoice code is copied here.

Privacy: request text is never logged by this server. Only lengths and timings are.

Run ``python readori_cosyvoice_server.py --help`` for the options. Pure logic (request parsing,
speed mapping, WAV header, configuration) lives in ``readori_cosyvoice_core`` and is unit tested
without torch.

Note: this module intentionally does not use ``from __future__ import annotations``; FastAPI
resolves the handlers' annotations (``Request``) from the enclosing scope at definition time.
"""

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from readori_cosyvoice_core import (
    DIALECTS,
    MAX_BODY_BYTES,
    MODE_INSTRUCT2,
    RequestError,
    ServerConfig,
    SpeechRequest,
    build_arg_parser,
    build_wav,
    check_bearer,
    config_from_args,
    cuda_visible_devices_for,
    parse_speech_request,
    prompt_wav_problem,
)

LOG = logging.getLogger("readori_cosyvoice")

# (pcm16 little-endian mono bytes, sample rate)
SynthResult = tuple[bytes, int]
Synthesizer = Callable[[SpeechRequest], SynthResult]


def _configure_logging() -> None:
    # Root stays at WARNING so that third-party libraries (CosyVoice logs through the root
    # logger) do not print request text at INFO level. Only this server's own logger is INFO.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    LOG.setLevel(logging.INFO)


def load_model(cfg: ServerConfig) -> Any:
    """Import upstream CosyVoice and load Fun-CosyVoice3-0.5B-2512 (slow; run once)."""
    visible = cuda_visible_devices_for(cfg.device)
    if visible is not None:
        # Upstream AutoModel/CosyVoice3 have no device argument; hide GPUs before torch loads.
        os.environ["CUDA_VISIBLE_DEVICES"] = visible

    repo = os.path.abspath(cfg.cosyvoice_dir)
    for path in (repo, os.path.join(repo, "third_party", "Matcha-TTS")):
        if path not in sys.path:
            sys.path.append(path)
    try:
        from cosyvoice.cli.cosyvoice import AutoModel  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            f"cannot import the official CosyVoice package from {repo!r} ({exc}). "
            "Clone https://github.com/FunAudioLLM/CosyVoice with --recursive, install its "
            "requirements, and pass --cosyvoice-dir."
        ) from exc

    started = time.monotonic()
    model = AutoModel(model_dir=cfg.model_dir)
    if type(model).__name__ != "CosyVoice3":
        raise SystemExit(
            f"{cfg.model_dir!r} is a {type(model).__name__} model; this server needs "
            "Fun-CosyVoice3-0.5B-2512 (CosyVoice3)."
        )
    LOG.info(
        "model loaded type=%s sample_rate=%s seconds=%.1f",
        type(model).__name__,
        model.sample_rate,
        time.monotonic() - started,
    )
    return model


def _to_pcm16(tts_speech: Any) -> bytes:
    """Convert one upstream ``tts_speech`` tensor (float, shape (1, N)) to int16 PCM bytes."""
    import numpy as np  # numpy is a CosyVoice dependency

    if hasattr(tts_speech, "detach"):
        tts_speech = tts_speech.detach().cpu().numpy()
    samples = np.asarray(tts_speech, dtype=np.float32).reshape(-1)
    samples = np.clip(samples, -1.0, 1.0)
    return (samples * 32767.0).astype("<i2").tobytes()


def make_synthesizer(model: Any, cfg: ServerConfig) -> Synthesizer:
    """Build the function that runs one synthesis with the official CosyVoice3 API."""

    def synthesize(req: SpeechRequest) -> SynthResult:
        dialect = req.dialect
        if dialect.mode == MODE_INSTRUCT2:
            # Upstream: inference_instruct2(tts_text, instruct_text, prompt_wav, ...)
            outputs = model.inference_instruct2(
                req.text, dialect.instruct, cfg.prompt_wav, stream=False, speed=req.speed
            )
        else:
            # Upstream: inference_cross_lingual("You are a helpful assistant.<|endofprompt|>"
            # + text, prompt_wav, ...)
            outputs = model.inference_cross_lingual(
                dialect.instruct + req.text, cfg.prompt_wav, stream=False, speed=req.speed
            )
        chunks = [_to_pcm16(item["tts_speech"]) for item in outputs]
        if not chunks:
            raise RequestError(500, "no_audio", "the model returned no audio")
        return b"".join(chunks), int(model.sample_rate)

    return synthesize


def create_app(cfg: ServerConfig, synthesizer: Synthesizer | None = None) -> Any:
    """Create the FastAPI app. ``synthesizer`` can be injected for tests; otherwise the model
    is loaded when the server starts."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response
    from starlette.concurrency import run_in_threadpool
    from starlette.exceptions import HTTPException as StarletteHTTPException

    state: dict[str, Any] = {"synth": synthesizer}
    lock = threading.Lock()  # one synthesis at a time: GPU memory is limited

    @asynccontextmanager
    async def lifespan(_app: Any):
        if state["synth"] is None:
            model = await run_in_threadpool(load_model, cfg)
            state["synth"] = make_synthesizer(model, cfg)
        yield

    app = FastAPI(
        title="Readori CosyVoice server", lifespan=lifespan, docs_url=None, redoc_url=None
    )

    @app.exception_handler(RequestError)
    async def _request_error(_request: Request, exc: RequestError) -> JSONResponse:
        return JSONResponse(exc.to_json(), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        error = RequestError(exc.status_code, "http_error", str(exc.detail))
        return JSONResponse(error.to_json(), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Only the exception class is logged: messages from third-party code can echo input.
        LOG.error("unhandled error type=%s", type(exc).__name__)
        error = RequestError(500, "internal_error", "internal server error")
        return JSONResponse(error.to_json(), status_code=500)

    def require_auth(request: Request) -> None:
        if not check_bearer(request.headers.get("authorization"), cfg.token):
            raise RequestError(401, "unauthorized", "missing or invalid bearer token")

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "model_loaded": state["synth"] is not None}

    @app.get("/v1/voices")
    async def voices(request: Request) -> dict[str, Any]:
        require_auth(request)
        return {
            "object": "list",
            "data": [
                {"id": vid, "name": DIALECTS[vid].label, "object": "voice"}
                for vid in cfg.dialects
            ],
        }

    def run_locked(req: SpeechRequest) -> tuple[bytes, int, float]:
        if not lock.acquire(timeout=cfg.queue_timeout):
            raise RequestError(503, "busy", "another synthesis is still running; retry shortly")
        try:
            started = time.monotonic()
            pcm, rate = state["synth"](req)
            return pcm, rate, time.monotonic() - started
        finally:
            lock.release()

    @app.post("/v1/audio/speech")
    async def speech(request: Request) -> Response:
        require_auth(request)
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            raise RequestError(413, "body_too_large", "request body is too large")
        req = parse_speech_request(
            await request.body(), max_chars=cfg.max_chars, enabled=cfg.dialects
        )
        if state["synth"] is None:
            raise RequestError(503, "loading", "the model is still loading")
        try:
            pcm, rate, seconds = await run_in_threadpool(run_locked, req)
        except RequestError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to a JSON 500 below
            LOG.error(
                "synthesis failed voice=%s chars=%d type=%s",
                req.dialect.id,
                len(req.text),
                type(exc).__name__,
            )
            raise RequestError(500, "synthesis_failed", "synthesis failed") from None
        audio_seconds = len(pcm) / 2 / rate
        LOG.info(
            "speech ok voice=%s chars=%d speed=%.2f audio_s=%.2f elapsed_s=%.2f rtf=%.2f",
            req.dialect.id,
            len(req.text),
            req.speed,
            audio_seconds,
            seconds,
            seconds / audio_seconds if audio_seconds else 0.0,
        )
        return Response(content=build_wav(pcm, rate), media_type="audio/wav")

    return app


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        cfg = config_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    problem = prompt_wav_problem(cfg.prompt_wav)
    if problem:
        parser.error(problem)

    _configure_logging()
    if cfg.host not in ("127.0.0.1", "localhost", "::1") and not cfg.token:
        LOG.warning(
            "listening on %s without a token: anyone on that network can use the GPU. "
            "The Readori app only sends a token over HTTPS (see README).",
            cfg.host,
        )
    import uvicorn

    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
