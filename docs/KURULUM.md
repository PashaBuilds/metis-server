# METIS — Sunucu kurulum rehberi

Bu rehber METIS'i şirket içindeki bir **Windows Server** makinesine internet bağlantısı olmadan kurmayı anlatır.
Linux (systemd) kurulumu sondaki ekte. Varsayılanlar (brief Bölüm 11): Windows Server, yerel hesaplar,
aynı sunucuda METIS'e ayrılmış PostgreSQL 16, TLS'in IIS/ARR'de sonlanması, 25 kullanıcı için 2 API süreci + 1 worker.

> Paket her değişiklikte GitHub Actions'ta bir **Windows Server 2022** makinesinde, ağ kapalıyken uçtan uca denenir:
> kurulum, giriş, servis yeniden başlatma, yedek, geri yükleme tatbikatı, yükseltme ve kaldırma. IIS/ARR + TLS ve
> gerçek şirket sunucusu **henüz denenmedi**; ilk kurulumu bir test sunucusunda yapmanı öneririm. Kendi Windows
> bilgisayarında denemek için sondaki "Ek: Kendi bilgisayarında deneme" bölümüne bak.

## 1. Önkoşullar

| Gereksinim | Ayrıntı |
|---|---|
| İşletim sistemi | Windows Server 2019 veya 2022, 64 bit, güncel |
| Donanım (25 kullanıcı) | 4 çekirdek, 8 GB RAM, veri için ayrı disk önerilir (≥ 50 GB) |
| Hesap | Yerel yönetici (kurulum için) |
| Ağ | Kullanıcıların sunucuya 443 ile erişmesi; METIS'in şirket model uç noktasına erişmesi |
| Dosyalar | `METIS-<sürüm>-server-win64.zip`, PostgreSQL 16 EDB çevrimdışı kurucusu, IIS URL Rewrite 2.1 ve ARR 3.0 `.msi` kurucuları, şirket TLS sertifikası (`.pfx`) |

Paket içeriği: gömülü Python 3.12, hash-kilitli Python paketleri (`wheelhouse/` + `requirements.lock`), derlenmiş
web arayüzü, WinSW servis sarmalayıcısı, `install-offline.ps1`, `upgrade.ps1`, `BASLA.txt`, bu rehber ve `SHA256SUMS`.

## 2. PostgreSQL 16 kurulumu (bir kez)

1. EDB kurucusunu çalıştır (`postgresql-16.x-windows-x64.exe`). Varsayılan klasör `C:\Program Files\PostgreSQL\16`.
2. Veri klasörü olarak veri diskini seç (ör. `D:\PostgreSQL\16\data`). Port 5432. `postgres` parolasını şirket kasasına kaydet.
3. **Locale** sayfasında `[Default locale]` yerine **`English, United States`** seç. Türkçe Windows'ta varsayılan
   ("Turkish_Türkiye") veritabanı kümesinin oluşturulmasını bozar ("The database cluster initialisation failed");
   ayrıca Türkçe büyük/küçük harf kuralı (I→ı) kullanıcı adı karşılaştırmalarını etkiler. Veritabanı yine UTF-8 olur.
   Son ekranda Stack Builder kutusunun işaretini kaldır (internet ister, gerekmez).
4. `C:\Program Files\PostgreSQL\16\data\postgresql.conf` içinde `listen_addresses = 'localhost'` kalsın (METIS aynı sunucuda).
5. Servisin çalıştığını doğrula: `Get-Service postgresql-x64-16`.

Kurulum betiği METIS'in rollerini ve veritabanını kendisi oluşturur; `postgres` parolasını bir kez sorar ve kaydetmez.
Elle yapmak istersen (veya şirket PG sunucusu kullanılacaksa) şu SQL yeterli:

