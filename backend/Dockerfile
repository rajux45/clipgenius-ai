FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for video processing & opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN chmod +x /app/start_all.sh

EXPOSE 8000

# When BUNDLED_WORKERS=1 (default in start_all.sh) the container runs API +
# worker + beat together; on multi-service plans you can override CMD with
# `gunicorn ...` for the API service and `celery ...` for worker/beat.
CMD ["/app/start_all.sh"]
