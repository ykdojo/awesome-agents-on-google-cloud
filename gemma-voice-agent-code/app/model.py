"""The agent brain: Gemma 4 31B, self-hosted on our Cloud Run GPU box, reached
through ADK's LiteLlm wrapper against vLLM's OpenAI-compatible API. No hosted
AI APIs anywhere in the path. Input is always text; voice notes are transcribed
(on the same box) before they get here.

ADK sessions carry the conversation history: each browser session maps to an ADK session, the
Runner assembles prior turns (including past tool calls and results) into context, and new
events are appended automatically. Long-term memory is deliberately not used.
"""
import asyncio
import os
import subprocess
import threading
import time
import uuid

from google.adk.agents import Agent
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService
from google.genai import types

import tools

MODEL_API_BASE = os.environ.get("MODEL_API_BASE", "").rstrip("/")
if not MODEL_API_BASE:
    raise RuntimeError("MODEL_API_BASE must point at the GPU box (vLLM OpenAI API)")
MODEL_ID = os.environ.get("MODEL_ID", "google/gemma-4-31B-it")
APP_NAME = "paper-voice-agent"


def _fetch_identity_token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    try:
        return id_token.fetch_id_token(Request(), MODEL_API_BASE)
    except Exception:  # noqa: BLE001 - local dev: user creds can't mint ID tokens
        return subprocess.check_output(
            "gcloud auth print-identity-token -q", shell=True
        ).decode().strip()


_token_fetched_at = 0.0
_token_lock = threading.Lock()


def _refresh_brain_token() -> None:
    """Identity tokens live ~1 hour. Under scale-to-zero, instances never
    outlived one; a pinned (min-instances) instance does, so refresh the token
    the model uses whenever it is older than 45 minutes."""
    global _token_fetched_at
    with _token_lock:
        if time.time() - _token_fetched_at < 2700:
            return
        _agent.model._additional_args["api_key"] = _fetch_identity_token()
        _token_fetched_at = time.time()


def _self_hosted_model():
    from google.adk.models.lite_llm import LiteLlm

    api_base = MODEL_API_BASE if MODEL_API_BASE.endswith("/v1") else MODEL_API_BASE + "/v1"
    # The model service is private; calls carry an identity token, refreshed by
    # _refresh_brain_token() before each turn.
    return LiteLlm(
        model=f"openai/{MODEL_ID}",
        base_url=api_base,
        api_key=_fetch_identity_token(),
        # Gemma 4 on vLLM wants these for thinking + clean output.
        extra_body={
            "chat_template_kwargs": {"enable_thinking": True},
            "skip_special_tokens": False,
        },
    )

SYSTEM_PROMPT = (
    "You are a friendly customer-service agent for a scientific-paper knowledge base. "
    "Users ask questions by voice or text. Use the search_papers and get_paper tools to ground "
    "your answers in actual papers, and cite them as (Author, Year). Keep your replies concise. "
    "If the user's audio is unclear, ask them to repeat."
)

_agent = Agent(
    name="paper_agent",
    model=_self_hosted_model(),
    instruction=SYSTEM_PROMPT,
    tools=[tools.search_papers, tools.get_paper],
)
# Persistent sessions (Vertex Agent Engine Sessions) when AGENT_ENGINE_ID is
# set; in-memory otherwise (local dev). The engine is an empty resource used
# purely as a session container - nothing is deployed to it.
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "")
if AGENT_ENGINE_ID:
    _sessions = VertexAiSessionService(
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("SESSION_LOCATION", "us-central1"),
        agent_engine_id=AGENT_ENGINE_ID,
    )
else:
    _sessions = InMemorySessionService()

