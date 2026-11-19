#!/usr/bin/env bash
# Atualiza e (re)sobe o TramitAI em produção. Rode na pasta do projeto, no servidor.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Falta o .env. Rode: python3 infra/init_env.py" >&2
  exit 1
fi
if grep -q "seudominio" .env; then
  echo "O .env ainda tem 'seudominio': preencha DOMAIN, FRONTEND_URL etc." >&2
  exit 1
fi

if grep -q "^EMAIL_URL=consolemail" .env; then
  echo "AVISO: EMAIL_URL não configurado. 'Esqueci minha senha' e alertas não serão enviados" >&2
  echo "       (e os links aparecem no log do worker). Configure antes de abrir para clientes." >&2
fi
if grep -q "^BACKUP_RCLONE_REMOTE=$" .env; then
  echo "AVISO: backup só fica no próprio servidor. Configure BACKUP_RCLONE_REMOTE." >&2
fi

COMPOSE=(docker compose -f docker-compose.prod.yml)
if [ -d .git ]; then
  git pull --ff-only
fi
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --remove-orphans
# O Caddyfile é montado como arquivo: mudou no git, mas o container segue com a config antiga.
"${COMPOSE[@]}" exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile \
  || echo "AVISO: não consegui recarregar o Caddy (rode: docker compose -f docker-compose.prod.yml restart caddy)" >&2
"${COMPOSE[@]}" ps
echo
echo "Pronto. Confira: https://$(grep '^DOMAIN=' .env | cut -d= -f2)/api/health/"
