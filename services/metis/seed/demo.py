"""Kurgusal çalışma alanı (yalnız geliştirme profili).

Tüm içerik KURGUSALDIR; proje `is_demo=True` olarak işaretlenir ve UI her yerde "Kurgusal" etiketi gösterir.
Gerçek şirket/kart verisi değildir; sayılar ve semboller örnek amaçlıdır.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from metis.core.config import get_settings
from metis.core.db import transaction
from metis.core.errors import AppError
from metis.core.models import Project, ProjectMember, ScopeValue, User
from metis.core.security import hash_password
from metis.modules.auth.service import ensure_worker_identity
from metis.modules.changes import schemas as cs
from metis.modules.changes import service as changes
from metis.modules.scopes.service import ensure_default_schedule
from metis.modules.sources import schemas as ss
from metis.modules.sources import service as sources

DEMO_PASSWORD = "Kurgusal-Parola-2026"  # noqa: S105 — yalnız geliştirme profili

SCOPES = {
    "domain": ["Gömülü yazılım", "FPGA"],
    "yatt": ["Haberleşme", "Güç yönetimi"],
    "kart": ["VPK120", "ZCU102", "K2"],
    "proje": ["Kurgusal-Atlas", "Kurgusal-Orion"],
}

S_VPK = {"domain": ["Gömülü yazılım"], "yatt": ["Haberleşme"], "kart": ["VPK120"], "proje": ["Kurgusal-Atlas"]}
S_ZCU = {"domain": ["Gömülü yazılım"], "yatt": ["Haberleşme"], "kart": ["ZCU102"], "proje": ["Kurgusal-Orion"]}
S_GEN = {"domain": ["Gömülü yazılım"], "yatt": [], "kart": ["*"], "proje": []}
S_FPGA = {"domain": ["FPGA"], "yatt": ["Haberleşme"], "kart": ["VPK120"], "proje": ["Kurgusal-Atlas"]}

NOTES = [
    {
        "key": "pcie_irq",
        "title": "AXI PCIe kesme yönetimi — uzman notu",
        "kind": "note",
        "scope": S_VPK,
        "text": (
            "AXI PCIe köprüsü kesme yönetimi (kurgusal uzman notu)\n\n"
            "VPK120 kartında AXI PCIe köprüsü MSI kesmelerini XAxiPcie_IntrEnable() çağrısı ile etkinleştirir.\n"
            "Kesme maskesi XPAR_XAXIPCIE_0_BASEADDR + 0x13C adresindeki IMR kaydında tutulur.\n"
            "Kesme işleyicisi (ISR) içinde yalnız durum bitleri temizlenir; uzun işler görev bağlamına ertelenir.\n"
            "ISR içinde printf kullanılmaz.\n"
        ),
    },
    {
        "key": "pcie_link",
        "title": "Link eğitimi Gen1'de kalma — problem kaydı",
        "kind": "test",
        "scope": S_VPK,
        "text": (
            "Problem kaydı PR-0412 (kurgusal)\n\n"
            "Belirti: PCIe link eğitimi Gen3 yerine Gen1 hızında tamamlanıyor.\n"
            "Link eğitimi Gen1 hızında kalırsa önce referans saatin 100 MHz olduğu doğrulanır.\n"
            "LTSSM durumu Recovery.Speed adımında takılıyorsa eşitleme (equalization) ayarları kontrol edilir.\n"
            "Saat düzeltildikten sonra link Gen3 x4 olarak eğitildi.\n"
        ),
    },
    {
        "key": "spi",
        "title": "SPI saat bölücü — sürücü kodu",
        "kind": "code",
        "scope": S_ZCU,
        "text": (
            "/* spi_clock.c — kurgusal sürücü parçası */\n"
            "#define SPI_REF_CLK_HZ 100000000u\n"
            "SPI denetleyicisi 100 MHz referans saatini 8 bölücü ile 12.5 MHz SCLK'ye indirir.\n"
            "void spi_set_divider(uint8_t div) { SPI_CR1 = (SPI_CR1 & ~0x38u) | ((div & 0x7u) << 3); }\n"
            "Bölücü değeri INIT_BUS çağrısından sonra yazılır.\n"
        ),
    },
    {
        "key": "uart",
        "title": "UART halka tamponu tasarım notu",
        "kind": "note",
        "scope": S_GEN,
        "text": (
            "UART alım tamponu (kurgusal tasarım notu)\n\n"
            "UART alım yolu halka tampon (ring buffer) kullanır.\n"
            "Halka tampon tek üretici ve tek tüketici ile çalışır; kilit kullanılmaz.\n"
            "Tampon boyutu 512 bayttır ve 2'nin kuvveti olarak tutulur.\n"
            "Tampon dolduğunda yeni gelen bayt düşürülür ve taşma sayacı artırılır.\n"
            "Tamponun 1024 bayta çıkarılması önerisi değerlendiriliyor; henüz karar verilmedi.\n"
        ),
    },
    {
        "key": "initbus",
        "title": "INIT_BUS başlatma sırası — prosedür",
        "kind": "document",
        "scope": S_ZCU,
        "text": (
            "Başlatma prosedürü (kurgusal)\n\n"
            "INIT_BUS çağrısı saat ayarından önce yapılır.\n"
            "INIT_BUS tamamlanmadan çevre birimi kayıtlarına yazılmaz.\n"
            "INIT_BUS başarısız olursa kart güvenli moda geçer.\n"
        ),
    },
    {
        "key": "uart_old",
        "title": "UART hız ölçümü — eski test kaydı",
        "kind": "test",
        "scope": S_VPK,
        "text": (
            "Test kaydı TR-118 (kurgusal)\n\n"
            "VPK120 kartında hata ayıklama UART'ı 115200 baud ile çalışır.\n"
        ),
    },
    {
        "key": "uart_new",
        "title": "UART hız ölçümü — saha notu",
        "kind": "note",
        "scope": S_VPK,
        "text": (
            "Saha notu (kurgusal)\n\n"
            "VPK120 kartında hata ayıklama UART'ı 921600 baud ile çalışır.\n"
        ),
    },
    {
        "key": "wdt",
        "title": "Watchdog besleme aralığı kararı",
        "kind": "note",
        "scope": S_FPGA,
        "text": (
            "Tasarım kararı DK-07 (kurgusal)\n\n"
            "Watchdog zaman aşımı 2 saniye olarak seçildi.\n"
            "Watchdog ana döngüde 500 ms aralıkla beslenir.\n"
            "Besleme ISR içinden yapılmaz; ana döngünün takıldığı fark edilemez.\n"
        ),
    },
]

PAGES = [
    {
        "title": "AXI PCIe kesme yönetimi",
        "kind": "component",
        "note": "pcie_irq",
        "scope": S_VPK,
        "summary": "VPK120 üzerindeki AXI PCIe köprüsünde MSI kesmelerinin nasıl etkinleştirildiği ve maskelendiği.",
        "aliases": ["PCIe interrupt", "MSI"],
        "claims": [
            "VPK120 kartında AXI PCIe köprüsü MSI kesmelerini XAxiPcie_IntrEnable() çağrısı ile etkinleştirir.",
            "Kesme maskesi XPAR_XAXIPCIE_0_BASEADDR + 0x13C adresindeki IMR kaydında tutulur.",
            "Kesme işleyicisi (ISR) içinde yalnız durum bitleri temizlenir; uzun işler görev bağlamına ertelenir.",
        ],
        "body": (
            "Köprü, MSI kesmelerini `XAxiPcie_IntrEnable()` çağrısı ile etkinleştirir. "
            "VPK120 kartında AXI PCIe köprüsü MSI kesmelerini XAxiPcie_IntrEnable() çağrısı ile etkinleştirir.\n\n"
            "Maske, `XPAR_XAXIPCIE_0_BASEADDR` tabanına göre `0x13C` ofsetindeki IMR kaydında tutulur. "
            "Kesme maskesi XPAR_XAXIPCIE_0_BASEADDR + 0x13C adresindeki IMR kaydında tutulur.\n\n"
            "Kesme işleyicisi (ISR) içinde yalnız durum bitleri temizlenir; uzun işler görev bağlamına ertelenir.\n\n"
            "Bu bileşen için DMA tarafındaki kuyruk derinliği henüz belgelenmedi."
        ),
        "unknowns": ["DMA kuyruk derinliği belgelenmedi."],
    },
    {
        "title": "PCIe link eğitimi Gen1'de kalıyor",
        "kind": "incident",
        "note": "pcie_link",
        "scope": S_VPK,
        "summary": "Link eğitiminin Gen1 hızında tamamlanmasının olası nedenleri ve kontrol sırası.",
        "aliases": ["link training", "LTSSM"],
        "claims": [
            "Link eğitimi Gen1 hızında kalırsa önce referans saatin 100 MHz olduğu doğrulanır.",
            "LTSSM durumu Recovery.Speed adımında takılıyorsa eşitleme (equalization) ayarları kontrol edilir.",
            "Saat düzeltildikten sonra link Gen3 x4 olarak eğitildi.",
        ],
        "body": "",
        "unknowns": ["ZCU102 kartında aynı belirtinin görülüp görülmediği bilinmiyor."],
    },
    {
        "title": "SPI saat bölücü ayarı",
        "kind": "procedure",
        "note": "spi",
        "scope": S_ZCU,
        "summary": "ZCU102 SPI denetleyicisinde SCLK frekansının bölücü ile ayarlanması.",
        "aliases": [],
        "claims": [
            "SPI denetleyicisi 100 MHz referans saatini 8 bölücü ile 12.5 MHz SCLK'ye indirir.",
            "Bölücü değeri INIT_BUS çağrısından sonra yazılır.",
        ],
        "body": "",
        "unknowns": [],
    },
    {
        "title": "UART halka tamponu",
        "kind": "concept",
        "note": "uart",
        "scope": S_GEN,
        "summary": "UART alım yolundaki kilitsiz halka tamponun çalışma ilkesi ve taşma davranışı.",
        "aliases": ["ring buffer"],
        "claims": [
            "Halka tampon tek üretici ve tek tüketici ile çalışır; kilit kullanılmaz.",
            "Tampon boyutu 512 bayttır ve 2'nin kuvveti olarak tutulur.",
            "Tampon dolduğunda yeni gelen bayt düşürülür ve taşma sayacı artırılır.",
        ],
        "body": "",
        "unknowns": ["Tamponun 1024 bayta çıkarılması önerisi değerlendiriliyor; henüz karar verilmedi."],
    },
    {
        "title": "INIT_BUS başlatma sırası",
        "kind": "procedure",
        "note": "initbus",
        "scope": S_ZCU,
        "summary": "Kart açılışında veri yolunun başlatılma sırası ve hata davranışı.",
        "aliases": [],
        "claims": [
            "INIT_BUS çağrısı saat ayarından önce yapılır.",
            "INIT_BUS tamamlanmadan çevre birimi kayıtlarına yazılmaz.",
            "INIT_BUS başarısız olursa kart güvenli moda geçer.",
        ],
        "body": "",
        "unknowns": [],
    },
    {
        "title": "Watchdog besleme aralığı",
        "kind": "decision",
        "note": "wdt",
        "scope": S_FPGA,
        "summary": "Watchdog zaman aşımı ve besleme aralığı için alınan tasarım kararı.",
        "aliases": [],
        "claims": [
            "Watchdog zaman aşımı 2 saniye olarak seçildi.",
            "Watchdog ana döngüde 500 ms aralıkla beslenir.",
            "Besleme ISR içinden yapılmaz; ana döngünün takıldığı fark edilemez.",
        ],
        "body": "",
        "unknowns": [],
    },
]

EXTRA_PAGES = [
    {
        "title": "Hata ayıklama UART hızı",
        "kind": "validation",
        "note": "uart_old",
        "scope": S_VPK,
        "summary": "VPK120 hata ayıklama konsolunun baud hızı (test kaydına göre).",
        "aliases": [],
        "claims": ["VPK120 kartında hata ayıklama UART'ı 115200 baud ile çalışır."],
        "body": "",
        "unknowns": [],
    },
    {
        "title": "Konsol baud hızı (saha)",
        "kind": "concept",
        "note": "uart_new",
        "scope": S_VPK,
        "summary": "Sahada ölçülen hata ayıklama konsolu hızı.",
        "aliases": [],
        "claims": ["VPK120 kartında hata ayıklama UART'ı 921600 baud ile çalışır."],
        "body": "",
        "unknowns": [],
    },
]

RELATIONS = [
    (1, "depends_on", 0, "Link sorunu incelemesi kesme yapılandırmasını varsayar."),
    (4, "prerequisite_for", 2, "Bölücü yazımı başlatma sırasından sonra gelir."),
    (5, "explains", 0, "Watchdog kararı ISR içinde uzun iş yapılmaması ilkesini açıklar."),
]


def _board_png() -> bytes:
    """Kurgusal kartın üstten şematik görünümü (PNG, harici dosya ya da kütüphane olmadan üretilir)."""
    import struct
    import zlib

    w, h = 640, 360
    shapes = [  # (x0, y0, x1, y1, renk) — sonra çizilen üstte
        (0, 0, w, h, (238, 242, 241)),
        (60, 40, 580, 320, (31, 95, 74)),  # kart
        (250, 120, 390, 260, (43, 43, 43)),  # FPGA/SoC
        (440, 80, 540, 140, (60, 60, 60)),  # bellek
        (440, 200, 540, 260, (60, 60, 60)),
        (30, 150, 95, 210, (194, 65, 12)),  # hata ayıklama konnektörü (sol kenar)
        (110, 172, 250, 188, (214, 226, 222)),  # UART hattı
    ]
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            color = next(c for x0, y0, x1, y1, c in reversed(shapes) if x0 <= x < x1 and y0 <= y < y1)
            rows.extend(color)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


def _publish(db, user: User, change) -> None:  # noqa: ANN001
    """"Yazar yayımlar": yayın öncesi kural kontrolü + yazarın kendi yayını. Kontrolün bulduğu çelişki bilerek geçilir ve
    Bilgi sağlığına düşer (gerçek akıştaki "Yine de yayımla"). Model tohumlamadan sonra eklenir; kontrol "model yok" der."""
    from metis.modules.changes.prepublish import rule_check

    rule_check(db, user, change)
    changes.publish_direct(db, user, change.id, cs.PublishDirectIn(hash=change.hash, acknowledge_issues=True))
    db.flush()


def _user(db, username: str, display: str, admin: bool = False) -> User:  # noqa: ANN001
    user = db.scalar(select(User).where(func.lower(User.username) == username))
    if not user:
        user = User(username=username, display_name=display, password_hash=hash_password(DEMO_PASSWORD), is_admin=admin)
        db.add(user)
        db.flush()
    return user


def create_demo_workspace(admin_username: str = "") -> dict:
    if not get_settings().is_dev:
        raise AppError("FORBIDDEN", "demo workspace is only available in the development profile")
    with transaction() as db:
        existing = db.scalar(select(Project).where(Project.is_demo.is_(True), Project.deleted_at.is_(None)))
        if existing:
            return {"project_id": str(existing.id), "created": False}
        admin = db.scalar(select(User).where(func.lower(User.username) == admin_username.lower())) if admin_username else None
        if admin is None:
            admin = db.scalar(select(User).where(User.is_admin.is_(True), User.kind == "human").order_by(User.created_at))
        if admin is None:
            admin = _user(db, "ayse", "Ayşe Yılmaz", admin=True)
        ensure_worker_identity(db)
        reviewer = _user(db, "baris", "Barış Demir")
        author = _user(db, "deniz", "Deniz Kaya")
        reader = _user(db, "ece", "Ece Arslan")
        project = Project(
            name="Kurgusal çalışma alanı",
            description="Geliştirme ve tanıtım için kurgusal gömülü yazılım bilgisi. Gerçek veri değildir.",
            is_demo=True,
        )
        db.add(project)
        db.flush()
        roles = {admin: ["steward", "reviewer", "contributor", "reader"], reviewer: ["reviewer", "contributor"], author: ["contributor"], reader: ["reader"]}
        for u, rs in roles.items():
            for r in rs:
                db.add(ProjectMember(project_id=project.id, user_id=u.id, role=r))
        for dim, values in SCOPES.items():
            for v in values:
                db.add(ScopeValue(project_id=project.id, dimension=dim, value=v, created_by=admin.id))
        ensure_default_schedule(db, project.id)
        db.flush()

        revs = {}
        for note in NOTES:
            content = sources.prepare_content(note["kind"], note["text"], None)
            meta = ss.SourceMetaIn(title=note["title"], kind=note["kind"], text=note["text"], scope=note["scope"])
            _, rev = sources.create_source(db, author, project.id, meta, content)
            revs[note["key"]] = rev
        db.flush()

        # Açıklayıcı görsel: kurgusal kartın üstten görünümü (görsel kaynak; kanıt değildir).
        board = sources.prepare_content("image", "Kurgusal kartın üstten şematik görünümü.", ("kurgusal-kart.png", _board_png()))
        _, board_rev = sources.create_source(db, author, project.id, ss.SourceMetaIn(title="Kurgusal kart — üstten görünüm", kind="image", text="Kurgusal kartın üstten şematik görünümü.", scope=S_VPK), board)
        figures = {"Hata ayıklama UART hızı": cs.FigureIn(source_revision_id=board_rev.id, caption="Kurgusal kart: hata ayıklama konnektörü sol kenarda (turuncu); açık renkli UART hattı işlemciye gider.")}

        # Yazar yayımlar: bilgiler yazarınca yayımlanır; saha notunu Barış yayımlar ve kontrolün bulduğu çelişkiyi
        # bilerek geçer (Bilgi sağlığına düşer).
        page_ids: list[uuid.UUID] = []
        items: list[cs.ItemIn] = []
        for spec in PAGES + EXTRA_PAGES:
            rev = revs[spec["note"]]
            publisher = reviewer if spec["note"] == "uart_new" else author
            claims = []
            for statement in spec["claims"]:
                ev = sources.create_evidence(db, author, rev.id, ss.EvidenceCreateIn(excerpt=statement))
                claims.append(cs.ClaimIn(statement=statement, kind="expert_statement", evidence=[cs.EvidenceRef(evidence_id=ev.id, quote=statement)]))
            body = spec["body"] or "\n\n".join(spec["claims"])
            fig = figures.get(spec["title"])
            item = cs.ItemIn(
                title=spec["title"],
                summary=spec["summary"],
                body_md=f"{body}\n\n{{{{görsel 1}}}}" if fig else body,
                kind=spec["kind"],
                scope=spec["scope"],
                unknowns=spec["unknowns"],
                aliases=spec["aliases"],
                claims=claims,
                figures=[fig] if fig else [],
            )
            change = changes.create_change(db, publisher, project.id, cs.ChangeCreateIn(summary=spec["title"], items=[item]))
            db.flush()
            _publish(db, publisher, change)
            page_ids.append(changes._items(db, change)[0].page_id)
            items.append(item)

        rels = [cs.RelationIn(subject_page_id=page_ids[a], predicate=p, object_page_id=page_ids[b], rationale=why) for a, p, b, why in RELATIONS]
        rel_change = changes.create_change(db, author, project.id, cs.ChangeCreateIn(summary="Kavram ilişkileri", relations=rels))
        db.flush()
        _publish(db, author, rel_change)

        from metis.core.models import Page

        # Başkasının bilgisini güncelleme: Barış, Deniz'in SPI sayfasına bir ad ekler → Deniz'in ana sayfasında
        # "Bilgilerin güncellendi".
        spi = db.get(Page, page_ids[2])
        update = items[2].model_copy(update={"page_id": spi.id, "base_revision_id": spi.published_revision_id, "aliases": ["SCLK bölücü"]})
        upd = changes.create_change(db, reviewer, project.id, cs.ChangeCreateIn(summary="SPI sayfasına arama adı eklendi", items=[update]))
        db.flush()
        _publish(db, reviewer, upd)

        # Yarım kalmış bir taslak (Deniz'in "Kaldığın yerden" listesinde; "Yayımla" ile yayımlanır)
        uart = revs["uart"]
        statement = "Tamponun 1024 bayta çıkarılması önerisi değerlendiriliyor; henüz karar verilmedi."
        ev = sources.create_evidence(db, author, uart.id, ss.EvidenceCreateIn(excerpt="Tampon boyutu 512 bayttır ve 2'nin kuvveti olarak tutulur."))
        ev2 = sources.create_evidence(db, author, uart.id, ss.EvidenceCreateIn(excerpt=statement))
        page = db.get(Page, page_ids[3])
        pending = cs.ItemIn(
            page_id=page.id,
            base_revision_id=page.published_revision_id,
            title="UART halka tamponu",
            summary="UART alım yolundaki kilitsiz halka tamponun çalışma ilkesi, taşma davranışı ve açık karar.",
            body_md="Tampon boyutu 512 bayttır ve 2'nin kuvveti olarak tutulur.\n\n" + statement,
            kind="concept",
            scope=S_GEN,
            unknowns=[],
            aliases=["ring buffer"],
            claims=[
                cs.ClaimIn(statement="Tampon boyutu 512 bayttır ve 2'nin kuvveti olarak tutulur.", evidence=[cs.EvidenceRef(evidence_id=ev.id, quote="Tampon boyutu 512 bayttır ve 2'nin kuvveti olarak tutulur.")]),
                cs.ClaimIn(statement=statement, kind="hypothesis", support="partial", evidence=[cs.EvidenceRef(evidence_id=ev2.id, quote=statement)]),
            ],
        )
        changes.create_change(db, author, project.id, cs.ChangeCreateIn(summary="Tampon boyutu açık kararı eklendi", items=[pending]))
        from metis.modules.health.maintenance import (
            _open_finding,
            conflict_fingerprint,
            conflict_pairs,
            deterministic_scan,
        )

        deterministic_scan(db, project.id, admin.id)
        # Yayında bilerek geçilen çelişki zaten bulgu; aynı parmak iziyle ikinci kez açılmaz.
        for pair in conflict_pairs(db, project.id):
            a, b = pair["a"], pair["b"]
            sides = [{"page_id": str(x["page_id"]), "page_title": x["title"], "quote": x["statement"], "evidence_id": str(x["evidence_id"])} for x in (a, b)]
            _open_finding(db, project.id, "conflict", conflict_fingerprint(a, b), [a["page_id"], b["page_id"]], "high", {"sides": sides, "detected_by": "rule"}, admin.id)
        project_id, admin_id = project.id, admin.id
        admin_username = admin.username
    model_note = _setup_fixture_model(admin_id)
    return {
        "project_id": str(project_id),
        "created": True,
        "users": {"admin": admin_username, "reviewer": "baris", "contributor": "deniz", "reader": "ece"},
        "demo_password_note": "Kurgusal kullanıcıların parolası seed dosyasındadır (yalnız geliştirme).",
        "fixture_model": model_note,
    }


def _setup_fixture_model(admin_id: uuid.UUID) -> str:
    """Kurgusal model sunucusu (127.0.0.1:9100) çalışıyorsa sağlayıcıyı ekle, probe et, ortak benchmark'ı çalıştır."""
    import socket

    from metis.core.models import Model, Provider
    from metis.modules.lab import service as lab

    url = "http://127.0.0.1:9100/v1"
    if url not in get_settings().endpoint_allowlist:
        return "atlandı: allowlist"
    try:
        with socket.create_connection(("127.0.0.1", 9100), timeout=1):
            pass
    except OSError:
        return "atlandı: kurgusal model sunucusu çalışmıyor (metis mock-llm)"
    with transaction() as db:
        existing = db.scalar(select(Provider).where(Provider.base_url == url, Provider.deleted_at.is_(None)))
        admin = db.get(User, admin_id)
        if existing is None:
            existing = lab.create_provider(db, admin, "Kurgusal model sunucusu", url, "", ["fixture-reference"], 2, 30)
        model = db.scalar(select(Model).where(Model.provider_id == existing.id, Model.remote_id == "fixture-reference"))
        model.display_name = "Kurgusal referans model"
        model_id = model.id
    lab.probe(model_id, admin_id)
    with transaction() as db:
        run = lab.start_benchmark(db, db.get(User, admin_id), model_id)
        run_id = run.id
    metrics = lab.execute_benchmark(run_id)
    return f"hazır: benchmark {metrics['passed']}/{metrics['n']}"
