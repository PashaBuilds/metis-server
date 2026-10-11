# install.sh ve upgrade.sh ortak yardımcıları (doğrudan çalıştırılmaz).
step() { printf '\n==> %s\n' "$*"; }
bundle_version() { head -n1 "$BUNDLE/VERSION"; }
verify_bundle() {
  step "Paket bütünlüğü doğrulanıyor (SHA256SUMS)"
  (cd "$BUNDLE" && sha256sum --quiet --strict -c SHA256SUMS) || { echo "Paket bütünlüğü bozuk; kurulum durduruldu." >&2; exit 1; }
  echo "  $(wc -l < "$BUNDLE/SHA256SUMS") dosya doğrulandı."
}
install_app_version() {
  local ver="$1" dir="$ROOT/app/$1"
  if [ -f "$dir/.installed" ]; then echo "$dir"; return; fi
  rm -rf "$dir"; mkdir -p "$dir"
  "$PYTHON" -m venv "$dir/venv" >&2
  # --no-index: ağ kullanılmaz; --require-hashes: yalnız kilit dosyasındaki özetlerle eşleşen tekerlekler
  "$dir/venv/bin/python" -m pip install --no-index --find-links "$BUNDLE/wheelhouse" --require-hashes \
      -r "$BUNDLE/requirements.lock" --disable-pip-version-check -q >&2
  cp -r "$BUNDLE/web" "$dir/web"
  echo "$ver" > "$dir/.installed"
  echo "$dir"
}
set_current() { ln -sfn "$1" "$ROOT/app/current.tmp" && mv -Tf "$ROOT/app/current.tmp" "$ROOT/app/current"; echo "  app/current → $1" >&2; }
metis_run() { local dir="$1"; shift; "$dir/venv/bin/python" -m metis.cli "$@"; }
wait_healthy() {
  step "Sağlık kontrolü bekleniyor"
  for _ in $(seq 1 "$2"); do
    if curl -fsS "http://127.0.0.1:$1/api/v1/health/ready" >/dev/null 2>&1; then echo "  hazır"; return 0; fi
    sleep 1
  done
  echo "METIS $2 saniyede hazır olmadı (journalctl -u metis-api)." >&2; return 1
}
write_metis_cmd() {
  mkdir -p "$ROOT/bin"
  printf '#!/bin/sh\nexport METIS_CONFIG=%s\nexec %s -m metis.cli "$@"\n' "$ROOT/config/metis.env" "$ROOT/app/current/venv/bin/python" > "$ROOT/bin/metis"
  chmod 755 "$ROOT/bin/metis"
}