```sql
CREATE ROLE metis_owner LOGIN CREATEDB PASSWORD '<uzun-rastgele>';   -- migration, yedek, geri yükleme tatbikatı
CREATE ROLE metis_app   LOGIN PASSWORD '<uzun-rastgele>';            -- çalışma zamanı (tablo sahibi değil)
CREATE DATABASE metis OWNER metis_owner ENCODING 'UTF8' TEMPLATE template0;
\c metis
CREATE EXTENSION IF NOT EXISTS pg_trgm;
ALTER SCHEMA public OWNER TO metis_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO metis_app;
```

## 3. Paketi doğrula ve aç

1. ZIP'i sunucuya kopyala. Yanındaki `.zip.sha256` ile karşılaştır:
   `Get-FileHash .\METIS-<sürüm>-server-win64.zip -Algorithm SHA256`
2. ZIP'i aç (ör. `D:\Kurulum\METIS-<sürüm>-server-win64`). Betik her dosyayı ayrıca `SHA256SUMS` ile doğrular.

## 4. Kurulum betiği

Yönetici PowerShell:

```powershell
cd D:\Kurulum\METIS-<sürüm>-server-win64
powershell -ExecutionPolicy Bypass -File .\install-offline.ps1 -PublicUrl https://metis.sirket.local
```

Seçenekler: `-InstallRoot C:\METIS` · `-PgBin "C:\Program Files\PostgreSQL\16\bin"` · `-ApiPort 8000` ·
`-ApiWorkers 2` · `-WorkerSlots 2` · `-EndpointAllowlist "https://llm.sirket.local/v1"`.

Betik sırasıyla: paketi doğrular → `C:\METIS\app\<sürüm>` altına Python ve paketleri kurar (`pip --no-index
--require-hashes`, ağ kullanılmaz) → ana anahtarı (`C:\METIS\config\master.key`) ve rolleri oluşturur →
`C:\METIS\config\metis.env` yazar (yalnız SYSTEM ve Administrators okuyabilir) → `metis migrate` → `metis doctor` →
`metis-api` ve `metis-worker` servislerini (WinSW, otomatik başlatma, hata olursa yeniden başlatma) kurar →
sağlık kontrolünü bekler → zamanlanmış görevleri kaydeder → ilk yönetici için **kurulum kodu** yazdırır.

Klasör düzeni:

```
C:\METIS\app\2.0.0\        python\ (gömülü Python + paketler), web\
C:\METIS\app\current       → etkin sürüm (junction)
C:\METIS\config\           metis.env, master.key   (gizli)
C:\METIS\data\             blobs\ (kaynak dosyaları), backups\, logs\
C:\METIS\services\         metis-api.exe/.xml, metis-worker.exe/.xml (WinSW)
C:\METIS\bin\metis.cmd     komut satırı: C:\METIS\bin\metis doctor
```

**Ana anahtarı yedekle:** `master.key` olmadan model sağlayıcı anahtarları çözülemez ve yedekler geri yüklenemez.
Dosyayı şirket parola kasasına koy; yedek arşivleri anahtarı içermez (yalnız parmak izini içerir).

## 5. IIS/ARR ters vekil ve TLS

1. IIS rolünü ekle: `Install-WindowsFeature Web-Server -IncludeManagementTools`.
2. URL Rewrite 2.1 ve ARR 3.0 `.msi` kurucularını çalıştır.
3. Sunucu düzeyinde vekili aç ve SSE için tamponlamayı kapat (yönetici PowerShell):
   ```powershell
   $appcmd = "$env:windir\system32\inetsrv\appcmd.exe"
   & $appcmd set config -section:system.webServer/proxy /enabled:"True" /preserveHostHeader:"True" /timeout:"00:10:00" /commit:apphost
   & $appcmd set config -section:system.webServer/proxy /responseBufferLimit:"0" /commit:apphost
   & $appcmd set config -section:system.webServer/rewrite/allowedServerVariables /+"[name='HTTP_X_FORWARDED_PROTO']" /commit:apphost
   ```
