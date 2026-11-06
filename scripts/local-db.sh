#!/bin/sh
# Start the local Postgres, apply the Auth/Storage shim, then Outcome migrations.
# Does not touch the live Supabase DATABASE_URL in .env.
set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
url="${LOCAL_DATABASE_URL:-postgresql://outcome:outcome@127.0.0.1:5433/outcome}"

docker compose -f docker-compose.local.yml up -d --wait

psql "$url" -v ON_ERROR_STOP=1 -q -f tests/backend/sql/supabase_local_shim.sql
DATABASE_URL="$url" "$root/.venv/bin/python" -m services.core.migrate

printf '%s\n' "Local database ready at $url"
printf '%s\n' "Run tests with:"
printf '%s\n' "  OUTCOME_TEST_AUTH_MODE=local_jwt DATABASE_URL=$url .venv/bin/python -m pytest tests/backend/test_reply.py -q"
