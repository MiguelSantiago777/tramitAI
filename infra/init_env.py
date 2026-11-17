#!/usr/bin/env python3
"""Cria o .env de produção a partir do .env.prod.example, gerando todos os segredos.

Uso (no servidor, na pasta do projeto):  python3 infra/init_env.py  [arquivo, padrão .env]
Não sobrescreve um .env existente. Só usa a biblioteca padrão do Python.
"""

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.prod.example"
TARGET = ROOT / (sys.argv[1] if len(sys.argv) > 1 else ".env")


def main() -> None:
    if TARGET.exists():
        sys.exit(".env já existe; não vou sobrescrever. Apague-o se quiser gerar de novo.")
    owner_pw, app_pw = secrets.token_hex(24), secrets.token_hex(24)
    db = "tramitai"
    generated = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "TRAMITAI_OWNER_PASSWORD": owner_pw,
        "TRAMITAI_APP_PASSWORD": app_pw,
        "DATABASE_URL": f"postgres://tramitai_app:{app_pw}@postgres:5432/{db}",
        "DATABASE_OWNER_URL": f"postgres://tramitai_owner:{owner_pw}@postgres:5432/{db}",
        "FIELD_ENCRYPTION_KEYS": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "WHATSAPP_BRIDGE_SECRET": secrets.token_urlsafe(48),
        "WHATSAPP_VERIFY_TOKEN": secrets.token_urlsafe(24),
        "BACKUP_PASSPHRASE": secrets.token_urlsafe(32),
    }
    lines = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and value == "__GERAR__":
            line = f"{key}={generated[key]}"
        lines.append(line)
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    TARGET.chmod(0o600)
    print(".env criado com segredos novos (permissão 600).")
    print("Agora edite o .env e preencha as linhas marcadas PREENCHER.")
    print("IMPORTANTE: copie BACKUP_PASSPHRASE para um lugar seguro fora do servidor.")


if __name__ == "__main__":
    main()
