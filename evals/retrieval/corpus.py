"""Arama ölçümü için kurgusal derlem ve soru seti (gerçek şirket içeriği değildir).

Kurgusal bir gömülü yazılım ekibinin (kart "K7") notları: uzun, çok başlıklı dokümanlar; kısa notlar; issue biçiminde
sorun → yorumlar → çözüm kayıtları. Türkçe ve İngilizce karışık, tanımlayıcı yoğun. Sorular türlerine göre etiketli:
`tanimlayici` (sembol/hex), `kavram`, `nasil`, `issue` (daha önce görüldü mü), `karisik` (TR↔EN, ASCII yazım).
"""

from __future__ import annotations

PAGES: list[tuple[str, str, str]] = [
    (
        "pcie-bringup",
        "PCIe bağlantı kurulumu (K7)",
        """## Genel bakış

K7 kartında PCIe denetleyicisi kök kompleks olarak çalışır ve dört hatlı (x4) bağlantı kurar. Bu doküman açılıştan
L0 durumuna kadar olan adımları ve sık görülen sorunları anlatır.

## Saat ve sıfırlama

Referans saat 100 MHz'dir ve kart üzerindeki saat üretecinden gelir. PERST# sinyali güç rayları kararlı olduktan sonra
en az 100 ms aktif tutulur; bu süre kısalırsa uç nokta cihaz algılanmaz.

## LTSSM durumları

Bağlantı eğitimi LTSSM durum makinesiyle ilerler: Detect, Polling, Configuration ve L0. Durum `LTSSM_STATE` yazmacından
okunur; 0x11 değeri L0 demektir, yani bağlantı kullanıma hazırdır. 0x00 değeri Detect durumunda takılı kalındığını gösterir.

## Gen3 eşitleme

Gen3 hızında eşitleme (equalization) zorunludur. Kurgusal kartımızda en kararlı sonuç P7 ön ayarıyla alındı; ön ayar
`PCIE_EQ_PRESET` yazmacına yazılır. Eşitleme başarısız olursa bağlantı Gen1 hızına düşer.

## BAR yapılandırması

Uç nokta BAR0 için 64 KB bellek alanı ister. Kök kompleks tarafında bu alan 0xA0000000 adresinden eşlenir ve önbelleksiz
(uncached) işaretlenir.

## MSI-X kesmeleri

Kesmeler MSI-X ile alınır; sürücü `XPcie_EnableMsix` çağrısıyla vektör tablosunu etkinleştirir. Vektör sayısı 8 ile
sınırlıdır.

## Sorun giderme

Bağlantı Gen1'de kalıyorsa önce referans saatte yayılı spektrum (SSC) açık mı bakılır; kurgusal uç noktamız SSC'yi
desteklemez. Cihaz hiç görünmüyorsa PERST# süresi ve 3.3 V rayı ölçülür.

## Ölçümler

Soğuk açılışta bağlantı ortalama 180 ms'de L0'a ulaşır. Gen3 x4 ile ölçülen DMA okuma hızı 2.9 GB/s'dir.
""",
    ),
    (
        "boot-flow",
        "Açılış akışı: FSBL, U-Boot, Linux",
        """## BootROM

Güç verildiğinde BootROM açılış modunu MODE pinlerinden okur ve QSPI flash'tan FSBL'yi yükler.

## FSBL

FSBL saatleri ve DDR'ı hazırlar, ardından `fsbl_handoff` ile U-Boot'a geçer. FSBL bitstream yüklemesini de yapar.

## DDR eğitimi

DDR eğitimi `ddr_train` fonksiyonuyla iki kez denenir. İkinci deneme de başarısız olursa FSBL hata LED'ini yakar ve
durur.

## U-Boot ortam değişkenleri

U-Boot açılış komutu `bootcmd` değişkenindedir. Bekleme süresi `bootdelay=3` olarak ayarlıdır; seri konsoldan bir tuşa
basılırsa otomatik açılış durur.

## Device tree

Device tree blob (dtb) DDR'da 0x00100000 adresine yüklenir. Kart varyantına göre farklı dtb seçimi `fdtfile` değişkeniyle
yapılır.

## Kernel komut satırı

Kernel komut satırında konsol `console=ttyPS0,115200` olarak verilir; kök dosya sistemi eMMC'nin ikinci bölümüdür.

## Güvenli açılış

Güvenli açılışta açık anahtarın özeti eFUSE'a yazılır. Bu işlem geri alınamaz; geliştirme kartlarında yapılmaz.

## Kurtarma

Flash bozulursa kart JTAG ile açılır ve FSBL yeniden yazılır.
""",
    ),
    (
        "spi-flash",
        "SPI NOR flash sürücüsü",
        """## Donanım

QSPI denetleyicisi dört veri hattıyla NOR flash'a bağlıdır. Flash kapasitesi 64 MB'tır.

## Saat ayarı

SPI saat bölücüsü 4 seçildiğinde 200 MHz referanstan 50 MHz SCLK elde edilir. Daha yüksek hızda okuma hataları görüldü.

## Komutlar

Hızlı okuma için quad output read komutu 0x6B kullanılır. 64 KB blok silme komutu 0xD8'dir; tüm yonga silme 0xC7.

## Dummy cycle

Quad okumada 8 dummy cycle gerekir. Bu değer yanlış ayarlanırsa okunan veri bir bayt kayar.

## Yazma koruması

Durum yazmacındaki BP bitleri blok korumasını belirler. Fabrika ayarında BP bitleri 0'dır; üretimde FSBL bölgesi
korunur.

## JEDEC kimliği

Açılışta JEDEC ID okunur. 0xFFFFFF okunuyorsa CS hattı ya da flash beslemesi kontrol edilir.
""",
    ),
    (
        "power-mgmt",
        "Güç yönetimi ve uyku modları",
        """## Güç rayları

Çekirdek beslemesi VCCINT 0.85 V'tur. Yardımcı ray VCCAUX 1.8 V'tur.

## PMIC

PMIC I2C üzerinden 0x2D adresinde yönetilir. Ray gerilimleri PMIC yazmaçlarıyla değiştirilir.

## Uyku modu

Kart suspend-to-RAM destekler; DDR öz-tazeleme (self-refresh) moduna alınır.

## Uyanma kaynakları

Uykudan uyanma GPIO 12 ve RTC alarmıyla mümkündür.

## Watchdog ile uyku

Uykuya girmeden önce watchdog `wdt_pause` ile durdurulmalıdır; aksi hâlde uyku sırasında besleme yapılamaz ve kart
yeniden başlar.

## DVFS

Frekans ve gerilim tablosu üç noktalıdır: 600 MHz, 1000 MHz ve 1300 MHz.
""",
    ),
    ("uart-console", "Hata ayıklama konsolu (UART)", "Konsol 115200 baud, 8N1 ayarındadır. `UART0_BASE` adresi 0xFF000000'dır.\n\nAkış denetimi (RTS/CTS) kapalıdır."),
    (
        "i2c-bus",
        "I2C veri yolu",
        "I2C veri yolu 400 kHz hızında çalışır; hat başına 2.2 kΩ pull-up dirençleri vardır.\n\n"
        "SCL hattı düşük takılırsa `i2c_bus_recover` dokuz saat darbesi göndererek yolu kurtarır.",
    ),
    ("gpio-irq", "GPIO kesmeleri", "GPIO kesmeleri kenar tetiklemeli ayarlanır: `gpio_irq_set_type` ile yükselen kenar seçilir.\n\nMekanik butonlarda 10 ms debounce uygulanır."),
    (
        "dma-engine",
        "DMA motoru",
        "DMA motoru scatter-gather tanımlayıcı zincirleriyle çalışır. Tanımlayıcılar 64 bayt hizalı olmalıdır.\n\n"
        "Cihazdan belleğe aktarımdan sonra işlemci veriyi okumadan önce `dma_sync_single_for_cpu` çağrılmalıdır; aksi hâlde "
        "önbellekteki eski veri okunur.",
    ),
    (
        "ethernet-phy",
        "Ethernet PHY",
        "PHY MDIO üzerinden 7 adresindedir. RGMII zamanlaması için alma yönünde 2 ns gecikme gerekir; gecikme PHY tarafında "
        "`rx-internal-delay-ps = 2000` ile verilir.\n\nOtomatik anlaşma (autoneg) açıktır.",
    ),
    ("watchdog", "Watchdog zamanlayıcısı", "Watchdog zaman aşımı 10 saniyedir. Uygulama `wdt_kick` ile her 2 saniyede besleme yapar.\n\nZaman aşımında kart donanımsal olarak yeniden başlar."),
    (
        "clock-tree",
        "Saat ağacı",
        "Çevre birimlerinin saat kaynağı `CLK_SRC` yazmacıyla seçilir: 0 dahili osilatör, 1 harici kristal, 2 PLL çıkışı.\n\n"
        "PLL kilitlenmesi en çok 100 µs sürer. Frekans `clk_set_rate` ile değiştirilir.",
    ),
    (
        "memory-map",
        "Bellek haritası",
        "DDR 0x00000000–0x7FFFFFFF aralığındadır. OCM 0xFFFC0000 adresindedir.\n\nDMA için 16 MB ayrılmış bellek (reserved-memory) "
        "device tree'de tanımlıdır.",
    ),
    (
        "yocto-build",
        "Yocto derleme ortamı",
        'Kart için makine adı `MACHINE = "k7-kurgu"` olarak ayarlanır.\n\nİmaj `bitbake core-image-minimal` ile derlenir; sstate '
        "önbelleği ortak sunucudadır.",
    ),
    (
        "coding-std",
        "Driver coding guidelines",
        "Drivers return negative errno values on failure.\n\nBusy-wait loops longer than 10 microseconds are not allowed; use "
        "`readl_poll_timeout` instead.\n\nUse `readl_relaxed` only when ordering with DMA is not required.",
    ),
    ("thermal", "Termal yönetim", "Sıcaklık `TEMP_SENSOR0` ile okunur. 85 °C'de frekans kısılır, 100 °C'de kart kapanır."),
    (
        "issue-pcie-gen1",
        "PCIe link stays at Gen1",
        """**Durum:** Kapalı · **Etiketler:** pcie · **Açan:** Kurgusal Yazılımcı · 2026-02-03

After board power-up the PCIe link trains only at Gen1 x4. Expected Gen3.

## Yorumlar

### Kurgusal BSP — 2026-02-04

Eşitleme ön ayarlarını P4 ve P7 ile denedik, değişmedi.

### Kurgusal BSP — 2026-02-05

Çözüm: referans saatte yayılı spektrum (SSC) açıktı. SSC kapatılınca bağlantı Gen3 x4'te kuruldu.
""",
    ),
    (
        "issue-uboot-env",
        "U-Boot ortamı her açılışta sıfırlanıyor",
        """**Durum:** Kapalı · **Etiketler:** u-boot · **Açan:** Kurgusal Kişi · 2026-03-10

`saveenv` sonrası yeniden açılışta değişkenler varsayılana dönüyor.

## Yorumlar

### Kurgusal BSP — 2026-03-11

Ortam bölgesi flash sektörüyle hizalı değildi. `CONFIG_ENV_OFFSET` 0x1E0000 yapılınca düzeldi.
""",
    ),
    (
        "issue-i2c-hang",
        "I2C sensör okuması kilitleniyor",
        """**Durum:** Kapalı · **Etiketler:** i2c · **Açan:** Kurgusal Kişi · 2026-04-02

Sıcaklık sensörü okunurken sürücü sonsuza kadar bekliyor.

## Yorumlar

### Kurgusal BSP — 2026-04-03

SCL hattı düşük kalıyordu. Yol kurtarma eklendi ve pull-up 4.7 kΩ'dan 2.2 kΩ'a indirildi; sorun bitti.
""",
    ),
    (
        "issue-dma-corrupt",
        "DMA ile alınan veri bozuk",
        """**Durum:** Kapalı · **Etiketler:** dma · **Açan:** Kurgusal Yazılımcı · 2026-05-12

Received buffers contain stale bytes intermittently.

## Yorumlar

### Kurgusal BSP — 2026-05-13

Önbellek geçersiz kılma eksikti. Aktarım bitince `dma_sync_single_for_cpu` çağrısı eklendi.
""",
    ),
    (
        "issue-wdt-reset",
        "Uyku modunda watchdog reset",
        """**Durum:** Kapalı · **Etiketler:** güç, watchdog · **Açan:** Kurgusal Kişi · 2026-06-01

Kart uykuya girdikten yaklaşık 10 saniye sonra yeniden başlıyor.

## Yorumlar

### Kurgusal BSP — 2026-06-02

Uykuya girmeden watchdog durdurulmuyordu. Suspend yolunda `wdt_pause` çağrısı eklendi.
""",
    ),
    (
        "issue-eth-crc",
        "Ethernet CRC hataları",
        """**Durum:** Kapalı · **Etiketler:** ethernet · **Açan:** Kurgusal Yazılımcı · 2026-07-07

Yük altında alınan paketlerde CRC hatası sayacı artıyor.

## Yorumlar

### Kurgusal BSP — 2026-07-08

RGMII gecikmesi hem MAC hem PHY tarafında verilmişti (çift gecikme). Gecikme yalnız PHY'de bırakıldı, hata kalmadı.
""",
    ),
]

