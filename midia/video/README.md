# Vídeo de apresentação

Gera `out/tramitai-apresentacao.mp4` (1920x1080) com telas reais do sistema, voz neural em
português (Microsoft Edge TTS, voz `pt-BR-FranciscaNeural`) e legendas.

Pré-requisito: ambiente de dev no ar (`docker compose up -d`, frontend em localhost:4200).

```bash
# 1. Escritório fictício "Silva & Lima Advocacia" (uma vez)
docker compose run --rm -v "$PWD/midia:/midia" backend sh -c "python manage.py shell < /midia/video/seed_demo.py"

# 2. Ferramentas (navegador, ffmpeg, voz)
docker build -t tramitai-video midia/video

# 3. Telas e vídeo
docker run --rm -v "$PWD/midia/video:/video" tramitai-video python3 capture.py
docker run --rm -v "$PWD/midia/video:/video" tramitai-video python3 make_video.py
# outra voz: ... python3 make_video.py pt-BR-AntonioNeural
```

O roteiro fica em `SCENES` dentro de `make_video.py`. O texto da narração é enviado ao serviço
de voz da Microsoft (só o roteiro, sem dados de clientes).
