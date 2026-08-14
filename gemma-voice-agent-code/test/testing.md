# Testing

How this app is tested, layer by layer. Every layer runs against a base URL,
so the same checks work locally and against a deployed service.

## Running the app locally

```sh
cd app
GOOGLE_CLOUD_PROJECT=<project> \
AGENT_ENGINE_ID=<engine id> \
MODEL_API_BASE=<gpu box url> \
SPEECH_SERVICE_URL=<gpu box url> \
PORT=8080 \
uv run --with-requirements requirements.txt python server.py
```

- `MODEL_API_BASE` and `SPEECH_SERVICE_URL` (both the GPU box URL) are
  required - all three models are served by the box, there is no hosted mode.
- Omit `AGENT_ENGINE_ID` for throwaway in-memory sessions.
- Auth locally comes from ADC (`gcloud auth application-default login`).
  One macOS quirk: set `SSL_CERT_FILE` to certifi's bundle (framework Python
  has no system certs, which breaks the OpenAlex tool).

## Layer 1: protocol smoke suite (run on every change)

```sh
test/smoke.sh <base url> <spoken wav>
```

Nine checks against the NDJSON chat protocol:

- text chat: first event is `meta`; a `done` event carries text; no `error`
  events ("Say only the word pong." should come back as pong, not the
  fallback apology - the fallback passing is a known blind spot, so eyeball it)
