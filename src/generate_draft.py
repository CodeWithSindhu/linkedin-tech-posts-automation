"""Generate a LinkedIn-ready draft from recent technology RSS stories.

This script only creates a local Markdown draft. It never publishes to LinkedIn.
"""
from __future__ import annotations

import html
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import feedparser

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "drafts"
MAX_ARTICLE_AGE_HOURS = int(os.getenv("MAX_ARTICLE_AGE_HOURS", "72"))
POST_HASHTAGS = ["Technology", "SoftwareDevelopment", "TechNews"]

FEEDS = [
    ("Google News — Technology", "https://news.google.com/rss/search?q=technology+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Hacker News", "https://hnrss.org/frontpage"),
    ("GitHub Blog", "https://github.blog/feed/"),
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def clean_text(value: str) -> str:
    """Remove markup and normalize whitespace from RSS fields."""
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def entry_datetime(entry: Any) -> datetime | None:
    """Convert an RSS parsed date to timezone-aware UTC."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def collect_articles() -> list[dict[str, str | datetime]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
    articles: list[dict[str, str | datetime]] = []

    for source_name, feed_url in FEEDS:
        LOGGER.info("Reading %s", source_name)
        try:
            feed = feedparser.parse(feed_url, request_headers={"User-Agent": "LinkedInTechDraftBot/1.0"})
            if getattr(feed, "bozo", False):
                LOGGER.warning("Feed returned a parsing warning: %s", source_name)
            for entry in feed.entries:
                title = clean_text(entry.get("title", ""))
                link = entry.get("link", "").strip()
                published = entry_datetime(entry)
                summary = clean_text(entry.get("summary", ""))

                if not title or not link or not published or published < cutoff:
                    continue
                if urlparse(link).scheme not in {"http", "https"}:
                    continue

                articles.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "summary": summary[:420],
                    "source": source_name,
                })
        except Exception as exc:  # A failed feed should not block the other feeds.
            LOGGER.warning("Could not read %s: %s", source_name, exc)

    # Avoid duplicate stories by URL and return newest first.
    unique: dict[str, dict[str, str | datetime]] = {}
    for article in articles:
        unique[str(article["link"])] = article

    return sorted(
        unique.values(),
        key=lambda item: item["published"],
        reverse=True,
    )


def build_post(article: dict[str, str | datetime]) -> str:
    title = str(article["title"])
    summary = str(article["summary"])
    link = str(article["link"])
    source = str(article["source"])

    lines = [
        f"📰 Tech story worth watching: {title}",
        "",
    ]
    if summary:
        lines.extend([summary, ""])
    lines.extend([
        "Why it matters:",
        "Technology moves quickly, but the important part is understanding how new developments affect the way we build, work, and solve problems.",
        "",
        "What is your take on this development? Are you already exploring it?",
        "",
        f"Read more: {link}",
        "",
        "Source: " + source,
        "",
        " ".join(f"#{tag}" for tag in POST_HASHTAGS),
    ])
    return "\n".join(lines)


def main() -> int:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    articles = collect_articles()

    if not articles:
        LOGGER.error(
            "No recent articles found. Try increasing MAX_ARTICLE_AGE_HOURS or check RSS feed availability."
        )
        return 1

    selected = articles[0]
    post = build_post(selected)
    now = datetime.now(timezone.utc)
    filename = f"linkedin-draft-{now:%Y-%m-%d}.md"
    output_path = DRAFTS_DIR / filename

    content = "\n".join([
        f"# LinkedIn Draft — {now:%Y-%m-%d}",
        "",
        "> Review the facts, wording, and source before publishing. This is an automatically assembled draft, not an endorsement.",
        "",
        f"**Topic:** {selected['title']}",
        f"**Published:** {selected['published'].isoformat()}",
        f"**Source:** {selected['source']}",
        f"**Article:** {selected['link']}",
        "",
        "## Suggested post",
        "",
        post,
        "",
    ])
    output_path.write_text(content, encoding="utf-8")
    LOGGER.info("Created draft: %s", output_path.relative_to(ROOT))
    print(f"Draft created: {output_path}")
    print("--- POST PREVIEW ---")
    print(post)
    return 0


if __name__ == "__main__":
    sys.exit(main())
