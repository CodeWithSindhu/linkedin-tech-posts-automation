"""Generate one randomized, source-grounded LinkedIn tech post per run.

The workflow is draft-only. It does not publish to LinkedIn or call a paid AI API.
"""
from __future__ import annotations

import html
import logging
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import feedparser
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "drafts"
IMAGES_DIR = DRAFTS_DIR / "images"
MAX_ARTICLE_AGE_HOURS = int(os.getenv("MAX_ARTICLE_AGE_HOURS", "72"))
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGES_PER_POST = 3
IST = timezone(timedelta(hours=5, minutes=30))

# Wide topic coverage. A single niche is chosen per run; the chosen article
# remains the only topic in that day's post.
FEEDS = [
    ("Hacker News", "https://hnrss.org/frontpage", "tech-news"),
    ("GitHub Blog", "https://github.blog/feed/", "open-source"),
    ("GitHub Changelog", "https://github.blog/changelog/feed/", "developer-tools"),
    ("Google News — Technology", "https://news.google.com/rss/search?q=technology+when:2d&hl=en-US&gl=US", "tech-news"),
    ("DEV — Frontend", "https://dev.to/feed/tag/frontend", "frontend"),
    ("DEV — Web Development", "https://dev.to/feed/tag/webdev", "frontend"),
    ("DEV — CSS", "https://dev.to/feed/tag/css", "modern-css"),
    ("DEV — JavaScript", "https://dev.to/feed/tag/javascript", "javascript"),
    ("DEV — React", "https://dev.to/feed/tag/react", "react"),
    ("DEV — Backend", "https://dev.to/feed/tag/backend", "backend"),
    ("DEV — Python", "https://dev.to/feed/tag/python", "backend"),
    ("DEV — WordPress", "https://dev.to/feed/tag/wordpress", "wordpress"),
    ("DEV — Database", "https://dev.to/feed/tag/database", "databases"),
    ("DEV — DevOps", "https://dev.to/feed/tag/devops", "devops-cloud"),
    ("DEV — AI", "https://dev.to/feed/tag/ai", "ai"),
    ("DEV — Security", "https://dev.to/feed/tag/security", "security"),
    ("DEV — Productivity", "https://dev.to/feed/tag/productivity", "developer-hacks"),
    ("DEV — Tutorial", "https://dev.to/feed/tag/tutorial", "developer-hacks"),
    ("Stack Overflow Blog", "https://stackoverflow.blog/feed/", "developer-tools"),
    ("CSS-Tricks", "https://css-tricks.com/feed/", "modern-css"),
    ("Smashing Magazine", "https://www.smashingmagazine.com/feed/", "ui-ux-design"),
    ("Codrops", "https://tympanus.net/codrops/feed/", "ui-ux-design"),
    ("UX Collective", "https://uxdesign.cc/feed", "ui-ux-design"),
]

