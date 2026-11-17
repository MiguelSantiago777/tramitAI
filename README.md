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

## WhatsApp em desenvolvimento

Com `WHATSAPP_GATEWAY=fake` nada sai para a Meta. Para ver o fluxo completo localmente:

```bash
# 1) cadastrar um número para o escritório (o token vem do env ou é pedido no terminal)
docker compose exec -e WHATSAPP_ACCESS_TOKEN=qualquer backend   python manage.py register_whatsapp_account --tenant-slug escritorio-exemplo   --phone-number-id 100000001 --waba-id waba-dev --display-phone "+55 21 3000-0000"

# 2) simular uma mensagem recebida (passa pelo webhook real, com assinatura)
docker compose exec backend python manage.py simulate_inbound   --phone-number-id 100000001 --from 5521998765432 --name "Maria" --text "Bom dia"
```

Depois abra **Conversas** no app e responda. Em produção, o webhook da Meta aponta para
`/api/webhooks/whatsapp/` (verify token = `WHATSAPP_VERIFY_TOKEN`, assinatura com `WHATSAPP_APP_SECRET`).

## IA (Lia)

- `LLM_PROVIDER=fake` (padrão): respostas determinísticas locais, nada sai da máquina.
- `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`: API da Anthropic. Modelo e esforço em
  `LLM_MODEL` / `LLM_EFFORT`. Prompts versionados em `backend/apps/ia/prompts/` (versão ativa em
  `manifest.json`; nunca edite uma versão já usada, crie `v2.md`).

Fluxo: primeiro contato → rascunho com o termo de ciência (sem IA) → advogado aprova → cliente
responde ACEITO → a partir daí cada mensagem passa pela triagem e vira rascunho na fila
**Aprovações**. Nada é enviado sem aprovação humana; tudo fica em `core_auditevent`
(append-only).

## Andamentos (DataJud)

- `PROCESS_SOURCE=fake` (padrão): histórico fixo local. `PROCESS_SOURCE=datajud` +
  `DATAJUD_API_KEY` (chave pública da [wiki do DataJud](https://datajud-wiki.cnj.jus.br/api-publica/acesso))
  consulta a API Pública do CNJ.
- O beat agenda, de hora em hora, os processos ativos sem consulta há `CASE_CHECK_INTERVAL_HOURS`
  (padrão 12h), espaçados para não tomar 429. Na tela do processo há "Verificar agora".
- A primeira consulta vira linha de base (sem aviso). Depois, cada andamento novo dos últimos
  `MOVEMENT_NOTIFY_MAX_AGE_DAYS` vira um rascunho de aviso em português simples por cliente
  vinculado, na fila **Aprovações**. Para o LLM vão só dados públicos do tribunal e o papel do
  cliente; nome, CPF e telefone não.
- Janela de 24h fechada: ao aprovar, sai o modelo da Meta abaixo; o texto aprovado fica
  "aguardando o cliente" e sai sozinho quando ele responder.

Modelo a cadastrar na WABA de cada escritório (categoria **Utility**, idioma `pt_BR`, nome
`atualizacao_processo`; o nome pode ser trocado em `WhatsAppAccount.movement_template_name`):

```text
Olá, {{1}}! Há uma atualização no seu processo nº {{2}}. Responda esta mensagem para receber os detalhes.
```

Simular um andamento em dev (passa pelo mesmo caminho da consulta real):

```bash
docker compose exec backend uv run python manage.py simulate_movement \
  --tenant escritorio-demo --cnj 0004242-57.2024.8.19.0001 --name "Conclusão"
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
