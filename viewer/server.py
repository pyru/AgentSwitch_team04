"""Local run console: browse harness runs and start one selected task at a time.

Binds to 127.0.0.1 only. Starting a run executes python -m harness.runner against a live tenant, exactly as
the CLI does, so AGENTS.md's "ask before running" applies to every click.
"""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from prod_agent import config

from . import runs
from .jobs import JobError, JobRunner

HOST = "127.0.0.1"
STATIC = Path(__file__).parent / "static"
MAX_BODY = 32 * 1024


def make_server(port: int, bases: dict[str, Path], jobs: JobRunner) -> ThreadingHTTPServer:
    token = secrets.token_hex(16)
    instances = set(config.INSTANCES)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # the page polls every second; keep the terminal readable
            pass

        def _send(self, status: int, body, content_type: str = "application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _local(self) -> set[str]:
            port = self.server.server_address[1]
            return {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            # Another site can reach 127.0.0.1 through DNS rebinding; the Host header is what it cannot choose.
            if self.headers.get("Host") not in self._local():
                return self._send(403, {"error": "forbidden host"})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    page = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", token)
                    return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
                if url.path == "/api/tasks":
                    return self._send(200, [{"id": t["id"], "instances": jobs.instances_for(t["id"]),
                                             "mode": t.get("mode"), "escalate": bool(t.get("escalate")),
                                             "fixture": t.get("fixture"), "prompt": t.get("prompt"),
                                             "checks": t.get("checks")} for t in jobs.tasks.values()])
                if url.path == "/api/jobs/current":
                    return self._send(200, jobs.status())
                if url.path == "/api/runs" and q.get("base") in bases:
                    return self._send(200, runs.list_run_roots(bases[q["base"]]))
                if url.path in ("/api/run", "/api/trace") and q.get("base") in bases:
                    task_dir = runs.resolve_task_dir(bases[q["base"]], q.get("root", ""), q.get("instance", ""),
                                                     q.get("task", ""), instances)
                    if task_dir is not None and url.path == "/api/run":
                        return self._send(200, runs.load_task_run(task_dir))
                    if task_dir is not None:
                        events, offset = runs.read_trace(task_dir / "trace.jsonl", int(q.get("offset", "0")))
                        return self._send(200, {"events": events, "offset": offset})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in self._local() \
                    or (origin is not None and origin.removeprefix("http://") not in self._local()) \
                    or not secrets.compare_digest(self.headers.get("X-Console-Token", ""), token):
                return self._send(403, {"error": "forbidden"})
            path = urlparse(self.path).path
            if path not in ("/api/jobs", "/api/ask"):
                return self._send(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                # Checked before reading, so an oversized or negative length never reaches rfile.read.
                if not 0 <= length <= MAX_BODY:
                    return self._send(413, {"error": f"request body must be at most {MAX_BODY} bytes"})
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("expected a JSON object")
                instance, confirm = str(body.get("instance", "")), str(body.get("confirm", ""))
                if path == "/api/ask":
                    return self._send(200, jobs.ask(instance, str(body.get("text", "")), confirm))
                return self._send(200, jobs.start(str(body.get("task_id", "")), instance, confirm))
            except (JobError, ValueError) as e:
                return self._send(400, {"error": str(e)})

    server = ThreadingHTTPServer((HOST, port), Handler)
    server.token = token
    return server
