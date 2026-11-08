# Basho

Plataforma de IA que **executa e organiza a operação de projetos de P&D tecnológico** e, no mesmo fluxo, **constrói continuamente as evidências exigidas pela Lei do Bem** — para PMEs que usufruem ou pretendem usufruir dos incentivos, observados os requisitos legais.

> O Basho apoia a documentação e a identificação preliminar de atividades potencialmente qualificáveis. Não garante benefício fiscal nem substitui responsáveis técnicos, contábeis ou legais.

## Documentação
- [Arquitetura](docs/architecture.md)
- [Decisões de arquitetura (ADRs)](docs/adr/)
- [Práticas de engenharia](docs/engineering-practices.md)
- [Regras para agentes de IA](CLAUDE.md)

## Stack
FastAPI + PostgreSQL + Claude (Maker) + verificador de outro modelo (Checker) · Next.js + TypeScript.

Monorepo:

| Pasta | Stack |
|-------|-------|
| `backend/` | Python 3.12 · uv · FastAPI · pydantic-settings · structlog · pytest · ruff · mypy |
| `frontend/` | Next.js (App Router) · TypeScript strict · Tailwind · shadcn/ui · TanStack Query · Zod |
| `docker-compose.yml` | PostgreSQL 16 para desenvolvimento local |

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 automaticamente)
- Node.js (versão em `frontend/.nvmrc`) e npm
- Docker com Docker Compose

## Setup local

1. **Variáveis de ambiente**

   ```bash
   cp .env.example .env
   ```

   Preencha todos os valores do `.env` (nunca versione esse arquivo). A API **não inicia**
   se alguma variável obrigatória faltar; a mensagem de erro lista só os nomes das variáveis,
   nunca os valores.

2. **Banco de dados**

   ```bash
   docker compose up -d --wait   # sobe o Postgres 16 e espera o healthcheck
   docker compose ps             # STATUS deve mostrar "healthy"
   ```

   São dois roles (ADR-0006): `MIGRATION_DATABASE_URL` usa o usuário do compose, dono do
   schema (ex.: `postgresql+psycopg://basho:<senha>@localhost:5432/basho`); `DATABASE_URL`
   usa um login da aplicação, membro de `basho_api`, sem UPDATE/DELETE no ledger e sujeito
   à RLS. Aplique as migrações e crie esse login uma vez (passo a passo em
   [`backend/README.md`](backend/README.md#roles-do-banco-e-rls)).

3. **Backend**

   ```bash
   cd backend
   cp ../.env .env               # ou exporte as variáveis no shell
   uv sync
   uv run uvicorn basho.main:app --factory --reload   # http://localhost:8000/health
   ```

4. **Frontend**

   ```bash
   cd frontend
   npm ci
   npm run dev                   # http://localhost:3000
   npm run gen:api               # regenera os tipos a partir de http://localhost:8000/openapi.json
   ```

## Checks (os mesmos da CI)

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm run build
```

A CI (`.github/workflows/ci.yml`) roda esses checks em todo PR para `main`.

## Contribuindo

Siga `CLAUDE.md` e `docs/engineering-practices.md`: uma issue → uma branch → um PR,
Conventional Commits e o template de PR em `.github/pull_request_template.md`.

## Demo local

`scripts/demo/up.sh` sobe banco, seed, API e interface. Roteiro e limitações em [docs/demo-local.md](docs/demo-local.md).
