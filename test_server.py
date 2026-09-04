import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from server import create_server, poster_url, release_year, search_catalog


class ServerTests(unittest.TestCase):
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

    def test_blocks_private_files(self):
        for private_file in (".env", "server.py", "render.yaml"):
            with self.subTest(private_file=private_file), self.assertRaises(HTTPError) as context:
                urlopen(f"{self.base_url}/{private_file}")
            self.assertEqual(context.exception.code, 403)
            context.exception.close()

    @patch("server.omdb")
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


if __name__ == "__main__":
    unittest.main()
