FROM python:3.11-slim-bookworm

# Default image targets CPU. For NVIDIA GPU:
#   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
# Host must provide CUDA via NVIDIA Container Toolkit; ENABLE_CUDA=1 installs
# a CUDA-capable CTranslate2 wheel used by faster-whisper.
ARG INSTALL_SILERO=0
ARG INSTALL_GIGAAM=0
ARG ENABLE_CUDA=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8 \
    WHISPER_MODEL=base \
    STT_ENGINE=whisper \
    SILERO_LANGUAGE=en \
    SILERO_DEVICE=cpu \
    STORAGE_DIR=/app/storage \
    TORCH_HOME=/app/.cache/torch \
    GIGAAM_MODEL_DIR=/app/.cache/models/gigaam-ru \
    GIGAAM_VAD_MODEL=/app/.cache/models/silero_vad.onnx \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg libgomp1 fontconfig \
        fonts-dejavu fonts-paratype fonts-roboto fonts-noto-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-silero.txt requirements-gigaam.txt ./
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_SILERO" = "1" ]; then pip install -r requirements-silero.txt; fi \
    && if [ "$INSTALL_GIGAAM" = "1" ]; then pip install -r requirements-gigaam.txt; fi \
    && if [ "$ENABLE_CUDA" = "1" ]; then \
         pip install --upgrade --force-reinstall "ctranslate2>=4.5.0"; \
       fi

# Preload Whisper model so the first run does not wait for a download.
# Always warm the CPU int8 path (works in both CPU and GPU images).
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

# Optional: preload Silero models (requires INSTALL_SILERO=1 at build).
# TORCH_HOME outside the storage volume — otherwise the volume overwrites cache on first run.
RUN mkdir -p /app/.cache/torch \
    && if [ "$INSTALL_SILERO" = "1" ]; then python -c "\
import torch; \
torch.hub.load('snakers4/silero-models', 'silero_stt', language='en', device=torch.device('cpu'), trust_repo=True); \
torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True); \
torch.hub.load('snakers4/silero-models', 'silero_te', trust_repo=True); \
print('Silero models preloaded')"; fi

# Optional: download GigaAM models outside the storage volume.
COPY scripts ./scripts
RUN if [ "$INSTALL_GIGAAM" = "1" ]; then python scripts/download_gigaam.py --dest /app/.cache/models; fi

# Custom subtitle fonts bundled for burn-in + UI preview.
COPY assets/fonts /usr/share/fonts/neurocut
RUN fc-cache -f /usr/share/fonts/neurocut

COPY app ./app
COPY storage/.gitkeep ./storage/.gitkeep

RUN mkdir -p /app/storage

EXPOSE 8000

# Default process for `docker run` / compose (override command as needed).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
