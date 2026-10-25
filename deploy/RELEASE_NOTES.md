METIS sunucu kurulum paketi (Windows, internetsiz). Dosya: `METIS-<sürüm>-server-win64.zip`; yanındaki `.sha256` ile doğrulanabilir.

**Kurulum:** ZIP'i aç, `BASLA.txt` ve `KURULUM.md` dosyalarını oku. Önkoşul: PostgreSQL 16.
Türkçe Windows'ta PostgreSQL kurulumunun **Locale** adımında `English, United States` seç; varsayılan bölge ayarı
veritabanı kümesinin oluşturulmasını bozuyor ("database cluster initialisation failed").

**2.0.21 — Model zenginleştirmesi (arama için):**
- Şirket modeli varken yayımlanmış bölümlere kısa bir **bağlam cümlesi** ve **"bu bölüm hangi soruları cevaplar"** yazılır;
  arama (kelime ve vektör) bunları kullanır. Zenginleştirme kanıt değildir: bilgi metnine, alıntıya ve Mentor cevabına
  girmez, ekranda gösterilmez. Taslaklar modele gönderilmez; model blokta olmayan bir tanımlayıcı (yazmaç, fonksiyon,
  hata kodu) uydurursa o cümle/soru atılır.
- Arka planda, düşük öncelikle: model meşgulse Mentor'a yer bırakır; zenginleştirme hataları modeli Mentor için kapatmaz.
  Model yoksa beklenir, arama zenginleştirmesiz sürer. Model ya da ayar değişmedikçe aynı bölüm yeniden gönderilmez.
- **Ayarlar → İnceleme politikası → Model zenginleştirmesi** (proje başına, yalnız yönetici; varsayılan açık). Kapatınca
  saklanan zenginleştirme de aramadan çıkar. İlerleme: Ayarlar → Sistem durumu. Şema 0013.
- Arama kalitesine katkısı **ölçülmedi** (bu sürümün geliştirme bilgisayarında şirket modeli yok; kurgusal modelle yalnız
  işleyiş denendi). Etkisini görmek için Model laboratuvarı → Arama ölçümü'nü zenginleştirme öncesi ve sonrası çalıştırın.

**2.0.20 — Vektör (anlamsal) arama:**
- Arama artık kelime eşleşmesinin yanında anlam benzerliğini de kullanabilir: farklı sözcüklerle ya da Türkçe–İngilizce
  karışık sorulan sorularda doğru bölüm daha üstte çıkar. İki sıralama RRF ile birleşir; tanımlayıcı (yazmaç, fonksiyon,
  hata kodu) birebir eşleşen bilgi her zaman en üstte kalır.
- Model **ayrı bir dosyadır** (`METIS-vektor-modeli-e5-base-1.zip`, multilingual-e5-base, MIT): kurulmazsa METIS önceki
  gibi yalnız kelime aramasıyla çalışır. Yerel CPU'da, internetsiz; şirket modeline bağlı değildir. Kurulum: KURULUM.md 10c.
- Bilgi havuzunda olmayan bir soru vektörle "en yakın" sonuca dönüşmez (kalibre eşik); Mentor'un "kanıt yok" kararı korunur.
- Ayarlar → Sistem durumu → Vektör arama (kurulu değil / hazırlanıyor n/m / açık / yüklenemedi). Mentor, vektör araması
  hazırlanırken ya da model yüklenemediğinde bunu cevabın altında söyler. Arama ölçümünde vektör kanalı açık/kapalı
  karşılaştırılabilir. Şema 0012.
- Kurgusal 44 soruluk sette gerçek modelle: MRR 0,932 → 0,955, nDCG@10 0,944 → 0,960, doğru bilgi ilk 5'te 0,977 (aynı).
  **Gerçek içerikte ölçülmedi.** Paket boyutu 36 → 71 MB (onnxruntime, tokenizers, numpy).
