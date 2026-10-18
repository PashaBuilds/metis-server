"""Tek, sınırlı model istemcisi: kalıcı `model_calls` logu, doğrulanan cache, DB tabanlı sağlayıcı semaforu.

Taşıma katmanının uygulama yetkisi yoktur. Çağıran taraf bağlamı çağrıdan önce yetkilendirir ve
sonucu kaydetmeden önce yetkiyi yeniden kontrol eder.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, func, select

from metis.core.config import get_settings
from metis.core.db import transaction, utcnow
from metis.core.errors import AppError
from metis.core.models import Model, ModelCache, ModelCall, Provider, ProviderSlot
from metis.core.security import decrypt_secret, validate_endpoint
from metis.core.util import hash_json
from metis.llm import prompts
from metis.llm.transport import TransportError, completions_url, post_completion

DEFAULT_PROFILE = {"json_mode": "json_object", "thinking": "default", "probed": False}
RETRYABLE_HTTP = {"HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504"}


@dataclass
class CallResult:
    ok: bool
    output: dict | None = None
    error: str | None = None
    call_id: uuid.UUID | None = None
    latency_ms: float = 0.0
    usage: dict = field(default_factory=dict)
    cached: bool = False
    raw: str = ""


def profile_of(model: Model) -> dict:
    return {**DEFAULT_PROFILE, **(model.transport_profile or {})}


def build_messages(system: str, payload: Any, schema: type[BaseModel] | None, profile: dict) -> tuple[list[dict], dict | None]:
    shape = schema.model_json_schema() if schema else None
    content = system
    if shape and profile.get("json_mode") != "json_schema":
        content += "\n\nRequired JSON schema:\n" + json.dumps(shape, ensure_ascii=False)
    return [
        {"role": "system", "content": content},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ], shape


def build_body(model: Model, messages: list[dict], shape: dict | None, schema_name: str, profile: dict, max_tokens: int) -> dict:
    body: dict[str, Any] = {"model": model.remote_id, "messages": messages, "temperature": 0, "max_tokens": max_tokens, "stream": False}
    mode = profile.get("json_mode")
    if mode == "json_schema" and shape:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": shape}}
    elif mode == "json_object":
        body["response_format"] = {"type": "json_object"}
    if profile.get("thinking") == "disabled":
        body["thinking"] = {"type": "disabled"}
    return body


def _acquire_slot(provider_id: uuid.UUID, limit: int, budget_s: float) -> uuid.UUID | None:
    deadline = time.monotonic() + budget_s
    pause = 0.05
    while True:
        with transaction() as db:
            db.scalar(select(Provider.id).where(Provider.id == provider_id).with_for_update())
            db.execute(delete(ProviderSlot).where(ProviderSlot.provider_id == provider_id, ProviderSlot.expires_at < utcnow()))
            used = db.scalar(select(func.count()).select_from(ProviderSlot).where(ProviderSlot.provider_id == provider_id)) or 0
            if used < max(1, limit):
                slot = ProviderSlot(provider_id=provider_id, expires_at=utcnow() + timedelta(seconds=budget_s + 10))
                db.add(slot)
                db.flush()
                return slot.id
        if time.monotonic() >= deadline:
            return None
        # Sıra beklerken veritabanını sık yoklamamak için geri çekilme (50 ms → en çok 0,5 sn, rastgele kaydırmalı).
        time.sleep(pause * (0.5 + random.random()))
        pause = min(0.5, pause * 1.5)


def _release_slot(slot_id: uuid.UUID) -> None:
    with transaction() as db:
        db.execute(delete(ProviderSlot).where(ProviderSlot.id == slot_id))


def _record_outcome(model_id: uuid.UUID, ok: bool, error: str | None) -> None:
    """Devre kesici: art arda 3 bağlantı hatası → 60 sn bekleme. Doğrulama hataları devreyi açmaz."""
    with transaction() as db:
        model = db.get(Model, model_id, with_for_update=True)
        if model is None:
            return
        if ok:
            model.failures = 0
            model.circuit_until = None
        elif error and error not in ("INVALID_RESPONSE", "VALIDATION", "PROVIDER_BUSY", "BUDGET_EXCEEDED"):
            model.failures += 1
            if model.failures >= 3:
                model.circuit_until = utcnow() + timedelta(seconds=60)


class ModelClient:
    def call(
        self,
        model: Model,
        provider: Provider,
        *,
        prompt_id: str,
        payload: Any,
        schema: type[BaseModel] | None,
        validator: Callable[[dict], bool] | None = None,
        purpose: str = "mentor",
        cache: bool = True,
        max_tokens: int = 1500,
        repairs: int = 1,
        timeout_s: float | None = None,
        job_id: uuid.UUID | None = None,
        answer_id: uuid.UUID | None = None,
        profile_override: dict | None = None,
    ) -> CallResult:
        if not 1 <= max_tokens <= 16000 or repairs not in (0, 1, 2):
            raise ValueError("invalid model call budget")
        prompt = prompts.load(prompt_id)
        profile = profile_override or profile_of(model)
        if purpose in ("benchmark", "probe"):
            cache = False  # benchmark ve probe cache kullanmaz
        messages, shape = build_messages(prompt.text, payload, schema, profile)
        key = hash_json(
            {
                "prompt": prompt.id,
                "prompt_sha": prompt.sha256,
                "messages": messages,
                "schema": shape,
                "model": str(model.id),
                "remote": model.remote_id,
                "config": model.config_version,
                "provider": str(provider.id),
                "url": provider.base_url,
                "secret_version": provider.secret_version,
                "max_tokens": max_tokens,
                "profile": profile,
            }
        )
        budget = float(min(provider.timeout_s, timeout_s or provider.timeout_s))
        started = time.perf_counter()

        if cache:
            with transaction() as db:
                hit = db.get(ModelCache, key)
                if hit is not None:
                    output = hit.output
                    try:
                        if schema:
                            output = schema.model_validate(output).model_dump(mode="json")
                        valid = validator(output) if validator else True
                    except (ValidationError, TypeError, ValueError):
                        valid = False
                    if valid:  # cache'ten gelen çıktı da yeniden doğrulanır
                        call = ModelCall(
                            model_id=model.id, prompt_id=prompt.id, prompt_version=prompt.version, purpose=purpose, input_hash=key,
                            state="cached", parsed_output=output, cached_from=hit.call_id, job_id=job_id, answer_id=answer_id, latency_ms=0,
                        )
                        db.add(call)
                        db.flush()
                        return CallResult(ok=True, output=output, call_id=call.id, cached=True)

        slot = None
        try:
            try:
                url = completions_url(validate_endpoint(provider.base_url))
                secret = decrypt_secret(provider.secret_enc) if provider.secret_enc else ""
            except AppError as exc:
                return self._fail(model, prompt, purpose, key, job_id, answer_id, exc.code, started)
            except TransportError as exc:
                return self._fail(model, prompt, purpose, key, job_id, answer_id, exc.code, started)
            slot = _acquire_slot(provider.id, provider.max_concurrency, budget)
            if slot is None:
                return self._fail(model, prompt, purpose, key, job_id, answer_id, "PROVIDER_BUSY", started)
            attempt = 0
            http_retries = 0
            current = list(messages)
            while True:
                left = budget - (time.perf_counter() - started)
                if left <= 0:
                    return self._fail(model, prompt, purpose, key, job_id, answer_id, "BUDGET_EXCEEDED", started)
                with transaction() as db:
                    call = ModelCall(
                        model_id=model.id, prompt_id=prompt.id, prompt_version=prompt.version, purpose=purpose, input_hash=key,
                        state="running", attempt=attempt, job_id=job_id, answer_id=answer_id,
                    )
                    db.add(call)
                    db.flush()
                    call_id = call.id
                body = build_body(model, current, shape, schema.__name__ if schema else "output", profile, max_tokens)
                headers = {"Content-Type": "application/json", "X-Request-ID": str(call_id)}
                if secret:
                    headers["Authorization"] = f"Bearer {secret}"
                raw_text, output, usage, error = "", None, {}, None
                attempt_start = time.perf_counter()
                try:
                    resp = post_completion(url, headers, body, left, provider.ca_bundle_ref or get_settings().ca_bundle or None)
                    usage = resp.data.get("usage") or {}
                    content = resp.data["choices"][0]["message"]["content"]
                    if not isinstance(content, str):
                        raise ValueError("content")
                    raw_text = content
                    parsed = json.loads(content)
                    if not isinstance(parsed, dict):
                        raise ValueError("object")
                    output = schema.model_validate(parsed).model_dump(mode="json") if schema else parsed
                    if validator and not validator(output):
                        error = "VALIDATION"
                except TransportError as exc:
                    error = exc.code
                    raw_text = exc.body
                except (ValidationError, ValueError, KeyError, TypeError, IndexError):
                    error = "INVALID_RESPONSE"
                duration = round((time.perf_counter() - attempt_start) * 1000, 2)
                with transaction() as db:
                    row = db.get(ModelCall, call_id)
                    assert row is not None
                    row.raw_output = raw_text[:200_000]
                    row.parsed_output = output if (output is not None and error is None) else {}
                    row.usage = usage if isinstance(usage, dict) else {}
                    row.latency_ms = duration
                    row.error = error
                    row.state = "failed" if error else "completed"
                    if not error and cache:
                        if db.get(ModelCache, key) is None:
                            db.add(ModelCache(key=key, call_id=call_id, output=output))
                if not error:
                    _record_outcome(model.id, True, None)
                    return CallResult(ok=True, output=output, call_id=call_id, latency_ms=round((time.perf_counter() - started) * 1000, 2), usage=usage, raw=raw_text)
                if error in ("INVALID_RESPONSE", "VALIDATION") and attempt < repairs:
                    attempt += 1
                    current = [
                        *messages,
                        {"role": "assistant", "content": raw_text[:20_000]},
                        {"role": "user", "content": "The previous response failed validation. Return only one JSON object that matches the required schema and the exact supplied evidence. Do not invent missing facts."},
                    ]
                    continue
                if error in RETRYABLE_HTTP and http_retries < 2:
                    http_retries += 1
                    attempt += 1
                    time.sleep(min(2.0, 0.25 * (2**http_retries)) * (0.5 + random.random()))
                    continue
                _record_outcome(model.id, False, error)
                return CallResult(ok=False, error=error, call_id=call_id, latency_ms=round((time.perf_counter() - started) * 1000, 2), usage=usage, raw=raw_text)
        finally:
            if slot is not None:
                _release_slot(slot)

    def _fail(self, model, prompt, purpose, key, job_id, answer_id, code, started) -> CallResult:  # noqa: ANN001
        with transaction() as db:
            call = ModelCall(
                model_id=model.id, prompt_id=prompt.id, prompt_version=prompt.version, purpose=purpose, input_hash=key,
                state="failed", error=code, job_id=job_id, answer_id=answer_id, latency_ms=0,
            )
            db.add(call)
            db.flush()
            call_id = call.id
        if code not in ("PROVIDER_BUSY", "BUDGET_EXCEEDED"):
            _record_outcome(model.id, False, code)
        return CallResult(ok=False, error=code, call_id=call_id, latency_ms=round((time.perf_counter() - started) * 1000, 2))
