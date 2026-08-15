"""The GPU box: ears, brain, and mouth on one GPU.

- POST /v1/audio/transcriptions: audio in (anything ffmpeg reads, transcoded to
  16k mono wav), transcription JSON out. Proxied to local vLLM (Whisper).
- POST /v1/chat/completions: OpenAI-style chat, streaming or not. Proxied to
  local vLLM (Gemma 4 31B). Enabled when BRAIN_MODEL_LOCATION is set.
- POST /v1/audio/speech: {"input": text} in, WAV bytes out. Kokoro on CUDA in
  this process.
- GET /healthz: 200 only when every enabled model process is ready.
"""
import io
import os
import subprocess
import tempfile
import wave

import httpx
import numpy as np
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

VLLM_URL = os.environ.get("VLLM_URL", "http://127.0.0.1:8001")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:8002")
BRAIN_ENABLED = bool(os.environ.get("BRAIN_MODEL_LOCATION"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "openai/whisper-large-v3-turbo")
SAMPLE_RATE = 24000

app = FastAPI()
_kokoro = None


def _to_wav16k(data: bytes) -> bytes:
    """Transcode arbitrary browser audio (webm/opus, ogg, m4a, wav) to 16k mono WAV."""
    with tempfile.NamedTemporaryFile(suffix=".bin") as src:
        src.write(data)
        src.flush()
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src.name,
             "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
            capture_output=True, check=True,
        )
        return out.stdout


@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile):
    raw = await file.read()
    try:
        wav = _to_wav16k(raw)
    except subprocess.CalledProcessError as e:
        return JSONResponse({"error": "transcode failed", "detail": e.stderr.decode()[-500:]}, status_code=400)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VLLM_URL}/v1/audio/transcriptions",
            files={"file": ("audio.wav", wav, "audio/wav")},
            data={"model": WHISPER_MODEL},
        )
    return JSONResponse(resp.json(), status_code=resp.status_code)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Streaming-safe proxy to the brain vLLM. LiteLLM/ADK talk to this."""
    if not BRAIN_ENABLED:
        return JSONResponse({"error": "no brain configured on this box"}, status_code=404)
    body = await request.body()
    client = httpx.AsyncClient(timeout=None)
    upstream = await client.send(
        client.build_request(
            "POST", f"{BRAIN_URL}/v1/chat/completions",
            content=body, headers={"Content-Type": "application/json"},
        ),
        stream=True,
    )

    async def cleanup():
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
        background=BackgroundTask(cleanup),
    )


def _kokoro_pipeline():
    global _kokoro
    if _kokoro is None:
        from kokoro import KPipeline

        _kokoro = KPipeline(lang_code="a")  # American English
    return _kokoro


@app.post("/v1/audio/speech")
async def speak(request: Request):
    body = await request.json()
    text = (body.get("input") or "").strip()
    if not text:
        return JSONResponse({"error": "no input"}, status_code=400)
    voice = body.get("voice") or os.environ.get("KOKORO_VOICE", "af_heart")
    pipeline = _kokoro_pipeline()
    chunks = []
    for _, _, audio in pipeline(text, voice=voice):
        chunks.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
    samples = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return Response(buf.getvalue(), media_type="audio/wav")


async def _ok(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            return (await client.get(url)).status_code == 200
    except Exception:  # noqa: BLE001
        return False


@app.get("/healthz")
@app.get("/health")
async def healthz():
    ears = await _ok(f"{VLLM_URL}/health")
    brain = (await _ok(f"{BRAIN_URL}/health")) if BRAIN_ENABLED else True
    ready = ears and brain
    return JSONResponse({"ears": ears, "brain": brain}, status_code=200 if ready else 503)
