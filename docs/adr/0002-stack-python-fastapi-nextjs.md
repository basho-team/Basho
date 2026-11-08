# ADR-0002: Stack Python (FastAPI) + Next.js

- **Status:** aceita
- **Data:** 2026-11-07
- **Decisores:** equipe Basho

## Contexto e problema
Precisamos de um ecossistema forte para IA/dados no backend e uma UI moderna e rápida de construir.

## Opções consideradas
1. Full TypeScript (Next.js + Drizzle)
2. Python + Streamlit
3. **Python (FastAPI) + Next.js**

## Decisão
Opção 3.

| Camada | Escolha |
| --- | --- |
| Linguagem backend | Python 3.12, gerenciado com `uv` |
| API | FastAPI + Pydantic v2 |
| ORM / migrações | SQLAlchemy 2 (async) + Alembic |
| Banco | PostgreSQL 16 (Docker Compose em dev) |
| LLM | SDK `anthropic` (Maker); cliente do segundo provedor atrás da interface `Verifier` |
| Qualidade | `ruff` (lint+format), `mypy --strict` nos módulos de domínio, `pytest` + `pytest-asyncio` |
| Logs | `structlog` (JSON), ids de correlação por requisição/job |
| Frontend | Next.js (App Router) + TypeScript strict + shadcn/ui + Tailwind + TanStack Query + Zod |
| CI | GitHub Actions: lint, type-check, testes de backend e frontend |

## Consequências
- **Positivas:** melhor tooling de IA, tipagem nas duas pontas, UI rápida.
- **Negativas:** duas linguagens; contrato entre elas precisa ser mantido.
- **Regras derivadas:**
  - O contrato da API é o OpenAPI gerado pelo FastAPI; o frontend gera tipos a partir dele (sem tipos duplicados à mão).
  - Versões de dependências fixadas (`uv.lock`, lockfile do frontend).
  - Nenhuma dependência nova sem justificativa no PR.
