"""Harita performans testi için kurgusal büyük graf (yalnız geliştirme profili).

Ayrı bir kurgusal proje oluşturur; tüm sayfalar normal katkı → inceleme → yayın akışından geçer.
"""

from __future__ import annotations

import random

from sqlalchemy import func, select

from metis.core.config import get_settings
from metis.core.db import transaction
from metis.core.errors import AppError
from metis.core.models import Project, ProjectMember, ScopeValue, User
from metis.modules.changes import schemas as cs
from metis.modules.changes import service as changes
from metis.modules.scopes.service import ensure_default_schedule
from metis.modules.sources import schemas as ss
from metis.modules.sources import service as sources

KINDS = ["concept", "component", "procedure", "decision", "incident", "validation"]
PREDICATES = ["depends_on", "implements", "verified_by", "prerequisite_for", "explains", "part_of"]
SUBSYSTEMS = ["UART", "SPI", "I2C", "DMA", "PCIe", "Ethernet", "Watchdog", "Bootloader", "Saat ağacı", "Kesme denetleyicisi"]


def create_graph_workspace(nodes: int = 200, edges_per_node: float = 1.5, seed: int = 7) -> dict:
    if not get_settings().is_dev:
        raise AppError("FORBIDDEN", "only in development profile")
    rng = random.Random(seed)
    with transaction() as db:
        admin = db.scalar(select(User).where(User.is_admin.is_(True), User.kind == "human").order_by(User.created_at))
        reviewer = db.scalar(select(User).where(func.lower(User.username) == "baris"))
        if admin is None or reviewer is None:
            raise AppError("INVALID_STATE", "run `metis demo` first")
        project = Project(name=f"Kurgusal harita testi ({nodes} düğüm)", description="Harita performans ölçümü için kurgusal graf.", is_demo=True)
        db.add(project)
        db.flush()
        for u, roles in ((admin, ["steward", "reviewer", "contributor", "reader"]), (reviewer, ["reviewer", "contributor"])):
            for r in roles:
                db.add(ProjectMember(project_id=project.id, user_id=u.id, role=r))
        db.add(ScopeValue(project_id=project.id, dimension="domain", value="Gömülü yazılım"))
        ensure_default_schedule(db, project.id)
        db.flush()
        scope = {"domain": ["Gömülü yazılım"], "yatt": [], "kart": [], "proje": []}
        lines = [f"{SUBSYSTEMS[i % len(SUBSYSTEMS)]} bileşeni {i:03d} için kurgusal ayar {rng.randint(1, 999)} değerindedir." for i in range(nodes)]
        content = sources.prepare_content("note", "\n".join(lines), None)
        _, rev = sources.create_source(db, admin, project.id, ss.SourceMetaIn(title="Kurgusal graf kaynağı", kind="note", text="\n".join(lines), scope=scope), content)
        page_ids = []
        for start in range(0, nodes, 5):
            items = []
            for i in range(start, min(nodes, start + 5)):
                ev = sources.create_evidence(db, admin, rev.id, ss.EvidenceCreateIn(excerpt=lines[i]))
                items.append(cs.ItemIn(title=f"{SUBSYSTEMS[i % len(SUBSYSTEMS)]} {i:03d}", summary=lines[i], body_md=lines[i], kind=rng.choice(KINDS), scope=scope, claims=[cs.ClaimIn(statement=lines[i], evidence=[cs.EvidenceRef(evidence_id=ev.id, quote=lines[i])])]))  # type: ignore[arg-type]
            ch = changes.create_change(db, admin, project.id, cs.ChangeCreateIn(summary="graf", items=items, submit=True))
            db.flush()
            changes.review(db, reviewer, ch.id, cs.ReviewIn(decision="approve", reason="kurgusal", evidence_checked=True, hash=ch.hash))
            changes.publish_change(db, reviewer, ch.id)
            page_ids.extend(i.page_id for i in changes._items(db, ch))
        rels = set()
        target = int(nodes * edges_per_node)
        while len(rels) < target:
            a = rng.randrange(nodes)
            b = (a + rng.randint(1, 12)) % nodes if rng.random() < 0.8 else rng.randrange(nodes)
            if a != b:
                rels.add((a, b, rng.choice(PREDICATES)))
        rel_list = sorted(rels)
        for start in range(0, len(rel_list), 20):
            batch = [cs.RelationIn(subject_page_id=page_ids[a], predicate=p, object_page_id=page_ids[b], rationale="kurgusal") for a, b, p in rel_list[start : start + 20]]  # type: ignore[arg-type]
            ch = changes.create_change(db, admin, project.id, cs.ChangeCreateIn(summary="graf ilişkileri", relations=batch, submit=True))
            db.flush()
            changes.review(db, reviewer, ch.id, cs.ReviewIn(decision="approve", reason="kurgusal", evidence_checked=True, hash=ch.hash))
            changes.publish_change(db, reviewer, ch.id)
        return {"project_id": str(project.id), "nodes": len(page_ids), "edges": len(rel_list)}
