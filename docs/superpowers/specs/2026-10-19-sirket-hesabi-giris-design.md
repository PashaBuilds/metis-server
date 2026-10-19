# Şirket hesabıyla giriş (Active Directory / LDAP) — tasarım

Tarih: 2026-10-19 · Ürün sahibinin isteği ve onayı ("Windows'a giriş ne ise METIS'e giriş de aynı olsun; şifrelerin
hiçbirini saklamayacak şekilde altyapıyı kur").

## Amaç
- Kullanıcı METIS'e Windows'a girdiği kullanıcı adı ve parolayla girer. Yönetici her kullanıcıyı elle tanımlamaz.
- İlk girişte METIS hesabı kendiliğinden oluşur (ad dizinden gelir); yönetici sonra rol verir.
- Hiçbir parola saklanmaz: ne kullanıcının parolası ne bir hizmet hesabı parolası. Doğrulama her girişte dizine
  kullanıcının kendi bilgileriyle yapılan bağlanmadır (LDAP simple bind, LDAPS üzerinden).

## Kararlar
- Protokol: LDAPS (`ldaps://`, 636). Şifresiz `ldap://` kabul edilmez (parola ağda açık giderdi).
- Tarayıcı ↔ METIS: şirket parolası METIS'e geldiği için şirket hesabıyla giriş yalnız `METIS_PUBLIC_URL` https iken
  açılır ve çalışır (`HTTPS_REQUIRED`). Yerel hesaplar (kurulumdaki yönetici) her zaman çalışır: yedek giriş.
- Kütüphane: `ldap3` (saf Python, internetsiz pakete kilitli hash'le girer).
- Ayarlar veritabanında (`directory_settings`, tek satır), Ayarlar → **Şirket hesabıyla giriş** (yalnız yönetici).
  Alanlar: sunucu adresi, etki alanı (UPN soneki `sirket.com.tr` ya da NetBIOS adı `SIRKET`), arama kökü (DN; boşsa
  UPN sonekinden türetilir), isteğe bağlı izinli grup (DN; doğrudan üyelik), yeni gelenlere rol: okur (varsayılan, ürün sahibinin kararı) | yok.
- Bağlanma adı: kullanıcı `ad`, `ad@sonek` ya da `ALAN\ad` yazabilir; METIS `ad` kısmını alır ve ayara göre
  `ad@sonek` ya da `ALAN\ad` ile bağlanır. Boş parola reddedilir (LDAP'ta boş parola anonim bağlanma demektir).
- Bağlandıktan sonra kullanıcı kendi kaydını okur: `sAMAccountName`, `displayName`, `mail`, `objectGUID`, `memberOf`.
  METIS kullanıcısı `objectGUID` ile eşleşir (`users.external_id`), `auth_source='directory'`, `password_hash` boş.
- Yerel hesapla aynı kullanıcı adındaki bir dizin hesabı yerel hesabı ele geçiremez: yerel hesap her zaman yerel
  parolayla doğrulanır; çakışan dizin girişi reddedilir.
- Dizin kullanıcısının parolası METIS'te değiştirilemez/sıfırlanamaz; hesabı kapatmak için yönetici METIS'te pasifleştirir
  ya da dizinde kapatılır (bir sonraki girişte bağlanma başarısız olur).
- Rolsüz kullanıcı giriş yapınca "yöneticinin rol vermesi bekleniyor" ekranını görür.
- Dizine ulaşılamazsa "şirket dizinine ulaşılamadı" (yanlış parola değil); başarısız denemeler mevcut hız sınırına
  sayılır (AD hesap kilitlenmesine karşı da koruma).

## Kapsam dışı (şimdilik)
- Parola sormadan Windows oturumuyla otomatik giriş (Kerberos/NTLM): IIS ve tarayıcı ayarı ister; ayrı iş.
- İç içe grup üyeliği, AD gruplarından rol eşleme.
