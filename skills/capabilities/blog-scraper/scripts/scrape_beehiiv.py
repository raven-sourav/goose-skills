#!/usr/bin/env python3
"""
Scrape Beehiiv newsletter posts via their hidden JSON endpoint.
No API key needed — works with any Beehiiv publication (including custom domains).

Usage:
  python3 scrape_beehiiv.py --url "https://www.growthunhinged.com"
  python3 scrape_beehiiv.py --url "https://www.growthunhinged.com" --days 30 --keywords "AI,pricing"
  python3 scrape_beehiiv.py --url "https://www.growthunhinged.com" --max-posts 10 --output json
  python3 scrape_beehiiv.py --url "https://www.growthunhinged.com" --full-content --output json
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timedelta, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Sec-Fetch-Dest": "empty",
}

PER_PAGE = 30


def fetch_posts(base_url, max_posts=None):
    """Fetch all posts from a Beehiiv publication via /posts endpoint."""
    base_url = base_url.rstrip("/")
    all_posts = []
    page = 0

    while True:
        url = f"{base_url}/posts?page={page}&perPage={PER_PAGE}"
        print(f"Fetching page {page + 1}...", file=sys.stderr)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[ERROR] Failed to fetch {url}: {e}", file=sys.stderr)
            break
        except json.JSONDecodeError:
            print(f"[ERROR] Response is not JSON — is this a Beehiiv site?", file=sys.stderr)
            break

        posts = data.get("posts", [])
        pagination = data.get("pagination", {})

        if not posts:
            break

        # Deduplicate by post ID
        seen_ids = {p["id"] for p in all_posts}
        posts = [p for p in posts if p["id"] not in seen_ids]
        all_posts.extend(posts)
        print(f"  Got {len(posts)} posts (total so far: {len(all_posts)})", file=sys.stderr)

        if max_posts and len(all_posts) >= max_posts:
            all_posts = all_posts[:max_posts]
            break

        total_pages = pagination.get("total_pages", 1)
        page += 1
        if page >= total_pages:
            break

    return all_posts


def fetch_post_content(base_url, slug):
    """Fetch full content of a single post via WebFetch-style HTML scraping."""
    url = f"{base_url}/p/{slug}"
    try:
        resp = requests.get(url, headers={
            "User-Agent": HEADERS["User-Agent"],
        }, timeout=15)
        resp.raise_for_status()

        import re
        match = re.search(
            r'window\.__remixContext\s*=\s*(\{.*?\})\s*;\s*</script>',
            resp.text,
            re.DOTALL,
        )
        if not match:
            return None

        data = json.loads(match.group(1))
        loader = data.get("state", {}).get("loaderData", {})

        # Find the post route loader data
        for key, val in loader.items():
            if "post" in key.lower() or "p/$" in key:
                if isinstance(val, dict):
                    post_data = val.get("post", val)
                    return post_data.get("body", post_data.get("content", None))

    except Exception as e:
        print(f"  [WARN] Could not fetch content for {slug}: {e}", file=sys.stderr)

    return None


def normalize_post(post, base_url):
    """Normalize a raw Beehiiv post into a clean dict."""
    authors = post.get("authors", [])
    author_name = authors[0].get("name", "") if authors else ""
    tags = [t.get("display", "") for t in post.get("content_tags", [])]

    return {
        "title": post.get("web_title", ""),
        "subtitle": post.get("web_subtitle", ""),
        "slug": post.get("slug", ""),
        "url": f"{base_url}/p/{post.get('slug', '')}",
        "date": post.get("created_at", ""),
        "updated_at": post.get("updated_at", ""),
        "author": author_name,
        "tags": tags,
        "image_url": post.get("image_url", ""),
        "reading_time": post.get("estimated_reading_time_display", ""),
        "is_premium": post.get("is_premium", False),
    }


def filter_posts(posts, keywords=None, days=None):
    """Filter posts by date and keywords."""
    filtered = posts

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        date_filtered = []
        for p in filtered:
            date_str = p.get("date", "")
            if not date_str:
                date_filtered.append(p)
                continue
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if dt >= cutoff:
                    date_filtered.append(p)
            except ValueError:
                date_filtered.append(p)
        filtered = date_filtered

    if keywords:
        kw_lower = [k.lower() for k in keywords]
        filtered = [
            p for p in filtered
            if any(
                kw in f"{p.get('title', '')} {p.get('subtitle', '')} {' '.join(p.get('tags', []))}".lower()
                for kw in kw_lower
            )
        ]

    return filtered


def format_summary(posts):
    """Format posts as a readable summary table."""
    lines = [
        f"{'#':<4} {'Date':<12} {'Read':<8} {'Title'}",
        "-" * 100,
    ]
    for i, p in enumerate(posts, 1):
        date = (p.get("date") or "")[:10]
        title = (p.get("title") or "")[:60]
        subtitle = p.get("subtitle") or ""
        reading = p.get("reading_time") or ""
        line = f"{i:<4} {date:<12} {reading:<8} {title}"
        if subtitle:
            line += f"\n{'':>26}{subtitle[:70]}"
        lines.append(line)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Beehiiv newsletter posts (no API key needed)",
    )
    parser.add_argument("--url", required=True, help="Beehiiv publication URL")
    parser.add_argument("--keywords", help="Filter by keywords (comma-separated, OR logic)")
    parser.add_argument("--days", type=int, help="Only include posts from last N days")
    parser.add_argument("--max-posts", type=int, help="Max posts to return")
    parser.add_argument("--full-content", action="store_true", help="Fetch full post body (slower)")
    parser.add_argument("--output", choices=["json", "summary"], default="summary", help="Output format")

    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    # Fetch
    raw_posts = fetch_posts(base_url, max_posts=args.max_posts)
    print(f"Fetched {len(raw_posts)} total posts.", file=sys.stderr)

    # Normalize
    posts = [normalize_post(p, base_url) for p in raw_posts]

    # Filter
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
    posts = filter_posts(posts, keywords=keywords, days=args.days)
    print(f"After filtering: {len(posts)} posts.", file=sys.stderr)

    # Optionally fetch full content
    if args.full_content:
        print("Fetching full content for each post...", file=sys.stderr)
        for i, p in enumerate(posts):
            print(f"  [{i+1}/{len(posts)}] {p['slug']}", file=sys.stderr)
            content = fetch_post_content(base_url, p["slug"])
            if content:
                p["body"] = content

    # Output
    if args.output == "summary":
        print(f"\nResults: {len(posts)} posts\n")
        print(format_summary(posts))
    else:
        print(json.dumps(posts, indent=2))


if __name__ == "__main__":
    main()
