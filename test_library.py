import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import library


def movie(identifier=1, title="A Origem", original="Inception", year="2010", kind="movie", genres=None):
    return library.as_movie({"id": identifier, "title": title, "original_title": original,
                            "release_date": year + "-07-01", "first_air_date": year + "-07-01",
                            "genre_ids": genres or [878, 28], "vote_average": 8.4,
                            "vote_count": 500, "popularity": 45, "backdrop_path": "/scene.jpg",
                            "poster_path": "/poster.jpg", "overview": "Uma aventura dentro dos sonhos."}, kind)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "cache.sqlite3"
        patcher = patch("library.STORE", library.DiskCache(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cache_survives_new_instance(self):
        library.STORE.put("catalog", [movie()])
        self.assertEqual(library.DiskCache(self.path).get("catalog")[0]["title"], "A Origem")

    def test_cache_expiry_and_stale_fallback(self):
        library.STORE.put("old", [movie()], ttl=-1)
        self.assertIsNone(library.STORE.get("old"))
        self.assertEqual(len(library.STORE.get("old", stale=True)), 1)

    def test_maps_real_genres_and_landscape_image(self):
        item = movie()
        self.assertEqual(item["genres"], ["Ficção", "Ação"])
        self.assertEqual(item["backdrop"], "https://image.tmdb.org/t/p/w1280/scene.jpg")

    def test_preserves_title_words_and_years(self):
        for title in ("Drama", "2001", "Filme de terror", "Amor em 2024"):
            self.assertEqual(library.interpret_query(title, [movie(title=title)]), (title, {}))
        self.assertEqual(library.interpret_query("O ano de 2024", []), ("O ano de 2024", {}))

    def test_interprets_complete_filter_expression(self):
        self.assertEqual(library.interpret_query("séries de drama de 2024", []),
                         ("", {"type": "Série", "genre": "Drama", "year": "2024"}))
        self.assertEqual(library.interpret_query("ficção científica", []), ("", {"genre": "Ficção"}))

    @patch("library.tmdb", return_value={"results": []})
    def test_searches_portuguese_original_and_typos(self, api):
        for query in ("a origem", "Inception", "Incepton"):
            items, suggestions, correction = library.search(query, [movie()])
            self.assertEqual(items[0]["title"], "A Origem")
            self.assertIn("A Origem", suggestions)
        self.assertEqual(correction, "A Origem")

    @patch("library.tmdb")
    def test_filters_people_and_dates_from_remote_search(self, api):
        api.return_value = {"results": [
            {"id": 1, "media_type": "person"},
            {"id": 2, "media_type": "movie", "release_date": "1999-01-01"},
            {"id": 3, "media_type": "tv", "first_air_date": "2026-01-01", "name": "Nova série"},
        ]}
        items, _, _ = library.search("Nova", [])
        self.assertEqual([item["id"] for item in items], ["tmdb-tv-3"])

    @patch("library.catalog")
    def test_filters_paginate_and_rating_use_vote_threshold(self, catalog):
        weak = movie(2)
        weak.update(votes=2, score=10)
        catalog.return_value = [movie(), weak, movie(3, year="2020", kind="tv", genres=[18])]
        response = library.catalog_response({"order": ["rating"], "pageSize": ["1"]})
        self.assertEqual(response["total"], 2)
        self.assertEqual(len(response["items"]), 1)
        response = library.catalog_response({"q": ["séries de drama de 2020"]})
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["type"], "Série")

    @patch("library.tmdb")
    def test_details_include_runtime_cast_and_localized_synopsis(self, api):
        api.return_value = {"id": 1, "title": "A Origem", "release_date": "2010-07-01", "runtime": 148,
                            "overview": "Uma aventura dentro dos sonhos.", "credits": {"cast": [{"name": "Ator"}]},
                            "genres": [{"id": 878, "name": "Ficção científica"}]}
        result = library.details("tmdb-movie-1")
        self.assertEqual(result["runtime"], "148 min")
        self.assertEqual(result["cast"], ["Ator"])
        self.assertEqual(result["synopsis"], "Uma aventura dentro dos sonhos.")
        with self.assertRaises(ValueError):
            library.details("../secrets")

    @patch("library.tmdb")
    def test_catalog_covers_every_year_and_reuses_disk(self, api):
        def response(path, **params):
            year = params.get("primary_release_date.gte", params.get("first_air_date.gte"))[:4]
            return {"results": [{"id": int(year), "release_date": year + "-01-01", "first_air_date": year + "-01-01"}]}
        api.side_effect = response
        items = library.catalog()
        self.assertEqual(len(items), 54)
        self.assertEqual({int(item["year"]) for item in items}, set(range(2000, 2027)))
        calls = api.call_count
        library.catalog()
        self.assertEqual(api.call_count, calls)


if __name__ == "__main__":
    unittest.main()
