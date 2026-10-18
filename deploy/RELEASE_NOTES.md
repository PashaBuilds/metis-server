METIS v2 sunucu kurulum paketi (Windows, internetsiz). Dosya: `METIS-<sürüm>-server-win64.zip`; yanındaki `.sha256` ile doğrulanabilir.

**Kurulum:** ZIP'i aç, `BASLA.txt` ve `KURULUM.md` dosyalarını oku. Önkoşul: PostgreSQL 16.
Türkçe Windows'ta PostgreSQL kurulumunun **Locale** adımında `English, United States` seç; varsayılan bölge ayarı
veritabanı kümesinin oluşturulmasını bozuyor ("database cluster initialisation failed").

**rc.6 — gerçek modelle (DeepSeek) doğrulama ve düzeltmeler:**
- Herkese açık DeepSeek API'siyle (V4.1 Flash ve V4 Pro), yalnız kurgusal veriyle uçtan uca denendi: bağlantı testi,
  benchmark, Mentor, Metis görevleri, bakım taraması, yayın öncesi kontrol, 60 eşzamanlı istek ve hata durumları.
  Şirket içi DeepSeek V4 Flash ile henüz denenmedi.
- Mentor: kapsam artık her durumda kayıtlardan denetlenir; model kapsamı uymayan bir kaynakla cevap verirse cevap
  kullanılmaz ("Kapsamı netleştirelim"). Önceden iki DeepSeek modeli de bu yüzden benchmark'ta "uygun değil" çıkıyordu.
- Mentor: aramada yalnız yan sonuç olarak çıkan, çelişkili bir bilgi soruyu artık "Çelişkili" yapmıyor; çelişkili bilgi
  soruyla ilgiliyse yine "Çelişkili" denir. Model yokken bu durumda dürüstçe "Model kullanılamıyor" denir.
- Yayın öncesi kontrol: başka karta/projeye ait bilgi artık "çelişebilir" ya da "tekrar" sayılmıyor; ilgisiz bilgilerin
  "tekrar" sanılması düzeltildi (sayfa karşılaştırma talimatı netleştirildi).
- Metis görevleri: uzun kaynaklar bölümlere ayrılarak işlenir (önceden ≈50'den çok olgulu belgede görev başarısız
  oluyordu); taslak başına 200 iddia sınırı aşılırsa bu açıkça yazılır. "Taslağı düzenle" artık başlık ve özet önerir
  (iddialarla denetlenir) ve yazarın talimatını dikkate alır; özet bir sistem metniyle ezilmez.
- Yük: çok sayıda eşzamanlı Mentor sorusunda veritabanı bağlantı havuzu tükeniyordu (42 eşzamanlı soruda hata);
  düzeltildi. Yeni sağlayıcılarda aynı anda en çok 4 model isteği (önceden 2).
- Model laboratuvarında benchmark satırında "kapsam düzeltmesi" sayısı gösterilir.
- Şema değişmedi.

**rc.5 — düzeltme ve güncel örnek içerik:**
- Düzeltme: "Bilgilerin güncellendi" bildirimi, başkası yalnız ilgisiz bir bilgiyi yayımladığında da sahibinin tüm
  bilgilerini listeliyordu (rc.4). Artık yalnız gerçekten değişen bilgi gösterilir.
- `metis demo` örnek içeriği güncel akışı yansıtır: bilgiler yazarlarınca yayımlanmış ("Yayımlayan"), biri metin içi
  görselli; yarım bir taslak (Yayımla ile yayımlanır); yayımlanırken bilerek geçilmiş bir çelişki (Bilgi sağlığında);
  `deniz` için "Bilgilerin güncellendi" örneği. İncelemede bekleyen kayıt yok.
- Şema değişmedi.

**rc.4 — yazar yayımlar, yayın öncesi kontrol:**
- İkinci kişinin onayı kalktı (varsayılan politika "Yazar yayımlar"): taslağını yazan kişi "Yayımla" ile kendisi yayımlar.
- "Yayımla"ya basınca Metis taslağı yayındaki bilgilerle karşılaştırır: kural kontrolü (aynı ifade, farklı değer, örtüşen
  kapsam) ve bağlı yapay zekâ modeli varsa anlam kontrolü (çelişki, tekrar, aynı konu). Sorun yoksa hemen yayımlanır; varsa
  "Yayımlamadan önce bak" penceresi iki tarafı yan yana gösterir: "Taslağa dön" ya da "Yine de yayımla". Bilerek geçilen
  çelişki Bilgi sağlığına kaydedilir. Model yoksa ya da yanıt vermezse bu açıkça yazılır, kural kontrolüyle yayımlanabilir.
