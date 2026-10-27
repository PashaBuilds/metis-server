"""Model laboratuvarı: sağlayıcılar, modeller, probe → transport profili, ortak benchmark, yeterlilik, routing.

- UI asla sessizce model seçmez; "Otomatik" yalnız deterministik routing'dir (kalite kapısı → gecikme).
- Ortak benchmark'ı geçen model her projede kullanılabilir (projeye özel yeterlilik yok).
- Kritik hata (uydurma sayı/sembol, sahte kaynak, kapsam ihlali, çekimser yerde cevap) ortalamadan bağımsız eler.
- "Sonucu temizle" sunucuda `hidden_at` ile kalıcıdır; gizlenen sonuç yeterlilik sayılmaz.
"""

from __future__ import annotations

import json
import math
import statistics
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from metis.core.access import require_admin, require_member
from metis.core.audit import audit
from metis.core.db import transaction, utcnow
from metis.core.errors import AppError
from metis.core.models import (
    AllowedEndpoint,
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkResult,
    BenchmarkRun,
    Model,
    ModelProbe,
    ModelQualification,
    Project,
    Provider,
    User,
)
from metis.core.security import configured_endpoints, encrypt_secret, validate_endpoint
from metis.core.util import hash_json
from metis.llm import contracts, prompts
from metis.llm.client import ModelClient, profile_of
from metis.llm.validators import validate_answer

DATASET_KEY = "ortak-benchmark-v1"
PASS_RATIO = 0.9
MOCK_HOSTS = ("http://127.0.0.1:", "http://localhost:")
CRITICAL_REASONS = {"number", "symbol", "hex", "version"}


# ---------------------------------------------------------------- fingerprint ve uygunluk


def fingerprint(model: Model, provider: Provider) -> str:
    return hash_json(
        {
            "remote": model.remote_id,
            "config": model.config_version,
            "url": provider.base_url,
            "secret_version": provider.secret_version,
            "profile": {k: profile_of(model).get(k) for k in ("json_mode", "thinking")},
            "prompts": {p: prompts.load(p).sha256 for p in (prompts.EVIDENCE, prompts.SOURCE_SELECTION)},
            "max_tokens": 1500,
            "temperature": 0,
        }
    )


def latest_probe(db: Session, model_id: uuid.UUID, capability: str) -> ModelProbe | None:
    return db.scalar(
        select(ModelProbe).where(ModelProbe.model_id == model_id, ModelProbe.capability == capability).order_by(ModelProbe.at.desc()).limit(1)
    )


def current_qualification(db: Session, model: Model, provider: Provider) -> ModelQualification | None:
    return db.scalar(
        select(ModelQualification)
        .where(ModelQualification.model_id == model.id, ModelQualification.fingerprint == fingerprint(model, provider), ModelQualification.hidden_at.is_(None))
        .order_by(ModelQualification.at.desc())
        .limit(1)
    )


def eligibility(db: Session, model: Model, project: Project | None) -> tuple[bool, str]:
    provider = db.get(Provider, model.provider_id)
    if model.deleted_at is not None or provider is None or provider.deleted_at is not None:
        return False, "deleted"
    if not model.enabled:
        return False, "disabled"
    if model.is_fixture and project is not None and not project.is_demo:
        return False, "fixture_not_for_company_data"
    if model.circuit_until and model.circuit_until > utcnow():
        return False, "circuit_open"
    probe = latest_probe(db, model.id, "evidence_contract")
    if not probe or probe.status != "tested_pass":
        return False, "probe_missing"
    qual = current_qualification(db, model, provider)
    if qual is None:
        stale = db.scalar(select(ModelQualification.id).where(ModelQualification.model_id == model.id, ModelQualification.hidden_at.is_(None)).limit(1))
        return False, "config_changed" if stale else "not_qualified"
    if qual.critical_errors:
        return False, "critical_error"
    if not qual.passed:
        return False, "quality_failed"
    return True, "eligible"


def _p50(db: Session, model: Model, provider: Provider) -> float | None:
    lat = latency_samples(db, model, provider)
    return statistics.median(lat) if lat else None


