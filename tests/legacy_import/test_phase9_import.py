"""Faz 9 kabul: sentetik v0.5.5 yedeği (izole DB). Gerçek yedekle tatbikat ayrı raporlanır."""

from __future__ import annotations

import base64
import json
import logging
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from metis.core.config import get_settings
from metis.legacy_import.runner import run_import
from tests.legacy_import import synthetic as syn
from tests.legacy_import.synthetic import I


def _volatile_free(report: dict) -> dict:
    return json.loads(json.dumps(report, sort_keys=True, default=str))


def _table_counts(db) -> dict[str, int]:  # noqa: ANN001
    names = [r[0] for r in db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))]
    return {n: db.execute(text(f'SELECT count(*) FROM "{n}"')).scalar_one() for n in sorted(names)}


def _blob_files() -> set[str]:
    root = get_settings().blob_dir
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} if root.exists() else set()


@pytest.fixture
def backup(tmp_path: Path) -> Path:
    return syn.make_backup(tmp_path / "metis-yedek-çğış.metisbackup")


def test_dry_run_and_apply_produce_identical_report(backup: Path, db, tmp_path: Path, client) -> None:  # noqa: ANN001
    before = _table_counts(db)
    dry = run_import(backup, syn.PASSWORD, dry_run=True, report_dir=tmp_path / "rapor")
    assert dry["ok"], dry["summary"]
    db.rollback()
    after_dry = _table_counts(db)
    assert {k: v for k, v in after_dry.items() if k != "legacy_import_runs"} == {k: v for k, v in before.items() if k != "legacy_import_runs"}
    assert after_dry["legacy_import_runs"] == before["legacy_import_runs"] + 1
    assert Path(dry["paths"]["md"]).read_text(encoding="utf-8").startswith("# v0.5.5 aktarım raporu")

    applied = run_import(backup, syn.PASSWORD, dry_run=False)
    assert applied["ok"], applied["summary"]
    assert _volatile_free(dry["report"]) == _volatile_free(applied["report"])
    assert dry["fingerprint"] == applied["fingerprint"]
    rep = applied["report"]
    v = rep["verification"]
    assert v["publications"] == {"checked": 5, "with_matching_approval": 5, "failures": []}
    assert v["active_pages"]["count"] == 3  # pg1, pg2 (P1) + pg6 (P2); pg3 geri çekildi, pg5 silindi
    assert v["active_pages"]["claims"] == v["active_pages"]["claims_linked"] == 4
    assert v["deleted_hidden"]["visible_in_active_views"] == []
    assert v["blobs"]["count"] == v["blobs"]["sha256_verified"] == 5
    assert v["mentor_sample"]["state"] == "atlandı"
    assert rep["cancelled_jobs"] == [{"id": I("w2"), "title": "Saha raporunu işle", "state": "running"}]
    assert "ui-preferences:" + I("ayse") in rep["not_imported_settings"]
    assert any("owner_review" in n for n in rep["notes"])
    assert any("daha seyrek olan (14 gün)" in n for n in rep["notes"])
    reasons = {s["reason"] for s in rep["skipped"]}
    assert "worker/bot kimliği aktarılmaz; tek metis-worker kimliğine bağlandı" in reasons
    # dry-run ve apply koşu kayıtları
    runs = db.execute(text("SELECT mode, state FROM legacy_import_runs ORDER BY started_at")).all()
    assert [tuple(r) for r in runs] == [("dry_run", "completed"), ("apply", "completed")]


