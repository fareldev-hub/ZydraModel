FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV CMAKE_ARGS="-DGGML_NATIVE=OFF" \
    FORCE_CMAKE=1 \
    MODEL_PATH="/app/model/qwen2.5-0.5b-instruct-q4_k_m.gguf" \
    MODEL_CONTEXT_SIZE=8192 \
    MODEL_THREADS=4 \
    PYTHONUNBUFFERED=1 \
    API_KEYS_FILE="/data/database/api.json" \
    AUTH_FILE="/data/auth"

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && apt-get purge -y --auto-remove build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

COPY api.py /app/api.py
COPY training/data.txt /app/training/data.txt
COPY entrypoint.sh /app/entrypoint.sh
COPY static /app/static
COPY MODEL_LICENSES /app/MODEL_LICENSES

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
