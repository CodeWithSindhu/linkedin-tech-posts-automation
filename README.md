# LinkedIn Tech Posts Automation

A free, GitHub Actions-based daily content-pack generator for technology news, programming tutorials/tips, and design/UI inspiration.

> **Draft-only mode.** It does not publish to LinkedIn and does not need LinkedIn credentials. Your PC can be switched off because GitHub-hosted runners execute the workflow.

## What it creates each day

The generator creates up to three separate drafts:

1. **Trending tech/news** — recent technology and developer-tool stories, with Hacker News engagement used as one signal when available.
2. **Programming tip/tutorial** — recent posts from tagged developer feeds (web development, JavaScript, programming, tutorials, productivity) and programming publications.
3. **Design/UI inspiration** — articles from design and frontend publications such as Smashing Magazine, Codrops, and UX Collective.

Each draft has its own source link and may include up to three downloaded article images. A daily content-pack index links to all generated drafts.

## How it works

1. GitHub Actions runs daily on a GitHub-hosted runner.
2. Python reads public RSS/Atom feeds and filters out articles older than the configured age.
3. It ranks candidates by freshness, category relevance, topic keywords, and Hacker News points/comments where available.
4. It creates Markdown drafts and downloads usable article images from RSS media or article metadata/content.
5. The draft pack, Markdown files, and downloaded images are uploaded as the workflow artifact and committed to `drafts/`.

The workflow can also be started manually from **Actions → Generate LinkedIn Draft → Run workflow**.

## Sources

The configured feeds include:

- Hacker News and Google News technology search
- GitHub Blog and GitHub Changelog
- DEV Community tags: webdev, JavaScript, programming, tutorial, productivity
- Stack Overflow Blog and CSS-Tricks
- Smashing Magazine, Codrops, and UX Collective

RSS feeds are free to read, but their availability, content quality, image metadata, and posting frequency vary. The script selects recent candidates; it cannot guarantee every selected item is genuinely viral or universally trending.

## Images

The generator attempts to collect up to three article images from RSS media fields, social preview metadata, and article-body image tags. Supported downloads are JPEG, PNG, or WebP up to 4 MB each.

Images are included in the artifact under `drafts/images/` and previewed in each Markdown draft. Image extraction is best-effort: some publishers block automated requests or provide no suitable image.

**Check usage rights, attribution, and relevance before publishing.** Downloading an image does not grant permission to reuse it. Markdown image previews are not LinkedIn media uploads; publishing with images will require uploading the image files through LinkedIn's media API.

## Run it

1. Open the repository's **Actions** tab and enable workflows if GitHub asks.
2. Open **Generate LinkedIn Draft**.
3. Click **Run workflow**.
4. Download the `linkedin-post-draft` artifact from the completed run, or inspect the committed files in `drafts/`.

The schedule is **09:00 Asia/Kolkata** (03:30 UTC). GitHub may delay scheduled workflows during high load.

## Limitations

- No AI model is used; this keeps the workflow free and avoids external API keys.
- The post copy is a structured source-based draft, not original expert analysis or fact-checking.
- A tutorial feed can provide a tutorial topic, but the script does not invent step-by-step code tips. Add your own practical experience or rewrite the draft before posting.
- Only one article is selected per content category each day; review the source before publishing.

## Customization

Edit `FEEDS`, `MAX_ARTICLE_AGE_HOURS`, and `HASHTAGS` in `src/generate_draft.py`.

## LinkedIn publishing (future phase)

Automatic publishing requires a LinkedIn Developer application, appropriate product/permission approval, and OAuth authorization. Credentials must be stored in GitHub Actions Secrets, never in source code. For image posts, each image must be uploaded to LinkedIn as media before creating the post.

## License

MIT
