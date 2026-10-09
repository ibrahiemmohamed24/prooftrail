"""Local-only control room. Run: python -m prooftrail.web --port 8766.

No cloud account, mandatory third-party dependency or model call is required.
Uploads are processed in memory, never written into the frozen benchmark.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import application as service
from .ui.build import ASSET_DIR, page_files
from .ui.model import load_site


def make_handler(port):
    site = load_site()
    pages = {"/" + path: html.encode("utf-8") for path, html in page_files(site).items()}
    pages["/"] = pages["/index.html"]
    assets = {"/assets/" + file.relative_to(ASSET_DIR).as_posix(): file.read_bytes()
              for file in ASSET_DIR.rglob("*") if file.is_file() and "__pycache__" not in file.parts}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{host}" for host in hosts}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_):
            # Evidence and query strings must not appear in access logs.
            pass

        def respond(self, status, body, content_type="application/json; charset=utf-8"):
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def safe_host(self):
            if self.headers.get("Host") not in hosts:
                self.respond(403, {"error": "Local host only."})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self.respond(403, {"error": "Cross-origin access is not permitted."})
                return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.respond(403, {"error": "Cross-site access is not permitted."})
                return False
            return True

        def do_GET(self):
            if not self.safe_host():
                return
            path = urlsplit(self.path).path
            if path in pages:
                return self.respond(200, pages[path], "text/html; charset=utf-8")
            if path in assets:
                return self.respond(200, assets[path], mimetypes.guess_type(path)[0] or "application/octet-stream")
            try:
                if path == "/api/v1/health":
                    result = {"status": "ok", "network_required": False, "uploads_persisted": False}
                elif path == "/api/v1/overview":
                    result = asdict(site.overview)
                elif path == "/api/v1/cases":
                    result = {"cases": [asdict(case) for case in site.cases]}
                elif path in ("/api/v1/benchmark", "/benchmark.json"):
                    result = service.get_benchmark_summary()
                elif path.startswith("/api/v1/cases/"):
                    parts = path.split("/")
                    if len(parts) == 5:
                        result = service.get_case(parts[4])
                    elif len(parts) == 6 and parts[5] == "certificate":
                        result = service.get_evidence_certificate(parts[4])
                    else:
                        raise KeyError()
                elif path.startswith("/certificates/") and path.endswith((".json", ".md")):
                    name = path.rsplit("/", 1)[1]
                    case_id, extension = name.rsplit(".", 1)
                    certificate = service.get_evidence_certificate(case_id)
                    if extension == "json":
                        return self.respond(200, certificate)
                    from .config import FROZEN_DIR
                    return self.respond(200, (FROZEN_DIR / case_id / "certificate.md").read_bytes(), "text/markdown; charset=utf-8")
                else:
                    raise KeyError()
                self.respond(200, result)
            except KeyError:
                self.respond(404, {"error": "Not found."})
            except Exception:
                self.respond(500, {"error": "Unable to read local evidence."})

        def do_POST(self):
            if not self.safe_host():
                return
            routes = {"/api/v1/audits": service.audit_evidence, "/api/v1/ledgers/verify": service.verify_ledger}
            action = routes.get(urlsplit(self.path).path)
            if action is None:
                return self.respond(404, {"error": "Not found."})
            if self.headers.get("Transfer-Encoding"):
                return self.respond(400, {"error": "Chunked requests are not supported."})
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                return self.respond(415, {"error": "Use application/json."})
            try:
                size = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                size = -1
            if not 0 < size <= service.MAX_BYTES:
                return self.respond(413, {"error": "Provide a body between 1 byte and 2 MiB."})
            try:
                raw = self.rfile.read(size)
                if len(raw) != size:
                    return self.respond(400, {"error": "Incomplete request body."})
                result = action(service.decode_json(raw))
                self.respond(200, result)
            except service.InvalidEvidence as exc:
                self.respond(422, {"error": str(exc)})
            except TimeoutError:
                self.respond(408, {"error": "Request timed out."})
            except Exception:
                self.respond(500, {"error": "Audit could not be completed."})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.port))
    print(f"ProofTrail control room: http://127.0.0.1:{args.port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
