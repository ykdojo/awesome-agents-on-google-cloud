# Gemma Voice Agent

A voice customer-service agent that is fully self-hosted: ask a question by voice, the agent
searches a knowledge base, and answers back in voice, with no external AI APIs. Built entirely on
open-weights models. **Your data, your infra, your control.**

> **Fully self-hosted.** Speech-to-text (**Whisper** via vLLM), the brain (**Gemma 4 31B**
> via vLLM, orchestrated with ADK through LiteLLM), and text-to-speech (**Kokoro**) all run in one
> Cloud Run GPU service ([`gpu-speech/`](gpu-speech/)). Three open-weights models, no
> external AI APIs.

The knowledge base in this demo is scientific papers, standing in for whatever *your* private data
source is: an internal database, docs, or search engine.

## Architecture

Everything model-shaped runs on **one Cloud Run GPU service** (RTX 6000 Pro, scale-to-zero),
with a thin CPU service in front for the chat UI and agent loop:

| Stage | Component |
|---|---|
| Speech-to-text | **Whisper large-v3-turbo** (vLLM) |
| Agent loop / tool use | **Gemma 4 31B** (vLLM), orchestrated with **ADK** via LiteLLM |
| Knowledge lookup | OpenAlex paper search (stand-in for your in-infra data source) |
| Text-to-speech | **Kokoro** (82M) on the same GPU |
| Frontend | Basic chat interface: type or talk, replies come back as text and voice |

The GPU box sleeps when idle; the app detects that, wakes it on page load, and shows an
honest status (a wake banner with elapsed time, an in-stream event mid-conversation) while
it boots.

![Architecture](docs/architecture.svg)

## How it fits together

Two Cloud Run services with one seam between them:

- **The app** ([`app/`](app/)) is a small CPU service: the chat page and the ADK agent
  loop, and it talks to the private GPU box securely. Voice notes are transcribed once;
  the model only ever sees text. Conversations persist per user, failed turns can be
  resumed, and every turn emits traces.
- **The GPU box** ([`gpu-speech/`](gpu-speech/)) is where all three models live on one
  RTX 6000 Pro: two vLLM processes (Whisper, Gemma 4 31B) plus Kokoro inside the
  FastAPI router that owns the exposed port. It scales to zero; the big weights stream
  from a public GCS bucket at boot.

## Why ADK?

The [Agent Development Kit](https://adk.dev/) carries this app's production needs, and
every one of them is exercised in this repo. Persistence: conversation history and state
live in storage we manage, with swappable backends. Self-hosting: the agent's model is
ADK's LiteLLM wrapper pointed at our own vLLM endpoint. And the road from prototype to
production: error recovery with invocation resume, native OpenTelemetry tracing, and an
LLM-judged eval harness are all ADK features this app uses.

## Demo & screenshot

https://github.com/user-attachments/assets/ccdd3cf1-fd42-4b0a-8827-dd51140f795f

<img src="docs/ui-chat.png" width="380" alt="Chat UI: a multi-turn conversation about the practical benefits of meditation, each reply with a voice playback bar and waveform">

Writeup in progress: *From prototype to production: a self-hosted voice agent on
a single Cloud Run GPU*.
