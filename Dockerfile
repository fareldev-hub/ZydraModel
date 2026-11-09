FROM ghcr.io/ggml-org/llama.cpp:server

WORKDIR /app

ENV MODEL_SERVER_URL="http://127.0.0.1:8081" \
    PYTHONUNBUFFERED=1 \
    API_KEYS_FILE="/data/database/api.json" \
    AUTH_FILE="/data/auth" \
    LLAMA_CACHE="/data/model-cache"

COPY requirements.txt /app/requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt \
    && rm -rf /var/lib/apt/lists/*

COPY api.py /app/api.py
COPY entrypoint.sh /app/entrypoint.sh
COPY static /app/static
COPY MODEL_LICENSES /app/MODEL_LICENSES

RUN chmod +x /app/entrypoint.sh

ENV PATH="/opt/venv/bin:${PATH}"

EXPOSE 8000
HEALTHCHECK NONE

ENTRYPOINT ["/app/entrypoint.sh"]
