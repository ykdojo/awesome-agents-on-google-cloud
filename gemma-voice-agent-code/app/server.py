"""HTTP server: chat frontend + two endpoints.

- POST /chat: text or audio in; streams the answer as NDJSON events. Audio is
  transcribed (Whisper on the speech GPU service) exactly once: the transcript
  is emitted as an early `transcript` event for the UI bubble, and the same
  text (never the raw audio) is what the agent receives.
  Event order: meta, [transcript], [status...], delta..., done.
- POST /speak: text in, WAV audio out (Kokoro on the speech GPU service)
"""
import base64
import hashlib
import json
import os
import re
import threading
import traceback

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import telemetry

telemetry.setup()  # must run before the ADK Runner exists

import model
import speech_client

app = Flask(__name__, static_folder="static")


MODEL_BASE = os.environ.get("MODEL_API_BASE", "").rstrip("/")


def _wake_gpus():
    """Start (or keep) long-held waker requests against both GPU boxes so Cloud Run
    boots them. Idempotent: one waker per box at a time, no-ops when warm."""
    if MODEL_BASE:
        speech_client.ensure_waking(MODEL_BASE, "/health")
    if speech_client.enabled():
        speech_client.ensure_waking(speech_client.BASE)


# The moment this (fast, CPU-only) service comes up for any reason, the (slow,
# scale-to-zero) GPU boxes start booting too - before any page JS runs.
_wake_gpus()

# Pre-warm the session client off the request path: its first use constructs
# and authenticates an API client (10s+), which no user turn should pay.
threading.Thread(target=model.warm_session_client, daemon=True).start()


def _user_id() -> str:
    """Stable per-user key. With IAP enabled, verify the signed JWT and use its
    `sub` claim (emails can change; sub can't). Without IAP: single dev user."""
    assertion = request.headers.get("X-Goog-IAP-JWT-Assertion")
    audience = os.environ.get("IAP_AUDIENCE")
    if assertion and audience:
        from google.auth.transport import requests as ga_requests
        from google.oauth2 import id_token as g_id_token

        claims = g_id_token.verify_token(
            assertion,
            ga_requests.Request(),
            audience=audience,
            certs_url="https://www.gstatic.com/iap/verify/public_key",
        )
        if claims.get("iss") != "https://cloud.google.com/iap":
            raise PermissionError("bad IAP issuer")
        return claims["sub"].replace(":", "_")
    return "dev"


def _parse_request():
    text = None
    audio = None
    audio_mime = "audio/webm"
    session_id = "default"
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        f = request.files.get("audio")
        if f:
            audio = f.read()
            audio_mime = f.mimetype or audio_mime
        text = request.form.get("text") or None
        session_id = request.form.get("session_id") or session_id
    else:
        body = request.get_json(silent=True) or {}
        text = body.get("text")
        session_id = body.get("session_id") or session_id
    return text, audio, audio_mime, session_id


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/status")
def status():
    """Are the scale-to-zero GPU boxes awake? Any not-ready answer also (re)arms
    the long-held waker requests that actually drive their boot."""
    model_ok = speech_client.awake(MODEL_BASE, "/health") if MODEL_BASE else True
    speech_ok = speech_client.awake(speech_client.BASE) if speech_client.enabled() else True
    if not (model_ok and speech_ok):
        _wake_gpus()
    return jsonify({
        "model": model_ok, "speech": speech_ok, "ready": model_ok and speech_ok,
        "waking_seconds": speech_client.waking_seconds(),
    })


@app.get("/conversations")
def conversations_list():
    return jsonify({"conversations": model.list_conversations(_user_id())})


@app.delete("/conversations/<session_id>")
def conversations_delete(session_id):
    model.delete_conversation(_user_id(), session_id)
    return jsonify({"ok": True})


@app.patch("/conversations/<session_id>")
def conversations_rename(session_id):
    title = ((request.get_json(silent=True) or {}).get("title") or "").strip()
    if not title:
        return jsonify({"error": "no title"}), 400
    try:
        model.rename_conversation(_user_id(), session_id, title)
    except KeyError:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


