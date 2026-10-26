"""Bakım: deterministik taramalar (inceleme zamanı, kırık referans, sahipsiz sayfa, kaynak değişimi) ve
isteğe bağlı model destekli havuz denetimi (çelişki adayları). Tek bakım zamanlayıcısı (`schedules`)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from metis.core.db import transaction, utcnow
from metis.core.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingPage,
    Job,
    Page,
    PageRevision,
    Project,
    ProjectMember,
    PublicationRelation,
    RelationRevision,
    Schedule,
    Source,
    SourceRevision,
    User,
)
from metis.core.util import fingerprint
from metis.llm import contracts, prompts
from metis.modules.jobs.service import add_event
from metis.modules.scopes.semantics import overlaps

MAX_JUDGE_PAIRS = 8


def _open_finding(db: Session, project_id: uuid.UUID, kind: str, fp: str, page_ids: list[uuid.UUID], severity: str, detail: dict, actor: uuid.UUID | None) -> Finding | None:
    if db.scalar(select(Finding.id).where(Finding.project_id == project_id, Finding.fingerprint == fp, Finding.state == "open")):
        return None
    f = Finding(project_id=project_id, kind=kind, severity=severity, fingerprint=fp, detail=detail, created_by=actor)
    db.add(f)
    db.flush()
    for pid in dict.fromkeys(page_ids):
        db.add(FindingPage(finding_id=f.id, page_id=pid))
    return f



def conflict_fingerprint(a: dict, b: dict) -> str:
    """Aynı çelişki çifti için tek parmak izi (tarama, kurgusal tohum ve yeniden taramalar aynı bulguyu paylaşır)."""
    return fingerprint("conflict", *sorted([str(a["page_id"]), str(b["page_id"])]), _strip_numbers(a["statement"]))

def deterministic_scan(db: Session, project_id: uuid.UUID, actor: uuid.UUID | None) -> dict[str, int]:
    project = db.get(Project, project_id)
    assert project is not None
    counts = {"review_due": 0, "broken_ref": 0, "missing_owner": 0, "source_changed": 0}
    now = utcnow()
    pages = db.execute(
        select(Page, PageRevision).join(PageRevision, PageRevision.id == Page.published_revision_id).where(Page.project_id == project_id, Page.deleted_at.is_(None), Page.lifecycle == "active")
    ).all()
    for page, rev in pages:
        reviewed = page.reviewed_at or page.published_at
        if reviewed and reviewed + timedelta(days=project.review_interval_days) < now:
            if page.freshness == "current":
                page.freshness = "review_due"
            period = int((now - reviewed).days // max(1, project.review_interval_days))
            if _open_finding(db, project_id, "review_due", fingerprint("review_due", page.id, rev.id, period), [page.id], "low", {"page_title": rev.title, "reviewed_at": reviewed.isoformat(), "interval_days": project.review_interval_days}, actor):
                counts["review_due"] += 1
        owner = db.get(User, page.owner_id)
        if not owner or not owner.active:
            if _open_finding(db, project_id, "missing_owner", fingerprint("missing_owner", page.id, page.owner_id), [page.id], "low", {"page_title": rev.title}, actor):
                counts["missing_owner"] += 1
        for src_id, src_rev_no, current_no, deleted, title in db.execute(
            select(Source.id, SourceRevision.number, Source.current_revision_no, Source.deleted_at, Source.title)
            .join(SourceRevision, SourceRevision.source_id == Source.id)
            .join(Evidence, Evidence.source_revision_id == SourceRevision.id)
            .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
            .join(Claim, Claim.id == ClaimEvidence.claim_id)
            .where(Claim.page_revision_id == rev.id)
            .distinct()
        ):
            if deleted is not None:
                if _open_finding(db, project_id, "broken_ref", fingerprint("broken_source", page.id, src_id), [page.id], "high", {"page_title": rev.title, "source_title": title, "reason": "source_deleted"}, actor):
                    counts["broken_ref"] += 1
            elif current_no > src_rev_no and src_id != page.note_source_id:  # kendi notunun yeni taslağı değişiklik sayılmaz
                if _open_finding(db, project_id, "source_changed", fingerprint("source_changed_scan", page.id, src_id, current_no), [page.id], "medium", {"page_title": rev.title, "source_id": str(src_id), "source_title": title, "new_revision_number": current_no}, actor):
                    counts["source_changed"] += 1
    if project.active_publication_id:
        for rr in db.scalars(
            select(RelationRevision).join(PublicationRelation, PublicationRelation.revision_id == RelationRevision.id).where(PublicationRelation.publication_id == project.active_publication_id)
        ):
            for pid in (rr.subject_page_id, rr.object_page_id):
                p = db.get(Page, pid)
                if not p or p.deleted_at is not None or p.lifecycle != "active":
                    other = rr.object_page_id if pid == rr.subject_page_id else rr.subject_page_id
                    if _open_finding(db, project_id, "broken_ref", fingerprint("broken_relation", rr.relation_id, pid), [other], "medium", {"relation_id": str(rr.relation_id), "predicate": rr.predicate, "reason": "relation_target_inactive"}, actor):
                        counts["broken_ref"] += 1
    return counts


_FOLD = str.maketrans({"µ": "μ", "ς": "σ"})


def _strip_numbers(text: str) -> str:
    # Veritabanındaki biçim özetiyle (claims.shape_md5: ICU lower + aynı eşlemeler) aynı kural. casefold'un birleştirdiği
    # mikro işareti/Yunan mu, ß/ss ve son sigma da birleşir ("100 µs" ile "200 μs" aynı biçim).
    return re.sub(r"\d+(?:[.,]\d+)?", "#", text.lower().replace("ß", "ss").translate(_FOLD)).strip()


log = logging.getLogger("metis.maintenance")
_prefilter: list[bool] = []


def shape_prefilter(db: Session) -> bool:
    """claims.shape_md5 Python kuralıyla birebir mi? 0015 ICU'suz PostgreSQL'de yerel ayarın `lower`'ına düşer ("İ" gibi
    harflerde özet farklı olur); o zaman ön süzgeç kullanılmaz, aday kuralı tüm iddialarda Python'da uygulanır."""
    if not _prefilter:
        expr = db.scalar(
            text(
                """SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d
                   JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
                   WHERE d.adrelid = 'claims'::regclass AND a.attname = 'shape_md5'"""
            )
        )
        _prefilter.append(bool(expr and "und-x-icu" in expr))
        if not _prefilter[0]:
            log.warning("claims.shape_md5 without ICU collation: shape prefilter disabled")
    return _prefilter[0]


