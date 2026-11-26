"""Create a daily LinkedIn content pack from fresh technology, programming, and design feeds.

Draft-only: no LinkedIn API or credentials are used.
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
MAX_IMAGES_PER_POST = 3
HASHTAGS = {
    "trending": ["TechNews", "Technology", "Innovation"],
    "programming": ["Programming", "WebDevelopment", "CodingTips"],
    "design": ["UIDesign", "WebDesign", "UX"],
}

# Feed category controls which content pack slot an article can fill.
FEEDS = [
    ("Hacker News", "https://hnrss.org/frontpage", "trending"),
    ("GitHub Blog", "https://github.blog/feed/", "trending"),
    ("GitHub Changelog", "https://github.blog/changelog/feed/", "trending"),
    ("Google News — Technology", "https://news.google.com/rss/search?q=technology+when:2d&hl=en-US&gl=US&ceid=US:en", "trending"),
    ("DEV — Web Development", "https://dev.to/feed/tag/webdev", "programming"),
    ("DEV — JavaScript", "https://dev.to/feed/tag/javascript", "programming"),
    ("DEV — Programming", "https://dev.to/feed/tag/programming", "programming"),
    ("DEV — Tutorials", "https://dev.to/feed/tag/tutorial", "programming"),
    ("DEV — Productivity", "https://dev.to/feed/tag/productivity", "programming"),
    ("Stack Overflow Blog", "https://stackoverflow.blog/feed/", "programming"),
    ("CSS-Tricks", "https://css-tricks.com/feed/", "programming"),
    ("Smashing Magazine", "https://www.smashingmagazine.com/feed/", "design"),
    ("Codrops", "https://tympanus.net/codrops/feed/", "design"),
    ("UX Collective", "https://uxdesign.cc/feed", "design"),
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger(__name__)


class ArticleMediaParser(HTMLParser):
    """Collect social preview and article-body image URLs."""
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): value for key, value in attrs if value}
        if tag.lower() == "meta":
            key = (data.get("property") or data.get("name") or "").lower()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
                self.add(data.get("content"))
        elif tag.lower() == "img":
            self.add(data.get("src") or data.get("data-src") or data.get("data-lazy-src"))

    def add(self, value: str | None) -> None:
        if value and value.strip() and value.strip() not in self.urls:
            self.urls.append(value.strip())


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def entry_datetime(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_hn_metrics(summary: str) -> tuple[int | None, int | None]:
    points = re.search(r"\bPoints:\s*(\d+)", summary, re.IGNORECASE)
    comments = re.search(r"(?:#\s*)?Comments:\s*(\d+)", summary, re.IGNORECASE)
    return (int(points.group(1)) if points else None,
            int(comments.group(1)) if comments else None)


def clean_summary(summary: str) -> str:
    for pattern in (
        r"Article URL:\s*https?://\S+",
        r"Comments URL:\s*https?://\S+",
        r"\bPoints:\s*\d+",
        r"(?:#\s*)?Comments:\s*\d+",
    ):
        summary = re.sub(pattern, " ", summary, flags=re.IGNORECASE)
    return clean_text(summary)


def collect_articles() -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
    articles: list[dict[str, Any]] = []
    for source, feed_url, category in FEEDS:
        LOGGER.info("Reading %s", source)
        try:
            feed = feedparser.parse(feed_url, request_headers={"User-Agent": "LinkedInTechDraftBot/2.0"})
            if getattr(feed, "bozo", False):
                LOGGER.warning("Feed parse warning: %s", source)
            for entry in feed.entries:
                title = clean_text(entry.get("title", ""))
                link = str(entry.get("link", "")).strip()
                published = entry_datetime(entry)
                raw = clean_text(entry.get("summary", ""))
                points, comments = parse_hn_metrics(raw)
                summary = clean_summary(raw)
                if not title or not link or not published or published < cutoff:
                    continue
                if urlparse(link).scheme not in {"http", "https"}:
                    continue
                articles.append({
                    "title": title, "link": link, "published": published,
                    "summary": summary[:900], "source": source, "category": category,
                    "points": points, "comments": comments, "entry": entry,
                })
        except Exception as exc:
            LOGGER.warning("Feed failed %s: %s", source, exc)

    unique: dict[str, dict[str, Any]] = {}
    for item in articles:
        unique[item["link"]] = item
    return list(unique.values())


def score_article(article: dict[str, Any], slot: str) -> float:
    """Prefer fresh, category-relevant content and modest HN engagement."""
    age_hours = max(0.0, (datetime.now(timezone.utc) - article["published"]).total_seconds() / 3600)
    recency = max(0.0, 100.0 - age_hours * (100.0 / MAX_ARTICLE_AGE_HOURS))
    score = recency
    if article["category"] == slot:
        score += 35
    title = article["title"].lower()
    summary = article["summary"].lower()
    text = title + " " + summary

    if slot == "programming":
        keywords = ("how to", "tutorial", "tip", "trick", "guide", "snippet", "debug", "workflow", "shortcut", "productivity", "css", "javascript", "python", "react", "wordpress")
        score += sum(8 for word in keywords if word in text)
    elif slot == "design":
        keywords = ("design", "ui", "ux", "layout", "typography", "color", "motion", "animation", "accessibility", "visual", "css")
        score += sum(9 for word in keywords if word in text)
    else:
        keywords = ("release", "launch", "announces", "introduces", "security", "update", "open source", "new")
        score += sum(6 for word in keywords if word in title)

    if isinstance(article["points"], int):
        score += min(article["points"], 100) * 0.6
    if isinstance(article["comments"], int):
        score += min(article["comments"], 100) * 0.15
    return score


def choose_articles(articles: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for slot in ("trending", "programming", "design"):
        candidates = [a for a in articles if a["link"] not in used]
        if not candidates:
            continue
        best = max(candidates, key=lambda a: score_article(a, slot))
        selected[slot] = best
        used.add(best["link"])
    return selected


def find_image_urls(article: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    entry = article["entry"]
    for field in ("media_content", "media_thumbnail"):
        for item in entry.get(field) or []:
            if isinstance(item, dict):
                candidate = item.get("url")
                if candidate:
                    urls.append(candidate)
    for item in entry.get("links", []) or []:
        if item.get("rel") == "enclosure" and str(item.get("type", "")).startswith("image/"):
            urls.append(item.get("href", ""))

    # Parse article preview metadata and a few inline content images.
    try:
        request = Request(article["link"], headers={"User-Agent": "Mozilla/5.0 (compatible; LinkedInTechDraftBot/2.0)"})
        with urlopen(request, timeout=15) as response:
            page = response.read(1_500_000).decode("utf-8", errors="replace")
        parser = ArticleMediaParser()
        parser.feed(page)
        urls.extend(urljoin(article["link"], u) for u in parser.urls)
    except Exception as exc:
        LOGGER.info("Article image scan skipped: %s", exc)

    valid: list[str] = []
    for candidate in urls:
        if not candidate:
            continue
        absolute = urljoin(article["link"], candidate)
        parsed = urlparse(absolute)
        if parsed.scheme in {"http", "https"} and absolute not in valid:
            # Avoid obvious tiny icons, avatars and tracking pixels.
            lower = absolute.lower()
            if not any(token in lower for token in ("avatar", "favicon", "logo-small", "pixel", "tracking")):
                valid.append(absolute)
    return valid[:12]


def download_images(urls: list[str], date_stamp: str, slot: str) -> list[str]:
    downloaded: list[str] = []
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for index, image_url in enumerate(urls[:MAX_IMAGES_PER_POST], start=1):
        try:
            request = Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; LinkedInTechDraftBot/2.0)"})
            with urlopen(request, timeout=15) as response:
                mime = response.headers.get("Content-Type", "").split(";")[0].lower()
                if mime not in {"image/jpeg", "image/png", "image/webp"}:
                    continue
                data = response.read(MAX_IMAGE_BYTES + 1)
                if len(data) > MAX_IMAGE_BYTES:
                    continue
            ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
            name = f"{date_stamp}-{slot}-{index}.{ext}"
            path = IMAGES_DIR / name
            path.write_bytes(data)
            downloaded.append(name)
        except Exception as exc:
            LOGGER.info("Image download skipped: %s", exc)
    return downloaded


def build_post(article: dict[str, Any], slot: str) -> str:
    title = article["title"]
    summary = article["summary"]
    link = article["link"]
    if slot == "programming":
        opening = f"Developer bookmark: {title}"
        closing = "Worth testing in a small project and keeping only if it improves your workflow."
    elif slot == "design":
        opening = f"Design inspiration: {title}"
        closing = "A useful reminder to look at the details behind the visual result—not just the screenshot."
    else:
        opening = f"Tech update: {title}"
        closing = "I’m saving this to follow how the technology develops and where it becomes useful."
    lines = [opening, ""]
    if summary:
        lines.extend([summary, ""])
    else:
        lines.extend(["Open the source for the details and add your own specific takeaway before sharing.", ""])
    lines.extend([closing, "", f"Read the original: {link}", "",
                  " ".join(f"#{tag}" for tag in HASHTAGS[slot])])
    return "\n".join(lines)


def write_draft(slot: str, article: dict[str, Any], date_stamp: str) -> list[str]:
    images = download_images(find_image_urls(article), date_stamp, slot)
    post = build_post(article, slot)
    filename = f"linkedin-{slot}-{date_stamp}.md"
    output = DRAFTS_DIR / filename
    label = {"trending": "Trending tech/news", "programming": "Programming tip or tutorial", "design": "Design/UI inspiration"}[slot]
    content = [
        f"# {label} — {date_stamp}", "",
        "> Draft only. Check the source, add your own experience or specific takeaway, and confirm image rights before publishing.", "",
        f"**Topic:** {article['title']}",
        f"**Published:** {article['published'].isoformat()}",
        f"**Source:** {article['source']}",
        f"**Article:** {article['link']}",
    ]
    if isinstance(article["points"], int):
        content.append(f"**Hacker News:** {article['points']} points / {article['comments'] or 0} comments")
    content.extend(["", "## Suggested post text", "", post, "", "## Images", ""])
    if images:
        for image_name in images:
            content.extend([f"![Article image](images/{image_name})", "", f"Image file: drafts/images/{image_name}", ""])
        content.append("> Up to three images were collected from RSS or article metadata/content. Check license/attribution. The Markdown images are a review preview; LinkedIn needs separate media upload when publishing.")
    else:
        content.append("No suitable article images could be downloaded for this story. Use the article page's image manually if appropriate.")
    output.write_text("\n".join(content) + "\n", encoding="utf-8")
    LOGGER.info("Created %s with %d image(s)", filename, len(images))
    return images


def main() -> int:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    articles = collect_articles()
    if not articles:
        LOGGER.error("No fresh articles found from configured feeds.")
        return 1
    selected = choose_articles(articles)
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pack = [f"# Daily LinkedIn Content Pack — {date_stamp}", "",
            "> Choose one draft to personalize and publish. These are source-based drafts, not AI-written analysis.", ""]
    total_images = 0
    for slot in ("trending", "programming", "design"):
        article = selected.get(slot)
        if not article:
            pack.extend([f"## {slot.title()}", "", "No matching fresh article found today.", ""])
            continue
        image_names = write_draft(slot, article, date_stamp)
        total_images += len(image_names)
        pack.extend([f"## {slot.title()}", "", f"**{article['title']}**", f"Source: {article['link']}",
                     f"Draft file: drafts/linkedin-{slot}-{date_stamp}.md",
                     f"Images downloaded: {len(image_names)}", ""])
    pack_path = DRAFTS_DIR / f"linkedin-content-pack-{date_stamp}.md"
    pack_path.write_text("\n".join(pack), encoding="utf-8")
    print(f"Content pack: {pack_path}")
    print(f"Drafts created: {len(selected)}; images downloaded: {total_images}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
