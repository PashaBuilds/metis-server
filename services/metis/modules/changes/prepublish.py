"""Yayın öncesi kontrol ("Yazar yayımlar" politikası): taslağın iddiaları yayındaki bilgilerle çelişiyor ya da
taslak var olan bir bilgiyi tekrar ediyor mu?

1. Kural (her zaman, hızlı): aynı biçimli fakat farklı değerli iddia, örtüşen kapsamda (bakım taramasıyla aynı kural).
2. Model (uygun model varsa): kural adaylarını CLAIM_CONFLICT ile, aramayla bulunan en yakın bilgileri PAGE_DIFF ile
   değerlendirir. Model yoksa ya da yanıt vermezse bu açıkça bildirilir (sessiz geçiş yok); yayın kural sonucuyla
   yapılabilir, bakım taraması model kontrolünü sonra tamamlar.

Model çağrıları istek oturumu dışında yapılır; sonrasında erişim yeniden denetlenir (yavaş çağrı sonrası yetki ilkesi).
Sonuç taslağın `detail.prepublish` alanında, içerik hash'ine bağlı saklanır; yayın yalnız güncel kontrolle yapılır.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from metis.core.access import unreadable_revisions
from metis.core.db import transaction, utcnow
from metis.core.errors import AppError
from metis.core.models import ChangeSet, Claim, Page, PageRevision, Project, Provider, User
from metis.llm import contracts, prompts
from metis.llm.client import ModelClient
from metis.modules.changes import schemas
from metis.modules.health.maintenance import _strip_numbers
from metis.modules.scopes.semantics import overlaps

MAX_RULE_JUDGE = 5
MAX_SIMILAR = 3
CALL_TIMEOUT_S = 45.0


def _candidates(db, user: User, change: ChangeSet) -> dict:  # noqa: ANN001
    """Oturum içinde: taslağın iddiaları, kural adayları ve benzer bilgiler (model çağrısı yok)."""
    from metis.modules.changes.service import _items
    from metis.modules.search.service import search

    project_id = change.project_id
    drafts = []
    for item in _items(db, change):
        if item.action != "upsert" or not item.proposed_revision_id:
            continue
        rev = db.get(PageRevision, item.proposed_revision_id)
        assert rev is not None
        claims = list(db.scalars(select(Claim.statement).where(Claim.page_revision_id == rev.id).order_by(Claim.ord)))
        drafts.append({"page_id": item.page_id, "title": rev.title, "summary": rev.summary, "body": rev.body_md, "scope": rev.scope, "claims": claims})
    if not drafts:
        return {"drafts": [], "rule": [], "similar": []}
    own_pages = {d["page_id"] for d in drafts}
    rows = db.execute(
        select(Page.id, PageRevision.id, PageRevision.title, PageRevision.scope, Claim.statement)
        .join(PageRevision, PageRevision.id == Page.published_revision_id)
        .join(Claim, Claim.page_revision_id == PageRevision.id)
        .where(Page.project_id == project_id, Page.deleted_at.is_(None), Page.lifecycle == "active", Page.id.not_in(own_pages))
    ).all()
    hidden = unreadable_revisions(db, user, project_id, [r[1] for r in rows])
    rule, seen = [], set()
    for d in drafts:
        for ours in d["claims"]:
            shape = _strip_numbers(ours)
            for page_id, rev_id, title, scope, theirs in rows:
                if rev_id in hidden or theirs == ours or _strip_numbers(theirs) != shape or not overlaps(d["scope"], scope):
                    continue
                key = (page_id, shape)
                if key in seen:
                    continue
                seen.add(key)
                rule.append({"draft": d["title"], "draft_scope": d["scope"], "ours": ours, "page_id": page_id, "page_title": title, "scope": scope, "theirs": theirs})
    similar = []
    for d in drafts:
        hits = search(db, user, project_id, f"{d['title']} {d['summary']}"[:400], None, None, MAX_SIMILAR + len(own_pages)).hits
        for h in [h for h in hits if h.page_id not in own_pages][:MAX_SIMILAR]:
            statements = list(db.scalars(select(Claim.statement).where(Claim.page_revision_id == h.revision_id).order_by(Claim.ord)))
            similar.append({"draft": d, "page_id": h.page_id, "page_title": h.title, "statements": statements})
    return {"drafts": drafts, "rule": rule, "similar": similar}


def run_check(user_id: uuid.UUID, change_id: uuid.UUID) -> schemas.PrepublishCheckOut:
    from metis.modules.changes.service import accessible_change
    from metis.modules.lab.service import route

    # 1) Oturum içinde aday üretimi ve model seçimi (otomatik yönlendirme; uygun model yoksa açıkça "yok").
    with transaction() as db:
        user = db.get(User, user_id)
        assert user is not None
        change = accessible_change(db, user, change_id)
        if change.state not in ("draft", "in_review", "approved"):
            raise AppError("INVALID_STATE", "only open records can be checked", state=change.state)
        project = db.get(Project, change.project_id)
        assert project is not None
        change_hash = change.hash
        cand = _candidates(db, user, change)
        model, _reasons = route(db, project)
        provider = db.get(Provider, model.provider_id) if model else None
        model_name = model.display_name if model else None
        if model is not None:
            db.expunge(model)
        if provider is not None:
            db.expunge(provider)

    issues: list[dict] = []
    status = "not_configured" if model is None or provider is None else "ok"
    client = ModelClient()
    # 2) Kural adayları: model varsa değerlendirir, yoksa olası çelişki olarak bildirilir.
    for c in cand["rule"][:MAX_RULE_JUDGE] if status == "ok" else cand["rule"]:
        verdict, reason, by = "conflict", "", "rule"
        if status == "ok":
            left = {"subject": c["draft"], "attribute": "değer", "value": c["ours"], "quote": c["ours"], "scope": {**c["draft_scope"], "condition": ""}}
            right = {"subject": c["page_title"], "attribute": "değer", "value": c["theirs"], "quote": c["theirs"], "scope": {**c["scope"], "condition": ""}}
            res = client.call(model, provider, prompt_id=prompts.CLAIM_CONFLICT, payload={"kayit_a": left, "kayit_b": right}, schema=contracts.ClaimJudgement, purpose="prepublish", max_tokens=800, timeout_s=CALL_TIMEOUT_S)
            if not res.ok:
                status = "failed"
            else:
                verdict, reason, by = res.output["verdict"], res.output["reason"], "model"
        if verdict in ("conflict", "supersede"):
            issues.append({"kind": "conflict", "page_id": c["page_id"], "page_title": c["page_title"], "ours": c["ours"], "theirs": c["theirs"], "reason": reason, "detected_by": by})
    # 3) Benzer bilgiler: yalnız model ile (anlam karşılaştırması); modelsiz arama sonucu gürültülü olur.
    if status == "ok":
        for s in cand["similar"]:
            d = s["draft"]
            res = client.call(model, provider, prompt_id=prompts.PAGE_DIFF, payload={"kayit_a": "\n".join([d["title"], d["summary"], *d["claims"]])[:8000], "kayit_b": "\n".join([s["page_title"], *s["statements"]])[:8000]}, schema=contracts.PageDiff, purpose="prepublish", max_tokens=1000, timeout_s=CALL_TIMEOUT_S)
            if not res.ok:
                status = "failed"
                break
            kind = {"conflict_candidate": "conflict", "no_change": "duplicate", "update": "overlap", "supersede": "overlap"}.get(res.output["verdict"])
            if kind and not any(i["page_id"] == s["page_id"] and i["kind"] == kind for i in issues):
                issues.append({"kind": kind, "page_id": s["page_id"], "page_title": s["page_title"], "ours": "", "theirs": "", "reason": res.output["reason"], "detected_by": "model"})

    # 4) Yavaş çağrılardan sonra: erişim yeniden denetlenir, sonuç hash'e bağlı saklanır.
    with transaction() as db:
        user = db.get(User, user_id)
        assert user is not None
        change = accessible_change(db, user, change_id)
        db.refresh(change, with_for_update=True)
        if change.hash != change_hash:
            raise AppError("HASH_MISMATCH", "record changed during the check; check again", current_hash=change.hash)
        readable = []
        for i in issues:
            page = db.get(Page, i["page_id"])
            if page and page.published_revision_id and not unreadable_revisions(db, user, change.project_id, [page.published_revision_id]):
                readable.append({**i, "page_id": str(i["page_id"])})
        out = schemas.PrepublishCheckOut(hash=change_hash, model_status=status, model_name=model_name, issues=readable, checked_at=utcnow())
        change.detail = {**change.detail, "prepublish": out.model_dump(mode="json")}
        return out
