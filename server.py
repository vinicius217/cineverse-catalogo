import json
import mimetypes
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
OMDB_URL = "https://www.omdbapi.com/"
SEEDS = (("star", "Ficção"), ("dark", "Suspense"), ("love", "Drama"), ("war", "Ação"),
         ("life", "Drama"), ("world", "Aventura"), ("night", "Suspense"),
         ("last", "Drama"), ("dead", "Suspense"), ("the", "Outros"))
CACHE = {"items": [], "expires": 0.0}
YEAR_CACHE = {}
DETAILS = {}
CATALOG_LOCK = Lock()
MIN_YEAR = 2000
CURRENT_YEAR = 2026


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

import library


def omdb(**params):
    key = os.getenv("OMDB_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Configure OMDB_API_KEY no arquivo .env")
    return cached_omdb(key, tuple(sorted(params.items())), int(time.time() // 3600))


@lru_cache(maxsize=256)
def cached_omdb(key, params, time_bucket):
    cache_key = "omdb:v1:" + urlencode(params)
    cached = library.STORE.get(cache_key)
    if cached is not None:
        return cached
    query = urlencode({"apikey": key, **dict(params)})
    with urlopen(f"{OMDB_URL}?{query}", timeout=15) as response:
        data = json.load(response)
    if data.get("Response") == "False":
        raise RuntimeError(data.get("Error", "Erro ao consultar a OMDb"))
    library.STORE.put(cache_key, data, 7 * 86400)
    return data


def release_year(value):
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return 0


def _search(task):
    term, genre, media_type, year, page = task
    try:
        params = {"s": term, "type": media_type, "page": page}
        if year:
            params["y"] = year
        data = omdb(**params)
        return [dict(item, genre=genre) for item in data.get("Search", [])]
    except Exception:
        return []


def catalog():
    with CATALOG_LOCK:
        if not CACHE["items"]:
            cached = library.STORE.get("omdb:catalog:v2")
            if cached:
                CACHE.update(items=cached, expires=time.time() + 3600)
        items = build_catalog()
        return items


def build_catalog():
    if CACHE["items"] and CACHE["expires"] > time.time():
        return CACHE["items"]
    tasks = [(term, genre, media_type, None, 1) for term, genre in SEEDS for media_type in ("movie", "series")]
    # Include every year instead of relying only on broad searches for recent titles.
    tasks += [("love", "Drama", media_type, year, 1)
              for year in range(MIN_YEAR, CURRENT_YEAR + 1)
              for media_type in ("movie", "series")]
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
                        "score": "—", "image": poster_url(item.get("Poster")),
                    }
    items = sorted(unique.values(), key=lambda item: (item["image"] != "poster-placeholder.svg", release_year(item["year"]), item["title"]), reverse=True)
    if not items:
        if CACHE["items"]:
            return CACHE["items"]
        raise RuntimeError("Catálogo indisponível. Verifique a conexão e a configuração da OMDb.")
    CACHE.update(items=items, expires=time.time() + 7 * 86400)
    library.STORE.put("omdb:catalog:v2", items, 7 * 86400)
    return CACHE["items"]


def catalog_by_year(year, media_type="Todos"):
    cache_key = (year, media_type)
    cached = YEAR_CACHE.get(cache_key)
    if cached and cached["expires"] > time.time():
        return cached["items"]
    types = (("movie",) if media_type == "Filme" else ("series",) if media_type == "Série" else ("movie", "series"))
    tasks = [(term, genre, kind, year, page) for term, genre in SEEDS for kind in types for page in (1, 2)]
    unique = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        for results in pool.map(_search, tasks):
            for item in results:
                movie_id = item.get("imdbID")
                if movie_id and release_year(item.get("Year")) == int(year) and movie_id not in unique:
                    unique[movie_id] = {
                        "id": movie_id, "title": item.get("Title", "Sem título"),
                        "type": "Filme" if item.get("Type") == "movie" else "Série",
                        "genre": item["genre"], "year": item.get("Year", "—"),
                        "score": "—", "image": poster_url(item.get("Poster")),
                    }
    items = sorted(unique.values(), key=lambda item: item["title"].casefold())
    YEAR_CACHE[cache_key] = {"items": items, "expires": time.time() + 86400}
    return items


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
    } for item in raw_items[offset:offset + page_size]]
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
        if library.configured():
            return self.send_json(200, library.catalog_response(query))
        value = lambda key, default="": query.get(key, [default])[0]
        q, media_type, genre, year = value("q").lower(), value("type", "Todos"), value("genre", "Todos"), value("year")
        q, interpreted = library.interpret_query(q, CACHE["items"]) if q else (q, {})
        media_type = interpreted.get("type", media_type)
        genre = interpreted.get("genre", genre)
        year = interpreted.get("year", year)
        order = value("order", "recent")
        page = max(1, int(value("page", "1")))
        page_size = min(48, max(1, int(value("pageSize", "24"))))
        if q and genre == "Todos":
            items, total = search_catalog(q, media_type, year, page, page_size)
            return self.send_json(200, {"items": items, "total": total, "page": page, "pageSize": page_size})
        source = catalog_by_year(year, media_type) if year else catalog()
        items = [item for item in source
                 if (not q or normalize(q) in normalize(f'{item["title"]} {item["genre"]}'))
                 and (media_type == "Todos" or item["type"] == media_type)
                 and (genre == "Todos" or item["genre"] == genre)
                 and (not year or item["year"].startswith(year))]
        if order == "title":
            items.sort(key=lambda item: item["title"].casefold())
        start = (page - 1) * page_size
        featured = []
        if not q and not year:
            for kind in ("Filme", "Série"):
                candidates = [item for item in source if item["type"] == kind and item["image"] != "poster-placeholder.svg"]
                # Spread highlights across the catalog's years and keep both formats.
                indexes = sorted({round(index * (len(candidates) - 1) / 3) for index in range(4)}) if candidates else []
                featured.extend(candidates[index] for index in indexes)
        self.send_json(200, {"items": items[start:start + page_size], "total": len(items), "page": page, "pageSize": page_size, "featured": featured})

    def title_route(self, movie_id):
        if movie_id.startswith("tmdb-"):
            return self.send_json(200, library.details(movie_id))
        if movie_id not in DETAILS:
            data = omdb(i=movie_id, plot="full")
            DETAILS[movie_id] = {
                "id": data["imdbID"], "title": data["Title"],
                "type": "Filme" if data.get("Type") == "movie" else "Série",
                "genre": "Não informado" if data.get("Genre") == "N/A" else data.get("Genre"),
                "year": data.get("Year"), "score": "—" if data.get("imdbRating") == "N/A" else data.get("imdbRating"),
                "synopsis": "Sinopse indisponível." if data.get("Plot") == "N/A" else data.get("Plot"),
                "image": poster_url(data.get("Poster")),
                "runtime": data.get("Runtime", "Não informada"),
                "cast": [] if data.get("Actors") in (None, "N/A") else data["Actors"].split(", "),
                "ratingSource": "IMDb", "source": "OMDb",
            }
        self.send_json(200, DETAILS[movie_id])

    def static_file(self, request_path):
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        file_path = (ROOT / relative).resolve()
        public_files = {"index.html", "app.js", "styles.css", "poster-placeholder.svg"}
        blocked = ROOT not in file_path.parents or relative not in public_files
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


def normalize(value):
    return "".join(char for char in unicodedata.normalize("NFD", value.casefold())
                   if not unicodedata.combining(char))


def create_server(host="0.0.0.0", port=None):
    return ThreadingHTTPServer((host, int(port or os.getenv("PORT", "4173"))), CineverseHandler)


if __name__ == "__main__":
    server = create_server()
    print(f"Cineverse disponível em http://localhost:{server.server_port}")
    server.serve_forever()
