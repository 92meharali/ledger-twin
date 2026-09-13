#!/usr/bin/env sh
# Production start (Railway / Docker). Honors $PORT.
set -eu
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
