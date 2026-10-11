#!/usr/bin/env bash
# METIS sunucusunu internetsiz kurar (Linux, systemd). Windows varsayılan hedeftir; bu ikincil yoldur.
#
#   sudo ./install.sh --public-url https://metis.sirket.local \
#        --owner-url postgresql+psycopg://metis_owner:PAROLA@127.0.0.1:5432/metis \
#        --app-url   postgresql+psycopg://metis_app:PAROLA@127.0.0.1:5432/metis
#
# Önkoşul: python3.12 (venv modülüyle) ve PostgreSQL 16; roller/veritabanı KURULUM.md'deki SQL ile hazır.
# Tekrar çalıştırmak güvenlidir: var olan yapılandırma ve ana anahtar korunur.
set -Eeuo pipefail
BUNDLE="$(cd "$(dirname "$0")" && pwd)"
ROOT=/opt/metis; PUBLIC_URL=""; OWNER_URL=""; APP_URL=""; API_PORT=8000; API_WORKERS=2; SLOTS=2
SYSTEMD=1; PYTHON=${PYTHON:-python3.12}; ALLOW_HTTP=0; SERVICE_USER=metis
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2;;
    --public-url) PUBLIC_URL="$2"; shift 2;;
    --owner-url) OWNER_URL="$2"; shift 2;;
    --app-url) APP_URL="$2"; shift 2;;
    --api-port) API_PORT="$2"; shift 2;;
    --no-systemd) SYSTEMD=0; shift;;
    --allow-http) ALLOW_HTTP=1; shift;;
    --user) SERVICE_USER="$2"; shift 2;;
    *) echo "bilinmeyen seçenek: $1" >&2; exit 2;;
  esac
done
. "$BUNDLE/metis-common.sh"

step "METIS kurulumu ($(bundle_version))"
verify_bundle
VERSION=$(bundle_version)
APP_DIR=$(install_app_version "$VERSION")
set_current "$APP_DIR"

mkdir -p "$ROOT/config" "$ROOT/data"
ENV_FILE="$ROOT/config/metis.env"
if [ ! -f "$ENV_FILE" ]; then
  [ -n "$PUBLIC_URL" ] && [ -n "$OWNER_URL" ] && [ -n "$APP_URL" ] || { echo "İlk kurulumda --public-url, --owner-url ve --app-url gerekli." >&2; exit 2; }
  case "$PUBLIC_URL" in https://*) PROFILE=production;; *) [ "$ALLOW_HTTP" = 1 ] || { echo "--public-url https:// ile başlamalı (deneme için --allow-http)." >&2; exit 2; }; PROFILE=development;; esac
  umask 077
  [ -f "$ROOT/config/master.key" ] || "$PYTHON" -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())" > "$ROOT/config/master.key"
  cat > "$ENV_FILE" <<CONF
# METIS yapılandırması — yalnız root ve servis kullanıcısı okuyabilir.
METIS_ENV=$PROFILE
METIS_PUBLIC_URL=$PUBLIC_URL
METIS_DATABASE_URL=$APP_URL
METIS_OWNER_DATABASE_URL=$OWNER_URL
METIS_DATA_DIR=$ROOT/data
METIS_MASTER_KEY_FILE=$ROOT/config/master.key
METIS_STATIC_DIR=$ROOT/app/current/web
METIS_ENDPOINT_ALLOWLIST=
CONF
  umask 022
else
  step "Var olan yapılandırma korunuyor: $ENV_FILE"
fi
export METIS_CONFIG="$ENV_FILE"

step "Veritabanı şeması yükseltiliyor"
metis_run "$APP_DIR" migrate
step "metis doctor"
metis_run "$APP_DIR" doctor || true

if [ "$SYSTEMD" = 1 ]; then
  id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home "$ROOT" --shell /usr/sbin/nologin "$SERVICE_USER"
  chown -R "$SERVICE_USER" "$ROOT/data"; chgrp "$SERVICE_USER" "$ROOT/config" "$ROOT/config"/*; chmod 750 "$ROOT/config"; chmod 640 "$ROOT/config"/*
  for unit in metis-api.service metis-worker.service metis-backup.service metis-backup.timer metis-rehearsal.service metis-rehearsal.timer; do
    sed -e "s#{{ROOT}}#$ROOT#g" -e "s#{{PORT}}#$API_PORT#g" -e "s#{{WORKERS}}#$API_WORKERS#g" -e "s#{{SLOTS}}#$SLOTS#g" -e "s#{{USER}}#$SERVICE_USER#g" "$BUNDLE/$unit" > "/etc/systemd/system/$unit"
  done
  systemctl daemon-reload
  systemctl enable --now metis-api.service metis-worker.service metis-backup.timer metis-rehearsal.timer
  wait_healthy "$API_PORT" 90
fi
write_metis_cmd
step "Kurulum tamamlandı: METIS $VERSION"
echo "İlk yönetici için kurulum kodu:"
metis_run "$APP_DIR" setup-code || true
