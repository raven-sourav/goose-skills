# Meta Ad Library Scraper

Scrape competitor ads from Meta's Ad Library (Facebook, Instagram, Messenger, Threads, WhatsApp). Two approaches: official Graph API (free, recommended) or Apify (paid fallback).

## Scripts

### `search_meta_ads_direct.py` — Official Graph API (Recommended)

Uses Meta's official Ad Library API. Free, no third-party dependencies, safe for production use.

```bash
# Search by company name
python3 scripts/search_meta_ads_direct.py --search "HubSpot" --country US

# Detailed view with full ad text
python3 scripts/search_meta_ads_direct.py --search "Shopify" --output detailed

# Include historical (inactive) ads
python3 scripts/search_meta_ads_direct.py --search "Nike" --all-ads --max-ads 50

# JSON for downstream processing
python3 scripts/search_meta_ads_direct.py --search "CRM software" --output json
```

**Setup (one-time, 5 minutes):**

1. Go to https://developers.facebook.com/apps/
2. Create app → "Other" → "Business"
3. Copy App ID and App Secret from app settings
4. Set environment variables:

```bash
export META_APP_ID="your_app_id"
export META_APP_SECRET="your_app_secret"
```

Uses **App Token** (not personal token) — your personal Facebook account is not involved in API calls.

### `download_ad_creatives.py` — Creative Download + Analysis Pipeline

Downloads ad creative images with a structured folder taxonomy for visual analysis.

```bash
# Search + download in one step
python3 scripts/download_ad_creatives.py --search "HubSpot" --country US --max-ads 20

# From previously saved JSON
python3 scripts/download_ad_creatives.py --from-json raw_api_response.json

# Metadata only (skip image downloads)
python3 scripts/download_ad_creatives.py --search "Shopify" --metadata-only
```

**Output taxonomy:**

```
ad_creatives/
├── manifest.json                              ← master index of all ads
├── analysis_brief.md                          ← structured analysis prompt
├── raw_api_response.json                      ← raw API data for reuse
├── hubspot/
│   ├── 2026-02-15_facebook_instagram_hubspot_83721/
│   │   ├── creative_1.jpg                     ← primary ad image
│   │   ├── creative_2.jpg                     ← carousel slide / variant
│   │   └── metadata.json                      ← copy, spend, impressions, demographics
│   └── 2026-01-20_facebook_hubspot_44102/
│       ├── creative_1.png
│       └── metadata.json
```

**Auto-generated files:**

| File | Purpose |
|------|---------|
| `manifest.json` | Master index with all ads, folder paths, spend ranges, creative counts |
| `analysis_brief.md` | Analysis prompt covering 5 dimensions: visual patterns, messaging, format strategy, performance signals, competitive gaps |
| `metadata.json` (per ad) | Full ad copy, link titles, spend, impressions, demographics, regions |

### `search_meta_ads.py` — Apify Fallback

Uses Apify's `facebook-ads-scraper` actor. Costs ~$5/1K ads. Use only if the official API doesn't work for your use case.

```bash
python3 scripts/search_meta_ads.py --company "Nike" --output summary
```

Requires `APIFY_API_TOKEN` env var.

## Data Returned Per Ad

| Category | Fields |
|----------|--------|
| **Creative & Copy** | ad text, link title, link description, display URL, snapshot URL |
| **Spend** | lower/upper spend range, currency |
| **Reach** | lower/upper impression range, estimated audience size |
| **Distribution** | platforms, demographic breakdown, regional delivery, languages |
| **Timing** | start date, stop date (null if active) |
| **Advertiser** | page name, page ID, "paid for by" byline |

## CLI Reference — `search_meta_ads_direct.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--search` | *required* | Company name or keyword |
| `--country` | US | 2-letter country code |
| `--max-ads` | 25 | Max ads to return |
| `--active-only` | true | Only active ads |
| `--all-ads` | false | Include inactive/historical |
| `--output` | summary | `summary`, `detailed`, or `json` |
| `--token` | env var | Access token override |

## CLI Reference — `download_ad_creatives.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--search` | *required** | Company name or keyword |
| `--from-json` | *required** | Load from previously saved JSON |
| `--country` | US | 2-letter country code |
| `--max-ads` | 25 | Max ads to return |
| `--output-dir` | ./ad_creatives | Output directory |
| `--metadata-only` | false | Skip image downloads |
| `--token` | env var | Access token override |

*Either `--search` or `--from-json` is required.

## Safety & Rate Limits

- **App Token** authentication (decoupled from personal Facebook accounts)
- 2-second delay between API pages (well within 200 calls/hour limit)
- Automatic backoff on HTTP 429 (rate limit) responses
- No scraping or browser automation — pure official API calls
- Meta provides this API for public ad transparency (EU Digital Services Act)

## Dependencies

```bash
pip install requests
```

## Detailed Brief

See [`meta-ad-library-scraper-brief.md`](../../../meta-ad-library-scraper-brief.md) for a comprehensive internal brief including setup guide, data model, risk assessment, and competitive analysis playbook — ready to share with your team.