# Resumable invocations (experimental ADK feature): a turn that dies midway can
# be resumed from its last persisted event instead of being retyped. Our tools
# are read-only HTTP GETs, so at-least-once re-execution is safe.
_app = App(
    name=APP_NAME,
    root_agent=_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
_runner = Runner(app=_app, session_service=_sessions)


# One long-lived event loop on a daemon thread for the session-service coroutines,
# instead of building and tearing down a fresh loop on every request.
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


# Session ops on Agent Engine are expensive (~2.7s per call; creation is a
# long-running operation that can take 15s+), so: sessions the process has
# already ensured are never re-checked, and the frontend pre-creates upcoming
# sessions in the background while the user is still typing.
_ensured: set[tuple[str, str]] = set()
_needs_title: set[tuple[str, str]] = set()


def _ensure_session(user_id: str, session_id: str, first_message: str = "") -> None:
    """Get-or-create; a new conversation is titled from its first message.
    Pre-created sessions get their title from the first real message, applied
    in the background so the turn never waits on it."""
    key = (user_id, session_id)
    if key in _ensured:
        if key in _needs_title and first_message:
            _needs_title.discard(key)
            title = first_message.strip()[:48]
            threading.Thread(
                target=lambda: rename_conversation(user_id, session_id, title),
                daemon=True,
            ).start()
        return

    async def go():
        existing = await _sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            title = (first_message or "New conversation").strip()[:48]
            await _sessions.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id,
                state={"title": title},
            )
            if not first_message:
                _needs_title.add(key)

    _run(go())
    _ensured.add(key)


def warm_session_client() -> None:
    """One throwaway session read at process start, so the first real turn
    doesn't pay the client construction + auth cost inside the request."""
    try:
        _run(_sessions.list_sessions(app_name=APP_NAME, user_id="warmup"))
    except Exception:  # noqa: BLE001
        pass


def precreate_session(user_id: str, session_id: str) -> None:
    """Fire-and-forget creation of an upcoming conversation (from a background
    thread) so the user's first message doesn't pay the creation LRO."""
    try:
        _ensure_session(user_id, session_id)
    except Exception:  # noqa: BLE001 - best effort; the turn path retries anyway
        pass


# --- conversation management (backs the UI drawer) ---------------------------

def list_conversations(user_id: str) -> list[dict]:
    resp = _run(_sessions.list_sessions(app_name=APP_NAME, user_id=user_id))
    convos = sorted(resp.sessions, key=lambda s: s.last_update_time or 0, reverse=True)
    return [
        {
            "id": s.id,
            "title": (s.state or {}).get("title") or "Untitled",
            "updated": s.last_update_time,
        }
        for s in convos
    ]


def delete_conversation(user_id: str, session_id: str) -> None:
    _ensured.discard((user_id, session_id))
    _needs_title.discard((user_id, session_id))
    _run(_sessions.delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id))


def rename_conversation(user_id: str, session_id: str, title: str) -> None:
    """No update-state API exists; the persistence path for state is a state_delta event."""
    async def go():
        session = await _sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if session is None:
            raise KeyError(session_id)
        await _sessions.append_event(
            session,
            Event(
                invocation_id=f"rename-{uuid.uuid4().hex}",
                author="user",
                actions=EventActions(state_delta={"title": title.strip()[:48]}),
            ),
        )

    _run(go())


def get_history(user_id: str, session_id: str) -> list[dict]:
    """Visible turns only: user text and final model text; no thoughts, no tool traffic."""
    session = _run(
        _sessions.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    )
    if session is None:
        return []
    messages = []
    for event in session.events or []:
        if not (event.content and event.content.parts):
            continue
        text = "".join(
            p.text or "" for p in event.content.parts
            if p.text and not getattr(p, "thought", False)
        ).strip()
        if not text:
            continue
        role = "user" if event.author == "user" else "bot"
        messages.append({"role": role, "text": text})
    return messages


def reply_stream(text: str, session_id: str = "default", user_id: str = "dev"):
    """Streaming turn: text in (voice notes arrive here already transcribed), yields dicts.
    type=status (tool running), delta (text chunk), done (authoritative full text).
    Falls back to one done event if streaming is unavailable."""
    if not text or not text.strip():
        raise ValueError("need text")
    parts = [types.Part.from_text(text=text)]

    _refresh_brain_token()
    # Narrate the pre-model phases so the user never sits on bare dots:
    # session round-trip, then the model's prompt prefill, then Thinking.
    yield {"type": "status", "status": "Loading conversation"}
    _ensure_session(user_id, session_id, first_message=text)

    try:
        from google.adk.agents.run_config import RunConfig, StreamingMode

        run_config = RunConfig(streaming_mode=StreamingMode.SSE)
    except Exception:  # noqa: BLE001
        run_config = None

    yield {"type": "status", "status": "Waiting for the model"}
    state = _new_stream_state()
    events = _runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=parts),
        **({"run_config": run_config} if run_config else {}),
    )
    try:
        yield from _event_dicts(events, state)
    except Exception as e:  # noqa: BLE001 - surface honestly; the turn is resumable
        yield _error_dict(e, state)
        return
    yield _done_dict(state)


