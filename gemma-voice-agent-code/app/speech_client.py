"""Speech I/O against the self-hosted GPU box: Whisper for transcription,
Kokoro for synthesis. The service is private, so calls carry an identity
token: fetched from the metadata server on Cloud Run, or via the gcloud CLI
when running locally as a user.
"""
import os
import subprocess
import threading
import time

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

BASE = os.environ.get("SPEECH_SERVICE_URL", "").rstrip("/")
if not BASE:
    raise RuntimeError("SPEECH_SERVICE_URL must point at the GPU box")
# The speech service scales to zero; while an instance boots, Cloud Run answers
# 429 (no capacity). Retry through a cold start instead of failing the turn.
RETRY_DELAYS = (5, 10, 20, 40, 60)


def enabled() -> bool:
    return bool(BASE)


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    last_error = None
    for delay in RETRY_DELAYS + (None,):
        try:
            resp = requests.post(
                url, headers={"Authorization": f"Bearer {_token()}"}, **kwargs
            )
            if resp.status_code not in (429, 500, 503):
                resp.raise_for_status()
                return resp
            last_error = requests.HTTPError(f"{resp.status_code} from {url}", response=resp)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
        if delay is None:
            break
        time.sleep(delay)
    raise last_error


def _token(audience: str | None = None) -> str:
    try:
        return id_token.fetch_id_token(Request(), audience or BASE)
    except Exception:  # noqa: BLE001 - local dev: user creds can't mint ID tokens
        return subprocess.check_output(
            "gcloud auth print-identity-token -q", shell=True
        ).decode().strip()


_wakers: dict[str, threading.Thread] = {}
_wakers_lock = threading.Lock()
_wake_started: dict[str, float] = {}


def waking_seconds() -> int:
    """Seconds since the oldest still-active wake began (0 = not waking).
    Anchors the frontend's elapsed display so a page refresh doesn't reset it."""
    with _wakers_lock:
        starts = [_wake_started[b] for b, t in _wakers.items()
                  if t.is_alive() and b in _wake_started]
    return int(time.time() - min(starts)) if starts else 0


def ensure_waking(base: str, path: str = "/health") -> None:
    """Hold a long request against a cold service so Cloud Run actually boots an
    instance. Short aborted probes (awake) don't reliably drive a start; this does.
    One waker per service at a time; no-op if one is already in flight."""

    def _hold():
        try:
            requests.get(
                f"{base}{path}",
                headers={"Authorization": f"Bearer {_token(base)}"},
                timeout=420,
            )
        except Exception:  # noqa: BLE001
            pass
        finally:
            with _wakers_lock:
                _wakers.pop(base, None)
                _wake_started.pop(base, None)

    with _wakers_lock:
        t = _wakers.get(base)
        if t is not None and t.is_alive():
            return
        t = threading.Thread(target=_hold, daemon=True)
        _wakers[base] = t
        _wake_started.setdefault(base, time.time())
        t.start()


def awake(base: str, path: str = "/health") -> bool:
    """Fast probe: is an instance of this scale-to-zero service already up?
    False means 'warn the user and expect a slow first turn', not 'broken'.
    This only reports; pair with ensure_waking() to actually drive the boot."""
    try:
        resp = requests.get(
            f"{base}{path}",
            headers={"Authorization": f"Bearer {_token(base)}"},
            timeout=3,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def transcribe(audio: bytes, mime: str = "audio/webm") -> str:
    resp = _post_with_retry(
        f"{BASE}/v1/audio/transcriptions",
        files={"file": ("audio", audio, mime)},
        timeout=120,
    )
    return (resp.json().get("text") or "").strip()


def synthesize(text: str) -> bytes:
    resp = _post_with_retry(
        f"{BASE}/v1/audio/speech",
        json={"input": text},
        timeout=120,
    )
    return resp.content
