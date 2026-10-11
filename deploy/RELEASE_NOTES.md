METIS v2 sunucu kurulum paketi (Windows, internetsiz). Dosya: `METIS-<sürüm>-server-win64.zip`; yanındaki `.sha256` ile doğrulanabilir.

**Kurulum:** ZIP'i aç, `BASLA.txt` ve `KURULUM.md` dosyalarını oku. Önkoşul: PostgreSQL 16.

**Kendi bilgisayarında deneme (Windows 10/11, IIS olmadan):** yönetici PowerShell ile
`powershell -ExecutionPolicy Bypass -File .\install-offline.ps1 -PublicUrl http://localhost:8000 -AllowHttp`,
sonra tarayıcıda `http://localhost:8000`. Örnek içerik: `C:\METIS\bin\metis demo`. Kaldırma: `uninstall.ps1 -RemoveAll`.

**Doğrulama:** bu paket CI'da Windows Server 2022 üzerinde ağ kapalıyken kuruldu; giriş, servis yeniden başlatma, yedek,
geri yükleme tatbikatı, örnek içerik, yükseltme ve kaldırma denendi.

**Henüz denenmedi:** gerçek şirket sunucusu (IIS/ARR + TLS), Windows 10/11 masaüstü, şirket modeliyle bağlantı,
gerçek v0.5.5 yedeğinin aktarılması. Tire içeren sürümler (ör. `-rc.1`) pilot amaçlı ön sürümdür.
