"""Localized catalog, search and restart-safe provider cache."""
import json
import heapq
import os
import re
import sqlite3
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import ROOT, MIN_YEAR, CURRENT_YEAR as MAX_YEAR
MIN_RATING_VOTES = 100
GENRES = {28: "Ação", 12: "Aventura", 16: "Animação", 35: "Comédia", 80: "Crime",
          99: "Documentário", 18: "Drama", 10751: "Família", 14: "Fantasia", 36: "História",
          27: "Terror", 10402: "Música", 9648: "Mistério", 10749: "Romance", 878: "Ficção",
          10770: "Filme para TV", 53: "Suspense", 10752: "Guerra", 37: "Faroeste",
          10759: "Ação", 10762: "Infantil", 10763: "Notícias", 10764: "Reality",
          10765: "Ficção", 10766: "Novela", 10767: "Talk show", 10768: "Guerra"}
CATALOG_LOCK = Lock()


class DiskCache:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("CATALOG_CACHE_PATH", ROOT / ".cache" / "catalog.sqlite3"))

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)")
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, key, stale=False):
        try:
            with self.connect() as connection:
                row = connection.execute("SELECT value, expires FROM cache WHERE key = ?", (key,)).fetchone()
            return json.loads(row[0]) if row and (stale or row[1] > time.time()) else None
        except (OSError, sqlite3.Error, ValueError):
            return None

    def put(self, key, value, ttl=86400):
        try:
            with self.connect() as connection:
                connection.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                                   (key, json.dumps(value, ensure_ascii=False), time.time() + ttl))
                connection.execute("DELETE FROM cache WHERE expires < ?", (time.time() - 30 * 86400,))
        except (OSError, sqlite3.Error):
            pass  # A read-only/full disk must not make the site unavailable.


STORE = DiskCache()


def configured():
    return bool(os.getenv("TMDB_API_KEY", "").strip() or os.getenv("TMDB_ACCESS_TOKEN", "").strip())


def normalize(value):
    return " ".join("".join(char for char in unicodedata.normalize("NFD", str(value).casefold())
                            if not unicodedata.combining(char)).split())


def tmdb(path, **params):
    params = {"language": "pt-BR", **params}
    cache_key = "tmdb:v1:" + path + ":" + urlencode(sorted(params.items()))
    cached = STORE.get(cache_key)
    if cached is not None:
        return cached
    token = os.getenv("TMDB_ACCESS_TOKEN", "").strip()
    key = os.getenv("TMDB_API_KEY", "").strip()
    if not token and not key:
        raise RuntimeError("TMDB não configurado.")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        params["api_key"] = key
    request = Request(f"https://api.themoviedb.org/3/{path}?{urlencode(params)}", headers=headers)
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        cached = STORE.get(cache_key, stale=True)
        if cached is not None:
            return cached
        raise RuntimeError("Não foi possível consultar o TMDB. Tente novamente em instantes.") from None
    STORE.put(cache_key, data, 3600 if path.startswith("search/") else 7 * 86400)
    return data


def image_url(path, size="w500"):
    return f"https://image.tmdb.org/t/p/{size}{path}" if path and path.startswith("/") else ""


def as_movie(data, kind):
    genres = [GENRES.get(genre, "Outros") for genre in data.get("genre_ids", [])]
    if data.get("genres"):
        genres = [GENRES.get(genre["id"], genre["name"]) for genre in data["genres"]]
    date = data.get("release_date" if kind == "movie" else "first_air_date", "")
    return {
        "id": f"tmdb-{kind}-{data['id']}", "title": data.get("title") or data.get("name") or "Sem título",
        "originalTitle": data.get("original_title") or data.get("original_name") or "",
        "type": "Filme" if kind == "movie" else "Série", "genres": list(dict.fromkeys(genres)),
        "genre": " · ".join(dict.fromkeys(genres)) or "Não informado", "year": date[:4],
        "score": round(data.get("vote_average") or 0, 1) or "—", "votes": data.get("vote_count", 0),
        "popularity": data.get("popularity", 0), "image": image_url(data.get("poster_path")) or "poster-placeholder.svg",
        "backdrop": image_url(data.get("backdrop_path"), "w1280"),
        "synopsis": data.get("overview") or "Sinopse em português ainda indisponível.", "source": "TMDB",
    }


def in_range(movie):
    return movie["year"].isdigit() and MIN_YEAR <= int(movie["year"]) <= MAX_YEAR


