"""Yayın listesi yalnız değişenleri yazar (ürün sahibinin kararı 2026-10-27).

Her yayın yalnız o yayında değişen sayfaları/ilişkileri kaydeder (çıkarılan = revizyonsuz satır); şu an yayında olan
liste ayrı tabloda tutulur; herhangi bir yayının tam listesi değişikliklerden kurulur (eskiden her yayında saklanan
tam listeyle aynı). 20 bin sayfalık kurgusal derlemde tam liste 40 milyon satır / 6,1 GB etmişti.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from sqlalchemy import select, text

import metis
from metis.core.db import transaction
from metis.core.models import ActivePage, ActiveRelation, Project, Publication, PublicationPage, PublicationRelation
from metis.modules.knowledge.publish import manifest_at
from tests.kb import approve, draft, evidence, publish, publish_note, submit

UART = "UART modulu 115200 baud ile calisir."
UART2 = "UART tamponu 512 bayttir."


def _rel(client, pid, a, b):  # noqa: ANN001, ANN202
    r = client.post(f"/api/v1/projects/{pid}/changes", json={"summary": "ilişki", "relations": [{"subject_page_id": a, "predicate": "depends_on", "object_page_id": b, "rationale": "kurgusal"}], "submit": True})
    assert r.status_code == 201, r.text
    return r.json()


def _state(db, pid: uuid.UUID) -> tuple[uuid.UUID, dict, dict]:  # noqa: ANN001
    project = db.get(Project, pid)
    pages = dict(db.execute(select(ActivePage.page_id, ActivePage.revision_id).where(ActivePage.project_id == pid)).all())
    rels = dict(db.execute(select(ActiveRelation.relation_id, ActiveRelation.revision_id).where(ActiveRelation.project_id == pid)).all())
    return project.active_publication_id, pages, rels


def _written(db, pub_id: uuid.UUID) -> tuple[dict, dict]:  # noqa: ANN001
    pages = dict(db.execute(select(PublicationPage.page_id, PublicationPage.revision_id).where(PublicationPage.publication_id == pub_id)).all())
    rels = dict(db.execute(select(PublicationRelation.relation_id, PublicationRelation.revision_id).where(PublicationRelation.publication_id == pub_id)).all())
    return pages, rels


def test_publications_record_only_changes_and_history_is_rebuilt(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    project_id = uuid.UUID(pid)
    snapshots = []

    def snap() -> None:
        with transaction() as db:
            snapshots.append(_state(db, project_id))

    a = publish_note(c, rv, pid, "UART", f"{UART} {UART2}", [UART])
    snap()
    b = publish_note(c, rv, pid, "SPI", "SPI saati 10 MHz secilir.")["page_id"]
    snap()
    publish(rv, approve(rv, _rel(c, pid, a["page_id"], b))["id"])
    snap()
    page = c.get(f"/api/v1/pages/{a['page_id']}").json()
    ev1 = page["revision"]["claims"][0]["evidence"][0]["evidence_id"]
    ev2 = evidence(c, a["source"]["revision"]["id"], UART2)["id"]
    ch = draft(c, pid, "UART", [(UART, ev1), (UART2, ev2)], page_id=a["page_id"], base=page["revision"]["id"])
    publish(rv, approve(rv, submit(c, ch["id"]))["id"])
    snap()
    assert rv.post(f"/api/v1/pages/{b}/withdraw", json={"reason": "Kurgusal geri çekme"}).status_code == 200
    snap()

    with transaction() as db:
        pubs = db.scalars(select(Publication).where(Publication.project_id == project_id).order_by(Publication.seq)).all()
        assert len(pubs) == 5
        a_id, b_id = uuid.UUID(a["page_id"]), uuid.UUID(b)
        written = [_written(db, p.id) for p in pubs]
        # 1–2: yeni sayfa; 3: yalnız ilişki; 4: yalnız güncellenen A; 5: B ve ona bağlı ilişki çıkar (revizyonsuz satır).
        assert [set(w[0]) for w in written] == [{a_id}, {b_id}, set(), {a_id}, {b_id}]
        assert [len(w[1]) for w in written] == [0, 0, 1, 0, 1]
        assert written[4][0][b_id] is None and next(iter(written[4][1].values())) is None
        for pub, (active_id, pages, rels) in zip(pubs, snapshots, strict=True):
            assert pub.id == active_id
            assert manifest_at(db, pub) == (pages, rels)
        assert set(snapshots[-1][1]) == {a_id} and snapshots[-1][2] == {}


def test_reading_active_list_does_not_depend_on_old_publications(team):
    """Bilgi listesi ve harita güncel listeyi okur: eski yayınların satırları silinse de (yalnız testte) sonuç aynı."""
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    a = publish_note(c, rv, pid, "UART", UART)["page_id"]
    b = publish_note(c, rv, pid, "SPI", "SPI saati 10 MHz secilir.")["page_id"]
    publish(rv, approve(rv, _rel(c, pid, a, b))["id"])
    before = (c.get(f"/api/v1/projects/{pid}/pages").json()["total"], len(c.get(f"/api/v1/projects/{pid}/map").json()["edges"]))
    assert before == (2, 1)
    with transaction() as db:
        db.execute(text("ALTER TABLE publication_pages DISABLE TRIGGER USER; ALTER TABLE publication_relations DISABLE TRIGGER USER"))
        db.execute(text("DELETE FROM publication_pages; DELETE FROM publication_relations"))
        db.execute(text("ALTER TABLE publication_pages ENABLE TRIGGER USER; ALTER TABLE publication_relations ENABLE TRIGGER USER"))
    after = (c.get(f"/api/v1/projects/{pid}/pages").json()["total"], len(c.get(f"/api/v1/projects/{pid}/map").json()["edges"]))
    assert after == before


def test_real_migration_downgrade_and_upgrade_keep_history(team):
    """Gerçek Alembic: 0017 geri alınınca her yayın tam listeyi taşır; yeniden yükseltince değişiklikler ve güncel liste aynen."""
    from alembic import command

    from metis.cli import _alembic_config
    from metis.core.config import get_settings

    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    project_id = uuid.UUID(pid)
    a = publish_note(c, rv, pid, "UART", UART)["page_id"]
    b = publish_note(c, rv, pid, "SPI", "SPI saati 10 MHz secilir.")["page_id"]
    publish(rv, approve(rv, _rel(c, pid, a, b))["id"])
    assert rv.post(f"/api/v1/pages/{a}/withdraw", json={"reason": "Kurgusal geri çekme"}).status_code == 200
    all_rows = "SELECT publication_id, page_id, revision_id FROM publication_pages"
    all_rels = "SELECT publication_id, relation_id, revision_id FROM publication_relations"
    with transaction() as db:
        pubs = db.scalars(select(Publication).where(Publication.project_id == project_id).order_by(Publication.seq)).all()
        full = {p.id: manifest_at(db, p) for p in pubs}
        changes = (set(db.execute(text(all_rows)).all()), set(db.execute(text(all_rels)).all()))
        current = _state(db, project_id)[1:]
    cfg = _alembic_config(get_settings().owner_database_url)
    try:
        command.downgrade(cfg, "0016")
        with transaction() as db:
            assert db.scalar(text("SELECT to_regclass('active_pages')")) is None
            for pub_id, (pages, rels) in full.items():
                got = _written(db, pub_id)
                assert got == (pages, rels)
            assert db.scalar(text("SELECT is_nullable FROM information_schema.columns WHERE table_name = 'publication_pages' AND column_name = 'revision_id'")) == "NO"
    finally:
        command.upgrade(cfg, "head")
    with transaction() as db:
        assert (set(db.execute(text(all_rows)).all()), set(db.execute(text(all_rels)).all())) == changes
        assert _state(db, project_id)[1:] == current
        assert db.scalar(text("SELECT has_table_privilege(current_user, 'active_pages', 'INSERT')"))
    assert c.get(f"/api/v1/projects/{pid}/pages").json()["total"] == 1


def _migration():  # noqa: ANN202
    path = Path(metis.__file__).parent / "migrations" / "versions" / "0017_publication_changes.py"
    spec = importlib.util.spec_from_file_location("m0017", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_converts_full_lists_to_changes_and_downgrade_restores_them(db):  # noqa: ANN001
    m = _migration()
    proj, other = uuid.uuid4(), uuid.uuid4()
    p = [uuid.uuid4() for _ in range(4)]
    r = {name: uuid.uuid4() for name in ("a1", "a2", "b1", "c1", "d1")}
    pubs = [(uuid.uuid4(), proj, seq) for seq in (1, 2, 3, 4)] + [(uuid.uuid4(), other, 1)]
    full = {  # eski biçim: her yayın tam liste
        pubs[0][0]: {p[0]: r["a1"], p[1]: r["b1"]},
        pubs[1][0]: {p[0]: r["a2"], p[1]: r["b1"]},
        pubs[2][0]: {p[0]: r["a2"]},
        pubs[3][0]: {p[0]: r["a2"], p[1]: r["b1"], p[2]: r["c1"]},
        pubs[4][0]: {p[3]: r["d1"]},
    }
    db.execute(text("CREATE TEMP TABLE t_pubs (id uuid, project_id uuid, seq int, created_at timestamptz DEFAULT now())"))
    db.execute(text("CREATE TEMP TABLE t_rows (publication_id uuid, page_id uuid, revision_id uuid)"))
    for pub_id, project_id, seq in pubs:
        db.execute(text("INSERT INTO t_pubs (id, project_id, seq) VALUES (:i, :p, :s)"), {"i": pub_id, "p": project_id, "s": seq})
    for pub_id, rows in full.items():
        for page_id, rev_id in rows.items():
            db.execute(text("INSERT INTO t_rows VALUES (:a, :b, :c)"), {"a": pub_id, "b": page_id, "c": rev_id})

    def rows() -> set:
        return set(db.execute(text("SELECT publication_id, page_id, revision_id FROM t_rows")).all())

    for statement in m.to_changes("t_rows", "page_id", "t_pubs"):
        db.execute(text(statement))
    assert rows() == {
        (pubs[0][0], p[0], r["a1"]), (pubs[0][0], p[1], r["b1"]),
        (pubs[1][0], p[0], r["a2"]),
        (pubs[2][0], p[1], None),
        (pubs[3][0], p[1], r["b1"]), (pubs[3][0], p[2], r["c1"]),
        (pubs[4][0], p[3], r["d1"]),
    }
    for statement in m.to_full_lists("t_rows", "page_id", "t_pubs"):
        db.execute(text(statement))
    assert rows() == {(pub_id, page_id, rev_id) for pub_id, rs in full.items() for page_id, rev_id in rs.items()}
