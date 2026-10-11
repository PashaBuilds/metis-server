"""v0.5.5 → v2 eşlemesi (docs/adr/v2-ADR-002-legacy-import.md).

Tüm dönüşüm bellekte yapılır; dry-run ve apply aynı planı üretir. v0.5.5 UUID'leri korunur; yeni satırlar
için deterministik uuid5 kullanılır (aynı yedek → aynı plan → aynı rapor). İçe aktarma yeni onay/yayın üretmez.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from metis.core.security import decrypt_legacy_v1_secret, encrypt_secret, load_master_key
from metis.core.util import hash_json
from metis.legacy_import.archive import LegacyBackup
from metis.modules.scopes.semantics import DIMENSIONS, WILDCARD, normalize_scope

NS = uuid.UUID("6f7c2c1e-6d0a-4c2b-9a8e-6d6574697332")
ROLES = {"reader", "contributor", "reviewer", "steward"}
SOURCE_KINDS = {"note", "code", "document", "image", "table", "test"}
PAGE_KINDS = {"concept", "component", "procedure", "decision", "incident", "validation", "table", "learning_path"}
CLAIM_KINDS = {"design_intent", "observed_behavior", "tested_result", "expert_statement", "hypothesis", "derived_calculation"}
SUPPORTS = {"supported", "partial", "conflicting", "unsupported", "not_reviewed"}
PREDICATES = {"depends_on", "implements", "verified_by", "prerequisite_for", "explains", "part_of", "supersedes"}
CHANGE_STATES = {"draft", "in_review", "approved", "rejected", "published", "superseded"}
DECISIONS = {"approved": "approve", "approve": "approve", "changes_requested": "request_changes", "request_changes": "request_changes", "rejected": "reject", "reject": "reject"}
FINDING_KINDS = {"conflict", "source_changed", "review_due", "broken_ref", "missing_owner"}
JOB_KIND = {"ingest_source": "prepare_draft", "propose_wiki_update": "prepare_draft", "prepare_draft": "prepare_draft", "refine_draft": "refine_draft", "maintenance_review": "audit_pool", "review_conflict": "audit_pool", "suggest_relations": "audit_pool"}
DIM_ALIASES = {"domain": "domain", "yatt": "yatt", "yatt_group": "yatt", "card": "kart", "kart": "kart", "hardware": "kart", "project": "proje", "proje": "proje", "platform": "proje"}
WORKER_ID = uuid.uuid5(NS, "metis-worker")
NON_IMPORTED_SETTINGS_PREFIXES = ("scope-catalog:", "conflict-case:", "resolution-change:", "successor:", "maintenance-schedule:", "preparation-auto:", "work-change:", "dataset:", "routing-selection:")


def nid(*parts: object) -> uuid.UUID:
    return uuid.uuid5(NS, "|".join(str(p) for p in parts))


def U(v: Any) -> uuid.UUID | None:  # noqa: N802
    if v in (None, ""):
        return None
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError):
        return None


def ts(v: Any, fallback: datetime) -> datetime:
    if isinstance(v, int | float) and v > 0:
        return datetime.fromtimestamp(v, UTC)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=UTC)
        except ValueError:
            pass
    return fallback


LOCATOR_PAGE = re.compile(r"sayfa\s*(\d+)", re.IGNORECASE)


def parse_locator(text: str) -> dict:
    t = (text or "").strip()
    if not t:
        return {}
    m = LOCATOR_PAGE.search(t)
    if m and re.fullmatch(r"(?:PDF\s*[·:-]\s*)?sayfa\s*\d+", t, re.IGNORECASE):
        return {"page": int(m.group(1))}
    if m:
        return {"page": int(m.group(1)), "raw": t}
    return {"raw": t}


@dataclass
class Plan:
    rows: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    updates: list[tuple[str, uuid.UUID, dict]] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    not_imported_settings: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    cancelled_jobs: list[dict] = field(default_factory=list)
    blobs: dict[str, bytes] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)

    def add(self, table: str, row: dict) -> None:
        self.rows[table].append(row)

    def skip(self, table: str, ident: Any, reason: str) -> None:
        self.skipped.append({"table": table, "id": str(ident), "reason": reason})


def build_plan(backup: LegacyBackup, now: datetime, existing_worker: uuid.UUID | None = None) -> Plan:  # noqa: C901
    worker_id = existing_worker or WORKER_ID
    t = backup.tables
    plan = Plan(blobs=dict(backup.blobs))
    plan.source_counts = {k: len(v) for k, v in sorted(t.items())}
    v2_key = load_master_key()

    # -------------------------------------------------------------- kimlikler
    humans: set[uuid.UUID] = set()
    workers: set[uuid.UUID] = set()
    for row in t["identities"]:
        iid = U(row.get("id"))
        if iid is None:
            plan.skip("identities", row.get("id"), "geçersiz kimlik")
            continue
        if row.get("kind", "human") == "human":
            humans.add(iid)
            plan.add("users", {"id": iid, "username": row["username"], "display_name": row.get("name") or row["username"], "password_hash": row.get("password") or "", "kind": "human", "is_admin": bool(row.get("admin")), "active": bool(row.get("active", True)), "must_change_password": False, "created_at": now})
        else:
            workers.add(iid)
            plan.skip("identities", iid, "worker/bot kimliği aktarılmaz; tek metis-worker kimliğine bağlandı")
    if existing_worker is None:
        plan.add("users", {"id": worker_id, "username": "metis-worker", "display_name": "Metis", "password_hash": "", "kind": "worker", "is_admin": False, "active": True, "must_change_password": False, "created_at": now})

    def person(v: Any) -> uuid.UUID:
        u = U(v)
        if u in humans:
            return u  # type: ignore[return-value]
        return worker_id

    for row in t["credentials"]:
        plan.skip("credentials", row.get("digest", "")[:8] + "…", "oturumlar taşınmaz; herkes yeniden giriş yapar")

    # -------------------------------------------------------------- projeler, üyelik
    projects: dict[uuid.UUID, dict] = {}
    for row in t["projects"]:
        pid = U(row["id"])
        projects[pid] = row  # type: ignore[index]
        plan.add("projects", {"id": pid, "name": row["name"], "description": row.get("description", ""), "is_demo": bool(row.get("demo")), "review_policy": "independent" if row.get("independent_review", True) else "owner_review", "review_interval_days": int(row.get("review_days") or 90), "active_publication_id": None, "created_at": now})
        if row.get("publication_id"):
            plan.updates.append(("projects", pid, {"active_publication_id": U(row["publication_id"])}))  # type: ignore[arg-type]
        if not row.get("independent_review", True):
            plan.notes.append(f"«{row['name']}» projesi owner_review politikasıyla aktarıldı (pilot geçmişi korunur; yönetici değiştirebilir).")
    for row in t["memberships"]:
        uid, pid = U(row["identity_id"]), U(row["project_id"])
        if uid not in humans:
            plan.skip("memberships", f"{pid}/{uid}", "worker üyeliği aktarılmaz")
            continue
        for role in sorted(set(row.get("roles") or [])):
            if role in ROLES:
                plan.add("project_members", {"project_id": pid, "user_id": uid, "role": role})
            else:
                plan.skip("memberships", f"{pid}/{uid}/{role}", "bilinmeyen rol")

    # -------------------------------------------------------------- kapsam kataloğu
    catalog: dict[tuple[uuid.UUID, str, str], dict] = {}
    settings = {s["key"]: s.get("value") for s in t["settings"]}

    def add_scope(pid: uuid.UUID, dim: str, value: str, deleted: bool = False, origin: str = "katalog") -> None:
        value = str(value).strip()
        if not value or value == WILDCARD or dim not in DIMENSIONS:
            return
        key = (pid, dim, value.casefold())
        if key in catalog:
            if not deleted:
                catalog[key]["deleted_at"] = None
            return
        catalog[key] = {"id": nid("scope", pid, dim, value.casefold()), "project_id": pid, "dimension": dim, "value": value, "created_at": now, "created_by": None, "deleted_at": now if deleted else None, "deleted_by": None, "_origin": origin}

    for key, value in settings.items():
        if not key.startswith("scope-catalog:"):
            continue
        pid = U(key.split(":", 1)[1])
        if pid not in projects or not isinstance(value, dict):
            plan.skip("settings", key, "kapsam kataloğu projesi bulunamadı veya biçim tanınmadı")
            continue
        deleted_vals = value.get("deleted") or value.get("tombstones") or {}
        for raw_dim, vals in value.items():
            dim = DIM_ALIASES.get(raw_dim)
            if dim is None:
                continue
            for v in vals if isinstance(vals, list) else [vals]:
                add_scope(pid, dim, v.get("value") if isinstance(v, dict) else v)  # type: ignore[arg-type]
        if isinstance(deleted_vals, dict):
            for raw_dim, vals in deleted_vals.items():
                dim = DIM_ALIASES.get(raw_dim)
                for v in vals if dim else []:
                    add_scope(pid, dim, v, deleted=True)  # type: ignore[arg-type]
        for item in value.get("values", []) if isinstance(value.get("values"), list) else []:
            dim = DIM_ALIASES.get(item.get("dimension", ""))
            if dim:
                add_scope(pid, dim, item.get("value", ""), deleted=bool(item.get("deleted")))
    for pid, row in projects.items():
        if row.get("domain"):
            add_scope(pid, "domain", row["domain"], origin="proje alanı")

    # -------------------------------------------------------------- kaynaklar
    sources: dict[uuid.UUID, dict] = {}
    for row in t["sources"]:
        sid = U(row["id"])
        sources[sid] = row  # type: ignore[index]
        kind = row.get("kind") if row.get("kind") in SOURCE_KINDS else "note"
        if kind != row.get("kind"):
            plan.notes.append(f"Kaynak {sid}: bilinmeyen tür {row.get('kind')!r} → note")
        plan.add("sources", {"id": sid, "project_id": U(row["project_id"]), "owner_id": person(row["owner_id"]), "title": row["title"], "kind": kind, "current_revision_no": int(row.get("current") or 1), "created_at": now, "deleted_at": now if row.get("withdrawn") else None, "deleted_by": None})
        for uid in row.get("acl") or []:
            if U(uid) in humans:
                plan.add("source_acl", {"source_id": sid, "user_id": U(uid)})
            else:
                plan.skip("sources.acl", f"{sid}/{uid}", "ACL kullanıcısı bulunamadı")
    revisions: dict[uuid.UUID, dict] = {}
    for row in t["source_revisions"]:
        rid = U(row["id"])
        src = sources.get(U(row["source_id"]))  # type: ignore[arg-type]
        if src is None:
            plan.skip("source_revisions", rid, "kaynağı yok")
            continue
        meta = dict(row.get("metadata_json") or {})
        scope = normalize_scope(meta.pop("scope", {}))
        pid = U(src["project_id"])
        for dim in DIMENSIONS:
            for v in scope[dim]:
                add_scope(pid, dim, v, origin="kaynak kapsamı")  # type: ignore[arg-type]
        revisions[rid] = {**row, "_scope": scope}  # type: ignore[index]
        plan.add(
            "source_revisions",
            {
                "id": rid, "source_id": U(row["source_id"]), "number": int(row["number"]), "sha256": row["hash"], "media_type": row.get("media_type") or "text/plain",
                "filename": row.get("filename") or "kaynak.txt", "size_bytes": len(backup.blobs.get(row["hash"], b"")), "text": row.get("text") or "",
                "meta": {**meta, "legacy": True}, "scope": scope, "extraction": row.get("extraction") if row.get("extraction") in ("complete", "partial", "annotation_only") else "partial",
                "extractor_version": str(meta.get("extractor") or "v0.5.5"), "author_id": person(meta.get("author_id") or src["owner_id"]), "created_at": ts(row.get("created_at"), now),
            },
        )
    evidence: dict[uuid.UUID, dict] = {}
    for row in t["evidence"]:
        eid = U(row["id"])
        rev = revisions.get(U(row["source_revision_id"]))  # type: ignore[arg-type]
        if rev is None:
            plan.skip("evidence", eid, "kaynak revizyonu yok")
            continue
        text = rev.get("text") or ""
        excerpt = row.get("excerpt") or ""
        pos = text.find(excerpt) if excerpt else -1
        evidence[eid] = {**row, "_text": text}  # type: ignore[index]
        plan.add("evidence", {"id": eid, "source_revision_id": U(row["source_revision_id"]), "locator": parse_locator(row.get("locator", "")), "excerpt": excerpt, "char_start": pos if pos >= 0 else None, "char_end": pos + len(excerpt) if pos >= 0 else None, "created_at": now})

    # -------------------------------------------------------------- sayfalar ve revizyonlar
    page_rows = {U(p["id"]): p for p in t["pages"]}
    revs_by_page: dict[uuid.UUID, dict[int, uuid.UUID]] = defaultdict(dict)
    page_rev_v2_hash: dict[uuid.UUID, str] = {}
    non_verbatim = 0
    for row in sorted(t["page_revisions"], key=lambda r: (r["page_id"], r["number"])):
        rid, pid = U(row["id"]), U(row["page_id"])
        if pid not in page_rows:
            plan.skip("page_revisions", rid, "sayfası yok")
            continue
        page = page_rows[pid]
        scope = normalize_scope(row.get("scope"))
        for dim in DIMENSIONS:
            for v in scope[dim]:
                add_scope(U(page["project_id"]), dim, v, origin="sayfa kapsamı")  # type: ignore[arg-type]
        claims_payload, claim_rows, ce_rows = [], [], []
        for ord_, c in enumerate(row.get("claims") or [], start=1):
            cid = nid("claim", rid, ord_)
            statement = str(c.get("statement", "")).strip() or "(boş iddia)"
            kind = c.get("kind") if c.get("kind") in CLAIM_KINDS else "expert_statement"
            support = c.get("support") if c.get("support") in SUPPORTS else "not_reviewed"
            links = []
            for e in c.get("evidence_ids") or []:
                ev = evidence.get(U(e))  # type: ignore[arg-type]
                if ev is None:
                    plan.skip("claims.evidence_ids", f"{rid}#{ord_}", "kanıt bulunamadı")
                    continue
                verbatim = statement in (ev.get("excerpt") or "")
                if not verbatim:
                    non_verbatim += 1
                quote = statement if verbatim else (ev.get("excerpt") or "")[:8000]
                links.append({"evidence_id": str(U(e)), "quote": quote})
                ce_rows.append({"claim_id": cid, "evidence_id": U(e), "quote": quote})
            claim_rows.append({"id": cid, "page_revision_id": rid, "ord": ord_, "statement": statement, "kind": kind, "support": support})
            claims_payload.append({"statement": statement, "kind": kind, "support": support, "evidence": sorted(links, key=lambda x: (x["evidence_id"], x["quote"]))})
        kind = row.get("kind") if row.get("kind") in PAGE_KINDS else "concept"
        content = {"title": row["title"], "summary": row.get("summary") or "", "body_md": row.get("body") or "", "kind": kind, "scope": scope, "unknowns": list(row.get("unknowns") or []), "aliases": [], "claims": claims_payload}
        v2hash = hash_json(content)
        page_rev_v2_hash[rid] = v2hash  # type: ignore[index]
        revs_by_page[pid][int(row["number"])] = rid  # type: ignore[index]
        plan.add("page_revisions", {"id": rid, "page_id": pid, "number": int(row["number"]), "title": row["title"], "summary": content["summary"], "body_md": content["body_md"], "kind": kind, "scope": scope, "unknowns": content["unknowns"], "aliases": [], "author_id": person(row.get("author_id")), "hash": v2hash, "legacy_hash": row.get("hash"), "created_at": ts(row.get("created_at"), now)})
        for c in claim_rows:
            plan.add("claims", c)
        for c in ce_rows:
            plan.add("claim_evidence", c)
    if non_verbatim:
        plan.notes.append(f"{non_verbatim} iddia-kanıt bağı kanıt metninde birebir geçmiyor; bu iddialar mentor tarafından kullanılmaz (alıntı olarak kanıt metni saklandı).")
    for pid, row in page_rows.items():
        revs = revs_by_page.get(pid, {})  # type: ignore[arg-type]
        latest = revs.get(int(row.get("current") or 0)) or (revs[max(revs)] if revs else None)
        latest_row = next((r for r in plan.rows["page_revisions"] if r["id"] == latest), None)
        plan.add("pages", {"id": pid, "project_id": U(row["project_id"]), "kind": latest_row["kind"] if latest_row else "concept", "owner_id": person(row["owner_id"]), "lifecycle": row.get("lifecycle") if row.get("lifecycle") in ("active", "deprecated", "withdrawn") else "active", "freshness": row.get("freshness") if row.get("freshness") in ("current", "review_due", "dependency_changed", "unknown") else "unknown", "current_revision_no": int(row.get("current") or 0), "published_revision_id": None, "published_at": None, "reviewed_at": None, "created_at": now, "deleted_at": None, "deleted_by": None})
        if row.get("published_revision"):
            plan.updates.append(("pages", pid, {"published_revision_id": U(row["published_revision"])}))  # type: ignore[arg-type]

    # -------------------------------------------------------------- işler (jobs)
    job_ids: set[uuid.UUID] = set()
    change_requester: dict[uuid.UUID, uuid.UUID] = {}
    change_job: dict[uuid.UUID, uuid.UUID] = {}
    for row in t["work_items"]:
        jid = U(row["id"])
        state = row.get("state", "")
        if state == "completed":
            new_state = "completed"
        elif state in ("budget_exceeded",):
            new_state = "budget_exceeded"
        elif state in ("queued", "leased", "running", "awaiting_input", "waiting"):
            new_state = "cancelled"
            plan.cancelled_jobs.append({"id": str(jid), "title": row.get("title", ""), "state": state})
        else:
            new_state = "failed"
        requester = person(row["requester_id"])
        if requester == worker_id:
            plan.skip("work_items", jid, "istekte bulunan kullanıcı yok")
            continue
        job_ids.add(jid)  # type: ignore[arg-type]
        plan.add("jobs", {"id": jid, "project_id": U(row["project_id"]), "requester_id": requester, "kind": JOB_KIND.get(row.get("kind", ""), "audit_pool"), "title": row.get("title") or "v0.5.5 görevi", "inputs": {"legacy_kind": row.get("kind"), **{k: v for k, v in (row.get("inputs") or {}).items() if k in ("source_revision_ids", "instructions", "model_id")}}, "input_fingerprint": "", "state": new_state, "priority": 50, "model_id": None, "worker_id": None, "fence": int(row.get("fence") or 0), "attempt": int(row.get("attempt") or 0), "lease_until": None, "checkpoint": {"legacy": True, "report": (row.get("checkpoint") or {}).get("reports", {})}, "budget_used": {}, "result_summary": "v0.5.5'ten aktarıldı" + (" (yarım kalan görev iptal edildi)" if new_state == "cancelled" else ""), "error_code": (row.get("checkpoint") or {}).get("error"), "created_at": ts(row.get("created_at"), now), "updated_at": now, "finished_at": now if new_state != "completed" else ts(row.get("created_at"), now), "legacy": True})
        for i, m in enumerate(row.get("messages") or []):
            plan.add("job_messages", {"id": nid("jobmsg", jid, i), "job_id": jid, "role": "user" if m.get("kind") == "response" else "metis", "body": str(m.get("text", ""))[:4000] or "—", "detail": {"legacy_kind": m.get("kind")}, "author_id": None, "created_at": ts(m.get("at"), now), "answered_at": None})
        for out in row.get("outputs") or []:
            change_requester[U(out)] = requester  # type: ignore[index]
            change_job[U(out)] = jid  # type: ignore[index]

    # -------------------------------------------------------------- değişiklik setleri, onaylar, yayınlar
    changes: dict[uuid.UUID, dict] = {U(c["id"]): c for c in t["change_sets"]}  # type: ignore[misc]
    resolution_changes = {U(k.split(":", 1)[1]): v for k, v in settings.items() if k.startswith("resolution-change:")}
    successors = {U(k.split(":", 1)[1]): U((v or {}).get("change_id")) for k, v in settings.items() if k.startswith("successor:")}
    relation_revs: dict[uuid.UUID, uuid.UUID] = {}
    change_v2_hash: dict[uuid.UUID, str] = {}
    for cid, row in changes.items():
        author = person(row["author_id"])
        state = row.get("state", "draft")
        deleted = state == "deleted"
        v2_state = state if state in CHANGE_STATES else ("draft" if state in ("deleted", "changes_requested") else "draft")
        items = []
        for rev_id in row.get("revisions") or []:
            rid = U(rev_id)
            prow = next((r for r in plan.rows["page_revisions"] if r["id"] == rid), None)
            if prow is None:
                plan.skip("change_sets.revisions", f"{cid}/{rev_id}", "revizyon yok")
                continue
            base_no = int((row.get("bases") or {}).get(str(prow["page_id"]), 0) or 0)
            base_id = revs_by_page.get(prow["page_id"], {}).get(base_no) if base_no else None
            items.append({"id": nid("item", cid, rid), "change_set_id": cid, "page_id": prow["page_id"], "base_revision_id": base_id, "base_revision_no": base_no, "proposed_revision_id": rid, "action": "upsert"})
        rel_items = []
        for i, rel in enumerate(row.get("relations") or []):
            rel_id = U(rel.get("id")) or nid("relation", cid, i)
            subject, obj = U(rel.get("subject")), U(rel.get("object"))
            predicate = rel.get("predicate") or rel.get("type") or rel.get("relation") or "explains"
            if predicate not in PREDICATES:
                plan.notes.append(f"İlişki {rel_id}: bilinmeyen tür {predicate!r} → explains")
                predicate = "explains"
            if subject not in page_rows or obj not in page_rows:
                plan.skip("change_sets.relations", rel_id, "ilişki sayfası yok")
                continue
            rr_id = nid("relrev", rel_id, cid)
            relation_revs[rel_id] = rr_id  # type: ignore[index]
            plan.add("relations", {"id": rel_id, "project_id": U(row["project_id"]), "current_revision_no": 1, "published_revision_id": None, "created_at": now, "deleted_at": None})
            plan.add("relation_revisions", {"id": rr_id, "relation_id": rel_id, "number": 1, "subject_page_id": subject, "predicate": predicate, "object_page_id": obj, "scope": normalize_scope(rel.get("scope")), "rationale": str(rel.get("rationale") or rel.get("reason") or ""), "review_state": "accepted" if state == "published" else "proposed", "author_id": author, "created_at": ts(row.get("created_at"), now)})
            for e in rel.get("evidence_ids") or []:
                if U(e) in evidence:
                    plan.add("relation_revision_evidence", {"relation_revision_id": rr_id, "evidence_id": U(e), "quote": ""})
            rel_items.append({"id": nid("crel", cid, rel_id), "change_set_id": cid, "relation_id": rel_id, "base_revision_id": None, "proposed_revision_id": rr_id, "action": "upsert"})
        hash_payload = {
            "kind": "resolution" if cid in resolution_changes else "edit",
            "items": [{"page": i["page_id"], "base": i["base_revision_id"], "action": "upsert", "proposed": i["proposed_revision_id"], "hash": page_rev_v2_hash.get(i["proposed_revision_id"])} for i in sorted(items, key=lambda x: str(x["page_id"]))],
            "relations": [{"relation": r["relation_id"], "base": None, "proposed": r["proposed_revision_id"], "action": "upsert"} for r in sorted(rel_items, key=lambda x: str(x["relation_id"]))],
        }
        v2hash = hash_json(hash_payload)
        change_v2_hash[cid] = v2hash
        origin = "metis" if (U(row["author_id"]) in workers or cid in resolution_changes or cid in change_job) else "human"
        requester = change_requester.get(cid) or (person((resolution_changes.get(cid) or {}).get("requester_id")) if cid in resolution_changes else None)
        plan.add("change_sets", {"id": cid, "project_id": U(row["project_id"]), "author_id": author, "requester_id": requester if origin == "metis" and requester != worker_id else None, "origin": origin, "job_id": change_job.get(cid) if change_job.get(cid) in job_ids else None, "kind": hash_payload["kind"], "summary": row.get("summary") or "", "state": v2_state, "hash": v2hash, "legacy_hash": row.get("hash"), "predecessor_id": None, "source_answer_id": None, "detail": {"legacy": True, "legacy_state": state}, "created_at": ts(row.get("created_at"), now), "updated_at": ts(row.get("created_at"), now), "submitted_at": None, "published_at": None, "deleted_at": now if deleted else None, "deleted_by": None})
        for i in items:
            plan.add("change_set_items", i)
        for r in rel_items:
            plan.add("change_set_relations", r)
        if cid in change_job and change_job[cid] in job_ids:
            plan.add("job_outputs", {"job_id": change_job[cid], "change_set_id": cid})
    for original, successor in successors.items():
        if original in changes and successor in changes:
            plan.updates.append(("change_sets", successor, {"predecessor_id": original}))  # type: ignore[arg-type]

    for row in t["approvals"]:
        cid = U(row["change_id"])
        ch = changes.get(cid)  # type: ignore[arg-type]
        if ch is None:
            plan.skip("approvals", row["id"], "değişiklik seti yok")
            continue
        matches = row.get("hash") == ch.get("hash")
        review_hash = change_v2_hash[cid] if matches else hash_json({"legacy_approval_hash": row.get("hash")})  # type: ignore[index]
        policy = {"owner_review-v1": "owner_review", "independent-v1": "independent"}.get(row.get("policy", ""), str(row.get("policy") or "independent"))[:40]
        plan.add("reviews", {"id": U(row["id"]), "change_set_id": cid, "hash": review_hash, "reviewer_id": person(row["reviewer_id"]), "decision": DECISIONS.get(row.get("decision", ""), "request_changes"), "reason": row.get("reason") or "", "evidence_checked": False, "policy": policy, "legacy_hash": row.get("hash"), "created_at": ts(row.get("created_at"), now)})

    pubs = sorted(t["publications"], key=lambda p: (str(p.get("project_id")), str(p.get("created_at", "")), str(p["id"])))
    seq: Counter = Counter()
    first_published: dict[uuid.UUID, datetime] = {}
    for row in pubs:
        pub_id, pid = U(row["id"]), U(row["project_id"])
        seq[pid] += 1
        created = ts(row.get("created_at"), now)
        plan.add("publications", {"id": pub_id, "project_id": pid, "change_set_id": U(row.get("change_id")) if U(row.get("change_id")) in changes else None, "kind": "legacy", "created_by": None, "seq": seq[pid], "created_at": created})
        manifest = row.get("manifest") or {}
        for page_id, rev_id in (manifest.get("pages") or {}).items():
            if U(page_id) in page_rows and any(r["id"] == U(rev_id) for r in plan.rows["page_revisions"]):
                plan.add("publication_pages", {"publication_id": pub_id, "page_id": U(page_id), "revision_id": U(rev_id)})
                first_published.setdefault(U(rev_id), created)  # type: ignore[arg-type]
            else:
                plan.skip("publications.manifest", f"{pub_id}/{page_id}", "yayındaki sayfa revizyonu yok")
        for rel in manifest.get("relations") or []:
            rel_id = U(rel.get("id"))
            if rel_id in relation_revs:
                plan.add("publication_relations", {"publication_id": pub_id, "relation_id": rel_id, "revision_id": relation_revs[rel_id]})
    for page_id, row in page_rows.items():
        rid = U(row.get("published_revision"))
        if rid and rid in first_published:
            plan.updates.append(("pages", page_id, {"published_at": first_published[rid], "reviewed_at": first_published[rid]}))  # type: ignore[arg-type]
    for proj_id, prow in projects.items():
        pub_id = U(prow.get("publication_id"))
        if pub_id:
            for rr in plan.rows["publication_relations"]:
                if rr["publication_id"] == pub_id:
                    plan.updates.append(("relations", rr["relation_id"], {"published_revision_id": rr["revision_id"]}))
            for c in plan.rows["change_sets"]:
                if c["state"] == "published":
                    c["published_at"] = c["created_at"]
        _ = proj_id

    # -------------------------------------------------------------- bulgular, çelişki vakaları
    for row in t["findings"]:
        fid = U(row["id"])
        detail = dict(row.get("detail") or {})
        kind = row.get("kind") if row.get("kind") in FINDING_KINDS else "reported"
        state = "open" if row.get("state", "open") == "open" else "resolved"
        plan.add("findings", {"id": fid, "project_id": U(row["project_id"]), "kind": kind, "severity": row.get("severity") if row.get("severity") in ("low", "medium", "high") else "medium", "state": state, "detail": {**detail, "legacy": True}, "fingerprint": "", "resolution_reason": row.get("reason") or "", "resolved_by": None, "resolved_at": now if state == "resolved" else None, "created_by": None, "created_at": ts(row.get("created_at"), now)})
        for pid in {U(row.get("page_id")), U(detail.get("other_page_id"))}:
            if pid in page_rows:
                plan.add("finding_pages", {"finding_id": fid, "page_id": pid})
    for key, value in settings.items():
        if not key.startswith("conflict-case:") or not isinstance(value, dict):
            continue
        # v0.5.5: anahtar cevap kimliğidir (conflict-case:<answer_id>); bulgu, anlık görüntüdeki iki sayfadan bulunur
        case_id = nid("case", key)
        project_id = U(value.get("project_id"))
        if project_id not in projects:
            plan.skip("settings", key, "çelişki vakasının projesi bulunamadı")
            continue
        snap_pages = {U(p) for p in (value.get("snapshots") or {})}
        finding_id = next((f["id"] for f in plan.rows["findings"] if f["kind"] == "conflict" and f["project_id"] == project_id and {fp["page_id"] for fp in plan.rows["finding_pages"] if fp["finding_id"] == f["id"]} <= snap_pages and snap_pages), None)
        claim_rev = {c["id"]: c["page_revision_id"] for c in plan.rows["claims"]}
        snap_titles = {U(sn.get("revision_id")): str(sn.get("title", "")) for sn in (value.get("snapshots") or {}).values()}
        ev_titles = {str(ce["evidence_id"]): snap_titles[claim_rev[ce["claim_id"]]] for ce in plan.rows["claim_evidence"] if claim_rev.get(ce["claim_id"]) in snap_titles}

        def evidence_title(eid: Any, titles: dict = ev_titles) -> str:
            return titles.get(str(eid), "")

        assessment = value.get("assessment") or {}
        options = list(assessment.get("options") or [])
        state = "resolved" if value.get("state") == "published" else "open"
        plan.add("conflict_cases", {"id": case_id, "project_id": project_id, "finding_id": finding_id, "summary": str(assessment.get("summary", ""))[:2400], "questions": [str(q) for q in assessment.get("questions") or []], "state": state, "model_call_id": None, "created_by": person(value.get("requester_id")), "created_at": ts(value.get("started_at"), now)})
        for i, opt in enumerate(options):
            plan.add("conflict_options", {"id": nid("option", case_id, i), "case_id": case_id, "ord": i, "title": str(opt.get("title", "Seçenek"))[:240], "rationale": str(opt.get("rationale", "")), "prerequisite": str(opt.get("prerequisite", "")), "keep_page_ids": [U(p) for p in opt.get("keep_page_ids") or [] if U(p) in page_rows], "retire_page_ids": [U(p) for p in opt.get("retire_page_ids") or [] if U(p) in page_rows], "evidence": [{"evidence_id": str(e.get("evidence_id")), "quote": str(e.get("quote", "")), "page_title": evidence_title(e.get("evidence_id"))} for e in opt.get("evidence") or []]})
        chosen = value.get("chosen_option")
        change_id = U(value.get("change_id"))
        if change_id in changes and isinstance(chosen, int) and 0 <= chosen < len(options):
            if changes[change_id].get("state") != "published":
                plan.notes.append(f"Çelişki çözüm kaydı {change_id} incelemede aktarıldı: v0.5.5'te geri çekilecek sayfa kayda değil vakaya yazılıydı; v2'de yayımlansa bile karşı sayfa otomatik geri çekilmez. Bilgi sağlığı ekranından çözümü v2 akışıyla yeniden seç.")
            plan.add("conflict_resolutions", {"id": nid("resolution", case_id), "case_id": case_id, "option_id": nid("option", case_id, chosen), "chosen_by": person(value.get("requester_id")), "reason": str(value.get("human_reason") or "") or "v0.5.5 kaydı", "change_set_id": change_id, "created_at": now})
        elif change_id:
            plan.skip("settings", key, "çelişki çözüm kaydı eşleşmedi; vaka seçimsiz aktarıldı")

    # -------------------------------------------------------------- hazırlık çıktıları
    for row in t["extracted_claims"]:
        if U(row.get("source_revision_id")) not in revisions:
            plan.skip("extracted_claims", row["id"], "kaynak revizyonu yok")
            continue
        plan.add("extracted_claims", {"id": U(row["id"]), "project_id": U(row["project_id"]), "source_revision_id": U(row["source_revision_id"]), "job_id": U(row.get("work_id")) if U(row.get("work_id")) in job_ids else None, "fingerprint": row["fingerprint"], "subject": row["subject"][:300], "attribute": row["attribute"][:300], "value": row["value"], "condition": (row.get("scope") or {}).get("condition", ""), "quote": row["quote"], "quote_start": int(row.get("quote_start") or 0), "quote_end": int(row.get("quote_end") or 0), "scope": normalize_scope(row.get("scope")), "state": row.get("state") or "draft", "page_revision_id": U(row.get("page_revision_id")) if any(r["id"] == U(row.get("page_revision_id")) for r in plan.rows["page_revisions"]) else None, "created_at": now})
    for row in t["open_decisions"]:
        if U(row.get("source_revision_id")) not in revisions:
            plan.skip("open_decisions", row["id"], "kaynak revizyonu yok")
            continue
        plan.add("open_decisions", {"id": U(row["id"]), "project_id": U(row["project_id"]), "source_revision_id": U(row["source_revision_id"]), "job_id": U(row.get("work_id")) if U(row.get("work_id")) in job_ids else None, "fingerprint": row["fingerprint"], "description": row["description"], "quote": row["quote"], "quote_start": int(row.get("quote_start") or 0), "quote_end": int(row.get("quote_end") or 0), "state": row.get("state") or "open", "created_at": now})

    # -------------------------------------------------------------- mentor cevapları
    for row in t["answers"]:
        aid = U(row["id"])
        if U(row.get("owner_id")) not in humans:
            plan.skip("answers", aid, "sahibi bulunamadı")
            continue
        res = row.get("result") or {}
        decision = res.get("decision") if res.get("decision") in ("SUPPORTED", "PARTIAL", "NEEDS_SCOPE", "CONFLICTING", "NO_EVIDENCE", "RETRIEVAL_UNAVAILABLE", "MODEL_UNAVAILABLE", "VALIDATION_FAILED") else "VALIDATION_FAILED"
        page_of = {str(b.get("evidence_id")): U(b.get("page_id")) for b in res.get("evidence") or []}
        plan.add("answers", {"id": aid, "owner_id": U(row["owner_id"]), "project_id": U(row["project_id"]), "question": row.get("question") or "", "scope": normalize_scope(row.get("scope")), "level": "short", "decision": decision, "publication_id": U(res.get("publication_id")), "model_id": None, "prompt_version": str(res.get("prompt_version") or "evidence-quotes-v4"), "explanation": [], "explanation_dropped": 0, "timings": res.get("timings_ms") or {}, "detail": {"legacy": True, "related": [], "model": res.get("model")}, "legacy": True, "created_at": ts(row.get("created_at"), now), "deleted_at": None})
        for i, c in enumerate(res.get("claims") or [], start=1):
            if U(c.get("evidence_id")) in evidence:
                plan.add("answer_citations", {"id": nid("cite", aid, i), "answer_id": aid, "ord": i, "claim_id": None, "evidence_id": U(c["evidence_id"]), "page_id": page_of.get(str(c["evidence_id"])), "quote": c.get("quote") or ""})
        fb = row.get("feedback") or {}
        if fb.get("rating") in ("helpful", "not_helpful"):
            plan.add("answer_feedback", {"id": nid("feedback", aid), "answer_id": aid, "user_id": U(row["owner_id"]), "rating": fb["rating"], "comment": str(fb.get("comment", "")), "created_at": now})

    # -------------------------------------------------------------- sağlayıcılar ve modeller
    for row in t["providers"]:
        secret = ""
        if row.get("secret"):
            try:
                plain = decrypt_legacy_v1_secret(row["secret"], backup.master_key)
                secret = encrypt_secret(plain, v2_key)  # düz metin yalnız bellekte; diske/loga yazılmaz
                del plain
            except Exception:  # noqa: BLE001
                plan.notes.append(f"Sağlayıcı «{row.get('name')}» anahtarı çözülemedi; anahtar aktarılmadı, yeniden girilmeli.")
        plan.add("providers", {"id": U(row["id"]), "name": row.get("name") or row.get("base_url"), "base_url": row["base_url"], "secret_enc": secret, "secret_version": int(row.get("secret_version") or (1 if secret else 0)), "secret_updated_at": now if secret else None, "ca_bundle_ref": "", "max_concurrency": int(row.get("concurrency") or 2), "timeout_s": int(row.get("timeout") or 60), "created_at": now, "deleted_at": None})
    for row in t["models"]:
        prov = next((p for p in plan.rows["providers"] if p["id"] == U(row["provider_id"])), None)
        if prov is None:
            plan.skip("models", row["id"], "sağlayıcı yok")
            continue
        plan.add("models", {"id": U(row["id"]), "provider_id": prov["id"], "remote_id": row["remote_id"], "display_name": row.get("name") or row["remote_id"], "enabled": bool(row.get("enabled", True)), "is_fixture": str(row["remote_id"]).startswith("fixture-") and prov["base_url"].startswith(("http://127.0.0.1", "http://localhost")), "transport_profile": {}, "config_version": 1, "failures": 0, "circuit_until": None, "created_at": now, "deleted_at": None})
    if t["models"]:
        plan.notes.append("Model yeterlilikleri aktarılmadı (prompt ve transport değişti); modeller 'test edilmedi' durumunda. Model laboratuvarında probe ve benchmark çalıştır.")
    for name in ("benchmark_runs", "model_calls", "model_cache", "provider_leases", "search_entries", "idempotency"):
        if t[name]:
            plan.skip(name, f"{len(t[name])} satır", "arama indeksi v2'de aktif yayından yeniden kurulur" if name == "search_entries" else "operasyonel veri; aktarılmadı (sayısı raporda)")

    # -------------------------------------------------------------- denetim kaydı
    for row in t["audit_events"]:
        actor = U(row.get("actor_id"))
        plan.add("audit_events", {"id": U(row["id"]) or nid("audit", row.get("created_at"), row.get("operation")), "actor_id": actor if actor in humans else (worker_id if actor in workers else None), "op": str(row.get("operation", ""))[:80], "target_type": "", "target_id": str(row.get("target", ""))[:80], "detail": {**(row.get("detail") or {}), "legacy": True}, "correlation_id": str(row.get("correlation_id", ""))[:64], "created_at": ts(row.get("created_at"), now)})

    # -------------------------------------------------------------- bakım planı (tek zamanlayıcı)
    sched: dict[uuid.UUID, dict] = {}
    for key, value in settings.items():
        if not (key.startswith("maintenance-schedule:") or key.startswith("preparation-auto:")) or not isinstance(value, dict):
            continue
        pid = U(key.split(":", 1)[1])
        if pid not in projects:
            continue
        days = value.get("interval_days") or value.get("days") or (int(value["hours"]) / 24 if value.get("hours") else None) or 7
        days = max(1, int(round(float(days))))
        prev = sched.get(pid)  # type: ignore[arg-type]
        if prev and prev["interval_days"] != days:
            plan.notes.append(f"Proje {pid}: iki eski zamanlayıcı birleşti; daha seyrek olan ({max(days, prev['interval_days'])} gün) seçildi.")
            days = max(days, prev["interval_days"])
        sched[pid] = {"id": nid("schedule", pid), "project_id": pid, "kind": "maintenance", "interval_days": days, "next_run_at": None, "last_run_at": None, "enabled": bool(value.get("enabled", False)) or bool(prev and prev["enabled"]), "model_id": None}  # type: ignore[index]
    for pid in projects:
        sched.setdefault(pid, {"id": nid("schedule", pid), "project_id": pid, "kind": "maintenance", "interval_days": 7, "next_run_at": None, "last_run_at": None, "enabled": False, "model_id": None})
    for s in sched.values():
        plan.add("schedules", s)
    for key in sorted(settings):
        if not key.startswith(NON_IMPORTED_SETTINGS_PREFIXES):
            plan.not_imported_settings.append(key)
    for key in sorted(settings):
        if key.startswith(("work-change:", "dataset:", "routing-selection:")):
            plan.not_imported_settings.append(key)

    for row in catalog.values():
        row.pop("_origin", None)
        plan.add("scope_values", row)
    return plan
