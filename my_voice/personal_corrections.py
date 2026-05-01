from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import threading
from typing import Any
from urllib.parse import urlparse

from .config import AppConfig, default_config_path


_SERVER_LOCK = threading.Lock()
_SERVERS: dict[tuple[Path, int], ThreadingHTTPServer] = {}
_CORRECTIONS_CACHE_LOCK = threading.Lock()
_CORRECTIONS_CACHE: dict[Path, tuple[int | None, dict[str, str]]] = {}


@dataclass(slots=True)
class CorrectionResult:
    text: str
    applied: int


def corrections_path(config: AppConfig | None = None) -> Path:
    configured = (config.personal_corrections_path if config else "").strip()
    if configured:
        return Path(configured).expanduser()
    return default_config_path().parent / "corrections.json"


def load_corrections(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    terms = raw.get("terms", {}) if isinstance(raw, dict) else {}
    if not isinstance(terms, dict):
        return {}
    return {
        str(heard).strip(): str(replacement).strip()
        for heard, replacement in terms.items()
        if str(heard).strip() and str(replacement).strip()
    }


def get_cached_corrections(path: Path) -> dict[str, str]:
    mtime_ns = _mtime_ns(path)
    with _CORRECTIONS_CACHE_LOCK:
        cached = _CORRECTIONS_CACHE.get(path)
        if cached is not None and cached[0] == mtime_ns:
            return dict(cached[1])
        terms = load_corrections(path)
        _CORRECTIONS_CACHE[path] = (mtime_ns, terms)
        return dict(terms)


def save_corrections(path: Path, terms: dict[str, str]) -> None:
    cleaned = {
        str(heard).strip(): str(replacement).strip()
        for heard, replacement in terms.items()
        if str(heard).strip() and str(replacement).strip()
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"terms": cleaned}, handle, indent=2, sort_keys=True)
        handle.write("\n")
    with _CORRECTIONS_CACHE_LOCK:
        _CORRECTIONS_CACHE[path] = (_mtime_ns(path), cleaned)


def apply_personal_corrections(text: str, config: AppConfig) -> CorrectionResult:
    if not config.personal_corrections_enabled:
        return CorrectionResult(text=text, applied=0)
    terms = get_cached_corrections(corrections_path(config))
    corrected = text
    applied = 0
    for heard, replacement in sorted(terms.items(), key=lambda item: len(item[0]), reverse=True):
        corrected, count = _replace_term(corrected, heard, replacement)
        applied += count
    return CorrectionResult(text=corrected, applied=applied)


def open_personal_corrections_editor(config: AppConfig | None = None) -> str:
    config = config or AppConfig()
    path = corrections_path(config)
    port = config.personal_corrections_editor_port
    _ensure_server(path, port)
    url = f"http://127.0.0.1:{port}/"
    subprocess.Popen(["open", url])
    return url


def _replace_term(text: str, heard: str, replacement: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?<!\w){re.escape(heard)}(?!\w)", flags=re.IGNORECASE)
    return pattern.subn(lambda match: replacement, text)


def _mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _ensure_server(path: Path, port: int) -> None:
    key = (path, port)
    with _SERVER_LOCK:
        if key in _SERVERS:
            return
        handler = _handler_factory(path)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        thread = threading.Thread(target=server.serve_forever, name="personal-corrections-editor", daemon=True)
        thread.start()
        _SERVERS[key] = server


