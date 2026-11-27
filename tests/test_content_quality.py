import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import generate_draft as generator


def article(title, summary, niche="frontend"):
    return {
        "title": title,
        "summary": summary,
        "niche": niche,
        "link": "https://example.com/article",
        "published": datetime.now(timezone.utc),
        "source": "Test source",
        "entry": {},
    }


class ArticleQualityTests(unittest.TestCase):
    def test_rejects_marketing_article_in_frontend_feed(self):
        item = article(
            "Performance Marketing Agency New Mexico: How Analytix9 Engineers Profitable Revenue Scale",
            "At Analytix9, we run paid marketing campaigns for businesses seeking revenue scale.",
            "frontend",
        )
        self.assertFalse(generator.article_matches_niche(item))
        self.assertTrue(generator.article_is_promotional(item))
        self.assertIsNone(generator.choose_one([item]))

    def test_accepts_css_topic_from_css_feed(self):
        item = article(
            "A practical guide to CSS container queries for responsive components",
            "Learn how CSS container queries let components adapt to their parent layout.",
            "modern-css",
        )
        self.assertTrue(generator.article_matches_niche(item))
        self.assertFalse(generator.article_is_promotional(item))
        self.assertEqual(generator.choose_one([item])["niche"], "modern-css")

    def test_rejects_niche_mismatch(self):
        item = article(
            "A guide to paid advertising campaign management",
            "How to optimize campaign budgets and agency reporting.",
            "frontend",
        )
        self.assertIsNone(generator.choose_one([item]))


if __name__ == "__main__":
    unittest.main()