def route(db: Session, project: Project, user: User | None = None) -> tuple[Model | None, list[dict]]:
    """Deterministik routing: uygun modeller arasında en düşük benchmark p50; eşitlikte ad/id. `user` verilirse yalnız
    kişinin anahtarı olan (yöneticide ortak anahtar) sağlayıcıların modelleri seçilir (2.0.28)."""
    from metis.modules.keys.service import key_for

    reasons, candidates = [], []
    for model in db.scalars(select(Model).where(Model.deleted_at.is_(None)).order_by(Model.display_name, Model.id)):
        ok, reason = eligibility(db, model, project)
        if ok and user is not None and key_for(db, user, model.provider_id) is None:
            ok, reason = False, "personal_key_missing"
        reasons.append({"model_id": str(model.id), "display_name": model.display_name, "eligible": ok, "reason": reason})
        if ok:
            provider = db.get(Provider, model.provider_id)
            candidates.append((_p50(db, model, provider) or 1e12, model.display_name, str(model.id), model))  # type: ignore[arg-type]
    candidates.sort(key=lambda c: c[:3])
    return (candidates[0][3] if candidates else None), reasons


def available_models(db: Session, user: User, project_id: uuid.UUID) -> list[dict]:
    require_member(db, user, project_id)
    project = db.get(Project, project_id)
    out = []
    from metis.modules.keys.service import key_for

    for model in db.scalars(select(Model).where(Model.deleted_at.is_(None)).order_by(Model.display_name)):
        ok, reason = eligibility(db, model, project)
        if ok and key_for(db, user, model.provider_id) is None:
            ok, reason = False, "personal_key_missing"
        out.append({"id": str(model.id), "display_name": model.display_name, "eligible": ok, "reason": reason, "is_fixture": model.is_fixture})
    return out


# ---------------------------------------------------------------- sağlayıcı ve model CRUD


def provider_out(db: Session, p: Provider) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "base_url": p.base_url,
        "secret_configured": bool(p.secret_enc),
        "secret_updated_at": p.secret_updated_at.isoformat() if p.secret_updated_at else None,
        "max_concurrency": p.max_concurrency,
        "timeout_s": p.timeout_s,
        "ca_bundle_configured": bool(p.ca_bundle_ref),
        "created_at": p.created_at.isoformat(),
    }


def create_provider(db: Session, user: User, name: str, base_url: str, api_key: str, model_ids: list[str], max_concurrency: int, timeout_s: int, ca_bundle_ref: str = "") -> Provider:
    require_admin(user)
    url = validate_endpoint(base_url)
    ids = [m.strip() for m in model_ids if m.strip()]
    if not ids:
        raise AppError("VALIDATION_ERROR", "at least one model id", fields=[{"field": "model_ids", "type": "missing"}])
    if any(len(m) > 200 for m in ids):
        raise AppError("VALIDATION_ERROR", "model id too long", fields=[{"field": "model_ids", "type": "too_long"}])
    p = Provider(
        name=name.strip() or url,
        base_url=url,
        secret_enc=encrypt_secret(api_key) if api_key else "",
        secret_version=1 if api_key else 0,
        secret_updated_at=utcnow() if api_key else None,
        max_concurrency=max_concurrency,
        timeout_s=timeout_s,
        ca_bundle_ref=ca_bundle_ref,
    )
    db.add(p)
    db.flush()
    mock = url.startswith(MOCK_HOSTS)
    for rid in dict.fromkeys(ids):
        db.add(Model(provider_id=p.id, remote_id=rid, display_name=rid, is_fixture=mock and rid.startswith("fixture-"), transport_profile={}))
    audit(db, user.id, "provider.create", "provider", p.id, models=ids)  # anahtar loglanmaz
    return p


def rotate_key(db: Session, user: User, provider_id: uuid.UUID, api_key: str) -> Provider:
    require_admin(user)
    p = db.get(Provider, provider_id)
    if not p or p.deleted_at is not None:
        raise AppError("NOT_FOUND", "provider not found")
    p.secret_enc = encrypt_secret(api_key) if api_key else ""
    p.secret_version += 1
    p.secret_updated_at = utcnow()
    # Anahtar değişince yeterlilik fingerprint'i değişir → yeniden benchmark gerekir.
    audit(db, user.id, "provider.rotate_key", "provider", p.id, secret_version=p.secret_version)
    return p


