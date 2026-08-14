"""Benchmark ADK session backends: in-memory vs Vertex AI Agent Engine Sessions.

Reproduces the session-latency numbers in the writeup. Every operation is
timed N times; medians and ranges are printed. The raw-REST probe at the end
separates client-library overhead from API latency for the same read.

Run (from the repo root; needs gcloud ADC with access to the project):

    cd app && GOOGLE_CLOUD_PROJECT=<project> AGENT_ENGINE_ID=<engine id> \
      uv run --with-requirements requirements.txt python ../test/bench_sessions.py

Notes for interpreting results:
- Measurements include the network round-trip from wherever you run this to
  the us-central1 API endpoint. Run it on a VM in us-central1 to see the
  region-local floor.
- Session creation on Agent Engine is exposed as a long-running operation
  (the client polls until the operation completes), so its latency includes
  polling quantization on top of server-side work.
"""
import asyncio
import os
import statistics
import time
import uuid

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

APP = "bench"
N = int(os.environ.get("BENCH_ITERATIONS", "5"))


async def bench(svc, label):
    uid = f"bench-{uuid.uuid4().hex[:8]}"
    results: dict[str, list[float]] = {}

    def rec(name, t):
        results.setdefault(name, []).append(t)

    sids = []
    for i in range(N):
        sid = f"s{i}-{uuid.uuid4().hex[:8]}"
        t0 = time.time()
        await svc.get_session(app_name=APP, user_id=uid, session_id=sid)
        rec("get (miss)", time.time() - t0)

        t0 = time.time()
        await svc.create_session(
            app_name=APP, user_id=uid, session_id=sid, state={"title": "bench"}
        )
        rec("create", time.time() - t0)

        t0 = time.time()
        s = await svc.get_session(app_name=APP, user_id=uid, session_id=sid)
        rec("get (hit)", time.time() - t0)

        t0 = time.time()
        await svc.append_event(
            s,
            Event(
                invocation_id=f"bench-{i}-{uuid.uuid4().hex[:6]}",
                author="user",
                actions=EventActions(state_delta={"k": str(i)}),
            ),
        )
        rec("append event", time.time() - t0)
        sids.append(sid)

    t0 = time.time()
    await svc.list_sessions(app_name=APP, user_id=uid)
    rec("list", time.time() - t0)

    for sid in sids:
        t0 = time.time()
        await svc.delete_session(app_name=APP, user_id=uid, session_id=sid)
        rec("delete", time.time() - t0)

    print(f"\n{label}  (n={N}, seconds, median [min - max])")
    for k, v in results.items():
        print(f"  {k:13s} {statistics.median(v):8.3f}   [{min(v):.3f} - {max(v):.3f}]")


def raw_rest_probe(project, engine_id):
    """Time the same session read as a bare REST call, bypassing the SDK."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    sess = AuthorizedSession(creds)
    url = (
        f"https://us-central1-aiplatform.googleapis.com/v1beta1/projects/{project}"
        f"/locations/us-central1/reasoningEngines/{engine_id}/sessions"
    )
    times = []
    for _ in range(N):
        t0 = time.time()
        resp = sess.get(url, params={"pageSize": 1}, timeout=60)
        resp.raise_for_status()
        times.append(time.time() - t0)
    print(f"\nraw REST list (SDK bypassed)  (n={N}, seconds, median [min - max])")
    print(f"  {'list':13s} {statistics.median(times):8.3f}   [{min(times):.3f} - {max(times):.3f}]")


async def main():
    await bench(InMemorySessionService(), "InMemorySessionService")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    engine = os.environ.get("AGENT_ENGINE_ID")
    if project and engine:
        await bench(
            VertexAiSessionService(
                project=project, location="us-central1", agent_engine_id=engine
            ),
            "VertexAiSessionService (Agent Engine)",
        )
        raw_rest_probe(project, engine)
    else:
        print("\n(set GOOGLE_CLOUD_PROJECT and AGENT_ENGINE_ID for the Vertex half)")


if __name__ == "__main__":
    asyncio.run(main())
