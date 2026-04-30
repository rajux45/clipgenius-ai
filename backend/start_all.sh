#!/usr/bin/env bash
# Combined launcher used when we need a single container to run the API,
# the Celery worker, and Celery beat (e.g. on free tiers without separate
# worker services). When BUNDLED_WORKERS is unset, this script just runs
# the API process so it can be reused on plans where workers are split out.

set -euo pipefail

if [[ "${BUNDLED_WORKERS:-1}" == "1" ]]; then
  echo "[start_all] launching celery worker (with embedded beat) in background"
  celery -A app.worker worker --beat --loglevel=info \
    --concurrency="${WORKER_CONCURRENCY:-1}" \
    --schedule=/tmp/celerybeat-schedule \
    >/proc/1/fd/1 2>/proc/1/fd/2 &
  WORKER_PID=$!
  trap "kill -TERM ${WORKER_PID} 2>/dev/null || true" EXIT
fi

echo "[start_all] launching gunicorn (uvicorn worker) on port ${PORT:-8000}"
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY:-2}" \
  -b "0.0.0.0:${PORT:-8000}" \
  --timeout 300 \
  --access-logfile - \
  --error-logfile -