# (soru, beklenen sayfa(lar), beklenen alıntı (blokta birebir geçer) ya da "", tür)
QUESTIONS: list[tuple[str, list[str], str, str]] = [
    ("LTSSM_STATE 0x11 ne anlama gelir?", ["pcie-bringup"], "0x11 değeri L0 demektir", "tanimlayici"),
    ("PERST# ne kadar süre aktif tutulmalı?", ["pcie-bringup"], "en az 100 ms aktif tutulur", "kavram"),
    ("Gen3 eşitlemede hangi ön ayar kullanılıyor?", ["pcie-bringup"], "P7 ön ayarıyla alındı", "kavram"),
    ("XPcie_EnableMsix", ["pcie-bringup"], "XPcie_EnableMsix", "tanimlayici"),
    ("BAR0 kaç KB alan ister?", ["pcie-bringup"], "BAR0 için 64 KB", "kavram"),
    ("PCIe bağlantısı neden Gen1'de kalıyor?", ["issue-pcie-gen1", "pcie-bringup"], "SSC kapatılınca", "issue"),
    ("PCIe link only trains at Gen1, how was it fixed?", ["issue-pcie-gen1"], "SSC kapatılınca", "karisik"),
    ("DDR eğitimi kaç kez denenir?", ["boot-flow"], "iki kez denenir", "kavram"),
    ("U-Boot bootdelay kaç saniye?", ["boot-flow"], "bootdelay=3", "tanimlayici"),
    ("dtb hangi adrese yüklenir?", ["boot-flow"], "0x00100000", "tanimlayici"),
    ("kernel console parametresi nedir", ["boot-flow"], "console=ttyPS0,115200", "kavram"),
    ("fsbl_handoff", ["boot-flow"], "fsbl_handoff", "tanimlayici"),
    ("Flash bozulursa kart nasıl kurtarılır?", ["boot-flow"], "JTAG ile açılır", "nasil"),
    ("U-Boot ortam değişkenleri neden kaydedilmiyor?", ["issue-uboot-env"], "CONFIG_ENV_OFFSET", "issue"),
    ("CONFIG_ENV_OFFSET değeri", ["issue-uboot-env"], "0x1E0000", "tanimlayici"),
    ("quad read komutu hangisi?", ["spi-flash"], "0x6B", "kavram"),
    ("SPI saat bölücüsü kaç seçilmeli?", ["spi-flash"], "bölücüsü 4 seçildiğinde", "nasil"),
    ("quad okumada kaç dummy cycle gerekir", ["spi-flash"], "8 dummy cycle", "kavram"),
    ("JEDEC ID 0xFFFFFF okunuyor", ["spi-flash"], "CS hattı", "tanimlayici"),
    ("flash 64 KB blok silme komutu", ["spi-flash"], "0xD8", "kavram"),
    ("PMIC hangi I2C adresinde?", ["power-mgmt"], "0x2D", "kavram"),
    ("VCCINT gerilimi kaç volt?", ["power-mgmt"], "0.85 V", "tanimlayici"),
    ("Uyku modunda kart neden yeniden başlıyor?", ["issue-wdt-reset", "power-mgmt"], "wdt_pause", "issue"),
    ("uykudan uyanma kaynakları neler", ["power-mgmt"], "GPIO 12", "kavram"),
    ("konsol baud hızı", ["uart-console"], "115200 baud", "kavram"),
    ("UART0_BASE", ["uart-console"], "0xFF000000", "tanimlayici"),
    ("how to recover a stuck I2C bus", ["i2c-bus", "issue-i2c-hang"], "", "karisik"),
    ("I2C sensör okuması kilitleniyor ne yapıldı", ["issue-i2c-hang"], "Yol kurtarma eklendi", "issue"),
    ("i2c pull-up direnci kaç ohm", ["i2c-bus", "issue-i2c-hang"], "2.2 kΩ", "kavram"),
    ("buton debounce süresi", ["gpio-irq"], "10 ms debounce", "kavram"),
    ("gpio_irq_set_type", ["gpio-irq"], "gpio_irq_set_type", "tanimlayici"),
    ("DMA ile gelen veri bozuk, çözüm?", ["issue-dma-corrupt", "dma-engine"], "dma_sync_single_for_cpu", "issue"),
    ("DMA tanımlayıcı hizalaması", ["dma-engine"], "64 bayt hizalı", "kavram"),
    ("stale data after DMA receive", ["issue-dma-corrupt", "dma-engine"], "", "karisik"),
    ("PHY MDIO adresi", ["ethernet-phy"], "7 adresindedir", "kavram"),
    ("Ethernet CRC hataları neden oluyor?", ["issue-eth-crc"], "çift gecikme", "issue"),
    ("RGMII gecikmesi nerede verilmeli", ["ethernet-phy", "issue-eth-crc"], "", "nasil"),
    ("watchdog besleme aralığı", ["watchdog"], "her 2 saniyede", "kavram"),
    ("saat kaynagi nasil secilir", ["clock-tree"], "CLK_SRC", "karisik"),
    ("PLL kilitlenme süresi", ["clock-tree"], "100 µs", "kavram"),
    ("OCM adresi nedir", ["memory-map"], "0xFFFC0000", "tanimlayici"),
    ("Yocto MACHINE ayarı", ["yocto-build"], 'MACHINE = "k7-kurgu"', "tanimlayici"),
    ("meşgul bekleme döngüsü kuralı", ["coding-std"], "readl_poll_timeout", "karisik"),
    ("kart kaç derecede kapanır", ["thermal"], "100 °C'de kart kapanır", "kavram"),
]
