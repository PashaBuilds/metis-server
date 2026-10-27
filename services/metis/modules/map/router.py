"""Kavram haritası: yalnız aktif yayındaki, erişilebilir sayfalar ve ilişkiler. Erişilemeyen düğüm/kenar hiç dönmez."""

from __future__ import annotations

import uuid
from collections import deque

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import require_member, unreadable_revisions
from metis.core.deps import current_user, get_db
from metis.core.errors import AppError
from metis.core.models import ActivePage, ActiveRelation, Page, PageRevision, Project, RelationRevision, User
from metis.modules.scopes.semantics import matches_scope

router = APIRouter(tags=["map"])

MAX_NODES = 500


class MapNode(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    scope: dict
    freshness: str
    summary: str
    degree: int


class MapEdge(BaseModel):
    id: uuid.UUID
    source: uuid.UUID
    target: uuid.UUID
    predicate: str
    rationale: str


class MapOut(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]
    focus: uuid.UUID | None
    truncated: bool
    total_nodes: int


def build_map(
    db: Session, user: User, project_id: uuid.UUID, focus: uuid.UUID | None, depth: int, predicates: list[str], scope: dict
) -> MapOut:
    require_member(db, user, project_id)
    project = db.get(Project, project_id)
    if not project or not project.active_publication_id:
        return MapOut(nodes=[], edges=[], focus=None, truncated=False, total_nodes=0)
    rows = db.execute(
        select(Page, PageRevision)
        .join(ActivePage, ActivePage.page_id == Page.id)
        .join(PageRevision, PageRevision.id == ActivePage.revision_id)
        .where(ActivePage.project_id == project.id, Page.deleted_at.is_(None), Page.lifecycle == "active")
    ).all()
    hidden = unreadable_revisions(db, user, project_id, [r.id for _, r in rows])
    pages = {p.id: (p, r) for p, r in rows if r.id not in hidden and matches_scope(r.scope, scope)}
    edges = []
    for rr, rel_id in db.execute(
        select(RelationRevision, ActiveRelation.relation_id)
        .join(ActiveRelation, ActiveRelation.revision_id == RelationRevision.id)
        .where(ActiveRelation.project_id == project.id)
    ):
        if rr.subject_page_id in pages and rr.object_page_id in pages and (not predicates or rr.predicate in predicates):
            edges.append(MapEdge(id=rel_id, source=rr.subject_page_id, target=rr.object_page_id, predicate=rr.predicate, rationale=rr.rationale))
    degree: dict[uuid.UUID, int] = {pid: 0 for pid in pages}
    adj: dict[uuid.UUID, set[uuid.UUID]] = {pid: set() for pid in pages}
    for e in edges:
        degree[e.source] += 1
        degree[e.target] += 1
        adj[e.source].add(e.target)
        adj[e.target].add(e.source)
    keep = set(pages)
    if focus is not None:
        if focus not in pages:
            raise AppError("NOT_FOUND", "page not found")
        keep, queue = {focus}, deque([(focus, 0)])
        while queue:
            node, d = queue.popleft()
            if d >= depth:
                continue
            for nb in adj[node]:
                if nb not in keep:
                    keep.add(nb)
                    queue.append((nb, d + 1))
    ordered = sorted(keep, key=lambda pid: (-degree[pid], pages[pid][1].title))
    truncated = len(ordered) > MAX_NODES
    keep = set(ordered[:MAX_NODES])
    nodes = [
        MapNode(id=pid, title=pages[pid][1].title, kind=pages[pid][1].kind, scope=pages[pid][1].scope, freshness=pages[pid][0].freshness, summary=pages[pid][1].summary[:300], degree=degree[pid])
        for pid in ordered[:MAX_NODES]
    ]
    return MapOut(nodes=nodes, edges=[e for e in edges if e.source in keep and e.target in keep], focus=focus, truncated=truncated, total_nodes=len(pages))


@router.get("/projects/{project_id}/map", response_model=MapOut)
def get_map(
    project_id: uuid.UUID,
    focus: uuid.UUID | None = None,
    depth: int = Query(default=2, ge=1, le=3),
    predicate: list[str] = Query(default=[]),
    domain: list[str] = Query(default=[]),
    yatt: list[str] = Query(default=[]),
    kart: list[str] = Query(default=[]),
    proje: list[str] = Query(default=[]),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> MapOut:
    return build_map(db, user, project_id, focus, depth, predicate, {"domain": domain, "yatt": yatt, "kart": kart, "proje": proje})