def catalog():
    with CATALOG_LOCK:
        cached = STORE.get("tmdb:catalog:v2")
        if cached is not None:
            return cached

        def fetch(task):
            kind, year = task
            field = "primary_release_date" if kind == "movie" else "first_air_date"
            data = tmdb(f"discover/{kind}", **{
                f"{field}.gte": f"{year}-01-01", f"{field}.lte": f"{year}-12-31",
                "sort_by": "popularity.desc", "include_adult": "false", "vote_count.gte": 5,
            })
            return [as_movie(item, kind) for item in data.get("results", [])]

        tasks = [(kind, year) for year in range(MAX_YEAR, MIN_YEAR - 1, -1) for kind in ("movie", "tv")]
        try:
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(fetch, tasks))
        except RuntimeError:
            cached = STORE.get("tmdb:catalog:v2", stale=True)
            if cached:
                return cached
            raise
        unique = {item["id"]: item for batch in results for item in batch if in_range(item)}
        items = sorted(unique.values(), key=lambda item: item["popularity"], reverse=True)
        if not items:
            raise RuntimeError("Nenhum título disponível no momento.")
        STORE.put("tmdb:catalog:v2", items, 86400)
        return items


def catalog_by_year(year, media_type="Todos", genre="Todos", order="popular", page=1, size=24):
    """Merge provider pages lazily instead of downloading an entire year."""
    year = int(year)
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError("Ano inválido.")
    kinds = ("movie",) if media_type == "Filme" else ("tv",) if media_type == "Série" else ("movie", "tv")

    def discover(kind, start, end):
        field = "primary_release_date" if kind == "movie" else "first_air_date"
        sort = "vote_average.desc" if order == "rating" else "popularity.desc"
        if order == "title":
            sort = "title.asc" if kind == "movie" else "name.asc"
        params = {f"{field}.gte": start.isoformat(), f"{field}.lte": end.isoformat(),
                  "sort_by": sort, "include_adult": "false"}
        if order == "rating":
            params["vote_count.gte"] = MIN_RATING_VOTES
        if genre != "Todos":
            params["with_genres"] = "|".join(str(identifier) for identifier, name in GENRES.items() if name == genre) or "0"
        first = tmdb(f"discover/{kind}", page=1, **params)
        if int(first.get("total_pages", 1)) > 500:
            if start == end:
                raise RuntimeError("Limite de resultados do provedor atingido.")
            middle = start + (end - start) // 2
            return discover(kind, start, middle) + discover(kind, middle + timedelta(days=1), end)
        return [(kind, params, first)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(lambda kind: discover(kind, date(year, 1, 1), date(year, 12, 31)), kinds))
    streams = [stream for batch in batches for stream in batch]
    total = sum(int(first.get("total_results", len(first.get("results", [])))) for _, _, first in streams)
    start = (page - 1) * size
    if start >= total:
        return [], total

    def results(kind, params, first):
        yield from first.get("results", [])
        for number in range(2, int(first.get("total_pages", 1)) + 1):
            yield from tmdb(f"discover/{kind}", page=number, **params).get("results", [])

    def sort_key(item):
        if order == "title":
            return normalize(item.get("title") or item.get("name") or "")
        return -(item.get("vote_average" if order == "rating" else "popularity") or 0)

    def stream(kind, params, first):
        for raw in results(kind, params, first):
            yield raw, kind

    merged = heapq.merge(*(stream(*batch) for batch in streams), key=lambda pair: sort_key(pair[0]))
    selected, seen, count = [], set(), 0
    for raw, kind in merged:
        item = as_movie(raw, kind)
        if item["year"] != str(year) or item["id"] in seen:
            continue
        seen.add(item["id"])
        if count >= start:
            selected.append(item)
        count += 1
        if count == start + size:
            break
    return selected, total



def titles(movie):
    return {normalize(movie["title"]), normalize(movie.get("originalTitle", ""))} - {""}


def interpret_query(query, items):
    """Only parse full filter expressions; never remove words from a film title."""
    normalized = normalize(query)
    if any(normalized in titles(item) for item in items):
        return query, {}
    genre_names = {normalize(name): name for name in GENRES.values()}
    genre_names["ficcao cientifica"] = "Ficção"
    pattern = r"(?:(filmes?|series?)\s*)?(?:(?:de\s+)?(" + "|".join(sorted(genre_names, key=len, reverse=True)) + r")\s*)?(?:(?:de|em)\s+)?(20\d{2})?"
    match = re.fullmatch(pattern, normalized)
    if not match or not any(match.groups()):
        return query, {}
    kind, genre, year = match.groups()
    if year and not MIN_YEAR <= int(year) <= MAX_YEAR:
        return query, {}
    return "", {key: value for key, value in {
        "type": ("Filme" if kind.startswith("film") else "Série") if kind else None,
        "genre": genre_names.get(genre), "year": year,
    }.items() if value}


