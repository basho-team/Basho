#!/usr/bin/env bash
# Sobe a demo local do Basho com um banco NOVO (nada é apagado): Postgres em docker,
# migrações, seed sintético, API (uvicorn) e frontend (next start).
#
# Uso: scripts/demo/up.sh            # cria banco basho_demo_<carimbo> e sobe tudo
#      DEMO_DB=basho_demo_x scripts/demo/up.sh   # reutiliza um banco existente
# Variáveis: DEMO_SECRETS (padrão ~/.basho-demo-secrets), DEMO_PG_PORT (55432),
#            DEMO_API_PORT (8765), DEMO_WEB_PORT (3765).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETS="${DEMO_SECRETS:-$HOME/.basho-demo-secrets}"
PG_PORT="${DEMO_PG_PORT:-55432}"
API_PORT="${DEMO_API_PORT:-8765}"
WEB_PORT="${DEMO_WEB_PORT:-3765}"
CONTAINER="${DEMO_PG_CONTAINER:-basho-demo-pg}"
DB="${DEMO_DB:-basho_demo_$(date +%Y%m%d%H%M%S)}"
LOGS="${DEMO_LOGS:-$ROOT/.demo-logs}"
TENANT_ID="99999999-9999-4999-8999-999999999999"

secret() {  # gera uma vez, reutiliza depois (permissão 600)
  local file="$SECRETS/$1"
  if [[ ! -s "$file" ]]; then
    python3 -c "import secrets;print(secrets.token_urlsafe($2))" > "$file"
  fi
  chmod 600 "$file"
  cat "$file"
}

mkdir -p "$SECRETS" "$LOGS"; chmod 700 "$SECRETS"
OWNER_PW="$(secret pg_owner 18)"
API_PW="$(secret api_login 18)"
IDENTITY="$(secret identity 36)"

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  docker run -d --name "$CONTAINER" -e POSTGRES_DB=basho -e POSTGRES_USER=basho \
    -e POSTGRES_PASSWORD="$OWNER_PW" -p "127.0.0.1:$PG_PORT:5432" \
    -v basho-demo-pgdata:/var/lib/postgresql/data postgres:16-alpine >/dev/null
fi
docker start "$CONTAINER" >/dev/null
for _ in $(seq 1 60); do
  docker exec "$CONTAINER" pg_isready -U basho -d basho -h 127.0.0.1 >/dev/null 2>&1 && break
  sleep 1
done

psql_owner() { docker exec -e PGPASSWORD="$OWNER_PW" "$CONTAINER" psql -U basho -h 127.0.0.1 -v ON_ERROR_STOP=1 -qtA "$@"; }
if [[ -z "$(psql_owner -d basho -c "SELECT 1 FROM pg_database WHERE datname='$DB'")" ]]; then
  psql_owner -d basho -c "CREATE DATABASE \"$DB\""
fi

OWNER_URL="postgresql+psycopg://basho:$OWNER_PW@127.0.0.1:$PG_PORT/$DB"
API_URL="postgresql+psycopg://basho_api_login:$API_PW@127.0.0.1:$PG_PORT/$DB"
cd "$ROOT/backend"
uv sync -q
MIGRATION_DATABASE_URL="$OWNER_URL" uv run alembic upgrade head >/dev/null
psql_owner -d "$DB" -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='basho_api_login') THEN CREATE ROLE basho_api_login LOGIN PASSWORD '$API_PW' IN ROLE basho_api; END IF; END \$\$;"

cat > "$ROOT/backend/.env" <<ENV
# Gerado por scripts/demo/up.sh (não versionado). Banco: $DB
DATABASE_URL=$API_URL
MIGRATION_DATABASE_URL=$OWNER_URL
ANTHROPIC_API_KEY=not-configured
FEATHERLESS_API_KEY=not-configured
FEATHERLESS_BASE_URL=https://featherless.invalid/v1
CHECKER_MODEL=checker-not-configured
GITHUB_TOKEN=not-configured
TENANT_ID=$TENANT_ID
REVIEWER_IDENTITY_SECRET=$IDENTITY
ENV
chmod 600 "$ROOT/backend/.env"
uv run python -m basho.demo.seed >/dev/null

stop_port() {  # encerra só o processo que escuta na porta da demo
  local pid
  pid="$(ss -ltnp "sport = :$1" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true)"
  if [[ -n "$pid" ]]; then kill "$pid"; sleep 1; fi
}
stop_port "$API_PORT"
setsid nohup uv run uvicorn basho.main:app --factory --host 127.0.0.1 --port "$API_PORT" \
  > "$LOGS/api.log" 2>&1 < /dev/null &

cd "$ROOT/frontend"
printf 'BASHO_API_URL=http://127.0.0.1:%s\nREVIEWER_IDENTITY_SECRET=%s\n' "$API_PORT" "$IDENTITY" > .env.local
chmod 600 .env.local
[[ -d node_modules ]] || npm ci --no-audit --no-fund >/dev/null
[[ -f .next/BUILD_ID && "${DEMO_REBUILD:-0}" != "1" ]] || npm run build >/dev/null
stop_port "$WEB_PORT"
setsid nohup npx next start -p "$WEB_PORT" -H 127.0.0.1 > "$LOGS/web.log" 2>&1 < /dev/null &

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null && curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$API_PORT/health" >/dev/null || { echo "API não respondeu; veja $LOGS/api.log"; exit 1; }
curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null || { echo "Frontend não respondeu; veja $LOGS/web.log"; exit 1; }
echo "Basho demo no ar: http://127.0.0.1:$WEB_PORT  (API http://127.0.0.1:$API_PORT, banco $DB)"
