# METIS — Teslim

Bu belge METIS'in teslim özetidir: neyin yapıldığı, neyin nasıl doğrulandığı, neyin bu ortamda
doğrulanamadığı ve ürün sahibinin yapması gerekenler. Ayrıntılı günlük `docs/PROGRESS.md`'de.

Doğrulama türleri ayrı yazılır:
- **izole DB** — pytest, gerçek PostgreSQL 16, test başına temiz veritabanı
- **mock** — deterministik kurgusal model; hattın doğruluğunu gösterir, model kalitesini değil
- **tarayıcı** — Playwright/Chromium + axe WCAG AA
- **paket** — kurulum paketinin bu ortamda (Linux) uçtan uca kurulumu
- **CI** — GitHub Actions; Windows işi gerçek bir Windows Server 2022 runner'ında çalışır
- **canlı model / gerçek ortam** — bu ortamda **yok**; aşağıda "doğrulanmadı" diye işaretli

## 1. Çalıştırma

### Kendi bilgisayarında (geliştirme modu, kurgusal çalışma alanıyla)

Gereken: Python 3.12, Node 22, PostgreSQL 16 (yerelde, `metis_owner` ve `metis_app` rolleri, parola `metis-dev`).

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
npm install
npm run build:web
scripts/dev-up.sh --demo        # PG + migrate + kurgusal model (:9100) + API (:8000) + worker + kurgusal çalışma alanı
```

Tarayıcıda `http://localhost:8000`. Kurgusal kullanıcılar (parola `Kurgusal-Parola-2026`):

| Kullanıcı | Rol |
|---|---|
| `ayse` | yönetici |
| `baris` | inceleyici |
| `deniz` | katkı sahibi |
| `ece` | okur |

Kurgusal çalışma alanında 8 sayfa, ilişkiler, incelemede bekleyen bir kayıt, açık bir çelişki ("Hata ayıklama UART hızı" ↔
"Konsol baud hızı (saha)") ve 26/26 ile yeterli kurgusal model var. Mentor, görevler ve laboratuvar bu modelle çalışır.
Harita performansı için 200 düğümlük ayrı proje: `metis demo-graph --nodes 200`.

Testler:
```bash
.venv/bin/pytest                                              # backend (izole PG)
npx playwright test -c apps/web/playwright.e2e.config.ts      # uçtan uca akışlar (kendi DB'si ve sunucusu)
npx playwright test -c apps/web/playwright.config.ts          # vitrin, axe, harita fps (dev yığını :8000'de)
.venv/bin/python evals/run.py --mode mock                     # değerlendirme (mock)
```

### Sunucu kurulum paketi

- Üretim: `python deploy/build-bundle.py` → `dist/METIS-2.0.0-server-win64.zip` (≈35 MB, internetsiz kurulum).
- Rehber: `docs/KURULUM.md` (paketin içinde de var), kısa başlangıç: `BASLA.txt`.
- Sürüm etiketi (`v*`) atıldığında CI, ZIP'i GitHub Release'e tek dosya olarak ekler.

## 2. Ekran görüntüleri

`docs/design/final/`, iki tema (`-acik`, `-koyu`), 1440×900:

| # | Ekran |
|---|---|
| 01 | Ana sayfa |
| 02 | Bilgi havuzu |
| 03 | Bilgi sayfası + İz paneli |
| 04 | Mentor cevabı |
| 05 | Yeni katkı |
| 06 | İnceleme |
| 07 | Görevler |
| 08 | Bilgi sağlığı |
| 09 | Kavram haritası |
| 10 | Model laboratuvarı |
| 11 | Ayarlar |
| 12 | 390 px mobil: ana sayfa, bilgi sayfası + İz, mentor |

Yeniden üretmek için: `node scripts/final-screenshots.mjs`. Tasarım vitrini (Faz 0) görüntüleri de `docs/design/` altında.

## 3. Faz faz yapılanlar ve doğrulama

### Faz 0 — İskelet ve tasarım vitrini
**Yapılan:** repo, Alembic, test altyapısı, `tokens.css` (iki tema), IBM Plex, primitive'ler, kabuk, İz prototipi, `/_vitrin`.

