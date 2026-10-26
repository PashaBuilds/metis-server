"""Ölçek denemesi için kurgusal bilgi üreteci (gerçek şirket içeriği değildir).

Gömülü yazılım ekibinin notlarına benzeyen, aynı alanda çok sayıda sayfa üretir: alt sistem × belge türü × kart,
Türkçe ağırlıklı (yaklaşık üçte biri İngilizce), başlıklı bölümler, tanımlayıcılar (yazmaç, fonksiyon, hex adres),
sayı/birim değerleri ve sorun kaydı biçiminde notlar. Ölçüm derlemi (`evals/retrieval/corpus.py`) ile aynı sözcük
dağarcığını paylaşır; böylece ölçüm soruları büyük derlemde gerçekçi "rakiplerle" yarışır. Deterministik: aynı sıra
numarası her zaman aynı sayfayı verir.
"""

from __future__ import annotations

import random

BOARDS = ["R3", "M12", "T4", "Z9", "A5", "B8", "C2", "D6", "E1", "F7", "G3", "H5", "J2", "L8", "N4", "P6"]

TOPICS: list[tuple[str, str, list[str]]] = [
    # (ad, kısaltma, konuya özgü sözcükler)
    ("UART", "UART", ["baud hızı", "seri konsol", "FIFO", "parite", "stop biti", "akış denetimi"]),
    ("SPI", "SPI", ["saat kutbu", "chip select", "MISO hattı", "çerçeve boyu", "DMA aktarımı"]),
    ("I2C", "I2C", ["adres", "pull-up direnci", "saat uzatma", "ACK", "veri yolu kilitlenmesi"]),
    ("CAN", "CAN", ["bit zamanlaması", "örnekleme noktası", "hata sayacı", "bus-off", "filtre"]),
    ("Ethernet MAC", "EMAC", ["PHY", "MDIO", "bağlantı hızı", "RGMII gecikmesi", "çerçeve kaybı"]),
    ("PCIe", "PCIE", ["bağlantı eğitimi", "hat sayısı", "BAR", "MSI kesmesi", "Gen2 hızı"]),
    ("USB", "USB", ["enumerasyon", "uç nokta", "VBUS", "yüksek hız", "tanımlayıcı"]),
    ("DMA", "DMA", ["tanımlayıcı halkası", "kanal", "önbellek tutarlılığı", "aktarım boyu", "kesme"]),
    ("ADC", "ADC", ["örnekleme hızı", "referans gerilimi", "kalibrasyon", "gürültü", "kanal tarama"]),
    ("PWM", "PWM", ["görev oranı", "frekans", "ölü zaman", "tetik", "zamanlayıcı"]),
    ("GPIO", "GPIO", ["pin", "kesme kenarı", "debounce", "çekme direnci", "yön yazmacı"]),
    ("Watchdog", "WDT", ["zaman aşımı", "besleme", "sıfırlama nedeni", "erken uyarı", "pencere"]),
    ("RTC", "RTC", ["kristal", "alarm", "yedek pil", "saat kayması", "takvim"]),
    ("Bootloader", "BOOT", ["açılış modu", "imaj başlığı", "imza", "yedek bölüm", "geri dönüş"]),
    ("QSPI flash", "QSPI", ["sektör silme", "dört hat okuma", "yazma koruması", "sayfa programlama", "XIP"]),
    ("DDR", "DDR", ["eğitim", "zamanlama parametresi", "ECC", "yenileme", "veri gözü"]),
    ("Güç yönetimi", "PMU", ["uyku modu", "uyanma kaynağı", "gerilim rayı", "akım tüketimi", "sıralama"]),
    ("Saat ağacı", "CLK", ["PLL", "bölücü", "kilit süresi", "saat kapısı", "referans saat"]),
    ("Sıcaklık izleme", "TMON", ["eşik", "histerezis", "sensör", "kısma", "alarm"]),
    ("RTOS zamanlayıcı", "OS", ["görev önceliği", "yığın boyu", "tick", "kilitlenme", "kuyruk"]),
    ("Kesme denetleyicisi", "GIC", ["öncelik", "maskeleme", "iç içe kesme", "vektör", "gecikme"]),
    ("Önbellek ve MMU", "MMU", ["sayfa tablosu", "önbellek temizleme", "erişim hatası", "eşleme", "TLB"]),
    ("Güvenli açılış", "SBOOT", ["anahtar özeti", "imza doğrulama", "eFuse", "şifreli imaj", "geri alma koruması"]),
    ("OTA güncelleme", "OTA", ["paket", "bölüm değişimi", "doğrulama", "kesinti", "sürüm"]),
    ("Motor sürücü", "MOTOR", ["akım döngüsü", "enkoder", "hız rampası", "aşırı akım", "fren"]),
    ("Ses kodeği", "CODEC", ["I2S", "örnekleme oranı", "kazanç", "gürültü tabanı", "tampon"]),
    ("LTE modem", "MDM", ["AT komutu", "sinyal gücü", "bağlantı kopması", "PDP bağlamı", "güç tasarrufu"]),
    ("GNSS", "GNSS", ["uydu sayısı", "ilk konum süresi", "PPS", "anten", "NMEA cümlesi"]),
    ("Pil şarj", "CHG", ["şarj akımı", "sabit gerilim", "sıcaklık sınırı", "dolum", "koruma"]),
    ("EEPROM", "EEP", ["yazma döngüsü", "sayfa sınırı", "yazma süresi", "adres", "bütünlük"]),
    ("Şifreleme motoru", "CRYP", ["AES", "anahtar yuvası", "rastgele sayı", "kimlik doğrulama etiketi", "hızlandırıcı"]),
    ("Ekran", "DISP", ["piksel saati", "çerçeve tamponu", "arka ışık", "zamanlama", "yenileme hızı"]),
]