NICHE_LABELS = {
    "tech-news": "Technology & Tech News",
    "open-source": "Open Source",
    "developer-tools": "Developer Tools",
    "frontend": "Frontend Development",
    "modern-css": "Modern CSS & Styling",
    "javascript": "JavaScript",
    "react": "React",
    "backend": "Backend Development",
    "wordpress": "WordPress",
    "databases": "Databases",
    "devops-cloud": "DevOps & Cloud",
    "ai": "AI & Machine Learning",
    "security": "Cybersecurity",
    "developer-hacks": "Developer Tips & Smart Hacks",
    "ui-ux-design": "UI/UX & Design",
}
HASHTAGS = {
    "tech-news": "#Technology #TechNews #Innovation",
    "open-source": "#OpenSource #DeveloperTools #SoftwareDevelopment",
    "developer-tools": "#DeveloperTools #Programming #Productivity",
    "frontend": "#Frontend #WebDevelopment #JavaScript",
    "modern-css": "#CSS #WebDesign #Frontend",
    "javascript": "#JavaScript #WebDevelopment #Coding",
    "react": "#ReactJS #Frontend #JavaScript",
    "backend": "#Backend #SoftwareEngineering #Programming",
    "wordpress": "#WordPress #WebDevelopment #PHP",
    "databases": "#Databases #Backend #SoftwareEngineering",
    "devops-cloud": "#DevOps #CloudComputing #Automation",
    "ai": "#AI #MachineLearning #Technology",
    "security": "#Cybersecurity #WebSecurity #SoftwareDevelopment",
    "developer-hacks": "#CodingTips #DeveloperProductivity #Programming",
    "ui-ux-design": "#UIDesign #UX #WebDesign",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger(__name__)


class ArticleMediaParser(HTMLParser):
    """Collect article preview images and useful article-body images."""
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
            alt = (data.get("alt") or "").lower()
            if any(word in alt for word in ("avatar", "profile", "logo", "icon")):
                return
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


def clean_summary(summary: str) -> str:
    summary = re.sub(r"Article URL:\s*https?://\S+", " ", summary, flags=re.I)
    summary = re.sub(r"Comments URL:\s*https?://\S+", " ", summary, flags=re.I)
    summary = re.sub(r"\bPoints:\s*\d+", " ", summary, flags=re.I)
    summary = re.sub(r"(?:#\s*)?Comments:\s*\d+", " ", summary, flags=re.I)
    summary = clean_text(summary)
    return summary[:1100]


def collect_articles() -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_ARTICLE_AGE_HOURS)
    articles: list[dict[str, Any]] = []
    for source, feed_url, niche in FEEDS:
        LOGGER.info("Reading %s [%s]", source, niche)
        try:
            feed = feedparser.parse(feed_url, request_headers={"User-Agent": "LinkedInTechDraftBot/3.0"})
            for entry in feed.entries:
                title = clean_text(entry.get("title", ""))
                link = str(entry.get("link", "")).strip()
                published = entry_datetime(entry)
                summary = clean_summary(entry.get("summary", ""))
                if not title or not link or not published or published < cutoff:
                    continue
                if urlparse(link).scheme not in {"http", "https"}:
                    continue
                articles.append({
                    "title": title, "link": link, "published": published,
                    "summary": summary, "source": source, "niche": niche, "entry": entry,
                })
        except Exception as exc:
            LOGGER.warning("Feed failed %s: %s", source, exc)

    unique: dict[str, dict[str, Any]] = {}
    for article in articles:
        unique[article["link"]] = article
    return list(unique.values())


# Keep a feed's tag from being treated as proof of the article's niche.
NICHE_TERMS = {
    "frontend": ("frontend", "front-end", "html", "javascript", "react", "web development", "browser", "dom", "web app"),
    "modern-css": ("css", "stylesheet", "flexbox", "grid", "container query", "animation", "responsive"),
    "javascript": ("javascript", "typescript", "ecmascript", "node.js", "nodejs"),
    "react": ("react", "jsx", "next.js", "nextjs", "hooks"),
    "backend": ("backend", "back-end", "api", "server", "python", "php", "node.js", "database", "authentication"),
    "wordpress": ("wordpress", "wp-", "gutenberg", "woocommerce", "plugin", "theme development"),
    "databases": ("database", "sql", "postgres", "mysql", "mongodb", "redis", "query"),
    "devops-cloud": ("devops", "cloud", "docker", "kubernetes", "ci/cd", "deployment", "aws", "azure", "gcp"),
    "ai": ("artificial intelligence", "machine learning", "llm", "ai model", "generative ai"),
    "security": ("security", "vulnerability", "cve-", "authentication", "encryption", "privacy", "exploit"),
    "developer-hacks": ("coding", "developer", "programming", "terminal", "workflow", "shortcut", "debugging", "productivity"),
    "ui-ux-design": ("design", "ux", "ui", "user experience", "interface", "typography", "accessibility", "figma"),
    "open-source": ("open source", "github", "repository", "maintainer", "license"),
    "developer-tools": ("developer tool", "ide", "editor", "cli", "debugger", "github copilot", "vscode"),
}
PROMO_PATTERNS = (
    r"\b(?:agency|our services|hire us|contact us|book a call|free consultation|"
    r"get a quote|case study|we help businesses|at [a-z0-9-]+,? we|"
    r"best .{0,30} agency|marketing agency|revenue scale)\b",
    r"\b(?:sponsored|advertorial|affiliate link|buy now|limited time offer)\b",
)
PRACTICAL_TERMS = (
    "how to", "tutorial", "tip", "trick", "guide", "snippet", "debug", "workflow",
    "shortcut", "example", "build", "css", "layout", "release", "update", "open source",
    "design", "performance", "security", "explained", "what changed", "useful",
)


