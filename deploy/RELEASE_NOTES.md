METIS v2 sunucu kurulum paketi (Windows, internetsiz). Dosya: `METIS-<sürüm>-server-win64.zip`; yanındaki `.sha256` ile doğrulanabilir.

**Kurulum:** ZIP'i aç, `BASLA.txt` ve `KURULUM.md` dosyalarını oku. Önkoşul: PostgreSQL 16.
Türkçe Windows'ta PostgreSQL kurulumunun **Locale** adımında `English, United States` seç; varsayılan bölge ayarı
veritabanı kümesinin oluşturulmasını bozuyor ("database cluster initialisation failed").

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