- Bu ZIP yerel Windows 10 bilgisayarda derlendi (testler dahil); aynı commit'te CI yeşil (uçtan uca + temiz Windows Server'da
  kurulum/yükseltme). Çift tıklamada yükseltme sorusu → Yes denendi; yönetici izni onaylanamadığı için yükseltmenin kendisi
  bu sürümde o bilgisayarda **denenmedi** (ürün sahibinin "beklemeden yayımla" kararıyla istisna). Model eklentisinin
  kurulum betiği yalnız yönetici olmayan kabukta denendi (açık hatayla durdu); yönetici yolu **denenmedi**. Model, geliştirme
  sunucusu ve worker'la gerçek olarak çalıştırıldı.

**2.0.19 — Bölüm düzeyinde arama ve arama ölçümü:**
- Arama artık her bilginin **bölümlerini** (notun paragrafları, başlık yoluyla) puanlar: uzun bir dokümanda (ör. içe
  aktarılmış Confluence sayfası) doğru bölüm bulunur, sonuçta o bölüm gösterilir. Türkçe harfsiz yazılan sorular
  ("saat kaynagi") ve "İ" ile başlayan sözcükler eşleşir.
- **Mentor** uzun bir sayfanın tüm paragrafları yerine soruyla ilgili bölümlerini (+ başlığı ve komşuları) kullanır; birden
  çok sayfa arasında pay adil dağıtılır.
- **Model yanıt vermezse** Mentor artık yalnız sayfa listesi değil, sorunla ilgili yayımlanmış bölümleri birebir gösterir
  ("bu bir cevap değil" etiketiyle). Karar yine "Model kullanılamıyor"dur.
- **Model laboratuvarı → Arama ölçümü** (yönetici ve proje sorumlusu): ekibin gerçek sorularıyla arama kalitesi ölçülür
  (doğru bilgi ilk 5/10'da, MRR, nDCG, beklenen metin ilk 5'te); önceki ölçümle yan yana. Model kullanılmaz; sorular
  yalnız sunucuda saklanır.
- Kurgusal 44 soruluk sette (geliştirme): MRR 0,900 → 0,932, nDCG@10 0,919 → 0,944, doğru bilgi ilk 5'te 0,977 (aynı),
  beklenen metin ilk 5'te 0,805 (önce ölçülemiyordu). **Gerçek içerikte ölçülmedi.** Şema 0011; yükseltmede mevcut
  yayın bölümlere indekslenir.
- Bu ZIP yerel Windows 10 bilgisayarda derlendi (testler dahil); aynı commit'te CI yeşil (uçtan uca + temiz Windows Server'da
  kurulum/yükseltme). Çift tıklamada yükseltme sorusu çıktı; yükseltmenin kendisi bu sürümde o bilgisayarda **denenmedi**
  (sorunun önüne geçen Windows giriş penceresine erişim verilmedi; ürün sahibinin "beklemeden yayımla" kararıyla istisna).

**2.0.18 — Confluence ve GitLab'dan taslak:**
- **Ayarlar → Dış kaynaklar** (yalnız yönetici): Confluence Server/Data Center ve GitLab bağlantıları; token şifreli
  saklanır, yalnız izinli alan/projelerden alınır. **Bağlantıyı dene** kaydetmeden sınar. Ayrıntı: KURULUM.md 10a.
- **Yeni katkı → Kaynaktan al**: Confluence sayfası ya da GitLab issue'su adresle ya da başlıkla aranarak önizlenir ve
  taslağa çevrilir. Confluence: metin, başlıklar, tablolar, kod blokları not olur; PNG/JPEG/PDF ekleri ek olur. GitLab:
  açıklama ve yorumlar (yazan, tarih) not olur, ekran görüntüleri ek olur; sistem notları alınmaz.
- Kısıtlı Confluence sayfaları ve gizli GitLab issue'ları alınmaz. İçe aktarılan içerik bir insan yayımlayana kadar
  Mentor'a girmez. Yayımlanan bilgide kaynak satırı; aynı kaynak tekrar alınınca güncelleme taslağı. Şema 0010.
