# LinkedIn Tech Posts Automation

A free, GitHub Actions-based daily LinkedIn draft generator. It runs on GitHub-hosted runners, so your PC can be switched off.

**Draft-only:** It does not publish to LinkedIn and does not need LinkedIn credentials or a paid AI API.

## Daily behavior

The generator creates **one topic and one LinkedIn draft per run**, not three unrelated category posts.

It scans recent articles across a broad technology mix, rejects promotional or niche-mismatched items, then randomly chooses from a shortlist of higher-quality candidates:

- Frontend and backend development
- Modern CSS and styling techniques
- JavaScript, React, Python, and WordPress
- Databases, DevOps, cloud, and developer tools
- AI, cybersecurity, and open source
- UI/UX, design, tutorials, productivity tips, and smart developer hacks
- General technology news

It filters by article age, checks the article title/description against niche-specific terms, rejects common promotional/SEO patterns, scores freshness and practical value, then randomizes among a small shortlist. If no suitable article survives, the run fails rather than forcing a bad topic. Random selection does **not** mean every selected item is objectively trending or viral.

## Output

The workflow writes:

- drafts/linkedin-post-YYYY-MM-DD.md — one article, its source context, and one suggested post
- drafts/linkedin-content-pack-YYYY-MM-DD.md — a short index of that same topic
- drafts/images/ — downloaded source images and customized social graphics when suitable images are available

## Context and post copy

The post uses the article title and at most two complete sentences from its feed description, with a hard length limit. It does not paste the full article or an abruptly truncated excerpt. The copy is still template-based and is not AI-written or expert analysis. Verify the article and edit the wording before posting.

## Article image treatment

When an article image is available, the script uses Pillow to create a square editorial social graphic with:

- The article's actual image as the background
- The topic/niche label
- A readable headline and available summary context
- A randomized visual panel treatment

If multiple relevant article images are found, the workflow can create up to three coordinated graphics for the **same article/topic**. If no image is available, it produces a text-first draft and does not invent an image.

These graphics are image layouts made from source imagery, not AI-generated illustrations. Check publisher image rights, licensing, attribution, and suitability before reuse. Image downloads do not grant permission to repost.

## Sources

Free public RSS/Atom sources include Hacker News, Google News technology search, GitHub Blog/Changelog, DEV Community topic feeds, Stack Overflow Blog, CSS-Tricks, Smashing Magazine, Codrops, and UX Collective. Feed availability and article quality vary.

## Schedule and testing

- Scheduled daily at **09:00 Asia/Kolkata** (03:30 UTC)
- Can also be started manually from **Actions → Generate LinkedIn Draft → Run workflow**
- GitHub may delay scheduled workflows during high load

Download the linkedin-post-draft artifact from a completed run, or inspect the committed drafts files.

## Limitations

- No AI model is used; this keeps the automation free and avoids external API keys.
- RSS feeds do not reliably provide popularity data. Hacker News engagement may be present, but the selection is not a real-time trend-ranking system.
- Article summaries may be incomplete or publisher-formatted. Review the source before posting.
- The image-card design may crop source images; inspect the output and check rights.
- LinkedIn publishing is not enabled. Image publishing later requires uploading media to LinkedIn first and obtaining appropriate API permission.

## Customize

Edit FEEDS, NICHE_LABELS, HASHTAGS, and MAX_ARTICLE_AGE_HOURS in src/generate_draft.py.

## License

MIT
