#!/bin/bash
set -Eeuo pipefail

STATUS_FILE="${MODEL_STATUS_FILE:-/tmp/zydra-setup-status.json}"

write_status() {
    local stage="$1"
    local message="$2"
    local temporary_file="${STATUS_FILE}.$$"
    printf '{"stage":"%s","message":"%s"}\n' "$stage" "$message" > "$temporary_file"
    mv "$temporary_file" "$STATUS_FILE"
}

handle_setup_error() {
    local exit_code=$?
    write_status "failed" "Setup model gagal (exit code ${exit_code}); periksa log deploy Railway."
    exit "$exit_code"
}
trap handle_setup_error ERR

write_status "waiting_for_ollama" "Menunggu Ollama berjalan."
echo "Menunggu Ollama siap..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "Ollama siap"

if ! ollama show qwen3-vl:2b >/dev/null 2>&1; then
    write_status "downloading_base_model" "Mengunduh model dasar qwen3-vl:2b."
    echo "Pull qwen3-vl:2b..."
    ollama pull qwen3-vl:2b
else
    echo "qwen3-vl:2b sudah ada"
fi

write_status "creating_zydra_model" "Membuat model Zydra dari qwen3-vl:2b."
echo "Membuat atau memperbarui model Zydra..."
ollama create zydra -f /root/Modelfile

write_status "ready" "Model Zydra siap."
echo "Setup selesai"