- **Gerçek Confluence/GitLab ile denenmedi**: kurgusal sahte sunucuyla (testler + tarayıcı) denendi. İlk gerçek deneme
  şirket sunucusunda yapılacak.
- Bu ZIP yerel Windows 10 bilgisayarda derlendi (testler dahil); aynı commit'te CI yeşil (uçtan uca + temiz Windows Server'da
  kurulum/yükseltme). Çift tıklamayla **gerçek yükseltme denendi**: kurulu 2.0.15 → 2.0.18 (yedek alındı, şema 0010,
  sağlık `ready`).

**2.0.17 — Geri bildirim bölümü:**
- Sol menüde yeni **Geri bildirim**: herkes (Okur dahil) bir **Hata** ya da **İstek** yazar; en çok 5 ekran
  görüntüsü (PNG/JPEG) ekleyebilir. Görsel seçilebilir, sürüklenip bırakılabilir ya da **Ctrl+V** ile yapıştırılabilir.
- Giriş yapmış herkes tüm geri bildirimleri, görselleri ve durumlarını görür; türe ve duruma göre süzülebilir.
- **Durum ve cevap notu yalnız yöneticide:** Yeni / İnceleniyor / Düzeltildi / Yapılmayacak; cevap notu herkese görünür.
- Yazan kendi geri bildirimini, yönetici her geri bildirimi silebilir. Şema 0009.
- Bu ZIP yerel Windows 10 bilgisayarda derlendi (testler dahil); aynı commit'te CI yeşil (uçtan uca + temiz Windows Server'da
  kurulum/yükseltme). Çift tıklamada yükseltme sorusu denendi; yükseltmenin kendisi bu sürümde o bilgisayarda
  **denenmedi** (yönetici izni onaylanamadı; ürün sahibinin "beklemeden yayımla" kararıyla istisna).

**2.0.16 — parolasız giriş (ekip içi):**
- **Ayarlar → Giriş yöntemi → Parolasız girişi aç** (yalnız yönetici). Açıkken yönetici olmayan herkes METIS'e yalnız
  kullanıcı adıyla girer; ilk girişte hesap açılır ve **Okur** başlar, diğer rolleri yönetici verir.
- Yönetici hesapları her zaman parolalıdır: giriş ekranı yönetici adını görünce parola ister. Parolasız açılmış bir
  hesabı yönetici yapmak için ona geçici parola verilir.
- Bilinen ve kabul edilen risk: adrese ulaşabilen biri başka birinin kullanıcı adıyla girebilir (ekip içi kullanım
  kararı). Varsayılan kapalı; kapatınca herkes yeniden parolayla girer. Şema 0008.
- Ayarlar sekmesinin adı "Giriş yöntemi" oldu (parolasız giriş + şirket hesabıyla giriş).
- Bu ZIP yerel Windows 10 bilgisayarda derlendi (testler dahil); aynı commit'te CI yeşil (uçtan uca + temiz Windows Server'da
  kurulum/yükseltme). Çift tıklamada yükseltme sorusu denendi; yükseltmenin kendisi bu sürümde o bilgisayarda
  **denenmedi** (yönetici izni onaylanamadı; ürün sahibinin "beklemeden yayımla" kararıyla istisna).

