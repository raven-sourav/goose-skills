#!/usr/bin/env python3
"""
Search Meta Ad Library using the official Graph API (free, no Apify needed).

Setup (one-time, 5 minutes):
  1. Go to https://developers.facebook.com/apps/ and create a new app
  2. Choose "Other" use case, then "Business" type
  3. From your app dashboard, copy the App ID and App Secret
  4. Set env vars: META_APP_ID and META_APP_SECRET
  OR
  5. Generate a User Access Token from Graph API Explorer and set META_ACCESS_TOKEN

Usage:
  python3 search_meta_ads_direct.py --search "HubSpot"
  python3 search_meta_ads_direct.py --search "Nike" --country US --max-ads 20
  python3 search_meta_ads_direct.py --search "CRM software" --output summary
  python3 search_meta_ads_direct.py --search "Shopify" --active-only --output summary
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import requests

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Rate limit: 200 calls/hour = ~1 call per 18 seconds. We use 2s delay to be safe.
RATE_LIMIT_DELAY = 2

# Fields to request from the API
AD_FIELDS = ",".join([
    "ad_creative_bodies",
    "ad_creative_link_captions",
    "ad_creative_link_descriptions",
    "ad_creative_link_titles",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "ad_snapshot_url",
    "bylines",
    "currency",
    "delivery_by_region",
    "demographic_distribution",
    "estimated_audience_size",
    "impressions",
    "languages",
    "page_id",
    "page_name",
    "publisher_platforms",
    "spend",
])


def get_access_token(cli_token=None):
    """Get access token from CLI arg, env var, or generate from app credentials.

    Priority:
      1. --token CLI argument
      2. META_ACCESS_TOKEN env var (user token)
      3. META_APP_ID + META_APP_SECRET env vars (generates app token)
    """
    # Direct token
    token = cli_token or os.environ.get("META_ACCESS_TOKEN")
    if token:
        return token

    # App token from app credentials (safer — not tied to personal account)
    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")

    if app_id and app_secret:
        print("Generating app access token from META_APP_ID + META_APP_SECRET...", file=sys.stderr)
        resp = requests.get(
            f"{GRAPH_API_BASE}/oauth/access_token",
            params={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token")
            if token:
                print("App access token generated.", file=sys.stderr)
                return token

        print(f"Failed to generate app token: {resp.text}", file=sys.stderr)

    print(
        "Error: No access token found.\n\n"
        "Set one of:\n"
        "  1. META_ACCESS_TOKEN (user token from Graph API Explorer)\n"
        "  2. META_APP_ID + META_APP_SECRET (generates app token, safer)\n"
        "  3. --token flag\n\n"
        "Setup guide:\n"
        "  1. Go to https://developers.facebook.com/apps/\n"
        "  2. Create an app (Other → Business)\n"
        "  3. Copy App ID and App Secret from app settings\n"
        "  4. export META_APP_ID=your_app_id\n"
        "  5. export META_APP_SECRET=your_app_secret",
        file=sys.stderr,
    )
    sys.exit(1)


def search_ads(
    access_token,
    search_terms,
    country="ALL",
    max_ads=50,
    active_only=True,
):
    """Search Meta Ad Library via the official Graph API.

    Args:
        access_token: Meta API access token
        search_terms: Company name or keyword to search
        country: 2-letter country code or ALL
        max_ads: Maximum ads to return
        active_only: If True, only return currently active ads

    Returns:
        List of ad dicts
    """
    params = {
        "access_token": access_token,
        "search_terms": search_terms,
        "ad_type": "ALL",
        "ad_reached_countries": f'["{country}"]' if country != "ALL" else '["US"]',
        "fields": AD_FIELDS,
        "limit": min(max_ads, 25),  # API max per page is 25
    }

    if active_only:
        params["ad_active_status"] = "ACTIVE"

    all_ads = []
    page = 1
    url = f"{GRAPH_API_BASE}/ads_archive"

    while len(all_ads) < max_ads:
        print(f"Fetching page {page}... ({len(all_ads)} ads so far)", file=sys.stderr)

        try:
            resp = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"[ERROR] Request failed: {e}", file=sys.stderr)
            break

        if resp.status_code == 429:
            # Rate limited — back off
            retry_after = int(resp.headers.get("Retry-After", 60))
            print(f"Rate limited. Waiting {retry_after}s...", file=sys.stderr)
            time.sleep(retry_after)
            continue

        if resp.status_code != 200:
            error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = error_data.get("error", {}).get("message", resp.text[:200])
            print(f"[ERROR] API returned {resp.status_code}: {error_msg}", file=sys.stderr)
            break

        data = resp.json()
        ads = data.get("data", [])

        if not ads:
            break

        all_ads.extend(ads)

        # Check for next page
        paging = data.get("paging", {})
        next_url = paging.get("next")
        if not next_url or len(all_ads) >= max_ads:
            break

        # Use the next URL directly (it includes cursor params)
        url = next_url
        params = {}  # params are embedded in the next URL
        page += 1

        # Respect rate limits
        time.sleep(RATE_LIMIT_DELAY)

    return all_ads[:max_ads]


def normalize_ad(ad):
    """Normalize a raw Graph API ad into a clean dict."""
    # Extract spend range
    spend = ad.get("spend", {})
    spend_lower = spend.get("lower_bound", "") if isinstance(spend, dict) else ""
    spend_upper = spend.get("upper_bound", "") if isinstance(spend, dict) else ""

    # Extract impression range
    impressions = ad.get("impressions", {})
    imp_lower = impressions.get("lower_bound", "") if isinstance(impressions, dict) else ""
    imp_upper = impressions.get("upper_bound", "") if isinstance(impressions, dict) else ""

    # Extract ad text (may be a list)
    bodies = ad.get("ad_creative_bodies", [])
    ad_text = bodies[0] if bodies else ""

    # Extract link titles
    link_titles = ad.get("ad_creative_link_titles", [])
    link_title = link_titles[0] if link_titles else ""

    # Extract link descriptions
    link_descs = ad.get("ad_creative_link_descriptions", [])
    link_desc = link_descs[0] if link_descs else ""

    # Extract link captions (URLs shown in ad)
    link_captions = ad.get("ad_creative_link_captions", [])
    link_caption = link_captions[0] if link_captions else ""

    return {
        "page_name": ad.get("page_name", ""),
        "page_id": ad.get("page_id", ""),
        "ad_text": ad_text,
        "link_title": link_title,
        "link_description": link_desc,
        "link_caption": link_caption,
        "ad_snapshot_url": ad.get("ad_snapshot_url", ""),
        "start_date": ad.get("ad_delivery_start_time", ""),
        "stop_date": ad.get("ad_delivery_stop_time", ""),
        "platforms": ad.get("publisher_platforms", []),
        "languages": ad.get("languages", []),
        "currency": ad.get("currency", ""),
        "spend_lower": spend_lower,
        "spend_upper": spend_upper,
        "impressions_lower": imp_lower,
        "impressions_upper": imp_upper,
        "estimated_audience_size": ad.get("estimated_audience_size", {}),
        "demographic_distribution": ad.get("demographic_distribution", []),
        "delivery_by_region": ad.get("delivery_by_region", []),
        "bylines": ad.get("bylines", ""),
    }


def format_summary(ads):
    """Format ads as a human-readable summary."""
    lines = [
        f"{'#':<4} {'Page':<22} {'Platforms':<22} {'Start':<12} {'Spend':<15} {'Ad Text'}",
        "-" * 120,
    ]
    for i, ad in enumerate(ads, 1):
        page = (ad.get("page_name") or "Unknown")[:21]
        platforms = ", ".join(ad.get("platforms") or [])[:21]
        start = (ad.get("start_date") or "")[:10]

        spend_lo = ad.get("spend_lower", "")
        spend_hi = ad.get("spend_upper", "")
        currency = ad.get("currency", "")
        spend = f"{currency} {spend_lo}-{spend_hi}" if spend_lo else ""
        spend = spend[:14]

        text = (ad.get("ad_text") or "")[:45].replace("\n", " ")

        lines.append(f"{i:<4} {page:<22} {platforms:<22} {start:<12} {spend:<15} {text}")

    lines.append(f"\nTotal: {len(ads)} ads")
    return "\n".join(lines)


def format_detailed(ads):
    """Format ads with full details for analysis."""
    lines = []
    for i, ad in enumerate(ads, 1):
        lines.append(f"{'='*80}")
        lines.append(f"Ad #{i}: {ad.get('page_name', 'Unknown')}")
        lines.append(f"{'='*80}")
        lines.append(f"  Platforms: {', '.join(ad.get('platforms', []))}")
        lines.append(f"  Running since: {ad.get('start_date', 'N/A')}")
        if ad.get("stop_date"):
            lines.append(f"  Stopped: {ad['stop_date']}")

        spend_lo = ad.get("spend_lower", "")
        spend_hi = ad.get("spend_upper", "")
        if spend_lo:
            lines.append(f"  Spend: {ad.get('currency', '')} {spend_lo} - {spend_hi}")

        imp_lo = ad.get("impressions_lower", "")
        imp_hi = ad.get("impressions_upper", "")
        if imp_lo:
            lines.append(f"  Impressions: {imp_lo} - {imp_hi}")

        lines.append(f"\n  AD TEXT:")
        text = ad.get("ad_text", "")
        if text:
            for line in text.split("\n"):
                lines.append(f"    {line}")
        else:
            lines.append("    (no text)")

        if ad.get("link_title"):
            lines.append(f"\n  LINK TITLE: {ad['link_title']}")
        if ad.get("link_description"):
            lines.append(f"  LINK DESC: {ad['link_description']}")
        if ad.get("link_caption"):
            lines.append(f"  LINK URL: {ad['link_caption']}")
        if ad.get("ad_snapshot_url"):
            lines.append(f"  SNAPSHOT: {ad['ad_snapshot_url']}")

        lines.append("")

    lines.append(f"Total: {len(ads)} ads")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search Meta Ad Library via official Graph API (free, no Apify)",
    )
    parser.add_argument("--search", required=True, help="Company name or keyword to search")
    parser.add_argument("--country", default="US", help="2-letter country code (default: US)")
    parser.add_argument("--max-ads", type=int, default=25, help="Max ads to return (default: 25)")
    parser.add_argument("--active-only", action="store_true", default=True,
                        help="Only active ads (default: true)")
    parser.add_argument("--all-ads", action="store_true", help="Include inactive/historical ads")
    parser.add_argument("--output", choices=["json", "summary", "detailed"], default="summary",
                        help="Output format (default: summary)")
    parser.add_argument("--token", help="Access token (or set META_ACCESS_TOKEN / META_APP_ID+META_APP_SECRET)")

    args = parser.parse_args()

    active_only = not args.all_ads
    token = get_access_token(args.token)

    print(f"Searching Meta Ad Library for: \"{args.search}\"", file=sys.stderr)
    print(f"Country: {args.country} | Active only: {active_only} | Max: {args.max_ads}", file=sys.stderr)

    raw_ads = search_ads(
        access_token=token,
        search_terms=args.search,
        country=args.country,
        max_ads=args.max_ads,
        active_only=active_only,
    )

    print(f"Found {len(raw_ads)} ads.", file=sys.stderr)

    # Normalize
    ads = [normalize_ad(ad) for ad in raw_ads]

    # Output
    if args.output == "json":
        print(json.dumps(ads, indent=2, default=str))
    elif args.output == "detailed":
        print(format_detailed(ads))
    else:
        print(format_summary(ads))


if __name__ == "__main__":
    main()
