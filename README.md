# LinkedIn Tech Posts Automation

A free, GitHub Actions-based project that discovers recent technology stories and creates a LinkedIn-ready draft every day.

> **Current mode: draft only.** This project does not publish to LinkedIn, does not require LinkedIn credentials, and never posts without your review.

## How it works

1. GitHub Actions runs daily on a GitHub-hosted runner (your computer does not need to be on).
2. A Python script reads public technology RSS feeds.
3. It selects a recent story, builds a concise LinkedIn post draft, and saves it in `drafts/`.
4. The draft and any available article preview image are uploaded together as a workflow artifact and committed to the repository.

The workflow can also be started manually from **Actions → Generate LinkedIn Draft → Run workflow**.

## Project structure

```text
.
├── .github/
│   └── workflows/
│       └── generate-draft.yml
├── drafts/
│   └── .gitkeep
├── src/
│   └── generate_draft.py
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

No API key or paid service is needed for draft generation.

1. Open the repository's **Actions** tab and enable workflows if GitHub asks.
2. Open **Generate LinkedIn Draft**.
3. Select **Run workflow** to test it immediately.
4. Open the completed run and download the `linkedin-post-draft` artifact, or check the latest file in `drafts/`.

The scheduled run is set for **09:00 Asia/Kolkata** (03:30 UTC). GitHub may delay scheduled workflows during periods of high load; manual dispatch is available for immediate testing.

## Sources

The script uses public RSS feeds from:
- Google News technology search
- Hacker News
- The GitHub Blog

For Hacker News stories, it extracts points/comments and prioritizes higher-point stories among the recent feed items. Other feeds are fallback candidates based on recency. This is a lightweight popularity signal, not a complete trend analysis.

The generator removes Hacker News metadata from the post body so points/comments/URLs are not pasted as article text. It does not use an AI model, verify the article's claims, or create original reporting; add your own specific insight before publishing. Feed availability and article recency can vary.

If the feed or article page provides an image, the script downloads a supported JPEG, PNG, or WebP image (up to 4 MB) into `drafts/images/` and adds an image preview to the Markdown draft. The image is included in the workflow artifact. Some articles have no usable preview image, so image attachment is best-effort. Check image usage rights and attribution before posting.

## Customization

Edit `FEEDS`, `MAX_ARTICLE_AGE_HOURS`, and `POST_HASHTAGS` in `src/generate_draft.py`.

## LinkedIn publishing (future phase)

Automatic publishing is intentionally not configured. It requires a LinkedIn Developer application, approval for the appropriate posting product/permission, and a securely stored OAuth access token. Do not add tokens to source files or commit history. Until those prerequisites are met, review and publish drafts manually. For image posts, the image file must be uploaded to LinkedIn as media; the Markdown preview is for draft review and is not itself a LinkedIn attachment.

## License

MIT
