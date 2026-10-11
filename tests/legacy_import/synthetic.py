"""v0.5.5 şemasına uygun sentetik şifreli yedek üretici (v1 kodu çalıştırılmadan).

Biçim ve hash kuralları reference/v0.5.5'ten birebir: deployment/desktop/recovery.py (dış şifreleme, PyCryptodome
AES-GCM 16 bayt nonce), deployment/backup.py (snapshot.zip + manifest), services/api/knowledge.py (`hash_json`,
sayfa revizyonu ve değişiklik seti hash'leri), services/api/security.py (scrypt `salt:hex`, sağlayıcı sırrı
`b64(nonce16‖tag16‖ct)`), services/api/conflict_resolution.py (çelişki vakası ve çözüm kaydı ayarları).

Kapsam: tüm tablo türleri, Türkçe karakterli dosya adları, silinmiş kayıtlar, geri çekilmiş sayfa, çelişki vakası,
owner_review projesi, bitmemiş iş, worker kimliği, iki eski zamanlayıcı (birleşme notu), aktarılmayan ayarlar.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from Crypto.Cipher import AES

MAGIC = b"METISBK1"
NS = uuid.UUID("0b1d6a52-0a55-4f55-8d1e-5e6e7e1c0055")
PASSWORD = "Kurgusal-Yedek-Parola-2026"
OLD_USER_PASSWORD = "Eski-Kurgusal-Parola-1"
PROVIDER_SECRET = "sk-kurgusal-SIR-7f3a9c2e5b1d4a6f8e0c"


def I(name: str) -> str:  # noqa: N802,E743
    return str(uuid.uuid5(NS, name))


def hash_json(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def v1_password_hash(value: str, salt: str = "a1b2c3d4e5f60718293a4b5c6d7e8f90") -> str:
    return salt + ":" + hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def v1_encrypt_secret(secret: str, master: bytes) -> str:
    cipher = AES.new(master, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(secret.encode())
    return base64.b64encode(cipher.nonce + tag + ciphertext).decode()


def scope(card: str = "", project: str = "", domain: list[str] | None = None) -> dict:
    return {
        "platform": project,
        "hardware": card,
        "dimensions": {"domain": domain or ["Gömülü yazılım"], "yatt": [], "card": [card] if card else [], "project": [project] if project else []},
    }


T0 = "2025-11-03T09:00:00+00:00"


def at(minutes: int) -> str:
    return f"2025-11-{3 + minutes // 1440:02d}T{9 + (minutes % 1440) // 60:02d}:{minutes % 60:02d}:00+00:00"


def build_tables(master: bytes) -> tuple[dict[str, list[dict]], dict[str, bytes]]:  # noqa: PLR0915
    t: dict[str, list[dict]] = {}
    blobs: dict[str, bytes] = {}
    P1, P2 = I("p1"), I("p2")
    ayse, mert, selin, worker = I("ayse"), I("mert"), I("selin"), I("worker")
    t["identities"] = [
        {"id": ayse, "name": "Ayşe Kurgu", "username": "ayse.kurgu", "password": v1_password_hash(OLD_USER_PASSWORD), "kind": "human", "admin": True, "active": True},
        {"id": mert, "name": "Mert Örnek", "username": "mert.ornek", "password": v1_password_hash(OLD_USER_PASSWORD, "00112233445566778899aabbccddeeff"), "kind": "human", "admin": False, "active": True},
        {"id": selin, "name": "Selin Çalışkan", "username": "selin.caliskan", "password": v1_password_hash(OLD_USER_PASSWORD, "ffeeddccbbaa99887766554433221100"), "kind": "human", "admin": False, "active": True},
        {"id": worker, "name": "Metis worker", "username": "worker-" + worker[:8], "password": "", "kind": "worker", "admin": False, "active": True},
    ]
    t["credentials"] = []
    t["projects"] = [
        {"id": P1, "name": "Gömülü yazılım bilgi tabanı", "domain": "Gömülü yazılım", "description": "Kurgusal v0.5.5 projesi", "demo": False, "independent_review": True, "review_days": 90, "publication_id": I("pub4")},
        {"id": P2, "name": "Pilot — Atlas kartı", "domain": "Gömülü yazılım", "description": "owner_review pilot projesi", "demo": False, "independent_review": False, "review_days": 60, "publication_id": I("pub5")},
    ]
    t["memberships"] = [
        {"project_id": P1, "identity_id": ayse, "roles": ["steward", "reviewer", "contributor", "reader"]},
        {"project_id": P1, "identity_id": mert, "roles": ["reviewer", "contributor", "reader"]},
        {"project_id": P1, "identity_id": selin, "roles": ["contributor", "reader"]},
        {"project_id": P1, "identity_id": worker, "roles": ["contributor"]},
        {"project_id": P2, "identity_id": ayse, "roles": ["steward", "reviewer", "contributor", "reader"]},
    ]

    # ------------------------------------------------------------- kaynaklar
    sc = scope("VPK120", "Atlas")
    sc2 = scope("", "")
    texts = {
        "s1r1": "UART0 hata ayıklama hızı 115200 baud olarak ayarlanır.\nAkış denetimi kapalıdır.",
        "s1r2": "UART0 hata ayıklama hızı 921600 baud olarak ayarlanır.\nAkış denetimi kapalıdır.",
        "s2r1": "Saha ölçümünde konsol hızı 57600 baud bulundu.\nTablo 2: kablo uzunluğu 3 m.",
        "s3r1": "PCIe bağlantısı Gen2 x4 olarak eğitilir.",
        "s4r1": "Atlas kartında SPI saat bölücü 8'dir.",
    }
    sources = [
        ("s1", P1, ayse, "UART yapılandırma notu", "note", [], 2, False),
        ("s2", P1, mert, "Saha ölçümleri — çalışma", "document", [], 1, False),
        ("s3", P1, ayse, "Eski PCIe notu", "note", [ayse], 1, True),
        ("s4", P2, ayse, "Atlas SPI notu", "note", [], 1, False),
    ]
    t["sources"] = [{"id": I(k), "project_id": p, "owner_id": o, "title": ti, "kind": kd, "acl": acl, "current": cur, "withdrawn": wd} for k, p, o, ti, kd, acl, cur, wd in sources]
    revs = [
        ("s1r1", "s1", 1, "uart_notu.txt", "text/plain", sc),
        ("s1r2", "s1", 2, "uart_notu.txt", "text/plain", sc),
        ("s2r1", "s2", 1, "ölçüm_raporu_çğışİ.txt", "text/plain", sc),
        ("s3r1", "s3", 1, "pcıe_eğitim.txt", "text/plain", sc2),
        ("s4r1", "s4", 1, "spı_bölücü.txt", "text/plain", scope("Atlas-K2", "")),
    ]
    t["source_revisions"] = []
    for k, s, n, fn, mt, sco in revs:
        data = texts[k].encode()
        digest = hashlib.sha256(data).hexdigest()
        blobs[digest] = data
        t["source_revisions"].append({"id": I(k), "source_id": I(s), "number": n, "hash": digest, "media_type": mt, "filename": fn, "text": texts[k], "metadata_json": {"scope": sco, "author_id": ayse, "extractor": "metis-text-v1", "pages": 0}, "extraction": "complete", "created_at": at(n)})
    ev = [
        ("e1", "s1r1", "Satır 1", "UART0 hata ayıklama hızı 115200 baud olarak ayarlanır."),
        ("e2", "s2r1", "PDF · sayfa 3", "Saha ölçümünde konsol hızı 57600 baud bulundu."),
        ("e3", "s1r2", "Satır 1", "UART0 hata ayıklama hızı 921600 baud olarak ayarlanır."),
        ("e4", "s2r1", "PDF · sayfa 4 · tablo 2", "Tablo 2: kablo uzunluğu 3 m."),
        ("e5", "s3r1", "", "PCIe bağlantısı Gen2 x4 olarak eğitilir."),
        ("e6", "s4r1", "Satır 1", "Atlas kartında SPI saat bölücü 8'dir."),
    ]
    t["evidence"] = [{"id": I(k), "source_revision_id": I(r), "locator": loc, "excerpt": ex, "verified": True} for k, r, loc, ex in ev]
    EX = {k: ex for k, _, _, ex in ev}

    # ------------------------------------------------------------- sayfa revizyonları
    t["page_revisions"] = []
    rev_hash: dict[str, str] = {}

    def page_rev(key: str, page: str, number: int, title: str, body: str, evidence: list[str], claims: list[dict], sco: dict, kind: str = "concept", author: str = ayse, unknowns: list[str] | None = None) -> None:
        content = {"title": title, "summary": body.split(".")[0], "body": body, "kind": kind, "scope": sco, "evidence_ids": [I(e) for e in evidence], "claims": claims, "unknowns": unknowns or []}
        h = hash_json(content)
        rev_hash[key] = h
        t["page_revisions"].append({"id": I(key), "page_id": I(page), "number": number, **content, "author_id": author, "hash": h, "created_at": at(10 + number)})

    def claim(statement: str, evidence: list[str], kind: str = "observed_behavior") -> dict:
        return {"statement": statement, "kind": kind, "evidence_ids": [I(e) for e in evidence], "support": "supported"}

    page_rev("pg1r1", "pg1", 1, "Hata ayıklama UART hızı", "UART0 hata ayıklama hızı 115200 baud. Akış denetimi kapalı.", ["e1"], [claim(EX["e1"], ["e1"])], sc)
    page_rev("pg2r1", "pg2", 1, "Konsol baud hızı (saha)", "Sahada konsol 57600 baud ölçüldü.", ["e2", "e4"], [claim(EX["e2"], ["e2"]), claim("Kablo 3 metredir.", ["e4"], "tested_result")], sc, unknowns=["Ölçüm hangi yazılım sürümüyle yapıldı?"])
    page_rev("pg3r1", "pg3", 1, "PCIe bağlantı eğitimi", "PCIe bağlantısı Gen2 x4 olarak eğitilir.", ["e5"], [claim(EX["e5"], ["e5"])], sc2, kind="procedure")
    page_rev("pg4r1", "pg4", 1, "UART akış denetimi", "Akış denetimi kapalıdır.", ["e1"], [claim("Akış denetimi kapalıdır.", ["e1"])], sc, author=selin)
    page_rev("pg5r1", "pg5", 1, "Silinecek kurgusal kayıt", "Bu kayıt sonradan silindi.", ["e1"], [claim(EX["e1"], ["e1"])], sc)
    page_rev("pg6r1", "pg6", 1, "Atlas SPI saat bölücü", "Atlas kartında SPI saat bölücü 8.", ["e6"], [claim(EX["e6"], ["e6"])], scope("Atlas-K2", ""), kind="component")
    page_rev("pg1r2", "pg1", 2, "Hata ayıklama UART hızı", "UART0 hata ayıklama hızı 921600 baud. Akış denetimi kapalı.", ["e3"], [claim(EX["e3"], ["e3"])], sc, author=worker)
    page_rev("pg7r1", "pg7", 1, "Watchdog süresi", "Watchdog taslağı.", ["e1"], [claim("Watchdog taslağı.", ["e1"], "hypothesis")], sc, author=selin)
    page_rev("pg7r2", "pg7", 2, "Watchdog süresi", "Watchdog taslağı, düzeltilmiş.", ["e1"], [claim("Watchdog taslağı, düzeltilmiş.", ["e1"], "hypothesis")], sc, author=selin)
    page_rev("pg2r2", "pg2", 2, "Konsol baud hızı (saha)", "Sahada konsol 57600 baud ölçüldü.", ["e2", "e4"], [claim(EX["e2"], ["e2"]), claim("Kablo 3 metredir.", ["e4"], "tested_result")], sc, unknowns=["Ölçüm hangi yazılım sürümüyle yapıldı?"])

    t["pages"] = [
        {"id": I("pg1"), "project_id": P1, "owner_id": ayse, "current": 2, "published_revision": I("pg1r1"), "lifecycle": "active", "freshness": "current"},
        {"id": I("pg2"), "project_id": P1, "owner_id": mert, "current": 2, "published_revision": I("pg2r1"), "lifecycle": "active", "freshness": "current"},
        {"id": I("pg3"), "project_id": P1, "owner_id": ayse, "current": 1, "published_revision": I("pg3r1"), "lifecycle": "withdrawn", "freshness": "current"},
        {"id": I("pg4"), "project_id": P1, "owner_id": selin, "current": 1, "published_revision": None, "lifecycle": "active", "freshness": "unknown"},
        {"id": I("pg5"), "project_id": P1, "owner_id": ayse, "current": 1, "published_revision": I("pg5r1"), "lifecycle": "withdrawn", "freshness": "current"},
        {"id": I("pg6"), "project_id": P2, "owner_id": ayse, "current": 1, "published_revision": I("pg6r1"), "lifecycle": "active", "freshness": "current"},
        {"id": I("pg7"), "project_id": P1, "owner_id": selin, "current": 2, "published_revision": None, "lifecycle": "active", "freshness": "unknown"},
    ]

    # ------------------------------------------------------------- değişiklik setleri
    rel = {"subject": I("pg1"), "object": I("pg2"), "type": "depends_on", "evidence_ids": [I("e2")], "rationale": "Saha ölçümü hata ayıklama hızına bağlı.", "id": I("rel1"), "scope": sc}
    t["change_sets"] = []

    def change(key: str, project: str, author: str, summary: str, revisions: list[str], bases: dict[str, int], state: str, relations: list[dict] | None = None, extra_hash: dict | None = None) -> str:
        h = hash_json({"revisions": [rev_hash[r] for r in revisions], "relations": relations or []})
        if extra_hash is not None:
            h = hash_json({"content_hash": h, "resolution": extra_hash})
        t["change_sets"].append({"id": I(key), "project_id": project, "author_id": author, "summary": summary, "revisions": [I(r) for r in revisions], "bases": {I(p): n for p, n in bases.items()}, "relations": relations or [], "hash": h, "state": state, "created_at": at(100 + len(t["change_sets"]))})
        return h

    h_c1 = change("c1", P1, mert, "UART ve saha hızı", ["pg1r1", "pg2r1"], {"pg1": 0, "pg2": 0}, "published")
    h_c2 = change("c2", P1, ayse, "PCIe notu + ilişki", ["pg3r1"], {"pg3": 0}, "published", [rel])
    h_c3 = change("c3", P1, selin, "Akış denetimi", ["pg4r1"], {"pg4": 0}, "in_review")
    h_c4 = change("c4", P1, ayse, "Silinecek kayıt", ["pg5r1"], {"pg5": 0}, "deleted")
    h_c5 = change("c5", P2, ayse, "Atlas SPI", ["pg6r1"], {"pg6": 0}, "published")
    change("c6", P1, worker, "Metis: UART hızı güncellemesi", ["pg1r2"], {"pg1": 1}, "draft")
    change("c8", P1, selin, "Watchdog ilk taslak", ["pg7r1"], {"pg7": 0}, "superseded")
    change("c9", P1, selin, "Watchdog düzeltilmiş", ["pg7r2"], {"pg7": 1}, "draft")
    snapshots = {I("pg1"): {"page_id": I("pg1"), "revision_id": I("pg1r1"), "current": 1, "title": "Hata ayıklama UART hızı", "scope": sc}, I("pg2"): {"page_id": I("pg2"), "revision_id": I("pg2r1"), "current": 1, "title": "Konsol baud hızı (saha)", "scope": sc}}
    option = {"title": "Saha ölçümünü koru, eski notu geri çek", "rationale": "Saha ölçümü daha güncel.", "prerequisite": "", "keep_page_ids": [I("pg2")], "retire_page_ids": [I("pg1")], "evidence": [{"evidence_id": I("e2"), "quote": EX["e2"]}]}
    resolution = {"case_id": I("a1"), "requester_id": ayse, "option": option, "reason": "Saha ölçümü daha güncel ve doğrulanmış.", "snapshots": snapshots, "model_name": "kurgusal-model"}
    change("c7", P1, ayse, "Çelişki çözümü: " + option["title"], ["pg2r2"], {"pg2": 1}, "in_review", extra_hash=resolution)

    t["approvals"] = [
        {"id": I("ap1"), "change_id": I("c1"), "hash": h_c1, "reviewer_id": ayse, "decision": "approved", "reason": "Kanıtlar kontrol edildi.", "policy": "independent-v1", "created_at": at(200)},
        {"id": I("ap2"), "change_id": I("c2"), "hash": h_c2, "reviewer_id": mert, "decision": "approved", "reason": "Uygun.", "policy": "independent-v1", "created_at": at(201)},
        {"id": I("ap3"), "change_id": I("c3"), "hash": h_c3, "reviewer_id": mert, "decision": "changes_requested", "reason": "Kaynağı netleştir.", "policy": "independent-v1", "created_at": at(202)},
        {"id": I("ap4"), "change_id": I("c4"), "hash": h_c4, "reviewer_id": mert, "decision": "approved", "reason": "Uygun.", "policy": "independent-v1", "created_at": at(203)},
        {"id": I("ap5"), "change_id": I("c5"), "hash": h_c5, "reviewer_id": ayse, "decision": "approved", "reason": "Pilot: sahip incelemesi.", "policy": "owner_review-v1", "created_at": at(204)},
    ]
    pages_p1 = {I("pg1"): I("pg1r1"), I("pg2"): I("pg2r1")}
    t["publications"] = [
        {"id": I("pub1"), "project_id": P1, "manifest": {"schema": 1, "pages": dict(pages_p1), "relations": []}, "change_id": I("c1"), "created_at": at(300)},
        {"id": I("pub2"), "project_id": P1, "manifest": {"schema": 1, "pages": {**pages_p1, I("pg3"): I("pg3r1")}, "relations": [rel]}, "change_id": I("c2"), "created_at": at(301)},
        {"id": I("pub3"), "project_id": P1, "manifest": {"schema": 1, "pages": {**pages_p1, I("pg3"): I("pg3r1"), I("pg5"): I("pg5r1")}, "relations": [rel]}, "change_id": I("c4"), "created_at": at(302)},
        # c4 silindi: v1 remove_record_publication yeni bir yayın üretir (pg5 çıkar); pg3 elle geri çekildi
        {"id": I("pub4"), "project_id": P1, "manifest": {"schema": 1, "pages": {**pages_p1, I("pg3"): I("pg3r1")}, "relations": [rel]}, "change_id": I("c4"), "created_at": at(303)},
        {"id": I("pub5"), "project_id": P2, "manifest": {"schema": 1, "pages": {I("pg6"): I("pg6r1")}, "relations": []}, "change_id": I("c5"), "created_at": at(304)},
    ]
    t["search_entries"] = [{"publication_id": I("pub4"), "page_id": I("pg1"), "revision_id": I("pg1r1"), "content": "Hata ayıklama UART hızı"}]

    # ------------------------------------------------------------- bulgular, işler
    t["findings"] = [
        {"id": I("f1"), "project_id": P1, "page_id": I("pg1"), "kind": "conflict", "severity": "high", "state": "open", "detail": {"other_page_id": I("pg2"), "summary": "115200 ↔ 57600 baud"}, "reason": "", "created_at": at(400)},
        {"id": I("f2"), "project_id": P1, "page_id": I("pg1"), "kind": "source_changed", "severity": "medium", "state": "resolved", "detail": {"old_revision": I("pg1r1"), "new_source_revision": I("s1r2"), "same_scope": True}, "reason": "Yeni sürüm taslağa alındı.", "created_at": at(401)},
        {"id": I("f3"), "project_id": P1, "page_id": I("pg4"), "kind": "user_report", "severity": "low", "state": "open", "detail": {"text": "Başlık belirsiz."}, "reason": "", "created_at": at(402)},
    ]
    t["work_items"] = [
        {"id": I("w1"), "project_id": P1, "requester_id": mert, "title": "UART notunu karşılaştır", "kind": "refine_draft", "inputs": {"draft_change_id": I("c6"), "source_revision_ids": [I("s1r2")]}, "state": "completed", "worker_id": worker, "fence": 2, "lease_until": 0, "attempt": 1, "checkpoint": {"reports": [{"comparisons": []}]}, "messages": [{"kind": "question", "text": "Kapsam doğru mu?", "at": 1762160000}, {"kind": "response", "text": "Evet.", "at": 1762160100}], "outputs": [I("c6")], "created_at": at(500)},
        {"id": I("w2"), "project_id": P1, "requester_id": selin, "title": "Saha raporunu işle", "kind": "ingest_source", "inputs": {"source_revision_ids": [I("s2r1")]}, "state": "running", "worker_id": worker, "fence": 1, "lease_until": 1762160000.0, "attempt": 1, "checkpoint": {}, "messages": [], "outputs": [], "created_at": at(501)},
        {"id": I("w3"), "project_id": P1, "requester_id": ayse, "title": "Bakım denetimi", "kind": "maintenance_review", "inputs": {}, "state": "failed", "worker_id": worker, "fence": 1, "lease_until": 0, "attempt": 3, "checkpoint": {"error": "MODEL_UNAVAILABLE"}, "messages": [], "outputs": [], "created_at": at(502)},
    ]
    t["extracted_claims"] = [{"id": I("x1"), "project_id": P1, "source_revision_id": I("s1r2"), "work_id": I("w1"), "fingerprint": hashlib.sha256(b"x1").hexdigest(), "subject": "UART0", "attribute": "hata ayıklama hızı", "value": "921600 baud", "scope": {**sc, "condition": ""}, "quote": EX["e3"], "quote_start": 0, "quote_end": len(EX["e3"]), "valid_from": None, "page_revision_id": I("pg1r2"), "state": "draft"}]
    t["open_decisions"] = [{"id": I("o1"), "project_id": P1, "source_revision_id": I("s2r1"), "work_id": I("w2"), "fingerprint": hashlib.sha256(b"o1").hexdigest(), "description": "Ölçüm sürümü belirsiz.", "quote": EX["e2"], "quote_start": 0, "quote_end": len(EX["e2"]), "state": "open"}]

    # ------------------------------------------------------------- cevaplar
    t["answers"] = [
        {"id": I("a1"), "owner_id": ayse, "project_id": P1, "question": "Hata ayıklama UART hızı nedir?", "scope": sc, "result": {"decision": "CONFLICTING", "claims": [{"evidence_id": I("e1"), "quote": EX["e1"]}, {"evidence_id": I("e2"), "quote": EX["e2"]}], "evidence": [{"evidence_id": I("e1"), "page_id": I("pg1"), "page_revision_id": I("pg1r1")}, {"evidence_id": I("e2"), "page_id": I("pg2"), "page_revision_id": I("pg2r1")}], "publication_id": I("pub2"), "prompt_version": "evidence-quotes-v4", "model": "kurgusal-model"}, "feedback": {}, "created_at": at(600)},
        {"id": I("a2"), "owner_id": mert, "project_id": P2, "question": "Atlas SPI saat bölücü kaç?", "scope": scope("Atlas-K2", ""), "result": {"decision": "SUPPORTED", "claims": [{"evidence_id": I("e6"), "quote": EX["e6"]}], "evidence": [{"evidence_id": I("e6"), "page_id": I("pg6"), "page_revision_id": I("pg6r1")}], "publication_id": I("pub5"), "prompt_version": "evidence-quotes-v4", "timings_ms": {"total": 812}}, "feedback": {"rating": "helpful", "comment": "Doğru."}, "created_at": at(601)},
    ]

    # ------------------------------------------------------------- modeller
    t["providers"] = [{"id": I("prov1"), "name": "Şirket modeli (kurgusal)", "base_url": "https://llm.kurgusal.local/v1", "secret": v1_encrypt_secret(PROVIDER_SECRET, master), "secret_version": 1, "updated_at": at(700), "concurrency": 2, "timeout": 45}]
    t["models"] = [{"id": I("m1"), "provider_id": I("prov1"), "name": "Kurgusal büyük model", "remote_id": "kurgusal-70b", "enabled": True, "capabilities": {"json_schema": True}, "config_version": 3, "quality": {"qualified": True, "accuracy": 0.95}, "failures": 0, "circuit_until": 0}]
    t["provider_leases"] = []
    t["benchmark_runs"] = [{"id": I("b1"), "model_id": I("m1"), "dataset": "evidence-v4", "fingerprint": "f" * 64, "results": [], "metrics": {"accuracy": 0.95}, "demo": False, "state": "completed", "budget": 6, "created_at": at(701)}]
    t["model_calls"] = [{"id": I("mc1"), "model_id": I("m1"), "model_name": "kurgusal-70b", "prompt_version": "evidence-quotes-v4", "input_hash": "a" * 64, "system_hash": "b" * 64, "user_hash": "c" * 64, "context": {}, "state": "completed", "raw_output": "{}", "parsed_output": {}, "usage": {}, "duration_ms": 812.0, "error": "", "cached_from": None, "created_at": at(702)}]
    t["model_cache"] = [{"key": "d" * 64, "call_id": I("mc1"), "output": {}, "created_at": at(702)}]
    t["idempotency"] = [{"key": ayse + ":k1", "hash": "e" * 64, "result_id": I("c1")}]
    t["audit_events"] = [
        {"id": I("au1"), "actor_id": ayse, "operation": "change.review", "target": I("c1"), "detail": {"decision": "approved"}, "correlation_id": I("corr1"), "created_at": at(200)},
        {"id": I("au2"), "actor_id": worker, "operation": "change.create", "target": I("c6"), "detail": {}, "correlation_id": I("corr2"), "created_at": at(503)},
        {"id": I("au3"), "actor_id": ayse, "operation": "page.withdraw", "target": I("pg3"), "detail": {"reason": "Eskidi"}, "correlation_id": I("corr3"), "created_at": at(504)},
    ]

    # ------------------------------------------------------------- ayarlar
    t["settings"] = [
        {"key": "scope-catalog:" + P1, "value": {"domain": ["Gömülü yazılım"], "yatt": ["YATT-3"], "card": ["VPK120", "Eski-Kart"], "project": ["Atlas"], "deleted": {"card": ["Eski-Kart"]}}},
        {"key": "scope-catalog:" + P2, "value": {"hardware": ["Atlas-K2"], "platform": []}},
        {"key": "conflict-case:" + I("a1"), "value": {"id": I("a1"), "project_id": P1, "requester_id": ayse, "question": "Hata ayıklama UART hızı nedir?", "snapshots": snapshots, "state": "in_review", "model_name": "kurgusal-model", "model_id": I("m1"), "prompt_version": "conflict-resolution-v2", "assessment": {"summary": "İki sayfa farklı baud hızı bildiriyor.", "questions": ["Saha ölçümü hangi sürümle yapıldı?"], "options": [option, {"title": "Eski notu koru", "rationale": "Laboratuvar değeri.", "prerequisite": "Saha ölçümünü tekrarla.", "keep_page_ids": [I("pg1")], "retire_page_ids": [I("pg2")], "evidence": [{"evidence_id": I("e1"), "quote": EX["e1"]}]}]}, "change_id": I("c7"), "chosen_option": 0, "human_reason": resolution["reason"]}},
        {"key": "resolution-change:" + I("c7"), "value": resolution},
        {"key": "successor:" + I("c8"), "value": {"change_id": I("c9")}},
        {"key": "maintenance-schedule:" + P1, "value": {"enabled": True, "interval_days": 7}},
        {"key": "preparation-auto:" + P1, "value": {"enabled": True, "hours": 336}},
        {"key": "work-change:" + I("c6"), "value": {"work_item_id": I("w1")}},
        {"key": "dataset:evidence-v4", "value": {"cases": 26}},
        {"key": "routing-selection:" + P1, "value": {"model_id": I("m1")}},
        {"key": "ui-preferences:" + ayse, "value": {"theme": "dark"}},
    ]
    return t, blobs


def snapshot_zip(tables: dict, blobs: dict[str, bytes], master: bytes, *, extra_entries: dict[str, bytes] | None = None, drop_blob: str | None = None, corrupt_blob: str | None = None) -> bytes:
    doc = {"format": "metis-backup-v1", "schema": 2, "master_key_fingerprint": hashlib.sha256(master).hexdigest(), "tables": tables}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", json.dumps(doc, ensure_ascii=False))
        for digest, data in sorted(blobs.items()):
            if digest == drop_blob:
                continue
            z.writestr(f"blobs/{digest[:2]}/{digest}", data + (b"!" if digest == corrupt_blob else b""))
        for name, data in (extra_entries or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


def encrypt_outer(snapshot: bytes, master: bytes, password: str, *, outer_extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("snapshot.zip", snapshot)
        z.writestr("recovery.json", json.dumps({"format": 1, "master": base64.b64encode(master).decode()}))
        for name, data in (outer_extra or {}).items():
            z.writestr(name, data)
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=32768, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)
    cipher = AES.new(key, AES.MODE_GCM, nonce=secrets.token_bytes(16))
    cipher.update(MAGIC)
    encrypted, tag = cipher.encrypt_and_digest(buf.getvalue())
    return MAGIC + salt + cipher.nonce + tag + encrypted


def make_backup(
    path: Path,
    password: str = PASSWORD,
    *,
    mutate_tables: Callable[[dict], None] | None = None,
    extra_entries: dict[str, bytes] | None = None,
    outer_extra: dict[str, bytes] | None = None,
    drop_blob: bool = False,
    corrupt_blob: bool = False,
    master: bytes | None = None,
) -> Path:
    master = master or hashlib.sha256(b"kurgusal-v055-master").digest()
    tables, blobs = build_tables(master)
    if mutate_tables:
        mutate_tables(tables)
    first = sorted(blobs)[0]
    snap = snapshot_zip(tables, blobs, master, extra_entries=extra_entries, drop_blob=first if drop_blob else None, corrupt_blob=first if corrupt_blob else None)
    path.write_bytes(encrypt_outer(snap, master, password, outer_extra=outer_extra))
    return path


if __name__ == "__main__":  # elle tatbikat: python -m tests.legacy_import.synthetic <hedef>
    import sys

    out = make_backup(Path(sys.argv[1]))
    print(f"{out} (parola: {PASSWORD})")
