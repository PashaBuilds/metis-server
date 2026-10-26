"""Ölçek denemesinde (evals/scale) bulunan büyüme sorunlarına karşı korumalar.

Bakım taramasının çelişki adayı üretimi büyük derlemde de bitmeli (ölçek denemesi: 300 sayfada 58 sn, karesel).

Aday kuralı değişmez: aynı biçimli (sayılar #) fakat farklı metinli iddialar, farklı sayfalarda; sayfa çifti + biçim
başına bir aday; sıra eski iç içe döngüyle aynı (bakım ilk N adayı değerlendirir).
"""

from __future__ import annotations

import time
import uuid

from metis.modules.changes.prepublish import rule_candidates
from metis.modules.health.maintenance import pair_candidates


def _row(page: int, statement: str) -> tuple:
    return (uuid.UUID(int=page), f"Sayfa {page}", {}, statement, uuid.UUID(int=10_000 + page))


def test_pairs_follow_the_rule_and_order():
    rows = [
        _row(1, "Saat 100 MHz."),
        _row(2, "Saat 125 MHz."),
        _row(3, "Saat 100 MHz."),  # 1 ile aynı metin: aday değil; 2 ile aday
        _row(2, "Saat 133 MHz."),  # 1-2 çifti bu biçimde zaten var
        _row(1, "Saat 150 MHz."),  # aynı sayfa (1) ile değil; 2 ve 3 ile
        _row(4, "Başka bir cümle 5."),
    ]
    got = [(p["a"]["page_id"].int, p["b"]["page_id"].int, p["a"]["statement"], p["b"]["statement"]) for p in pair_candidates(rows)]
    assert got == [
        (1, 2, "Saat 100 MHz.", "Saat 125 MHz."),
        (2, 3, "Saat 125 MHz.", "Saat 100 MHz."),
        (3, 1, "Saat 100 MHz.", "Saat 150 MHz."),
    ]


def test_pairs_scale_linearly():
    def word(i: int) -> str:  # sayısız, her satıra ayrı biçim
        return "".join(chr(97 + int(d)) for d in str(i))

    rows = [_row(i, f"{word(i)} yazmacı kurulumda {i % 7} ms bekler") for i in range(30_000)]
    rows += [_row(1, "Saat 100 MHz."), _row(2, "Saat 125 MHz.")]
    t = time.perf_counter()
    pairs = pair_candidates(rows)
    assert time.perf_counter() - t < 5  # iç içe döngüyle 4,5 · 10^8 karşılaştırma (dakikalar)
    assert [(p["a"]["page_id"].int, p["b"]["page_id"].int) for p in pairs] == [(1, 2)]


def test_prepublish_rule_candidates_index_by_shape():
    """Yayın öncesi kural kontrolü: taslak iddiası başına tüm yayını taramaz; kural ve sıra aynı."""
    scope = {"kart": ["K7"]}
    rows = [(uuid.UUID(int=i), uuid.UUID(int=50_000 + i), f"Sayfa {i}", scope, f"Yazmaç {i} hazır.") for i in range(60_000)]
    rows += [
        (uuid.UUID(int=1), uuid.UUID(int=90_001), "Saat notu", scope, "Saat 125 MHz."),
        (uuid.UUID(int=2), uuid.UUID(int=90_002), "Gizli not", scope, "Saat 150 MHz."),
        (uuid.UUID(int=3), uuid.UUID(int=90_003), "Başka kart", {"kart": ["Z9"]}, "Saat 133 MHz."),
        (uuid.UUID(int=4), uuid.UUID(int=90_004), "Aynı metin", scope, "Saat 100 MHz."),
    ]
    drafts = [{"title": "Taslak", "scope": scope, "claims": ["Saat 100 MHz.", "Yeni bir cümle."] * 60}]
    t = time.perf_counter()
    rule = rule_candidates(drafts, rows, hidden={uuid.UUID(int=90_002)})
    assert time.perf_counter() - t < 5  # iddia başına 40 bin satır taramak: 120 iddiada 7 milyon karşılaştırma
    assert [(r["page_title"], r["theirs"]) for r in rule] == [("Saat notu", "Saat 125 MHz.")]


def test_publication_manifest_is_indexed_by_revision(db):  # noqa: ANN001
    """"Bu revizyon hiç yayımlandı mı" sorusu (yetki denetimi, geçmiş) her yayında yüzlerce kez sorulur; manifest her
    yayında tüm sayfaları taşır (20 bin sayfalık içe aktarmada on milyonlarca satır): dizinsiz tam tarama olur."""
    from sqlalchemy import text

    defs = db.scalars(text("SELECT indexdef FROM pg_indexes WHERE tablename = 'publication_pages'")).all()
    assert any("(revision_id)" in d for d in defs), defs
