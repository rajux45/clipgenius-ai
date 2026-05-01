#!/usr/bin/env bash
# Combined launcher used when we need a single container to run the API,
# the Celery worker, and Celery beat (e.g. on free tiers without separate
# worker services). Set BUNDLED_WORKERS=0 to skip the worker (e.g. when
# the worker runs as its own Render service).

set -euo pipefail

WORKER_PID=""
GUNICORN_PID=""

shutdown() {
  # Forward SIGTERM to all children we started so they can flush and exit
  # cleanly. `wait` after this lets each child finish its grace period.
  if [[ -n "${WORKER_PID}" ]]; then
    kill -TERM "${WORKER_PID}" 2>/dev/null || true
  fi
  if [[ -n "${GUNICORN_PID}" ]]; then
    kill -TERM "${GUNICORN_PID}" 2>/dev/null || true
  fi
}
trap shutdown TERM INT

if [[ "${BUNDLED_WORKERS:-1}" == "1" ]]; then
  echo "[start_all] launching celery worker (with embedded beat) in background"
  celery -A app.worker worker --beat --loglevel=info \
    --concurrency="${WORKER_CONCURRENCY:-1}" \
    --schedule=/tmp/celerybeat-schedule &
  WORKER_PID=$!
fi

echo "[start_all] launching gunicorn (uvicorn worker) on port ${PORT:-8000}"
gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY:-2}" \
  -b "0.0.0.0:${PORT:-8000}" \
  --timeout 300 \
  --access-logfile - \
  --error-logfile - &
GUNICORN_PID=$!

# Wait for either child to exit. If gunicorn dies the container should die
# too (so Render can restart us); same if the celery worker crashes hard.
# `wait -n` returns when the first child exits and surfaces its exit code.
set +e
wait -n
EXIT_CODE=$?
set -e

# One child exited -- tell the other to wind down, then wait for it before
# returning so logs flush and resources are released.
shutdown
wait || true
exit "${EXIT_CODE}"