def retry_stream(session_id: str, invocation_id: str, user_id: str = "dev"):
    """Resume a failed invocation from its last persisted event (no new user
    message; ADK re-executes the dangling step and continues). Same event
    protocol as reply_stream."""
    _refresh_brain_token()
    agen = _runner.run_async(
        user_id=user_id, session_id=session_id, invocation_id=invocation_id
    )

    def sync_events():
        while True:
            try:
                yield asyncio.run_coroutine_threadsafe(agen.__anext__(), _loop).result()
            except StopAsyncIteration:
                return

    state = _new_stream_state()
    state["invocation_id"] = invocation_id
    try:
        yield from _event_dicts(sync_events(), state)
    except Exception as e:  # noqa: BLE001
        yield _error_dict(e, state)
        return
    yield _done_dict(state)


def rewind(session_id: str, invocation_id: str, user_id: str = "dev") -> None:
    """Give-up path: drop a failed invocation from effective history so it
    can't poison future turns."""
    _run(
        _runner.rewind_async(
            user_id=user_id,
            session_id=session_id,
            rewind_before_invocation_id=invocation_id,
        )
    )


def _new_stream_state() -> dict:
    return {"final": None, "streamed": "", "invocation_id": None, "error": None}


def _event_dicts(events, state):
    for event in events:
        if getattr(event, "invocation_id", None):
            state["invocation_id"] = event.invocation_id
        if getattr(event, "error_code", None) or getattr(event, "error_message", None):
            state["error"] = f"{event.error_code or 'error'}: {event.error_message or ''}".strip()
        try:
            calls = event.get_function_calls()
        except Exception:  # noqa: BLE001
            calls = None
        if calls:
            state["streamed"] = ""
            # Name the tool and its query, and count calls across the turn,
            # so multi-step research reads as progress instead of one
            # unchanging "Searching papers".
            for call in calls:
                state["tool_count"] = state.get("tool_count", 0) + 1
                name = getattr(call, "name", "") or ""
                args = getattr(call, "args", None) or {}
                if name == "search_papers":
                    q = str(args.get("query", "")).strip()
                    label = f'Searching papers: "{q[:48]}"' if q else "Searching papers"
                elif name == "get_paper":
                    label = "Reading a paper"
                else:
                    label = f"Running {name}" if name else "Running a tool"
                if state["tool_count"] > 1:
                    label += f" (step {state['tool_count']})"
                yield {"type": "status", "status": label}
        if event.content and event.content.parts:
            # The model reasons before it answers; those tokens are hidden below,
            # so surface the phase once instead of leaving the user on bare dots.
            if not state.get("thinking_shown") and any(
                getattr(p, "thought", False) for p in event.content.parts
            ):
                state["thinking_shown"] = True
                yield {"type": "status", "status": "Thinking"}
            # Skip thought parts: reasoning models (Gemma via vLLM) stream their
            # chain-of-thought as parts flagged thought=True, which is not for users.
            chunk = "".join(
                p.text or ""
                for p in event.content.parts
                if p.text and not getattr(p, "thought", False)
            )
            if not chunk:
                continue
            if getattr(event, "partial", False):
                state["streamed"] += chunk
                yield {"type": "delta", "text": chunk}
            elif event.is_final_response():
                state["final"] = chunk


def _error_dict(e: Exception, state: dict) -> dict:
    return {
        "type": "error",
        "error": f"{type(e).__name__}: {e}",
        "invocation_id": state.get("invocation_id"),
        "retryable": bool(state.get("invocation_id")),
    }


def _done_dict(state: dict) -> dict:
    """Honest terminal event: a turn that produced no text failed, even when the
    runner swallowed the exception (resumable mode logs it and ends the stream)."""
    text = state["final"] or state["streamed"]
    if not text:
        return {
            "type": "error",
            "error": state.get("error") or "The model turn failed before producing an answer.",
            "invocation_id": state.get("invocation_id"),
            "retryable": bool(state.get("invocation_id")),
        }
    return {
        "type": "done",
        "text": text,
        "invocation_id": state.get("invocation_id"),
    }
