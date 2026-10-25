"""Kurgusal arama derlemini (evals/retrieval/corpus.py) not tabanlı bilgi olarak yayımlar ve ölçüm sorularını hazırlar."""

from __future__ import annotations

import uuid

from evals.retrieval.corpus import PAGES, QUESTIONS

from metis.modules.search.evaluate import EvalQuestion
from tests.kb import DEFAULT_SCOPE


def publish_corpus(client, pid: str) -> dict[str, str]:  # noqa: ANN001
    """Projenin "Yazar yayımlar" politikasında olduğunu varsayar. Dönen: slug → sayfa kimliği."""
    out = {}
    for slug, title, body in PAGES:
        item = {"note": True, "title": title, "summary": "", "body_md": body, "scope": DEFAULT_SCOPE}
        r = client.post(f"/api/v1/projects/{pid}/changes", json={"summary": title, "items": [item]})
        assert r.status_code == 201, r.text
        change = r.json()
        assert client.post(f"/api/v1/changes/{change['id']}/check").status_code == 200
        change = client.get(f"/api/v1/changes/{change['id']}").json()
        r = client.post(f"/api/v1/changes/{change['id']}/publish-direct", json={"hash": change["hash"], "acknowledge_issues": True})
        assert r.status_code == 200, r.text
        out[slug] = r.json()["published_page_ids"][0]
    return out


def corpus_questions(pages: dict[str, str]) -> list[EvalQuestion]:
    return [
        EvalQuestion(id=str(i), question=q, expected_page_ids=[uuid.UUID(pages[s]) for s in slugs], expected_quote=quote, kind=kind)
        for i, (q, slugs, quote, kind) in enumerate(QUESTIONS)
    ]