def article_is_promotional(article: dict[str, Any]) -> bool:
    text = (article["title"] + " " + article["summary"]).lower()
    return any(re.search(pattern, text, flags=re.I) for pattern in PROMO_PATTERNS)


def article_matches_niche(article: dict[str, Any]) -> bool:
    niche = article["niche"]
    text = (article["title"] + " " + article["summary"]).lower()
    if niche == "tech-news":
        # Broad tech-news feed: require a recognizable technical/product subject.
        return any(term in text for term in (
            "software", "technology", "developer", "programming", "computer",
            "ai", "chip", "browser", "internet", "open source", "security",
            "startup", "tech", "app", "platform",
        ))
    terms = NICHE_TERMS.get(niche, ())
    if not terms:
        return False
    return any(term in text for term in terms)


def quality_score(article: dict[str, Any]) -> float:
    """Rank valid candidates by freshness and practical value."""
    age = max(0.0, (datetime.now(timezone.utc) - article["published"]).total_seconds() / 3600)
    freshness = max(0.0, 100.0 - age * (100.0 / max(1, MAX_ARTICLE_AGE_HOURS)))
    text = (article["title"] + " " + article["summary"]).lower()
    relevance = sum(5 for term in PRACTICAL_TERMS if term in text)
    if 100 <= len(article["summary"]) <= 700:
        relevance += 8
    if len(article["title"]) < 22 or len(article["title"]) > 145:
        relevance -= 15
    if not article_matches_niche(article):
        relevance -= 100
    if article_is_promotional(article):
        relevance -= 150
    return freshness + relevance


