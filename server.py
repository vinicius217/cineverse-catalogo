import json
import mimetypes
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
OMDB_URL = "https://www.omdbapi.com/"
SEEDS = (("star", "Ficção"), ("dark", "Suspense"), ("love", "Drama"), ("war", "Ação"),
         ("life", "Drama"), ("world", "Aventura"), ("night", "Suspense"),
         ("last", "Drama"), ("dead", "Suspense"), ("the", "Outros"))
CACHE = {"items": [], "expires": 0.0}
DETAILS = {}
MIN_YEAR = 2000
CURRENT_YEAR = min(datetime.now().year, 2026)


def poster_url(value):
    return value if value and value != "N/A" else "poster-placeholder.svg"


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip().replace("_", "").isalnum():
            os.environ.setdefault(name.strip(), value.strip().strip("'\""))


load_env()


def omdb(**params):
    key = os.getenv("OMDB_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Configure OMDB_API_KEY no arquivo .env")
    query = urlencode({"apikey": key, **params})
    with urlopen(f"{OMDB_URL}?{query}", timeout=15) as response:
        data = json.load(response)
    if data.get("Response") == "False":
        raise RuntimeError(data.get("Error", "Erro ao consultar a OMDb"))
    return data


def release_year(value):
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return 0


def _search(task):
    term, genre, media_type, year = task
    try:
        params = {"s": term, "type": media_type, "page": 1}
        if year:
            params["y"] = year
        data = omdb(**params)
        return [dict(item, genre=genre) for item in data.get("Search", [])]
    except Exception:
        return []


def catalog():
    if CACHE["items"] and CACHE["expires"] > time.time():
        return CACHE["items"]
    tasks = [(term, genre, media_type, None) for term, genre in SEEDS for media_type in ("movie", "series")]
    tasks += [(term, genre, media_type, CURRENT_YEAR) for term, genre in SEEDS[:3] for media_type in ("movie", "series")]
    unique = {}
    with ThreadPoolExecutor(max_workers=13) as pool:
        for results in pool.map(_search, tasks):
            for item in results:
                movie_id = item.get("imdbID")
                year = release_year(item.get("Year"))
                if movie_id and MIN_YEAR <= year <= CURRENT_YEAR and movie_id not in unique:
                    unique[movie_id] = {
                        "id": movie_id, "title": item.get("Title", "Sem título"),
                        "type": "Filme" if item.get("Type") == "movie" else "Série",
                        "genre": item["genre"], "year": item.get("Year", "—"),
                        "score": "—", "image": item["Poster"],
                    }
    items = sorted(unique.values(), key=lambda item: (release_year(item["year"]), item["title"]), reverse=True)
    CACHE.update(items=items, expires=time.time() + 7 * 86400)
    return CACHE["items"]


def search_catalog(query, media_type, year, page, page_size):
    start = (page - 1) * page_size
    first_omdb_page = start // 10 + 1
    last_omdb_page = (start + page_size - 1) // 10 + 1
    params = []
    for omdb_page in range(first_omdb_page, last_omdb_page + 1):
        item = {"s": query, "page": omdb_page}
        if media_type in ("Filme", "Série"):
            item["type"] = "movie" if media_type == "Filme" else "series"
        if year:
            item["y"] = year
        params.append(item)

    def fetch_page(item):
        try:
            return omdb(**item)
        except RuntimeError as error:
            if "not found" in str(error).lower():
                return {"Search": [], "totalResults": "0"}
            raise

    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(fetch_page, params))
    raw_items = [item for response in responses for item in response.get("Search", [])]
    offset = start - (first_omdb_page - 1) * 10
    items = [{
        "id": item["imdbID"], "title": item.get("Title", "Sem título"),
        "type": "Filme" if item.get("Type") == "movie" else "Série",
        "genre": "Resultado da pesquisa", "year": item.get("Year", "—"),
        "score": "—", "image": poster_url(item.get("Poster")),
    } for item in raw_items[offset:offset + page_size]
        if MIN_YEAR <= release_year(item.get("Year")) <= CURRENT_YEAR]
    total = int(responses[0].get("totalResults", 0)) if responses else 0
    return items, total


class CineverseHandler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                return self.send_json(200, {"ok": True, "configured": bool(os.getenv("OMDB_API_KEY", "").strip())})
            if parsed.path == "/api/catalog":
                return self.catalog_route(parse_qs(parsed.query))
            if parsed.path.startswith("/api/title/"):
                return self.title_route(parsed.path.rsplit("/", 1)[-1])
            return self.static_file(parsed.path)
        except Exception as error:
            self.send_json(500, {"error": str(error)})

    def catalog_route(self, query):
        value = lambda key, default="": query.get(key, [default])[0]
        q, media_type, genre, year = value("q").lower(), value("type", "Todos"), value("genre", "Todos"), value("year")
        order = value("order", "recent")
        page = max(1, int(value("page", "1")))
        page_size = min(48, max(1, int(value("pageSize", "24"))))
        if q:
            items, total = search_catalog(q, media_type, year, page, page_size)
            return self.send_json(200, {"items": items, "total": total, "page": page, "pageSize": page_size})
        items = [item for item in catalog()
                 if (not q or q in f'{item["title"]} {item["genre"]}'.lower())
                 and (media_type == "Todos" or item["type"] == media_type)
                 and (genre == "Todos" or item["genre"] == genre)
                 and (not year or item["year"].startswith(year))]
        if order == "title":
            items.sort(key=lambda item: item["title"].casefold())
        start = (page - 1) * page_size
        self.send_json(200, {"items": items[start:start + page_size], "total": len(items), "page": page, "pageSize": page_size})

    def title_route(self, movie_id):
        if movie_id not in DETAILS:
            data = omdb(i=movie_id, plot="full")
            DETAILS[movie_id] = {
                "id": data["imdbID"], "title": data["Title"],
                "type": "Filme" if data.get("Type") == "movie" else "Série",
                "genre": "Não informado" if data.get("Genre") == "N/A" else data.get("Genre"),
                "year": data.get("Year"), "score": "—" if data.get("imdbRating") == "N/A" else data.get("imdbRating"),
                "synopsis": "Sinopse indisponível." if data.get("Plot") == "N/A" else data.get("Plot"),
                "image": poster_url(data.get("Poster")),
            }
        self.send_json(200, DETAILS[movie_id])

    def static_file(self, request_path):
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        file_path = (ROOT / relative).resolve()
        blocked = ((ROOT not in file_path.parents and file_path != ROOT) or relative.startswith(".")
                   or file_path.suffix in {".py", ".json", ".yaml", ".yml"})
        if blocked:
            self.send_error(403)
            return
        if not file_path.is_file():
            self.send_error(404)
            return
        payload = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mimetypes.guess_type(file_path)[0] or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


def create_server(host="0.0.0.0", port=None):
    return ThreadingHTTPServer((host, int(port or os.getenv("PORT", "4173"))), CineverseHandler)


if __name__ == "__main__":
    server = create_server()
    print(f"Cineverse disponível em http://localhost:{server.server_port}")
    server.serve_forever()
