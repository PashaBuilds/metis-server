#!/usr/bin/env bash
# Kurulu METIS'i bu paketteki sürüme yükseltir: yedek → yanına kurulum → servis durdur → current → migrate → başlat → sağlık.
# Başarısızlıkta önceki sürüme döner. Kullanım: sudo ./upgrade.sh [--root /opt/metis] [--no-systemd] [--api-port 8000]
set -Eeuo pipefail
BUNDLE="$(cd "$(dirname "$0")" && pwd)"
ROOT=/opt/metis; SYSTEMD=1; API_PORT=8000; PYTHON=${PYTHON:-python3.12}; SKIP_BACKUP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2;;
    --no-systemd) SYSTEMD=0; shift;;
    --api-port) API_PORT="$2"; shift 2;;
    --skip-backup) SKIP_BACKUP=1; shift;;
    *) echo "bilinmeyen seçenek: $1" >&2; exit 2;;
  esac
done
. "$BUNDLE/metis-common.sh"
verify_bundle
export METIS_CONFIG="$ROOT/config/metis.env"
[ -f "$METIS_CONFIG" ] || { echo "Kurulu METIS bulunamadı; önce install.sh." >&2; exit 1; }
OLD_DIR=$(readlink -f "$ROOT/app/current")
OLD_VERSION=$(cat "$OLD_DIR/.installed")
NEW_VERSION=$(bundle_version)
step "Yükseltme: $OLD_VERSION → $NEW_VERSION"
[ "$OLD_VERSION" != "$NEW_VERSION" ] || { echo "Bu sürüm zaten kurulu."; exit 0; }
BACKUP=""
if [ "$SKIP_BACKUP" = 0 ]; then
  step "Yükseltme öncesi yedek"
  metis_run "$OLD_DIR" backup > /dev/null
  BACKUP=$("$PYTHON" -c "import json,sys;print(json.load(open(sys.argv[1]))['file'])" "$ROOT/data/backups/last-backup.json")
  echo "  yedek: $BACKUP"
fi
NEW_DIR=$(install_app_version "$NEW_VERSION")
[ "$SYSTEMD" = 1 ] && systemctl stop metis-worker.service metis-api.service
set_current "$NEW_DIR"
MIGRATED=0
rollback() {
  echo "Yükseltme başarısız; önceki sürüme dönülüyor ($OLD_VERSION)." >&2
  [ "$SYSTEMD" = 1 ] && systemctl stop metis-worker.service metis-api.service || true
  set_current "$OLD_DIR"
  if [ "$MIGRATED" = 1 ] && [ -n "$BACKUP" ]; then
    echo "Şema yükseltilmişti; eski sürüm için yedeği boş bir veritabanına geri yükle: metis restore $BACKUP" >&2
  fi
  [ "$SYSTEMD" = 1 ] && systemctl start metis-api.service metis-worker.service || true
  exit 1
}
trap rollback ERR
step "Şema yükseltiliyor"
metis_run "$NEW_DIR" migrate
MIGRATED=1
if [ "$SYSTEMD" = 1 ]; then systemctl start metis-api.service metis-worker.service; wait_healthy "$API_PORT" 90; fi
trap - ERR
step "Eski sürümler temizleniyor (en yeni iki sürüm kalır)"
ls -1dt "$ROOT"/app/*/.installed 2>/dev/null | grep -v "/app/current/" | tail -n +3 | while read -r f; do d=$(dirname "$f"); [ "$d" = "$(readlink -f "$ROOT/app/current")" ] || { rm -rf "$d"; echo "  silindi: $(basename "$d")"; }; done
step "Yükseltme tamamlandı: METIS $NEW_VERSION"
