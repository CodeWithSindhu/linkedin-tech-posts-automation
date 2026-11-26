"""Generate a LinkedIn-ready draft and optional article image from public RSS feeds.

This script only creates a draft. It never publishes to LinkedIn.
"""
from __future__ import annotations

import html
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import feedparser

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "drafts"
IMAGES_DIR = DRAFTS_DIR / "images"
MAX_ARTICLE_AGE_HOURS = int(os.getenv("MAX_ARTICLE_AGE_HOURS", "72"))
MAX_IMAGE_BYTES = 4 * 1024 * 1024
POST_HASHTAGS = ["Technology", "SoftwareDevelopment", "TechNews"]

FEEDS = [
    ("Google News — Technology", "https://news.google.com/rss/search?q=technology+when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("Hacker News", "https://hnrss.org/frontpage"),
    ("GitHub Blog", "https://github.blog/feed/"),
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger(__name__)


class ImageMetaParser(HTMLParser):
    """Find common social preview image metadata in an article's HTML."""
    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        data = {key.lower(): value for key, value in attrs if value}
        property_name = (data.get("property") or data.get("name") or "").lower()
        if property_name in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
            candidate = data.get("content")
            if candidate and candidate.strip():
                self.image_url = candidate.strip()
                # Prefer the first Open Graph image; stop collecting after one.
                return


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
    points_match = re.search(r"\bPoints:\s*(\d+)", summary, re.IGNORECASE)
    comments_match = re.search(r"(?:#\s*)?Comments:\s*(\d+)", summary, re.IGNORECASE)
    return (
        int(points_match.group(1)) if points_match else None,
        int(comments_match.group(1)) if comments_match else None,
    )


def clean_article_summary(summary: str) -> str:
    summary = re.sub(r"Article URL:\s*https?://\S+", " ", summary, flags=re.IGNORECASE)
    summary = re.sub(r"Comments URL:\s*https?://\S+", " ", summary, flags=re.IGNORECASE)
    summary = re.sub(r"\bPoints:\s*\d+", " ", summary, flags=re.IGNORECASE)
    summary = re.sub(r"(?:#\s*)?Comments:\s*\d+", " ", summary, flags=re.IGNORECASE)
    return clean_text(summary)


def image_url_from_entry(entry: Any, article_url: str) -> str | None:
    """Return an image URL from RSS media fields, or article OG metadata."""
    for field in ("media_content", "media_thumbnail"):
        values = entry.get(field) or []
        for item in values:
            candidate = item.get("url") if isinstance(item, dict) else None
            if candidate and urlparse(candidate).scheme in {"http", "https"}:
                return candidate

    for item in entry.get("links", []) or []:
        if item.get("rel") == "enclosure" and str(item.get("type", "")).startswith("image/"):
            candidate = item.get("href")
            if candidate and urlparse(candidate).scheme in {"http", "https"}:
                return candidate

    try:
        request = Request(article_url, headers={"User-Agent": "Mozilla/5.0 (compatible; LinkedInTechDraftBot/1.0)"})
        with urlopen(request, timeout=12) as response:
            page = response.read(1_000_000).decode("utf-8", errors="replace")
        parser = ImageMetaParser()
        parser.feed(page)
        if parser.image_url:
            candidate = urljoin(article_url, parser.image_url)
            if urlparse(candidate).scheme in {"http", "https"}:
                return candidate
    except Exception as exc:
        LOGGER.warning("Could not inspect article for a preview image: %s", exc)
    return None


def download_image(image_url: str, date_stamp: str) -> tuple[str, str] | None:
    """Download a small, recognized image file into drafts/images."""
    try:
        request = Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; LinkedInTechDraftBot/1.0)"})
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                LOGGER.warning("Skipping unsupported image type: %s", content_type)
                return None
            data = response.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                LOGGER.warning("Skipping image larger than 4 MB")
                return None
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        image_name = f"article-image-{date_stamp}.{extension}"
        image_path = IMAGES_DIR / image_name
        image_path.write_bytes(data)
        return str(image_path.relative_to(DRAFTS_DIR)), image_name
    except Exception as exc:
        LOGGER.warning("Could not download article image: %s", exc)
        return None


def collect_articles() -> list[dict[str, str | int | datetime | None | Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
    articles: list[dict[str, str | int | datetime | None | Any]] = []

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
                    "entry": entry,
                })
        except Exception as exc:
            LOGGER.warning("Could not read %s: %s", source_name, exc)

    unique: dict[str, dict[str, str | int | datetime | None | Any]] = {}
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


def build_post(article: dict[str, str | int | datetime | None | Any]) -> str:
    title = str(article["title"])
    summary = str(article["summary"])
    link = str(article["link"])

    lines = [f"Interesting tech story: {title}", ""]
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
        LOGGER.error("No recent articles found. Check RSS feed availability or increase MAX_ARTICLE_AGE_HOURS.")
        return 1

    selected = articles[0]
    now = datetime.now(timezone.utc)
    date_stamp = now.strftime("%Y-%m-%d")
    image_info = None
    candidate_image = image_url_from_entry(selected["entry"], str(selected["link"]))
    if candidate_image:
        image_info = download_image(candidate_image, date_stamp)

    post = build_post(selected)
    output_path = DRAFTS_DIR / f"linkedin-draft-{date_stamp}.md"

    hn_metrics = ""
    if isinstance(selected["points"], int):
        hn_metrics = f"**Hacker News engagement:** {selected['points']} points"
        if isinstance(selected["comments"], int):
            hn_metrics += f", {selected['comments']} comments"

    metadata = [
        f"# LinkedIn Draft — {date_stamp}",
        "",
        "> Review the facts and add your own specific takeaway before publishing. This draft is assembled from RSS data; it is not AI fact-checking or original analysis.",
        "",
        f"**Topic:** {selected['title']}",
        f"**Published:** {selected['published'].isoformat()}",
        f"**Source:** {selected['source']}",
        f"**Article:** {selected['link']}",
    ]
    if hn_metrics:
        metadata.append(hn_metrics)

    metadata.extend(["", "## Suggested post text", "", post, ""])
    if image_info:
        relative_image_path, image_name = image_info
        metadata.extend([
            "## Image to attach",
            "",
            f"![Article image](images/{image_name})",
            "",
            f"Image file: `drafts/images/{image_name}`",
            "",
            "> This image is downloaded from the article's RSS media or social preview metadata. Check usage rights and attribution before publishing. LinkedIn publishing will need the image uploaded as media; a Markdown image alone does not publish an attachment.",
            "",
        ])
    else:
        metadata.extend([
            "## Image to attach",
            "",
            "No suitable image was found in the RSS feed or article preview metadata for this story. Choose an image from the original article manually.",
            "",
        ])

    output_path.write_text("\n".join(metadata), encoding="utf-8")
    LOGGER.info("Created draft: %s", output_path.relative_to(ROOT))
    print(f"Draft created: {output_path}")
    if image_info:
        print(f"Image saved: drafts/images/{image_info[1]}")
    print("--- POST PREVIEW ---")
    print(post)
    return 0


if __name__ == "__main__":
    sys.exit(main())
