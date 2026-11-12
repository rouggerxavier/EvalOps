# Migrations do banco

O schema da API vive em dois lugares que precisam concordar:

- `apps/api/app/models.py`: models SQLAlchemy. Os testes e o dev em SQLite criam o
  banco com `Base.metadata.create_all` mais `ensure_schema_compatibility()`
  (`apps/api/app/db.py`).
- `apps/api/alembic/versions/`: migrations Alembic. Produção (Postgres 16) usa só
  elas.

Toda mudança de schema entra nos dois: no model e numa revision nova.

## Qual caminho roda

- `EVALOPS_USE_ALEMBIC=1`: o lifespan da API roda `alembic upgrade head` ao subir
  (`apps/api/app/main.py`). `docker-compose.prod.yml` liga essa variável e também
  roda `alembic upgrade head` antes da API.
- Sem a variável: `create_all`. É o caminho dos testes (`apps/api/tests/conftest.py`
  força SQLite) e do dev local.

O Alembic lê a URL de `DATABASE_URL` (ou `EVALOPS_DB_URL`) em `alembic/env.py`;
`alembic.ini` não tem URL.

## Aplicar

```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/evalops alembic upgrade head
alembic current
alembic downgrade -1
```

Banco criado antes por `create_all` (sem tabela `alembic_version`) não roda a
baseline: marque-o com `alembic stamp 0001_baseline` e depois `alembic upgrade head`.

## Criar uma revision

1. Altere o model em `app/models.py`.
2. Contra um Postgres já em `head`, gere a revision:

   ```bash
   alembic revision --autogenerate -m "descricao curta"
   ```

3. Revise o arquivo gerado à mão. O autogenerate não acerta índice de expressão,
   DDL só de Postgres nem backfill.
4. Confirme que models e migrations batem:

   ```bash
   alembic upgrade head && alembic check
   ```

   `alembic check` deve terminar com `No new upgrade operations detected.`

Índice que só existe em Postgres (ex.: `ix_traces_metadata_prompt_ref`) fica no
model com `.ddl_if(dialect="postgresql")`, para o `create_all` em SQLite pulá-lo.

Postgres temporário para os passos 2 e 4:

```bash
docker run --rm -d --name evalops-pg-tmp -p 55433:5432 -e POSTGRES_USER=evalops -e POSTGRES_PASSWORD=evalops -e POSTGRES_DB=evalops postgres:16-alpine
```

```bash
docker stop evalops-pg-tmp
```

## CI

O job `migrate-postgres` (`.github/workflows/ci.yml`) sobe Postgres 16, instala a
API com `-c requirements.lock` e roda `alembic upgrade head`. Ele não roda
`alembic check`; rode o passo 4 localmente antes do PR.

## Fundações de tarefas — 0014

Esta versão adiciona snapshots materializados, modelos declarados, predições, avaliações, métricas, principals e recibos. Antes de iniciar a nova API sobre um banco existente, faça backup e aplique `alembic upgrade head`; `EVALOPS_USE_ALEMBIC=1` mantém o caminho normal em produção. A API não completa parcialmente essa migration por `create_all`.

Para um banco local criado por `create_all` e sem `alembic_version`, verifique primeiro se o schema corresponde integralmente à revisão 0013 (incluindo mudanças anteriores). Somente nessa condição use `alembic stamp 0013_user_credential_version` seguido de `alembic upgrade head`. Não use stamp para ocultar divergências de schema. Bancos novos continuam aceitando `create_all` no modo local.

Upgrade preserva IDs, JSONs, status e `passed` legados. Os novos resultados usam decisão própria. O downgrade 0014 é bloqueado se houver dados de tarefas ou principals; não apaga evidências nem transforma chaves de principals em chaves legadas. Rollback operacional desabilita principals e suspende a UI nova, mantendo o schema aditivo. Não retornar uma API antiga ao tráfego enquanto houver chaves de principal ativas, pois ela não aplica o isolamento de ambiente dessas identidades.
