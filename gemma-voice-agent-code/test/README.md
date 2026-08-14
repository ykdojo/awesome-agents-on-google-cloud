# Session backend benchmarks

How much time ADK session storage adds, compared across three backends through
the same `SessionService` interface.

![Chart: Agent Engine takes seconds per operation; SQLite and in-memory are near zero](session-backends.png)

## What was tested

`bench_session_backends.py` times the two paths a chat app takes, five rounds each:

- **New conversation**: `create_session` (the first create in a fresh process is
  reported separately - that's the slow one)
- **Continuing turn**: `get_session` + `append_event` (one turn's session work)

Backends: `InMemorySessionService`, `DatabaseSessionService` on local SQLite,
`DatabaseSessionService` on Cloud SQL (Postgres 16, smallest tier, us-central1,
reached through the Cloud SQL Auth Proxy), and `VertexAiSessionService`
(Agent Engine Sessions). No model is involved anywhere.

## Results (2026-08-14, from a Cloud Run job container in us-central1)

The fair setup: all four backends timed from the same container in the backends'
own region, schema and engine pre-created by an untimed warmup, then measured
through a brand-new client. Medians of 5 operations; three job executions.

| Backend | New (first in process) | New (later) | Continuing turn |
|---|---|---|---|
| in-memory | ~0 s | ~0 s | ~0 s |
| SQL (SQLite via ADK) | 0.016 s | 0.004 s | 0.008 s |
| SQL (Cloud SQL via ADK) | 0.27 s (first connection) | 0.026 s | 0.056 s |
| Agent Engine (ADK) | 0.25 s | 0.27 s | 0.31 s |

Notes:

- google-adk 2.6.3 (the version the app ran) and 2.7.0 measured the same.
- The first-ever execution saw 1.4 s Agent Engine creates once; later executions
  settled at ~0.25 s.
- Distance amplifies everything: the same operations from a Mac far outside the
  region took seconds (Agent Engine ~2-3.5 s per op, Cloud SQL 0.8-1.6 s through
  the Auth Proxy), and 15 s+ first creates were observed on 2026-08-12. Those
  extremes did not reproduce in the fair in-region setup.
- Cloud SQL = smallest Postgres 16 tier, reached over Cloud Run's built-in
  connection (no proxy process). ADK's one-time schema creation on a fresh
  database (~7 s remote) is excluded by the warmup, as production would never
  pay it per process.

`bench_sessions.py` is the earlier, finer-grained script: it times each operation
individually and ends with a raw-REST probe of the same read (~0.16 s), which is
what showed the overhead lives in the client path rather than the API.

## Run it

```sh
cd app && GOOGLE_CLOUD_PROJECT=<project> AGENT_ENGINE_ID=<engine id> \
  SQL_DB_URL=postgresql+asyncpg://postgres:<password>@127.0.0.1:5433/postgres \
  uv run --with-requirements requirements.txt \
  --with sqlalchemy --with aiosqlite --with asyncpg \
  python ../test/bench_session_backends.py
```

The engine can be an empty Agent Engine resource - nothing deploys to it. The
Cloud SQL URL points at a local Cloud SQL Auth Proxy (or, in a Cloud Run job,
the built-in `/cloudsql/...` socket). Both cloud env vars are optional: without
them the local backends still run. For the fair in-region numbers, run the same
script as a Cloud Run job in the backends' region.

## Other files here

- `smoke.sh` - acceptance suite for the deployed app; `testing.md` explains all
  the test layers.
- `cold.sh` - cold-boot timing for the GPU box.
