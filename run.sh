#!/bin/bash
set -e

echo "Menunggu Ollama siap..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "Ollama siap"

if ! ollama list | grep -q "qwen3-vl:2b"; then
    echo "Pull qwen3-vl:2b..."
    ollama pull qwen3-vl:2b
else
    echo "qwen3-vl:2b sudah ada"
fi

echo "Membuat model Zydra..."
ollama create zydra -f /root/Modelfile

echo "Setup selesai"