def add_models(db: Session, user: User, provider_id: uuid.UUID, model_ids: list[str]) -> list[Model]:
    require_admin(user)
    p = db.get(Provider, provider_id)
    if not p or p.deleted_at is not None:
        raise AppError("NOT_FOUND", "provider not found")
    existing = {m.remote_id for m in db.scalars(select(Model).where(Model.provider_id == p.id, Model.deleted_at.is_(None)))}
    out = []
    for rid in dict.fromkeys(m.strip() for m in model_ids if m.strip()):
        if rid in existing:
            continue
        m = Model(provider_id=p.id, remote_id=rid, display_name=rid, is_fixture=p.base_url.startswith(MOCK_HOSTS) and rid.startswith("fixture-"), transport_profile={})
        db.add(m)
        out.append(m)
    db.flush()
    audit(db, user.id, "model.add", "provider", p.id, models=[m.remote_id for m in out])
    return out


def update_model(db: Session, user: User, model_id: uuid.UUID, enabled: bool | None, display_name: str | None) -> Model:
    require_admin(user)
    m = db.get(Model, model_id)
    if not m or m.deleted_at is not None:
        raise AppError("NOT_FOUND", "model not found")
    if enabled is not None:
        m.enabled = enabled
    if display_name:
        m.display_name = display_name.strip()[:200]
    audit(db, user.id, "model.update", "model", m.id, enabled=m.enabled)
    return m


def delete_model(db: Session, user: User, model_id: uuid.UUID) -> None:
    require_admin(user)
    m = db.get(Model, model_id)
    if not m or m.deleted_at is not None:
        raise AppError("NOT_FOUND", "model not found")
    m.deleted_at = utcnow()
    m.enabled = False
    audit(db, user.id, "model.delete", "model", m.id)


def delete_provider(db: Session, user: User, provider_id: uuid.UUID) -> None:
    require_admin(user)
    p = db.get(Provider, provider_id)
    if not p or p.deleted_at is not None:
        raise AppError("NOT_FOUND", "provider not found")
    p.deleted_at = utcnow()
    p.secret_enc = ""
    db.execute(update(Model).where(Model.provider_id == p.id).values(deleted_at=utcnow(), enabled=False))
    audit(db, user.id, "provider.delete", "provider", p.id)


# ---------------------------------------------------------------- izinli model adresleri


def _providers_using(db: Session, url: str) -> int:
    return len(list(db.scalars(select(Provider.id).where(Provider.base_url == url, Provider.deleted_at.is_(None)))))


def list_allowed_endpoints(db: Session, user: User) -> list[dict]:
    """Sunucu ayarındakiler (yalnız metis.env'den değişir) ve arayüzden eklenenler (kaldırılabilir)."""
    require_admin(user)
    out = [{"id": None, "url": url, "source": "config", "created_at": None, "created_by": None, "providers": _providers_using(db, url)} for url in configured_endpoints()]
    for row in db.scalars(select(AllowedEndpoint).order_by(AllowedEndpoint.created_at)):
        by = db.get(User, row.created_by)
        out.append({"id": str(row.id), "url": row.url, "source": "ui", "created_at": row.created_at.isoformat(), "created_by": by.display_name if by else None, "providers": _providers_using(db, row.url)})
    return out


def allow_endpoint(db: Session, user: User, url: str) -> AllowedEndpoint:
    """Yönetici bir model adresine izin verir. Biçim, ağ aralığı (METIS_ENDPOINT_NETWORKS) ve üretimde https denetimleri
    sağlayıcı eklemedeki gibi yapılır; yalnız izin listesi şartı aranmaz. Zaten izinliyse var olan kayıt döner."""
    require_admin(user)
    clean = validate_endpoint(url, check_allowlist=False)
    if clean in configured_endpoints():
        raise AppError("ENDPOINT_CONFIGURED", "endpoint is already allowed by server configuration", url=clean)
    existing = db.scalar(select(AllowedEndpoint).where(AllowedEndpoint.url == clean))
    if existing:
        return existing
    row = AllowedEndpoint(url=clean, created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user.id, "endpoint.allow", "allowed_endpoint", row.id, url=clean)
    return row


