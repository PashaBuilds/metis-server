#!/usr/bin/env bash
# Geliştirme ortamını ayağa kaldırır: PostgreSQL, migrate, kurgusal model, API, worker.
# Kullanım: scripts/dev-up.sh [--demo]   (--demo: kurgusal çalışma alanını oluşturur)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data
export METIS_ENV=${METIS_ENV:-development}
export METIS_DATABASE_URL=${METIS_DATABASE_URL:-postgresql+psycopg://metis_owner:metis-dev@127.0.0.1:5432/metis}
export METIS_STATIC_DIR=${METIS_STATIC_DIR:-apps/web/dist}
if [ ! -f .data/master.key ]; then .venv/bin/python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())" > .data/master.key; fi
export METIS_MASTER_KEY_FILE=${METIS_MASTER_KEY_FILE:-$PWD/.data/master.key}

if command -v pg_ctlcluster >/dev/null 2>&1; then pg_ctlcluster 16 main start 2>/dev/null || true; fi
.venv/bin/metis migrate
[ -d apps/web/dist ] || npm run build:web

pkill -f "[m]etis mock-llm" 2>/dev/null || true
pkill -f "[m]etis serve" 2>/dev/null || true
pkill -f "[m]etis worker" 2>/dev/null || true
nohup .venv/bin/metis mock-llm --port 9100 > .data/mock-llm.log 2>&1 &
nohup .venv/bin/metis serve --port 8000 --workers 1 > .data/serve.log 2>&1 &
nohup .venv/bin/metis worker > .data/worker.log 2>&1 &
sleep 3
if [ "${1:-}" = "--demo" ]; then .venv/bin/metis demo; fi
curl -s http://127.0.0.1:8000/api/v1/health/ready; echo
echo "METIS: http://localhost:8000   (Vite geliştirme sunucusu için: npm run dev -w @metis/web → http://localhost:5173)"
