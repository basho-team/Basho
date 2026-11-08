#!/bin/sh
# Processo do backend, escolhido por BASHO_PROCESS:
#   api     - FastAPI (DATABASE_URL = basho_api_login)
#   worker  - fila de agent_runs (DATABASE_URL = basho_worker_login)
#   migrate - serviço one-shot com o role dono: migrações + logins de menor privilégio
#             (+ seed sintético com DATABASE_URL = basho_api_login, se RUN_SEED=1).
# Só o migrate recebe MIGRATION_DATABASE_URL; API e worker nunca (ADR-0006).
set -eu

case "${BASHO_PROCESS:-api}" in
  api)
    exec uvicorn basho.main:app --factory --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
    ;;
  worker)
    exec python -m basho.agent.worker
    ;;
  migrate)
    alembic upgrade head
    python -m basho.provision
    # Seed sintético idempotente (is_synthetic), como o login da API: nunca o dono.
    if [ "${RUN_SEED:-0}" = "1" ]; then
      exec python -m basho.seed
    fi
    ;;
  *)
    echo "BASHO_PROCESS inválido (use api, worker ou migrate)" >&2
    exit 64
    ;;
esac
