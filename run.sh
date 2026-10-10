#!/bin/bash
set -e

echo "🔧 [run.sh] Memulai setup Zydra..."

echo "⏳ Menunggu Ollama siap..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "✅ Ollama siap"

if ! ollama list | grep -q "llama3.2:1b"; then
    echo "📥 Pull llama3.2:1b..."
    ollama pull llama3.2:1b
else
    echo "✓ llama3.2:1b sudah ada (dari volume)"
fi

echo "Membuat model Zydra..."
ollama create zydra -f /root/Modelfile

echo "✅ [run.sh] Setup selesai!"
