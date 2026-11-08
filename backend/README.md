# Basho — backend

API FastAPI (Python 3.12, gerenciada com [uv](https://docs.astral.sh/uv/)).
Veja o [README da raiz](../README.md) para o setup local completo.

```bash
uv sync
uv run uvicorn basho.main:app --factory --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

## Banco de dados e migrações

Alembic assíncrono (`backend/migrations/`). A URL vem só de `MIGRATION_DATABASE_URL`
(`postgresql+psycopg://...`, role dono do schema; sem fallback para `DATABASE_URL`).
Migrações rodam pela CLI, nunca no startup da API:

```bash
uv run alembic upgrade head      # aplica
uv run alembic downgrade base    # reverte tudo
```

`evidence_events` é append-only (ADR-0003): trigger bloqueia `UPDATE`/`DELETE`/`TRUNCATE`.

## Roles do banco e RLS

A migração `0002` cria dois roles **NOLOGIN** (sem senha), detentores de privilégio:
`basho_api` (API) e `basho_worker` (worker). Ambos só têm `SELECT`/`INSERT` em
`evidence_events` — nunca `UPDATE`/`DELETE`/`TRUNCATE` — e não são donos de nada.
`evidence_events` tem RLS **forçada** com a política
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`: sem
`basho.db.tenant_session` nenhuma linha é visível e nenhum INSERT é aceito.

O role de `MIGRATION_DATABASE_URL` é o dono do schema e precisa de `CREATEROLE` (ou ser
superuser) na primeira vez que a `0002` roda no cluster. O downgrade revoga os privilégios,
mas mantém os roles (objetos do cluster, possivelmente usados por outros bancos).

O login de cada ambiente é criado fora das migrações (senhas não passam pelo Alembic).
Depois de `alembic upgrade head`, como o role dono:

```sql
CREATE ROLE basho_api_login LOGIN PASSWORD '<senha>' IN ROLE basho_api;
CREATE ROLE basho_worker_login LOGIN PASSWORD '<senha>' IN ROLE basho_worker;
```

e use `postgresql+psycopg://basho_api_login:<senha>@.../basho` em `DATABASE_URL`.
Nunca aponte `DATABASE_URL` para o role dono: ele pode desligar o trigger e a RLS.

**Tabela nova de negócio** (na própria migração): `tenant_id NOT NULL`;
`ENABLE` + `FORCE ROW LEVEL SECURITY`; `CREATE POLICY <tabela>_tenant_isolation` com a
expressão acima em `USING` e `WITH CHECK`; `GRANT` só do necessário a `basho_api`,
`basho_worker`. Tabelas append-only (ex.: `audit_log`) recebem só `SELECT, INSERT` e entram
em `APPEND_ONLY_TABLES` de `tests/db/test_rls_roles_db.py`. As guardas desse arquivo falham
se alguma tabela ficar sem RLS forçada ou se os roles da app ganharem
`DELETE`/`TRUNCATE`.

No Windows, o psycopg assíncrono exige `SelectorEventLoop`; o `env.py` e os testes já
cuidam disso. Ao subir a API localmente no Windows, use `--loop none`.

## Testes de banco

Testes marcados com `@pytest.mark.db` usam Postgres real. Defina `TEST_DATABASE_URL`
(fallback: `DATABASE_URL`) com o **role dono** do servidor local (`docker compose up -d postgres`);
os testes criam logins `basho_test_*` com senha aleatória, membros de `basho_api`/`basho_worker`,
e rodam o ledger **como o role da app**;
os testes recriam os bancos dedicados `basho_test` e `basho_test_migrations`, sem tocar no
banco de dev. Sem banco acessível eles são pulados, exceto com `REQUIRE_DB_TESTS=1` (usado no CI), que os faz falhar.

```bash
export TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/basho
uv run pytest -m db        # só os testes de banco
uv run pytest -m "not db"  # sem banco
```
