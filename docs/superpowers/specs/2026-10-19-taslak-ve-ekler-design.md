# Tasarım: Tek adımda "Taslak hazırla" — not + ekler (2026-10-19)

Durum: taslak tasarım, ürün sahibinin onayını bekliyor. Kurgusal örneklerle yazıldı.

## 1. Neden

Ürün sahibi şirket kurulumunda ilk bilgisini girmeye çalıştı:

- "Yeni katkı"da bir uzman notu yazdı ve açıklamayı destekleyen bir görsel ekledi.
- Sonuç kafa karıştırıcıydı:
  - Kaynak bir sürüm tek dosya taşıyabildiği için görsel "asıl içerik", yazdığı metin "görselin açıklaması" sayıldı.
  - Ekranda "Bu dosyadan metin çıkarılamadı… içeriği uzman notu olarak eklemen gerekiyor" uyarısı çıktı.
  - Kaynak kaydedildi, ama taslak adımına geçmediği için bilgi havuzunda ve kayıtlarda hiçbir şey görünmedi.

Ürün sahibinin istediği (kendi sözleriyle özet):

- **Kaynak ve taslak ayrılmasın.** "Taslak hazırla" denir. Her taslak kendiliğinden kaynaktır. Taslak geliştirilir, yayın elle yapılır.
- Bir notu **birden çok görsel ve PDF** destekleyebilir.
  - Not bu eklere kendi cümleleriyle atıf yapar ("2. görselde görüldüğü gibi…"). Ek bir bağlama mekanizması istenmiyor.
  - Okuyan kişi ekli tüm dosyalara ulaşabilmeli; yeterli olan bu.
- **Metis yalnız yazılı notu okur.** Görseller ve PDF'ler okunmaz, yapay zekâya gönderilmez, alıntı için kullanılmaz; yalnız açılıp indirilebilen eklerdir.
- Bilgi şirkette genellikle bu yolla gelir: bir açıklama + ekran görüntüleri ve PDF'ler.

## 2. Hedefler

1. "Yeni katkı" tek adım olur: başlık, kapsam, not ve ekler; ardından "Kaydet" (taslak) ve "Yayımla".
2. Bir taslağa tek seferde **birden çok** PNG/JPEG/PDF eklenebilir. Ekler tek tek kaldırılabilir ve yayımlanan bilgide **"Ekler"** bölümünde listelenir:
   - görseller küçük önizlemeyle, büyütülerek açılır;
   - PDF'ler adıyla, açılır ve indirilir.
3. Taslak kaydedilir, sonra yeniden açılıp geliştirilebilir. "Kayıtlar"da taslak olarak görünür. Bilgi havuzuna yalnız "Yayımla" ile girer. Yayın öncesi çelişki/tekrar kontrolü aynen çalışır.
4. Yazılı not, bilginin dayanağıdır (uzman beyanı). Mentor, arama ve çelişki kontrolü bu notu kullanır; ekleri kullanmaz.
5. İz paneli bu tür bilgide tek bir dayanak gösterir: "Uzman notu · yazan · tarih · ekler". Cümle cümle alıntı işaretleme istenmez.

## 3. Hedef olmayanlar

- Görsellerde/PDF'lerde yazı tanıma (OCR), PDF'ten metin çıkarıp alıntı yapma, eklerin modele gönderilmesi.
- Notun ekleri satır satır işaret etmesi için özel sözdizimi. Atfı yazar düz metinle yapar.
- Geçici yüklemelerin (taslağa eklenip hiç yayımlanmayan dosyaların) temizlenmesi: ayrı iş.

## 4. Anti-hedefler (çalışsa bile başarısızlık sayılır)

- Yazarın, notu yayımlamak için alıntı seçmek ya da iddia bağlamak zorunda kalması.
- Ekleri olan bir bilginin, okuyucuya hangi dosyaların ekli olduğunu göstermemesi ya da bir ekin indirilememesi.
- Yayımlanmış bir bilginin ya da ekinin sonradan sessizce değişebilmesi. Değişmezlik ilkesi korunur: değişiklik yeni sürümdür.
- Yetkisi olmayan birinin bir eke doğrudan bağlantıyla ulaşabilmesi (404 kuralı aynen).
- Görselin ya da PDF'in içeriğinin herhangi bir yolla yapay zekâya gitmesi.

## 5. Kısıtlar (projenin değişmez ilkeleri)