- Başkasının bilgisini güncellersen de doğrudan yayımlarsın; bilginin sahibi ana sayfada "Bilgilerin güncellendi"
  bildirimini görür ("Gördüm" ile kapanır).
- Bilgi sayfasında "Yayımlayan: …". Ayarlar → Yayın politikası'ndan "Bağımsız inceleme" seçilirse eski akış aynen geçerli.
- Model ve worker yine hiçbir şey yayımlamaz; yayın her zaman bir kişinin eylemidir ve içerik hash'ine bağlı kaydedilir.
- Şema 0004: mevcut projeler "Yazar yayımlar" politikasına geçer (yöneticiler Ayarlar'dan değiştirebilir); `upgrade.ps1`
  geçişi kendiliğinden uygular.

**rc.3 — açıklayıcı görseller:**
- Bilgi taslağına görsel eklenebilir (Yeni katkı → Kendim yazayım → "Görsel ekle"): var olan bir görsel kaynağı seç ya da
  PNG/JPEG yükle, açıklama yaz. Görsel bilgi sayfasında metnin içinde, açıklamasıyla görünür; tıklayınca büyür.
- Görsel açıklayıcıdır, kanıt sayılmaz; inceleme ve onaydan geçer, onaydan sonra değiştirilemez (değişiklik yeni sürümdür).
  Kaynağına erişimi olmayan kişi sayfayı göremez. Kaynak panelinde görsel kaynaklar önizlenir; Markdown dışa aktarımına
  görseller de girer.
- Veritabanına bir tablo eklendi (şema 0003); `upgrade.ps1` geçişi kendiliğinden uygular.

**rc.2 — arayüz sadeleştirmesi:**
- Yeni renk paleti (lehim yeşili + turkuaz): eylem ve seçimler turkuaz, uyarılar turuncu; altın yalnız kanıt için.
- İnceleme: tek düğme "Onayla ve yayımla" (insan onayı, gerekçe ve kontrol kutusu aynen).
- Yeni katkı: kaynak eklenince iki yol (Metis hazırlasın / Kendim yazayım) hemen altında; projede kaynak yoksa form
  doğrudan açılır; isteğe bağlı alanlar katlı.
- Üst çubuktaki kapsam seçici kaldırıldı; kapsam yalnız onu kullanan yerlerde (soru kutusu, Mentor, Harita).
- Yöneticiye ana sayfada kurulum listesi (model, kapsam değerleri, ekip); tamamlananlar gizlenir.
- Ayarlar'da yalnız kişinin kullanabildiği sekmeler; yoğunluk ayarı kaldırıldı; tek projede proje seçici yok.
- Bilgi havuzu ve Kavram haritasında ek filtreler "Diğer filtreler" altında; Görevler'deki yinelenen denetim kartı
  kaldırıldı (tarama Bilgi sağlığından).
- Teknik terimler sade Türkçeye çevrildi ("Güncel sürüme taşı", "Otomatik (önerilen)", "Yazarı kendisi onayladı" vb.);
  beklenmeyen hatalarda hata kimliği gösterilir.
- rc.2'de veritabanı şeması değişmedi.

**Kendi bilgisayarında deneme (Windows 10/11, IIS olmadan):** yönetici PowerShell ile
`powershell -ExecutionPolicy Bypass -File .\install-offline.ps1 -PublicUrl http://localhost:8000 -AllowHttp`,
sonra tarayıcıda `http://localhost:8000`. Örnek içerik: `C:\METIS\bin\metis demo`. Kaldırma: `uninstall.ps1 -RemoveAll`.

**Doğrulama:** bu paket CI'da Windows Server 2022 üzerinde ağ kapalıyken kuruldu; giriş, servis yeniden başlatma, yedek,
geri yükleme tatbikatı, örnek içerik, yükseltme ve kaldırma denendi.

**Henüz denenmedi:** gerçek şirket sunucusu (IIS/ARR + TLS), Windows 10/11 masaüstünde paketin kendisi, şirket modeliyle bağlantı,
gerçek v0.5.5 yedeğinin aktarılması. Tire içeren sürümler (ör. `-rc.1`) pilot amaçlı ön sürümdür.
