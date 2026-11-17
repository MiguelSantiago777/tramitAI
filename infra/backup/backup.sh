#!/bin/sh
# Um backup agora. Arquivos: /backups/db-<data>.dump.enc e /backups/whatsapp-<data>.tar.gz.enc
set -eu
set -o pipefail
: "${BACKUP_PASSPHRASE:?defina BACKUP_PASSPHRASE (guarde fora do servidor!)}"
: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"
DB="${TRAMITAI_DB_NAME:-tramitai}"
DIR=/backups
KEEP="${BACKUP_KEEP_DAYS:-14}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$DIR"

encrypt() { openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$1"; }

# Superusuário: o dump precisa ver todas as linhas (o RLS limita os roles da aplicação).
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "${POSTGRES_HOST:-postgres}" -U "$POSTGRES_USER" \
  -d "$DB" -Fc | encrypt "$DIR/db-$TS.dump.enc.part"
mv "$DIR/db-$TS.dump.enc.part" "$DIR/db-$TS.dump.enc"

if [ -d /bridge ]; then
  tar -C /bridge -czf - . | encrypt "$DIR/whatsapp-$TS.tar.gz.enc.part"
  mv "$DIR/whatsapp-$TS.tar.gz.enc.part" "$DIR/whatsapp-$TS.tar.gz.enc"
fi

find "$DIR" -name '*.enc' -mtime "+$KEEP" -delete
find "$DIR" -name '*.part' -delete

if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  rclone copy "$DIR" "$BACKUP_RCLONE_REMOTE" --include "*-$TS.*" --quiet
  echo "backup $TS: ok (local + remoto)"
else
  echo "backup $TS: ok (só local; configure BACKUP_RCLONE_REMOTE para copiar para fora)"
fi
