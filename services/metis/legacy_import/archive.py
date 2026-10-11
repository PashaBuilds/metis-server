"""v0.5.5 şifreli yedek dosyasını açar ve doğrular (reference/v0.5.5/deployment/desktop/recovery.py, backup.py).

Biçim: b"METISBK1" (8) + salt (16) + nonce (16) + tag (16) + şifreli veri. AES-256-GCM, AAD = b"METISBK1",
anahtar = scrypt(parola, salt, n=32768, r=8, p=1, dklen=32). Açılan ZIP: snapshot.zip + recovery.json.
snapshot.zip: manifest.json (format metis-backup-v1, schema 1|2) + blobs/xx/<sha256>.

Güvenlik: arşivden dosya yolu doğrudan çıkarılmaz (path traversal yok); her blob yalnız manifestteki
doğrulanmış sha256'dan türetilen adla okunur; boyut sınırları uygulanır; parola loglanmaz.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"METISBK1"
MAX_FILE = 512 * 1024 * 1024 + 2 * 1024 * 1024
MAX_SNAPSHOT = 512 * 1024 * 1024
MAX_MANIFEST = 64 * 1024 * 1024
MAX_BLOB = 10 * 1024 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")

V055_TABLES = {
    "identities", "credentials", "projects", "memberships", "sources", "source_revisions", "evidence", "pages",
    "page_revisions", "change_sets", "approvals", "publications", "search_entries", "findings", "work_items",
    "providers", "models", "provider_leases", "benchmark_runs", "answers", "audit_events", "idempotency", "settings",
    "extracted_claims", "open_decisions", "model_calls", "model_cache",
}


class ImportRefused(Exception):
    """İçe aktarma reddedildi; hiçbir şey değiştirilmedi."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LegacyBackup:
    sha256: str
    manifest: dict
    master_key: bytes
    blobs: dict[str, bytes] = field(default_factory=dict)

    @property
    def tables(self) -> dict[str, list[dict]]:
        return self.manifest["tables"]


def derive_key(password: str, salt: bytes) -> bytes:
    if len(password) < 12:
        raise ImportRefused("WRONG_PASSWORD", "Yedek parolası en az 12 karakter olmalı.")
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=32768, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)


def decrypt(raw: bytes, password: str) -> bytes:
    if len(raw) < 64 or raw[:8] != MAGIC:
        raise ImportRefused("NOT_A_BACKUP", "Geçerli bir METIS v0.5.5 şifreli yedeği değil.")
    salt, nonce, tag, body = raw[8:24], raw[24:40], raw[40:56], raw[56:]
    key = derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, body + tag, MAGIC)
    except InvalidTag:
        raise ImportRefused("WRONG_PASSWORD", "Yedek parolası yanlış veya dosya hasarlı.") from None


def open_backup(path: Path, password: str) -> LegacyBackup:
    if not path.is_file():
        raise ImportRefused("NOT_FOUND", "Yedek dosyası bulunamadı.")
    if path.stat().st_size > MAX_FILE:
        raise ImportRefused("TOO_LARGE", "Yedek dosyası boyut sınırını aşıyor.")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    plain = decrypt(raw, password)
    try:
        outer = zipfile.ZipFile(io.BytesIO(plain))
    except zipfile.BadZipFile:
        raise ImportRefused("CORRUPT", "Yedek içeriği geçersiz (ZIP değil).") from None
    with outer:
        if set(outer.namelist()) != {"snapshot.zip", "recovery.json"}:
            raise ImportRefused("CORRUPT", "Yedek içeriği beklenen iki dosyadan oluşmuyor.")
        if outer.getinfo("snapshot.zip").file_size > MAX_SNAPSHOT or outer.getinfo("recovery.json").file_size > 4096:
            raise ImportRefused("TOO_LARGE", "Yedek içeriğinin boyutu geçersiz.")
        try:
            recovery = json.loads(outer.read("recovery.json"))
            master = base64.b64decode(recovery["master"], validate=True)
        except (ValueError, KeyError, TypeError):
            raise ImportRefused("CORRUPT", "Kurtarma anahtarı okunamadı.") from None
        if recovery.get("format") != 1 or len(master) != 32:
            raise ImportRefused("CORRUPT", "Kurtarma anahtarı geçersiz.")
        snapshot_bytes = outer.read("snapshot.zip")
    try:
        snapshot = zipfile.ZipFile(io.BytesIO(snapshot_bytes))
    except zipfile.BadZipFile:
        raise ImportRefused("CORRUPT", "snapshot.zip okunamadı.") from None
    with snapshot:
        try:
            info = snapshot.getinfo("manifest.json")
        except KeyError:
            raise ImportRefused("CORRUPT", "manifest.json yok.") from None
        if info.file_size > MAX_MANIFEST:
            raise ImportRefused("TOO_LARGE", "manifest.json boyut sınırını aşıyor.")
        try:
            manifest = json.loads(snapshot.read(info))
        except ValueError:
            raise ImportRefused("CORRUPT", "manifest.json okunamadı.") from None
        if manifest.get("format") != "metis-backup-v1" or manifest.get("schema") not in (1, 2):
            raise ImportRefused("UNSUPPORTED", "Desteklenmeyen yedek şeması.")
        if manifest.get("master_key_fingerprint") != hashlib.sha256(master).hexdigest():
            raise ImportRefused("CORRUPT", "Kurtarma anahtarı manifestle eşleşmiyor.")
        tables = manifest.get("tables")
        if not isinstance(tables, dict) or not set(tables) <= V055_TABLES:
            raise ImportRefused("UNSUPPORTED", "Yedekte beklenmeyen tablolar var.")
        for name in V055_TABLES:
            tables.setdefault(name, [])
        blobs: dict[str, bytes] = {}
        for row in tables["source_revisions"]:
            digest_hex = str(row.get("hash", ""))
            if not HEX64.match(digest_hex):
                raise ImportRefused("BAD_HASH", f"Geçersiz kaynak özeti: {digest_hex[:80]!r}")
            if digest_hex in blobs:
                continue
            name = f"blobs/{digest_hex[:2]}/{digest_hex}"  # yol yalnız doğrulanmış özetten türetilir
            try:
                item = snapshot.getinfo(name)
            except KeyError:
                raise ImportRefused("MISSING_BLOB", f"Kaynak dosyası eksik: {digest_hex}") from None
            if item.file_size > MAX_BLOB:
                raise ImportRefused("TOO_LARGE", f"Kaynak dosyası boyut sınırını aşıyor: {digest_hex}")
            data = snapshot.read(item)
            if hashlib.sha256(data).hexdigest() != digest_hex:
                raise ImportRefused("HASH_MISMATCH", f"Kaynak dosyası özeti uyuşmuyor: {digest_hex}")
            blobs[digest_hex] = data
    return LegacyBackup(sha256=digest, manifest=manifest, master_key=master, blobs=blobs)
