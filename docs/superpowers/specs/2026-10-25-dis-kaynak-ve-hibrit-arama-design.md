# Dış kaynaktan taslak ve hibrit arama — tasarım (2026-10-25)

Ürün sahibinin isteği ve onayıyla. Araştırma dayanağı Git dışında (`devir/reports/Hibrit bilgi arama mimarisi.md`);
bu belge onun METIS'e uyarlanmış kararlarıdır. "**Benim kararım**" işaretli maddeler ajanın kararıdır, ürün sahibi
değiştirebilir.

## 1. Amaç ve neden

- **GitLab issue'ları** "bunu daha önce nasıl çözdük?" hafızasıdır: başka ekibin açıp bizim çözdüğümüz sorunlar,
  kendine issue açıp adım adım not düşen kişilerin işleri. Bilgi konuşmanın içindedir (soru, yorumlar, çözüm).
- **Confluence sayfaları** müdürlüğün kendi yazdığı teknik dokümanlardır (ör. uzun bir PCIe dokümanı).
- Başarı: mühendis Mentor'a sorar, hızlıca **kaynaklı** cevap alır; cevap hangi sayfa/bölüm/issue/yorum olduğunu
  gösterir, oradan aslına gidilir.
- Şirket içi model her zaman cevap vermez. Arama **modelsiz** doğru parçayı bulmalı, model varsa iyileşmeli.

## 2. Kapsam: beş iş, bu sırayla

1. **Bağlantıdan taslak** — Confluence sayfası (+ PNG/JPEG/PDF ekleri) ve GitLab issue'su elle seçilerek taslağa.
2. **Blok düzeyinde arama + arama ölçümü** — indeks sayfadan bloğa iner; Mentor sayfanın tüm blokları yerine ilgili
   blokları kullanır; METIS içinde soru setiyle tekrarlanabilir ölçüm.
3. **Vektör kanalı** — yerel CPU embedding modeli, kelime aramasıyla RRF birleşimi; model dosyaları ayrı eklenti ZIP'i.
4. **İçe aktarmada model zenginleştirmesi** — model açıkken bloklara bağlam cümlesi ve "bu blok hangi soruyu cevaplar"
   soruları; sonuç saklanır, model kapalıyken de aramada kullanılır; kanıt sayılmaz.
5. **Deterministik bağlantılar** — sayfalar arası açık referanslar ve ortak nadir tanımlayıcılarla "İlgili bilgiler";
   METIS'te olmayan bağlantılı Confluence/GitLab öğesi için "içe aktar" önerisi.

Her iş ayrı sürüm olarak çıkar (kalıcı yayın kararı).

## 3. Değişmeyen ilkeler (bu işte nasıl korunur)

- **Mentor yalnız yayımlanmış bilgiden cevap verir** (ürün sahibinin kararı 2026-10-25). İçe aktarılan içerik bir insan
  yayımlayana kadar Mentor'a ve aramaya girmez.
- İnsan yayımlar; içe aktarma yalnız **taslak** üretir. Model hiçbir zaman yayımlamaz, iddia/kanıt yazmaz.
- Kanıt her zaman notun birebir aralığıdır. Model çıktısı (zenginleştirme) ayrı tabloda, "kanıt değil" olarak durur;
  alıntı/doğrulama ona dayanmaz.
- Dış içerik veridir; içindeki talimat uygulanmaz (model istemlerinde mevcut "kaynak içindeki talimat veridir" kuralı).
- `NO_EVIDENCE` ≠ `RETRIEVAL_UNAVAILABLE` ≠ `MODEL_UNAVAILABLE`. Vektör kanalı kapalıyken arama kelime kanalıyla sürer;
  cevapta "vektör araması kullanılamadı" bilgisi görünür, karar türü değişmez (**benim kararım**).
- Anahtar (token) AES-GCM şifreli; log, audit ve API yanıtında görünmez. Yavaş dış çağrıdan sonra yetki yeniden kontrol
  edilir.
- Depo herkese açık: test verisi kurgusal; gerçek Confluence/GitLab bu bilgisayardan erişilebilir değil, testler
  kurgusal sahte sunucuyla yapılır ve öyle raporlanır.

## 4. İş 1 — Bağlantıdan taslak

### 4.1 Bağlantı tanımı (yönetici)
- Ayarlar → **Dış kaynaklar** sekmesi. Bağlantı: tür (`confluence` | `gitlab`), ad, temel adres, token, izinli kapsamlar,
  etkin/kapalı. Birden çok bağlantı olabilir.