- **İnsan yayımlar, model yayımlamaz.** Varsayılan politika "Yazar yayımlar" + yayın öncesi kontrol (hash'e bağlı).
- **Revizyonlar değişmez:** ORM kancası + PostgreSQL trigger. Yeni tablolar da `IMMUTABLE_TABLES`'a girer.
- **Kaynaksız teknik iddia yok.** Bu tasarımda kaynak, yazarın notudur. İddialar notun birebir parçalarıdır; Mentor'un `claim.statement in evidence.excerpt` ve `validate_answer` kuralları değişmeden geçer.
- **Erişilemeyene 404.** Eklere erişim, ait oldukları bilgi revizyonunu okuma iznine bağlıdır.
- **İnternetsiz, CDN yok.** Önizleme ve görüntüleme tarayıcının kendi yeteneğiyle yapılır; PDF için ek kütüphane yok, dosya yeni sekmede ya da indirilerek açılır.
- **Yükleme güvenliği aynen:** uzantı + sihirli bayt denetimi (`sources/files.py`) ve dosya başına `METIS_MAX_UPLOAD_BYTES`. İndirme yanıtı `attachment` + `nosniff` + `CSP: sandbox`. Görsel önizlemesi için yalnız `image/png|jpeg` satır içi gösterilebilir.
- **Yedek/geri yükleme ve dışa aktarım** ekleri kapsamalı.

## 6. Kararlaştırılanlar (ürün sahibi)

- Kaynak adımı kalkar; "Taslak hazırla" tek giriş noktasıdır. Taslak = kaynak.
- Ekler: birden çok görsel ve PDF; yalnız ulaşılabilir dosyalar; Metis okumaz.
- Metis'in okuyacağı tek şey yazılı nottur. PDF'ten Metis'in taslak hazırlaması istenmiyor.
- İz'de bu tür bilgi için tek dayanak ("uzman notu · yazan · tarih · ekler") yöntemi kabul.
- **Eski yöntem tamamen kalkar (2026-10-19).** Kaynaktan alıntı seçerek yazma, demo içeriği ve v0.5.5 aktarımı artık kullanılmıyor; proje şirkette sıfırdan başlıyor. Tek editör, tek yöntem: not + ekler.
  - Bu karar, brief'teki "v0.5.5 verisi taşınacak" maddesini (Bölüm 5.10) geçersiz kılar.
  - Değişmeyen: kullanıcının yeni yöntemle girdiği her bilgi her güncellemede korunur. Yükseltme yedek alır, şemayı taşır, veri silmez.

## 7. Nasıl (önerilen yapı)

### 7.1 Veri

- **Bilgi ↔ not kaynağı (1:1).**
  - Bu yolla oluşturulan her bilgi sayfasının arkasında bir `Source(kind='note')` bulunur. Başlığı sayfanın başlığıdır ve sahibi ilk yazardır.
  - Sayfa ile not kaynağı arasındaki bağ bir alanla tutulur: `pages.note_source_id`, null olabilir; eski sayfalarda null.
  - Bu kaynak kaynak listelerinde ayrı bir kaynak olarak gösterilmez.
- **Not → kaynak revizyonu:** yayına hazırlanırken notun metni değişmez bir `SourceRevision` olur (text = not; `text/markdown`; extraction `complete`).
- **Otomatik iddialar:**
  - Not, boş satırlarla ayrılmış bloklara bölünür. Boş bloklar ve yalnız işaret içeren satırlar atılır.
  - Her blok bir `Claim(kind='expert_statement')` olur. Kanıtı, o bloğun not revizyonundaki birebir aralığıdır (`Evidence` char_start/char_end; statement == quote == excerpt).
  - Bölme deterministiktir; aynı not her zaman aynı iddiaları verir.
  - Blok başına sınır 8000 karakter (mevcut kanıt sınırı). Daha uzun blok cümle sınırından bölünür.
- **Ekler:** yeni değişmez tablo `page_revision_attachments`.
  - Alanlar: `page_revision_id`, `ord`, `sha256`, `filename`, `media_type`, `size_bytes`.
  - Bilgi revizyonuyla sürümlenir ve revizyon hash'ine girer. Ek listesi boşsa hash'e eklenmez; eski hash'ler geçerli kalır, figürlerdeki gibi.
  - Dosyalar mevcut içerik adresli blob deposunda (`core/blobs.py`) tutulur.
- **Taslak sırasında yükleme:** yeni değişebilir tablo `attachment_uploads`.
  - Alanlar: `id`, `project_id`, `uploader_id`, `sha256`, `filename`, `media_type`, `size_bytes`, `created_at`.
  - Yükleme anında blob yazılır. Taslak içeriği ekleri bu kimliklerle anar; revizyon yazılırken `page_revision_attachments` satırları kopyalanır.
  - Başkasının yüklemesi kullanılamaz (404).

### 7.2 Akış

1. **Yeni katkı → Taslak hazırla:** başlık, kapsam, not (düz metin/Markdown), "Dosya ekle" (çoklu seçim + sürükle-bırak; PNG/JPEG/PDF), özet (isteğe bağlı).
2. **Kaydet:** değişiklik kaydı (`ChangeSet`) taslak olarak oluşur ya da güncellenir.
   - Sayfa revizyonu notu (`body_md`) ve ekleri taşır, henüz iddiası yoktur (taslakta sıfır iddiaya bugün de izin var).
   - "Kayıtlar"da görünür ve yeniden açılabilir.
3. **Yayımla:**
   - Sunucu önce taslağı yayına hazırlar: not kaynak revizyonu, otomatik iddialar ve kanıtlar yazılır, yeni sayfa revizyonu ve yeni hash oluşur.
   - Sonra mevcut yayın öncesi kontrol (`/check`) ve doğrudan yayın (`/publish-direct`) aynen çalışır.
   - Kontrol uyarı verirse "Taslağa dön" ile düzenleme sürer; yeniden "Yayımla" yeni bir not revizyonu üretir.
4. **Var olan bilgiyi düzenleme:** not tabanlı bir bilgi açıldığında aynı editör gelir. Yayımlandığında aynı not kaynağına yeni revizyon eklenir.
5. **"Bağımsız inceleme" politikası** seçili projelerde: hazırlama adımı "incelemeye gönder"de yapılır; inceleyici hash'e bağlı onayı mevcut ekrandan verir.

### 7.3 Okuma

- **Bilgi sayfası:** not paragrafları bugünkü gibi gösterilir. Altta "Ekler" bölümü:
  - görseller küçük önizleme, tıklayınca büyür;
  - PDF'ler ad + boyut + "Aç".
- **İz paneli (not tabanlı bilgi):**
  - Başlık "Uzman notu · <yazan> · <tarih>" ve ilgili paragraf vurgulu.
  - Altta ek listesi.
  - "Yeni sürüm ekle" bağlantısı yerine "Bilgiyi düzenle".
- **Mentor/arama/çelişki kontrolü:** otomatik iddialar üzerinden değişmeden çalışır. Ekler bu yollara hiç girmez.
- **Dışa aktarım (Markdown ZIP):** ekler `ekler/<sayfa>/<dosya>` olarak eklenir ve bilgi dosyasında listelenir.
- **Yedek/geri yükleme:** ek blob'ları yedeğe girer. Geri yüklemede `page_revision_attachments.sha256` blob'ları da doğrulanır.

### 7.4 Yetki

- **Taslak:** yalnız yazar ve proje yöneticisi (steward) görür ve düzenler; bugünkü kural.
- **Yayımlanmış bilginin ekleri:** o revizyonu okuyabilen herkes. İndirme ucu revizyon okuma iznini denetler, değilse 404.
- **Ek yükleme:** katkı rolü (contributor) gerekir.

## 8. Eski yöntemin kaldırılması

İki aşamada yapılır: önce yeni akış (§7) çalışır hâle gelir, sonra eski yol kaldırılır.

**Üründen kalkanlar:**

- **"Yeni katkı"daki kaynak adımı.**
  - `SourceStep` ve kaynak seçimi kalkar.
  - Alıntı seçme/bağlama editörü kalkar: `DraftEditor`'daki kaynak görüntüleyici ve "Bu alıntıyı iddiaya bağla".
  - Taslaktaki satır içi figür seçici (`FigurePicker`) kalkar; yerine ekler gelir.
- **Kaynaklar ekranları ve İz'deki "Yeni sürüm ekle".** Kaynak kavramı kullanıcıya görünmez; not kaynakları arka planda kalır.
- **"Metis hazırlasın":** kaynaktan taslak hazırlayan Metis görevleri (`worker/prepare`, `worker/refine`) ve bunların arayüzü kalkar.
  - "Metis görevleri" ekranında yalnız bilgi havuzu denetimi gibi kalan işler görünür.
  - Ekranın içinin boşaldığı durumda menüden kaldırılması → builder kararı.
- **v0.5.5 aktarımı:**
  - `legacy_import` modülü, `metis import-v1` komutu ve Ayarlar → "v0.5.5 aktarımı" sekmesi kalkar;
  - testleri ve belgeleri de birlikte kalkar.
- **Demo içeriği:**
  - Başlatıcıdaki "kurgusal örnek içerik eklensin mi?" sorusu kalkar;
  - kurulum betiklerindeki ve belgelerdeki `metis demo` anlatımı kalkar;
  - kurgusal çalışma alanı uyarı bandı ve `is_demo` ayrımı ürün arayüzünden kalkar.
- **Mentor cevabından taslak** ("Bu cevaptan taslak oluştur"): kalkar. Model metni uzman notu olamaz; cevaptaki bilgiyi bir uzman kendi notuyla yazar.

**Kalanlar:**

- Bilgi sayfası, İz, Mentor, arama, kavram haritası, yayın öncesi kontrol, bilgi sağlığı (bakım taraması), kayıtlar, yedek/geri yükleme, Model laboratuvarı.
- **Geliştirme ve testler için kurgusal tohum:**
  - Testler ve görsel/e2e denemeler kurgusal veriye ihtiyaç duyar (CLAUDE.md: denemeler kurgusal veriyle). Kurgusal tohum yeni yönteme (not + ekler) çevrilerek yalnız geliştirme/test aracı olarak kalır.
  - Kurulu üründe çalıştırılamaz ve kurulum betiklerinden çağrılmaz.

**Veritabanı:**

- Kullanılmayan tablolar ve sütunlar bu işte silinmez; şema değişikliği yalnız eklemedir. Örneğin `legacy_import_runs` ve alıntılı iddiaların tabloları ileride ayrı bir temizlikle ele alınır.
- Yeni yönteme geçmeden önce yayımlanmış bilgi yok. Demo çalışma alanı olan kurulumlarda yükseltme demo projesini **silmez**; demo projesi yalnız arayüzde görünmez olur. Silme geri alınamaz, kullanıcı verisiyle karışma riskini almıyoruz.

**Şirket kurulumundaki mevcut kaynak:**

- Ürün sahibinin şirkette girdiği tek kayıt, bir sayfaya bağlanmamış bir uzman notu kaynağı (metin + bir görsel).
- Yükseltmede bu tür bağımsız kaynaklar kendiliğinden **taslağa dönüştürülür**: metin → not, dosya → ek. Böylece kullanıcının girdiği hiçbir şey kaybolmaz ve "Kayıtlar"da taslak olarak görünür.

## 9. Builder'a bırakılanlar

- Blok bölme kurallarının ayrıntısı:
  - başlık satırları ayrı blok mu, liste maddeleri tek blok mu;
  - deterministik olması ve iddiaların notun birebir parçaları olması şartıyla.
- Ek sayısı üst sınırı (öneri: taslak başına 30) ve toplam boyut sınırı.
- Ekler bölümünün görsel tasarımı ("İz" tasarım dili: altın yalnız kanıt için; iki tema; 12 px altı yazı yok).
- API uçlarının adları ve şema ayrıntıları; OpenAPI ve TS tiplerinin yeniden üretimi.
- Mevcut e2e testlerinin (`setup-source-iz`, `figures`, `review-flow`) yeni akışa uyarlanması ya da eski yol için korunması.

### 9.1 Benim kararlarım (ürün sahibi okurken denetlesin)

- **Sayfa türü, bilinmeyenler, arama adları:** yeni formda kalır, "Diğer alanlar" altında katlı durur (rc.2'deki "isteğe bağlı alanlar katlı" ilkesi). Varsayılan tür bugünkü gibi.
- **Kendi notunun yeni revizyonu "kaynak değişti" sayılmaz:**
  - not tabanlı sayfanın kendi not kaynağına yayın sırasında eklenen revizyon, o sayfa için `dependency_changed` ya da `source_changed` bulgusu üretmez;
  - `sources/service.py:mark_dependents` ve `health/maintenance.py` bu durumu dışarıda bırakır.
- **Yayımlanmamış taslağın erişimi:** taslağın not kaynağı ve yüklenen ekleri yalnız şu kişilerce görülebilir: taslağın yazarı, proje yöneticileri (steward) ve inceleyiciler (reviewer). İnceleyiciler listede, çünkü "Bağımsız inceleme" politikasında taslağı açabilmeleri gerekiyor. İddiasız taslak revizyonu bugün her üyeye açık; bu da kapatılır.
- **İddialar listesi gizlenir:** not tabanlı sayfada "İddialar" listesi gösterilmez, çünkü gövdeyle aynı metni tekrarlardı. Paragraf işaretleri ve İz kalır.

- **Kaldırma kapsamı (§8):** Mentor'dan taslak, demo yerine kurgusal geliştirme tohumu, veritabanında silme yerine gizleme, bağımsız kaynakların taslağa dönüştürülmesi.

## 10. Açık sorular

Yok: eski sayfalar sorusu ürün sahibinin kararıyla kapandı (§6, §8).
