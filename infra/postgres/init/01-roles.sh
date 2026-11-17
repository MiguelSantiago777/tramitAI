#!/usr/bin/env bash
# Cria os dois roles do TramitAI e o banco da aplicação.
#
#   tramitai_owner: dono das tabelas, roda migrations. CREATEDB para o pytest criar o banco de teste.
#   tramitai_app:   usado pela aplicação em runtime. Sem SUPERUSER e sem BYPASSRLS, então o RLS
#                   sempre vale para ele. Os GRANTs de DML são aplicados pelo post_migrate (apps.core).
#
# Roda automaticamente no primeiro start do container postgres (docker-entrypoint-initdb.d)
# e é reaproveitado no CI (com PGHOST/PGPASSWORD no ambiente).
set -euo pipefail

: "${TRAMITAI_DB_NAME:=tramitai}"
: "${TRAMITAI_OWNER_PASSWORD:?defina TRAMITAI_OWNER_PASSWORD}"
: "${TRAMITAI_APP_PASSWORD:?defina TRAMITAI_APP_PASSWORD}"

psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER:-postgres}" \
  --dbname "${POSTGRES_DB:-postgres}" \
  -v db_name="$TRAMITAI_DB_NAME" \
  -v owner_pw="$TRAMITAI_OWNER_PASSWORD" \
  -v app_pw="$TRAMITAI_APP_PASSWORD" <<-'EOSQL'
	CREATE ROLE tramitai_owner LOGIN CREATEDB NOSUPERUSER NOBYPASSRLS PASSWORD :'owner_pw';
	CREATE ROLE tramitai_app   LOGIN NOCREATEDB NOSUPERUSER NOBYPASSRLS PASSWORD :'app_pw';
	CREATE DATABASE :"db_name" OWNER tramitai_owner;
EOSQL