def disallow_endpoint(db: Session, user: User, endpoint_id: uuid.UUID) -> None:
    require_admin(user)
    row = db.get(AllowedEndpoint, endpoint_id)
    if not row:
        raise AppError("NOT_FOUND", "allowed endpoint not found")
    if _providers_using(db, row.url):
        # Kaldırılırsa o sağlayıcının modelleri her çağrıda ENDPOINT_NOT_ALLOWED ile düşer: önce sağlayıcı silinmeli.
        raise AppError("ENDPOINT_IN_USE", "endpoint is used by a provider", url=row.url)
    db.delete(row)
    audit(db, user.id, "endpoint.disallow", "allowed_endpoint", row.id, url=row.url)


# ---------------------------------------------------------------- probe


def _record_probe(model_id: uuid.UUID, capability: str, status: str, detail: dict) -> None:
    with transaction() as db:
        db.add(ModelProbe(model_id=model_id, capability=capability, status=status, detail=detail))


def probe(model_id: uuid.UUID, actor_id: uuid.UUID) -> dict:
    """Bağlantı/kimlik, JSON nesnesi, json_schema desteği, düşünme parametresi ve kanıt sözleşmesi testi.
    Transport profili sonuçtan seçilir; desteklenmeyen parametre sessizce düşürülmez, profile yazılır."""
    with transaction() as db:
        model = db.get(Model, model_id)
        if not model or model.deleted_at is not None:
            raise AppError("NOT_FOUND", "model not found")
        provider = db.get(Provider, model.provider_id)
        db.expunge(model)
        db.expunge(provider)
    client = ModelClient()
    results: dict[str, dict] = {}

    def attempt(capability: str, profile: dict) -> bool:
        r = client.call(model, provider, prompt_id="probe-v1", payload={"echo": capability}, schema=contracts.ProbeOut, purpose="probe", repairs=0, max_tokens=200, profile_override=profile, validator=lambda o: o.get("echo") == capability)
        status = "tested_pass" if r.ok else "tested_fail"
        results[capability] = {"status": status, "error": r.error, "latency_ms": r.latency_ms}
        _record_probe(model.id, capability, status, {"error": r.error, "latency_ms": r.latency_ms, "profile": profile})
        return r.ok

    base_ok = attempt("connection", {"json_mode": "json_object", "thinking": "default"})
    auth_error = results["connection"]["error"] in ("HTTP_401", "HTTP_403")
    _record_probe(model.id, "auth", "tested_fail" if auth_error else ("tested_pass" if base_ok else "unknown"), {})
    if not base_ok and not auth_error:
        prompt_only_ok = attempt("prompt_only", {"json_mode": "prompt_only", "thinking": "default"})
    else:
        prompt_only_ok = False
    schema_ok = attempt("json_schema", {"json_mode": "json_schema", "thinking": "default"}) if base_ok else False
    json_mode = "json_schema" if schema_ok else ("json_object" if base_ok else ("prompt_only" if prompt_only_ok else "json_object"))
    thinking_ok = attempt("thinking_disabled", {"json_mode": json_mode, "thinking": "disabled"}) if (base_ok or prompt_only_ok) else False
    profile = {"json_mode": json_mode, "thinking": "disabled" if thinking_ok else "not_supported", "probed": True, "probed_at": datetime.now(UTC).isoformat(timespec="seconds")}
    contract_ok = False
    if base_ok or prompt_only_ok:
        case = _dataset_cases()[0]
        payload = {k: case["payload"][k] for k in ("question", "scope", "level", "conflict", "evidence")}
        model.transport_profile = profile
        r = client.call(model, provider, prompt_id=prompts.EVIDENCE, payload=payload, schema=contracts.EvidenceAnswer, purpose="probe", repairs=0, profile_override=profile)
        v = validate_answer(r.output, case["payload"]["evidence"], scope=case["payload"].get("scope")) if r.ok else None
        contract_ok = bool(v and v.structure_ok and v.decision == case["expected"]["decision"])
        results["evidence_contract"] = {"status": "tested_pass" if contract_ok else "tested_fail", "error": r.error or (None if contract_ok else "CONTRACT")}
        _record_probe(model.id, "evidence_contract", results["evidence_contract"]["status"], {"error": results["evidence_contract"]["error"]})
    else:
        _record_probe(model.id, "evidence_contract", "unknown", {"reason": "connection_failed"})
    with transaction() as db:
        m = db.get(Model, model.id)
        assert m is not None
        m.transport_profile = profile
        if contract_ok:
            m.failures = 0
            m.circuit_until = None
        from metis.core.audit import audit as _audit

        _audit(db, actor_id, "model.probe", "model", m.id, profile=profile, contract=contract_ok)
    return {"profile": profile, "results": results, "evidence_contract": contract_ok}


