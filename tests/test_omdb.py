"""Tests for OMDb catalog behavior, independent of HTTP."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import library
from backend.omdb import catalog, catalog_by_year, poster_url, release_year, search_catalog


class OmdbTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        cache_patch = patch("backend.library.STORE", library.DiskCache(Path(temporary.name) / "cache.sqlite3"))
        cache_patch.start()
        self.addCleanup(cache_patch.stop)

    @patch("backend.omdb.omdb")
    def test_searches_omdb_and_paginates_results(self, mocked_omdb):
        def response(**params):
            page = params["page"]
            if page == 5:
                raise RuntimeError("Movie not found!")
            result_size = 5 if page == 4 else 10
            return {
                "totalResults": "35",
                "Search": [{"imdbID": f"tt{page}-{index}", "Title": f"Filme {page}-{index}",
                            "Type": "movie", "Year": "2024", "Poster": "N/A"}
                           for index in range(result_size)],
            }
        mocked_omdb.side_effect = response

        items, total = search_catalog("matrix", "Filme", "2024", 2, 24)

        self.assertEqual(total, 35)
        self.assertEqual(len(items), 11)
        self.assertEqual(items[0]["id"], "tt3-4")
        self.assertEqual(items[0]["image"], "poster-placeholder.svg")
        self.assertTrue(all(call.kwargs["type"] == "movie" for call in mocked_omdb.call_args_list))

    def test_uses_placeholder_for_missing_posters(self):
        self.assertEqual(poster_url(None), "poster-placeholder.svg")
        self.assertEqual(poster_url(""), "poster-placeholder.svg")
        self.assertEqual(poster_url("N/A"), "poster-placeholder.svg")
        self.assertEqual(poster_url("https://example.com/poster.jpg"), "https://example.com/poster.jpg")

    def test_extracts_release_year(self):
        self.assertEqual(release_year("2024"), 2024)
        self.assertEqual(release_year("2022–2025"), 2022)
        self.assertEqual(release_year("N/A"), 0)

    @patch("backend.omdb.CACHE", {"items": [], "expires": 0})
    @patch("backend.omdb._search")
    def test_catalog_handles_missing_posters_and_prioritizes_covers(self, search):
        search.return_value = [
            {"imdbID": "tt1", "Title": "Missing", "Type": "movie", "Year": "2026", "genre": "Drama"},
            {"imdbID": "tt2", "Title": "Cover", "Type": "movie", "Year": "2024", "genre": "Drama", "Poster": "https://example.com/poster.jpg"},
        ]
        items = catalog()
        self.assertEqual([item["id"] for item in items], ["tt2", "tt1"])
        self.assertEqual(items[1]["image"], "poster-placeholder.svg")
        catalog()
        calls_after_load = search.call_count
        catalog()
        self.assertEqual(search.call_count, calls_after_load)

    @patch("backend.omdb.CACHE", {"items": [], "expires": 0})
    @patch("backend.omdb._search")
    def test_catalog_covers_2000_through_2026(self, search):
        def results(task):
            _, genre, kind, year, _ = task
            return [{"imdbID": f"tt{year}-{kind}", "Title": "Title", "Type": kind,
                     "Year": str(year or 1999), "genre": genre, "Poster": "N/A"}]
        search.side_effect = results
        items = catalog()
        self.assertEqual({int(item["year"]) for item in items}, set(range(2000, 2027)))
        self.assertEqual(len(items), 54)
        self.assertEqual({item["type"] for item in items}, {"Filme", "Série"})

    @patch("backend.omdb.CACHE", {"items": [], "expires": 0})
    @patch("backend.omdb._search", return_value=[])
    def test_reports_unavailable_catalog_instead_of_empty_success(self, search):
        with self.assertRaises(RuntimeError):
            catalog()

    @patch("backend.omdb.omdb")
    def test_search_keeps_classic_titles(self, omdb):
        omdb.return_value = {"totalResults": "1", "Search": [
            {"imdbID": "tt0133093", "Title": "The Matrix", "Type": "movie", "Year": "1999", "Poster": "N/A"}
        ]}
        items, total = search_catalog("matrix", "Todos", "", 1, 10)
        self.assertEqual(items[0]["year"], "1999")
        self.assertEqual(total, 1)

    @patch("backend.omdb._search")
    def test_builds_a_deduplicated_catalog_for_a_year(self, mocked_search):
        mocked_search.return_value = [
            {"imdbID": "tt2026", "Title": "Novo filme", "Type": "movie", "Year": "2026", "Poster": "N/A", "genre": "Drama"},
            {"imdbID": "ttold", "Title": "Filme antigo", "Type": "movie", "Year": "1999", "Poster": "N/A", "genre": "Drama"},
        ]
        items = catalog_by_year("2026", "Filme")
        self.assertEqual([item["id"] for item in items], ["tt2026"])
        self.assertEqual(len(mocked_search.call_args_list), 20)


if __name__ == "__main__":
    unittest.main()
