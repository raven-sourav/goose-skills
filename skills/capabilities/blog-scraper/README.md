# Blog / Newsletter Scraper

Scrape newsletter posts from **Substack** and **Beehiiv** publications using their public JSON API endpoints. No API keys, no Apify, completely free.

## Supported Platforms

| Platform | Endpoint Used | Custom Domains |
|----------|--------------|----------------|
| **Substack** | `/api/v1/archive` (public JSON) | ✅ Auto-detected |
| **Beehiiv** | `/posts` (hidden JSON) | ✅ Auto-detected |
| **RSS/Atom** | Standard feed discovery | ✅ (original script) |

## Scripts

### `scrape_substack.py` — Substack Scraper

Scrapes any Substack newsletter via their public JSON API.

```bash
# Basic usage
python3 scripts/scrape_substack.py --url "https://www.lennysnewsletter.com" --days 30

# Filter by keywords
python3 scripts/scrape_substack.py --url "https://newsletter.substack.com" --keywords "AI,pricing" --output json

# Fetch full post HTML content
python3 scripts/scrape_substack.py --url "https://newsletter.substack.com" --full-content --output json
```

**Data returned per post:**
- Title, subtitle, slug, canonical URL
- Author, tags, word count
- Reactions (❤), comment count
- Full HTML body (with `--full-content`)
- Paid vs. free flag

### `scrape_beehiiv.py` — Beehiiv Scraper

Scrapes any Beehiiv newsletter via their hidden `/posts` JSON endpoint.

```bash
# Basic usage
python3 scripts/scrape_beehiiv.py --url "https://www.growthunhinged.com" --days 30

# Filter by keywords
python3 scripts/scrape_beehiiv.py --url "https://www.growthunhinged.com" --keywords "pricing" --output json
```

**Data returned per post:**
- Title, subtitle, slug, URL
- Author, tags, reading time
- Image URL, premium flag

### `scrape_blogs.py` — RSS Feed Scraper (Original)

Scrapes blog posts via RSS/Atom feeds with optional Apify fallback.

```bash
python3 scripts/scrape_blogs.py --urls "https://blog.example.com" --days 30
```

## CLI Flags (Substack & Beehiiv scripts)

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | *required* | Newsletter URL |
| `--keywords` | none | Filter by keywords (comma-separated, OR logic) |
| `--days` | all | Only include posts from last N days |
| `--max-posts` | all | Max posts to return |
| `--full-content` | false | Fetch full post body (slower) |
| `--output` | summary | `summary` (table) or `json` |

## How It Works

Both scripts exploit the same pattern discovered in Substack/Beehiiv's architecture: **these platforms expose structured JSON endpoints for every publication**, even on custom domains. No web scraping, no headless browsers — just direct API calls that return clean data.

- **Substack**: Every publication has `/api/v1/archive?sort=new&limit=12&offset=0` returning post metadata as JSON array
- **Beehiiv**: Every publication has `/posts?page=0&perPage=30` returning `{posts: [...], pagination: {...}}`

## Dependencies

```bash
pip install requests
```

No API keys. No Apify. No Selenium. Just `requests`.

## Tested With

| Newsletter | Platform | Posts Found |
|-----------|----------|-------------|
| [Growth Unhinged](https://www.growthunhinged.com) (Kyle Poyar) | Beehiiv | 207 |
| [Lenny's Newsletter](https://www.lennysnewsletter.com) | Substack | 457 |
| [Marketing for Geeks](https://www.marketingforgeeks.com) | Substack | 15 |