def match_score(query, movie):
    query = normalize(query)
    scores = []
    for title in titles(movie):
        if query == title:
            scores.append(3)
        elif query in title:
            scores.append(2)
        elif len(query) >= 4:
            scores.append(max(SequenceMatcher(None, query, title).ratio(),
                              *(SequenceMatcher(None, query, word).ratio() for word in title.split())))
    return max(scores, default=0)


def search(query, local):
    ranked = sorted(((match_score(query, item), item) for item in local), key=lambda pair: pair[0], reverse=True)
    suggestions = list(dict.fromkeys(item["title"] for score, item in ranked if score >= .72))[:5]
    matches = [item for score, item in ranked if score >= 2]
    # Search the provider as well, so titles outside the curated selection remain discoverable.
    try:
        data = tmdb("search/multi", query=query, include_adult="false", page=1)
    except RuntimeError:
        if not matches:
            raise
        data = {}
    remote = [as_movie(item, item["media_type"]) for item in data.get("results", [])
              if item.get("media_type") in ("movie", "tv") and not item.get("adult")]
    matches = list({item["id"]: item for item in [*matches, *remote] if in_range(item)}.values())
    correction = ""
    if not matches and suggestions:
        matches = [item for score, item in ranked if score >= .72][:12]
        correction = suggestions[0]
    return matches, suggestions, correction


def catalog_response(query):
    value = lambda key, default="": query.get(key, [default])[0]
    page = max(1, int(value("page", "1")))
    size = min(48, max(1, int(value("pageSize", "24"))))
    local = [] if value("year") and not value("q").strip() else catalog()
    q, interpreted = interpret_query(value("q").strip()[:160], local)
    kind = interpreted.get("type", value("type", "Todos"))
    genre = interpreted.get("genre", value("genre", "Todos"))
    year = interpreted.get("year", value("year"))
    if year and not q:
        items, total = catalog_by_year(year, kind, genre, value("order", "popular"), page, size)
        return {"items": items, "total": total, "page": page, "pageSize": size,
                "featured": [], "source": "TMDB", "suggestions": [], "correction": "",
                "interpreted": interpreted, "searchLimited": False}
    items, suggestions, correction = search(q, local) if q else (local, [], "")
    items = [item for item in items if (kind == "Todos" or item["type"] == kind)
             and (genre == "Todos" or genre in item["genres"]) and (not year or item["year"] == year)]
    order = value("order", "popular")
    if order == "title":
        items.sort(key=lambda item: normalize(item["title"]))
    elif order == "recent":
        items.sort(key=lambda item: (item["year"], item["popularity"]), reverse=True)
    elif order == "rating":
        items = [item for item in items if item["votes"] >= MIN_RATING_VOTES]
        items.sort(key=lambda item: (float(item["score"] if item["score"] != "—" else 0), item["votes"]), reverse=True)
    elif not q:
        items.sort(key=lambda item: item["popularity"], reverse=True)
    featured = []
    for kind in ("Filme", "Série"):
        featured.extend([item for item in local if item["type"] == kind and item["backdrop"]][:4])
    start = (page - 1) * size
    return {"items": items[start:start + size], "total": len(items), "page": page, "pageSize": size,
            "featured": featured, "source": "TMDB", "suggestions": suggestions, "correction": correction,
            "interpreted": interpreted, "searchLimited": bool(q)}


def details(movie_id):
    match = re.fullmatch(r"tmdb-(movie|tv)-(\d+)", movie_id)
    if not match:
        raise ValueError("Identificador inválido.")
    kind, identifier = match.groups()
    data = tmdb(f"{kind}/{identifier}", append_to_response="credits,external_ids,alternative_titles")
    movie = as_movie(data, kind)
    runtime = data.get("runtime") or next(iter(data.get("episode_run_time") or []), None)
    movie.update(runtime=f"{runtime} min" if runtime else "Não informada",
                 cast=[person["name"] for person in data.get("credits", {}).get("cast", [])[:6]],
                 seasons=data.get("number_of_seasons"), ratingSource="TMDB",
                 imdbId=data.get("imdb_id") or data.get("external_ids", {}).get("imdb_id"))
    return movie
