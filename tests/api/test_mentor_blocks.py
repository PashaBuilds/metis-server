"""Mentor ve bloklar (İş 2): uzun sayfanın ilgili blokları pakete girer; model yokken ilgili yayımlanmış bölümler."""

from __future__ import annotations

from metis.modules.mentor.service import select_blocks
from tests.retrieval_kit import publish_corpus


def _rows(n: int, headings: dict[int, str]) -> list[dict]:
    return [{"claim_id": f"c{i}", "ord": i, "statement": headings.get(i, f"paragraf {i}")} for i in range(n)]


def test_select_blocks_keeps_neighbours_and_heading():
    rows = _rows(20, {0: "## A", 10: "## B"})
    assert [r["ord"] for r in select_blocks(rows, ["c14"])] == [10, 13, 14, 15]
    assert [r["ord"] for r in select_blocks(rows, ["c3", "c14"])] == [0, 2, 3, 4, 10, 13, 14, 15]
    assert [r["ord"] for r in select_blocks(rows, [])] == list(range(8))  # blok sıralaması yoksa ilk 8
    short = _rows(6, {})
    assert select_blocks(short, ["c5"]) == short  # kısa sayfa olduğu gibi


def test_model_unavailable_returns_related_passages(team):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    pages = publish_corpus(team["contributor"], pid)
    r = team["reader"].post(f"/api/v1/projects/{pid}/mentor/answers", json={"question": "PERST# ne kadar süre tutulur?"})
    assert r.status_code == 200, r.text
    ans = r.json()
    assert ans["decision"] == "MODEL_UNAVAILABLE" and ans["citations"] == [] and ans["explanation"] == []
    passages = ans["related_passages"]
    assert 1 <= len(passages) <= 5
    first = passages[0]
    assert first["page_id"] == pages["pcie-bringup"] and first["heading_path"] == "Saat ve sıfırlama" and "PERST#" in first["text"]
    again = team["reader"].get(f"/api/v1/answers/{ans['id']}").json()
    assert again["related_passages"] == passages


def test_allocate_gives_every_page_its_best_block():
    from metis.modules.mentor.service import MAX_BUNDLE, allocate

    pages = []
    for p in range(3):
        rows = [{"claim_id": f"p{p}c{i}", "ord": i, "statement": "## B" if i % 5 == 0 else f"p{p} paragraf {i}", "page_id": str(p)} for i in range(30)]
        pages.append((rows, [f"p{p}c{i}" for i in (3, 8, 13, 18, 23, 28)]))
    out = allocate(pages)
    assert sum(len(x) for x in out) <= MAX_BUNDLE
    for p, chosen in enumerate(out):
        assert f"p{p}c3" in {r["claim_id"] for r in chosen}, p  # her sayfanın en iyi bloğu pakette
        assert [r["ord"] for r in chosen] == sorted(r["ord"] for r in chosen)


def test_unreadable_page_passage_hidden(team):  # noqa: ANN001
    import uuid

    from metis.core.db import transaction
    from metis.core.models import Page, SourceAcl

    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    pages = publish_corpus(team["contributor"], pid)
    ans = team["reader"].post(f"/api/v1/projects/{pid}/mentor/answers", json={"question": "PERST# ne kadar süre tutulur?"}).json()
    assert any(p["page_id"] == pages["pcie-bringup"] for p in ans["related_passages"])
    with transaction() as db:  # kaynak yalnız yöneticiye açılır: okur o sayfayı göremez
        page = db.get(Page, uuid.UUID(pages["pcie-bringup"]))
        db.add(SourceAcl(source_id=page.note_source_id, user_id=uuid.UUID(team["admin"].user["id"])))
    again = team["reader"].get(f"/api/v1/answers/{ans['id']}").json()
    assert all(p["page_id"] != pages["pcie-bringup"] for p in again["related_passages"])
