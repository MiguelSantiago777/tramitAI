# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM python:3.14-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=uv /uv /usr/local/bin/uv
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Desenvolvimento: dependências de dev incluídas, código montado por volume no compose.
FROM base AS dev
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Produção: imagem genérica (roda igual em AWS, GCP ou VPS).
FROM base AS prod
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN DJANGO_SECRET_KEY=collectstatic-only DATABASE_URL=postgres://x@localhost/x \
    python manage.py collectstatic --noinput
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