KINDS_TR = ["sürücü notları", "bring-up notları", "sorun kaydı", "test prosedürü", "tasarım notu", "ölçüm raporu"]
KINDS_EN = ["driver notes", "bring-up log", "issue", "test procedure", "design note", "measurement report"]

SECTIONS_TR = ["Genel bakış", "Yapılandırma", "Yazmaçlar", "Zamanlama", "Başlatma sırası", "Sorun giderme", "Ölçümler",
               "Bilinen sorunlar", "Test adımları", "Notlar"]
SECTIONS_EN = ["Overview", "Configuration", "Registers", "Timing", "Init sequence", "Troubleshooting", "Measurements",
               "Known issues", "Test steps", "Notes"]

FIELDS = ["CTRL", "STAT", "CFG", "MODE", "DIV", "EN", "IRQ", "MASK", "DATA", "TIMEOUT", "THRESH", "PRESET", "STATE"]
VERBS = ["init", "start", "stop", "reset", "config", "read", "write", "poll", "enable", "disable", "calibrate"]
UNITS = [("ms", 1, 500), ("µs", 1, 900), ("MHz", 1, 400), ("kHz", 1, 900), ("mA", 1, 1500), ("V", 1, 12), ("°C", 20, 125),
         ("KB", 4, 512), ("Mbps", 1, 1000)]

