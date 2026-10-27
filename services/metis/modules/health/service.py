"""Bilgi sağlığı: tek kavram 'bulgu'. Eylemler: düzeltme taslağı, geri çek, gerekçeyle kapat. Toplu kapatma yok.
Çelişki çözümü: iki tarafın kanıtı + seçenek (korunacak / geri çekilecek) + gerekçe + onay kutusu →
normal inceleme akışına giden değişiklik seti (doğrudan yayın yok)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import can_read_page_revision, require_human, require_member
from metis.core.audit import audit
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import (
    ChangeSet,
    ConflictCase,
    ConflictOption,
    ConflictResolution,
    Finding,
    FindingPage,
    Model,
    Page,
    PageRevision,
    Project,
    User,
)
from metis.modules.scopes.service import ensure_default_schedule, lock_project

KIND_ORDER = ["conflict", "source_changed", "review_due", "broken_ref", "missing_owner", "reported"]


class FindingPageOut(BaseModel):
    page_id: uuid.UUID
    title: str
    lifecycle: str


class FindingOut(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    state: str
    detail: dict
    pages: list[FindingPageOut]
    created_at: object
    resolved_at: object
    resolution_reason: str
    resolved_by_name: str | None
    case_id: uuid.UUID | None


class FindingListOut(BaseModel):
    items: list[FindingOut]
    counts: dict[str, int]


class ResolveIn(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)


class ScanIn(BaseModel):
    model_id: uuid.UUID | None = None


class ScheduleIn(BaseModel):
    enabled: bool
    interval_days: int = Field(ge=1, le=90)
    model_id: uuid.UUID | None = None


class ScheduleOut(BaseModel):
    enabled: bool
    interval_days: int
    model_id: uuid.UUID | None
    next_run_at: object
    last_run_at: object


class OptionOut(BaseModel):
    id: uuid.UUID
    ord: int
    title: str
    rationale: str
    prerequisite: str
    keep: list[FindingPageOut]
    retire: list[FindingPageOut]
    evidence: list[dict]


class CaseOut(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID
    summary: str
    questions: list[str]
    state: str
    options: list[OptionOut]
    resolution_change_id: uuid.UUID | None


class ChooseIn(BaseModel):
    option_id: uuid.UUID
    reason: str = Field(min_length=16, max_length=2000)
    acknowledge_whole_pages: bool


def _visible(db: Session, user: User, finding: Finding) -> list[FindingPageOut] | None:
    out = []
    for fp in db.scalars(select(FindingPage).where(FindingPage.finding_id == finding.id)):
        page = db.get(Page, fp.page_id)
        if not page or page.deleted_at is not None:
            continue
        rev_id = page.published_revision_id or db.scalar(select(PageRevision.id).where(PageRevision.page_id == page.id).order_by(PageRevision.number.desc()).limit(1))
        rev = db.get(PageRevision, rev_id) if rev_id else None
        if not can_read_page_revision(db, user, rev):
            return None  # erişilemeyen sayfa içeren bulgu hiç gösterilmez
        out.append(FindingPageOut(page_id=page.id, title=rev.title if rev else "", lifecycle=page.lifecycle))
    return out


def finding_out(db: Session, user: User, f: Finding) -> FindingOut | None:
    pages = _visible(db, user, f)
    if pages is None:
        return None
    if not pages and f.kind != "broken_ref":
        return None
    resolver = db.get(User, f.resolved_by) if f.resolved_by else None
    case_id = db.scalar(select(ConflictCase.id).where(ConflictCase.finding_id == f.id).order_by(ConflictCase.created_at.desc()).limit(1))
    return FindingOut(
        id=f.id, kind=f.kind, severity=f.severity, state=f.state, detail=f.detail, pages=pages, created_at=f.created_at, resolved_at=f.resolved_at,
        resolution_reason=f.resolution_reason, resolved_by_name=resolver.display_name if resolver else None, case_id=case_id,
    )


def list_findings(db: Session, user: User, project_id: uuid.UUID, state: str, kind: str | None) -> FindingListOut:
    require_member(db, user, project_id)
    q = select(Finding).where(Finding.project_id == project_id, Finding.state == state)
    if kind:
        q = q.where(Finding.kind == kind)
    items = [o for f in db.scalars(q.order_by(Finding.created_at.desc()).limit(300)) if (o := finding_out(db, user, f))]
    counts: dict[str, int] = {}
    for s in ("open", "resolved"):
        counts[s] = sum(1 for f in db.scalars(select(Finding).where(Finding.project_id == project_id, Finding.state == s)) if finding_out(db, user, f))
    return FindingListOut(items=items, counts=counts)


def get_finding(db: Session, user: User, finding_id: uuid.UUID) -> Finding:
    f = db.get(Finding, finding_id)
    if not f:
        raise AppError("NOT_FOUND", "finding not found")
    require_member(db, user, f.project_id)
    if finding_out(db, user, f) is None:
        raise AppError("NOT_FOUND", "finding not found")
    return f


def resolve(db: Session, user: User, finding_id: uuid.UUID, reason: str, *, auto: bool = False) -> Finding:
    if not auto:
        require_human(user)
    f = get_finding(db, user, finding_id) if not auto else db.get(Finding, finding_id)
    assert f is not None
    if not auto:
        require_member(db, user, f.project_id, ["reviewer", "steward"])
    if f.state != "open":
        raise AppError("INVALID_STATE", "finding already resolved")
    f.state = "resolved"
    f.resolution_reason = reason.strip()
    f.resolved_by = user.id
    f.resolved_at = utcnow()
    audit(db, user.id, "finding.resolve", "finding", f.id, reason=reason.strip(), auto=auto)
    return f


def auto_resolve_on_publish(db: Session, actor: User, change: ChangeSet, page_ids: set[uuid.UUID]) -> None:
    """Yeni revizyon yayımlanınca o sayfanın kaynak-değişti/inceleme-zamanı bulguları kapanır;
    çözüm kaydı yayımlanınca ilgili çelişki bulgusu kapanır."""
    if page_ids:
        rows = db.scalars(
            select(Finding)
            .join(FindingPage, FindingPage.finding_id == Finding.id)
            .where(FindingPage.page_id.in_(page_ids), Finding.state == "open", Finding.kind.in_(["source_changed", "review_due"]))
        ).all()
        for f in rows:
            resolve(db, actor, f.id, "Sayfanın yeni revizyonu incelenip yayımlandı.", auto=True)
    if change.kind == "resolution" and change.detail.get("finding_id"):
        f = db.get(Finding, uuid.UUID(change.detail["finding_id"]))
        if f and f.state == "open":
            resolve(db, actor, f.id, f"Çelişki çözüm kaydı yayımlandı: {change.summary}", auto=True)
            case = db.scalar(select(ConflictCase).where(ConflictCase.finding_id == f.id).order_by(ConflictCase.created_at.desc()).limit(1))
            if case:
                case.state = "resolved"


def get_schedule(db: Session, user: User, project_id: uuid.UUID) -> ScheduleOut:
    require_member(db, user, project_id)
    s = ensure_default_schedule(db, project_id)
    return ScheduleOut(enabled=s.enabled, interval_days=s.interval_days, model_id=s.model_id, next_run_at=s.next_run_at, last_run_at=s.last_run_at)


def set_schedule(db: Session, user: User, project_id: uuid.UUID, data: ScheduleIn) -> ScheduleOut:
    require_human(user)
    require_member(db, user, project_id, ["steward"])
    lock_project(db, project_id)
    s = ensure_default_schedule(db, project_id)
    if data.model_id:
        from metis.modules.lab.service import eligibility

        m = db.get(Model, data.model_id)
        ok, reason = eligibility(db, m, db.get(Project, project_id)) if m else (False, "not_found")
        if not ok:
            raise AppError("MODEL_NOT_ELIGIBLE", "model not eligible", reason=reason)
    s.enabled = data.enabled
    s.interval_days = data.interval_days
    s.model_id = data.model_id
    s.next_run_at = utcnow() + timedelta(days=data.interval_days)
    audit(db, user.id, "schedule.update", "project", project_id, enabled=data.enabled, interval_days=data.interval_days)
    return get_schedule(db, user, project_id)


def scan_now(db: Session, user: User, project_id: uuid.UUID, data: ScanIn) -> uuid.UUID:
    require_human(user)
    require_member(db, user, project_id, ["contributor", "reviewer", "steward"])
    from metis.core.models import Job
    from metis.modules.jobs.service import add_event

    inputs = {}
    if data.model_id:
        from metis.modules.lab.service import eligibility

        m = db.get(Model, data.model_id)
        ok, reason = eligibility(db, m, db.get(Project, project_id)) if m else (False, "not_found")
        if not ok:
            raise AppError("MODEL_NOT_ELIGIBLE", "model not eligible", reason=reason)
        # Elle başlatılan tarama başlatanın anahtarıyla (2.0.28); zamanlanmış tarama ortak anahtarla.
        from metis.modules.keys.service import key_for

        key = key_for(db, user, m.provider_id)  # type: ignore[union-attr]
        if key is None:
            raise AppError("PERSONAL_KEY_MISSING", "add your own API key for this model's provider", provider_id=str(m.provider_id))  # type: ignore[union-attr]
        inputs["model_id"] = str(data.model_id)
        inputs["key_source"] = key.source
    job = Job(project_id=project_id, requester_id=user.id, kind="maintenance", title="Bakım taraması", inputs=inputs, state="queued", priority=30, model_id=data.model_id)
    db.add(job)
    db.flush()
    add_event(db, job.id, "state", state="queued")
    audit(db, user.id, "health.scan", "project", project_id, job_id=job.id)
    return job.id


# ---------------------------------------------------------------- çelişki çözümü


def _page_out(db: Session, page_id: uuid.UUID) -> FindingPageOut:
    page = db.get(Page, page_id)
    rev = db.get(PageRevision, page.published_revision_id) if page and page.published_revision_id else None
    return FindingPageOut(page_id=page_id, title=rev.title if rev else "", lifecycle=page.lifecycle if page else "withdrawn")


def case_out(db: Session, case: ConflictCase) -> CaseOut:
    options = db.scalars(select(ConflictOption).where(ConflictOption.case_id == case.id).order_by(ConflictOption.ord)).all()
    res = db.scalar(select(ConflictResolution).where(ConflictResolution.case_id == case.id).order_by(ConflictResolution.created_at.desc()).limit(1))
    return CaseOut(
        id=case.id,
        finding_id=case.finding_id,  # type: ignore[arg-type]
        summary=case.summary,
        questions=case.questions,
        state=case.state,
        options=[OptionOut(id=o.id, ord=o.ord, title=o.title, rationale=o.rationale, prerequisite=o.prerequisite, keep=[_page_out(db, p) for p in o.keep_page_ids], retire=[_page_out(db, p) for p in o.retire_page_ids], evidence=o.evidence) for o in options],
        resolution_change_id=res.change_set_id if res else None,
    )


def open_case(db: Session, user: User, finding_id: uuid.UUID) -> CaseOut:
    """Deterministik seçenekler: her taraf için 'bu sayfa korunsun, diğeri geri çekilsin'. Model kazanan seçmez."""
    require_human(user)
    f = get_finding(db, user, finding_id)
    if f.kind != "conflict" or f.state != "open":
        raise AppError("INVALID_STATE", "only open conflicts can be resolved")
    existing = db.scalar(select(ConflictCase).where(ConflictCase.finding_id == f.id, ConflictCase.state == "open").limit(1))
    if existing:
        return case_out(db, existing)
    sides = f.detail.get("sides", [])
    if len(sides) < 2:
        raise AppError("INVALID_STATE", "conflict has fewer than two sides")
    case = ConflictCase(
        project_id=f.project_id,
        finding_id=f.id,
        summary="İki onaylı kayıt aynı özellik için farklı değer bildiriyor. Hangisinin doğru olduğu kanıtla doğrulanmadan karar verilmez.",
        questions=["Hangi ölçüm, test kaydı veya güncel veri sayfası doğru değeri gösteriyor?", "Değerler farklı koşullar (mod, kart, sürüm) için mi geçerli?"],
        created_by=user.id,
    )
    db.add(case)
    db.flush()
    for i, keep in enumerate(sides[:2]):
        other = sides[1 - i]
        db.add(
            ConflictOption(
                case_id=case.id,
                ord=i,
                title=f"«{keep['page_title']}» korunsun",
                rationale="Bir insan bu tarafın kanıtını doğrularsa uygulanır; diğer sayfa bütünüyle geri çekilir (o sayfadaki ilgisiz bilgiler de yayından kalkar).",
                prerequisite="Doğru değeri gösteren güncel bir kaynak (ölçüm, test kaydı, veri sayfası) incelenmiş olmalı.",
                keep_page_ids=[uuid.UUID(keep["page_id"])],
                retire_page_ids=[uuid.UUID(other["page_id"])],
                evidence=[{"evidence_id": s["evidence_id"], "quote": s["quote"], "page_title": s["page_title"]} for s in (keep, other)],
            )
        )
    audit(db, user.id, "conflict.case_open", "finding", f.id, case_id=case.id)
    db.flush()
    return case_out(db, case)


def choose(db: Session, user: User, case_id: uuid.UUID, data: ChooseIn) -> CaseOut:
    require_human(user)
    case = db.get(ConflictCase, case_id)
    if not case or case.state != "open":
        raise AppError("NOT_FOUND", "case not found")
    f = get_finding(db, user, case.finding_id)  # type: ignore[arg-type]
    require_member(db, user, f.project_id, ["contributor"])
    if not data.acknowledge_whole_pages:
        raise AppError("REVIEW_CHECK_REQUIRED", "acknowledge that whole pages are withdrawn")
    option = db.get(ConflictOption, data.option_id)
    if not option or option.case_id != case.id:
        raise AppError("NOT_FOUND", "option not found")
    from metis.modules.changes import schemas as cs
    from metis.modules.changes import service as changes

    items = []
    for pid in option.retire_page_ids:
        page = db.get(Page, pid)
        if not page or page.lifecycle != "active" or not page.published_revision_id:
            raise AppError("INVALID_STATE", "page already inactive")
        items.append(cs.ItemIn(page_id=pid, base_revision_id=page.published_revision_id, action="withdraw"))
    change = changes.create_change(db, user, f.project_id, cs.ChangeCreateIn(summary=f"Çelişki çözümü: {option.title}. Gerekçe: {data.reason.strip()}"[:4000], items=items, submit=True), kind="resolution")
    change.detail = {**change.detail, "finding_id": str(f.id), "case_id": str(case.id), "resolution": {"option": option.title, "reason": data.reason.strip()}}
    db.add(ConflictResolution(case_id=case.id, option_id=option.id, chosen_by=user.id, reason=data.reason.strip(), change_set_id=change.id))
    audit(db, user.id, "conflict.choose", "finding", f.id, option_id=option.id, change_id=change.id)
    db.flush()
    return case_out(db, case)
