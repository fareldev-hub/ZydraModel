#!/bin/bash
set -Eeuo pipefail

STATUS_FILE="${MODEL_STATUS_FILE:-/tmp/zydra-setup-status.json}"

if ! command -v curl >/dev/null 2>&1; then
    echo "curl tidak ditemukan; image container belum memasang dependency setup." >&2
    exit 1
fi

write_status() {
    local stage="$1"
    local message="$2"
    local temporary_file="${STATUS_FILE}.$$"
    printf '{"stage":"%s","message":"%s"}\n' "$stage" "$message" > "$temporary_file"
    mv "$temporary_file" "$STATUS_FILE"
}

handle_setup_error() {
    local exit_code=$?
    write_status "failed" "Setup model gagal (exit code ${exit_code}); periksa log container."
    exit "$exit_code"
}
trap handle_setup_error ERR

write_status "waiting_for_ollama" "Menunggu Ollama berjalan."
echo "Menunggu Ollama siap..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "Ollama siap"

if ! ollama show smollm2:1.7b >/dev/null 2>&1; then
    write_status "downloading_base_model" "Mengunduh model dasar smollm2:1.7b."
    echo "Pull smollm2:1.7b..."
    ollama pull smollm2:1.7b
else
    echo "smollm2:1.7b sudah ada"
fi

write_status "creating_zydra_model" "Membuat model Zydra dari smollm2:1.7b."
echo "Membuat atau memperbarui model Zydra..."
ollama create zydra -f /root/Modelfile

write_status "ready" "Model Zydra siap."
echo "Setup selesai"
