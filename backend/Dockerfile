# Imagem única do backend: API ou worker, escolhido por BASHO_PROCESS (api | worker).
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependências primeiro (cache de camada), depois o código.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
# Fixtures sintéticas do GitHub para as tools simuladas do worker (GITHUB_FIXTURES_DIR).
COPY tests/fixtures/github ./fixtures/github
RUN uv sync --locked --no-dev

RUN useradd --create-home --uid 10001 basho
USER basho

COPY --chown=basho:basho docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["sh", "/usr/local/bin/docker-entrypoint.sh"]