def test_imported_knowledge_is_usable_in_v2(backup: Path, client, db) -> None:  # noqa: ANN001
    assert run_import(backup, syn.PASSWORD, dry_run=False)["ok"]
    # eski parola (v0.5.5 scrypt salt:hex) ile giriş; ilk girişte v2 parametreleriyle yeniden hash
    client.login("ayse.kurgu", syn.OLD_USER_PASSWORD)
    stored = db.execute(text("SELECT password_hash FROM users WHERE username='ayse.kurgu'")).scalar_one()
    assert stored.startswith("scrypt$")
    p1, p2 = I("p1"), I("p2")
    # aktif sayfalar listede; geri çekilmiş ve silinmiş kayıtlar görünmez
    rows = client.get(f"/api/v1/projects/{p1}/pages").json()
    ids = {row["page_id"] for row in rows["items"]}
    assert ids == {I("pg1"), I("pg2")}
    # sayfa açılır, ●n işaretleri doğru kaynağa gider
    page = client.get(f"/api/v1/pages/{I('pg2')}").json()
    claims = page["revision"]["claims"]
    assert [c["statement"] for c in claims] == ["Saha ölçümünde konsol hızı 57600 baud bulundu.", "Kablo 3 metredir."]
    ev = claims[0]["evidence"][0]
    assert ev["evidence_id"] == I("e2")
    iz = client.get(f"/api/v1/evidence/{ev['evidence_id']}").json()
    assert iz["source"]["title"] == "Saha ölçümleri — çalışma"
    assert iz["highlight"] is not None
    assert iz["locator"]["page"] == 3
    assert "57600 baud" in iz["excerpt"]
    assert claims[0]["verbatim"] is True and claims[1]["verbatim"] is False
    # owner_review politikası korunur
    proj = client.get(f"/api/v1/projects/{p2}").json()
    assert proj["review_policy"] == "owner_review"
    # arama indeksi aktif yayın için yeniden kuruldu
    hits = client.get(f"/api/v1/projects/{p1}/search", params={"q": "baud"}).json()
    assert {h["page_id"] for h in hits["hits"]} == {I("pg1"), I("pg2")}
    # silinmiş sayfa doğrudan açılmaz (geri çekildi uyarısıyla geçmiş görünür ama listede/aramada yok)
    assert I("pg5") not in {h["page_id"] for h in client.get(f"/api/v1/projects/{p1}/search", params={"q": "silindi"}).json()["hits"]}
    # çelişki bulgusu ve vaka; çözüm kaydı incelemede
    findings = client.get(f"/api/v1/projects/{p1}/findings", params={"state": "open"}).json()
    kinds = sorted(f["kind"] for f in findings["items"])
    assert kinds == ["conflict", "reported"]
    case_id = db.execute(text("SELECT id FROM conflict_cases")).scalar_one()
    res = db.execute(text("SELECT change_set_id FROM conflict_resolutions WHERE case_id=:c"), {"c": case_id}).scalar_one()
    assert str(res) == I("c7")
    # eski cevap "v1 alıntı cevabı" olarak işaretli
    assert db.execute(text("SELECT count(*) FROM answers WHERE legacy")).scalar_one() == 2
    # modeller test edilmedi durumunda (yeterlilik taşınmaz)
    assert db.execute(text("SELECT count(*) FROM model_qualifications")).scalar_one() == 0
    # audit: legacy_import olayı + eski olaylar legacy=true
    assert db.execute(text("SELECT count(*) FROM audit_events WHERE op='legacy_import'")).scalar_one() == 1
    assert db.execute(text("SELECT count(*) FROM audit_events WHERE detail->>'legacy'='true' AND op <> 'legacy_import'")).scalar_one() == 3
    # bloblar yerinde ve doğrulanmış
    expected = {f"{h[:2]}/{h}" for h in db.execute(text("SELECT sha256 FROM source_revisions")).scalars()}
    assert len(expected) == 5 and expected <= _blob_files()


