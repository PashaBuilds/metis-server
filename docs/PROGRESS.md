# METIS v2 — ilerleme kaydı

Yeni oturum buradan devam eder: son "Durum" bölümüne ve en alttaki "Sıradaki iş"e bak.
Doğrulama türleri ayrı yazılır: **izole DB** (pytest + gerçek PostgreSQL 16), **mock model**, **tarayıcı** (Playwright/Chromium + axe), **canlı model**, **gerçek ortam**.

## Altyapı varsayılanları (brief Bölüm 11 — sorulmadan uygulandı)

| # | Konu | Uygulanan varsayılan | Değiştirme |
|---|---|---|---|
| 1 | Sunucu OS | Windows Server (WinSW servisleri); Linux systemd birimleri ikincil | `deploy/linux/` |
| 2 | Kimlik | Yerel hesaplar (scrypt); `AuthProvider` arayüzü LDAP için hazır | `metis.modules.auth.provider` |
| 3 | PostgreSQL | Aynı sunucuda METIS'e ayrılmış native PG 16 servisi; betik EDB kurucusunu çalıştırmaz, talimat verir | `METIS_DATABASE_URL` |
| 4 | TLS | IIS/ARR ters vekil + şirket sertifikası; METIS 127.0.0.1'de dinler | `docs/KURULUM.md` |
| 5 | Kapasite | 25 kullanıcı, 2 API süreci, 1 worker (2 slot) | servis XML / `--workers` |

