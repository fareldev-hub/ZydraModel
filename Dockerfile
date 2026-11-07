FROM python:3.11-slim

WORKDIR /app

ENV MODEL_PATH="/app/model/zydra-base" \
    MODEL_LORA_PATH="/app/model/zydra-lora" \
    MODEL_CONTEXT_SIZE=8192 \
    MODEL_THREADS=4 \
    PYTHONUNBUFFERED=1 \
    API_KEYS_FILE="/data/database/api.json" \
    AUTH_FILE="/data/auth"

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.7,<3.0" \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY api.py /app/api.py
COPY entrypoint.sh /app/entrypoint.sh
COPY static /app/static
COPY MODEL_LICENSES /app/MODEL_LICENSES

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