4. Sertifikayı içe aktar (`Import-PfxCertificate -FilePath sertifika.pfx -CertStoreLocation Cert:\LocalMachine\My`).
5. Yeni site: `C:\inetpub\metis`, bağlama **https 443**, ana bilgisayar adı `metis.sirket.local`, sertifikayı seç.
   İsteğe bağlı http 80 bağlaması (yalnız https'e yönlendirir).
6. Paketteki `iis-web.config` dosyasını `C:\inetpub\metis\web.config` olarak kopyala.
7. Tarayıcıdan `https://metis.sirket.local` aç. Sayfa gelmezse: `C:\METIS\bin\metis doctor` ve
   `C:\METIS\data\logs\service\metis-api.*.log`.

### 5a. Hızlı deneme: http ile şirket ağına açma (`ag-erisimi.ps1`, 2.0.12'den beri)

METIS-Baslat.exe ile kurulmuş bir METIS'i (http, deneme profili) sertifikasız olarak şirket ağına açar. Aynı makinede,
paket klasöründe yönetici PowerShell ile:

```powershell
powershell -ExecutionPolicy Bypass -File .\ag-erisimi.ps1
```

Betik IIS'i açar (Windows 10/11'de Windows özelliği olarak), URL Rewrite 2.1 ve ARR 3.0'ı kurar (kurucuları
`rewrite_amd64*.msi` ve `requestRouter_amd64*.msi` Microsoft'tan bir kez indirilip paket klasörüne ya da
İndirilenler'e konur), vekili ayarlar, 80 portunda "METIS" sitesini kurar (Default Web Site durur),
`METIS_PUBLIC_URL`'ü makinenin DNS'teki tam adına (`http://<ad>.<alan-adı>`) çevirir, servisleri yeniden başlatır,
güvenlik duvarında 80'i etki alanı/özel ağ için açar ve adresi dener. Farklı bir ad için `-Adres <ad>`. Tekrar
çalıştırılabilir. Adres her zaman bu tam adla yazılmalı (kısa ad ya da IP ile giriş reddedilir).
http şifresizdir (parolalar ağda açık gider): birkaç kişilik deneme içindir; kalıcı kullanımda şirket sertifikasıyla
yukarıdaki https düzenine geçilir. Ürün sahibinin şirket içi Windows 10 sanal makinesinde denendi (2026-10-19): IIS ilk açılışta yeniden başlatma istedi, sonra betik tamamlandı ve METIS başka bir bilgisayardan tam adla açılıp giriş yapıldı. CI yalnız betiğin sözdizimini denetler.

`METIS_PUBLIC_URL` tarayıcıda yazılan adresle **birebir** aynı olmalı (Origin ve CSRF denetimi buna göre yapılır).
Adres değişirse `metis.env` içinde düzelt ve servisleri yeniden başlat (`Restart-Service metis-api`).

## 6. İlk yönetici ve ekip

1. Tarayıcıda "Kurulum" ekranı açılır; betiğin yazdığı kurulum kodunu gir (24 saat, tek kullanım). Kod kaybolursa:
   `C:\METIS\bin\metis setup-code`.
2. Yönetici hesabını oluştur; **Ayarlar → Ekip ve izinler**'den kullanıcıları ve rollerini ekle.
3. Komut satırından yönetici gerekirse: `C:\METIS\bin\metis admin create --username ayse`.

## 7. Şirket modelini ekleme

1. **Model laboratuvarı → Sağlayıcı ekle**: temel adres (ör. `https://llm.sirket.local/v1`), anahtar, model kimlikleri.
   Anahtar diskte şifreli tutulur, arayüzde yalnız "tanımlı" görünür.
