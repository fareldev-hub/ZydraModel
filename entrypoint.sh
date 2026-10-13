#!/bin/bash
set -e

export OLLAMA_MODELS="${OLLAMA_MODELS:-/data/ollama}"
mkdir -p "$OLLAMA_MODELS" "$(dirname "${INSTRUCTIONS_FILE:-/data/instructions.txt}")"

ollama serve &
OLLAMA_PID=$!

/root/run.sh &
SETUP_PID=$!

python3 -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}" &
API_PID=$!

cleanup() {
    trap - SIGTERM SIGINT
    kill "$API_PID" "$OLLAMA_PID" 2>/dev/null || true
    if [ -n "$SETUP_PID" ]; then
        kill "$SETUP_PID" 2>/dev/null || true
    fi
    wait 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

while true; do
    if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
        wait "$OLLAMA_PID"
        exit $?
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
        wait "$API_PID"
        exit $?
    fi
    if [ -n "$SETUP_PID" ] && ! kill -0 "$SETUP_PID" 2>/dev/null; then
        if ! wait "$SETUP_PID"; then
            echo "Setup model gagal" >&2
            exit 1
        fi
        SETUP_PID=""
    fi
    sleep 2
done
