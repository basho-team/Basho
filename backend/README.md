# Basho — backend

API FastAPI (Python 3.12, gerenciada com [uv](https://docs.astral.sh/uv/)).
Veja o [README da raiz](../README.md) para o setup local completo.

```bash
uv sync
uv run uvicorn basho.main:app --factory --reload
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```
