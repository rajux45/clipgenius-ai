FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for video processing & opencv. redis-server is bundled so the
# container can run end-to-end on hosts that don't provide a managed Redis
# (e.g. HuggingFace Spaces) — the in-container instance is only used as the
# Celery broker when REDIS_URL is unset.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        ca-certificates \
        curl \
        redis-server \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Pre-download the faster-whisper model so the worker never has to fetch it
# at runtime (which would compete for RAM with the rest of the worker on
# tiny dynos). The 'tiny' model is ~75 MB and lives in the HF cache.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cpu', compute_type='int8')"

COPY . .
RUN chmod +x /app/start_all.sh

EXPOSE 8000

# When BUNDLED_WORKERS=1 (default in start_all.sh) the container runs API +
# worker + beat together; on multi-service plans you can override CMD with
# `gunicorn ...` for the API service and `celery ...` for worker/beat.
CMD ["/app/start_all.sh"]
