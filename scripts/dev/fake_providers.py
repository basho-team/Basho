"""SERVIDOR FALSO de Google OAuth/Drive e Notion, só para desenvolvimento e ensaio da demo.

Imita o mínimo que o Basho usa e guarda tudo em memória. Não valida token, não é seguro e não
substitui a integração real: serve para exercitar o fluxo ponta a ponta sem credenciais e para
abrir no navegador os documentos que o Basho gerou (`/doc/<id>`, `/notion/<id>`, `/_state`).

    python scripts/dev/fake_providers.py 9100

Aponte o backend para ele com GOOGLE_DRIVE_API_URL, GOOGLE_TOKEN_URI e NOTION_API_URL.
"""

import html
import json
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

FOLDER_MIME = "application/vnd.google-apps.folder"
LOCK = threading.Lock()
DRIVE: dict[str, dict[str, Any]] = {}
NOTION: dict[str, dict[str, Any]] = {}
PORT = 9100


def _new_id() -> str:
    return uuid.uuid4().hex[:28]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # silencia o log padrão
        return

    # --- utilidades ---
    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("content-length", 0)))

    def _json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _page(self, body: str) -> None:
        data = body.encode()
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _log(self, line: str) -> None:
        print(f"[fake] {self.command} {self.path.split('?')[0]} {line}", flush=True)

    # --- roteamento ---
    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        path, query = parts.path, parse_qs(parts.query)
        with LOCK:
            if m := re.fullmatch(r"/drive/v3/files/([^/]+)", path):
                return self._drive_get(m.group(1))
            if path == "/drive/v3/files":
                return self._drive_list(query.get("q", [""])[0])
            if m := re.fullmatch(r"/v1/pages/([^/]+)", path):
                return self._notion_get(m.group(1))
            if m := re.fullmatch(r"/v1/blocks/([^/]+)/children", path):
                return self._notion_children(m.group(1))
            if m := re.fullmatch(r"/doc/([^/]+)", path):
                doc = DRIVE.get(m.group(1))
                return self._page(doc["html"]) if doc else self._json({}, 404)
            if m := re.fullmatch(r"/notion/([^/]+)", path):
                return self._notion_view(m.group(1))
            if path == "/_state":
                return self._json(self._state())
        self._json({}, 404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        raw = self._body()
        with LOCK:
            if path == "/token":
                self._log("-> token")
                return self._json({"access_token": "fake-access-token", "expires_in": 3600})
            if path == "/drive/v3/files":
                return self._drive_create_folder(json.loads(raw))
            if path == "/upload/drive/v3/files":
                return self._drive_upload(raw)
            if path == "/v1/pages":
                return self._notion_create(json.loads(raw))
        self._json({}, 404)

    def do_PATCH(self) -> None:
        path = urlsplit(self.path).path
        raw = self._body()
        with LOCK:
            if m := re.fullmatch(r"/v1/blocks/([^/]+)/children", path):
                page = NOTION.get(m.group(1))
                if page is None:
                    return self._json({}, 404)
                page["blocks"].extend(json.loads(raw).get("children", []))
                return self._json({"results": []})
        self._json({}, 404)

    # --- Drive ---
    def _drive_get(self, file_id: str) -> None:
        item = DRIVE.get(file_id) or {
            "id": file_id,
            "name": "Pasta de teste (servidor falso)",
            "mimeType": FOLDER_MIME,
        }
        self._log(f"-> {item['name']}")
        self._json(
            {
                "id": item["id"],
                "name": item["name"],
                "mimeType": item["mimeType"],
                "capabilities": {"canAddChildren": True},
            }
        )

    def _drive_list(self, query: str) -> None:
        parent = re.search(r"'([^']+)' in parents", query)
        name = re.search(r"name = '((?:[^'\\]|\\.)*)'", query)
        wants_folder = "mimeType = '" + FOLDER_MIME + "'" in query
        wanted = name.group(1).replace("\\'", "'").replace("\\\\", "\\") if name else None
        found = [
            f
            for f in DRIVE.values()
            if parent
            and parent.group(1) in f.get("parents", [])
            and f["name"] == wanted
            and (f["mimeType"] == FOLDER_MIME) == wants_folder
        ]
        self._json({"files": [self._file_out(f) for f in found[:1]]})

    def _file_out(self, f: dict[str, Any]) -> dict[str, Any]:
        return {"id": f["id"], "name": f["name"], "webViewLink": f"http://127.0.0.1:{PORT}/doc/{f['id']}"}

    def _drive_create_folder(self, meta: dict[str, Any]) -> None:
        folder = {"id": _new_id(), "name": meta["name"], "mimeType": FOLDER_MIME, "parents": meta.get("parents", [])}
        DRIVE[folder["id"]] = folder
        self._log(f"-> pasta {folder['name']}")
        self._json({"id": folder["id"]})

    def _drive_upload(self, raw: bytes) -> None:
        boundary = self.headers["content-type"].split("boundary=")[1].encode()
        sections = [p for p in raw.split(b"--" + boundary) if b"Content-Type" in p]
        meta = json.loads(sections[0].split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0])
        content = sections[1].split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0].decode()
        doc = {"id": _new_id(), "name": meta["name"], "mimeType": meta["mimeType"], "parents": meta.get("parents", []), "html": content}
        DRIVE[doc["id"]] = doc
        self._log(f"-> documento {doc['name']}")
        self._json(self._file_out(doc))

    # --- Notion ---
    def _notion_get(self, page_id: str) -> None:
        page = NOTION.get(page_id) or {"id": page_id, "title": "Página de teste (servidor falso)", "blocks": [], "parent": None}
        self._json(
            {
                "id": page["id"],
                "url": f"http://127.0.0.1:{PORT}/notion/{page['id']}",
                "properties": {"title": {"type": "title", "title": [{"plain_text": page["title"]}]}},
            }
        )

    def _notion_children(self, parent_id: str) -> None:
        kids = [
            {"id": p["id"], "type": "child_page", "child_page": {"title": p["title"]}}
            for p in NOTION.values()
            if p["parent"] == parent_id
        ]
        self._json({"results": kids, "has_more": False, "next_cursor": None})

    def _notion_create(self, body: dict[str, Any]) -> None:
        title = "".join(t["text"]["content"] for t in body["properties"]["title"]["title"])
        page = {"id": _new_id(), "title": title, "parent": body["parent"]["page_id"], "blocks": list(body.get("children", []))}
        NOTION[page["id"]] = page
        self._log(f"-> página {title}")
        self._json({"id": page["id"], "url": f"http://127.0.0.1:{PORT}/notion/{page['id']}"})

    def _notion_view(self, page_id: str) -> None:
        page = NOTION.get(page_id)
        if page is None:
            return self._json({}, 404)
        lines = []
        for block in page["blocks"]:
            kind = block["type"]
            text = html.escape("".join(t["text"]["content"] for t in block[kind]["rich_text"]))
            lines.append({"heading_2": f"<h2>{text}</h2>", "bulleted_list_item": f"<li>{text}</li>"}.get(kind, f"<p>{text}</p>"))
        self._page(f"<h1>{html.escape(page['title'])}</h1>" + "".join(lines))

    def _state(self) -> dict[str, Any]:
        return {
            "drive": [{"name": f["name"], "type": f["mimeType"], "parents": f.get("parents")} for f in DRIVE.values()],
            "notion": [{"title": p["title"], "blocks": len(p["blocks"])} for p in NOTION.values()],
        }


if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9100
    print(f"servidor FALSO de Drive/Notion em http://127.0.0.1:{PORT} (só desenvolvimento)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
