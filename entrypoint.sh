#!/bin/bash
set -e

ollama serve &
OLLAMA_PID=$!

/root/run.sh &
RUN_PID=$!

echo "Menunggu model Zydra siap..."
until ollama list 2>/dev/null | grep -q "zydra"; do
    sleep 2
done
echo "Model Zydra siap"

python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

cleanup() {
    kill $API_PID $RUN_PID $OLLAMA_PID 2>/dev/null || true
    wait 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

wait -n $OLLAMA_PID $API_PID
