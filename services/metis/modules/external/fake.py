"""Kurgusal Confluence + GitLab sunucusu (testler ve geliştirme denemesi). Gerçek şirket verisi içermez.

`handle(request)` hem testlerde `httpx.MockTransport` ile hem de `metis mock-sources` komutuyla (http.server) çalışır.
Confluence `/confluence` bağlam yolu altında, GitLab kökte (`/api/v4`). Geçerli token: `kurgusal-token`.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import httpx

TOKEN = "kurgusal-token"  # noqa: S105 — kurgusal sunucunun sabit deneme anahtarı
PNG = b"\x89PNG\r\n\x1a\n" + b"\x05" * 64
PDF = b"%PDF-1.4\n% kurgusal\n%%EOF\n"

STORAGE_1001 = (
    "<h2>Bağlantı eğitimi</h2>"
    "<p>Kart açılışında <code>LTSSM_STATE</code> değeri <strong>0x11</strong> olana kadar beklenir.</p>"
    "<table><tbody><tr><th>Yazmaç</th><th>Değer</th></tr><tr><td>PCIE_CTRL</td><td>0x1</td></tr></tbody></table>"
    '<ac:image><ri:attachment ri:filename="sema.png"/></ac:image>'
    "<h2>Sorun giderme</h2>"
    '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">c</ac:parameter>'
    "<ac:plain-text-body><![CDATA[pcie_link_up(dev);]]></ac:plain-text-body></ac:structured-macro>"
    '<ac:structured-macro ac:name="toc"/>'
)

PAGES = {
    "1001": {"title": "PCIe Notu", "space": "BSP", "version": 3, "storage": STORAGE_1001, "restricted": False},
    "1002": {"title": "Kısıtlı Sayfa", "space": "BSP", "version": 1, "storage": "<p>Gizli.</p>", "restricted": True},
    "1003": {"title": "Başka Alan", "space": "GIZLI", "version": 1, "storage": "<p>Başka alan.</p>", "restricted": False},
    "1004": {"title": "Saat Ağacı", "space": "BSP", "version": 2, "storage": "<p>Saat kaynağı <code>CLK_SRC</code> seçimi.</p>", "restricted": False},
}
ATTACHMENTS = {
    "1001": [
        ("sema.png", "image/png", PNG),
        ("veri.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK\x03\x04kurgusal"),
        ("kilavuz.pdf", "application/pdf", PDF),
    ]
}

ISSUES = {
    ("ekip/bsp", 7): {
        "title": "PCIe bağlantısı kurulmuyor",
        "description": "Kart açılışta `LTSSM_STATE` 0x11'de kalıyor.\n\n![log](/uploads/abc123/log.png)",
        "state": "closed",
        "labels": ["pcie", "sürücü"],
        "confidential": False,
        "notes": [
            {"system": True, "author": "Kurgusal Kişi", "created_at": "2026-01-05T09:05:00.000Z", "body": "added ~pcie label"},
            {"system": False, "author": "Kurgusal İkinci", "created_at": "2026-01-06T08:30:00.000Z", "body": "Saat kaynağını değiştirdin mi?"},
            {"system": False, "author": "Kurgusal Kişi", "created_at": "2026-01-06T11:00:00.000Z", "body": "Evet, `CLK_SRC` = 2 yapınca düzeldi."},
        ],
    },
    ("ekip/bsp", 8): {"title": "Gizli konu", "description": "Gizli.", "state": "opened", "labels": [], "confidential": True, "notes": []},
}
PROJECT_IDS = {"ekip/bsp": 5}


def _json(data: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(data).encode(), headers={"Content-Type": "application/json"})


def _restrictions(restricted: bool) -> dict:
    groups = [{"type": "group", "name": "kurgusal-kisitli"}] if restricted else []
    return {"read": {"restrictions": {"user": {"results": []}, "group": {"results": groups}}}}


def _page(pid: str) -> dict:
    p = PAGES[pid]
    return {
        "id": pid,
        "type": "page",
        "title": p["title"],
        "space": {"key": p["space"]},
        "version": {"number": p["version"]},
        "body": {"storage": {"value": p["storage"], "representation": "storage"}},
        "ancestors": [],
        "restrictions": _restrictions(bool(p["restricted"])),
        "_links": {"webui": f"/pages/viewpage.action?pageId={pid}"},
    }


def _confluence(request: httpx.Request, path: str) -> httpx.Response:
    if request.headers.get("Authorization") != f"Bearer {TOKEN}":
        return _json({"message": "unauthorized"}, 401)
    q = request.url.params
    if path == "/rest/api/user/current":
        return _json({"type": "known", "username": "kurgusal.okur"})
    if path == "/rest/api/content":
        hits = [pid for pid, p in PAGES.items() if p["space"] == q.get("spaceKey") and p["title"] == q.get("title")]
        return _json({"results": [_page(h) for h in hits], "size": len(hits)})
    if path == "/rest/api/content/search":
        cql = q.get("cql", "")
        spaces = re.findall(r'"([^"]+)"', cql.split(") AND title", 1)[0]) if "space in (" in cql else []
        m = re.search(r'title ~ "([^"]*)"', cql)
        term = (m.group(1) if m else "").casefold()
        hits = [pid for pid, p in PAGES.items() if p["space"] in spaces and term in str(p["title"]).casefold()]
        return _json({"results": [{"id": h, "title": PAGES[h]["title"], "space": {"key": PAGES[h]["space"]}} for h in hits]})
    m = re.fullmatch(r"/rest/api/content/(\d+)", path)
    if m:
        return _json(_page(m.group(1))) if m.group(1) in PAGES else _json({"message": "not found"}, 404)
    m = re.fullmatch(r"/rest/api/content/(\d+)/child/attachment", path)
    if m:
        start = int(q.get("start", "0"))
        files = ATTACHMENTS.get(m.group(1), [])[start:]
        return _json(
            {
                "results": [
                    {
                        "title": name,
                        "extensions": {"mediaType": media, "fileSize": len(data)},
                        "_links": {"download": f"/download/attachments/{m.group(1)}/{name}?version=1"},
                    }
                    for name, media, data in files
                ]
            }
        )
    m = re.fullmatch(r"/download/attachments/(\d+)/([^/]+)", path)
    if m:
        for name, media, data in ATTACHMENTS.get(m.group(1), []):
            if name == unquote(m.group(2)):
                return httpx.Response(200, content=data, headers={"Content-Type": media})
    return _json({"message": "not found"}, 404)


def _issue(path: str, iid: int) -> dict:
    i = ISSUES[(path, iid)]
    return {
        "project_id": PROJECT_IDS[path],
        "iid": iid,
        "title": i["title"],
        "description": i["description"],
        "state": i["state"],
        "labels": i["labels"],
        "confidential": i["confidential"],
        "author": {"name": "Kurgusal Kişi"},
        "created_at": "2026-01-05T09:00:00.000Z",
        "updated_at": "2026-01-07T10:00:00.000Z",
        "web_url": f"http://127.0.0.1:9160/{path}/-/issues/{iid}",
    }


def _gitlab(request: httpx.Request, raw: str) -> httpx.Response:
    if request.headers.get("PRIVATE-TOKEN") != TOKEN:
        return _json({"message": "401 Unauthorized"}, 401)
    if raw == "/api/v4/user":
        return _json({"username": "kurgusal.okur"})
    by_id = {v: k for k, v in PROJECT_IDS.items()}
    m = re.fullmatch(r"/api/v4/projects/([^/]+)/issues/(\d+)", raw)
    if m:
        path = unquote(m.group(1))
        key = (path, int(m.group(2)))
        return _json(_issue(*key)) if key in ISSUES else _json({"message": "404 Not found"}, 404)
    m = re.fullmatch(r"/api/v4/projects/(\d+)/issues/(\d+)/notes", raw)
    if m:
        path = by_id.get(int(m.group(1)), "")
        issue = ISSUES.get((path, int(m.group(2))))
        if issue is None:
            return _json({"message": "404 Not found"}, 404)
        if request.url.params.get("page", "1") != "1":
            return _json([])
        return _json([{"system": n["system"], "author": {"name": n["author"]}, "created_at": n["created_at"], "body": n["body"]} for n in issue["notes"]])
    m = re.fullmatch(r"/api/v4/projects/(\d+)/uploads/([^/]+)/([^/]+)", raw)
    if m and m.group(2) == "abc123" and unquote(m.group(3)) == "log.png":
        return httpx.Response(200, content=PNG, headers={"Content-Type": "image/png"})
    m = re.fullmatch(r"/api/v4/projects/([^/]+)/issues", raw)
    if m:
        path = unquote(m.group(1))
        term = request.url.params.get("search", "").casefold()
        hits = [_issue(p, i) for (p, i), v in ISSUES.items() if p == path and term in str(v["title"]).casefold()]
        return _json(hits)
    return _json({"message": "404 Not found"}, 404)


def handle(request: httpx.Request) -> httpx.Response:
    raw = request.url.raw_path.decode().split("?", 1)[0]
    if raw.startswith("/confluence/"):
        return _confluence(request, unquote(raw[len("/confluence") :]))
    if raw.startswith("/api/v4/"):
        return _gitlab(request, raw)
    return _json({"message": "not found"}, 404)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        host = self.headers.get("Host", "127.0.0.1")
        req = httpx.Request("GET", f"http://{host}{self.path}", headers=dict(self.headers.items()))
        resp = handle(req)
        self.send_response(resp.status_code)
        self.send_header("Content-Type", resp.headers.get("Content-Type", "application/octet-stream"))
        self.send_header("Content-Length", str(len(resp.content)))
        self.end_headers()
        self.wfile.write(resp.content)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def serve(host: str, port: int) -> None:
    print(f"Kurgusal Confluence: http://{host}:{port}/confluence  ·  Kurgusal GitLab: http://{host}:{port}  ·  token: {TOKEN}")
    ThreadingHTTPServer((host, port), _Handler).serve_forever()
