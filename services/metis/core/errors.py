"""Hata kod kataloğu.

Servis katmanı `AppError` fırlatır; HTTP zarfına çeviri yalnız uygulama sınırında
(`metis.app`) yapılır. `message` İngilizce/teknik; kullanıcıya gösterilen Türkçe metin
frontend'de `i18n/tr.ts` içindeki kod kataloğundan gelir.
"""

from __future__ import annotations

from typing import Any

# code -> (http status, retryable)
CATALOG: dict[str, tuple[int, bool]] = {
    "UNAUTHENTICATED": (401, False),
    "INVALID_CREDENTIALS": (401, False),
    "PASSWORD_CHANGE_REQUIRED": (403, False),
    "CSRF_REJECTED": (403, False),
    "ORIGIN_REJECTED": (403, False),
    "FORBIDDEN": (403, False),
    "ROLE_REQUIRED": (403, False),
    "ADMIN_REQUIRED": (403, False),
    "HUMAN_REQUIRED": (403, False),
    "SELF_REVIEW_FORBIDDEN": (403, False),
    "SOURCE_ACCESS_CHANGED": (403, False),
    "SETUP_CODE_INVALID": (403, False),
    "NOT_FOUND": (404, False),
    "REVISION_CONFLICT": (409, False),
    "HASH_MISMATCH": (409, False),
    "INVALID_STATE": (409, False),
    "IDEMPOTENCY_CONFLICT": (409, False),
    "ALREADY_EXISTS": (409, False),
    "SETUP_ALREADY_DONE": (409, False),
    "LEASE_EXPIRED": (409, False),
    "DELETED_REFERENCE": (409, False),
    "WITHDRAWN": (409, False),
    "TARGET_NOT_EMPTY": (409, False),
    "VALIDATION_ERROR": (422, False),
    "WEAK_PASSWORD": (422, False),
    "UNSUPPORTED_FILE": (422, False),
    "FILE_TOO_LARGE": (413, False),
    "SCOPE_INVALID": (422, False),
    "SCOPE_MISMATCH": (422, False),
    "CLAIM_EVIDENCE": (422, False),
    "QUOTE_NOT_IN_EVIDENCE": (422, False),
    "EVIDENCE_REQUIRED": (422, False),
    "FIGURE_NOT_IMAGE": (422, False),
    "REVIEW_REQUIRED": (409, False),
    "CHECK_REQUIRED": (409, False),
    "CHECK_WARNINGS": (409, False),
    "FIGURE_MISSING": (422, False),
    "INVALID_ENDPOINT": (422, False),
    "ENDPOINT_NOT_ALLOWED": (422, False),
    "ADDRESS_NOT_ALLOWED": (422, False),
    "TLS_REQUIRED": (422, False),
    "MODEL_NOT_ELIGIBLE": (422, False),
    "MODEL_REQUIRED": (422, False),
    "REVIEW_CHECK_REQUIRED": (422, False),
    "REASON_REQUIRED": (422, False),
    "RATE_LIMITED": (429, True),
    "DNS_UNAVAILABLE": (503, True),
    "SECRET_STORE_UNAVAILABLE": (503, False),
    "SERVICE_UNAVAILABLE": (503, True),
    "INTERNAL": (500, True),
}


class AppError(Exception):
    def __init__(self, code: str, message: str = "", status: int | None = None, **details: Any) -> None:
        if code not in CATALOG and status is None:
            raise ValueError(f"Unknown error code {code}")
        default_status, retryable = CATALOG.get(code, (status or 500, False))
        self.code = code
        self.status = status or default_status
        self.message = message or code.replace("_", " ").lower()
        self.retryable = retryable
        self.details = details
        super().__init__(f"{code}: {self.message}")

    def envelope(self, correlation_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "correlation_id": correlation_id,
                "details": self.details,
            }
        }


def not_found(what: str = "record") -> AppError:
    return AppError("NOT_FOUND", f"{what} not found")
