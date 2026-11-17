# Backup diário: dump do Postgres + sessões do WhatsApp, criptografados (AES-256) e, se
# configurado, copiados para fora do servidor (rclone: Cloudflare R2, Backblaze B2, S3...).
FROM postgres:16-alpine
RUN apk add --no-cache rclone openssl
COPY backup.sh loop.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/loop.sh /usr/local/bin/restore.sh
CMD ["/usr/local/bin/loop.sh"]
