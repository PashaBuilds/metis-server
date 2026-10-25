"""GitLab REST v4 erişimi (`PRIVATE-TOKEN`): issue, yorumlar (system notlar hariç), yüklenen dosyalar."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

from metis.core.errors import AppError
from metis.modules.external.confluence import SearchItem
from metis.modules.external.http import ExternalHttp

PROJECT_RE = re.compile(r"^[\w.-]+(/[\w.-]+)+$")
# Dosya adında "/" yok: "../" ile izinli proje dışına (ör. başka projenin dosyasına) çıkılamaz.
UPLOAD_RE = re.compile(r"\]\((/uploads/([0-9A-Za-z]{6,64})/([^/)\s]+))\)")
UPLOAD_LINK_RE = re.compile(r"!?\[[^\]]*\]\(/uploads/[0-9A-Za-z]{6,64}/([^/)\s]+)\)")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg")
STATES = {"opened": "Açık", "closed": "Kapalı"}


@dataclass(frozen=True)
class GitlabRef:
    project_path: str
    iid: int


@dataclass
class GitlabNote:
    author: str
    created_at: str
    body: str


@dataclass
class GitlabIssue:
    project_id: int
    project_path: str
    iid: int
    title: str
    description: str
    state: str
    labels: list[str]
    author: str
    created_at: str
    updated_at: str
    web_url: str
    confidential: bool
    notes: list[GitlabNote] = field(default_factory=list)


def _unrecognized() -> AppError:
    return AppError("EXTERNAL_URL_UNRECOGNIZED", "not a GitLab issue address of this connection")


def parse_ref(base_url: str, url: str) -> GitlabRef:
    base, target = urlsplit(base_url.rstrip("/")), urlsplit(url.strip())
    if not url.strip().startswith(("http://", "https://")):
        raise _unrecognized()
    if (target.scheme, (target.hostname or "").lower(), target.port) != (base.scheme, (base.hostname or "").lower(), base.port):
        raise _unrecognized()
    if not target.path.startswith(base.path):
        raise _unrecognized()
    m = re.match(r"^/(.+?)(?:/-)?/issues/(\d+)/?$", target.path[len(base.path) :])
    if not m or not PROJECT_RE.match(m.group(1)):
        raise _unrecognized()
    return GitlabRef(m.group(1), int(m.group(2)))


def _project(path_or_id: str | int) -> str:
    return quote(str(path_or_id), safe="")


def fetch(http: ExternalHttp, ref: GitlabRef, max_pages: int = 20) -> GitlabIssue:
    data = http.get_json(f"/api/v4/projects/{_project(ref.project_path)}/issues/{ref.iid}")
    try:
        issue = GitlabIssue(
            project_id=int(data["project_id"]),
            project_path=ref.project_path,
            iid=int(data["iid"]),
            title=str(data.get("title") or "")[:240],
            description=str(data.get("description") or ""),
            state=str(data.get("state") or ""),
            labels=[str(x) for x in data.get("labels") or []],
            author=str((data.get("author") or {}).get("name") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            web_url=str(data.get("web_url") or ""),
            confidential=bool(data.get("confidential")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("EXTERNAL_BAD_RESPONSE", "unexpected GitLab issue shape") from exc
    if issue.confidential:
        return issue  # gizli issue alınmaz (servis reddeder); yorumları hiç okunmaz
    for page in range(1, max_pages + 1):
        notes = http.get_json(
            f"/api/v4/projects/{issue.project_id}/issues/{issue.iid}/notes",
            {"sort": "asc", "order_by": "created_at", "per_page": 100, "page": page},
        )
        if not isinstance(notes, list):
            raise AppError("EXTERNAL_BAD_RESPONSE", "unexpected GitLab notes shape")
        for n in notes:
            # Sistem notları ve dahili (internal/confidential) yorumlar alınmaz: yayımlanınca tüm üyelere açılırdı.
            if n.get("system") or n.get("internal") or n.get("confidential"):
                continue
            issue.notes.append(GitlabNote(str((n.get("author") or {}).get("name") or ""), str(n.get("created_at") or ""), str(n.get("body") or "")))
        if len(notes) < 100:
            break
    return issue


def issue_markdown(issue: GitlabIssue) -> str:
    meta = [f"**Durum:** {STATES.get(issue.state, issue.state)}"]
    if issue.labels:
        meta.append(f"**Etiketler:** {', '.join(issue.labels)}")
    if issue.author:
        meta.append(f"**Açan:** {issue.author}")
    if issue.created_at:
        meta.append(issue.created_at[:10])
    parts = [" · ".join(meta)]
    if issue.description.strip():
        parts.append(issue.description.strip())
    if issue.notes:
        parts.append("## Yorumlar")
        for n in issue.notes:
            parts.append(f"### {n.author or 'Bilinmeyen'} — {n.created_at[:10]}")
            if n.body.strip():
                parts.append(n.body.strip())
    return "\n\n".join(parts).replace("\r\n", "\n")


def upload_refs(markdown: str) -> list[tuple[str, str]]:
    out: dict[tuple[str, str], None] = {}
    for m in UPLOAD_RE.finditer(markdown):
        if m.group(3) not in (".", ".."):
            out[(m.group(2), m.group(3))] = None
    return list(out)


def replace_uploads(markdown: str) -> str:
    """GitLab'a göreli yükleme bağlantıları METIS'te açılmaz: `[Görsel: ad]` / `[Ek: ad]` işaretine döner (dosya ek olur)."""

    def marker(m: re.Match[str]) -> str:
        name = m.group(1)
        return f"[Görsel: {name}]" if name.lower().endswith(IMAGE_EXT) else f"[Ek: {name}]"

    return UPLOAD_LINK_RE.sub(marker, markdown)


def download_upload(http: ExternalHttp, project_id: int, secret: str, filename: str, limit: int) -> bytes:
    if "/" in filename or filename in (".", ".."):
        raise AppError("EXTERNAL_BAD_RESPONSE", "invalid upload name")
    return http.get_bytes(f"/api/v4/projects/{int(project_id)}/uploads/{quote(secret, safe='')}/{quote(filename, safe='')}", limit)


def search(http: ExternalHttp, projects: list[str], q: str) -> list[SearchItem]:
    out: list[SearchItem] = []
    for path in projects:
        if not PROJECT_RE.match(path):
            continue
        rows = http.get_json(f"/api/v4/projects/{_project(path)}/issues", {"search": q, "per_page": 20, "order_by": "updated_at"})
        for r in rows if isinstance(rows, list) else []:
            if r.get("confidential"):
                continue
            out.append(SearchItem(key=f"{path}#{r.get('iid')}", title=str(r.get("title") or ""), url=str(r.get("web_url") or ""), container=path))
    return out[:40]


def current_user(http: ExternalHttp) -> str:
    data = http.get_json("/api/v4/user")
    if not isinstance(data, dict) or not data.get("username"):
        raise AppError("EXTERNAL_UNAUTHORIZED", "token not accepted")
    return str(data["username"])
