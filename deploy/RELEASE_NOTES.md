METIS sunucu kurulum paketi (Windows, internetsiz). Dosya: `METIS-<sürüm>-server-win64.zip`; yanındaki `.sha256` ile doğrulanabilir.

**Kurulum:** ZIP'i aç, `BASLA.txt` ve `KURULUM.md` dosyalarını oku. Önkoşul: PostgreSQL 16.
Türkçe Windows'ta PostgreSQL kurulumunun **Locale** adımında `English, United States` seç; varsayılan bölge ayarı
veritabanı kümesinin oluşturulmasını bozuyor ("database cluster initialisation failed").

**2.0.9 — şirket modelini arayüzden ekleme:**
- Model laboratuvarında **Sağlayıcı ekle** dediğinde adrese henüz izin verilmemişse METIS bunu söyler ve
  **İzin ver ve ekle** ile izin verirsin. `metis.env`'e elle adres eklemek ve servisleri yeniden başlatmak gerekmez.
- İzinli adresler **Ayarlar → Sistem durumu → İzinli model adresleri** altında: `metis.env`'dekiler "Sunucu ayarı"
  olarak, arayüzden eklenenler kimin eklediği ve kullanan sağlayıcı sayısıyla. Kullanılmayan adresin izni kaldırılabilir.
- Güvenlik kuralları aynı: yalnız yöneticiler izin verir; yalnız iç ağ adreslerine izin verilir; sunucu kurulumunda
  adres `https://` olmalı; her izin denetim kaydına yazılır ve yedekle taşınır.
- Şema 0005 (izinli adresler tablosu); yükseltme geçişi kendiliğinden uygular.
- Bu ZIP yerel Windows 10 bilgisayarda derlendi ve çift tıklamayla 2.0.8 → 2.0.9 yükseltmesiyle denendi.

**2.0.8 — başlatıcı düzeltmesi (çift tıklayınca "hiçbir şey olmuyordu"):**
- Düzeltme: 2.0.7'de `METIS-Baslat.exe` çalışıyordu ama soruları ("yükseltilsin mi?", "kurulsun mu?") açık
  pencerelerin **arkasında** ve görev çubuğunda düğmesi olmadan açıyordu; ekranda bir şey görünmüyordu. İleti kutuları
  artık her zaman en üstte ve görev çubuğunda görünür.
- Başlatıcı zaten açıkken yeniden çift tıklanırsa ikinci bir kurulum/yükseltme başlamaz; "zaten çalışıyor" denir.
- Yönetici izni (UAC) verilmezse ya da süresi dolarsa tek, açık bir uyarı gösterilir. Yükseltmede kurulu sürüm açılmaya
  devam eder. Önceden ardından yanıltıcı bir "tamamlanamadı" hatası da geliyordu.
- Türkçe Windows'ta yedek/geri yükleme hata iletileri (pg_dump/pg_restore) okunamayan karakter yüzünden
  kaybolabiliyordu; artık her durumda gösterilir.
- Ürün adı her yerde yalnız "METIS".
- Bu ZIP yerel bir Windows 10 bilgisayarda derlendi ve çift tıklamayla denendi (2.0.0 → 2.0.8 yükseltmesi, yedek,
  Chrome'da açılış, sol menüde "Sürüm 2.0.8").
- Şema değişmedi.

**2.0.7 — yeni sürüm adı, görünen sürüm, yükseltme düzeltmesi:**
- Sürümler artık büyük.küçük.ilerleme biçiminde: bu sürüm **2.0.7** (önceki ön sürümler rc.1–rc.7). Sonraki sürümler
  2.0.8, 2.0.9 … diye ilerler.
- Sürüm arayüzde görünür: sol menüde METIS yazısının altında ve hesap menüsünde ("Sürüm 2.0.7"). `METIS-Baslat.exe`'nin
  Özellikler → Ayrıntılar sekmesinde de yazar.
- Düzeltme: rc.1–rc.6 ile kurulu bir bilgisayarda rc.7'nin başlatıcısı "Bu paket (2.0.0-rc.7) kurulu sürümden (2.0.0)
  eski" deyip yükseltmiyordu (eski paketler sürümü "2.0.0" olarak kaydediyordu). 2.0.7'nin başlatıcısı bu kurulumları
  yeni sürüme yükseltmeyi önerir (`upgrade.ps1`: önce yedek, sonra geçiş).
- Başlatıcı PowerShell 7 penceresinden açıldığında da çalışır (önceden paket bütünlük denetimi hata veriyordu).
- Şema değişmedi.

**rc.7 — çift tıklanabilir başlatıcı (METIS-Baslat.exe):**
- Paket klasöründeki `METIS-Baslat.exe`'ye çift tıklamak yeterli; PowerShell komutu yazmak gerekmez. İlk açılışta onay
  ister, yönetici izni alır, deneme modunda kurar (yalnız bu bilgisayardan, http://localhost:8000), PostgreSQL parolasını
  bir kez sorar, isterse kurgusal örnek içerik ekler ve Chrome'u (yoksa varsayılan tarayıcıyı) kurulum kodu **hazır**
  olarak açar. Sonraki açılışlarda METIS'i (kapalıysa başlatıp) açar; yeni sürümün exe'si yükseltmeyi önerir.
- PostgreSQL 16 kurulu değilse ne yapılacağını söyler (PostgreSQL'i bu paket kurmaz).
- Exe imzasızdır: Windows "bilgisayarınızı korudu" derse "Ek bilgi → Yine de çalıştır". Şirket bilgisayarında BT
  engelliyorsa KURULUM.md'deki komutla kurulum aynen geçerli.
- Düzeltme: paket sürümü artık ön sürüm adını taşır (`METIS-2.0.0-rc.7-server-win64.zip`); önceden tüm rc'ler "2.0.0"
  olduğundan `upgrade.ps1` rc'ler arası yükseltmeyi "zaten kurulu" sanıp atlıyordu.
- Ağ üzerinden erişilecek sunucu kurulumu (IIS + sertifika) değişmedi; exe o kurulumda da sonraki açılışlarda doğru adresi açar.

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

**Kendi bilgisayarında deneme (Windows 10/11, IIS olmadan):** PostgreSQL 16'yı kur, ZIP'i aç, `METIS-Baslat.exe`'ye çift
tıkla. Komutla kurulum: yönetici PowerShell ile
`powershell -ExecutionPolicy Bypass -File .\install-offline.ps1 -PublicUrl http://localhost:8000 -AllowHttp`.
Kaldırma: `uninstall.ps1 -RemoveAll`.

**Doğrulama:** yayımlanan ZIP yerel Windows 10 bilgisayarda derlenip çift tıklamayla denendi. Aynı commit CI'da Windows
Server 2022 üzerinde ağ kapalıyken kuruldu; giriş, servis yeniden başlatma, yedek, geri yükleme tatbikatı, örnek içerik,
yükseltme ve kaldırma denendi (CI kendi derlediği paketle sınar; o paket yayımlanmaz).

**Henüz denenmedi:** gerçek şirket sunucusu (IIS/ARR + TLS), Windows 11, şirket modeliyle bağlantı,
gerçek v0.5.5 yedeğinin aktarılması. 2.0.x sürümleri pilot sürümleridir.
