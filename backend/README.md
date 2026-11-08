# Basho — backend

API FastAPI (Python 3.12, gerenciada com [uv](https://docs.astral.sh/uv/)).
Veja o [README da raiz](../README.md) para o setup local completo.

```bash
uv sync
uv run uvicorn basho.main:app --factory --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

## Banco de dados e migrações

Alembic assíncrono (`backend/migrations/`). A URL vem só de `DATABASE_URL`
(`postgresql+psycopg://...`). Migrações rodam pela CLI, nunca no startup da API:

```bash
uv run alembic upgrade head      # aplica
uv run alembic downgrade base    # reverte tudo
```

`evidence_events` é append-only (ADR-0003): trigger bloqueia `UPDATE`/`DELETE`/`TRUNCATE`.

No Windows, o psycopg assíncrono exige `SelectorEventLoop`; o `env.py` e os testes já
cuidam disso. Ao subir a API localmente no Windows, use `--loop none`.

## Testes de banco

Testes marcados com `@pytest.mark.db` usam Postgres real. Defina `TEST_DATABASE_URL`
(fallback: `DATABASE_URL`) apontando para o servidor local (`docker compose up -d postgres`);
os testes recriam os bancos dedicados `basho_test` e `basho_test_migrations`, sem tocar no
banco de dev. Sem banco acessível eles são pulados, exceto com `REQUIRE_DB_TESTS=1` (usado no CI), que os faz falhar.

```bash
export TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/basho
uv run pytest -m db        # só os testes de banco
uv run pytest -m "not db"  # sem banco
```