**2.0.15 — şirket hesabıyla giriş (Active Directory):**
- Kullanıcılar METIS'e Windows'a girdikleri kullanıcı adı ve parolayla girebilir; yönetici her kullanıcıyı elle
  açmaz. İlk girişte hesap kendiliğinden oluşur ve kişi **Okur** olarak başlar; diğer rolleri yönetici verir
  (Ayarlar → Üyeler ve roller'de "Şirket hesabı" etiketiyle görünür). İstenirse "Rol bekler" seçilebilir.
- **Parola saklanmaz:** METIS her girişte şirket dizinine kişinin kendi bilgileriyle **LDAPS** üzerinden sorar; hizmet
  hesabı yok. Şirket hesabının parolası METIS'te değiştirilemez/sıfırlanamaz.
- Ayar: **Ayarlar → Şirket hesabıyla giriş** (yalnız yönetici): dizin sunucusu, etki alanı, isteğe bağlı izinli grup,
  **Bağlantıyı dene** (kaydetmez, hesap açmaz). Ayrıntı: KURULUM.md 6a.
- **https şart:** şirket parolası tarayıcıdan METIS'e geldiği için özellik yalnız METIS https ile açılıyorsa
  etkinleşir; ayarlar http'de de girilip kaydedilebilir. Kurulumdaki yerel yönetici hesabı her zaman çalışır.
- Rolü olmayan kullanıcı giriş yapınca "yöneticinin rol vermesi bekleniyor" ekranı görür.
- Düzeltme: geri yükleme tatbikatı geçici veritabanını silerken o anda bağlı bir arka plan süreci varsa ara sıra
  başarısız oluyor ve geçici veritabanı kalıyordu; silme artık yeniden denenir.
- Gerçek bir Active Directory ile **henüz denenmedi** (kurgusal dizinle testler ve https geliştirme sunucusunda uçtan uca
  akış). Şema 0007. Bu ZIP yerel Windows 10 bilgisayarda derlendi. **Yükseltme gerçek bilgisayarda denendi:** kurulu METIS
  2.0.8 → 2.0.15 (yönetici izni onaylandı; yedek → şema 0007 → sağlık kontrolü → eski sürüm temizliği), aynı sürümün
  bir önceki derlemesiyle (yalnız API sözleşme dosyası ve belgeler farklı); son derlemede çift tıklama kurulu aynı sürümü
  açtı. Temiz Windows Server 2022'de kurulum, yükseltme ve kaldırma bu sürümün kodu için CI'da denendi (1049c10). Bundan
  sonra otomatik CI yok: doğrulama yerel derlemede.

**2.0.14 — Model laboratuvarı herkese salt okunur:**
- Yönetici olmayan kullanıcılar da sol menüde **Model laboratuvarı**'nı görür: eklenen modeller, uygunluk durumu,
  son benchmark sonuçları (isabet, kritik hata, süre), **Kalite ve gecikme** grafiği, benchmark geçmişi ve sonuç
  ayrıntısı ("Sonucu aç").
- Ekleme, test, benchmark, açma/kapama, silme, sonuç temizleme yalnız yöneticide (sunucu da reddeder). Sağlayıcılar
  bölümü, model sunucusunun adresi, anahtar durumu ve bağlantı ayrıntıları yöneticiye özel kalır.
- Bu ZIP yerel Windows 10 bilgisayarda derlendi; çift tıklamada yükseltme sorusu denendi; yükseltmenin kendisi o
  bilgisayarda **denenmedi** (ajan Windows yönetici iznini onaylayamaz; ürün sahibinin "beklemeden yayımla" kararıyla
  istisna); temiz Windows Server 2022'de kurulum, yükseltme ve kaldırma CI'da.

**2.0.13 — METIS bir alt yolda: http://<makine>/metis; http'de Taslak hazırla düzeltmesi:**
- **Düzeltme:** şirket içi http adresinden (https değil, localhost değil) açınca "İlk bilgiyi ekle" / "Taslak hazırla"
  "Something went wrong!" ile çöküyordu: sayfa, tarayıcının yalnız https ve localhost'ta verdiği `crypto.randomUUID`'i
  çağırıyordu. Artık her bağlamda çalışan yöntemle üretiliyor. (2.0.10–2.0.12'yi http ile ağa açanları etkiler.)
- METIS artık bir alt yolda yayınlanabilir; sunucu makinesi başka işler için de kullanılabilir. Alt yol
  `METIS_PUBLIC_URL`'ün yolundan gelir (ör. `http://<ad>.<alan-adı>/metis`); API, arayüz ve oturum çerezi o yolun
  altındadır. Aynı paket kökte de çalışır.
- `ag-erisimi.ps1` artık METIS'i IIS Default Web Site altında `/metis` uygulaması olarak açar; kök (`/`) ve diğer
  yollar boş kalır. 2.0.12'nin kökü kaplayan "METIS" sitesi varsa kaldırılır. Farklı yol için `-Yol /bilgi`.
  IIS ilk açılışta yeniden başlatma isterse betik kırmızı hata yerine ne yapılacağını söyler.
- **2.0.12 ile şirket ağına açtıysan:** yükselttikten sonra `ag-erisimi.ps1`'i bir kez daha çalıştır; adres
  `http://<ad>/metis` olur. Çalıştırmazsan METIS eski adresinde (kökte) çalışmaya devam eder.
- Ekip ve izinler'deki rol açıklaması yeni yönteme göre düzeltildi (Katkı sahibi taslak hazırlar, yayımlar).
- `/metis` alt yolu yerel geliştirme sunucusunda tarayıcıyla denendi (giriş, gezinme, derin bağlantı, çıkış); IIS
  ile gerçek makinede ilk deneme bu sürümde. Bu ZIP yerel Windows 10 bilgisayarda derlendi; çift tıklamada yükseltme
  sorusu denendi; yükseltmenin kendisi o bilgisayarda **denenmedi** (ajan Windows yönetici iznini onaylayamaz; ürün
  sahibinin "beklemeden yayımla" kararıyla istisna); temiz Windows Server 2022'de kurulum, yükseltme ve kaldırma CI'da.

**2.0.12 — şirket ağından erişim (deneme) ve ek yükleme düzeltmesi:**
- Yeni `ag-erisimi.ps1`: METIS-Baslat.exe ile kurulmuş METIS'i tek komutla şirket ağına açar. IIS'i açar, 80
  portundan METIS'e iletir, adresi makinenin tam adına (`http://<ad>.<alan-adı>`) çevirir, güvenlik duvarını ayarlar
  (KURULUM.md 5a). http şifresizdir; birkaç kişilik deneme içindir, kalıcı kullanımda https'e geçilir. Betik gerçek
  makinede henüz denenmedi.
- Ekler artık tek tek yüklenir: birkaç büyük fotoğraf birlikte seçilince sunucu önündeki IIS'in istek sınırına
  takılıyordu (tek tek yüklemede dosya başına sınır geçerli; biri başarısız olursa öncekiler kalır).
- Bu ZIP yerel Windows 10 bilgisayarda derlendi; çift tıklamada yükseltme sorusu denendi. Yükseltmenin kendisi o
  bilgisayarda **denenmedi** (ajan Windows yönetici iznini onaylayamaz; ürün sahibinin "beklemeden yayımla" kararıyla
  istisna); temiz Windows Server 2022'de kurulum, yükseltme ve kaldırma CI'da denendi.

**2.0.11 — çıkış düzeltmesi:**
- **Çıkış yap** artık sayfayı yenilemeden giriş ekranına geçer. Önceden aynı sayfa görünümünde kalıyor, giriş ekranı
  ancak F5 ile geliyordu (oturum sunucuda yine kapanıyordu; sorun yalnız arayüzdeydi).
- Bu ZIP yerel Windows 10 bilgisayarda derlendi; çift tıklamada yükseltme sorusu denendi. Yükseltmenin kendisi o
  bilgisayarda **denenmedi** (ajan Windows yönetici iznini onaylayamaz; ürün sahibinin "beklemeden yayımla" kararıyla
  istisna); temiz Windows Server 2022'de kurulum, yükseltme ve kaldırma CI'da denendi.

**2.0.10 — tek adımda taslak: not + ekler:**
- **Yeni katkı → Taslak hazırla:** ayrı "önce kaynak ekle" adımı yok. Başlık, kapsam ve notu yaz; istersen birden çok
  görsel (PNG, JPEG) ya da PDF ekle (çoklu seçim ya da sürükle-bırak). Taslağı kaydet, Kayıtlar'dan açıp geliştir;
  hazır olduğunda **Yayımla** (yayın öncesi çelişki/tekrar kontrolü aynen çalışır).
- Not bilginin dayanağıdır (uzman beyanı): METIS notu paragraflarına ayırır, her paragraf bir bilgi parçası olur;
  alıntı seçmen ya da bağlaman gerekmez. Metis (Mentor, kontrol) yalnız notu okur; **ekler okunmaz, aranmaz, yapay
  zekâya gönderilmez** — yalnız bilgiyle birlikte saklanır ve açılır/indirilir.
- Bilgi sayfasında **Ekler** bölümü: görseller küçük önizlemeyle (tıklayınca büyür), PDF'ler adıyla. İz paneli bu tür
  bilgide "Uzman notu · yazan · tarih" ve ekleri gösterir; "Bilgiyi düzenle" ile yeni sürüm yazılır.
- **Kalkanlar:** kaynaktan alıntı seçerek yazma, "Metis hazırlasın" (kaynaktan taslak) ve "Taslağı düzenle" görevleri,
  Mentor'da "Bu cevaptan bilgi taslağı öner", v0.5.5 aktarımı (komut, Ayarlar sekmesi, kurulum seçeneği) ve
  başlatıcıdaki "kurgusal örnek içerik eklensin mi?" sorusu.
- Yayımlanmış bir bilgiyi düzenlerken kaydedilen taslak, yayımlanana kadar yayındaki bilgiyi değiştirmez ve yalnız
  yazarı, sorumlular ve inceleyiciler görür (ekleri dahil; boş notlu taslak da).
- **Yükseltmede verin korunur:** yayımlanmış bilgiler aynen kalır. Hiçbir bilgiye bağlanmamış eski kaynaklar (ör. bir
  görselle eklenmiş uzman notu) kendiliğinden taslağa dönüşür: yazdığın metin → not, görsel/PDF → ek; Kayıtlar'da
  görünür. PDF'ten çıkarılmış metin nota konmaz (PDF yalnız ek olur). Dönüştürülemeyen bir kaynak olursa silinmez;
  yükseltme çıktısında (`skipped_sources`) adı ve nedeniyle listelenir.
- Şema 0006 (not tabanlı bilgi ve ekler); yükseltme geçişi kendiliğinden uygular.
- Bu ZIP yerel Windows 10 bilgisayarda derlendi; çift tıklamada yükseltme sorusu denendi. Yükseltmenin kendisi o
  bilgisayarda **denenmedi** (ürün sahibinin kararıyla istisna; onaylayacak kimse yoktu); temiz Windows Server 2022'de
  kurulum, yükseltme ve kaldırma CI'da denendi.

**2.0.9 — şirket modelini arayüzden ekleme:**
- Model laboratuvarında **Sağlayıcı ekle** dediğinde adrese henüz izin verilmemişse METIS bunu söyler ve
  **İzin ver ve ekle** ile izin verirsin. `metis.env`'e elle adres eklemek ve servisleri yeniden başlatmak gerekmez.
- İzinli adresler **Ayarlar → Sistem durumu → İzinli model adresleri** altında: `metis.env`'dekiler "Sunucu ayarı"
  olarak, arayüzden eklenenler kimin eklediği ve kullanan sağlayıcı sayısıyla. Kullanılmayan adresin izni kaldırılabilir.
- Güvenlik kuralları aynı: yalnız yöneticiler izin verir; yalnız iç ağ adreslerine izin verilir; sunucu kurulumunda
  adres `https://` olmalı; her izin denetim kaydına yazılır ve yedekle taşınır.
- Şema 0005 (izinli adresler tablosu); yükseltme geçişi kendiliğinden uygular.
- Bu ZIP yerel Windows 10 bilgisayarda derlendi; çift tıklamada yükseltme sorusu ve yönetici izni verilmediğindeki
  davranış denendi. Yükseltmenin kendisi (2.0.8 → 2.0.9) o bilgisayarda **denenmedi** (ürün sahibinin kararıyla
  istisna); temiz Windows Server 2022'de kurulum, yükseltme ve kaldırma CI'da denendi.

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
