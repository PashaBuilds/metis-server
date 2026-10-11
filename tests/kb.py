"""Bilgi akışı test yardımcıları (kurgusal veri)."""

from __future__ import annotations

import json

DEFAULT_SCOPE = {"domain": ["Gömülü yazılım"], "yatt": [], "kart": ["VPK120"], "proje": []}


def add_note(
    client, project_id: str, title: str, text: str, scope: dict | None = None, acl: list[str] | None = None
) -> dict:  # noqa: ANN001
    meta = {"title": title, "kind": "note", "text": text, "scope": scope or DEFAULT_SCOPE, "acl": acl or []}
    r = client.post(f"/api/v1/projects/{project_id}/sources", files={"meta": (None, json.dumps(meta))})
    assert r.status_code == 201, r.text
    return r.json()


def upload(
    client,
    project_id: str,
    filename: str,
    data: bytes,
    title: str = "Dosya",
    kind: str = "document",
    text: str = "",
    scope: dict | None = None,
):  # noqa: ANN001, ANN201
    meta = {"title": title, "kind": kind, "text": text, "scope": scope or DEFAULT_SCOPE}
    return client.post(
        f"/api/v1/projects/{project_id}/sources", files={"meta": (None, json.dumps(meta)), "file": (filename, data)}
    )


def evidence(client, revision_id: str, excerpt: str) -> dict:  # noqa: ANN001
    r = client.post(f"/api/v1/source-revisions/{revision_id}/evidence", json={"excerpt": excerpt})
    assert r.status_code == 201, r.text
    return r.json()


def draft(
    client,
    project_id: str,
    title: str,
    claims: list[tuple[str, str]],
    body: str = "",
    scope: dict | None = None,
    page_id=None,
    base=None,
    key=None,
    kind="concept",
    aliases=None,
) -> dict:  # noqa: ANN001
    """claims: [(statement, evidence_id)] — iddia metni kanıtta birebir geçer."""
    item = {
        "page_id": page_id,
        "base_revision_id": base,
        "title": title,
        "summary": f"{title} özeti",
        "body_md": body or "\n\n".join(s for s, _ in claims),
        "kind": kind,
        "scope": scope or DEFAULT_SCOPE,
        "aliases": aliases or [],
        "claims": [
            {"statement": s, "kind": "expert_statement", "evidence": [{"evidence_id": e, "quote": s}]}
            for s, e in claims
        ],
    }
    headers = {"Idempotency-Key": key} if key else None
    r = client.post(f"/api/v1/projects/{project_id}/changes", json={"summary": title, "items": [item]}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def submit(client, change_id: str) -> dict:  # noqa: ANN001
    r = client.post(f"/api/v1/changes/{change_id}/submit")
    assert r.status_code == 200, r.text
    return r.json()


def approve(client, change: dict) -> dict:  # noqa: ANN001
    r = client.post(
        f"/api/v1/changes/{change['id']}/reviews",
        json={"decision": "approve", "reason": "Kontrol edildi", "evidence_checked": True, "hash": change["hash"]},
    )
    assert r.status_code == 200, r.text
    return r.json()


def publish(client, change_id: str) -> dict:  # noqa: ANN001
    r = client.post(f"/api/v1/changes/{change_id}/publish")
    assert r.status_code == 200, r.text
    return r.json()


def publish_note(
    author,
    reviewer,
    project_id: str,
    title: str,
    text: str,
    statements: list[str] | None = None,
    scope: dict | None = None,
    **kw,
) -> dict:  # noqa: ANN001
    """Kaynak ekle → kanıt → taslak → incele → yayımla. Dönen: {'source','change','page_id'}"""
    src = add_note(author, project_id, f"{title} notu", text, scope=scope)
    rev_id = src["revision"]["id"]
    statements = statements or [text]
    claims = [(s, evidence(author, rev_id, s)["id"]) for s in statements]
    ch = draft(author, project_id, title, claims, scope=scope, **kw)
    ch = submit(author, ch["id"])
    ch = approve(reviewer, ch)
    ch = publish(reviewer, ch["id"])
    return {"source": src, "change": ch, "page_id": ch["published_page_ids"][0]}