def conflict_pairs(db: Session, project_id: uuid.UUID) -> list[dict]:
    """Örtüşen kapsamda aynı biçimli fakat farklı değerli iddia çiftleri (deterministik aday üretimi)."""
    def base():  # noqa: ANN202
        return (
            select()
            .select_from(Page)
            .join(PageRevision, PageRevision.id == Page.published_revision_id)
            .join(Claim, Claim.page_revision_id == PageRevision.id)
            .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
            .where(Page.project_id == project_id, Page.deleted_at.is_(None), Page.lifecycle == "active")
        )

    # Yalnız birden çok sayfada görülen biçimler (claims.shape_md5 dizini): büyük derlemde tüm iddiaları taşımamak için.
    q = base().add_columns(Page.id, PageRevision.title, PageRevision.scope, Claim.statement, ClaimEvidence.evidence_id)
    if shape_prefilter(db):
        shared = base().add_columns(Claim.shape_md5).group_by(Claim.shape_md5).having(func.count(func.distinct(Page.id)) > 1)
        q = q.where(Claim.shape_md5.in_(shared))
    rows = db.execute(q).all()
    return pair_candidates(rows)


def pair_candidates(rows: list) -> list[dict]:
    """(page_id, title, scope, statement, evidence_id) satırlarından aday çiftler. Satırlar biçime göre gruplanır (yalnız
    aynı biçimliler karşılaştırılır: büyük derlemde doğrusal); sıra, satır sırasıyla iç içe döngünün sırasıdır."""
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(_strip_numbers(r[3]), []).append(i)
    found: list[tuple[int, int]] = []
    for shape, idx in groups.items():
        if len(idx) < 2:
            continue
        seen: set[tuple] = set()
        for x, i in enumerate(idx):
            a = rows[i]
            for j in idx[x + 1 :]:
                b = rows[j]
                if a[0] == b[0] or a[3] == b[3]:
                    continue
                key = (*sorted([str(a[0]), str(b[0])]), shape)
                if key not in seen:
                    seen.add(key)
                    found.append((i, j))
    found.sort()
    return [
        {"a": {"page_id": a[0], "title": a[1], "scope": a[2], "statement": a[3], "evidence_id": a[4]}, "b": {"page_id": b[0], "title": b[1], "scope": b[2], "statement": b[3], "evidence_id": b[4]}}
        for a, b in ((rows[i], rows[j]) for i, j in found)
    ]


