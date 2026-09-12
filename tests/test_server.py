import json
import threading
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path

from backend import library

from backend.server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        cache_patch = patch("backend.library.STORE", library.DiskCache(Path(temporary.name) / "cache.sqlite3"))
        cache_patch.start()
        self.addCleanup(cache_patch.stop)

    @classmethod
    def setUpClass(cls):
        cls.server = create_server("127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_health_does_not_expose_key(self):
        with urlopen(f"{self.base_url}/api/health") as response:
            data = json.load(response)
            self.assertEqual(response.status, 200)
            self.assertTrue(data["ok"])
            self.assertNotIn("key", data)

    def test_serves_home_page(self):
        with urlopen(self.base_url) as response:
            html = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertIn("CINEVERSE", html)
            self.assertIn('<option value="2000">2000</option>', html)
            self.assertIn('<option value="2026">2026</option>', html)
            self.assertNotIn("<!-- YEAR_OPTIONS -->", html)

    @patch("backend.library.configured", return_value=True)
    @patch("backend.library.catalog_response")
    def test_catalog_api_includes_server_rendered_cards(self, catalog_response, configured):
        catalog_response.return_value = {"items": [{"id": "tmdb-movie-1", "title": "<Filme>"}],
                                         "total": 1, "page": 1, "pageSize": 24}
        with urlopen(f"{self.base_url}/api/catalog") as response:
            data = json.load(response)
        self.assertEqual(data["total"], 1)
        self.assertIn("&lt;Filme&gt;", data["items"][0]["html"]["card"])

    @patch("backend.library.details")
    def test_details_api_includes_server_rendered_facts(self, details):
        details.return_value = {"id": "tmdb-movie-1", "title": "Filme", "runtime": "120 min"}
        with urlopen(f"{self.base_url}/api/title/tmdb-movie-1") as response:
            data = json.load(response)
        self.assertIn("120 min", data["html"]["facts"])

    def test_blocks_private_files(self):
        for private_file in (".env", "backend/server.py", "backend/config.py", "backend/omdb.py",
                             "backend/library.py", "backend/presentation.py", "tests/test_server.py", "render.yaml"):
            with self.subTest(private_file=private_file), self.assertRaises(HTTPError) as context:
                urlopen(f"{self.base_url}/{private_file}")
            self.assertEqual(context.exception.code, 403)
            context.exception.close()

    def test_serves_frontend_assets_at_existing_urls(self):
        for asset in ("app.js", "styles.css", "poster-placeholder.svg"):
            with self.subTest(asset=asset), urlopen(f"{self.base_url}/{asset}") as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())

    @patch("backend.library.configured", return_value=False)
    @patch("backend.omdb.catalog_response")
    def test_catalog_routes_to_omdb_when_tmdb_is_not_configured(self, catalog_response, configured):
        catalog_response.return_value = {"items": [{"id": "tt1", "title": "Filme"}], "total": 1}
        with urlopen(f"{self.base_url}/api/catalog?q=matrix&page=2") as response:
            data = json.load(response)
        catalog_response.assert_called_once_with({"q": ["matrix"], "page": ["2"]})
        self.assertIn("card", data["items"][0]["html"])

    @patch("backend.omdb.details")
    def test_imdb_identifier_routes_to_omdb(self, details):
        details.return_value = {"id": "tt1", "title": "Filme"}
        with urlopen(f"{self.base_url}/api/title/tt1") as response:
            data = json.load(response)
        details.assert_called_once_with("tt1")
        self.assertIn("facts", data["html"])



if __name__ == "__main__":
    unittest.main()
