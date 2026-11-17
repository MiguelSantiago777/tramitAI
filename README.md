# TramitAI

Secretária jurídica no WhatsApp para pequenos escritórios de advocacia. A assistente que fala com o
cliente final se chama **Lia**. A IA nunca envia nada sozinha: tudo passa pela aprovação do advogado.

## Stack

- **backend/**: Python 3.14, Django 5.2 + DRF, JWT (simplejwt), drf-spectacular, Celery + Redis, PostgreSQL 16. Dependências com `uv`.
- **frontend/**: Angular 22 (standalone, signals, zoneless) + Angular Material. Testes com Vitest.
- **infra/**: script de init do Postgres (roles).

## Rodando local

```bash
cp .env.example .env          # ajuste se quiser
docker compose up -d          # postgres, redis, migrate, backend, worker, beat, frontend
```

- App: http://localhost:4200
- API: http://localhost:8000/api/ · Swagger: http://localhost:8000/api/docs/ · Health: `/api/health/`

Criar um escritório com usuário titular (onboarding manual do piloto):

```bash
docker compose exec backend python manage.py create_tenant --name "Escritório Exemplo" --owner-email voce@exemplo.com
```

## Testes e lint

```bash
# backend
docker compose run --rm --no-deps backend sh -c "ruff check . && ruff format --check . && mypy . && pytest"
# frontend
cd frontend && npm run lint && npm run format:check && npm run test:ci
```

## Multi-tenant (coluna + RLS)

Toda tabela de negócio herda `apps.core.models.TenantModel` (coluna `tenant_id`) e liga RLS na
migration com `apps.core.db.EnableRLS`. São duas travas:

1. **Aplicação**: o manager padrão filtra pelo tenant ativo e levanta erro se não houver um.
2. **Postgres**: `ENABLE` + `FORCE ROW LEVEL SECURITY` com policy
   `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` (fail-closed).

O tenant vem do claim `tid` do JWT. A autenticação confere a `Membership` e roda
`set_config('app.tenant_id', %s, true)` dentro da transação do request (`ATOMIC_REQUESTS`).

Roles do banco:

| Role | Uso | Privilégios |
|---|---|---|
| `tramitai_owner` | migrations, criação do banco de teste | dono das tabelas, CREATEDB |
| `tramitai_app` | aplicação e testes | só SELECT/INSERT/UPDATE/DELETE, sem SUPERUSER/BYPASSRLS |

Regras para código novo:

- Tabela de negócio nova: herde `TenantModel` e ponha `EnableRLS("<model>")` na migration. Um
  teste falha se esquecer.
- Tasks Celery recebem `tenant_id` explícito e usam `tenant_atomic(tenant_id)` em blocos curtos.
- **Nunca** chame HTTP/LLM dentro de transação aberta: lê numa transação curta, chama fora e grava
  em outra transação curta. Em views, enfileire a task com `transaction.on_commit`.
- Não use `transactional_db` nos testes (o flush faz TRUNCATE, que o role da aplicação não tem).