@app.post("/conversations/<session_id>/prepare")
def conversations_prepare(session_id):
    """Fire-and-forget pre-creation: the frontend calls this the moment a new
    conversation id exists, so the (slow, LRO-backed) session creation runs
    while the user is still typing their first message."""
    user_id = _user_id()
    threading.Thread(
        target=model.precreate_session, args=(user_id, session_id), daemon=True
    ).start()
    return jsonify({"ok": True}), 202


@app.get("/conversations/<session_id>/messages")
def conversations_messages(session_id):
    return jsonify({"messages": model.get_history(_user_id(), session_id)})


@app.post("/chat")
def chat():
    text, audio, audio_mime, session_id = _parse_request()
    user_id = _user_id()

    def generate():
        yield json.dumps({"type": "meta", "speech_available": os.environ.get("DISABLE_TTS") != "1"}) + "\n"
        try:
            # The GPU services scale to zero; probe the ones this turn needs and be
            # honest about the wait, while the wakers drive the actual boot.
            cold = (MODEL_BASE and not speech_client.awake(MODEL_BASE, "/health")) or (
                audio and speech_client.enabled() and not speech_client.awake(speech_client.BASE)
            )
            if cold:
                _wake_gpus()
                yield json.dumps({
                    "type": "status",
                    "status": "Waking up the GPU (it sleeps when idle) - the first reply can take a few minutes",
                }) + "\n"
            message = text
            if audio:
                transcript = speech_client.transcribe(audio, audio_mime)
                yield json.dumps({"type": "transcript", "text": transcript}) + "\n"
                message = f"{text}\n{transcript}" if text else transcript
            if not message or not message.strip():
                yield json.dumps({"type": "error", "error": "I couldn't hear that - please try again."}) + "\n"
                return
            for event in model.reply_stream(text=message, session_id=session_id, user_id=user_id):
                yield json.dumps(event) + "\n"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/retry")
def retry():
    """Resume a failed turn from where it stopped (ADK invocation resume)."""
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    invocation_id = body.get("invocation_id")
    if not session_id or not invocation_id:
        return jsonify({"error": "need session_id and invocation_id"}), 400
    user_id = _user_id()

    def generate():
        yield json.dumps({"type": "meta", "speech_available": os.environ.get("DISABLE_TTS") != "1"}) + "\n"
        try:
            for event in model.retry_stream(
                session_id=session_id, invocation_id=invocation_id, user_id=user_id
            ):
                yield json.dumps(event) + "\n"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/rewind")
def rewind():
    """Give up on a failed turn: drop it from the conversation's effective history."""
    body = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    invocation_id = body.get("invocation_id")
    if not session_id or not invocation_id:
        return jsonify({"error": "need session_id and invocation_id"}), 400
    model.rewind(session_id=session_id, invocation_id=invocation_id, user_id=_user_id())
    return jsonify({"ok": True})


_voice_bucket = None


def _voice_cache():
    """GCS bucket for rendered speech, or None when not configured. Content-
    addressed (hash of the spoken text), so repeats are cache hits that skip
    synthesis entirely. Best-effort: any storage failure falls back to synth."""
    global _voice_bucket
    name = os.environ.get("VOICE_CACHE_BUCKET")
    if not name:
        return None
    if _voice_bucket is None:
        from google.cloud import storage

        _voice_bucket = storage.Client().bucket(name)
    return _voice_bucket


@app.post("/speak")
def speak():
    try:
        text = (request.get_json(silent=True) or {}).get("text", "")
        if not text:
            return jsonify({"error": "no text"}), 400
        spoken = re.sub(r"[*#_`]+", "", text)  # markdown reads terribly aloud
        wav, blob = None, None
        try:
            bucket = _voice_cache()
            if bucket is not None:
                key = "tts/" + hashlib.sha256(spoken.encode()).hexdigest()[:32] + ".wav"
                blob = bucket.blob(key)
                if blob.exists():
                    wav = blob.download_as_bytes()
        except Exception:  # noqa: BLE001
            wav, blob = None, None
        if wav is None:
            wav = speech_client.synthesize(spoken)
            if blob is not None:
                try:
                    blob.upload_from_string(wav, content_type="audio/wav")
                except Exception:  # noqa: BLE001
                    pass
        return jsonify({"audio_wav_base64": base64.b64encode(wav).decode()})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
