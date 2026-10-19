# v2-ADR-002 — v0.5.5 verisinin aktarımı (`metis import-v1`)

Tarih: 2026-10-10 · Durum: **kaldırıldı (2026-10-19, ürün sahibinin kararı; 2.0.10)** — proje sıfırdan başlıyor, kod ve testler silindi; `legacy_import_runs` tablosu şemada duruyor · Kod: `services/metis/legacy_import/` · Test: `tests/legacy_import/`

## Bağlam
Ürün sahibinin v0.5.5 masaüstü uygulamasındaki tüm bilgi v2 sunucusuna taşınmalı (brief 5.10). Girdi, v0.5.5'in "Yedek al"
ile ürettiği şifreli yedek dosyası ve parolasıdır; bu dosya v0.5.5 ana anahtarını da içerdiği için model sağlayıcı
anahtarları da taşınabilir. v1 kodu çalıştırılmaz; biçim `reference/v0.5.5` kaynaklarından okunmuştur
(`deployment/desktop/recovery.py`, `deployment/backup.py`, `services/api/db.py`, `knowledge.py`,
`conflict_resolution.py`, `security.py`, `scopes.py`).

## Karar

### Akış
1. **Aç ve doğrula** (`archive.py`): `METISBK1` + salt16 + nonce16 + tag16 + gövde; scrypt(n=32768, r=8, p=1) → AES-256-GCM,
   AAD=`METISBK1`. Dış ZIP tam olarak `snapshot.zip` + `recovery.json` içermeli; manifest `metis-backup-v1`, şema 1|2,
   ana anahtar parmak izi `recovery.json` ile eşleşmeli; tablo adları v0.5.5 kümesinin alt kümesi olmalı.
   Bloblar yalnız manifestteki **doğrulanmış 64 hex** özetten türetilen adla okunur (arşivden yol çıkarılmaz →
   path traversal yok), boyut sınırı 10 MB/blob, 512 MB snapshot, 64 MB manifest; her blob SHA-256 ile doğrulanır.
2. **Boşluk kontrolü:** hedefte insan kullanıcı veya proje varsa `TARGET_NOT_EMPTY` (dry-run dahil).
   Var olan `metis-worker` kimliği yeniden kullanılır.
3. **Plan** (`transform.py`): tüm dönüşüm bellekte; v0.5.5 UUID'leri korunur, yeni satırlar için deterministik uuid5
   (aynı yedek → aynı plan). İçe aktarma yeni onay veya yayın **üretmez**; v1 hash'leri `legacy_hash`'te saklanır.
4. **Plan doğrulaması** (`runner.verify_plan`) ve rapor. Rapor zaman/mod içermez → dry-run ve apply raporu birebir aynı
   (parmak izi: rapor JSON'unun SHA-256'sı).
5. **Apply:** bloblar `<data>/.import-<uuid>/` geçici dizinine yazılıp doğrulanır → tek transaction: FK sırasıyla
   (`Base.metadata.sorted_tables`) ekleme, gecikmeli işaretçiler (aktif yayın, yayımlanmış revizyon, ilişki revizyonu,
   önceki kayıt), aktif yayın için arama indeksinin yeniden kurulması, **gerçek servislerle ikinci doğrulama**
   (`page_detail` ile her aktif sayfa açılır, iddia↔kanıt sayıları plan doğrulamasıyla aynı olmalı), tek
   `legacy_import` audit olayı, `legacy_import_runs` satırı → commit → bloblar yerine taşınır. Herhangi bir hatada
   rollback + geçici dizin silinir; kullanıcıya "Hiçbir şey değiştirilmedi." döner.