- tool chat: a `status` event appears (the UI's "Searching papers"), then `done`
- audio chat: one multipart POST; the `transcript` event must contain the
  spoken question (the wav asks about REM sleep, so it greps for "sleep");
  `done` arrives; no `error` events
- speak: returns valid base64 WAV (RIFF header, >1KB)

Generate the spoken wav on macOS:
`say -v Samantha -r 150 -o q.aiff "What papers do you have about R E M sleep?"
&& afconvert -f WAVE -d LEI16@16000 -c 1 q.aiff question.wav`

## Layer 2: conversation lifecycle (persistent sessions)

No script yet - curl sequence, in order:

```sh
SID="test-$(date +%s)"
curl -X POST $BASE/chat -H 'Content-Type: application/json' \
  -d "{\"text\":\"Say only the word banana.\",\"session_id\":\"$SID\"}"
curl $BASE/conversations                       # lists $SID, auto-titled from the message
curl $BASE/conversations/$SID/messages         # replays user + bot turns
curl -X PATCH $BASE/conversations/$SID -H 'Content-Type: application/json' \
  -d '{"title":"Renamed"}'                     # rename via state-delta event
curl $BASE/conversations                       # shows the new title
curl -X DELETE $BASE/conversations/$SID
```

Cross-instance persistence check: run a chat against the deployed service,
then `curl http://127.0.0.1:8080/conversations` on a local server pointed at
the same `AGENT_ENGINE_ID` - the conversation must appear there too.

## Layer 3: UI checks (browser, after frontend changes)

Manual or driven via browser automation:

- send a text message: user bubble immediately, dots, streamed reply, voice bar
- record a voice note: "Transcribing" placeholder replaced by the transcript
  from the stream (one upload; there is no /transcribe endpoint anymore)
- drawer: hamburger opens it; first open shows loading dots, reopening
  renders instantly from the in-memory cache and refreshes in the background;
  conversations listed newest-first; rename shows a save check (✓) while
  editing; delete needs two taps (✕ arms to a red ?); New starts fresh;
  Sign out at the bottom clears the IAP session
- conversation URLs: every conversation owns ?c=<id>; refreshing or reopening
  that URL lands back in it with history replayed
- turn narration: dots, then Loading conversation, Waiting for the model,
  Thinking, Searching papers (when a tool runs), then streaming text
- replayed history: every bot message carries a voice bar; first play shows a
  loading state, then fetches from the voice cache (or re-synthesizes) and
  plays in place without scrolling
- empty states: a fresh or empty conversation shows the example-question hint,
  which clears on the first message; an empty drawer says "No conversations
  yet."
- session pre-create: page load and New fire POST /conversations/<id>/prepare
  in the background, so a first message should not pay session creation
- reply quality: no chain-of-thought text in any reply (thought parts are
  filtered; a leak looks like "The user wants me to...")
- cold GPU: a cold page load shows the wake banner with the server-anchored
  elapsed timer; history stays browsable and the composer is disabled until
  /status reports ready

## Layer 4: cold-start UX (on demand - costs a GPU boot)

```sh
GPU_PROJECT=<project> test/cold.sh <app url> <wav>
```

Forces the GPU service(s) cold (env-bump revision), then asserts: /status
reports not-ready; an audio chat sent while cold emits the "Waking up the GPU"
status event and still completes; /status recovers to ready. Quirk: the
forcing update boots the new revision to verify it, which can leave a box
warm - the test uses an audio turn so the reliably-cold speech path is
exercised. Don't run in CI.

## Layer 5: error recovery

A failed turn must surface as an `error` event (with `invocation_id` and
`retryable: true`), never as the apology fallback. Two verified paths:

```sh
# 1. Force a model failure; the stream must end in a retryable error event:
MODEL_ID=bogus-model  # plus the usual env; vLLM rejects the unknown id
python -c "import model; print(list(model.reply_stream('hi', session_id='t1', user_id='t'))[-1])"

# 2. Cross-process resume: fail a turn (broken MODEL_ID) in one process, then
# in a NEW process with a working MODEL_ID:
python -c "import model; print(list(model.retry_stream(session_id='t1', invocation_id='<from step 1>', user_id='t'))[-1])"
# -> must be a done event answering the ORIGINAL question (resume re-runs the
# invocation from its last persisted event; no duplicate user message).
```

Over HTTP: `POST /retry {session_id, invocation_id}` streams the same NDJSON;
`POST /rewind {session_id, invocation_id}` drops a poisoned invocation from
effective history. In the UI, a failed turn shows the reason plus a Retry
button. Rules verified: the fallback apology only appears when the model
genuinely returns empty text after a healthy turn; empty-output turns are
treated as failures.

## Layer 6: behavior eval (on demand; costs model + judge calls)

```sh
cd eval && uv run --with-requirements ../app/requirements.txt \
  --with pytest,pytest-asyncio,rouge-score --with "google-adk[gcp,eval]>=2.4" \
  python -m pytest run_eval.py -s
```

Six cases in `eval/paper_search.evalset.json`: three that must call the search
tool, two that must not (greeting, capability question), one ambiguity case
that should ask for clarification. Scored by an LLM judge
(final_response_match_v2, threshold 0.7, judge stays Gemini) against
rubric-style references; exact tool-args matching and ROUGE are deliberately
not used (brittle across models). The candidate is the app's agent against
the GPU box; the judge model is test infrastructure only. Never gate on the `adk eval`
CLI exit code (always 0 in ADK 2.4).

## Layer 7: observability spot-check

After a deployed turn, open **Trace Explorer** (Cloud Console > Trace) for the
project and filter by OpenTelemetry service = the OTEL_SERVICE_NAME value.
Expect one trace per turn: `invocation > invoke_agent > call_llm >
generate_content` (plus `execute_tool` when the agent searched), with GenAI
token counts (in/out) shown on the trace header. Requires
roles/telemetry.writer on the service account and `--no-cpu-throttling`
(throttled CPU delays span export).

Do NOT verify via the legacy v1 REST list API - it only surfaces the plain
HTTP client spans, not the OTLP-ingested ADK spans, and will make you think
tracing is broken when it isn't. Trace Explorer is the source of truth.

Data retention: `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false` is set on the
deployed service, so spans carry structure, latencies, and token counts but
never prompt/response text. Conversation content lives only in the session
store. Flip the env var on (locally, against throwaway sessions) when a trace
needs full payloads for debugging.

The Flask request span and the ADK turn span are currently separate traces
(the runner's thread starts its own context) - known, acceptable for now.

Tool failures are visible two ways even when the agent degrades gracefully:
each failed OpenAlex attempt logs `openalex attempt N/4 failed: <error>` to
Cloud Logging, and the execute_tool span carries `openalex.degraded=true`
plus the recorded exception in Trace Explorer.

## Layer 8: session-backend benchmark (on demand)

```sh
cd app && GOOGLE_CLOUD_PROJECT=<project> AGENT_ENGINE_ID=<engine id> \
  uv run --with-requirements requirements.txt python ../test/bench_sessions.py
```

Times every session operation (n=5, medians) against the in-memory backend
and Agent Engine, plus a raw-REST probe of the same API with the SDK
bypassed. Reproduces the writeup's latency table. Key reference points from
2026-08-12: ~1.2-1.6s per op via the ADK client path, ~0.16s raw REST,
create can exceed 15s on the first call in a process. The gap is client-path
overhead (google-adk 2.6.3 constructs a new API client per operation).

## Known blind spots

- The mic itself (getUserMedia) can't be automated - test by hand on a phone
  against an HTTPS deployment.
- smoke.sh's text check accepts any done text, including the fallback apology.
- IAP only exists deployed (enabled on the dev service: sign-in flow, JWT
  verification, and per-user conversation isolation all verified 2026-08-11);
  local runs use the `dev` user.
