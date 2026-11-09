#!/bin/bash
set -euo pipefail

mkdir -p /data

if [[ "${RUN_LOCAL_MODEL:-true}" != "true" ]]; then
  exec python3 -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}"
fi

/app/llama-server \
  -hf "${HF_MODEL_REPO:-fareld3v-hub/zydra}" \
  --host 127.0.0.1 \
  --port 8081 \
  --alias zydra-loRa \
  --ctx-size "${MODEL_CONTEXT_SIZE:-2048}" \
  --threads "${MODEL_THREADS:-4}" \
  --no-mmproj-offload &
llama_pid=$!

python3 -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}" &
api_pid=$!

cleanup() {
  kill "$llama_pid" "$api_pid" 2>/dev/null || true
  wait "$llama_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

set +e
wait -n "$llama_pid" "$api_pid"
status=$?
set -e
exit "$status"