def choose_one(articles: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [
        article for article in articles
        if article_matches_niche(article)
        and not article_is_promotional(article)
        and len(article["title"]) >= 22
        and len(article["title"]) <= 145
    ]
    if not valid:
        return None

    # Randomize within a small high-quality shortlist, not across unrelated labels.
    ranked = sorted(valid, key=quality_score, reverse=True)
    shortlist = ranked[:min(12, len(ranked))]
    top_score = quality_score(shortlist[0])
    shortlist = [item for item in shortlist if quality_score(item) >= top_score - 18]
    chosen = random.choice(shortlist)
    chosen["niche"] = chosen["niche"]
    return chosen


def find_image_urls(article: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    entry = article["entry"]
    for field in ("media_content", "media_thumbnail"):
        for item in entry.get(field) or []:
            if isinstance(item, dict) and item.get("url"):
                urls.append(item["url"])
    for item in entry.get("links", []) or []:
        if item.get("rel") == "enclosure" and str(item.get("type", "")).startswith("image/"):
            urls.append(item.get("href", ""))

    try:
        request = Request(article["link"], headers={"User-Agent": "Mozilla/5.0 (compatible; LinkedInTechDraftBot/3.0)"})
        with urlopen(request, timeout=15) as response:
            page = response.read(1_500_000).decode("utf-8", errors="replace")
        parser = ArticleMediaParser()
        parser.feed(page)
        urls.extend(urljoin(article["link"], url) for url in parser.urls)
    except Exception as exc:
        LOGGER.info("Article image scan skipped: %s", exc)

    valid: list[str] = []
    for candidate in urls:
        if not candidate:
            continue
        absolute = urljoin(article["link"], candidate)
        parsed = urlparse(absolute)
        lower = absolute.lower()
        if parsed.scheme not in {"http", "https"} or absolute in valid:
            continue
        if any(token in lower for token in ("avatar", "favicon", "logo-small", "pixel", "tracking", "placeholder")):
            continue
        valid.append(absolute)
    return valid[:12]


def download_images(urls: list[str], date_stamp: str) -> list[tuple[Path, str]]:
    downloaded: list[tuple[Path, str]] = []
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for index, image_url in enumerate(urls[:MAX_IMAGES_PER_POST], start=1):
        try:
            request = Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; LinkedInTechDraftBot/3.0)"})
            with urlopen(request, timeout=15) as response:
                mime = response.headers.get("Content-Type", "").split(";")[0].lower()
                if not mime.startswith("image/"):
                    continue
                data = response.read(MAX_IMAGE_BYTES + 1)
                if len(data) > MAX_IMAGE_BYTES:
                    continue
            source = Image.open(__import__("io").BytesIO(data)).convert("RGB")
            raw_path = IMAGES_DIR / f"{date_stamp}-source-{index}.jpg"
            source.thumbnail((1800, 1800))
            source.save(raw_path, "JPEG", quality=88, optimize=True)
            downloaded.append((raw_path, image_url))
        except Exception as exc:
            LOGGER.info("Image download skipped: %s", exc)
    return downloaded


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def create_social_graphic(source_path: Path, article: dict[str, Any], index: int, date_stamp: str) -> Path:
    """Create a clean image-led card: image area and text area never overlap."""
    size = 1200
    source = Image.open(source_path).convert("RGB")
    # The source photo/illustration occupies its own top region. No text is drawn
    # over it, so text embedded in a publisher image cannot collide with our copy.
    photo = ImageOps.fit(source, (size, 470), method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (13, 20, 35))
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 470, size, size), fill=(13, 20, 35))

    margin = 72
    label = NICHE_LABELS.get(article["niche"], "Technology").upper()
    draw.text((margin, 520), label, font=load_font(28, bold=True), fill=(95, 205, 255))

    title = article["title"].strip()
    max_width = size - margin * 2
    chosen_font = load_font(64, bold=True)
    lines = wrap_text(draw, title, chosen_font, max_width)
    while len(lines) > 4 and chosen_font.size > 42:
        chosen_font = load_font(chosen_font.size - 4, bold=True)
        lines = wrap_text(draw, title, chosen_font, max_width)
    y = 585
    line_height = chosen_font.size + 14
    for line in lines[:4]:
        draw.text((margin, y), line, font=chosen_font, fill=(255, 255, 255))
        y += line_height

    # Keep footer fixed and clear of the headline.
    footer = "ONE IDEA • READ THE SOURCE • TEST IT IN YOUR PROJECT"
    draw.text((margin, 1118), footer, font=load_font(22, bold=True), fill=(185, 198, 215))
    output = IMAGES_DIR / f"{date_stamp}-linkedin-card-1.jpg"
    canvas.save(output, "JPEG", quality=92, optimize=True)
    return output


def make_post(article: dict[str, Any]) -> str:
    """Write concise source-aware copy; never paste a raw, potentially truncated article."""
    niche = NICHE_LABELS.get(article["niche"], "Technology")
    title = article["title"].strip()
    summary = clean_text(article.get("summary", ""))
    # Feed descriptions are often full promotional pages. Use at most two complete
    # sentences and reject text that looks like keyword-stuffed ad copy.
    sentences = re.split(r"(?<=[.!?])\s+", summary)
    context = " ".join(sentence.strip() for sentence in sentences[:2] if sentence.strip())
    context = context[:420].rsplit(" ", 1)[0] if len(context) > 420 else context
    context = re.sub(re.escape(title), "", context, flags=re.I).strip(" -:.")

    lines = [title, ""]
    if context:
        lines.extend([context, ""])
    lines.extend([
        f"Topic: {niche}.",
        "",
        "A useful thing to check when reading this:",
        "What changed, why does it matter in a real project, and what trade-off should developers watch for?",
        "",
        f"Source: {article['link']}",
        "",
        HASHTAGS.get(article["niche"], "#Technology #Programming #Design"),
    ])
    return "\n".join(lines)