## Kararlar
- **Python 3.12**, FastAPI senkron uçlar (thread pool) + SQLAlchemy 2 + psycopg 3. Mentor akışı SSE.
- **Tek şema dosyası** `services/metis/core/models.py`; ilk migration tüm tabloları kurar (`0001`), `0002` çalışma zamanı rol yetkileri (v1 ADR-003: `metis_owner` yalnız migration, `metis_app` çalışma zamanı).
- Değişmez tablolar: `source_revisions, evidence, page_revisions, claims, claim_evidence, relation_revisions, relation_revision_evidence, reviews, publications, publication_pages, publication_relations, audit_events` — PG `BEFORE UPDATE OR DELETE` trigger'ı (`METIS_IMMUTABLE`) + ORM `before_flush` kancası.
- Hata zarfı `{error:{code,message,retryable,correlation_id,details}}`; Türkçe metin frontend `i18n/tr.ts`.
- Oturum: HttpOnly + SameSite=Strict cookie (+ HTTPS'te Secure), CSRF başlığı, Origin allowlist (`METIS_PUBLIC_URL`), Host doğrulaması. Giriş hız sınırı DB'de (`login_attempts`).
- Frontend kökte npm workspace (`apps/web`), Playwright testleri `tests/e2e`, `tests/visual` altında; `@playwright/test` 1.56.1'e sabit (yüklü Chromium 1194 ile eşleşir). TypeScript 5.9 (openapi-typescript peer sınırı).
- Tema kapsamlı sınıflar (`.theme-light/.theme-dark`) vitrinde iki temayı yan yana göstermek için tokens.css'e eklendi.
- İz çizgisi: işaretin altındaki satır aralığından geçer (metnin üzerinden geçmez), 45° pahlı ortogonal yol, uçlarda via halkası.

## Faz durumu

### Faz 0 — İskelet ve tasarım vitrini — TAMAMLANDI
Yapılanlar: repo yapısı, `CLAUDE.md`, ruff/eslint/tsc, Alembic (0001, 0002), pytest + gerçek PG fixture (oturum başına geçici DB, test başına TRUNCATE), Playwright + axe; `tokens.css` (iki tema), IBM Plex Sans/Mono `latin` + `latin-ext`; primitive'ler (Button, IconButton, Chip, StatusBadge, Input, Textarea, Select, Checkbox, Tabs, Segmented, Dialog, ConfirmDialog, Drawer, Toast+Geri al, Tooltip, Skeleton, EmptyState, List/Row, Kbd, Section); kabuk (daraltılabilir ray, üst çubuk, proje seçici, kapsam çubuğu, komut paleti Ctrl/Cmd+K ve `/`, tema, mobil sekme çubuğu + çekmece); İz prototipi (via → İz paneli → animasyonlu iz, kanıt şeridi); `/_vitrin` (yalnız geliştirme profili).

Kabul ölçütleri:
- Vitrin iki temada axe AA temiz — **doğrulandı (tarayıcı)**: `tests/visual/vitrin.spec.ts`, açık ve koyu sistem teması, wcag2a/2aa/21aa, 0 ihlal (sayfa her iki tema örneğini birlikte içerir).
- 1366/1920/390 ekran görüntüleri `docs/design/` — **doğrulandı (tarayıcı)**: `vitrin-1366.png`, `vitrin-1920.png`, `vitrin-390.png`, `iz-prototip-1440.png`, `iz-prototip-390.png`; üç genişlikte yatay kaydırma yok.
- İz çizgisi klavye ve reduced-motion ile — **doğrulandı (tarayıcı)**: Tab+Enter açar, Esc kapatır ve odak işarete döner; reduced-motion'da `animation-name: none`.
- Türkçe glif — **doğrulandı (tarayıcı)**: `document.fonts.check` ğşıİĞŞüöç Plex Sans ve Mono için true. 12 px altı yazı yok — **doğrulandı (tarayıcı)**.
- Backend temel: 26 pytest (**izole DB**): sağlık, güvenlik başlıkları, Host/Origin/CSRF, kurulum kodu tek kullanım, giriş hız sınırı, zorunlu parola değişimi, audit trigger + ORM kancası, kapsam semantiği property testleri.

### Faz 1 — Kimlik, proje, kapsam, kaynak — TAMAMLANDI
- Kurulum kodu (tek kullanımlık, 24 sa), giriş/çıkış, CSRF, roller (rol başına satır; steward ⊇ reviewer+contributor), üyeler, kapsam kataloğu (ekle/sil, '*' ayrılmış), kaynak + revizyon (`expected_revision` → 409), allowlist + magic byte + 10 MB, sandbox PDF çıkarımı (alt süreç, 8 sn, bellek 512 MB: POSIX'te RLIMIT_AS, Windows'ta Job Object; sınır uygulanamazsa çıkarım yapılmaz), sayfa başına kanıt, SHA-256 blob deposu, ACL.
- Kabul: yetki matrisi rol×uç (11 uç × 5 rol, **izole DB**); immutability trigger (source_revisions, evidence; **izole DB**); PDF zaman ve bellek limiti (**izole DB/alt süreç**); e2e kurulum→giriş→kaynak→taslak→inceleme→yayın→İz paneli (**tarayıcı**, `tests/e2e/setup-source-iz.spec.ts`).

### Faz 2 — Katkı, inceleme, yayın — TAMAMLANDI
- Elle taslak, iddia↔alıntı bağlama (kaynak metninde seçim), iddia bazlı diff, hash'e bağlı inceleme, bağımsız/owner_review politikası, atomik yayın, geri çekme, yeniden temellendirme, soft delete + geri al.
- Kabul: onaydan sonra içerik değişince yayın reddi (HASH_MISMATCH), eşzamanlı düzenlemede 409, yayın ortasında hata → eski yayın aktif (fault-injection), worker kimliği onay/yayın/geri çekme yapamaz (**izole DB**); e2e tam akış (düzeltme iste → düzenle → onay → yayın → sil/geri al → geri çek) (**tarayıcı**, `tests/e2e/review-flow.spec.ts`).
- Alt ajanın bulduğu hata düzeltildi: bağımsız politikada `requester_id` NULL olunca "İncelemeni bekleyenler" boş kalıyordu (NULL-güvenli filtre + regresyon testi).

### Faz 3 — Bilgi havuzu, bilgi sayfası, arama — TAMAMLANDI
- Domain/satır listesi, URL + sunucuda kalıcı filtreler, bilgi sayfası (kanıt şeridi, ●n → İz paneli, TOC scroll-spy, geçmiş + karşılaştırma, sorun bildir, geri çek/sil), FTS simple+turkish, birebir sembol, domain paketi alias'ları, pg_trgm bulanık sembol, komut paleti araması.
- Kabul: "kesmeler"→"kesme", `XAxiPcie_IntrEnable`/`INIT_BUS` birebir, "interrupt"/"ISR"→"Kesme yönetimi", erişilemeyen sayfa arama/liste/sayım/ilişki/doğrudan erişimde sızmıyor (**izole DB**).

### Faz 4 — Model gateway ve kaynaklı mentor — TAMAMLANDI (canlı model doğrulanmadı)
- Sağlayıcı/model (AES-GCM anahtar, UI'da yalnız "tanımlı"), SSRF allowlist + ağ kontrolü, probe → transport profili (json_schema / json_object / prompt_only, thinking disabled/not_supported), `model_calls` logu, doğrulanan cache, DB semaforu, devre kesici. Mentor hattı 5.6 (8 karar, SSE, yetki yeniden kontrolü, sessiz fallback yok, cevaptan taslak önerisi).
- Kabul: `evals/` mock modda **%100** (26 kanıt + 27 worker + 15 açıklama-doğrulayıcı vakası; **mock**, deterministik referans model — model kalitesi değildir); RETRIEVAL_UNAVAILABLE ≠ NO_EVIDENCE; model çağrısı sırasında yetki iptali → 403, cevap kaydedilmez; sessiz fallback yok (seçilen model bozulunca ikinci uygun model çağrılmaz, alternatif önerilir) (**izole DB + mock**). Canlı model: **doğrulanmadı** (bu ortamda şirket modeli yok); `python evals/run.py --mode live ...` ile ayrı raporlanacak.

### Faz 5 — Metis worker — TAMAMLANDI
- Kuyruk (SKIP LOCKED, lease/fence/attempt ≤3, öncelik, ayrı benchmark slotu), SSE (Last-Event-ID), extract→retrieve→compare→judge→relate, awaiting_input (kapsam cevabı insanın yeni kaynak revizyonu olur), refine_draft, bakım/denetim görevleri.
- Kabul: lease dolunca başka worker devam eder ve eski worker yazamaz; iptal fence'i artırır; aynı kaynak iki kez → tek taslak; bütçe aşımı kısmi sonucu korur; çıktı yalnız draft/in_review (**izole DB + mock**).

### Faz 6 — Bilgi sağlığı ve çelişki çözümü — TAMAMLANDI
- Bulgular (çelişki, kaynak değişti, inceleme zamanı, kırık referans, sahipsiz sayfa, bildirilen), deterministik bakım taraması, tek zamanlayıcı, çözüm seçenekleri → incelemeye giden `resolution` kaydı, yayında otomatik bulgu kapanışı.
- Kabul: kaynak yeni revizyonunda bağlı sayfa `dependency_changed` + bulgu ve mentor kullanmaz; çözüm kaydı onaysız yayımlanamaz (**izole DB**).

### Faz 7 — Kavram haritası — TAMAMLANDI
- `GET /projects/{pid}/map` (odak, derinlik 1–3, ilişki türü ve kapsam filtresi, kesilme bilgisi); ilişki önerileri incelemeden geçmeden haritada görünmez. Geliştirme için `metis demo-graph --nodes 200` (200 düğüm / 300 kenar, normal katkı→inceleme→yayın akışıyla).
- Kabul: erişilemeyen düğüm ve kenarı görünmüyor; odak/derinlik/ilişki filtresi; öneri incelemeden önce canlı değil (**izole DB**, `tests/api/test_phase7_map.py`). 200 düğüm fps ve liste görünümü axe: UI ile ölçülecek.

### Faz 8 — Model laboratuvarı — TAMAMLANDI
- Sağlayıcı/model yönetimi, probe, ortak benchmark (26 vaka, ayrı benchmark slotu), sonuç temizleme, geçmiş, yeterlilik ve deterministik yönlendirme (kalite kapısı → gecikme).
- Kabul: kritik hata (uydurma sayı, sahte kaynak, kapsam ihlali) yüksek ortalamaya rağmen eler; n<30 için p95 "yetersiz örnek"; temizleme kalıcı ve yeterliliği düşürür; devre kesici yönlendirmeyi engeller; yönlendirme deterministik (**izole DB + mock**, `tests/api/test_phase8_lab.py`). Kurgusal referans model 26/26.

### Faz 4–8 ekranları — TAMAMLANDI (alt ajan yazdı, lider doğruladı)
- Mentor (SSE, model seçici, detay düzeyi, via ateşlenmesi 40 ms, alıntı kartları, İz paneli, karar durumları, cevaptan taslak `/katki?answer=`), ana sayfa model seçici (`mentor_model_id`), Görevler (iki görev kartı, SSE canlı detay, soru cevaplama, teknik ayrıntılar), Bilgi sağlığı (açık/çözülen, türe göre, eylemler, "Şimdi denetle", çelişkiden çözüme), Kavram haritası (xyflow + elk web worker, PCB düğümleri, mürekkep izler, liste görünümü, klavye, minimap, "Tümünü göster"), Model laboratuvarı (sağlayıcı, tablo, seç/test/benchmark/temizle, geçmiş, kalite–gecikme grafiği), Ayarlar ek sekmeleri (Bakım planı, Sistem durumu, Dışa aktar, v0.5.5 aktarımı).
- Lider doğrulaması (kendi koşuları): `tsc -b` ve `eslint` 0 hata; e2e **5/5** (kurulum, inceleme, mentor akışı + uygun olmayan model, çelişkiden çözüme + SSE denetim; `metis_e2e`, mock :9102 + worker); görsel **14/14** (vitrin + harita); harita 200 düğüm **medyan 59.9 fps** (ortalama 55, en yavaş %10 59.5; hedef 60, eşik 30); axe AA iki temada (harita liste görünümü dahil). Son ekran görüntüleri `docs/design/final/` (28 dosya) incelendi.
- Alt ajanın raporladığı ve düzeltilen backend hataları: (1) CONFLICTING cevapta ilgili tüm sayfalar "açık çelişki" işaretleniyordu → yalnız bulgunun sayfaları (regresyon testi); (2) kurgusal tohum ile kural taraması farklı çelişki parmak izi kullanıyordu → tek `conflict_fingerprint` (regresyon testi eski kodla 2≠1 ile kırmızı); (3) görsel Playwright config e2e spec'lerini de eşliyordu → yalnız `tests/visual`.
- CI'da yakalanan: PDF bellek sınırında `cryptography` başlatma hatası `parse_error` diye raporlanıyordu → bellek/kaynak hatası olarak sınıflandırılıyor; test 20 MB'a indirildi (35–45 MB makineye göre bazen yetiyor).
- CI Windows işinde bulunan: Windows'ta PDF çıkarımına bellek sınırı uygulanmıyordu (yalnız zaman sınırı) → alt süreç kendini bellek sınırlı bir Job Object'e atar; uygulanamazsa kapalı başarısızlık (`sandbox_unavailable`, birim testi). Windows davranışı yalnız CI'da doğrulanır.
- CI Linux işinde bulunan: satır içi `code` 0.92em ile 12 px metinde 11.04 px oluyordu → `max(12px, 0.92em)`. Vitrin 12 px testi tembel yüklenen içerikten önce taradığı için yerelde boşta geçiyordu → içeriği bekliyor; yeni `tests/visual/min-font.spec.ts` 12 ana ekranı + bir bilgi sayfasını tarıyor (13/13).
- **CI'da bulunan veri bütünlüğü hatası:** istek oturumunun commit'i FastAPI'nin varsayılan "request" kapsamında yanıt **gönderildikten sonra** çalışıyordu. Sonuç: (a) hemen ardından gelen okuma eski veriyi görebiliyordu (Lab'da "Devre dışı bırak" sonrası liste eski kaldı; e2e iz kaydıyla doğrulandı: PATCH `enabled:false` döndü, 48 ms sonraki GET `true`), (b) commit hatası olsa bile istemci 2xx alıyordu. Düzeltme: 91 uçta `Depends(get_db, scope="function")` → commit/rollback yanıttan önce. Regresyon testi (`test_commit_happens_before_response_is_sent`) eski kodda 204 ile kırmızı, düzeltmeyle 500.
- Kararsızlık: harita liste görünümü axe (açık tema) bir kez, eşzamanlı yük altında kırmızı oldu (9 koşuda 1). Tekrarlanamadı; animasyonlar bitmeden ölçüm hipoteziyle test sonlu animasyonların bitmesini bekleyecek şekilde sağlamlaştırıldı. Kök neden kesin değil.

### Faz 9 — v0.5.5 verisinin taşınması — TAMAMLANDI (gerçek yedekle tatbikat yapılmadı)
- `metis import-v1 <yedek> [--dry-run] [--report-dir]`: parola etkileşimli; şifre çözme + doğrulama (`legacy_import/archive.py`), bellekte plan (`transform.py`), plan doğrulaması + rapor, tek transaction'lı apply + gerçek servislerle ikinci doğrulama (`runner.py`). ADR: `docs/adr/v2-ADR-002-legacy-import.md`.
- Uçlar: `GET /legacy-import/runs`, `GET /legacy-import/runs/{id}` (yönetici); `GET /projects/{pid}/export.zip` (Markdown ZIP: sayfalar + index.md + kaynaklar.md).
- Sentetik yedek üretici `tests/legacy_import/synthetic.py` (v1 kodu çalıştırılmadan; PyCryptodome ile v1 biçimleri).
- Kabul (**izole DB**, 22 test): dry-run ve apply raporu birebir aynı (parmak izi eşit; CLI ile de denendi); yayın↔onay 5/5, aktif 3 sayfa ve 4/4 iddia kanıta bağlı, silinmiş/geri çekilmiş görünmüyor; eski parola ile giriş + yeniden hash; ●n doğru kaynak ve konuma gidiyor; owner_review korunuyor; arama yeniden kuruluyor; sağlayıcı anahtarı `v2:` ile yeniden şifreli, düz metin `pg_dump` çıktısında/raporlarda/loglarda/blob dizininde yok; hata vakaları (yanlış parola, bozuk tag, bozuk gövde, ZIP değil, eksik blob, hash uyuşmazlığı, yanlış kurtarma anahtarı, dolu DB, ikinci apply, manifestte path traversal ×5, arşivde traversal girdileri, yazma sırasında hata) "Hiçbir şey değiştirilmedi" ve tablo sayıları + blob dizini değişmeden.
- **Gerçek ortam: yapılmadı** — ürün sahibinin v0.5.5 yedeği bu ortamda yok. v0.5.5 kaynağında tanımı olmayan iki biçim (kapsam kataloğu ayarı, ilişki alan adları) toleranslı okunuyor; raporun "atlanan" ve "notlar" bölümü farkı gösterir.
- Bulunup düzeltilen: legacy konum metni (`"PDF · sayfa 4 · tablo 2"`) etikette kayboluyordu → `locator.raw` varsa özgün metin gösterilir.

### Faz 10 — Sunucu kurulum paketi — TAMAMLANDI (gerçek Windows'ta çalıştırılmadı)
- `metis doctor` (10 denetim, kritik/kritik değil), `metis backup` (pg_dump -Fc + bloblar + manifest; ana anahtar değil parmak izi; üzerine yazmaz; `last-backup.json`; `--keep-days`), `metis restore <arşiv|latest>` (yalnız boş DB, anahtar parmak izi, özet doğrulama), `--rehearsal` (geçici DB'ye yükle → satır sayıları + bloblar → sil). Kod: `services/metis/ops/`.
- `deploy/build-bundle.py` → `dist/METIS-<sürüm>-server-win64.zip` (35 MB): gömülü Python 3.12.10, pip zipapp, hash-kilitli wheelhouse (`deploy/locks/win64.lock`, hedef platform işaretleriyle tamamlanır), web, WinSW 2.12, `install-offline.ps1`, `upgrade.ps1`, `metis-common.ps1`, servis XML'leri, `iis-web.config`, `BASLA.txt`, `KURULUM.md`, `SHA256SUMS`. Dış ikililer sabit sürüm + sabit SHA-256. Linux eşdeğeri (`--target linux64`, systemd birimleri, `install.sh`/`upgrade.sh`).
- `docs/KURULUM.md` (Türkçe, adım adım: PG16 EDB, paket doğrulama, kurulum, IIS/ARR + TLS + SSE ayarı, ilk yönetici, model, yedek/geri yükleme, yükseltme, v0.5.5 aktarımı, sorun giderme).
- `.github/workflows/ci.yml`: Linux (ruff, OpenAPI diff, pytest PG16, evals mock, tsc/eslint/build, Playwright vitrin + e2e), Windows 2022 (pytest + PG servisi, paket üretimi, **ağ kapalı adımda** ZIP'ten kurulum, giriş, yeniden başlatma sonrası kalıcılık, yedek, tatbikat, `upgrade.ps1`), etikette tek ZIP release.
- Kabul:
  - Yedek → boş DB'ye geri yükleme turu, tatbikat, kurcalanmış arşiv reddi, başka ana anahtar reddi, doctor — **doğrulandı (izole DB + gerçek pg_dump/pg_restore 16)**, `tests/ops` 6 test.
  - Paketten internetsiz kurulum → migrate → doctor → API ayakta → kurulum + veri → yeniden başlatma sonrası veri kalıcı → yedek + tatbikat → yükseltme (2 sürüm saklama) → yükseltme hatasında geri dönüş — **doğrulandı (Linux paketiyle, bu ortamda)**. Bu sırada bulunan iki hata düzeltildi: temizlik `current`'ı sayıp önceki sürümü siliyordu; ERR trap fonksiyon içinde tetiklenmiyordu (`set -E`).
  - Windows paketi: üretildi; `SHA256SUMS` doğrulaması PowerShell 7'de (bozuk dosya reddi dahil) ve tüm `.ps1` dosyalarının sözdizimi doğrulandı; `.ps1` UTF-8 BOM'lu (PS 5.1). `pip download --platform` Windows'a özgü bağımlılığı (`tzdata`, psycopg) atlıyordu → hedef ortam işaretleriyle tamamlama eklendi.
  - **Windows CI (Windows Server 2022 runner, PG16 choco) — doğrulandı** (PR #1, 25c30d9): pytest (api, legacy_import, ops), paket üretimi, ağ kapalı adımda (`HTTP(S)_PROXY=127.0.0.1:9`, `PIP_NO_INDEX`) ZIP'ten kurulum, ilk yönetici + kaynak, `Restart-Service` sonrası veri kalıcı, `metis backup`, `restore --rehearsal latest`, `upgrade.ps1` 2.0.0 → 2.0.0+ci2 (yedek → migrate → sağlık → doctor 10/10).
  - Windows CI'da bulunan ve düzeltilen: `npm.cmd` bulunamıyordu (`shutil.which`); `Install-AppVersion` pip çıktısını dönüşe karıştırıyordu (junction kurulamıyordu); `metis doctor` cp1252 konsolda UnicodeEncodeError (stdout/stderr UTF-8); yerel sağlık kontrolü `HTTP_PROXY`'ye gidiyordu (vekilsiz HttpClient); WinSW `stop` eşzamansız → yükseltmede `start` boşa düşüp API kapalı kalıyordu (geri dönüş doğru çalıştı); Stop/Start artık Stopped/Running bekliyor.
  - Sınır: CI kurulumu `-AllowHttp` (geliştirme profili); üretim profili + IIS/ARR + TLS Windows'ta denenmedi. **Gerçek şirket sunucusunda kurulum: yapılmadı.**

## Sıradaki iş
Teslim yazıldı (`docs/TESLIM.md`). PR #1 CI'ı Linux + Windows yeşil (ed2a68c) ve `main`'e birleştirildi (6b8036b).
Karar (ürün sahibi, 2026-10-11): bundan sonra PR açılmaz; değişiklikler doğrudan `main`'e push edilir (ayrıntı `CLAUDE.md` → Git akışı). Gerçek ortam doğrulamaları (Windows sunucu, şirket modeli, gerçek v0.5.5 yedeği) ürün sahibinde.

### Deneme kurulumu ve ön sürüm (2026-10-11)
- `deploy/windows/uninstall.ps1`: varsayılan kaldırma servisleri, zamanlanmış görevleri ve program dosyalarını siler; ayarları, ana anahtarı, verileri ve veritabanını korur. `-RemoveAll` veritabanını, rolleri ve `C:\METIS`'i de siler.
- CI Windows işine eklendi: `metis demo` (kurgusal çalışma alanı, giriş + sayfa kontrolü) ve iki aşamalı kaldırma testi.
- `KURULUM.md`: "12. Kaldırma" ve "Ek: Kendi bilgisayarında deneme" (Windows 10/11, `-AllowHttp`, IIS yok). Windows 10/11 masaüstünde **denenmedi**; senaryo CI'da Windows Server 2022'de koşuyor.
- Release işi: tire içeren etiketler (`v2.0.0-rc.1`) ön sürüm (pre-release) olarak yayımlanır.
- CI kaldırma testi ilk koşuda takıldı: `Invoke-Psql` bitince `PGPASSWORD`'u silip çağıranın değerini bozuyordu, sonraki `psql` parola sorup bekledi. Önceki değer geri konuyor, `psql -w`; CI işlerine zaman sınırı (Linux 45, Windows 90, kaldırma adımı 10 dk). 0baad88'de Linux + Windows yeşil (kaldırma dahil).
- Etiket gönderimi bu oturumda 403 (yalnız dal gönderimi açık). Release artık `deploy/RELEASE` ile tetikleniyor: `main`'de CI yeşil olunca etiket + release GitHub jetonuyla oluşur. İlk ön sürüm: `v2.0.0-rc.1`.
- Actions kotası %90'a ulaştı (1.836/2.000 dk; takılan koşu büyük pay). CI daraltıldı: belge değişikliği tetiklemez, eski koşu iptal edilir (concurrency), Windows işi yalnız ilgili değişikliklerde / sürümde / `[windows]` ile / elle.

### Public depoya geçiş (2026-10-11)
- Bu depo (`metis-server`), özel geliştirme deposundan **temiz geçmişle** (tek başlangıç commit'i) başlatıldı; yukarıdaki commit kısaltmaları ve "PR #1" o özel depoya aittir.
- Çıkarılanlar: şirket adı, `reference/v0.5.5/` (önceki sürümün kaynakları; özel arşivde), belgelerdeki kişisel hitaplar. Commit yazarı GitHub noreply e-postası.
- Örnek verilerdeki adlar (Atlas, Orion, K1/K2, ZCU102 vb.) kurgusaldır.

### Pilot planı (2026-10-15, ürün sahibiyle)
- Hedef: 13–14 kişilik ekip, şirket içi ağ (intranet, internetsiz). Sunucu: ayrılacak bir iş istasyonu veya BT'nin vereceği bilgisayar; ekip tarayıcıyla bağlanır.
- Dosyalar internet bilgisayarında indirilip yalnız taşıma amacıyla intranete aktarılır; kurulum ve kullanım tamamen intranette.
- Sıra (2026-10-17 güncellendi): (1) ürün sahibinin **kişisel** bilgisayarında `-AllowHttp` + `localhost` prova, yalnız kurgusal veri (`metis demo`), taşıma ve yükseltme provası; (2) şirket bilgisayarında (intranet) temiz kurulum, gerçek içerik (demo yok, `master.key` ayrıca yedeklenir); (3) sunucuya taşıma + ağdan erişim.
- Açık işler: başka bilgisayara taşıma (adres değişir) için paketlenmiş, denenmiş bir adım yok — eklenecek ve (1)'de prova edilecek; ağdan erişim yolu (IIS + şirket sertifikası veya iç ağda doğrudan erişim seçeneği) kararı bekliyor.
- **Gerçek ortam (ürün sahibinin intranet bilgisayarı, 2026-10-15):** PostgreSQL 16.15-5 EDB kurucusu varsayılan locale (Türkçe Windows) ile "database cluster initialisation failed" verdi; Locale = `English, United States` ile sorunsuz kuruldu. `KURULUM.md` 2. bölüm, deneme eki ve sorun giderme tablosuna eklendi.

### Arayüz sadeleştirmesi ve yeni palet (2026-10-17, ürün sahibinin onayıyla) — `v2.0.0-rc.2`
İnceleme: uygulama kurgusal veriyle çalıştırılıp ekranlar gezildi; tüm `tr.ts` metinleri ve her ekranın kodu "ilk kez kullanan mühendis" gözüyle tarandı. Dört palet seçeneği gerçek ekranlarda önizlendi; ürün sahibi önerilen seçeneği ve tüm önerileri onayladı.
- **Palet "Lehim yeşili + Turkuaz":** `--vurgu*` (birincil düğme, aktif menü/sekme, sayaç, bağlantı alt çizgisi, odak halkası), `--ray-aktif/--ray-nokta`; `--dikkat` turuncu (altın kanıtla karışmasın). Brief 6.2 güncellendi.
- **Akış:** "Onayla ve yayımla" tek düğme (ön yüzde onay → yayın; yayın başarısızsa kayıt onaylı kalır, "Yayımla" görünür; arka uç değişmedi). Yeni katkıda ara "Taslağa geç"/"Editörü aç" adımları kalktı; kaynak yoksa "Yeni kaynak" açık; kaynak formunda kapsam çip+açılır seçici (`ScopeField`), isteğe bağlı alanlar katlı; iddia türü katlı. Üst çubuk kapsam seçicisi kaldırıldı (`ScopeDialog`, `metis:open-scope` olayıyla). Yöneticiye ana sayfada kurulum listesi.
- **Sadeleştirme:** Ayarlar sekmeleri role göre; yoğunluk ayarı kaldırıldı; tek projede proje adı düz metin; bilgi sayfasında boş bölümler ve yinelenen "Bu konuyu sor" gizlendi; Bilgi sağlığı görünüm düğmesi kaldırıldı; Görevler'deki "Bilgi havuzunu denetle" kartı kaldırıldı; Bilgi havuzu/harita ek filtreleri "Diğer filtreler" altında.
- **Metin:** "kayıt" yalnız değişiklik kaydı; kaynak için "sürüm", bilgi için "revizyon"; teknik terimler sadeleşti; giriş/kurulum ekranı metinleri `tr.ts`'e taşındı; beklenmeyen hatada hata kimliği gösterilir; Model laboratuvarına yöneticiye özel neden metinleri (`labReasons`).
- Doğrulama: `tsc` + `eslint` temiz; Playwright görsel/axe 27/27 (harita 200 düğüm dahil) — **tarayıcı**; e2e 5/5 (kurulum, inceleme, mentor ×2, görev/sağlık; testler yeni akışa göre güncellendi) — **tarayıcı + izole DB + mock model**; ek axe taraması: yönetici ve katkı sahibi, iki tema, ana ekranlar (≈30 ekran × 2 tema) 0 ihlal — **tarayıcı**. Arka uç ve şema değişmedi (pytest koşturulmadı). `docs/design/final/` yeniden üretildi.
- Bilinçli olarak yapılmayanlar (ürün sahibine önerilmedi/ertelendi): "Taslağı düzenle ve karşılaştır"ın taslak sayfasına taşınması, Lab'de tek "Doğrula" düğmesi.
- rc.2 CI (647faef): Linux yeşil; Windows'ta `test_probe_reports_auth_failure` HTTP_401 yerine CONNECTION_FAILED aldı. Neden: kurgusal model sunucusu 401/404'ü istek gövdesini okumadan gönderip soketi kapatıyordu; Windows okunmamış veriyle kapanan sokete RST yollar (zamanlamaya bağlı yarış). Düzeltme: `mock_server.do_POST` gövdeyi önce okur. Ayrıca CI'da Windows pytest (30 dk) ve "Servis günlükleri" (3 dk) adımlarına zaman sınırı; ikinci adım 13 dk takılmıştı.
- Ardından Windows "Paketi üret" adımı düştü: `--locked` derleme bağımlılıkları PyPI'dan yeniden çözüp kilitle karşılaştırıyordu; rc.1'den sonra çıkan fastapi/pydantic/pypdf/sqlalchemy/starlette sürümleri farkı doğurdu. Düzeltme: `--locked` iken üçüncü taraf paketler kilit dosyasından `--no-deps --require-hashes` ile indirilir (tekrarlanabilir paket). Yerelde win64 paketi üretildi (35,4 MB).
- **`v2.0.0-rc.2` yayımlandı** (2026-10-17, ön sürüm): 7b8a41e'de CI Linux + Windows yeşil (pytest, paket üretimi, ağ kapalı kurulum, duman testi, örnek içerik, yükseltme 2.0.0 → +ci2, kaldırma); release işi etiketi ve ZIP'i oluşturdu.

### Açıklayıcı görseller (2026-10-18, ürün sahibinin isteği) — `v2.0.0-rc.3`
- İstek: bilgiye destekleyici/açıklayıcı fotoğraf eklemek. Karar: görseller **metnin içinde** (ürün sahibi).
- Arka uç: `page_revision_figures` (değişmez; ORM kancası + PG trigger, migration `0003`); `ItemIn.figures` (en çok 20, açıklama ≤500); gövdede kendi satırında `{{görsel N}}`. Doğrulama: görsel projedeki, okunabilir, `image/*` bir kaynak revizyonu (`FIGURE_NOT_IMAGE`), yer tutucu var olan sıraya işaret eder (`FIGURE_MISSING`). Görseller revizyon hash'ine dahil (görselsiz revizyonların hash'i değişmedi). Erişim: `revision_source_ids` ve `unreadable_revisions` görsel kaynaklarını da sayar. Kaynak yeni sürüm alınca görseli kullanan sayfa da "Kaynak değişti". Metis "Taslağı düzenle" görselleri taşır (modelden geçirmez, sona yerleştirir). Arama metninde yer tutucu açıklamayla değişir; Markdown dışa aktarımına görseller `gorseller/` altında girer.
- Ön yüz: editörde "Görsel ekle" (var olan görsel kaynağı ya da yükleme + açıklama; imlecin olduğu yere, metne dokunulmadıysa sona), görsel listesi (açıklama düzenle, kaldır → numaralar kayar), önizleme; bilgi sayfasında metin içi `<figure>` + büyütme penceresi; kayıt detayında "Görseller"; İz panelinde görsel kaynak önizlemesi. Görsel kanıt değildir, altın kullanılmaz.
- Doğrulama: pytest tümü yeşil (**izole DB**; yeni `tests/api/test_figures.py` 7 test: yayın + indirme, tür ve yer tutucu doğrulama, hash, erişim gizleme, bağımlılık işaretleme, değişmezlik); e2e 6/6 (yeni `figures.spec.ts`: yükle → önizle → incele → yayımla → sayfada görsel yüklenir ve büyür) — **tarayıcı + izole DB**; görsel/axe 27/27 ve yeni ekranlarda ek axe (iki tema, sayfa, büyütme, editör, görsel ekle, önizleme) 0 ihlal — **tarayıcı**. Test görseli kurgusal (`tests/e2e/fixtures/kurgusal-kart.png`).
- **`v2.0.0-rc.3` yayımlandı** (2026-10-18, ön sürüm): 103b125'te CI Linux + Windows yeşil (Windows: pytest, paket, ağ kapalı kurulum + migration 0003, duman testi, yükseltme, kaldırma).

### Yazar yayımlar + yayın öncesi kontrol (2026-10-18, ürün sahibinin kararı) — `v2.0.0-rc.4`
- İstek: herkes kendi uzmanlık bilgisini ekleyip **kendisi** yayımlasın; ikinci kişinin onayı olmasın; Metis (kural + bağlı model) eski bilgilerle çelişki/tekrar olmadığını denetleyip kullanıcıyı uyarsın. Uyarının zamanı: **yayın anında** (önerildi, kabul edildi; bakım taraması arka planda sürüyor). Kararlar: başkasının bilgisini düzenleyen de doğrudan yayımlar, sahibine bildirim gider (a); model yoksa/başarısızsa kural kontrolüyle ve açık uyarıyla yayın serbest (evet). Brief Bölüm 2 madde 1'e ve CLAUDE.md özetine "yazar + otomatik kontrol" notu eklendi.
- Arka uç: politika `self_publish` (varsayılan; migration `0004` mevcut projeleri de geçirir, kısıt genişledi). `POST /changes/{id}/check` (`prepublish.py`): oturum içinde aday üretimi — kural (bakım taramasıyla aynı: `_strip_numbers` biçimi, farklı değer, `overlaps`), arama ile en yakın 3 bilgi —; model çağrıları oturum dışında (`CLAIM_CONFLICT` kural adaylarına, `PAGE_DIFF` benzer bilgilere: conflict_candidate→çelişki, no_change→tekrar, update/supersede→örtüşme); sonra erişim yeniden denetlenir, okunamayan bilgi uyarıda görünmez, sonuç `detail.prepublish`'e içerik hash'iyle saklanır (hash değişmişse `HASH_MISMATCH`). `POST /changes/{id}/publish-direct`: `REVIEW_REQUIRED` (politika başka), `ROLE_REQUIRED` (katkı sahibi değil), `CHECK_REQUIRED` (güncel kontrol yok), `CHECK_WARNINGS` (uyarı onaylanmadı); geçerse `policy=self_publish` onay kaydı (hash'e bağlı) + atomik yayın; onaylanan çelişkiler kanıtlı iki tarafla Bilgi sağlığına bulgu (bakım taramasıyla aynı parmak izi, tekrar açılmaz). Gelen kutusu `updated_pages`: sahibi olduğun bilgiyi başkası yayımladıysa (son "Gördüm"den sonra, tercih `updates_seen_at` = sunucu zamanı).
- Ön yüz: editörde ve karar panelinde tek "Yayımla" (kontrol → sorun yoksa yayın; varsa "Yayımlamadan önce bak" penceresi; "Taslağa dön" editörü güncel hash'le yeniden açar); incelemedeki kayıtta inceleyiciye katlı "Düzeltme iste ya da reddet"; ana sayfada "Bilgilerin güncellendi" + "Gördüm"; bilgi sayfasında "Yayımlayan"; Ayarlar → "Yayın politikası" (Yazar yayımlar / Bağımsız inceleme; eski kişisel pilot yalnız seçiliyse görünür). Kayıtlar sekmesi "Karar bekleyenler".
- Doğrulama: pytest tümü yeşil (**izole DB**; mevcut testlerin fixture'ları bağımsız inceleme politikasına alındı; yeni `tests/api/test_self_publish.py` 11 test: varsayılan politika, kontrol + yayın, hash bağı, kural çelişkisi → uyarı → onaylı yayın → bulgu + çözüm vakası + taramada tekrar yok, ayrık kapsam, okunamayan bilgi gizli, rol, bağımsız politika, sahibine bildirim + "Gördüm", model ile çelişki/tekrar — **mock model** —, model hatasında kural sonucu); e2e 8/8 (kurulum doğrudan yayın, inceleme akışı bağımsız politikada, yeni: çelişki uyarısı → Taslağa dön → Yine de yayımla → Bilgi sağlığı; editörde uyarı → Taslağa dön → düzenle → yeniden yayımla) — **tarayıcı + izole DB**; görsel/axe 27/27 + yeni ekranlarda ek axe (kayıt, uyarı penceresi, editör, ana sayfa bildirimi, politika; iki tema) 0 ihlal — **tarayıcı**. Gerçek modelle denenmedi.
- Sınırlar: kontrol yalnız yayındaki bilgilerle karşılaştırır (açık taslaklar arası değil); model en çok 5 kural adayı + 3 benzer bilgi değerlendirir (her çağrı ≤45 sn); bildirim yalnız ana sayfada (e-posta yok).
- **`v2.0.0-rc.4` yayımlandı** (2026-10-18, ön sürüm): 1596de7'de CI Linux + Windows yeşil (Windows: pytest, paket, ağ kapalı kurulum + migration 0004, duman testi, örnek içerik, yükseltme, kaldırma); release işi etiketi ve ZIP'i (37,2 MB) oluşturdu.

### Örnek içerik tutarlılığı + bildirim düzeltmesi (2026-10-18) — `v2.0.0-rc.5`
- Ürün sahibi sordu: demo çalışma alanı son isteklerle tutarlı mı? Değildi: sayfalar Barış'ın bağımsız onayıyla yayımlanıyordu ("Onaylayan"), bir kayıt "incelemede" bekliyordu, metin içi görsel ve "Bilgilerin güncellendi" örneği yoktu. Ayrıca kullanıcıya verilen deneme örneği (J3/J7) yalnız geliştirme DB'sindeki test verisindeydi, demo'da yok — düzeltildi (aşağıdaki 115200/57600 örneği).
- Tohum (`seed/demo.py`): bilgiler "yazar yayımlar" ile yayımlanır (`prepublish.rule_check` = oturum içi kural kontrolü, model durumu dürüstçe "not_configured"; ardından `publish_direct`). Saha notunu Barış yayımlar; kural kontrolü 115200/921600 çelişkisini bulur, bilerek geçilir → Bilgi sağlığında `acknowledged_at_publish` bulgusu (taramayla aynı parmak izi, tekrar açılmaz). "Hata ayıklama UART hızı" sayfasında kurgusal kartın üstten şematik görseli (PNG tohumda kütüphanesiz üretilir; altın kullanılmaz). Barış, Deniz'in SPI sayfasına arama adı ekler → Deniz'e "Bilgilerin güncellendi". Tampon kaydı incelemede değil, yarım taslak.
- **Hata (rc.4):** `updated_pages` yayın manifestosunu (tüm sayfalar) kullandığı için başkasının ilgisiz yayını sahibinin bütün sayfalarını "güncellendi" gösteriyordu; demo testi yakaladı. Sorgu artık `ChangeSetItem` ile yalnız o kayıtta değişen sayfaları sayar. Regresyon testi eklendi (düzeltme olmadan kırmızı, sonra yeşil).
- Doğrulama: pytest tümü yeşil (**izole DB**; yeni demo testi: politika, incelemede kayıt yok, "Yayımlayan", görsel, onaylı çelişki bulgusu, bildirim); e2e 8/8 — **tarayıcı + izole DB**; görsel/axe 27/27 ve yeni demo ekranları (ana sayfa, görselli sayfa, sağlık, kayıtlar; iki tema) 0 ihlal — **tarayıcı**, geliştirme DB'si yeni tohumla yeniden kuruldu.

