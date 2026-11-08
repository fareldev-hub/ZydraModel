#!/bin/bash
set -euo pipefail

mkdir -p /data
exec python3 -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}"
