import unittest

from backend import presentation


class PresentationTests(unittest.TestCase):
    def test_missing_poster_and_escaping(self):
        movie = {"id": '" onclick="bad', "title": "<Lost>", "image": "N/A"}
        rendered = presentation.present(movie)["html"]
        self.assertIn("no-cover", rendered["poster"])
        self.assertNotIn("<img", rendered["poster"])
        self.assertNotIn("<Lost>", rendered["card"])
        self.assertIn("&lt;Lost&gt;", rendered["card"])
        self.assertIn('data-open="&quot; onclick=&quot;bad"', rendered["card"])

    def test_catalog_keeps_data_and_renders_suggestions(self):
        movie = {"id": "tt1", "title": "Filme", "image": "https://example.com/a.jpg"}
        data = {"items": [movie], "featured": [movie], "total": 25, "page": 2,
                "suggestions": ['<script>"']}
        result = presentation.catalog(data)
        self.assertEqual(result["total"], 25)
        self.assertEqual(result["page"], 2)
        self.assertIn("<img", result["items"][0]["html"]["poster"])
        self.assertIn("heroMeta", result["featured"][0]["html"])
        self.assertNotIn("<script>", result["suggestionsHtml"])
        self.assertNotIn("html", movie)

    def test_details_escape_provider_text(self):
        result = presentation.present({"id": "tt1", "title": "Filme", "cast": ["<actor>"],
                                       "seasons": 3, "originalTitle": "Original"})["html"]
        self.assertIn("&lt;actor&gt;", result["facts"])
        self.assertIn("Temporadas", result["facts"])
        self.assertIn("Título original", result["facts"])