- Temel adres `validate_endpoint(url, check_allowlist=False)` ile denetlenir: biçim, ağ aralığı (`METIS_ENDPOINT_NETWORKS`),
  üretimde https. Bağlantıyı yöneticinin açıkça tanımlaması izin sayılır; model izin listesine eklenmez (**benim kararım**).
- **İzinli kapsamlar zorunlu** (**benim kararım**): Confluence için alan anahtarları (`DOC`, `BSP`…), GitLab için proje
  yolları (`grup/proje`). Token'ın gördüğü ama listede olmayan içerik alınamaz (`EXTERNAL_SCOPE_NOT_ALLOWED`).
- **Yetki modeli** (**benim kararım**): bağlantı başına tek token (bu iş için açılmış okuma hesabı). Kaynak sistemde
  **görüntüleme kısıtı olan Confluence sayfaları** (`restrictions.read`) ve **gizli (confidential) GitLab issue'ları**
  varsayılan olarak alınmaz (`EXTERNAL_RESTRICTED`); bunlar yayımlanınca projenin tüm üyelerine açılırdı. Kişi başına
  token yok; içe aktaranın kaynak sistemdeki yetkisi ayrıca sınanmaz (izinli kapsamlar + kısıtlı içerik reddi bunu sınırlar).
- Bağlantılar ve izinli kapsamlar tüm METIS projelerinde kullanılabilir; proje eşlemesi yok (**benim kararım**, tek
  müdürlük kurulumu).
- "Bağlantıyı dene": Confluence `GET /rest/api/user/current`, GitLab `GET /api/v4/user`; kaydetmez. Sonuç: tamam /
  yetkisiz / ulaşılamadı / TLS hatası.
- Kimlik doğrulama: Confluence Server/Data Center kişisel erişim anahtarı `Authorization: Bearer`; GitLab
  `PRIVATE-TOKEN`. Şirket CA'sı `METIS_CA_BUNDLE`.
- HTTP: `httpx`, `trust_env=False`, yönlendirme izlenmez, toplam süre sınırı (30 sn), yanıt gövdesi sınırı (JSON 8 MiB,
  ek dosyası `METIS_MAX_UPLOAD_BYTES`). Ek indirme adresi bağlantının temel adresiyle aynı kökenden olmalı.

### 4.2 Kullanım (katkı sahibi)
- Yeni katkı → **Kaynaktan al**. İki yol: bağlantı yapıştır, ya da bağlantı seçip başlıkla ara (Confluence CQL
  `type=page AND space in (izinliler) AND title ~ "…"`, GitLab izinli projelerde `issues?search=`; ilk 20).
- "Önizle" → sunucu çeker, dönüştürür, ekleri METIS eki olarak yükler (kullanıcı adına), bir **içe aktarma kaydı**
  (`external_imports`) yazar ve önizleme döner: başlık, not metni, ekler, atlananlar, köken.
- "Taslağa çevir" → mevcut taslak formu bu değerlerle dolar; kullanıcı düzenler, "Taslağı kaydet" / "Yayımla" her zamanki
  akış (yayın öncesi kontrol dahil). Taslak öğesi `import_id` taşır; sunucu kaydın bu kullanıcıya ve projeye ait
  olduğunu, kullanılmadığını denetler.
- Rol: projede katkı sahibi (ek yüklemeyle aynı). Yalnız insan.

### 4.3 Köken ve tekrar alma
- Tablo `external_origins`: proje, bağlantı, dış anahtar (Confluence: `confluence:<sayfa id>`, GitLab:
  `gitlab:<proje id>#<iid>`), adres, son sürüm (Confluence `version.number`, GitLab `updated_at`), sayfa. Proje başına
  dış anahtar tekil.
- Taslak kaydedilince köken sayfaya bağlanır. Aynı öğe tekrar önizlenirse önizleme mevcut sayfayı söyler; arayüz
  "Var olan bilgiyi aç" ve "Güncelleme taslağı hazırla" sunar (ikincisi mevcut düzenleme akışıyla `page_id` +
  `base_revision_id`).
