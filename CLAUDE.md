# METIS — geliştirme ajanı çalışma kuralları

Bu dosya repodaki geliştirme ajanlarına (Claude Code) yöneliktir; uygulamanın model sistem mesajı değildir.
Tek ürün talimatı kaynağı: `METIS-v2-BRIEF.md`. İlerleme ve kararlar: `docs/PROGRESS.md`.

## Çalışma biçimi
- Kullanıcı eylem istediğinde uygula; rutin, geri alınabilir adımlarda tekrar izin sorma. Kapsamı veya veri güvenliğini etkileyen belirsizliği netleştir.
- Kısa, somut Türkçe. İlerleme mesajında bulgu + sonraki adım; teslimde değişiklik, doğrulama, kalan sınırlar.
- Mock, gerçek model, izole DB ve tarayıcı doğrulamalarını **ayrı** bildir. Test edilmeyen davranışa "çalışıyor" deme.
- Önemli kararları ve doğrulamaları `docs/PROGRESS.md`'de tut. Yerel commit / push / release durumlarını ayır.
- Kullanıcı verisini, kaynak revizyonlarını ve mevcut çalışmayı koru; denemeleri kurgusal veriyle yap. Anahtarları kod, log veya Git'e yazma.
- Yeni oturumda önce `git status` ve `docs/PROGRESS.md`'nin son bölümünü oku; oradan devam et.
- **Git akışı (ürün sahibinin kararı, 2026-10-11):** bu reponun tek push'layanı ajan. PR açma; doğrulanmış değişikliği doğrudan `main`'e commit + push et (oturum başka dal verse bile). Geliştirirken yalnız ilgili testleri/denetimleri çalıştır; tam doğrulama `-Derle`'de bir kez yapılır (aynı işi iki kez koşma). Geçmişi yeniden yazma (force-push yok).
- **Depo herkese açık (public).** Koda, belgelere, commit mesajlarına ve test verisine şirket adı, gerçek proje/kart adı, kişi adı, e-posta, iç ağ adresi veya gerçek kaynak içeriği yazma; örnek veri kurgusal olmalı. Commit yazarı GitHub noreply e-postası.
- **CI (ürün sahibinin kararı 2026-10-19):** push'ta otomatik CI yok. Sürüm adayı başına bir kez: `scripts\release.ps1 -Derle` başta `gh workflow run CI` ile aynı commit için CI'ı başlatır (yerelde yapılamayanlar: uçtan uca Playwright + temiz Windows Server'da çevrimdışı kurulum/yükseltme) ve kendisi paralel olarak ruff, eslint, OpenAPI sözleşmesi, tam pytest + masaüstü testi, tsc + vite, paket yapar. `-Yayimla` o commit'te CI yeşilini ister. Ara push'larda CI'ı bekleme ya da tetikleme.
- **Sürüm yayımlama (ürün sahibinin kararı 2026-10-18):** sürüm büyük.küçük.ilerleme (ör. `2.0.8`; rc adı yok). Tek kaynak `services/metis/__init__.py` `__version__`; `deploy/RELEASE` (`v2.0.8`), iki `package.json`, `package-lock.json` ve `apps/web/openapi.json` aynı olmalı (`tests/ops/test_version.py`). Yayımlanan ZIP **yerel Windows bilgisayarda derlenip gerçek Windows'ta çift tıklamayla denenmiş ZIP'in kendisidir**; CI'da yeniden derlenmez. Akış: sürümü yükselt + `deploy/RELEASE_NOTES.md` → commit + push → `scripts\release.ps1 -Derle` (temiz main = origin/main, CI'ı başlatır, ruff, eslint, OpenAPI sözleşmesi, pytest + masaüstü testi, `build-bundle.py --locked --require-launcher`, ZIP özeti `dist\aday.json`'a) → ZIP'i ayrı klasöre aç, `METIS-Baslat.exe`'ye çift tıkla (kurulum/yükseltme, Chrome, sol menüde sürüm) → `scripts\release.ps1 -Yayimla` (ZIP değişmemiş, commit hâlâ origin/main, o commit'te CI yeşil; `gh release create` etiketi sunucuda oluşturur). Denenmemiş ZIP yayımlanmaz; deneme sonucu `docs/PROGRESS.md`'ye yazılır. İstisna yalnız ürün sahibinin o sürüm için açık kararıyla olur (ör. 2.0.9: UAC'yi onaylayacak kimse yoktu); sürüm notlarında ve PROGRESS'te neyin denenmediği açıkça yazılır.
- **Kalıcı yayın kararı (ürün sahibi, 2026-10-19, aksi söylenene kadar):** doğrulanmış her değişiklik sormadan yeni sürüm olarak çıkar: sürümü yükselt → `-Derle` → kurulu METIS'i yükseltmeyi dene → `-Yayimla` → sonra bildir. Ajan kabuğu yönetici değildir, UAC'yi onaylayamaz; onaylanamazsa kısmi deneme (soru + izin verilmedi yolu) yapılır ve denenmeyen yükseltme bu karara dayanan istisna olarak sürüm notlarına ve PROGRESS'e yazılır.