TR_SENTENCES = [
    "{word} için {sym} yazmacı kullanılır; değer {num} olarak ayarlanır.",
    "{func} çağrısı {word} adımını tamamlar ve {sym} bitini temizler.",
    "Açılışta {word} en az {num} bekler; bu süre kısalırsa {topic} hatası görülür.",
    "{topic} tarafında {word} sorunu {board} kartında da görüldü, çözüm {sym} değerinin değiştirilmesiydi.",
    "Ölçülen {word} ortalama {num}; üst sınır {num2}.",
    "{sym} yazmacında {hex} değeri {word} durumunu gösterir.",
    "Sürücü {func} ile {word} ayarını yapar, ardından {func2} çağrılır.",
    "{word} kapatılınca hata kayboldu; kök neden {topic} yapılandırmasındaki yanlış {word2} idi.",
    "Varsayılan {word} {num}; yüksek yükte {num2} değerine çıkarılır.",
    "{topic} denetleyicisi {hex} adresinden eşlenir ve {word} için önbelleksiz işaretlenir.",
    "Test sırasında {word} {num} aşarsa adım başarısız sayılır ve kayıt alınır.",
    "Bu kartta {word} yapılırken {sym} alanı salt okunurdur.",
]
EN_SENTENCES = [
    "The {sym} register controls {word}; it is set to {num} by default.",
    "Calling {func} completes the {word} step and clears {sym}.",
    "{word} must settle for at least {num}, otherwise the {topic} block reports an error.",
    "Measured {word} averaged {num} with a worst case of {num2}.",
    "A value of {hex} in {sym} indicates the {word} state.",
    "The fix for the {word} issue on {board} was to change {sym} and call {func2} after reset.",
    "Disabling {word} removed the failure; the root cause was a wrong {word2} setting in {topic}.",
    "The {topic} controller is mapped at {hex} and marked uncached for {word}.",
    "If {word} exceeds {num} during the test the step fails and a log is captured.",
]
ISSUE_TR = ["Belirti", "Yorumlar", "Kök neden", "Çözüm"]
ISSUE_EN = ["Symptom", "Comments", "Root cause", "Resolution"]


def _num(rng: random.Random) -> str:
    unit, lo, hi = rng.choice(UNITS)
    return f"{rng.randint(lo, hi)} {unit}"


def _sentence(rng: random.Random, en: bool, topic: tuple[str, str, list[str]], board: str, syms: list[str], funcs: list[str]) -> str:
    tpl = rng.choice(EN_SENTENCES if en else TR_SENTENCES)
    words = topic[2]
    return tpl.format(
        word=rng.choice(words),
        word2=rng.choice(words),
        sym=f"`{rng.choice(syms)}`",
        func=f"`{rng.choice(funcs)}()`",
        func2=f"`{rng.choice(funcs)}()`",
        num=_num(rng),
        num2=_num(rng),
        hex=f"0x{rng.randrange(16**8):08X}",
        topic=topic[0],
        board=rng.choice(BOARDS),
    )


def page(i: int) -> tuple[str, str, str]:
    """Sıra numarası `i` için (kart, başlık, gövde). Başlık sıra numarasını taşır: aynı başlık iki kez üretilmez."""
    rng = random.Random(1_000_003 * (i + 1))
    topic = TOPICS[rng.randrange(len(TOPICS))]
    # Ölçüm derleminin kartı (VPK120) da seçilebilir: kart süzgeçli ölçümde iğnelerin aynı karttan rakipleri olur.
    board = (*BOARDS, "VPK120")[rng.randrange(len(BOARDS) + 1)]
    en = rng.random() < 0.33
    abbr = topic[1]
    syms = [f"{board}_{abbr}{rng.randint(0, 3)}_{f}" for f in rng.sample(FIELDS, 4)]
    funcs = [f"{abbr.lower()}_{v}" for v in rng.sample(VERBS, 3)]
    issue = rng.random() < 0.25
    if issue:
        kind = "issue" if en else "sorun kaydı"
        sections = ISSUE_EN if en else ISSUE_TR
    else:
        kind = rng.choice(KINDS_EN if en else KINDS_TR)
        sections = rng.sample(SECTIONS_EN if en else SECTIONS_TR, rng.randint(3, 7))
    title = f"{topic[0]} {kind} ({board}) #{i}"
    parts = []
    for s in sections:
        parts.append(f"## {s}")
        for _ in range(rng.randint(1, 2)):
            parts.append(" ".join(_sentence(rng, en, topic, board, syms, funcs) for _ in range(rng.randint(2, 4))))
    return board, title, "\n\n".join(parts) + "\n"