def _handler_factory(path: Path):
    class CorrectionsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(200, EDITOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/corrections":
                body = json.dumps({"terms": load_corrections(path), "path": str(path)}).encode("utf-8")
                self._send(200, body, "application/json")
                return
            self._send(404, b"Not found", "text/plain")

        def do_PUT(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/corrections":
                self._send(404, b"Not found", "text/plain")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                terms = _parse_terms_payload(payload)
                save_corrections(path, terms)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode("utf-8"), "application/json")
                return
            body = json.dumps({"terms": load_corrections(path), "path": str(path)}).encode("utf-8")
            self._send(200, body, "application/json")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return CorrectionsHandler


def _parse_terms_payload(payload: dict[str, Any]) -> dict[str, str]:
    terms = payload.get("terms", {})
    if isinstance(terms, dict):
        return {
            str(heard).strip(): str(replacement).strip()
            for heard, replacement in terms.items()
            if str(heard).strip() and str(replacement).strip()
        }
    if isinstance(terms, list):
        parsed: dict[str, str] = {}
        for row in terms:
            if not isinstance(row, dict):
                continue
            heard = str(row.get("heard", "")).strip()
            replacement = str(row.get("replacement", "")).strip()
            if heard and replacement:
                parsed[heard] = replacement
        return parsed
    raise ValueError("terms must be an object or list")


EDITOR_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MyVoice Personal Corrections</title>
  <style>
    :root { color-scheme: light dark; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; padding: 28px; background: Canvas; color: CanvasText; }
    main { max-width: 880px; margin: 0 auto; }
    h1 { font-size: 24px; margin: 0 0 6px; }
    p { margin: 0 0 18px; color: color-mix(in srgb, CanvasText 70%, transparent); }
    table { width: 100%; border-collapse: collapse; border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); }
    th, td { padding: 10px; border-bottom: 1px solid color-mix(in srgb, CanvasText 12%, transparent); text-align: left; }
    th { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    input { width: 100%; box-sizing: border-box; padding: 8px 9px; border-radius: 6px; border: 1px solid color-mix(in srgb, CanvasText 25%, transparent); font: inherit; background: Field; color: FieldText; }
    .actions { display: flex; gap: 8px; margin: 14px 0; align-items: center; }
    button { padding: 8px 12px; border-radius: 6px; border: 1px solid color-mix(in srgb, CanvasText 20%, transparent); font: inherit; background: ButtonFace; color: ButtonText; cursor: pointer; }
    button.primary { background: AccentColor; color: AccentColorText; border-color: AccentColor; }
    button.danger { color: #b42318; }
    .path, .status { font-size: 12px; color: color-mix(in srgb, CanvasText 62%, transparent); }
    .remove { width: 1%; white-space: nowrap; }
  </style>
</head>
<body>
  <main>
    <h1>Personal Corrections</h1>
    <p>MyVoice applies these whole-word and whole-phrase replacements before cleanup.</p>
    <div class="actions">
      <button id="add">Add</button>
      <button id="save" class="primary">Save</button>
      <button id="reload">Reload</button>
      <span id="status" class="status"></span>
    </div>
    <table>
      <thead><tr><th>Heard as</th><th>Replace with</th><th></th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
    <p id="path" class="path"></p>
  </main>
  <script>
    const rows = document.querySelector("#rows");
    const status = document.querySelector("#status");
    const path = document.querySelector("#path");

    function row(heard = "", replacement = "") {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><input class="heard" value="${escapeAttr(heard)}" placeholder="cong"></td>
        <td><input class="replacement" value="${escapeAttr(replacement)}" placeholder="Kong"></td>
        <td class="remove"><button class="danger">Delete</button></td>
      `;
      tr.querySelector("button").addEventListener("click", () => tr.remove());
      rows.appendChild(tr);
      tr.querySelector("input").focus();
    }

    function escapeAttr(value) {
      return String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
    }

    async function load() {
      const response = await fetch("/api/corrections");
      const data = await response.json();
      rows.innerHTML = "";
      Object.entries(data.terms || {}).forEach(([heard, replacement]) => row(heard, replacement));
      if (!rows.children.length) row();
      path.textContent = data.path ? `Stored at ${data.path}` : "";
      status.textContent = "Loaded";
    }

    async function save() {
      const terms = {};
      rows.querySelectorAll("tr").forEach((tr) => {
        const heard = tr.querySelector(".heard").value.trim();
        const replacement = tr.querySelector(".replacement").value.trim();
        if (heard && replacement) terms[heard] = replacement;
      });
      const response = await fetch("/api/corrections", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({terms})
      });
      if (!response.ok) throw new Error(await response.text());
      status.textContent = "Saved";
      await load();
    }

    document.querySelector("#add").addEventListener("click", () => row());
    document.querySelector("#save").addEventListener("click", () => save().catch((err) => status.textContent = err.message));
    document.querySelector("#reload").addEventListener("click", () => load().catch((err) => status.textContent = err.message));
    load().catch((err) => status.textContent = err.message);
  </script>
</body>
</html>
"""