| Kabul ölçütü | Durum |
|---|---|
| Vitrin iki temada axe AA temiz | doğrulandı — tarayıcı |
| 1366/1920/390 görüntüleri, yatay kaydırma yok | doğrulandı — tarayıcı |
| İz klavye ile ve reduced-motion'da çalışıyor | doğrulandı — tarayıcı |
| Türkçe glifler; 12 px altında yazı yok | doğrulandı — tarayıcı (vitrin + 12 ana ekran + bilgi sayfası; CI'da yakalanan satır içi kod 11 px hatası düzeltildi) |

### Faz 1 — Kimlik, proje, kapsam, kaynak

| Kabul ölçütü | Durum |
|---|---|
| Yetki matrisi rol×uç (11 uç × 5 rol) | doğrulandı — izole DB |
| Değişmezlik trigger'ı | doğrulandı — izole DB |
| PDF zaman ve bellek sınırı | doğrulandı — izole DB, alt süreç |
| Kurulum→kaynak→taslak→inceleme→yayın→İz e2e | doğrulandı — tarayıcı |

CI'da yakalanıp düzeltilenler:
- PDF bellek sınırına takılan çıkarım "ayrıştırma hatası" diye raporlanıyordu.
- Windows'ta PDF çıkarımına bellek sınırı hiç uygulanmıyordu; artık Job Object ile uygulanıyor, uygulanamazsa çıkarım yapılmıyor.

### Faz 2 — Katkı, inceleme, yayın

| Kabul ölçütü | Durum |
|---|---|
| Onaydan sonra içerik değişince yayın reddi (hash) | doğrulandı — izole DB |
| Eşzamanlı düzenlemede 409 | doğrulandı — izole DB |
| Yayın ortasında hata → eski yayın aktif kalıyor | doğrulandı — izole DB, hata enjeksiyonu |
| Worker kimliği onay/yayın yapamıyor | doğrulandı — izole DB |
| Tam akış e2e | doğrulandı — tarayıcı |

Son CI turunda bulunan ve düzeltilen önemli bir hata: veritabanı commit'i yanıt gönderildikten sonra çalışıyordu (commit hatası 2xx ile kaybolabilir, hemen sonraki okuma eski veriyi görebilirdi). Artık commit yanıttan önce; regresyon testi var.

### Faz 3 — Bilgi havuzu, bilgi sayfası, arama

| Kabul ölçütü | Durum |
|---|---|
| Türkçe gövdeleme ("kesmeler"→"kesme") | doğrulandı — izole DB |
| Birebir sembol arama | doğrulandı — izole DB |
| Domain paketi eşanlamlıları | doğrulandı — izole DB |
| Erişilemeyen sayfa hiçbir yoldan sızmıyor | doğrulandı — izole DB |

### Faz 4 — Model gateway ve kaynaklı mentor

| Kabul ölçütü | Durum |
|---|---|
| `evals/` mock modda %100 (26 kanıt + 27 worker + 15 açıklama-doğrulayıcı) | doğrulandı — mock |
| `RETRIEVAL_UNAVAILABLE` ≠ `NO_EVIDENCE` | doğrulandı — izole DB + mock |
| Model çağrısı sırasında yetki iptali → 403, cevap kaydedilmez | doğrulandı — izole DB + mock |
| Sessiz fallback yok | doğrulandı — izole DB + mock, tarayıcı |
| Mentor ekranı (SSE, via ateşlenmesi, alıntı kartları, İz paneli, cevaptan taslak) | doğrulandı — tarayıcı, e2e |
| Canlı model | **doğrulanmadı** — şirket modeli yok |

Canlı model için: `python evals/run.py --mode live --base-url https://… --model <model-id> --api-key-env <ANAHTAR_DEGISKENI>` ayrı rapor üretir (anahtar ortam değişkeninden okunur, komut satırına yazılmaz).

### Faz 5 — Metis worker

| Kabul ölçütü | Durum |
|---|---|
| Lease dolunca iş devam ediyor, eski worker yazamıyor | doğrulandı — izole DB + mock |
| İptal fence'i artırıyor | doğrulandı — izole DB + mock |
| Aynı kaynak iki kez → tek taslak | doğrulandı — izole DB + mock |
| Bütçe aşımı kısmi sonucu koruyor | doğrulandı — izole DB + mock |
| Çıktı yalnız taslak/incelemede | doğrulandı — izole DB + mock |
| Görevler ekranı canlı (SSE) | doğrulandı — tarayıcı, e2e |

### Faz 6 — Bilgi sağlığı ve çelişki çözümü

| Kabul ölçütü | Durum |
|---|---|
| Kaynak yeni revizyon alınca bağlı sayfalar işaretleniyor, mentor kullanmıyor | doğrulandı — izole DB |
| Çelişki çözümü incelemesiz yayımlanamıyor | doğrulandı — izole DB |
| "Çelişkiden çözüme" akışı → kayıt incelemede | doğrulandı — tarayıcı, e2e |

Son doğrulamada iki hata bulunup düzeltildi:
- Mentor, ilgili her sayfayı "açık çelişki" diye işaretliyordu; artık yalnız çelişen sayfalar işaretleniyor.
- Kurgusal tohum ile kural taraması aynı çelişkiyi iki kez açabiliyordu; artık tek parmak izi kullanılıyor.

İkisi için de regresyon testi var.

### Faz 7 — Kavram haritası

| Kabul ölçütü | Durum |
|---|---|
| 200 düğümde akıcı | doğrulandı — tarayıcı, ölçüldü (aşağıda) |
| Liste görünümü axe temiz | doğrulandı — tarayıcı, iki tema |
| Erişilemeyen düğüm görünmüyor | doğrulandı — izole DB |

200 düğüm, 3 saniyelik kaydırma/yakınlaştırma ölçümü: medyan 59.9 fps, ortalama 55 fps, en yavaş %10 59.5 fps (hedef 60).
Ölçüm başsız Chromium'da, bu ortamın CPU'sunda yapıldı.

### Faz 8 — Model laboratuvarı

| Kabul ölçütü | Durum |
|---|---|
| Kritik hata (uydurma sayı, sahte kaynak, kapsam ihlali) ortalamadan bağımsız eliyor | doğrulandı — izole DB + mock |
| n<30 için p95 "yetersiz örnek" | doğrulandı — izole DB + mock, tarayıcı |
| Ekle → test et → benchmark akışı | doğrulandı — tarayıcı, e2e |

### Faz 9 — v0.5.5 verisinin taşınması

| Kabul ölçütü | Durum |
|---|---|
| Sentetik yedek: dry-run ve apply birebir aynı rapor | doğrulandı — izole DB, CLI ile de |
| Tüm hata vakaları "hiçbir şey değiştirilmedi" ile bitiyor | doğrulandı — izole DB (yanlış parola, bozuk tag/gövde, ZIP değil, eksik blob, hash uyuşmazlığı, yanlış kurtarma anahtarı, dolu DB, ikinci apply, path traversal, yazma sırasında hata) |
| Aktarılan sayfalar açılıyor, ●n doğru kaynağa gidiyor | doğrulandı — izole DB |
| Sağlayıcı anahtarı yeniden şifreli, düz metin hiçbir dosya/logda yok | doğrulandı — izole DB (`pg_dump`, raporlar, loglar, blob dizini taranarak) |
| Gerçek yedekle tatbikat | **doğrulanmadı** — senin yedeğin bu ortamda yok |

Eşleme kararları: `docs/adr/v2-ADR-002-legacy-import.md`.

### Faz 10 — Sunucu kurulum paketi

| Kabul ölçütü | Durum |
|---|---|
| Yedek → boş DB'ye geri yükleme, tatbikat, kurcalanmış arşiv reddi | doğrulandı — izole DB, gerçek `pg_dump`/`pg_restore` |
| İnternetsiz kurulum → servis → giriş → yeniden başlatma sonrası kalıcılık → yükseltme → hata durumunda geri dönüş | doğrulandı — paket (Linux eşdeğeri, bu ortamda) |
| Aynı akış Windows'ta, ağ kapalı | doğrulandı — CI (Windows Server 2022 runner, PostgreSQL 16): ZIP'ten internetsiz kurulum, servisler, ilk yönetici, kaynak yükleme, servis yeniden başlatma sonrası veri kalıcı, yedek, geri yükleme tatbikatı, `upgrade.ps1` ile 2.0.0 → 2.0.0+ci2 (yedek → migrate → sağlık → doctor) |
| Gerçek şirket sunucusunda kurulum | **doğrulanmadı** |

Paket testinde bulunan dört hata düzeltildi:
1. Windows'a özgü bağımlılık (`tzdata`) wheelhouse'a girmiyordu.
2. Yükseltme sonrası temizlik, geri dönülecek önceki sürümü siliyordu.
3. Yükseltme hatasında geri dönüş tetiklenmiyordu.
4. PowerShell 5.1 için BOM eksikti.

Windows CI işinde bulunan ve düzeltilen hatalar (hepsi gerçek bir şirket sunucusunda da çıkacaktı):
1. Kurulum betiği pip çıktısını dönüş değerine karıştırıyordu, `app\current` bağlantısı kurulamıyordu.
2. `metis doctor` Türkçe çıktıyı Windows konsolunda (cp1252) yazamayıp çöküyordu; CLI çıktısı artık UTF-8.
3. Sağlık kontrolü `HTTP_PROXY` tanımlıyken 127.0.0.1'i de vekile gönderiyordu; yerel istekler artık vekilsiz.
4. Yükseltmede WinSW `stop` süreç kapanmadan dönüyordu; hemen gelen `start` "zaten çalışıyor" deyip boşa düşüyor,
   API kapalı kalıyordu. Geri dönüş doğru çalıştı (2.0.0'a dönüp servisleri başlattı). Durdurma/başlatma artık
   Stopped/Running durumunu bekliyor; sonraki koşuda yükseltme yeşil.
5. Paket üretimi Windows'ta `npm`'i (`npm.cmd`) bulamıyordu.

Sınırlar: CI kurulumu `-AllowHttp` ile (geliştirme profili, http) yapıldı; üretim profili (https, IIS/ARR önünde) Windows'ta
denenmedi. Yükseltme testindeki `+ci2` yalnız paket adını değiştirir, uygulama sürümü 2.0.0 kalır. Gerçek şirket sunucusu,
gerçek ağ kısıtları ve EDB kurulumlu PostgreSQL ile deneme **yapılmadı**.

### Faz 11 (opsiyonel) — Yapılmadı

Brief bu fazı yalnız sabit Faz 5 hattının yetmediği somut vakalar ölçülürse açılacak şekilde tanımlıyor (5.7).
Mock değerlendirmede hat 27/27 worker vakasını geçti; yetmediğini gösteren bir vaka yok. Canlı modelle ölçüm de bu ortamda
yapılamadı. Gerekçesiz bir tool-call döngüsü eklemek, brief'in deterministik hat ilkesine aykırı olurdu.

Canlı model benchmark'ı sonrası sabit hattın kaçırdığı vakalar çıkarsa, açılması değerlendirilmeli.

## 4. Uygulanan altyapı varsayılanları (brief Bölüm 11)

| # | Konu | Varsayılan | Değiştirme yeri |
|---|---|---|---|
| 1 | Sunucu | Windows Server, WinSW servisleri | `deploy/linux/` (systemd) hazır |
| 2 | Kimlik | Yerel hesaplar (scrypt) | LDAP için `AuthProvider` arayüzü hazır |
| 3 | PostgreSQL | Aynı sunucuda METIS'e ayrılmış PG 16 | Betik EDB kurucusunu çalıştırmaz, talimat verir |
| 4 | TLS | IIS/ARR ters vekil, şirket sertifikası | Örnek `web.config` pakette; METIS 127.0.0.1'de dinler |
| 5 | Kapasite | 25 kullanıcı: 2 API süreci, 1 worker (2 slot) | Kurulum parametreleri |

## 5. Brief'ten bilinçli sapmalar ve kararlar

- **Kapsam tanımları ayrı menü değil:** v1'de ayrı nav öğesiydi. v2'de **Ayarlar → Kapsam tanımları** altında; üst
  çubuktaki kapsam seçiciden "Tanımları yönet" ile de açılıyor (brief 576'nın istediği değişiklik).
- **Dry-run kaydı:** veri tablolarına hiçbir şey yazmaz. Yalnız `legacy_import_runs` işletim tablosuna bir satır ekler, raporu
  Ayarlar → v0.5.5 aktarımı ekranında görebilesin diye. Reddedilen denemeler hiçbir şey yazmaz.
- **v0.5.5 kaynağında tanımı olmayan iki biçim:** kapsam kataloğu ayarı ve ilişki alan adları toleranslı okunuyor. Gerçek
  yedekte farklı çıkarsa raporun "atlanan kayıtlar" ve "notlar" bölümü gösterir.
- **İncelemede bekleyen eski çözüm kaydı:** v0.5.5'te geri çekilecek sayfa vakaya yazılıydı, kayda değil. v2'de yayımlansa bile
  karşı sayfa otomatik geri çekilmez. Rapor bunu not eder; çözümün Bilgi sağlığı ekranından yeniden seçilmesi önerilir.
- **Yedek arşivi ana anahtarı içermez:** yalnız parmak izini içerir. Anahtar ayrı saklanmalı. Geri yükleme farklı anahtarla
  reddedilir.
- **Mentor "Otomatik" model seçimi:** dürüstçe "Otomatik (kalite kapısı → gecikme)" diye etiketli ve deterministik. Uygun olmayan
  model seçilirse sessizce başka modele geçilmez.

## 6. Senin yapman gerekenler

1. **Gerçek v0.5.5 yedeğiyle aktarım tatbikatı.** Boş bir v2 kurulumunda:
   - `metis import-v1 <yedek> --dry-run --report-dir rapor` çalıştır, `.md` raporu oku (sayılar, atlananlar, notlar).
   - Uygunsa `--dry-run` olmadan çalıştır.
   - Birkaç sayfayı aç, ●n işaretlerinin doğru kaynağa gittiğine bak. Eski kullanıcı parolasıyla giriş dene.
   - Rehber: KURULUM.md bölüm 10.
2. **Şirket sunucusunda kurulum.** Önce bir test sunucusunda:
   - PG 16 (EDB çevrimdışı kurucu).
   - `install-offline.ps1 -PublicUrl https://…`.
   - IIS/ARR + sertifika.
   - `master.key`'i kasaya koy.
   - Rehber: KURULUM.md bölüm 1–6.
3. **Şirket model endpoint'i.**
   - Model laboratuvarında sağlayıcıyı ekle; adrese izin verilmemişse **İzin ver ve ekle** (2026-10-19'dan beri
     `metis.env`'e elle eklemek gerekmez). Sonra **Test et**, **Benchmark çalıştır**.
   - Canlı değerlendirme: `python evals/run.py --mode live …`. Sonucu mock'tan ayrı oku.

## 7. Bilinen sınırlar ve önerilen sonraki adımlar

- **Model kalitesi ölçülmedi:** tüm model doğrulamaları kurgusal modelle; gerçek model kalitesi bilinmiyor.
- **Windows ve gerçek veri:** paket Windows Server 2022 CI runner'ında internetsiz kuruldu ve yükseltildi; gerçek şirket sunucusunda (IIS/ARR + TLS, üretim profili) kurulum ve gerçek v0.5.5 verisi doğrulanmadı.
- **OpenAPI tipleri:** bazı JSON alanları (cevap zamanlamaları, model probe/benchmark özetleri, iş raporları) OpenAPI'de tiplenmemiş
  `object`; arayüz bunları savunmacı ayrıştırıyor. Öneri: Pydantic şemalarında açık tipler.
- **Kimlik:** LDAP/AD girişi yok (arayüz hazır); gerekirse sunucu adı ve grup→rol eşlemesi öğrenilip eklenir.
- **Harita ölçümü:** bu ortamın CPU'sunda yapıldı; zayıf istemcilerde ayrıca bakılmalı. "Tümünü göster" 200 düğümü hedefler.
- **Kararsız test:** harita liste görünümü axe testi bir kez, yük altında başarısız oldu, 9 koşudan 1'inde. Animasyon bitmeden
  ölçüm hipoteziyle test sağlamlaştırıldı. Kök neden kesin doğrulanmadı.