# ---------------------------------------------------------------- ortak benchmark


def _dataset_cases() -> list[dict]:
    """v1'in 6 vakalık seti + evals/'tan holdout ve taze vakalar (aynı v2 biçiminde)."""
    path = Path(__file__).resolve().parents[2] / "seed" / "benchmark-cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"]


def ensure_dataset(db: Session) -> BenchmarkDataset:
    ds = db.scalar(select(BenchmarkDataset).where(BenchmarkDataset.key == DATASET_KEY))
    if ds:
        return ds
    ds = BenchmarkDataset(key=DATASET_KEY, name="Ortak benchmark", version="1", description="v0.5.5 ortak seti + holdout/taze kanıt vakaları (26 vaka).")
    db.add(ds)
    db.flush()
    for c in _dataset_cases():
        db.add(BenchmarkCase(dataset_id=ds.id, case_key=c["id"], task=c["task"], payload=c["payload"], expected=c["expected"]))
    db.flush()
    return ds


def classify(case: BenchmarkCase, ok: bool, output: dict | None, error: str | None) -> dict:
    expected = case.expected["decision"]
    if not ok:
        return {"decision": None, "passed": False, "critical": False, "critical_kind": None, "error": error}
    v = validate_answer(output, case.payload["evidence"], case.payload.get("level", "short"), scope=case.payload.get("scope"))
    if not v.structure_ok:
        kind = "fake_source" if v.error == "quote_mismatch" else "invalid_structure"
        return {"decision": "VALIDATION_FAILED", "passed": False, "critical": kind == "fake_source", "critical_kind": kind if kind == "fake_source" else None, "error": v.error}
    decision = v.decision
    critical_kind = None
    if expected in ("NO_EVIDENCE", "NEEDS_SCOPE", "CONFLICTING") and decision in ("SUPPORTED", "PARTIAL"):
        critical_kind = "scope_violation" if expected == "NEEDS_SCOPE" else "false_answer"
    elif any(r in CRITICAL_REASONS for s in v.dropped for r in s.reasons):
        critical_kind = "fabricated_value"
    return {"decision": decision, "passed": decision == expected and critical_kind is None, "critical": critical_kind is not None, "critical_kind": critical_kind, "error": None, "guard": v.guard}


def start_benchmark(db: Session, user: User, model_id: uuid.UUID) -> BenchmarkRun:
    require_admin(user)
    model = db.get(Model, model_id)
    if not model or model.deleted_at is not None:
        raise AppError("NOT_FOUND", "model not found")
    provider = db.get(Provider, model.provider_id)
    ds = ensure_dataset(db)
    run = BenchmarkRun(model_id=model.id, dataset_id=ds.id, fingerprint=fingerprint(model, provider), state="queued", requested_by=user.id)  # type: ignore[arg-type]
    db.add(run)
    db.flush()
    audit(db, user.id, "benchmark.start", "model", model.id, run_id=run.id)
    return run


