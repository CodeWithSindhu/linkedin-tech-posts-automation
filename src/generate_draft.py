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


def parse_hn_metrics(summary: str) -> tuple[int | None, int | None]:
    """Extract HN points/comments from hnrss metadata, if present."""
    points_match = re.search(r"\bPoints:\s*(\d+)", summary, re.IGNORECASE)
    comments_match = re.search(r"(?:#\s*)?Comments:\s*(\d+)", summary, re.IGNORECASE)
    points = int(points_match.group(1)) if points_match else None
    comments = int(comments_match.group(1)) if comments_match else None
    return points, comments


def clean_article_summary(summary: str) -> str:
    """Strip HN link/engagement metadata so it isn't pasted into the post."""
    summary = re.sub(r"Article URL:\s*https?://\S+", " ", summary, flags=re.IGNORECASE)
    summary = re.sub(r"Comments URL:\s*https?://\S+", " ", summary, flags=re.IGNORECASE)
    summary = re.sub(r"\bPoints:\s*\d+", " ", summary, flags=re.IGNORECASE)
    summary = re.sub(r"(?:#\s*)?Comments:\s*\d+", " ", summary, flags=re.IGNORECASE)
    return clean_text(summary)


def collect_articles() -> list[dict[str, str | int | datetime | None]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
    articles: list[dict[str, str | int | datetime | None]] = []

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
                raw_summary = clean_text(entry.get("summary", ""))
                points, comments = parse_hn_metrics(raw_summary)
                summary = clean_article_summary(raw_summary)

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
                    "points": points,
                    "comments": comments,
                })
        except Exception as exc:  # A failed feed should not block the other feeds.
            LOGGER.warning("Could not read %s: %s", source_name, exc)

    unique: dict[str, dict[str, str | int | datetime | None]] = {}
    for article in articles:
        unique[str(article["link"])] = article

    return sorted(
        unique.values(),
        key=lambda item: (
            item["points"] if isinstance(item["points"], int) else -1,
            item["published"],
        ),
        reverse=True,
    )


def build_post(article: dict[str, str | int | datetime | None]) -> str:
    """Create a clean, honest draft without pretending generic filler is analysis."""
    title = str(article["title"])
    summary = str(article["summary"])
    link = str(article["link"])
    source = str(article["source"])

    lines = [
        f"Interesting tech story: {title}",
        "",
    ]
    if summary:
        lines.extend([summary, ""])

    lines.extend([
        "The part worth looking into is what this changes for the people using it—not just the announcement itself.",
        "",
        "I’d want to understand who benefits, what trade-offs it introduces, and how it performs in real use.",
        "",
        "What’s your take?",
        "",
        f"Read the original: {link}",
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

    hn_metrics = ""
    if isinstance(selected["points"], int):
        hn_metrics = f"**Hacker News engagement:** {selected['points']} points"
        if isinstance(selected["comments"], int):
            hn_metrics += f", {selected['comments']} comments"

    metadata = [
        f"# LinkedIn Draft — {now:%Y-%m-%d}",
        "",
        "> Review and add your own specific takeaway before publishing. This draft is assembled from RSS data; it is not AI fact-checking or original analysis.",
        "",
        f"**Topic:** {selected['title']}",
        f"**Published:** {selected['published'].isoformat()}",
        f"**Source:** {selected['source']}",
        f"**Article:** {selected['link']}",
    ]
    if hn_metrics:
        metadata.append(hn_metrics)
    metadata.extend(["", "## Suggested post", "", post, ""])

    output_path.write_text("\n".join(metadata), encoding="utf-8")
    LOGGER.info("Created draft: %s", output_path.relative_to(ROOT))
    print(f"Draft created: {output_path}")
    print("--- POST PREVIEW ---")
    print(post)
    return 0


if __name__ == "__main__":
    sys.exit(main())