2. Adrese daha önce izin verilmediyse pencerede "Bu adrese henüz izin verilmedi" uyarısı çıkar: **İzin ver ve ekle**.
   METIS yalnız izin verilen adreslere model isteği (anahtar ve kaynak metinleri) gönderir. İzin veritabanında tutulur
   (`metis.env`'e elle dokunmak gerekmez, servis yeniden başlatılmaz), denetim kaydına yazılır ve yedekle taşınır.
   Yalnız yöneticiler izin verebilir. İç ağ aralıkları (`METIS_ENDPOINT_NETWORKS`, varsayılan 10.x, 172.16–31.x,
   192.168.x, 127.x) dışındaki adreslere izin verilemez; üretim profilinde adres `https://` olmalı. İzinli adresler
   **Ayarlar → Sistem durumu → İzinli model adresleri** altında listelenir; kullanılmayanın izni oradan kaldırılır.
   `metis.env`'deki `METIS_ENDPOINT_ALLOWLIST` (virgülle birden fazla) eskisi gibi çalışır ve orada "Sunucu ayarı"
   olarak görünür. Şirket iç CA'sı gerekiyorsa `metis.env`'e `METIS_CA_BUNDLE=C:\METIS\config\sirket-ca.pem`.
3. Modeli seç → **Test et** (bağlantı, JSON şeması, düşünme modu, kanıt sözleşmesi) → **Benchmark çalıştır**.
   Kritik hatası olmayan ve kalite kapısını geçen model mentor ve görevlerde kullanılabilir hâle gelir.
4. **Anahtarı değiştirirsen** (veya adres/model ayarı değişirse) model "ayar değişti" nedeniyle kullanım dışı kalır;
   benchmark'ı yeniden çalıştır. Bu bilinçli bir güvenliktir: kalite kapısı yeni ayarla yeniden ölçülür.
5. DeepSeek (OpenAI uyumlu) notları — herkese açık DeepSeek API'siyle kurgusal veriyle denendi (2026-10-18), şirket
   içi DeepSeek V4 Flash ile **henüz denenmedi**: bağlantı testi `json_schema`'yı desteklenmiyor bulur ve `json_object`
   + düşünme kapalı profilini kendisi seçer (beklenen). Sağlayıcı aynı anda en çok 4 istek gönderir (14 kişilik yük
   testinde en kötü Mentor cevabı ≈10 sn); model yanıt vermezse 60 sn'de kesilir ve kullanıcıya "model kullanılamıyor"
   denir. Art arda 3 bağlantı hatasında model 60 sn dinlenmeye alınır, varsa diğer uygun model kullanılır.

## 8. Yedek ve geri yükleme

- Otomatik: "METIS gece yedeği" (her gece 02:15, 14 gün saklanır) ve "METIS geri yükleme tatbikatı" (pazar 03:30;
  son yedeği geçici bir veritabanına yükleyip doğrular ve siler). Görev Zamanlayıcı'da görünürler.
- Elle yedek: `C:\METIS\bin\metis backup` → `C:\METIS\data\backups\metis-backup-<tarih>.zip` (pg_dump + kaynak dosyaları
  + manifest; ana anahtar dahil değil). Arşivleri başka bir diske/ağ paylaşımına da kopyala.
- Tatbikat: `C:\METIS\bin\metis restore --rehearsal latest` (canlı veriye dokunmaz).
- Gerçek geri yükleme (felaket sonrası, yeni sunucu):
  1. Aynı `master.key` ve `metis.env` ile kurulum betiğini çalıştır, ama **migrate'ten önce** dur — veya boş bir
     veritabanı oluştur (`CREATE DATABASE metis OWNER metis_owner TEMPLATE template0`) ve hiç migrate çalıştırma.
  2. Servisleri durdur: `Stop-Service metis-worker, metis-api`.
  3. `C:\METIS\bin\metis restore D:\Yedek\metis-backup-<tarih>.zip` — hedef boş değilse reddeder, hiçbir şey değiştirmez.
  4. Servisleri başlat, `metis doctor`.
- Sistem durumu ekranı (Ayarlar → Sistem durumu) son yedeğin zamanını gösterir.

## 9. Yükseltme

Yeni paketi açıp klasöründe yönetici PowerShell ile:

```powershell
powershell -ExecutionPolicy Bypass -File .\upgrade.ps1
```

Betik önce yedek alır; yeni sürümü eskisinin yanına kurar (servisler çalışırken); servisleri durdurup
`app\current`'ı yeni sürüme çevirir; `metis migrate` çalıştırır; servisleri başlatıp sağlık kontrolü yapar.
Hata olursa önceki sürüme döner. Şema yükseltmesi uygulandıktan sonra hata olduysa eski sürümle çalışmak için
yükseltme öncesi yedeği (ekrana yazılır) boş bir veritabanına geri yükle. En yeni iki sürüm saklanır.

## 10. Bilgi ekleme (2.0.10'dan beri)

**Yeni katkı → Taslak hazırla**: başlık, kapsam ve not; isteğe bağlı birden çok görsel (PNG/JPEG) ya da PDF eki.
Not bilginin dayanağıdır (uzman beyanı); Metis yalnız notu okur, ekleri okumaz — ekler bilgiyle birlikte saklanır ve
açılır. Taslak kaydedilir, Kayıtlar'dan açılıp geliştirilir; **Yayımla** ile bilgi havuzuna girer (yayın öncesi
çelişki/tekrar kontrolüyle). v0.5.5 aktarımı ve "önce kaynak ekle, sonra alıntı seç" yöntemi 2.0.10'da kaldırıldı;
yükseltmede hiçbir bilgiye bağlanmamış eski kaynaklar kendiliğinden taslağa dönüşür (metin → not, dosya → ek).

