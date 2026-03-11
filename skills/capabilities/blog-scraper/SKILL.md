---
name: blog-scraper
description: >
  Scrape blog posts from Substack, Beehiiv, and RSS feeds. No API key needed.
  Includes dedicated Substack and Beehiiv scrapers using their native JSON APIs,
  plus a generic RSS/Atom scraper with optional Apify fallback for JS-heavy sites.
---

# Blog Scraper

Scrape blog posts from Substack, Beehiiv, and generic RSS/Atom feeds. No API key needed.

Only dependency: `pip install requests`.

---

## Substack Scraper

Scrape any Substack publication (subdomain or custom domain) via the public `/api/v1/archive` JSON endpoint.

```bash
# Summary table of recent posts
python3 skills/blog-scraper/scripts/scrape_substack.py \
  --url "https://newsletter.substack.com" --days 30 --output summary

# JSON with keyword filter
python3 skills/blog-scraper/scripts/scrape_substack.py \
  --url "https://www.lennysnewsletter.com" --keywords "AI" --output json

# Full post content (HTML body)
python3 skills/blog-scraper/scripts/scrape_substack.py \
  --url "https://newsletter.substack.com" --full-content --output json
```

**How it works:**
- Resolves custom domains to Substack base URLs automatically
- Paginates through `/api/v1/archive` (12 posts per page)
- `--full-content` fetches each post via `/api/v1/posts/{slug}` for full HTML body
- Returns: title, subtitle, slug, URL, date, author, tags, word count, reading time, reactions, comments, paid status

## Beehiiv Scraper

Scrape any Beehiiv publication (including custom domains) via the hidden `/posts` JSON endpoint.

```bash
# Summary table
python3 skills/blog-scraper/scripts/scrape_beehiiv.py \
  --url "https://www.growthunhinged.com" --days 30 --output summary

# JSON with keyword filter
python3 skills/blog-scraper/scripts/scrape_beehiiv.py \
  --url "https://www.growthunhinged.com" --keywords "pricing" --output json

# Full post content
python3 skills/blog-scraper/scripts/scrape_beehiiv.py \
  --url "https://www.growthunhinged.com" --full-content --output json
```

**How it works:**
- Paginates through `/posts?page=N&perPage=30` with deduplication
- `--full-content` scrapes each post page and extracts body from Remix context data
- Returns: title, subtitle, slug, URL, date, author, tags, reading time, premium status

## Substack / Beehiiv CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | *required* | Newsletter URL |
| `--keywords` | none | Filter by keywords (comma-separated, OR logic) |
| `--days` | all | Only include posts from last N days |
| `--max-posts` | all | Max posts to return |
| `--full-content` | false | Fetch full post body (slower) |
| `--output` | summary | `summary` (table) or `json` |

---

## Generic RSS/Atom Scraper

Scrape any blog via RSS/Atom feed discovery, with optional Apify fallback for JS-heavy sites.

```bash
# Scrape a blog's RSS feed
python3 skills/blog-scraper/scripts/scrape_blogs.py \
  --urls "https://growthx.ai/blog" --days 30

# Multiple blogs with keyword filter
python3 skills/blog-scraper/scripts/scrape_blogs.py \
  --urls "https://blog1.com,https://blog2.com" --keywords "AI,marketing" --output summary

# Force Apify for JS-heavy sites
python3 skills/blog-scraper/scripts/scrape_blogs.py \
  --urls "https://example.com" --mode apify
```

**How it works:**
1. Discovers RSS/Atom feeds via `<link rel="alternate">` tags and common paths (`/feed`, `/rss`, `/atom.xml`, etc.)
2. Parses feeds (RSS 2.0 and Atom)
3. Falls back to Apify `jupri/rss-xml-scraper` if RSS fails (when token available)

### RSS CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--urls` | *required* | Blog URL(s), comma-separated |
| `--keywords` | none | Keywords to filter (comma-separated, OR logic) |
| `--days` | 30 | Only include posts from last N days |
| `--max-posts` | 50 | Max posts to return |
| `--mode` | auto | `auto` (RSS + fallback), `rss` (RSS only), `apify` (Apify only) |
| `--output` | json | Output format: `json` or `summary` |
| `--token` | env var | Apify token (only needed for Apify mode/fallback) |
| `--timeout` | 300 | Max seconds for Apify run |

## Cost

All scrapers are **free** — no API keys or tokens needed. Apify fallback (RSS scraper only) uses minimal credits.