- Güncelleme taslağı notu baştan, yeni dönüştürmeyle doldurur. Kökende son içe aktarılan not metninin hash'i saklanır;
  yayındaki not bundan farklıysa (METIS'te elle düzenlenmiş) form üstünde uyarı çıkar: "Bu bilgi içe aktarıldıktan sonra
  METIS'te değiştirilmiş; yeni taslak o değişiklikleri içermez. Geçmişten karşılaştırın." Otomatik birleştirme yok
  (**benim kararım**).
- Bilgi sayfasında "Kaynak: Confluence/GitLab — <adres> · sürüm · alınma tarihi" satırı.
- Kaynak değişince haber verme bu işin dışında (sonraki iş); sürüm bilgisi bunun için saklanır.

### 4.4 Confluence sayfası → not
- `GET /rest/api/content/{id}?expand=body.storage,version,space,ancestors`. Adres biçimleri:
  `…/pages/viewpage.action?pageId=N`, `…/spaces/KEY/pages/N/…`, `…/display/KEY/Başlık` (başlıkla arama), `?pageId=N`.
- Depolama biçimi (XHTML, `ac:`/`ri:`) standart kütüphaneyle Markdown'a: başlıklar, paragraflar, kalın/eğik/kod, listeler
  (iç içe), tablolar (Markdown tablo; birleşik hücre düzleşir), `code` makrosu → çitli kod bloğu, bilgi/uyarı/not panelleri
  → alıntı bloğu, `expand` → başlık + içerik, görsel (`ac:image` + `ri:attachment`) → `[Görsel: ad.png]` işareti,
  sayfa bağlantısı → metin + (varsa) adres, desteklenmeyen makrolar (`toc`, `children`, `jira`…) → atlanır ve
  atlananlar listesine yazılır.
- Uzun sayfa **bölünmez** (**benim kararım**): iş 2'deki blok indeksi doğru bölümü bulur; bölmek inceleme yükünü artırır.
  Not sınırı 200 000 karakter; aşılırsa `EXTERNAL_TOO_LARGE` (karakter sayısıyla).
- Ekler: `child/attachment` (sayfalı). PNG/JPEG/PDF ve dosya başına sınır içindekiler alınır; önce gövdede geçenler,
  en çok 30. Diğerleri "atlandı" (neden: tür / boyut / sınır) ve Confluence adresiyle listelenir. Ekler okunmaz (bugünkü
  ilke).

### 4.5 GitLab issue'su → not
- `GET /api/v4/projects/{yol}/issues/{iid}` + notlar (`/notes?sort=asc&order_by=created_at`, sayfalı). `system=true`
  notlar (etiket eklendi vb.) atlanır.
- Not biçimi: üstte "Durum · Etiketler · Açan · tarih", sonra açıklama, sonra `## Yorumlar` ve her yorum için
  `### <ad> — <tarih>` başlığı + gövde. Yorumlar başlıklı olduğu için iş 2'de her yorum ayrı blok/bağlam taşır.
- Gövdedeki yüklemeler (`/uploads/<gizli>/<dosya>`): PNG/JPEG/PDF ise `GET /api/v4/projects/{id}/uploads/{gizli}/{dosya}`
  ile alınmaya çalışılır; olmazsa "atlandı".
- Adres biçimleri: `…/<grup>/<proje>/-/issues/<iid>` ve `…/<grup>/<proje>/issues/<iid>`.
- Kişi adları şirket içi kurulumda veridir; kod, test ve belgelerde kurgusal adlar.

## 5. İş 2 — Blok düzeyinde arama ve arama ölçümü

### 5.1 Blok indeksi
- Yeni tablo `search_passages`: yayındaki her revizyonun her iddiası (not bloğu) bir satır — sayfa, revizyon, yayın,
  iddia, sıra, **başlık yolu** (notun önceki `#` başlıklarından: "PCIe › Bağlantı eğitimi › LTSSM"), gövde, semboller,
  kapsam, tür, `tsv_simple`, `tsv_turkish`. `index_pages` sayfa satırıyla birlikte aynı işlemde yeniden kurar.
- İndeks metni: sayfa başlığı (A) + başlık yolu (B) + gövde (C); alıntı yalnız gövde aralığıdır.
- `simple` kanalında I/ı/İ/i tek kurala katlanır (indeks ve sorguda aynı Python işlevi); `turkish` kanalı Türkçe harflerle
  kalır (**benim kararım**; ölçümle sınanır).

### 5.2 Arama ve Mentor
- Arama blokları puanlar (sembol birebir isabeti sabit üstte, başlık/alias, iki FTS kanalı); sayfa puanı en iyi bloklarından
  gelir; sonuç sayfa listesi + her sayfanın en iyi bloğundan önizleme. Var olan `SearchOut` biçimi korunur, alanlar eklenir.
- Mentor her aday sayfa için **tüm iddialar yerine ilgili blokları** alır: sayfa başına en iyi 6 blok + her birinin
  komşusu ve bağlı olduğu başlık bloğu, paket toplamı en çok 40 iddia (**benim kararım**; sayılar ölçümle ayarlanır).
  Kısa sayfa (≤ 8 blok) olduğu gibi girer.
- **Model yokken Mentor** (**benim kararım**): karar yine `MODEL_UNAVAILABLE`; ama yanıt artık yalnız ilgili sayfa listesi
  değil, **ilgili bölümleri** de taşır (en iyi 5 yayımlanmış blok, sayfa + başlık yolu + birebir metin). Arayüz bunları
  "Model yanıt vermedi. Bu bir cevap değil; sorunla ilgili yayımlanmış bölümler:" başlığıyla gösterir. Cümle üretilmez,
  doğrulayıcıdan geçmiş bir cevap gibi sunulmaz.

### 5.3 Arama ölçümü (METIS içinde)
- Yönetici ve proje sorumlusu, proje başına **soru seti** kurar: soru + beklenen sayfa(lar) + isteğe bağlı beklenen alıntı
  (blok gövdesinde geçmesi gereken metin; revizyon değişse de çalışır) + tür etiketi (tanımlayıcı / kavram / nasıl / issue).
- "Ölçümü çalıştır" deterministik: her soru mevcut aramayla (ve iş 3'ten sonra seçilen kanal ayarlarıyla) koşar;
  sayfa için recall@5, recall@10, MRR, nDCG@10; alıntı için "ilk 5'te"; tür kırılımı; soru başına sıra. Sonuç saklanır,
  önceki koşuyla yan yana gösterilir.
- Gerçek sorular sunucuda, veritabanında durur; depoya girmez. Depoda kurgusal Türkçe/İngilizce derlem + soru seti
  (`evals/retrieval/`) aynı ölçümü testte ve geliştirmede çalıştırır.
- Yer: Lab → **Arama ölçümü** (yönetici ve sorumlu görür).

## 6. İş 3 — Vektör kanalı

- Model: `intfloat/multilingual-e5-small` ya da `-base` (MIT), ONNX, CPU. Seçim bu bilgisayarda ölçümle: kurgusal
  sette kalite ve CPU hızı; varsayılan small, base anlamlı fark verirse base (**benim kararım**).
- Çalışma zamanı: `onnxruntime` + `tokenizers` + `numpy` ana pakete (wheelhouse; Windows cp312 wheel'leri var).
  **Model dosyaları ayrı eklenti ZIP'i**: `METIS-<sürüm>-vektor-modeli.zip` (model, tokenizer, lisans, SHA256SUMS, kurulum
  betiği `vektor-modeli-kur.ps1` → `C:\METIS\models\<model>`; `metis.env`'de `METIS_EMBEDDING_MODEL_DIR`; servisleri
  yeniden başlatır). Model ZIP'i yoksa METIS aynen çalışır, kanal "kurulu değil".
- Model ZIP'i yalnız model değişince yeniden derlenir; adı METIS sürümünden bağımsızdır
  (`METIS-vektor-modeli-<model>-<n>.zip`). İlk çıktığı GitHub sürümüne ikinci dosya olarak eklenir; sonraki sürüm notları
  ona bağlantı verir. `-Derle`/`-Yayimla` ona dokunmaz; ayrı `scripts\vector-model.ps1` derler, özetini yazar, isteğe
  bağlı yükler (**benim kararım**). Kurulum denemesi ana paketteki gibi; UAC onaylanamazsa istisna notu.
- Vektör saklama: `passage_vectors` (model kimliği + blok metni hash'i → float16 vektör). Aynı metin yeniden
  hesaplanmaz. pgvector **kullanılmaz** (**benim kararım**): Windows'ta hazır ikili yok, beklenen ölçekte (≤ 500 bin blok)
  süreç içi numpy taraması milisaniyeler sürer; yetki ve kapsam filtresi aynı SQL satırlarından gelir. Ölçek aşılırsa
  yeniden değerlendirilir.
- Hesaplama worker'da: yayın sonrası iş kuyruğa girer (`embed_passages`), eksik vektörleri toplu hesaplar; ilk kurulumda
  tüm yayın. API süreci sorgu vektörünü kendi hesaplar (model süreç başına bir kez yüklenir), proje matrisini bellekte
  tutar ve her aramada ucuz bir sürüm sayacıyla tazeler.
- Birleştirme: sembol isabeti sabit üstte; kelime ve vektör blok sıralamaları RRF (k=60) ile. Ayarlar (kanal açık/kapalı,
  k) arama ölçümünde karşılaştırılabilir.
- Durum: Ayarlar → Sistem durumu ve Lab'da "Vektör arama: kurulu değil / hazırlanıyor (n/m) / açık". Arama yanıtında
  `dense: available | unavailable | partial`.

## 7. İş 4 — İçe aktarmada model zenginleştirmesi

- Kapsam (**benim kararım**): **yalnız yayımlanmış** bloklar (elle yazılmış ve içe aktarılmış hepsi); yayımlanmamış içerik
  modele gönderilmez. İlk açılışta tüm yayın düşük öncelikle, tek eşzamanlı çağrıyla, iş başına en çok 50 blokla taranır;
  sonra yalnız yeni/değişen bloklar.
- Görevler (blok başına): **bağlam cümlesi** (blok sayfanın neresinde, ne hakkında; 1–2 cümle) ve **sorular** (bloğun
  cevapladığı en çok 3 soru). Süzgeç deterministik: sorudaki her tanımlayıcı (sembol/hex) blok gövdesinde birebir geçmeli,
  boş/aşırı uzun çıktı atılır.
- Saklama `passage_enrichments`: (blok metni hash'i, görev, model, istem sürümü) anahtarlı; idempotent; model çağrıları
  mevcut `ModelClient` ve `model_calls` kaydıyla. Kanıt değildir; arayüzde "Metis notu" olarak bile gösterilmez, yalnız
  aramada kullanılır (**benim kararım**).
- Arama: zenginleştirme metni `tsv` D ağırlığında ve vektör girdisinde (başlık yolu + bağlam + gövde). Zenginleştirme
  gelince blok yeniden indekslenir/vektörlenir.
- İş türü `enrich_passages` (sistem işi, düşük öncelik). Model yoksa iş bekler; art arda hata → geri çekilme (devre kesici
  benzeri); arama zenginleştirmesiz sürer. Proje ayarı: zenginleştirme açık/kapalı (varsayılan açık, model yoksa etkisiz).

## 8. İş 5 — Deterministik bağlantılar

- Yayında, her sayfa için kenarlar (`page_links`, yayınla yeniden kurulur): (a) nottaki Confluence/GitLab adresleri ve
  `#123`/`grup/proje#123` referansları → `external_origins` ile METIS sayfasına; (b) iki sayfanın ortak **nadir**
  sembolleri (proje içinde en çok N sayfada geçen; IDF ağırlıklı, eşik üstü).
- Bilgi sayfasında **İlgili bilgiler** (kenar türü ve gerekçesiyle: "aynı issue'ya bağlanıyor", "ortak: `LTSSM_STATE`").
- METIS'te karşılığı olmayan dış adres → sayfada "Bağlantılı, METIS'te yok: <adres> · İçe aktar" (katkı sahibine).
- Mentor ve arama: ilgili sayfalar yalnız "ilgili" listesinde önerilir; kanıt paketine kendiliğinden girmez.
- Model önerili bağlantı ve sentez sayfaları bu kapsamda yok (sonraki iş).

## 9. Hedef dışı / sonraki işler

Otonom eşitleme (alan/etiket), kaynak değişince "kaynak değişti" bulgusu, eklerin okunması (PDF/Word/görsel), GitLab
merge request ve wiki, model önerili bağlantı/iddia/sentez sayfaları, pgvector, CPU reranker, Confluence Cloud.

## 10. Doğrulama

- Her iş için önce kırmızı sonra yeşil API testleri (kurgusal sahte Confluence/GitLab HTTP sunucusu, izole PG), arayüz
  için tarayıcı denetimi (geliştirme yığını), arama işleri için kurgusal ölçüm setinde önce/sonra rakamları.
- Gerçek Confluence/GitLab ile deneme ürün sahibinde (sanal makine); sürüm notunda "denenmedi" diye yazılır.
- Sürüm başına `-Derle` + CI + kısmi yükseltme denemesi + `-Yayimla`.