## 11. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| PG kurulumunda "database cluster initialisation failed" | PG'yi kaldır, `C:\Program Files\PostgreSQL\16` klasörünü sil, Locale = `English, United States` ile yeniden kur |
| Servis başlamıyor | `C:\METIS\data\logs\service\*.log`, `C:\METIS\bin\metis doctor` |
| "Şema sürümü" uyarısı | `C:\METIS\bin\metis migrate` |
| Giriş sonrası 403 / CSRF | `METIS_PUBLIC_URL` tarayıcıdaki adresle aynı mı? |
| Mentor cevabı parça parça gelmiyor | ARR `responseBufferLimit=0` ve dinamik sıkıştırma kapalı mı? |
| Model eklenemiyor | "izin verilen ağların dışında" → adres iç ağda mı (`METIS_ENDPOINT_NETWORKS`)? https gerekiyor mu? Şirket CA'sı (`METIS_CA_BUNDLE`) |
| Disk doluyor | `C:\METIS\data\backups` saklama süresi (`--keep-days`), günlük boyutu |

## 12. Kaldırma

Paket klasöründe, yönetici PowerShell ile:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1              # servisler, görevler, program dosyaları
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveAll   # + veritabanı, ayarlar, ana anahtar, veriler, yedekler
```

Varsayılan kaldırma `C:\METIS\config`, `C:\METIS\data` ve `metis` veritabanını korur; aynı paketle yeniden kurunca
kaldığı yerden devam eder. `-RemoveAll` geri alınamaz. PostgreSQL'in kendisi kaldırılmaz.

## Ek: Kendi bilgisayarında deneme

Windows 10 veya 11 (64 bit) bir bilgisayarda, IIS ve sertifika olmadan, yalnız o bilgisayardan erişilecek şekilde:

1. PostgreSQL 16'yı kur (EDB kurucusu; `postgres` parolasını not al, port 5432). **Locale** sayfasında
   `English, United States` seç (2. bölüm, 3. madde); son ekranda Stack Builder işaretini kaldır.
2. Release sayfasından `METIS-<sürüm>-server-win64.zip` dosyasını indir. ZIP'e sağ tık → Özellikler → "Engellemeyi
   kaldır" (varsa) → Tamam; sonra sağ tık → **Tümünü ayıkla**.
3. Açılan klasörde **`METIS-Baslat.exe`**'ye çift tıkla. Komut yazmak gerekmez:
   - Windows "Windows bilgisayarınızı korudu" derse: **Ek bilgi → Yine de çalıştır** (exe imzasız; şirket bilgisayarında
     BT engelliyorsa aşağıdaki "Komutla kurulum"u kullan).
   - "METIS kurulacak, devam?" → **Evet** → yönetici izni (UAC) → **Evet**.
   - Açılan pencerede PostgreSQL `postgres` parolasını bir kez yaz (görünmez, kaydedilmez); kurulum birkaç dakika sürer.
   - Chrome (yoksa varsayılan tarayıcı) kurulum sayfasıyla açılır; **kurulum kodu hazır gelir**. Adını, kullanıcı adını,
     parolanı ve proje adını yazıp yönetici hesabını oluştur.
4. Sonraki her açışta `METIS-Baslat.exe` METIS'i (kapalıysa başlatıp) tarayıcıda açar. Yeni sürümün paketindeki
   `METIS-Baslat.exe` kurulu sürümü görür ve **yükseltmeyi önerir** (önce yedek alınır, sorun olursa geri döner).
5. Denemen bitince: `powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemoveAll`.

Komutla kurulum (exe kullanılamazsa): PowerShell'i **Yönetici olarak** aç, paket klasörüne geç ve
`powershell -ExecutionPolicy Bypass -File .\install-offline.ps1 -PublicUrl http://localhost:8000 -AllowHttp` çalıştır;
ekrana yazılan kurulum kodunu `http://localhost:8000` adresinde gir.