### Eşleme ayrıntıları (brief tablosuna ek kararlar)
| Konu | Karar |
|---|---|
| Kapsam | v0.5.5 `{platform, hardware, dimensions{domain,yatt,card,project}}` → v2 dört boyut (`card→kart`, `project→proje`; yalnız iki alan varsa `hardware→kart`, `platform→proje`). Katalog: `scope-catalog:<proje>` ayarı + kaynak/sayfa kapsamlarında geçen değerler + proje `domain` alanı; `deleted` listesi silinmiş katalog değeri olarak gelir. Katalog biçimi v0.5.5 kaynağında yer almadığından birden çok yaygın biçim kabul edilir; tanınmayan biçim raporda "atlandı" olur. |
| Sayfa revizyonu hash'i | v2 içerik hash'i yeniden hesaplanır (`hash`), v1 hash'i `legacy_hash`. |
| İddia↔kanıt | `claims[].evidence_ids` → `claim_evidence`. İddia metni kanıtta birebir geçiyorsa alıntı iddianın kendisidir; geçmiyorsa alıntı kanıt metnidir ve iddia mentor paketine girmez (v2 kuralı: birebir geçmeyen iddia kullanılmaz). Sayısı raporda not edilir. |
| Değişiklik seti durumu | `deleted` → `deleted_at` (durum `draft`), `changes_requested` → `draft`; v1 durumu `detail.legacy_state`'te. Değişiklik hash'i v2 biçimiyle yeniden hesaplanır. |
| Onaylar | Onay hash'i v1 değişiklik hash'iyle eşleşiyorsa v2 onayı yeni v2 hash'ine bağlanır; eşleşmiyorsa eşleşmeyen sabit bir hash alır (yayın yetkisi vermez). |
| Yayınlar | `kind=legacy`, proje başına sıra numarası tarih sırasıyla. Yayın sayfaları/ilişkileri manifestten. |
| İlişkiler | v0.5.5 ilişki alan adı kaynakta tanımlı olmadığından `type`/`predicate`/`relation` kabul edilir; bilinmeyen tür `explains` olur ve raporda not edilir. |
| Çelişki vakası | `conflict-case:<cevap>` → `conflict_cases` (bulgu, anlık görüntüdeki iki sayfayla eşleşen açık çelişki bulgusundan bulunur) + seçenekler; `change_id` + `chosen_option` → `conflict_resolutions`. Yayımlanmış vaka `resolved`, diğerleri `open`. İncelemede bekleyen v0.5.5 çözüm kaydı yalnız korunan sayfanın güncellemesini içerir (geri çekme vakada yazılıydı); v2'de yayımlanırsa karşı sayfa otomatik geri çekilmez — raporda not edilir, v2 akışıyla yeniden seçilmesi önerilir. |
| İşler | Bitmiş işler salt okunur geçmiş; `queued/leased/running/awaiting_input` → `cancelled` ve raporda listelenir. İşin istekte bulunanı yoksa iş atlanır. |
| Cevaplar | `legacy=true`, "v1 alıntı cevabı" olarak gösterilir; alıntılar `answer_citations`. |
| Sağlayıcı anahtarı | v0.5.5 ana anahtarıyla çözülür (`b64(nonce16‖tag16‖ct)`, AAD yok), v2 ana anahtarıyla `v2:` biçiminde yeniden şifrelenir; düz metin yalnız bellekte. Çözülemezse anahtar aktarılmaz, not düşülür. |
| Modeller | Yeterlilik taşınmaz; "test edilmedi" durumunda gelir. Bu yüzden rapordaki "örnek mentor soruları" adımı aktarım anında daima **atlandı** olur; model laboratuvarında benchmark sonrası çalıştırılır. |
| Zamanlayıcı | `maintenance-schedule:*` ve `preparation-auto:*` tek `schedules` satırına birleşir; aralık farklıysa daha seyrek olan seçilir (notta yazılır). |
| Konum metni | `"PDF · sayfa 3"` → `{page: 3}`; ek bilgi içeren metin (`"PDF · sayfa 4 · tablo 2"`) → `{page: 4, raw: "…"}` ve arayüzde özgün metin gösterilir. |

### Dry-run kaydı
Brief "dry-run yazmaz" der. Veri tablolarına hiçbir şey yazılmaz; yalnız `legacy_import_runs` işletim tablosuna bir
satır eklenir (Ayarlar → v0.5.5 aktarımı ekranında rapor görünsün diye). Bu satır boşluk kontrolünü etkilemez.
Reddedilen denemeler (yanlış parola, bozuk dosya, dolu DB…) hiçbir satır yazmaz.

## Doğrulama
- `tests/legacy_import/synthetic.py`: v1 kodu çalıştırılmadan v0.5.5 şemasına uygun yedek üretir (tüm tablo türleri,
  Türkçe dosya adları, silinmiş kayıt, geri çekilmiş sayfa, çelişki vakası + çözüm kaydı, owner_review projesi,
  yarım iş, worker kimliği, iki eski zamanlayıcı, aktarılmayan ayarlar, v1 biçimli parola hash'i ve sağlayıcı sırrı).
- `tests/legacy_import/test_phase9_import.py` (izole PG): dry-run ≡ apply raporu; aktarılan sayfalar açılıyor, ●n doğru
  kaynağa/konuma gidiyor; eski parola ile giriş ve yeniden hash; arama; owner_review korunuyor; anahtar yeniden
  şifrelenmiş ve düz metin `pg_dump` çıktısında, raporlarda, loglarda ve blob dizininde yok; hata vakaları (yanlış parola,
  bozuk tag, bozuk gövde, ZIP değil, eksik blob, hash uyuşmazlığı, yanlış kurtarma anahtarı, dolu DB, ikinci apply,
  manifestte path traversal, arşivde traversal girdileri, yazma sırasında hata) "Hiçbir şey değiştirilmedi" ile sonlanıyor
  ve tablo sayıları/blob dizini değişmiyor.
- **Gerçek yedekle tatbikat yapılmadı** (bu ortamda ürün sahibinin yedeği yok). Adımlar `docs/TESLIM.md`'de.

## Sonuçlar
- Aktarım bir kez, boş bir v2 kurulumuna yapılır; tekrar gerekirse veritabanı sıfırlanıp yeniden çalıştırılır.
- v0.5.5 kaynağında tanımı bulunmayan iki biçim (kapsam kataloğu ayarı, ilişki alan adları) toleranslı okunur;
  gerçek yedekte farklı çıkarsa rapordaki "atlanan kayıtlar" ve "notlar" bölümü bunu gösterir.
