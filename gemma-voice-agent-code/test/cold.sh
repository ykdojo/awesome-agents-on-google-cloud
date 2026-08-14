#!/usr/bin/env bash
# Cold-start UX test: forces the GPU boxes to sleep, then verifies both wake
# layers: /status reports not-ready (page-load overlay signal), and a /chat sent
# while cold emits the waking-up status event and still completes.
#
# Costs a real GPU cold start per run (several minutes) - run on demand, not in CI.
# Quirk: forcing cold via a service update boots the new revision to verify it,
# which can leave that box warm again. The speech box reliably ends up cold, so
# layer 2 uses an AUDIO message (needs the speech box) to guarantee a cold path.
#
# Usage: GPU_PROJECT=<project> test/cold.sh <APP_URL> <WAV_FILE>
# Optional env: MODEL_SVC, SPEECH_SVC, REGION.
set -uo pipefail

APP="${1:?need the app URL}"
WAV="${2:?need a wav file for the audio turn}"
MODEL_SVC="${MODEL_SVC:-speech-gpu}"
SPEECH_SVC="${SPEECH_SVC:-speech-gpu}"
GPU_PROJECT="${GPU_PROJECT:?set GPU_PROJECT to the project hosting the GPU services}"
REGION="${REGION:-us-central1}"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

echo "== forcing GPU services cold (new revisions, no traffic) =="
for svc in $(printf "%s\n%s\n" "$MODEL_SVC" "$SPEECH_SVC" | sort -u); do
  gcloud run services update "$svc" --project "$GPU_PROJECT" --region "$REGION" \
    --update-env-vars "COLD_TEST_MARKER=$(date +%s)" --quiet >/dev/null 2>&1 &&
    echo "  $svc: new revision (instance drained)"
done
sleep 10

echo "== layer 1: /status while cold =="
s=$(curl -sS --max-time 30 "$APP/status")
echo "  $s"
echo "$s" | grep -q '"ready":false' && ok "status reports not-ready while cold" || bad "status did not report cold: $s"

echo "== layer 2: audio chat sent while cold =="
resp=$(curl -sS --max-time 590 -X POST "$APP/chat" \
  -F "audio=@$WAV;type=audio/wav" -F "session_id=cold-test")
echo "$resp" | grep -q '"Waking up the GPU' && ok "waking-up status event emitted" || bad "no waking-up status event"
echo "$resp" | grep -q '"type": *"transcript"' && ok "transcript arrived after wake" || bad "no transcript event"
echo "$resp" | grep -q '"type": *"done"' && ok "turn completed despite cold start" || bad "turn did not complete"
echo "$resp" | grep -q '"type": *"error"' && bad "error event in cold-start stream" || ok "no error events"

echo "== layer 1 again: /status should now be ready =="
for i in $(seq 1 60); do
  s=$(curl -sS --max-time 30 "$APP/status")
  echo "$s" | grep -q '"ready":true' && break
  sleep 5
done
echo "$s" | grep -q '"ready":true' && ok "status became ready (overlay would dismiss)" || bad "status never became ready: $s"

echo
echo "== $PASS passed, $FAIL failed =="
exit $([ $FAIL -eq 0 ] && echo 0 || echo 1)
