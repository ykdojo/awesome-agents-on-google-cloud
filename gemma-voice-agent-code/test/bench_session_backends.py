"""Compare ADK session backends on the two paths a chat app actually takes.

Backends (all through the same ADK session-service interface):
  - InMemorySessionService                  (process memory)
  - DatabaseSessionService on local SQLite  (SQL, no network)
  - DatabaseSessionService on Cloud SQL     (SQL service; set SQL_DB_URL)
  - VertexAiSessionService                  (Agent Engine Sessions)

Scenarios:
  - new conversation:        create_session
  - continuing conversation: get_session + append_event (one turn's session work)

The first create in a process is reported separately from later ones: that
first call is the slow one on Agent Engine.

Run (from the repo root; needs gcloud ADC with access to the project):

    cd app && GOOGLE_CLOUD_PROJECT=<project> AGENT_ENGINE_ID=<engine id> \
      uv run --with-requirements requirements.txt --with sqlalchemy --with aiosqlite \
      python ../test/bench_session_backends.py

Without the two env vars, the Agent Engine leg is skipped.
"""
import asyncio
import json
import os
import statistics
import tempfile
import time
import uuid

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.sessions import (
    DatabaseSessionService,
    InMemorySessionService,
    VertexAiSessionService,
)

APP = "bench"
N = int(os.environ.get("BENCH_ITERATIONS", "5"))


async def bench(svc, label):
    uid = f"bench-{uuid.uuid4().hex[:8]}"
    creates, continues, sids = [], [], []

    for i in range(N):
        sid = f"s{i}-{uuid.uuid4().hex[:8]}"
        t0 = time.time()
        await svc.create_session(
            app_name=APP, user_id=uid, session_id=sid, state={"title": "bench"}
        )
        creates.append(time.time() - t0)
        sids.append(sid)

    for sid in sids:
        t0 = time.time()
        s = await svc.get_session(app_name=APP, user_id=uid, session_id=sid)
        await svc.append_event(
            s,
            Event(
                invocation_id=f"bench-{uuid.uuid4().hex[:6]}",
                author="user",
                actions=EventActions(state_delta={"k": "v"}),
            ),
        )
        continues.append(time.time() - t0)

    for sid in sids:
        await svc.delete_session(app_name=APP, user_id=uid, session_id=sid)

    result = {
        "backend": label,
        "new_first_s": round(creates[0], 3),
        "new_later_s": round(statistics.median(creates[1:]), 3),
        "continue_s": round(statistics.median(continues), 3),
    }
    print(
        f"{label:22s} new (first): {result['new_first_s']:7.3f}   "
        f"new (later): {result['new_later_s']:7.3f}   "
        f"continue: {result['continue_s']:7.3f}"
    )
    return result


async def main():
    print(f"seconds; 'later' and 'continue' are medians of {N}\n")
    results = [await bench(InMemorySessionService(), "in-memory")]

    with tempfile.TemporaryDirectory() as d:
        results.append(
            await bench(
                DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{d}/bench.db"),
                "SQL (SQLite via ADK)",
            )
        )

    sql_url = os.environ.get("SQL_DB_URL")
    if sql_url:
        results.append(
            await bench(DatabaseSessionService(db_url=sql_url), "SQL (Cloud SQL via ADK)")
        )

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    engine = os.environ.get("AGENT_ENGINE_ID")
    if project and engine:
        results.append(
            await bench(
                VertexAiSessionService(
                    project=project, location="us-central1", agent_engine_id=engine
                ),
                "Agent Engine (ADK)",
            )
        )
    else:
        print("\n(set GOOGLE_CLOUD_PROJECT and AGENT_ENGINE_ID for the Agent Engine leg)")

    print("\n" + json.dumps(results))


if __name__ == "__main__":
    asyncio.run(main())
