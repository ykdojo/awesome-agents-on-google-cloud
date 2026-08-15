# app

The voice-agent front: chat UI, the ADK agent, and thin clients for the GPU
box ([`../gpu-speech/`](../gpu-speech/)), which serves all three models:
Whisper (ears), Gemma 4 31B (brain), and Kokoro (mouth). There are no hosted
fallbacks; `MODEL_API_BASE` (the brain, via LiteLLM) and `SPEECH_SERVICE_URL`
are required.

- `server.py` - Flask app: serves the chat page, `POST /chat` (text or audio
  in, NDJSON event stream out), `POST /transcribe` (display transcription),
  `POST /speak` (text in, WAV out)
- `model.py` - the ADK agent (Gemini for now, behind one narrow interface)
- `speech_client.py` - authenticated client for the speech GPU service
  (Whisper ears, Kokoro mouth)
- `tools.py` - paper search/lookup via the OpenAlex API (stand-in for your
  in-infra data source)
- `static/index.html` - mobile chat UI: text field plus a mic button

Required env: `SPEECH_SERVICE_URL` and `MODEL_API_BASE` (both the GPU box URL;
the app authenticates with its identity token), `MODEL_ID` (the served model
name, e.g. `google/gemma-4-31B-it`), and `GOOGLE_CLOUD_PROJECT`.

Deploy:

```sh
gcloud run deploy paper-voice-agent \
  --source . \
  --region us-central1 \
  --cpu 2 --memory 2Gi \
  --max-instances 1 --timeout 600 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project id>,MODEL_ID=google/gemma-4-31B-it,MODEL_API_BASE=<gpu box url>,SPEECH_SERVICE_URL=<gpu box url>
```

The service account running this app needs `roles/run.invoker` on the GPU box.

Tests: `test/smoke.sh <app url> <wav>` (warm protocol suite),
`test/cold.sh <app url> <wav>` (cold-start UX, costs a real GPU boot).
