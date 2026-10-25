"""Confluence Server/Data Center REST erişimi (kişisel erişim anahtarı, `Authorization: Bearer`)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote_plus, urlsplit

from metis.core.errors import AppError
from metis.modules.external.http import ExternalHttp

SPACE_RE = re.compile(r"^[A-Za-z0-9_~-]{1,255}$")
PAGE_EXPAND = (
    "body.storage,version,space,ancestors,"
    "restrictions.read.restrictions.user,restrictions.read.restrictions.group,"
    "ancestors.restrictions.read.restrictions.user,ancestors.restrictions.read.restrictions.group"
)


@dataclass(frozen=True)
class ConfluenceRef:
    page_id: str | None
    space: str | None
    title: str | None


@dataclass
class ConfluencePage:
    id: str
    title: str
    space: str
    version: int
    url: str
    storage: str
    restricted: bool


@dataclass
class RemoteFile:
    filename: str
    media_type: str
    size: int
    download: str


@dataclass
class SearchItem:
    key: str
    title: str
    url: str
    container: str


def _unrecognized() -> AppError:
    return AppError("EXTERNAL_URL_UNRECOGNIZED", "not a Confluence page address of this connection")


def _relative(base_url: str, url: str) -> tuple[str, dict[str, list[str]]]:
    base, target = urlsplit(base_url.rstrip("/")), urlsplit(url.strip())
    if (target.scheme, (target.hostname or "").lower(), target.port) != (base.scheme, (base.hostname or "").lower(), base.port):
        raise _unrecognized()
    if not target.path.startswith(base.path):
        raise _unrecognized()
    return target.path[len(base.path) :], parse_qs(target.query)


def parse_ref(base_url: str, url: str) -> ConfluenceRef:
    if not url.strip().startswith(("http://", "https://")):
        raise _unrecognized()
    path, query = _relative(base_url, url)
    if query.get("pageId", [""])[0].isdigit():
        return ConfluenceRef(query["pageId"][0], None, None)
    m = re.match(r"^/spaces/([^/]+)/pages/(\d+)(?:/|$)", path)
    if m:
        return ConfluenceRef(m.group(2), unquote_plus(m.group(1)), None)
    m = re.match(r"^/display/([^/]+)/([^/?#]+)", path)
    if m:
        return ConfluenceRef(None, unquote_plus(m.group(1)), unquote_plus(m.group(2)))
    raise _unrecognized()


def _restricted(content: dict) -> bool:
    def has(node: dict) -> bool:
        read = ((node.get("restrictions") or {}).get("read") or {}).get("restrictions") or {}
        users = (read.get("user") or {}).get("results") or []
        groups = (read.get("group") or {}).get("results") or []
        return bool(users or groups)

    return has(content) or any(has(a) for a in content.get("ancestors") or [])


def _page(http: ExternalHttp, data: dict) -> ConfluencePage:
    try:
        return ConfluencePage(
            id=str(data["id"]),
            title=str(data.get("title") or "")[:240],
            space=str((data.get("space") or {}).get("key") or ""),
            version=int((data.get("version") or {}).get("number") or 0),
            url=f"{http.base_url}/pages/viewpage.action?pageId={data['id']}",
            storage=str(((data.get("body") or {}).get("storage") or {}).get("value") or ""),
            restricted=_restricted(data),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("EXTERNAL_BAD_RESPONSE", "unexpected Confluence page shape") from exc


def fetch(http: ExternalHttp, ref: ConfluenceRef) -> ConfluencePage:
    if ref.page_id:
        return _page(http, http.get_json(f"/rest/api/content/{ref.page_id}", {"expand": PAGE_EXPAND}))
    data = http.get_json("/rest/api/content", {"spaceKey": ref.space, "title": ref.title, "type": "page", "expand": PAGE_EXPAND})
    results = (data or {}).get("results") or []
    if not results:
        raise AppError("EXTERNAL_NOT_FOUND", "remote item not found")
    return _page(http, results[0])


def attachments(http: ExternalHttp, page_id: str, cap: int = 200) -> list[RemoteFile]:
    out: list[RemoteFile] = []
    start = 0
    while len(out) < cap:
        data = http.get_json(f"/rest/api/content/{page_id}/child/attachment", {"limit": 100, "start": start})
        results = (data or {}).get("results") or []
        for a in results:
            ext = a.get("extensions") or {}
            out.append(
                RemoteFile(
                    filename=str(a.get("title") or ""),
                    media_type=str(ext.get("mediaType") or ""),
                    size=int(ext.get("fileSize") or 0),
                    download=str((a.get("_links") or {}).get("download") or ""),
                )
            )
        if len(results) < 100:
            break
        start += len(results)
    return out[:cap]


def _cql_text(q: str) -> str:
    return q.replace("\\", " ").replace('"', " ").strip()


def search(http: ExternalHttp, spaces: list[str], q: str) -> list[SearchItem]:
    keys = ",".join(f'"{s}"' for s in spaces if SPACE_RE.match(s))
    if not keys:
        return []
    cql = f'type=page AND space in ({keys}) AND title ~ "{_cql_text(q)}"'
    expand = "space,restrictions.read.restrictions.user,restrictions.read.restrictions.group"
    data = http.get_json("/rest/api/content/search", {"cql": cql, "limit": 20, "expand": expand})
    out = []
    for r in (data or {}).get("results") or []:
        rid = str(r.get("id") or "")
        if not rid.isdigit() or _restricted(r):  # kısıtlı sayfanın başlığı da listelenmez
            continue
        out.append(
            SearchItem(
                key=rid,
                title=str(r.get("title") or ""),
                url=f"{http.base_url}/pages/viewpage.action?pageId={rid}",
                container=str((r.get("space") or {}).get("key") or ""),
            )
        )
    return out


def current_user(http: ExternalHttp) -> str:
    data = http.get_json("/rest/api/user/current")
    if not isinstance(data, dict) or data.get("type") == "anonymous" or not data.get("username"):
        raise AppError("EXTERNAL_UNAUTHORIZED", "token not accepted")
    return str(data["username"])
