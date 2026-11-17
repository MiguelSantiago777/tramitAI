#!/bin/sh
# Roda o backup todo dia em BACKUP_HOUR (hora UTC; 6 = 3h em Brasília).
set -u
HOUR="${BACKUP_HOUR:-6}"
echo "backup agendado para ${HOUR}h UTC"
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) ${HOUR}:00:00" +%s 2>/dev/null || echo 0)
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  /usr/local/bin/backup.sh || echo "backup FALHOU" >&2
done
