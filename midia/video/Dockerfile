# Ferramentas do vídeo: navegador (capturas), ffmpeg (montagem) e edge-tts (voz neural).
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --break-system-packages playwright==1.49.0 edge-tts httpx==0.28.1

WORKDIR /video
