#!/usr/bin/env bash
# Runs method 3 in a Linux container. Needed on Intel macOS, where
# google-antigravity ships no x86_64 wheel (Apple Silicon and Linux only).
# On Apple Silicon or Linux, `pip install google-antigravity` and run the
# script directly instead.
set -euo pipefail
cd "$(dirname "$0")"

# Cloud-account mode: set GOOGLE_GENAI_USE_ENTERPRISE=TRUE and point
# GOOGLE_APPLICATION_CREDENTIALS at an ADC json; it gets mounted read-only.
ADC_ARGS=()
if [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
  ADC_ARGS=(-v "$GOOGLE_APPLICATION_CREDENTIALS":/adc.json:ro -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json)
fi

docker run --rm -v "$PWD":/work -w /work \
  "${ADC_ARGS[@]}" \
  -e HN_AGENT_MODEL \
  -e GOOGLE_GENAI_USE_ENTERPRISE \
  -e GOOGLE_CLOUD_LOCATION \
  -e BIGQUERY_OAUTH_TOKEN="$(gcloud auth print-access-token)" \
  -e GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project 2>/dev/null)" \
  python:3.12-slim \
  bash -c 'pip install -q -r requirements-method3.txt && python method3_antigravity.py "$@"' -- "$@"
