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

Trilha de fundo: composta por `make_music.py` (pad, baixo e arpejo em Dó maior, sem direitos de
terceiros) e mixada no fim por `add_music` em `make_video.py`, que também vale para os manuais. A
música abaixa sozinha enquanto a narração fala; o volume geral fica em `MUSIC_VOLUME`.

O roteiro fica em `SCENES` dentro de `make_video.py`. O texto da narração é enviado ao serviço
de voz da Microsoft (só o roteiro, sem dados de clientes).

## Manuais (aba Manuais do sistema)

Oito vídeos curtos, um por assunto, servidos pelo próprio sistema em `/videos/manuais/`.

```bash
# dados extras do escritório de demonstração (equipe, respostas prontas, etiquetas)
docker compose run --rm -v "$PWD/midia:/midia" backend sh -c "python manage.py shell < /midia/video/seed_manuais.py"

docker run --rm -v "$PWD/midia/video:/video" tramitai-video python3 capture_manuais.py
docker run --rm -v "$PWD/midia/video:/video" tramitai-video python3 make_manuais.py          # todos
docker run --rm -v "$PWD/midia/video:/video" tramitai-video python3 make_manuais.py agenda   # só um

cp midia/video/out/manuais/* frontend/public/videos/manuais/
```

Roteiro de cada manual: lista `MANUAIS` em `make_manuais.py`. Telas e elementos destacados:
`SHOTS` em `capture_manuais.py`.
