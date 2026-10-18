"""Kurgusal OpenAI uyumlu model sunucusu (yalnız geliştirme/test; 127.0.0.1).

Model kimlikleri:
  fixture-reference          — sözleşmeye uyan deterministik referans
  fixture-liar               — uydurma sayı/sembol ekler, çekimser yerde destekli cevap uydurur
  fixture-fake-source        — kanıt paketinde olmayan iddia kimliği alıntılar
  fixture-scope-violator     — kapsam kısıtını yok sayar
  fixture-broken             — JSON olmayan metin döner
  fixture-slow               — 0,3 sn bekler (gecikme sıralaması için yeterli; testleri yavaşlatmaz)
  fixture-500                — HTTP 500 döner
  fixture-no-schema          — response_format=json_schema isteğine 400 döner
  fixture-no-thinking        — 'thinking' parametresine 400 döner
  fixture-one-slip           — tek vakada kapsam ihlali (yüksek ortalama + 1 kritik hata)
'Authorization: Bearer wrong-key' → 401.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from metis.llm import prompts
from metis.llm.mock_logic import respond

KNOWN = [
    "fixture-reference",
    "fixture-liar",
    "fixture-fake-source",
    "fixture-scope-violator",
    "fixture-broken",
    "fixture-slow",
    "fixture-500",
    "fixture-no-schema",
    "fixture-no-thinking",
    "fixture-one-slip",
]
PROMPT_IDS = [
    prompts.EVIDENCE,
    prompts.SOURCE_SELECTION,
    prompts.EXTRACT,
    prompts.PAGE_DIFF,
    prompts.CLAIM_CONFLICT,
    prompts.RELATION,
    prompts.REFINE,
    prompts.CONFLICT_RESOLUTION,
]


def identify(system: str) -> str | None:
    for pid in PROMPT_IDS:
        if system.startswith(prompts.load(pid).text[:200]):
            return pid
    if system.startswith("Probe"):
        return "probe"
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "metis-mock/1"

    def log_message(self, *_args) -> None:  # noqa: ANN002
        return

    def _send(self, status: int, body: dict | str) -> None:
        data = (json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._send(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in KNOWN]})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        # Gövde her yanıttan önce okunur: okunmamış veriyle kapanan soket Windows'ta RST gönderir ve
        # istemci 401/404 yerine bağlantı hatası görür.
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not self.path.rstrip("/").endswith("/chat/completions") or self.path.count("/v1/") > 1:
            self._send(404, {"error": {"message": "not found"}})
            return
        if self.headers.get("Authorization") == "Bearer wrong-key":
            self._send(401, {"error": {"message": "invalid api key"}})
            return
        try:
            body = json.loads(raw)
        except ValueError:
            self._send(400, {"error": {"message": "bad json"}})
            return
        model = body.get("model", "")
        if model not in KNOWN:
            self._send(404, {"error": {"message": f"model {model} not found"}})
            return
        if model == "fixture-500":
            self._send(500, {"error": {"message": "internal"}})
            return
        if model == "fixture-no-schema" and (body.get("response_format") or {}).get("type") == "json_schema":
            self._send(400, {"error": {"message": "response_format json_schema is not supported"}})
            return
        if model == "fixture-no-thinking" and "thinking" in body:
            self._send(400, {"error": {"message": "unknown parameter: thinking"}})
            return
        if model == "fixture-slow":
            time.sleep(0.3)
        messages = body.get("messages") or []
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user" and m["content"].startswith("{")), "{}")
        try:
            payload = json.loads(user)
        except ValueError:
            payload = {}
        pid = identify(system)
        if model == "fixture-broken":
            content = "Elbette! İşte cevabınız: kanıtla destekli."
        elif pid == "probe":
            content = json.dumps({"ok": True, "echo": payload.get("echo", "")})
        elif pid is None:
            content = json.dumps({"error": "unknown prompt"})
        else:
            content = json.dumps(respond(pid, payload, model), ensure_ascii=False)
        usage = {"prompt_tokens": len(json.dumps(messages)) // 4, "completion_tokens": len(content) // 4}
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        self._send(200, {"id": "mock", "object": "chat.completion", "model": model, "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}], "usage": usage})


def make_server(host: str = "127.0.0.1", port: int = 9100) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Kurgusal model yalnız yerel adreste çalışır.")
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 9100) -> None:
    server = make_server(host, port)
    print(f"METIS kurgusal model: http://{host}:{port}/v1  (gerçek model değildir)")
    server.serve_forever()


def start_background(port: int) -> ThreadingHTTPServer:
    server = make_server("127.0.0.1", port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
