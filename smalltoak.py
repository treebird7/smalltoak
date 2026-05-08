#!/usr/bin/env python3
"""smalltoak — minimal copy-paste messaging between coding agents.

Supports two transports:
  HTTP (recommended for cross-machine):
    Set SMALLTOAK_SERVER_URL=http://host:7474 on all machines.
    Run `python smalltoak.py serve [--port 7474]` on one machine.
    Set SMALLTOAK_TOKEN=<shared-secret> on all machines for auth.
    Falls back to JSONL if server unreachable.

  JSONL (local / git-backed):
    Default when SMALLTOAK_SERVER_URL is not set.
    Messages stored in SMALLTOAK_STORE (default: messages.jsonl).

Usage:
    python smalltoak.py post "your message here" --from birdsan
    python smalltoak.py post "reply" --from watsan --to birdsan [--priority high] [--reply-to 3]
    python smalltoak.py read
    python smalltoak.py read --to birdsan
    python smalltoak.py read --last 5
    python smalltoak.py read --since 1h
    python smalltoak.py count
    python smalltoak.py delete --id 1
    python smalltoak.py search "query"
    python smalltoak.py compact
    python smalltoak.py serve [--port 7474]
"""

import json
import os
import sys
import time
import hmac
import ssl
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error

STORE = os.environ.get("SMALLTOAK_STORE", "messages.jsonl")
SERVER_URL = os.environ.get("SMALLTOAK_SERVER_URL", "").rstrip("/")
TOKEN = os.environ.get("SMALLTOAK_TOKEN", "")
DEFAULT_PORT = 7474

# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------


def _load() -> list[dict]:
    if not os.path.exists(STORE):
        return []
    msgs = []
    for line in open(STORE):
        line = line.strip()
        if line:
            try:
                msgs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return msgs


def _next_id(msgs: list[dict]) -> int:
    if not msgs:
        return 1
    return max(m.get("id", 0) for m in msgs) + 1


# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def _http_post(
    text: str,
    sender: str,
    recipient: str | None = None,
    priority: str | None = None,
    reply_to: str | None = None,
) -> dict | None:
    payload = json.dumps(
        {
            "text": text,
            "from": sender,
            "to": recipient,
            "priority": priority,
            "reply_to": reply_to,
        }
    ).encode()
    headers = {"Content-Type": "application/json", **_auth_headers()}
    req = urllib.request.Request(
        f"{SERVER_URL}/messages", data=payload, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _http_read(
    recipient: str | None = None,
    sender: str | None = None,
    last: int | None = None,
    since: str | None = None,
) -> list[dict] | None:
    params: dict = {}
    if recipient:
        params["to"] = recipient
    if sender:
        params["from"] = sender
    if last:
        params["last"] = str(last)
    if since:
        params["since"] = since
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(f"{SERVER_URL}/messages{qs}", headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def post(
    text: str,
    sender: str,
    recipient: str | None = None,
    priority: str | None = None,
    reply_to: str | None = None,
) -> dict:
    if SERVER_URL:
        result = _http_post(text, sender, recipient, priority, reply_to)
        if result:
            return result
    msgs = _load()
    msg = {
        "id": _next_id(msgs),
        "ts": datetime.now(timezone.utc).isoformat(),
        "from": sender,
        "text": text,
        "priority": priority,
        "reply_to": reply_to,
    }
    if recipient:
        msg["to"] = recipient
    with open(STORE, "a") as f:
        f.write(json.dumps(msg) + "\n")
    return msg


def read(
    recipient: str | None = None,
    sender: str | None = None,
    last: int | None = None,
    since: str | None = None,
) -> list[dict]:
    if SERVER_URL:
        result = _http_read(recipient, sender, last, since)
        if result is not None:
            return result
    msgs = _load()

    if since:
        cutoff = _parse_since(since)
        msgs = [m for m in msgs if datetime.fromisoformat(m["ts"]) >= cutoff]

    if recipient:
        msgs = [m for m in msgs if m.get("to") == recipient or m.get("to") is None]

    if sender:
        msgs = [m for m in msgs if m.get("from") == sender]

    if last:
        msgs = msgs[-last:]

    return msgs


def count() -> int:
    if SERVER_URL:
        result = _http_read()
        if result is not None:
            return len(result)
    return len(_load())


def delete(msg_id: int) -> None:
    msgs = _load()
    msgs = [m for m in msgs if m.get("id") != msg_id]
    with open(STORE, "w") as f:
        for msg in msgs:
            f.write(json.dumps(msg) + "\n")


def search(query: str) -> list[dict]:
    if SERVER_URL:
        result = _http_read()
        if result is not None:
            return [m for m in result if query.lower() in m["text"].lower()]
    return [m for m in _load() if query.lower() in m["text"].lower()]


def compact() -> None:
    with open(STORE, "w") as f:
        for msg in _load():
            f.write(json.dumps(msg) + "\n")


def _parse_since(s: str) -> datetime:
    s = s.strip().lower()
    now = datetime.now(timezone.utc)
    if s.endswith("h"):
        return now - timedelta(hours=float(s[:-1]))
    if s.endswith("m"):
        return now - timedelta(minutes=float(s[:-1]))
    if s.endswith("d"):
        return now - timedelta(days=float(s[:-1]))
    return datetime.fromisoformat(s)


def _format_msg(m: dict) -> str:
    ts = datetime.fromisoformat(m["ts"]).strftime("%H:%M:%S")
    to_str = f" → {m['to']}" if m.get("to") else ""
    return f"\033[92m#{m['id']:04d}\033[0m [{ts}] \033[94m{m['from']}\033[0m{to_str}: {m['text']}"


def _format_priority(m: dict) -> str:
    if m.get("priority"):
        return f" (\033[91m{m['priority']}\033[0m)"
    return ""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {fmt % args}", flush=True)

    def _check_auth(self) -> bool:
        if not TOKEN:
            return True
        got = self.headers.get("Authorization", "")
        return hmac.compare_digest(got.encode(), f"Bearer {TOKEN}".encode())

    def _send_json(self, code: int, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._check_auth():
            return self._send_json(401, {"error": "unauthorized"})
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/messages":
            return self._send_json(404, {"error": "not found"})
        qs = urllib.parse.parse_qs(parsed.query)
        recipient = (qs.get("to") or [None])[0]
        sender = (qs.get("from") or [None])[0]
        last = int(qs["last"][0]) if "last" in qs else None
        since = (qs.get("since") or [None])[0]
        self._send_json(200, read(recipient, sender, last, since))

    def do_POST(self):
        if not self._check_auth():
            return self._send_json(401, {"error": "unauthorized"})
        if self.path != "/messages":
            return self._send_json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        # Security fix: Content-Length cap
        if length > 65536:
            return self._send_json(413, {"error": "payload too large"})
        body = json.loads(self.rfile.read(length))
        msg = post(
            body["text"],
            body["from"],
            body.get("to"),
            body.get("priority"),
            body.get("reply_to"),
        )
        self._send_json(201, msg)


def serve(port: int = DEFAULT_PORT):
    global SERVER_URL
    SERVER_URL = ""  # server itself always uses JSONL directly
    # SECURITY: default-bind loopback. smalltoak's token auth is OPTIONAL
    # (off by default) — a LAN-reachable instance with no token is open
    # read+write to its JSONL message store. Set SMALLTOAK_HOST=0.0.0.0
    # only after also setting SMALLTOAK_TOKEN.
    host = os.environ.get("SMALLTOAK_HOST", "127.0.0.1")
    if host != "127.0.0.1" and host != "::1" and not TOKEN:
        raise SystemExit(
            f"refusing to bind {host} without SMALLTOAK_TOKEN — "
            "set SMALLTOAK_TOKEN to enable network access"
        )
    server = HTTPServer((host, port), _Handler)
    # Security fix: Optional TLS
    cert_file = os.environ.get("SMALLTOAK_CERT")
    key_file = os.environ.get("SMALLTOAK_KEY")
    if cert_file and key_file:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    auth_note = (
        "  token auth: ON"
        if TOKEN
        else "  token auth: OFF (set SMALLTOAK_TOKEN to enable)"
    )
    print(f"smalltoak server listening on {host}:{port}")
    print(auth_note)
    print(f"  store: {os.path.abspath(STORE)}")
    print(f"  cert: {cert_file}" if cert_file else "  cert: not set")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.server_close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    json_out = "--json" in sys.argv
    if json_out:
        sys.argv.remove("--json")

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "post":
        text = ""
        sender = os.environ.get("SMALLTOAK_AGENT", "unknown")
        recipient = priority = reply_to = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--from" and i + 1 < len(sys.argv):
                sender = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--to" and i + 1 < len(sys.argv):
                recipient = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--priority" and i + 1 < len(sys.argv):
                priority = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--reply-to" and i + 1 < len(sys.argv):
                reply_to = sys.argv[i + 1]
                i += 2
            else:
                text = sys.argv[i]
                i += 1
        if not text:
            print(
                'Usage: smalltoak post "message" --from agent [--to agent] [--priority p] [--reply-to id]'
            )
            sys.exit(1)
        msg = post(text, sender, recipient, priority, reply_to)
        if json_out:
            print(json.dumps(msg, indent=2))
        else:
            print(f"#{msg['id']:04d} sent")

    elif cmd == "read":
        recipient = sender = last = since = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--to" and i + 1 < len(sys.argv):
                recipient = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--from" and i + 1 < len(sys.argv):
                sender = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--last" and i + 1 < len(sys.argv):
                last = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--since" and i + 1 < len(sys.argv):
                since = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        msgs = read(recipient, sender, last, since)
        if json_out:
            print(json.dumps(msgs, indent=2))
        else:
            if not msgs:
                print("(no messages)")
            for m in msgs:
                print(_format_msg(m) + _format_priority(m))

    elif cmd == "count":
        if json_out:
            print(json.dumps({"count": count()}))
        else:
            print(count())

    elif cmd == "delete":
        if "--id" not in sys.argv:
            print("Usage: smalltoak delete --id <id>")
            sys.exit(1)
        idx = sys.argv.index("--id")
        msg_id = int(sys.argv[idx + 1])
        delete(msg_id)
        print(f"Message #{msg_id:04d} deleted")

    elif cmd == "search":
        if len(sys.argv) < 3:
            print('Usage: smalltoak search "query"')
            sys.exit(1)
        msgs = search(sys.argv[2])
        if json_out:
            print(json.dumps(msgs, indent=2))
        else:
            for m in msgs:
                print(_format_msg(m) + _format_priority(m))

    elif cmd == "compact":
        compact()
        print("Messages compacted")

    elif cmd == "serve":
        port = DEFAULT_PORT
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        serve(port)

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: post, read, count, delete, search, compact, serve")
        sys.exit(1)


if __name__ == "__main__":
    main()