Bilmen gerekenler:
- `METIS-Baslat.exe` yalnız bu bilgisayardan erişilen **deneme kurulumunu** yapar. Ekibin ağdan bağlanacağı sunucu
  kurulumu (IIS + şirket sertifikası) için 4–5. bölümler; o kurulumda da exe sonraki açılışlarda doğru adresi açar.
- `-AllowHttp` yalnız deneme içindir: bağlantı şifresizdir ve uygulama geliştirme profilinde çalışır.
- Mentor ve görevler bir yapay zekâ modeli ister. Model eklemeden kaynak yükleme, katkı, inceleme, yayın, bilgi havuzu ve
  arama denenebilir; Mentor "model kullanılamıyor" der.
- Servisler bilgisayar her açıldığında kendiliğinden başlar; kaldırma betiği bunları da siler.
- Çift tıkladıktan sonra birkaç saniye içinde bir METIS sorusu en üstte açılır (görev çubuğunda da görünür). Açılmazsa
  tekrar tıklamadan önce `%TEMP%\METIS\baslat.log` dosyasına bak; başlatıcı zaten açıksa "zaten çalışıyor" der.
  (2.0.7 ve öncesinde sorular pencerelerin arkasında açılabiliyordu; 2.0.8'de düzeltildi.)
- Bu senaryo CI'da Windows Server 2022'de soru sormayan modda (kurulum, ikinci açılış, yükseltme), 2.0.8'den itibaren
  ayrıca Windows 10 masaüstünde çift tıklamayla (yükseltme, Chrome'da açılış) denendi. Windows 10'da etkileşimli ilk
  kurulum (UAC + parola sorusu) ve Windows 11 **denenmedi**.

## Ek: Linux (systemd)

`python deploy/build-bundle.py --target linux64` ile üretilen paket; önkoşul `python3.12` (venv) ve PostgreSQL 16
(roller 2. adımdaki SQL ile). Paket klasöründe:

```bash
sudo ./install.sh --public-url https://metis.sirket.local \
  --owner-url 'postgresql+psycopg://metis_owner:PAROLA@127.0.0.1:5432/metis' \
  --app-url   'postgresql+psycopg://metis_app:PAROLA@127.0.0.1:5432/metis'
sudo ./upgrade.sh            # yeni paketle yükseltme
/opt/metis/bin/metis doctor
```

Servisler: `metis-api`, `metis-worker`; zamanlayıcılar: `metis-backup.timer`, `metis-rehearsal.timer`. TLS için
nginx veya şirketin ters vekili; SSE için `proxy_buffering off`.
