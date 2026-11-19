#!/bin/bash
set -euo pipefail

mkdir -p /data

if [[ "${RUN_LOCAL_MODEL:-true}" != "true" ]]; then
  exec python3 -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}"
fi

# Port 8081 = khusus vision (mmproj), port 8082 = khusus chat teks (zydra-loRa).
# MODEL_SERVER_URL tetap diekspor sebagai alias lama untuk server vision.
export MODEL_SERVER_URL="http://127.0.0.1:8081"
export VISION_SERVER_URL="http://127.0.0.1:8081"
export CHAT_SERVER_URL="http://127.0.0.1:8082"

/app/llama-server \
  -hf "${VISION_MODEL_REPO:-${HF_MODEL_REPO:-ggml-org/SmolVLM2-500M-Video-Instruct-GGUF:Q8_0}}" \
  --host 127.0.0.1 \
  --port 8081 \
  --alias zydra-vision \
  --ctx-size "${VISION_CONTEXT_SIZE:-${MODEL_CONTEXT_SIZE:-2048}}" \
  --threads "${VISION_THREADS:-${MODEL_THREADS:-4}}" \
  --no-mmproj-offload &
vision_pid=$!

# zydra-loRa dipakai untuk chat saja, projector gambar sengaja dinonaktifkan.
/app/llama-server \
  -hf "${CHAT_MODEL_REPO:-fareld3v-hub/zydra}" \
  --hf-file "${CHAT_MODEL_FILE:-zydra-loRa.gguf}" \
  --no-mmproj \
  --host 127.0.0.1 \
  --port 8082 \
  --alias zydra-loRa \
  --ctx-size "${CHAT_CONTEXT_SIZE:-${MODEL_CONTEXT_SIZE:-2048}}" \
  --threads "${CHAT_THREADS:-${MODEL_THREADS:-4}}" &
chat_pid=$!

python3 -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}" &
api_pid=$!

cleanup() {
  kill "$vision_pid" "$chat_pid" "$api_pid" 2>/dev/null || true
  wait "$vision_pid" 2>/dev/null || true
  wait "$chat_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

set +e
wait -n "$vision_pid" "$chat_pid" "$api_pid"
status=$?
set -e
exit "$status"
