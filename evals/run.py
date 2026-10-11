"""METIS prompt değerlendirmesi.

Kullanım:
  python evals/run.py --mode mock
  python evals/run.py --mode live --base-url https://llm.sirket.local/v1 --model deepseek-v4-flash-0731 \
      --api-key-env METIS_EVAL_API_KEY --json-mode json_object --thinking disabled [--ca-bundle C:\\certs\\ca.pem]

Mock modu deterministik referans modeli (metis.llm.mock_server) kullanır: sonuç hattın doğruluğunu gösterir,
model kalitesini DEĞİL. Canlı mod sonuçları ayrı raporlanır (sayı/payda/n ile). Rapor: evals/reports/.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from metis.llm import contracts, prompts
from metis.llm.client import build_body, build_messages
from metis.llm.transport import TransportError, completions_url, post_completion
from metis.llm.validators import check_sentence, validate_answer

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
REPORTS = ROOT / "reports"


class _Model:
    def __init__(self, remote_id: str) -> None:
        self.remote_id = remote_id


def call(base_url: str, model: str, prompt_id: str, payload: dict, schema, profile: dict, key: str, ca: str | None, timeout: float = 120):  # noqa: ANN001, ANN201
    messages, shape = build_messages(prompts.load(prompt_id).text, payload, schema, profile)
    body = build_body(_Model(model), messages, shape, schema.__name__, profile, 2000)  # type: ignore[arg-type]
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    started = time.perf_counter()
    try:
        resp = post_completion(completions_url(base_url), headers, body, timeout, ca)
        content = resp.data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        output = schema.model_validate(parsed).model_dump(mode="json")
        return output, None, (time.perf_counter() - started) * 1000
    except TransportError as exc:
        return None, exc.code, (time.perf_counter() - started) * 1000
    except (ValidationError, ValueError, KeyError, TypeError, IndexError):
        return None, "INVALID_RESPONSE", (time.perf_counter() - started) * 1000


def run_evidence(args, profile, key) -> dict:  # noqa: ANN001
    data = json.loads((CASES / "evidence.json").read_text(encoding="utf-8"))
    rows = []
    for case in data["cases"]:
        payload = {k: case[k] for k in ("question", "scope", "level", "conflict", "evidence")}
        output, error, ms = call(args.base_url, args.model, prompts.EVIDENCE, payload, contracts.EvidenceAnswer, profile, key, args.ca_bundle)
        if error:
            rows.append({"id": case["id"], "origin": case["origin"], "expected": case["expected"], "decision": None, "passed": False, "critical": False, "error": error, "latency_ms": round(ms, 1)})
            continue
        v = validate_answer(output, case["evidence"], case["level"])
        decision = v.decision if v.structure_ok else "VALIDATION_FAILED"
        critical = (not v.structure_ok) or (case["expected"] in ("NO_EVIDENCE", "NEEDS_SCOPE", "CONFLICTING") and decision in ("SUPPORTED", "PARTIAL"))
        rows.append(
            {
                "id": case["id"],
                "origin": case["origin"],
                "expected": case["expected"],
                "decision": decision,
                "passed": v.structure_ok and decision == case["expected"],
                "critical": critical,
                "sentences_kept": len(v.kept),
                "sentences_dropped": len(v.dropped),
                "drop_reasons": sorted({r for s in v.dropped for r in s.reasons}),
                "error": None if v.structure_ok else v.error,
                "latency_ms": round(ms, 1),
            }
        )
    return {"n": len(rows), "passed": sum(r["passed"] for r in rows), "critical": sum(r["critical"] for r in rows), "rows": rows}


def run_worker(args, profile, key) -> dict:  # noqa: ANN001
    data = json.loads((CASES / "worker.json").read_text(encoding="utf-8"))
    rows = []
    for case in data["cases"]:
        task = case["task"]
        if task == "extract":
            out, err, ms = call(args.base_url, args.model, prompts.EXTRACT, {"text": case["text"], "scope": {}}, contracts.Extraction, profile, key, args.ca_bundle)
            ok = False
            detail = {}
            if out:
                claim_text = " ".join(c["quote"] + " " + c["value"] for c in out["claims"])
                quotes_ok = all(c["quote"] in case["text"] for c in out["claims"]) and all(d["quote"] in case["text"] for d in out["open_decisions"])
                forbidden = [f for f in case.get("forbidden", []) if f.casefold() in claim_text.casefold()]
                ok = len(out["claims"]) == case["claims"] and len(out["open_decisions"]) == case["decisions"] and not forbidden and quotes_ok
                detail = {"claims": len(out["claims"]), "decisions": len(out["open_decisions"]), "forbidden_found": forbidden, "quotes_verbatim": quotes_ok}
            rows.append({"id": case["id"], "task": task, "passed": ok, "error": err, "detail": detail, "latency_ms": round(ms, 1)})
            continue
        if task == "compare":
            out, err, ms = call(args.base_url, args.model, prompts.PAGE_DIFF, {"kayit_a": case["note"], "kayit_b": case["page"]}, contracts.PageDiff, profile, key, args.ca_bundle)
        elif task == "judge":
            out, err, ms = call(args.base_url, args.model, prompts.CLAIM_CONFLICT, {"kayit_a": case["left"], "kayit_b": case["right"]}, contracts.ClaimJudgement, profile, key, args.ca_bundle)
        else:
            out, err, ms = call(args.base_url, args.model, prompts.RELATION, {"kayit_a": case["left"], "kayit_b": case["right"]}, contracts.RelationJudgement, profile, key, args.ca_bundle)
        verdict = out["verdict"] if out else None
        rows.append({"id": case["id"], "task": task, "expected": case["expected"], "verdict": verdict, "passed": verdict == case["expected"], "error": err, "latency_ms": round(ms, 1)})
    return {"n": len(rows), "passed": sum(r["passed"] for r in rows), "rows": rows}


def run_explanation() -> dict:
    data = json.loads((CASES / "explanation.json").read_text(encoding="utf-8"))
    statements = {b["claim_id"]: b["statement"] for b in data["bundle"]}
    rows = []
    for case in data["cases"]:
        r = check_sentence(case["sentence"], case["claim_ids"], statements)
        got = "kept" if r.kept else "dropped"
        ok = got == case["expected"] and (got == "kept" or case.get("reason") in r.reasons)
        rows.append({"id": case["id"], "expected": case["expected"], "got": got, "reasons": r.reasons, "passed": ok})
    return {"n": len(rows), "passed": sum(r["passed"] for r in rows), "rows": rows, "known_limits": data["known_limits"]}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def render_md(report: dict) -> str:
    lines = [f"# Değerlendirme raporu — {report['mode']}", "", f"Tarih: {report['at']}  ", f"Model: `{report['model']}`  ", f"Profil: `{json.dumps(report['profile'])}`", ""]
    if report["mode"] == "mock":
        lines += ["> Mock mod: deterministik referans model. Sonuç hattın doğruluğunu gösterir; gerçek model kalitesi değildir.", ""]
    for name, key in (("Kanıtlı cevap (evidence-explain-v1)", "evidence"), ("Worker prompt'ları", "worker"), ("Açıklama cümle denetimi (deterministik)", "explanation")):
        sec = report[key]
        extra = f", kritik hata {sec['critical']}" if "critical" in sec else ""
        lines += [f"## {name}", "", f"**{sec['passed']}/{sec['n']}** geçti{extra}.", ""]
        failed = [r for r in sec["rows"] if not r["passed"]]
        if failed:
            lines += ["Geçmeyenler:", ""] + [f"- `{r['id']}` — {json.dumps({k: v for k, v in r.items() if k not in ('id', 'passed')}, ensure_ascii=False)}" for r in failed] + [""]
    if report.get("by_origin"):
        lines += ["## Kaynağa göre (kanıtlı cevap)", ""] + [f"- {k}: {v['passed']}/{v['n']}" for k, v in report["by_origin"].items()] + [""]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["mock", "live"], default="mock")
    p.add_argument("--base-url", default="")
    p.add_argument("--model", default="fixture-reference")
    p.add_argument("--api-key-env", default="")
    p.add_argument("--json-mode", default="json_object", choices=["json_object", "json_schema", "prompt_only"])
    p.add_argument("--thinking", default="default", choices=["default", "disabled"])
    p.add_argument("--ca-bundle", default=None)
    p.add_argument("--out", default="")
    args = p.parse_args()
    server = None
    if args.mode == "mock":
        from metis.llm.mock_server import start_background

        port = free_port()
        server = start_background(port)
        args.base_url = f"http://127.0.0.1:{port}/v1"
    elif not args.base_url:
        print("--base-url gerekli", file=sys.stderr)
        return 2
    key = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
    profile = {"json_mode": args.json_mode, "thinking": args.thinking, "probed": False}
    report = {
        "mode": args.mode,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": args.model,
        "profile": profile,
        "evidence": run_evidence(args, profile, key),
        "worker": run_worker(args, profile, key),
        "explanation": run_explanation(),
    }
    by_origin: dict[str, dict] = {}
    for r in report["evidence"]["rows"]:
        o = by_origin.setdefault(r["origin"], {"n": 0, "passed": 0})
        o["n"] += 1
        o["passed"] += int(r["passed"])
    report["by_origin"] = by_origin
    if server:
        server.shutdown()
    REPORTS.mkdir(exist_ok=True)
    stem = args.out or f"{args.mode}-{args.model}"
    (REPORTS / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (REPORTS / f"{stem}.md").write_text(render_md(report), encoding="utf-8")
    ev, wk, ex = report["evidence"], report["worker"], report["explanation"]
    print(f"evidence {ev['passed']}/{ev['n']} (kritik {ev['critical']}) · worker {wk['passed']}/{wk['n']} · explanation {ex['passed']}/{ex['n']}")
    return 0 if args.mode == "live" or (ev["passed"] == ev["n"] and wk["passed"] == wk["n"] and ex["passed"] == ex["n"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
