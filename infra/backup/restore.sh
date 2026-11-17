#!/bin/sh
# Restaura um dump: restore.sh /backups/db-<data>.dump.enc
# ATENÇÃO: apaga e recria os dados do banco. Pare backend, worker, beat e bridge antes.
set -eu
set -o pipefail
FILE="${1:?uso: restore.sh /backups/db-<data>.dump.enc}"
: "${BACKUP_PASSPHRASE:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$FILE" \
  | PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h "${POSTGRES_HOST:-postgres}" \
      -U "$POSTGRES_USER" -d "${TRAMITAI_DB_NAME:-tramitai}" --clean --if-exists --no-owner \
      --role=tramitai_owner
echo "restaurado: $FILE"