def execute_benchmark(run_id: uuid.UUID, should_stop=lambda: False) -> dict:  # noqa: ANN001
    with transaction() as db:
        run = db.get(BenchmarkRun, run_id, with_for_update=True)
        if not run or run.state not in ("queued", "running"):
            return {"skipped": True}
        run.state = "running"
        model = db.get(Model, run.model_id)
        provider = db.get(Provider, model.provider_id)  # type: ignore[union-attr]
        cases = list(db.scalars(select(BenchmarkCase).where(BenchmarkCase.dataset_id == run.dataset_id).order_by(BenchmarkCase.case_key)))
        for obj in (model, provider, *cases):
            db.expunge(obj)
    client = ModelClient()
    rows = []
    for case in cases:
        if should_stop():
            break
        payload = {k: case.payload[k] for k in ("question", "scope", "level", "conflict", "evidence")}
        r = client.call(model, provider, prompt_id=prompts.EVIDENCE, payload=payload, schema=contracts.EvidenceAnswer, purpose="benchmark", repairs=0)  # type: ignore[arg-type]
        verdict = classify(case, r.ok, r.output, r.error)
        rows.append((case, r, verdict))
        with transaction() as db:
            db.add(
                BenchmarkResult(
                    run_id=run_id, case_id=case.id, decision=verdict["decision"], passed=verdict["passed"], critical=verdict["critical"],
                    critical_kind=verdict["critical_kind"], latency_ms=r.latency_ms if r.ok else None, error=verdict["error"] or r.error, output=r.output or {},
                )
            )
    n = len(rows)
    passed = sum(1 for _, _, v in rows if v["passed"])
    critical = sum(1 for _, _, v in rows if v["critical"])
    errors = sum(1 for _, r, _ in rows if not r.ok)
    latencies = sorted(r.latency_ms for _, r, _ in rows if r.ok)
    metrics = {
        "n": n,
        "passed": passed,
        "critical_errors": critical,
        "critical_kinds": sorted({v["critical_kind"] for _, _, v in rows if v["critical_kind"]}),
        # Modelin kapsam dışı cevabını deterministik kapsam koruması durdurdu (geçti sayılır, ayrıca gösterilir).
        "scope_guarded": sum(1 for _, _, v in rows if v.get("guard") == "scope"),
        "errors": errors,
        "accuracy": (passed / n) if n else None,
        "p50_ms": statistics.median(latencies) if latencies else None,
        "p95_ms": latencies[math.ceil(len(latencies) * 0.95) - 1] if len(latencies) >= 30 else None,
        "p95_notice": "yetersiz örnek (n < 30)" if len(latencies) < 30 else None,
        "pass_rule": f"doğruluk ≥ {PASS_RATIO:.0%} ve kritik hata 0",
    }
    with transaction() as db:
        run = db.get(BenchmarkRun, run_id)
        assert run is not None
        complete = n == len(cases)
        run.state = "completed" if complete else "cancelled"
        run.metrics = metrics
        run.finished_at = utcnow()
        m = db.get(Model, run.model_id)
        p = db.get(Provider, m.provider_id)  # type: ignore[union-attr]
        if complete and fingerprint(m, p) == run.fingerprint:  # type: ignore[arg-type]
            ok = critical == 0 and n > 0 and passed / n >= PASS_RATIO and errors == 0
            db.add(ModelQualification(model_id=m.id, fingerprint=run.fingerprint, task_class="evidence_answer", passed=ok, critical_errors=critical, run_id=run.id))  # type: ignore[union-attr]
    return metrics


def latency_samples(db: Session, model: Model, provider: Provider) -> list[float]:
    fp = fingerprint(model, provider)
    rows = db.execute(
        select(BenchmarkResult.latency_ms)
        .join(BenchmarkRun, BenchmarkRun.id == BenchmarkResult.run_id)
        .where(BenchmarkRun.model_id == model.id, BenchmarkRun.fingerprint == fp, BenchmarkRun.hidden_at.is_(None), BenchmarkResult.latency_ms.is_not(None))
    ).scalars()
    return sorted(float(x) for x in rows)


def latency_summary(db: Session, model: Model, provider: Provider) -> dict:
    lat = latency_samples(db, model, provider)
    n = len(lat)
    return {
        "n": n,
        "p50_ms": statistics.median(lat) if lat else None,
        "p95_ms": lat[math.ceil(n * 0.95) - 1] if n >= 30 else None,
        "p95_notice": None if n >= 30 else "yetersiz örnek",
    }


def clear_results(db: Session, user: User, model_id: uuid.UUID | None) -> int:
    """Sonucu temizle: sunucuda gizli işaretlenir, polling ile geri gelmez; yeterlilik de düşer."""
    require_admin(user)
    now = utcnow()
    q_runs = update(BenchmarkRun).where(BenchmarkRun.hidden_at.is_(None))
    q_quals = update(ModelQualification).where(ModelQualification.hidden_at.is_(None))
    if model_id:
        q_runs = q_runs.where(BenchmarkRun.model_id == model_id)
        q_quals = q_quals.where(ModelQualification.model_id == model_id)
    count = db.execute(q_runs.values(hidden_at=now)).rowcount
    db.execute(q_quals.values(hidden_at=now))
    audit(db, user.id, "benchmark.clear", "model", model_id or "all", runs=count)
    return count or 0
