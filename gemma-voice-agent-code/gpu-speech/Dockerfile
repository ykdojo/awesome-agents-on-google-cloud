FROM vllm/vllm-openai:latest

RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi uvicorn httpx kokoro soundfile librosa

# Pin: transformers 5.15.0 breaks Gemma 4 config parsing under vLLM
# (AmbiguousGlobalPerLayerAttributeError: 'head_dim' is per-layer;
# https://github.com/vllm-project/vllm/issues/51744)
RUN pip install --no-cache-dir 'transformers==5.14.1'

# Bake the (small, ungated) model weights into the image so cold starts skip
# the Hugging Face download: Whisper turbo ~1.6GB, Kokoro ~330MB.
ENV HF_HOME=/models
RUN python3 -c "from huggingface_hub import snapshot_download; \
    snapshot_download('openai/whisper-large-v3-turbo'); \
    snapshot_download('hexgrad/Kokoro-82M')"

# Run one real synthesis at build time: it pulls everything Kokoro fetches
# lazily (the spaCy English model from GitHub, misaki lexicons, the voice
# tensor) into the image and validates the pipeline. The box has no public
# internet at runtime, so anything not baked here is a hang.
RUN python3 -c "from kokoro import KPipeline; \
    assert sum(len(a.audio) for a in KPipeline(lang_code='a')('Warm up.', voice='af_heart') if a.audio is not None) > 0"

ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY server.py start.sh ./
RUN chmod +x start.sh

ENTRYPOINT ["/app/start.sh"]
