"""`metis import-v1` çalıştırıcısı (brief 5.10, docs/adr/v2-ADR-002-legacy-import.md).

Akış: yedeği aç ve doğrula → hedef DB boş mu → planı bellekte kur → plan üzerinden doğrulama → rapor.
`--dry-run` yalnız raporu üretir (veri yazmaz; yalnız `legacy_import_runs` işletim kaydı tutulur).
Apply: bloblar geçici dizine → tek transaction (FK sırasıyla ekleme, gecikmeli işaretçiler, arama indeksi,
DB üzerinden ikinci doğrulama, audit) → commit → bloblar yerine taşınır. Herhangi bir hata: rollback, geçici
dizin silinir, "hiçbir şey değiştirilmedi". Rapor iki modda birebir aynıdır (zaman/mod rapora girmez).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select, update

from metis.core.audit import audit
from metis.core.blobs import blob_path
from metis.core.config import get_settings
from metis.core.db import Base, transaction
from metis.core.errors import AppError
from metis.core.models import LegacyImportRun, Project, PublicationPage, User
from metis.legacy_import.archive import ImportRefused, LegacyBackup, open_backup
from metis.legacy_import.transform import Plan, build_plan

log = logging.getLogger("metis.legacy_import")
NOTHING_CHANGED = "Hiçbir şey değiştirilmedi."
DEFERRED_FK = {("projects", "active_publication_id"), ("pages", "published_revision_id"), ("pages", "published_at"), ("pages", "reviewed_at"), ("relations", "published_revision_id"), ("change_sets", "predecessor_id")}


class VerificationFailed(Exception):
    pass


# ------------------------------------------------------------------ doğrulama (plan üzerinden)


def verify_plan(plan: Plan, backup: LegacyBackup) -> dict[str, Any]:
    t = backup.tables
    rows = plan.rows
    # 1) v1 verify(): her yayının, değişiklik setinin hash'iyle eşleşen bir onayı var
    changes = {str(c["id"]): c for c in t["change_sets"]}
    approvals = t["approvals"]
    pub_checks = []
    for pub in sorted(t["publications"], key=lambda p: str(p["id"])):
        ch = changes.get(str(pub.get("change_id")))
        ok = bool(ch) and any(a["change_id"] == ch["id"] and a["hash"] == ch["hash"] and a["decision"] == "approved" for a in approvals)
        pub_checks.append({"publication_id": str(pub["id"]), "ok": ok})
    # 2) aktif yayındaki her sayfa açılabiliyor, iddiaları kanıta bağlı
    pages = {p["id"]: p for p in rows["pages"]}
    evidence_ids = {e["id"] for e in rows["evidence"]}
    claims_by_rev: dict[Any, list[Any]] = defaultdict(list)
    for c in rows["claims"]:
        claims_by_rev[c["page_revision_id"]].append(c["id"])
    links: Counter = Counter(ce["claim_id"] for ce in rows["claim_evidence"] if ce["evidence_id"] in evidence_ids)
    active_pub = {pid: vals["active_publication_id"] for tbl, pid, vals in plan.updates if tbl == "projects"}
    active_pages = []
    for pp in rows["publication_pages"]:
        if pp["publication_id"] not in active_pub.values():
            continue
        page = pages.get(pp["page_id"])
        if not page or page["lifecycle"] != "active" or page["deleted_at"] is not None:
            continue
        claim_ids = claims_by_rev.get(pp["revision_id"], [])
        active_pages.append({"page_id": str(pp["page_id"]), "revision_id": str(pp["revision_id"]), "claims": len(claim_ids), "claims_linked": sum(1 for c in claim_ids if links[c] > 0)})
    active_pages.sort(key=lambda x: x["page_id"])
    # 3) silinmiş/geri çekilmiş kayıtlar aktif görünümlerde yok
    active_ids = {a["page_id"] for a in active_pages}
    deleted_change_pages = {str(i["page_id"]) for c in rows["change_sets"] if c["deleted_at"] is not None for i in rows["change_set_items"] if i["change_set_id"] == c["id"]}
    withdrawn = {str(p["id"]) for p in rows["pages"] if p["lifecycle"] != "active"}
    leaked = sorted((deleted_change_pages | withdrawn) & active_ids)
    deleted_sources = [str(s["id"]) for s in rows["sources"] if s["deleted_at"] is not None]
    return {
        "blobs": {"count": len(backup.blobs), "sha256_verified": len(backup.blobs), "hashes": sorted(backup.blobs)},
        "publications": {"checked": len(pub_checks), "with_matching_approval": sum(1 for p in pub_checks if p["ok"]), "failures": [p["publication_id"] for p in pub_checks if not p["ok"]]},
        "active_pages": {"count": len(active_pages), "claims": sum(a["claims"] for a in active_pages), "claims_linked": sum(a["claims_linked"] for a in active_pages), "pages": active_pages},
        "deleted_hidden": {"withdrawn_pages": len(withdrawn), "deleted_change_pages": len(deleted_change_pages), "deleted_sources": len(deleted_sources), "visible_in_active_views": leaked},
        "provider_secrets": {"providers": len(rows["providers"]), "reencrypted": sum(1 for p in rows["providers"] if p["secret_enc"]), "plaintext_written": False},
        "mentor_sample": {"state": "atlandı", "reason": "Aktarılan modellerin yeterliliği taşınmaz (prompt ve transport değişti); Model laboratuvarında test ve benchmark sonrası örnek sorular çalıştırılır."},
    }


def verification_ok(v: dict[str, Any]) -> bool:
    ap = v["active_pages"]
    return not v["publications"]["failures"] and ap["claims"] == ap["claims_linked"] and not v["deleted_hidden"]["visible_in_active_views"]


# ------------------------------------------------------------------ rapor


def build_report(plan: Plan, backup: LegacyBackup, verification: dict[str, Any]) -> dict[str, Any]:
    skipped_by: Counter = Counter((s["table"], s["reason"]) for s in plan.skipped)
    return {
        "format": "metis-legacy-import-report-v1",
        "source_sha256": backup.sha256,
        "source_schema": backup.manifest.get("schema"),
        "source_counts": plan.source_counts,
        "target_counts": {k: len(v) for k, v in sorted(plan.rows.items()) if v},
        "skipped_summary": [{"table": t, "reason": r, "count": n} for (t, r), n in sorted(skipped_by.items())],
        "skipped": sorted(plan.skipped, key=lambda s: (s["table"], s["id"])),
        "cancelled_jobs": sorted(plan.cancelled_jobs, key=lambda j: j["id"]),
        "notes": sorted(set(plan.notes)),
        "not_imported_settings": sorted(set(plan.not_imported_settings)),
        "verification": verification,
        "verification_ok": verification_ok(verification),
    }


def report_markdown(report: dict[str, Any], mode: str) -> str:
    v = report["verification"]
    ok = "geçti" if report["verification_ok"] else "KALDI"
    lines = [
        "# v0.5.5 aktarım raporu",
        "",
        f"- Mod: {'deneme (dry-run) — veri yazılmadı' if mode == 'dry_run' else 'uygulama — tek transaction ile yazıldı'}",
        f"- Yedek SHA-256: `{report['source_sha256']}` (şema {report['source_schema']})",
        f"- Doğrulama: **{ok}**",
        "",
        "## Satır sayıları",
        "",
        "| v0.5.5 tablosu | satır |",
        "|---|---|",
        *[f"| {k} | {n} |" for k, n in report["source_counts"].items() if n],
        "",
        "| v2 tablosu | aktarılan satır |",
        "|---|---|",
        *[f"| {k} | {n} |" for k, n in report["target_counts"].items()],
        "",
        "## Atlanan kayıtlar",
        "",
        *([f"- {s['table']}: {s['count']} — {s['reason']}" for s in report["skipped_summary"]] or ["- Yok"]),
        "",
        "## Doğrulama",
        "",
        f"- Bloblar: {v['blobs']['sha256_verified']}/{v['blobs']['count']} SHA-256 doğrulandı.",
        f"- Yayınlar: {v['publications']['with_matching_approval']}/{v['publications']['checked']} yayının v0.5.5 hash'iyle eşleşen onayı var."
        + (f" Eşleşmeyen: {', '.join(v['publications']['failures'])}" if v["publications"]["failures"] else ""),
        f"- Aktif yayın: {v['active_pages']['count']} sayfa açılabiliyor; {v['active_pages']['claims_linked']}/{v['active_pages']['claims']} iddia kanıtına bağlı.",
        f"- Silinmiş/geri çekilmiş: {v['deleted_hidden']['withdrawn_pages']} geri çekilmiş sayfa, {v['deleted_hidden']['deleted_change_pages']} silinmiş kayıt sayfası, {v['deleted_hidden']['deleted_sources']} silinmiş kaynak; aktif görünümde görünen: {len(v['deleted_hidden']['visible_in_active_views'])}.",
        f"- Sağlayıcı anahtarları: {v['provider_secrets']['reencrypted']}/{v['provider_secrets']['providers']} v2 ana anahtarıyla yeniden şifrelendi; düz metin hiçbir dosyaya veya loga yazılmadı.",
        f"- Örnek mentor soruları: {v['mentor_sample']['state']} — {v['mentor_sample']['reason']}",
        "",
        "## Notlar",
        "",
        *([f"- {n}" for n in report["notes"]] or ["- Yok"]),
        "",
        "## Yarım kalan görevler (iptal edildi)",
        "",
        *([f"- {j['title'] or j['id']} (eski durum: {j['state']})" for j in report["cancelled_jobs"]] or ["- Yok"]),
        "",
        "## Aktarılmayan ayarlar",
        "",
        *([f"- `{k}`" for k in report["not_imported_settings"]] or ["- Yok"]),
        "",
    ]
    return "\n".join(lines)


def _report_fingerprint(report: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


# ------------------------------------------------------------------ uygulama


def _require_empty(db: Any) -> None:
    humans = db.scalar(select(func.count()).select_from(User).where(User.kind == "human"))
    projects = db.scalar(select(func.count()).select_from(Project))
    if humans or projects:
        raise ImportRefused("TARGET_NOT_EMPTY", "Hedef veritabanı boş değil (kullanıcı veya proje var). Aktarım yalnız boş bir v2 veritabanına yapılır.")


def _existing_worker(db: Any) -> uuid.UUID | None:
    return db.scalar(select(User.id).where(User.kind == "worker", User.username == "metis-worker"))


def _stage_blobs(blobs: dict[str, bytes]) -> Path:
    root = get_settings().blob_dir
    root.mkdir(parents=True, exist_ok=True)
    staging = root.parent / f".import-{uuid.uuid4().hex}"
    for digest, data in blobs.items():
        target = blob_path(digest, staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ImportRefused("HASH_MISMATCH", f"Geçici blob doğrulanamadı: {digest}")
    return staging


def _promote_blobs(staging: Path, digests: list[str]) -> None:
    for digest in digests:
        target = blob_path(digest)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(blob_path(digest, staging), target)
    shutil.rmtree(staging, ignore_errors=True)


def _insert_plan(db: Any, plan: Plan) -> None:
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    unknown = set(plan.rows) - set(tables)
    if unknown:
        raise VerificationFailed(f"bilinmeyen hedef tablolar: {sorted(unknown)}")
    for table in Base.metadata.sorted_tables:
        rows = plan.rows.get(table.name)
        if rows:
            for start in range(0, len(rows), 500):
                db.execute(insert(table), rows[start : start + 500])
    for name, ident, values in plan.updates:
        table = tables[name]
        if not set(values) <= {c for t, c in DEFERRED_FK if t == name}:
            raise VerificationFailed(f"beklenmeyen güncelleme: {name} {sorted(values)}")
        db.execute(update(table).where(table.c.id == ident).values(**values))


def _db_verify(db: Any, plan: Plan, verification: dict[str, Any]) -> None:
    """Yazılan veriyi gerçek servislerle doğrular; plan doğrulamasıyla birebir aynı sonucu bekler."""
    from metis.modules.knowledge.service import page_detail
    from metis.modules.search.index import index_pages

    expected = {a["page_id"]: a for a in verification["active_pages"]["pages"]}
    stewards: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for m in plan.rows["project_members"]:
        if m["role"] == "steward":
            stewards[m["project_id"]].append(m["user_id"])
    seen: dict[str, dict] = {}
    for project in db.scalars(select(Project)).all():
        if not project.active_publication_id:
            continue
        rows = db.scalars(select(PublicationPage.page_id).where(PublicationPage.publication_id == project.active_publication_id)).all()
        active = []
        for page_id in rows:
            if str(page_id) not in expected:
                continue
            active.append(page_id)
            detail = None
            for uid in stewards.get(project.id, []):
                user = db.get(User, uid)
                try:
                    detail = page_detail(db, user, page_id)
                    break
                except AppError:
                    continue
            if detail is None:
                raise VerificationFailed(f"aktif sayfa açılamadı: {page_id}")
            claims = detail.revision.claims
            seen[str(page_id)] = {"claims": len(claims), "claims_linked": sum(1 for c in claims if c.evidence)}
        index_pages(db, project.id, project.active_publication_id, set(active))
    for pid, exp in expected.items():
        got = seen.get(pid)
        if got is None or got["claims"] != exp["claims"] or got["claims_linked"] != exp["claims_linked"]:
            raise VerificationFailed(f"DB doğrulaması planla uyuşmuyor: sayfa {pid}: beklenen {exp}, bulunan {got}")


def _apply(plan: Plan, report: dict[str, Any], report_md: str, run_id: uuid.UUID, started: datetime) -> None:
    staging = _stage_blobs(plan.blobs)
    try:
        with transaction() as db:
            _require_empty(db)
            _insert_plan(db, plan)
            db.flush()
            _db_verify(db, plan, report["verification"])
            audit(db, None, "legacy_import", "system", run_id, source_sha256=report["source_sha256"], target_counts=report["target_counts"], legacy=True)
            db.add(LegacyImportRun(id=run_id, started_at=started, finished_at=datetime.now(UTC), source_sha256=report["source_sha256"], mode="apply", report=report, report_md=report_md, state="completed"))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _promote_blobs(staging, sorted(plan.blobs))


def run_import(path: Path, password: str, *, dry_run: bool, report_dir: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    started = datetime.now(UTC)
    mode = "dry_run" if dry_run else "apply"
    try:
        backup = open_backup(Path(path), password)
        with transaction() as db:
            _require_empty(db)
            worker = _existing_worker(db)
        plan = build_plan(backup, now or started, existing_worker=worker)
        verification = verify_plan(plan, backup)
        report = build_report(plan, backup, verification)
        if not report["verification_ok"]:
            raise VerificationFailed("doğrulama başarısız: " + json.dumps({k: verification[k] for k in ("publications", "deleted_hidden")}, ensure_ascii=False)[:400])
        md = report_markdown(report, mode)
        run_id = uuid.uuid4()
        if dry_run:
            with transaction() as db:
                db.add(LegacyImportRun(id=run_id, started_at=started, finished_at=datetime.now(UTC), source_sha256=backup.sha256, mode="dry_run", report=report, report_md=md, state="completed"))
        else:
            _apply(plan, report, md, run_id, started)
    except ImportRefused as exc:
        log.warning("legacy import refused", extra={"code": exc.code})
        return {"ok": False, "code": exc.code, "summary": f"Aktarım reddedildi: {exc.message} {NOTHING_CHANGED}"}
    except (VerificationFailed, AppError) as exc:
        log.error("legacy import failed", extra={"error": type(exc).__name__})
        return {"ok": False, "code": "IMPORT_FAILED", "summary": f"Aktarım başarısız: {exc} {NOTHING_CHANGED}"}
    except Exception as exc:  # noqa: BLE001 — rollback zaten yapıldı; kullanıcıya dürüst özet
        log.exception("legacy import failed")
        return {"ok": False, "code": "IMPORT_FAILED", "summary": f"Aktarım başarısız ({type(exc).__name__}). {NOTHING_CHANGED}"}
    paths = {}
    if report_dir:
        report_dir.mkdir(parents=True, exist_ok=True)
        stem = f"import-v1-{mode}-{started.strftime('%Y%m%d-%H%M%S')}"
        (report_dir / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (report_dir / f"{stem}.md").write_text(md, encoding="utf-8")
        paths = {"json": str(report_dir / f"{stem}.json"), "md": str(report_dir / f"{stem}.md")}
    counts = report["target_counts"]
    summary = (
        f"{'Deneme (dry-run) tamamlandı — veri yazılmadı' if dry_run else 'Aktarım tamamlandı'}. "
        f"{counts.get('users', 0)} kullanıcı satırı, {counts.get('projects', 0)} proje, {counts.get('pages', 0)} sayfa, "
        f"{counts.get('source_revisions', 0)} kaynak revizyonu, {len(report['skipped'])} atlanan kayıt. "
        f"Doğrulama geçti. Rapor parmak izi {_report_fingerprint(report)[:12]}."
    )
    return {"ok": True, "run_id": str(run_id), "mode": mode, "report": report, "report_md": md, "paths": paths, "fingerprint": _report_fingerprint(report), "summary": summary}
