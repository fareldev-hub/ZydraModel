FROM ollama/ollama:latest

RUN apt-get update && apt-get install -y \
        curl \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install fastapi uvicorn requests

ENV PATH="/opt/venv/bin:$PATH"

COPY Modelfile /root/Modelfile
COPY api.py /root/api.py
COPY run.sh /root/run.sh
COPY entrypoint.sh /root/entrypoint.sh

RUN chmod +x /root/run.sh /root/entrypoint.sh

WORKDIR /root

EXPOSE 11434 8000

ENTRYPOINT ["/root/entrypoint.sh"]
