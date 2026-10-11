# METIS v2 — geliştirme ajanı çalışma kuralları

Bu dosya repodaki geliştirme ajanlarına (Claude Code) yöneliktir; uygulamanın model sistem mesajı değildir.
Tek ürün talimatı kaynağı: `METIS-v2-BRIEF.md`. İlerleme ve kararlar: `docs/PROGRESS.md`.

## Çalışma biçimi
- Kullanıcı eylem istediğinde uygula; rutin, geri alınabilir adımlarda tekrar izin sorma. Kapsamı veya veri güvenliğini etkileyen belirsizliği netleştir.
- Kısa, somut Türkçe. İlerleme mesajında bulgu + sonraki adım; teslimde değişiklik, doğrulama, kalan sınırlar.
- Mock, gerçek model, izole DB ve tarayıcı doğrulamalarını **ayrı** bildir. Test edilmeyen davranışa "çalışıyor" deme.
- Önemli kararları ve doğrulamaları `docs/PROGRESS.md`'de tut. Yerel commit / push / release durumlarını ayır.
- Kullanıcı verisini, kaynak revizyonlarını ve mevcut çalışmayı koru; denemeleri kurgusal veriyle yap. Anahtarları kod, log veya Git'e yazma.
- Yeni oturumda önce `git status` ve `docs/PROGRESS.md`'nin son bölümünü oku; oradan devam et.
- **Git akışı (ürün sahibinin kararı, 2026-10-11):** bu reponun tek push'layanı ajan. PR açma; doğrulanmış değişikliği doğrudan `main`'e commit + push et (oturum başka dal verse bile). Push öncesi hızlı denetimleri (ruff, ilgili pytest, tsc/eslint) yerelde çalıştır; push sonrası `main` CI'ını (Linux + Windows) izle, kırmızıysa hemen düzelt. Geçmişi yeniden yazma (force-push yok).
- **Depo herkese açık (public).** Koda, belgelere, commit mesajlarına ve test verisine şirket adı, gerçek proje/kart adı, kişi adı, e-posta, iç ağ adresi veya gerçek kaynak içeriği yazma; örnek veri kurgusal olmalı. Commit yazarı GitHub noreply e-postası.
- **CI:** public depoda standart Actions dakikaları ücretsiz; yine de değişiklikleri biriktirip tek push yap. Yalnız belge değişikliği CI çalıştırmaz; Windows işi yalnız `deploy/`, `ops/`, `legacy_import/`, `cli.py`, `pdf_extract.py`, `pyproject.toml` değişince, sürüm yayımlarken veya commit mesajında `[windows]` varken koşar. Takılan bir koşu fark edersen kullanıcıya iptal ettir (ajan iptal edemiyor).
- **Sürüm yayımlama:** ajan oturumu etiket (tag) gönderemez. `deploy/RELEASE` dosyasına yeni adı yaz (ör. `v2.0.0-rc.2`; tireli = ön sürüm), `deploy/RELEASE_NOTES.md`'yi güncelle, `main`'e push et; CI Linux + Windows yeşil olunca release işi etiketi ve ZIP'li release'i oluşturur.

## Değişmez ilkeler (brief Bölüm 2 — özet)
İnsan onayı zorunlu (sunucu tarafı yetki) · revizyonlar değişmez (ORM kancası + PG trigger) · onay hash'e bağlı · atomik yayın ·
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

## Kod düzeni
- Backend: `services/metis/modules/<modül>/{router,schemas,service,repo}.py`. `AppError` servis katmanında; HTTP zarfı yalnız `metis.app`'te.
- Şema: `services/metis/core/models.py` + Alembic (`services/metis/migrations`). Yeni tablo/sütun = yeni migration.
- Frontend: `apps/web/src/{app,design,features,lib,i18n}`. Tüm kullanıcı metni `i18n/tr.ts`'te. `any` yasak.
- Tasarım dili "İz": altın (`--iz*`) **yalnız kanıt** için; Plex Sans/Mono; iki tema; 12 px altı yazı yok.
