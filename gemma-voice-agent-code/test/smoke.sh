#!/usr/bin/env bash
# End-to-end smoke test for the voice agent backend. Asserts the event protocol
# the frontend depends on, so any architecture change can be checked against it.
#
# Usage: test/smoke.sh [BASE_URL] [WAV_FILE]
#   BASE_URL defaults to http://127.0.0.1:8080
#   WAV_FILE: a short spoken question (16k mono wav). If omitted, audio tests
#   are skipped.
set -uo pipefail

BASE="${1:-http://127.0.0.1:8080}"
WAV="${2:-}"
SESSION="smoke-$$"
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# Warm up: the first agent call on a fresh server pays client-init latency that
# has nothing to do with the protocol under test.
curl -sS --max-time 300 -X POST "$BASE/chat" -H 'Content-Type: application/json' \
  -d '{"text": "warmup", "session_id": "warmup"}' -o /dev/null || true

# --- 1. text chat: NDJSON stream shape -------------------------------------
resp=$(curl -sS --max-time 120 -X POST "$BASE/chat" \
  -H 'Content-Type: application/json' \
  -d "{\"text\": \"Say only the word pong.\", \"session_id\": \"$SESSION\"}")
first_type=$(echo "$resp" | head -1 | python3 -c 'import json,sys; print(json.load(sys.stdin).get("type"))')
[ "$first_type" = "meta" ] && ok "text chat: first event is meta" || bad "text chat: first event is $first_type, wanted meta"
done_text=$(echo "$resp" | python3 -c '
import json,sys
final=""
for line in sys.stdin:
    e=json.loads(line)
    if e.get("type")=="done": final=e.get("text","")
print(final)')
[ -n "$done_text" ] && ok "text chat: done event has text (${done_text:0:40}...)" || bad "text chat: no done text"
echo "$resp" | grep -q '"type": *"error"' && bad "text chat: stream contained an error event" || ok "text chat: no error events"

# --- 2. text chat with a tool question: status event appears ---------------
resp=$(curl -sS --max-time 180 -X POST "$BASE/chat" \
  -H 'Content-Type: application/json' \
  -d "{\"text\": \"Find one recent paper about REM sleep.\", \"session_id\": \"$SESSION\"}")
echo "$resp" | grep -q '"type": *"status"' && ok "tool chat: status event seen" || bad "tool chat: no status event"
echo "$resp" | grep -q '"type": *"done"' && ok "tool chat: done event seen" || bad "tool chat: no done event"

# --- 3. audio path: one request, transcript event in the /chat stream -------
if [ -n "$WAV" ] && [ -f "$WAV" ]; then
  resp=$(curl -sS --max-time 180 -X POST "$BASE/chat" \
    -F "audio=@$WAV;type=audio/wav" -F "session_id=$SESSION-audio")
  t=$(echo "$resp" | python3 -c '
import json,sys
for line in sys.stdin:
    e=json.loads(line)
    if e.get("type")=="transcript": print(e.get("text","")); break')
  echo "$t" | grep -qi "sleep" && ok "audio chat: transcript event heard the question ($t)" || bad "audio chat: transcript was '$t'"
  echo "$resp" | grep -q '"type": *"done"' && ok "audio chat: done event seen" || bad "audio chat: no done event"
  echo "$resp" | grep -q '"type": *"error"' && bad "audio chat: error event in stream" || ok "audio chat: no error events"
else
  echo "SKIP: audio tests (no wav provided)"
fi

# --- 4. speak: returns a real WAV -------------------------------------------
spk=$(curl -sS --max-time 60 -X POST "$BASE/speak" \
  -H 'Content-Type: application/json' -d '{"text": "Hello there."}')
hdr=$(echo "$spk" | python3 -c '
import base64,json,sys
d=json.load(sys.stdin)
b=base64.b64decode(d.get("audio_wav_base64",""))
print(b[:4].decode("latin1") if len(b)>1000 else "TOO_SHORT")')
[ "$hdr" = "RIFF" ] && ok "speak: valid WAV returned" || bad "speak: bad audio ($hdr)"

echo
echo "== $PASS passed, $FAIL failed =="
exit $([ $FAIL -eq 0 ] && echo 0 || echo 1)