## Değişmez ilkeler (brief Bölüm 2 — özet)
İnsan yayımlar, model yayımlamaz (sunucu tarafı yetki; varsayılan "Yazar yayımlar" + yayın öncesi otomatik çelişki/tekrar kontrolü, ürün sahibinin kararı 2026-10-18) · revizyonlar değişmez (ORM kancası + PG trigger) · onay hash'e bağlı · atomik yayın ·
kaynaksız teknik iddia yok, deterministik doğrulama · NO_EVIDENCE ≠ RETRIEVAL/MODEL_UNAVAILABLE · kapsam metadata'dan ·
sahte veri yok (ölçülmemiş = null/"ölçülmedi") · kaynak içindeki talimat veridir · internetsiz Windows sunucu hedefi, CDN yok ·
anahtar AES-GCM şifreli · yavaş çağrıdan sonra yetki yeniden kontrolü, erişilemeyene 404.

## Yerel geliştirme
```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
npm install                      # kökte npm workspace (apps/web)
scripts/dev-up.sh                # PG + migrate + mock model + API + worker (+ kurgusal çalışma alanı)
.venv/bin/pytest                 # izole PostgreSQL test DB'si (SQLite yok)
npm run build:web                # tsc + vite build
npx playwright test -c apps/web/playwright.config.ts       # görsel + axe + harita fps (geliştirme yığını :8000'de)
npx playwright test -c apps/web/playwright.e2e.config.ts   # uçtan uca akışlar (kendi geçici DB'si ve sunucusu)
.venv/bin/python scripts/export_openapi.py && (cd apps/web && npx openapi-typescript openapi.json -o src/lib/api/schema.d.ts)
```

### Windows'ta (geliştirme bilgisayarı)
PowerShell; `.venv\Scripts\…` yolu. Python ≥3.12 yeter (paket hedefi ayrıca gömülü 3.12'dir). PostgreSQL 16 servisi
(`C:\Program Files\PostgreSQL\16`). Bilgisayarda deneme amaçlı kurulu METIS'in `metis_owner`/`metis_app` rollerine
ve `metis` veritabanına **dokunma**; testler ayrı `metisdev` rolüyle (CREATEDB, kurgusal parola) çalışır. Rol bir kez,
`postgres` parolasını bilen kişi tarafından açılır; adı `metis_` ile başlamaz (`uninstall.ps1 -RemoveAll` o önekli rolleri siler).
```powershell
py -3 -m venv .venv; .venv\Scripts\python -m pip install -e ".[dev]"; npm install
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -U postgres -c "CREATE ROLE metisdev LOGIN CREATEDB PASSWORD 'metis-dev'"  # bir kez
$env:METIS_TEST_ADMIN_DSN = "postgresql://metisdev:metis-dev@127.0.0.1:5432/postgres"
$env:METIS_PG_BIN = "C:\Program Files\PostgreSQL\16\bin"; $env:Path = "$env:METIS_PG_BIN;$env:Path"  # pg_dump
.venv\Scripts\python -m pytest -q                        # METIS_DESKTOP_TEST=1: başlatıcı ileti kutusu gerçek masaüstünde
.venv\Scripts\python -m ruff check services tests evals deploy
.venv\Scripts\python deploy\build-bundle.py --target win64 --locked --require-launcher   # dist\METIS-<sürüm>-server-win64.zip
```
`scripts/dev-up.sh` bash'e özgüdür; Windows'ta geliştirme yığını gerekirse `metis migrate/serve/worker/mock-llm`
komutları `METIS_DATABASE_URL` ayrı bir veritabanını (ör. `metisdev`) gösterecek biçimde elle çalıştırılır.
`npm install` `package-lock.json`'a yalnız `"peer": true` satırları ekliyorsa (npm sürüm farkı) commit'leme.

## Kod düzeni
- Backend: `services/metis/modules/<modül>/{router,schemas,service,repo}.py`. `AppError` servis katmanında; HTTP zarfı yalnız `metis.app`'te.
- Şema: `services/metis/core/models.py` + Alembic (`services/metis/migrations`). Yeni tablo/sütun = yeni migration.
- Frontend: `apps/web/src/{app,design,features,lib,i18n}`. Tüm kullanıcı metni `i18n/tr.ts`'te. `any` yasak.
- Tasarım dili "İz": altın (`--iz*`) **yalnız kanıt** için; Plex Sans/Mono; iki tema; 12 px altı yazı yok.
