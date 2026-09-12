"""HTTP entry point: routes, responses and public static files."""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import FRONTEND_ROOT, MIN_YEAR, CURRENT_YEAR
from . import library
from . import omdb
from . import presentation


class CineverseHandler(BaseHTTPRequestHandler):
    def send_content(self, status, payload, content_type, cache_control="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status, data):
        self.send_content(status, json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def send_catalog(self, data):
        return self.send_json(200, presentation.catalog(data))

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                return self.send_json(200, {"ok": True, "configured": library.configured() or bool(os.getenv("OMDB_API_KEY", "").strip()),
                                            "provider": "TMDB" if library.configured() else "OMDb",
                                            "version": "2026.09.catalog-v3", "commit": os.getenv("RENDER_GIT_COMMIT", "local")})
            if parsed.path == "/api/catalog":
                return self.catalog_route(parse_qs(parsed.query))
            if parsed.path.startswith("/api/title/"):
                return self.title_route(parsed.path.rsplit("/", 1)[-1])
            return self.static_file(parsed.path)
        except ValueError:
            self.send_json(400, {"error": "Parâmetros inválidos."})
        except Exception:
            self.send_json(503, {"error": "Catálogo indisponível. Tente novamente em instantes."})

    def catalog_route(self, query):
        provider = library if library.configured() else omdb
        return self.send_catalog(provider.catalog_response(query))

    def title_route(self, movie_id):
        provider = library if movie_id.startswith("tmdb-") else omdb
        return self.send_json(200, presentation.present(provider.details(movie_id)))

    def static_file(self, request_path):
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        file_path = (FRONTEND_ROOT / relative).resolve()
        public_files = {"index.html", "app.js", "styles.css", "poster-placeholder.svg"}
        blocked = FRONTEND_ROOT not in file_path.parents or relative not in public_files
        if blocked:
            self.send_error(403)
            return
        if not file_path.is_file():
            self.send_error(404)
            return
        payload = file_path.read_bytes()
        if relative == "index.html":
            options = "".join(f'<option value="{year}">{year}</option>'
                              for year in range(CURRENT_YEAR, MIN_YEAR - 1, -1))
            payload = payload.replace(b"<!-- YEAR_OPTIONS -->", options.encode())
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        self.send_content(200, payload, content_type, "no-cache")


    def log_message(self, *_):
        pass


def create_server(host="0.0.0.0", port=None):
    return ThreadingHTTPServer((host, int(port or os.getenv("PORT", "4173"))), CineverseHandler)


if __name__ == "__main__":
    server = create_server()
    print(f"Cineverse disponível em http://localhost:{server.server_port}")
    server.serve_forever()