def run_maintenance_job(ctx) -> None:  # noqa: ANN001
    from metis.worker.prepare import call, load_model

    with transaction() as db:
        job = ctx.guard(db)
        project_id, job_id, requester_id = job.project_id, job.id, job.requester_id
        use_model = bool(job.inputs.get("model_id"))
        model = provider = None
        if use_model:
            model, provider = load_model(db, job)
    ctx.step("scan")
    with transaction() as db:
        ctx.guard(db)
        counts = deterministic_scan(db, project_id, requester_id)
        pairs = conflict_pairs(db, project_id)
    conflicts = 0
    judged = []
    for pair in pairs[:MAX_JUDGE_PAIRS]:
        a, b = pair["a"], pair["b"]
        if not overlaps(a["scope"], b["scope"]):
            judged.append({"a": a["title"], "b": b["title"], "verdict": "scope_disjoint"})
            continue
        if use_model:
            ctx.step("judge", page=a["title"])
            left = {"subject": a["title"], "attribute": "değer", "value": a["statement"], "quote": a["statement"], "scope": {**a["scope"], "condition": ""}}
            right = {"subject": b["title"], "attribute": "değer", "value": b["statement"], "quote": b["statement"], "scope": {**b["scope"], "condition": ""}}
            verdict = call(ctx, model, provider, prompts.CLAIM_CONFLICT, {"kayit_a": left, "kayit_b": right}, contracts.ClaimJudgement, output_tokens=800)["verdict"]
        else:
            verdict = "conflict"  # aynı biçim, farklı değer, örtüşen kapsam: deterministik aday (insan inceler)
        judged.append({"a": a["title"], "b": b["title"], "verdict": verdict})
        if verdict != "conflict":
            continue
        with transaction() as db:
            ctx.guard(db)
            sides = [{"page_id": str(x["page_id"]), "page_title": x["title"], "quote": x["statement"], "evidence_id": str(x["evidence_id"])} for x in (a, b)]
            fp = conflict_fingerprint(a, b)
            if _open_finding(db, project_id, "conflict", fp, [a["page_id"], b["page_id"]], "high", {"sides": sides, "detected_by": "model" if use_model else "rule"}, requester_id):
                conflicts += 1
    report = {"counts": {**counts, "conflict": conflicts}, "judged": judged}
    total = sum(report["counts"].values())
    labels = {"conflict": "çelişki", "review_due": "inceleme zamanı", "source_changed": "kaynak değişti", "broken_ref": "kırık referans", "missing_owner": "sahipsiz sayfa"}
    parts = [f"{n} {labels[k]}" for k, n in report["counts"].items() if n]
    summary = f"{total} yeni bulgu: " + ", ".join(parts) + "." if total else "Yeni bulgu yok."
    with transaction() as db:
        sched = db.scalar(select(Schedule).where(Schedule.project_id == project_id, Schedule.kind == "maintenance"))
        if sched:
            sched.last_run_at = utcnow()
    ctx.finish("completed", summary, report=report)
    _ = job_id


def schedule_due_jobs() -> int:
    """Tek bakım zamanlayıcısı: süresi gelen projeler için bakım görevi kuyruğa alınır."""
    created = 0
    with transaction() as db:
        now = utcnow()
        for sched in db.scalars(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run_at <= now).with_for_update(skip_locked=True)):
            project = db.get(Project, sched.project_id)
            if not project or project.deleted_at is not None:
                continue
            active = db.scalar(select(Job.id).where(Job.project_id == project.id, Job.kind == "maintenance", Job.state.in_(["queued", "running"])))
            if not active:
                requester = db.scalar(
                    select(User.id).join(ProjectMember, ProjectMember.user_id == User.id).where(ProjectMember.project_id == project.id, ProjectMember.role == "steward", User.active.is_(True)).limit(1)
                ) or db.scalar(select(User.id).where(User.is_admin.is_(True), User.active.is_(True), User.kind == "human").limit(1))
                if requester:
                    job = Job(project_id=project.id, requester_id=requester, kind="maintenance", title="Bakım taraması", inputs={"model_id": str(sched.model_id)} if sched.model_id else {}, state="queued", priority=30, model_id=sched.model_id)
                    db.add(job)
                    db.flush()
                    add_event(db, job.id, "state", state="queued")
                    created += 1
            sched.next_run_at = now + timedelta(days=sched.interval_days)
    return created
