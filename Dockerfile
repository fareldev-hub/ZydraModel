FROM ollama/ollama:latest

RUN apt-get update && apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && mkdir -p /data/ollama

ENV PATH="/opt/venv/bin:$PATH"
ENV OLLAMA_MODELS="/data/ollama"
ENV INSTRUCTIONS_FILE="/data/instructions.txt"
ENV PYTHONUNBUFFERED=1

WORKDIR /root

COPY requirements.txt /root/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /root/requirements.txt
COPY Modelfile /root/Modelfile
COPY api.py /root/api.py
COPY run.sh /root/run.sh
COPY entrypoint.sh /root/entrypoint.sh
COPY static ./static

RUN chmod +x /root/run.sh /root/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/root/entrypoint.sh"]