def write_draft(article: dict[str, Any], date_stamp: str) -> int:
    source_images = download_images(find_image_urls(article), date_stamp)
    graphics: list[Path] = []
    # One composed image per daily post. Original source images remain in the
    # artifact as references; don't create repetitive cards from every image.
    if source_images:
        source_path, _image_url = source_images[0]
        try:
            graphics.append(create_social_graphic(source_path, article, 1, date_stamp))
        except Exception as exc:
            LOGGER.warning("Could not create custom image %s: %s", source_path.name, exc)

    niche = article["niche"]
    label = NICHE_LABELS.get(niche, "Technology")
    post = make_post(article)
    filename = f"linkedin-post-{date_stamp}.md"
    output = DRAFTS_DIR / filename
    content = [
        f"# LinkedIn Draft — {date_stamp}", "",
        "> One-topic daily draft. Verify the article, edit the opinion to match your own experience, and check image rights before publishing.", "",
        f"**Niche:** {label}",
        f"**Topic:** {article['title']}",
        f"**Published:** {article['published'].isoformat()}",
        f"**Source:** {article['source']}",
        f"**Article:** {article['link']}",
        "", "## Suggested post", "", post, "",
        "## Custom article graphics", "",
    ]
    if graphics:
        for graphic in graphics:
            content.extend([f"![Custom article graphic](images/{graphic.name})", "", f"Image file: drafts/images/{graphic.name}", ""])
        content.append("> These are designed editorial cards made from article imagery and its headline/context. They are not AI-generated illustrations. Confirm image reuse rights and attribution before posting.")
    else:
        content.extend([
            "No usable article image was found. This draft is text-first; use the article's own image only if you have permission.",
            "",
            "> Image-led option: keep the post copy short, use one or more relevant article images, and retain the article link/source for context.",
        ])
    output.write_text("\n".join(content) + "\n", encoding="utf-8")
    LOGGER.info("Created one topic draft: %s (%d custom image(s))", filename, len(graphics))
    return len(graphics)


def main() -> int:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    # Remove previous generated packs so legacy multi-topic drafts don't remain
    # in the artifact/repository alongside today's single-topic post.
    for old_draft in DRAFTS_DIR.glob("linkedin-*.md"):
        old_draft.unlink(missing_ok=True)
    if IMAGES_DIR.exists():
        for old_image in IMAGES_DIR.iterdir():
            if old_image.is_file():
                old_image.unlink(missing_ok=True)
    articles = collect_articles()
    if not articles:
        LOGGER.error("No fresh articles found from configured feeds.")
        return 1
    selected = choose_one(articles)
    if not selected:
        LOGGER.error("No topic could be selected.")
        return 1

    # Use the local India calendar date for daily naming and schedule consistency.
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    date_stamp = now_ist.strftime("%Y-%m-%d")
    # Randomize graphic treatment; selection is randomized above as well.
    random.seed(f"{date_stamp}-{selected['link']}-{os.getenv('GITHUB_RUN_ID', 'manual')}")
    count = write_draft(selected, date_stamp)
    pack_path = DRAFTS_DIR / f"linkedin-content-pack-{date_stamp}.md"
    pack_path.write_text(
        "\n".join([
            f"# Daily LinkedIn Content — {date_stamp}", "",
            "One topic only. Niche and article are randomly selected from fresh, source-based candidates.", "",
            f"**Selected niche:** {NICHE_LABELS.get(selected['niche'], selected['niche'])}",
            f"**Selected topic:** {selected['title']}",
            f"**Source:** {selected['link']}",
            f"**Draft:** drafts/linkedin-post-{date_stamp}.md",
            f"**Custom graphics:** {count}",
            "",
            "> Selection uses recency and relevance signals, then randomizes among stronger candidates. It does not prove a topic is globally trending or viral.",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"Selected one topic: {selected['title']}")
    print(f"Daily draft: {DRAFTS_DIR / f'linkedin-post-{date_stamp}.md'}")
    print(f"Custom graphics: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
