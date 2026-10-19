#!/usr/bin/env bash
# Uçtan uca testler için izole sunucu: boş metis_e2e veritabanı, geçici veri dizini, port 8001.
# Ayrıca kurgusal model (mock-llm, :9102) ve Metis worker arka planda çalışır; çıkışta hepsi kapatılır.
# Playwright (apps/web/playwright.e2e.config.ts) webServer olarak çalıştırır.
# Testlerin aynı ortamla `metis setup-code` çalıştırabilmesi için ortam değişkenleri
# ${METIS_E2E_ENV_FILE:-/tmp/metis-e2e.env} dosyasına yazılır.
set -euo pipefail
cd "$(dirname "$0")/.."

# Yönetici bağlantısı testlerle aynı (METIS_TEST_ADMIN_DSN); `su postgres` gerekmez (CI'da etkileşimli parola sorar).
ADMIN_DSN=${METIS_TEST_ADMIN_DSN:-postgresql://metis_owner:metis-dev@127.0.0.1:5432/postgres}
psql "$ADMIN_DSN" -q -v ON_ERROR_STOP=1 -c 'DROP DATABASE IF EXISTS metis_e2e WITH (FORCE)' -c 'CREATE DATABASE metis_e2e OWNER metis_owner' < /dev/null

DATA_DIR=$(mktemp -d -t metis-e2e-XXXXXX)
export METIS_ENV=development
export METIS_DATABASE_URL=postgresql+psycopg://metis_owner:metis-dev@127.0.0.1:5432/metis_e2e
export METIS_DATA_DIR="$DATA_DIR"
export METIS_MASTER_KEY
METIS_MASTER_KEY=$(.venv/bin/python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
export METIS_PUBLIC_URL=http://localhost:8001
export METIS_STATIC_DIR=apps/web/dist
# Boş: kurgusal model (:9102) bilerek sunucu ayarında yok; e2e, yöneticinin adrese arayüzden izin vermesini de sınar.
# (9100 yazılmamalı: `metis demo` o adresi izinli görürse kendi kurgusal sağlayıcısını da ekler.)
export METIS_ENDPOINT_ALLOWLIST=

ENV_FILE=${METIS_E2E_ENV_FILE:-/tmp/metis-e2e.env}
umask 077
cat > "$ENV_FILE" <<ENV
METIS_ENV=$METIS_ENV
METIS_DATABASE_URL=$METIS_DATABASE_URL
METIS_DATA_DIR=$METIS_DATA_DIR
METIS_MASTER_KEY=$METIS_MASTER_KEY
METIS_PUBLIC_URL=$METIS_PUBLIC_URL
METIS_STATIC_DIR=$METIS_STATIC_DIR
METIS_ENDPOINT_ALLOWLIST=$METIS_ENDPOINT_ALLOWLIST
ENV

.venv/bin/metis migrate

PIDS=()
cleanup() {
  trap - EXIT INT TERM
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

.venv/bin/metis mock-llm --port 9102 > "$DATA_DIR/mock-llm.log" 2>&1 &
PIDS+=($!)
.venv/bin/metis worker > "$DATA_DIR/worker.log" 2>&1 &
PIDS+=($!)
.venv/bin/metis serve --port 8001 --workers 1 &
PIDS+=($!)
wait -n "${PIDS[@]}"

