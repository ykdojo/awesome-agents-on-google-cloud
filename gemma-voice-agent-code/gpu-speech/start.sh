#!/usr/bin/env bash
# One GPU box: Whisper (ears) + Gemma 4 31B (brain) as two vLLM processes on
# side ports, Kokoro (mouth) inside the front app, which owns the exposed port.
set -e

# The two vLLM processes MUST start sequentially: gpu-memory-utilization is a
# cap on TOTAL device usage as each process sees it, so concurrent engine
# profiling is a race (whoever profiles while the other holds memory concludes
# there is no room for its cache blocks and dies). Ears first (small, seconds),
# then the brain with a cap that includes the ears' resident share.

# Ears: small, baked into the image.
vllm serve "${WHISPER_MODEL:-openai/whisper-large-v3-turbo}" \
  --port 8001 --host 127.0.0.1 \
  --gpu-memory-utilization "${WHISPER_GPU_MEM_UTIL:-0.12}" \
  &

if [[ -n "${BRAIN_MODEL_LOCATION:-}" ]]; then
  for i in $(seq 1 120); do
    curl -sf -o /dev/null http://127.0.0.1:8001/health && break
    sleep 5
  done

  # Brain: weights streamed from the public GCS bucket (~90s via the Run:ai
  # streamer). Model flags mirror the validated codelab deployment. The 0.75
  # cap = ears' 0.12 + ~0.60 for the brain, with headroom.
  vllm serve "${BRAIN_MODEL_LOCATION}" \
    --served-model-name "${BRAIN_MODEL_NAME:-google/gemma-4-31B-it}" \
    --port 8002 --host 127.0.0.1 \
    --enable-chunked-prefill --enable-prefix-caching \
    --generation-config auto \
    --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 \
    --dtype bfloat16 --quantization fp8 --kv-cache-dtype fp8 \
    --max-num-seqs "${BRAIN_MAX_NUM_SEQS:-8}" \
    --max-model-len "${BRAIN_MAX_MODEL_LEN:-16384}" \
    --gpu-memory-utilization "${BRAIN_GPU_MEM_UTIL:-0.75}" \
    --load-format runai_streamer \
    &
fi

# Cloud Run's startup probe waits on /healthz, which requires every enabled
# process to be ready.
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}"
