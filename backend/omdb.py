"""OMDb provider: requests, catalog, search, filters and details."""
import json
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Lock
from urllib.parse import urlencode
from urllib.request import urlopen

from .config import MIN_YEAR, CURRENT_YEAR
from . import library

OMDB_URL = "https://www.omdbapi.com/"
SEEDS = (("star", "Ficção"), ("dark", "Suspense"), ("love", "Drama"), ("war", "Ação"),
         ("life", "Drama"), ("world", "Aventura"), ("night", "Suspense"),
         ("last", "Drama"), ("dead", "Suspense"), ("the", "Outros"))
CACHE = {"items": [], "expires": 0.0}
YEAR_CACHE = {}
DETAILS = {}
CATALOG_LOCK = Lock()


def poster_url(value):
    return value if value and value != "N/A" else "poster-placeholder.svg"


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


def as_movie(item):
    return {
        "id": item["imdbID"], "title": item.get("Title", "Sem título"),
        "type": "Filme" if item.get("Type") == "movie" else "Série",
        "genre": item.get("genre", "Resultado da pesquisa"), "year": item.get("Year", "—"),
        "score": "—", "image": poster_url(item.get("Poster")),
    }


def collect_titles(tasks, accepts_year, workers):
    unique = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for results in pool.map(_search, tasks):
            for item in results:
                identifier = item.get("imdbID")
                if identifier and identifier not in unique and accepts_year(release_year(item.get("Year"))):
                    unique[identifier] = as_movie(item)
    return unique


def catalog():
    with CATALOG_LOCK:
        if not CACHE["items"]:
            cached = library.STORE.get("omdb:catalog:v2")
            if cached:
                CACHE.update(items=cached, expires=time.time() + 3600)
        return build_catalog()


def build_catalog():
    if CACHE["items"] and CACHE["expires"] > time.time():
        return CACHE["items"]
    tasks = [(term, genre, media_type, None, 1) for term, genre in SEEDS for media_type in ("movie", "series")]
    # Include every year instead of relying only on broad searches for recent titles.
    tasks += [("love", "Drama", media_type, year, 1)
              for year in range(MIN_YEAR, CURRENT_YEAR + 1)
              for media_type in ("movie", "series")]
    unique = collect_titles(tasks, lambda year: MIN_YEAR <= year <= CURRENT_YEAR, 13)
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
    unique = collect_titles(tasks, lambda release: release == int(year), 20)
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
    items = [as_movie(item) for item in raw_items[offset:offset + page_size]]
    total = int(responses[0].get("totalResults", 0)) if responses else 0
    return items, total


def catalog_response(query):
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
        return {"items": items, "total": total, "page": page, "pageSize": page_size}
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
    return {"items": items[start:start + page_size], "total": len(items),
            "page": page, "pageSize": page_size, "featured": featured}


def details(movie_id):
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
    return DETAILS[movie_id]


def normalize(value):
    return "".join(char for char in unicodedata.normalize("NFD", value.casefold())
                   if not unicodedata.combining(char))