def test_provider_key_reencrypted_and_no_plaintext_anywhere(backup: Path, db, tmp_path: Path, caplog, _database) -> None:  # noqa: ANN001
    from metis.core.security import decrypt_secret

    caplog.set_level(logging.DEBUG)
    out = run_import(backup, syn.PASSWORD, dry_run=False, report_dir=tmp_path / "rapor")
    assert out["ok"]
    enc = db.execute(text("SELECT secret_enc FROM providers")).scalar_one()
    assert enc.startswith("v2:")
    assert decrypt_secret(enc) == syn.PROVIDER_SECRET
    needle = syn.PROVIDER_SECRET
    # DB'nin tamamı (pg_dump), raporlar, loglar, blob dizini
    dsn = _database.replace("postgresql+psycopg://", "postgresql://")
    # encoding açık: Türkçe Windows'ta (cp1254) varsayılan kod sayfası UTF-8 dökümü çözemiyor, stdout None kalıyordu.
    # errors="replace": stderr'deki uyarılar yerel kod sayfasında gelir (yalnız dökümün kendisi denetlenir).
    dump = subprocess.run(["pg_dump", "--data-only", dsn], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    assert needle not in dump
    assert syn.PASSWORD not in dump
    for f in (tmp_path / "rapor").iterdir():
        assert needle not in f.read_text(encoding="utf-8")
    assert needle not in caplog.text and syn.PASSWORD not in caplog.text
    for p in get_settings().blob_dir.rglob("*"):
        if p.is_file():
            assert needle.encode() not in p.read_bytes()
    log_dir = get_settings().log_dir
    if log_dir.exists():
        for p in log_dir.rglob("*"):
            if p.is_file():
                assert needle not in p.read_text(encoding="utf-8", errors="ignore")
    assert needle not in json.dumps(out, default=str)


def _assert_refused(path: Path, db, code: str, password: str = syn.PASSWORD) -> None:  # noqa: ANN001
    before, blobs = _table_counts(db), _blob_files()
    out = run_import(path, password, dry_run=False)
    assert not out["ok"]
    assert out["code"] == code, out
    assert out["summary"].endswith("Hiçbir şey değiştirilmedi.")
    db.rollback()
    assert _table_counts(db) == before
    assert _blob_files() == blobs
    staging = [p for p in get_settings().blob_dir.parent.iterdir() if p.name.startswith(".import-")] if get_settings().blob_dir.parent.exists() else []
    assert staging == []


def test_wrong_password(backup: Path, db) -> None:  # noqa: ANN001
    _assert_refused(backup, db, "WRONG_PASSWORD", password="Yanlış-Parola-1234")


def test_broken_tag(backup: Path, db) -> None:  # noqa: ANN001
    raw = bytearray(backup.read_bytes())
    raw[45] ^= 0x01  # tag alanı (40..56)
    backup.write_bytes(bytes(raw))
    _assert_refused(backup, db, "WRONG_PASSWORD")


def test_broken_ciphertext(backup: Path, db) -> None:  # noqa: ANN001
    raw = bytearray(backup.read_bytes())
    raw[-1] ^= 0xFF
    backup.write_bytes(bytes(raw))
    _assert_refused(backup, db, "WRONG_PASSWORD")


def test_not_a_backup(tmp_path: Path, db) -> None:  # noqa: ANN001
    f = tmp_path / "rastgele.bin"
    f.write_bytes(b"PK\x03\x04" + b"x" * 200)
    _assert_refused(f, db, "NOT_A_BACKUP")


def test_missing_blob(tmp_path: Path, db) -> None:  # noqa: ANN001
    _assert_refused(syn.make_backup(tmp_path / "y.bak", drop_blob=True), db, "MISSING_BLOB")


def test_blob_hash_mismatch(tmp_path: Path, db) -> None:  # noqa: ANN001
    _assert_refused(syn.make_backup(tmp_path / "y.bak", corrupt_blob=True), db, "HASH_MISMATCH")


def test_target_not_empty(backup: Path, db, client) -> None:  # noqa: ANN001
    from tests.factories import setup_admin

    setup_admin(client)
    db.rollback()
    _assert_refused(backup, db, "TARGET_NOT_EMPTY")
    # dry-run da dolu DB'de reddeder
    out = run_import(backup, syn.PASSWORD, dry_run=True)
    assert out["code"] == "TARGET_NOT_EMPTY"


def test_second_apply_is_refused(backup: Path, db) -> None:  # noqa: ANN001
    assert run_import(backup, syn.PASSWORD, dry_run=False)["ok"]
    db.rollback()
    _assert_refused(backup, db, "TARGET_NOT_EMPTY")


@pytest.mark.parametrize(
    "bad_hash",
    ["../../../etc/passwd", "..\\..\\windows\\win.ini", "/etc/shadow", "a" * 63 + "/", "A" * 64],
)
def test_path_traversal_in_manifest_hash(tmp_path: Path, db, bad_hash: str) -> None:  # noqa: ANN001
    def mutate(t: dict) -> None:
        t["source_revisions"][0]["hash"] = bad_hash

    _assert_refused(syn.make_backup(tmp_path / "y.bak", mutate_tables=mutate), db, "BAD_HASH")
    assert not (tmp_path.parent / "etc").exists()


def test_path_traversal_entries_are_never_extracted(tmp_path: Path, db) -> None:  # noqa: ANN001
    evil = {"../../kotu.txt": b"x", "blobs/../../../kotu2.txt": b"y"}
    path = syn.make_backup(tmp_path / "y.bak", extra_entries=evil)
    out = run_import(path, syn.PASSWORD, dry_run=True)
    assert out["ok"]  # fazladan girdiler yok sayılır; yol hiçbir zaman arşivden türetilmez
    root = get_settings().blob_dir.parent
    assert not list(root.parent.rglob("kotu*.txt"))
    # dış ZIP'te beklenmeyen dosya: reddedilir
    _assert_refused(syn.make_backup(tmp_path / "z.bak", outer_extra={"../kotu.txt": b"x"}), db, "CORRUPT")


def test_failure_during_apply_rolls_back_everything(backup: Path, db, monkeypatch) -> None:  # noqa: ANN001
    import metis.legacy_import.runner as runner

    def boom(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("yazma sırasında kurgusal hata")

    monkeypatch.setattr(runner, "_db_verify", boom)
    before, blobs = _table_counts(db), _blob_files()
    out = run_import(backup, syn.PASSWORD, dry_run=False)
    assert not out["ok"] and out["summary"].endswith("Hiçbir şey değiştirilmedi.")
    db.rollback()
    assert _table_counts(db) == before
    assert _blob_files() == blobs


def test_wrong_recovery_key_fingerprint(tmp_path: Path, db) -> None:  # noqa: ANN001
    path = tmp_path / "y.bak"
    master = b"m" * 32
    tables, blobs = syn.build_tables(master)
    snap = syn.snapshot_zip(tables, blobs, b"x" * 32)  # manifest başka bir ana anahtarın parmak izini taşıyor
    path.write_bytes(syn.encrypt_outer(snap, master, syn.PASSWORD))
    _assert_refused(path, db, "CORRUPT")
    assert base64  # noqa: B018


def test_counts_match_source(backup: Path) -> None:
    out = run_import(backup, syn.PASSWORD, dry_run=True)
    rep = out["report"]
    src, dst = rep["source_counts"], rep["target_counts"]
    assert dst["users"] == 4  # 3 insan + metis-worker
    assert dst["projects"] == src["projects"] == 2
    assert dst["source_revisions"] == src["source_revisions"]
    assert dst["evidence"] == src["evidence"]
    assert dst["page_revisions"] == src["page_revisions"]
    assert dst["change_sets"] == src["change_sets"]
    assert dst["reviews"] == src["approvals"]
    assert dst["publications"] == src["publications"]
    assert dst["jobs"] == src["work_items"]
    assert dst["answers"] == src["answers"]
    assert dst["schedules"] == 2
    assert "benchmark_runs" not in dst and "model_calls" not in dst
    assert select and func  # noqa: B018


def test_runs_endpoint_and_markdown_export(backup: Path, client, make_client) -> None:  # noqa: ANN001
    import io
    import zipfile

    assert run_import(backup, syn.PASSWORD, dry_run=True)["ok"]
    assert run_import(backup, syn.PASSWORD, dry_run=False)["ok"]
    client.login("ayse.kurgu", syn.OLD_USER_PASSWORD)
    runs = client.get("/api/v1/legacy-import/runs").json()
    assert [r["mode"] for r in runs] == ["apply", "dry_run"]
    assert runs[0]["summary"]["verification_ok"] is True and runs[0]["summary"]["active_pages"] == 3
    detail = client.get(f"/api/v1/legacy-import/runs/{runs[0]['id']}").json()
    assert detail["report_md"].startswith("# v0.5.5 aktarım raporu")
    assert syn.PROVIDER_SECRET not in json.dumps(detail)
    # yönetici olmayan kullanıcı göremez
    other = make_client()
    other.login("selin.caliskan", syn.OLD_USER_PASSWORD)
    assert other.get("/api/v1/legacy-import/runs").status_code == 403
    # Markdown ZIP: yalnız aktif yayın, index + kaynaklar
    r = client.get(f"/api/v1/projects/{I('p1')}/export.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "attachment;" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = sorted(z.namelist())
    assert names == ["index.md", "kaynaklar.md", "sayfalar/hata-ayiklama-uart-hizi.md", "sayfalar/konsol-baud-hizi-saha.md"]
    page = z.read("sayfalar/konsol-baud-hizi-saha.md").decode()
    assert "# Konsol baud hızı (saha)" in page and "[^1]" in page and "Sayfa 3" in page
    assert "PDF · sayfa 4 · tablo 2" in page
    assert "Saha ölçümleri — çalışma" in z.read("kaynaklar.md").decode()
    assert "Silinecek" not in "".join(z.read(n).decode() for n in names)
    # üye olmayan: 404
    assert other.get(f"/api/v1/projects/{I('p2')}/export.zip").status_code == 404
