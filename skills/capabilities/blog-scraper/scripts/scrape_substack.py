#!/usr/bin/env python3
"""
Scrape Substack newsletter posts via their public JSON API.
No API key needed — works with any Substack publication (including custom domains).

Usage:
  python3 scrape_substack.py --url "https://newsletter.substack.com"
  python3 scrape_substack.py --url "https://newsletter.substack.com" --days 30 --keywords "AI,startup"
  python3 scrape_substack.py --url "https://custom-domain.com" --max-posts 10 --output json
  python3 scrape_substack.py --url "https://newsletter.substack.com" --full-content --output json
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timedelta, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

PAGE_SIZE = 12


def resolve_substack_url(url):
    """Resolve a custom domain to its Substack base URL, or return as-is if already Substack."""
    url = url.rstrip("/")

    # Test if the archive API works directly on this URL
    test = f"{url}/api/v1/archive?sort=new&limit=1&offset=0"
    try:
        resp = requests.get(test, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return url
    except Exception:
        pass

    # If custom domain, try to find the underlying Substack subdomain
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if "substack.com" in resp.url:
            resolved = resp.url.rstrip("/").split("/p/")[0].split("/archive")[0]
            print(f"Resolved custom domain to: {resolved}", file=sys.stderr)
            return resolved
    except Exception:
        pass

    return url


def fetch_posts(base_url, max_posts=None):
    """Fetch all posts from a Substack publication via /api/v1/archive."""
    all_posts = []
    offset = 0

    while True:
        url = f"{base_url}/api/v1/archive?sort=new&limit={PAGE_SIZE}&offset={offset}"
        print(f"Fetching offset {offset}...", file=sys.stderr)

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            posts = resp.json()
        except requests.RequestException as e:
            print(f"[ERROR] Failed to fetch {url}: {e}", file=sys.stderr)
            break
        except json.JSONDecodeError:
            print(f"[ERROR] Response is not JSON — is this a Substack site?", file=sys.stderr)
            break

        if not isinstance(posts, list) or len(posts) == 0:
            break

        all_posts.extend(posts)
        print(f"  Got {len(posts)} posts (total so far: {len(all_posts)})", file=sys.stderr)

        if max_posts and len(all_posts) >= max_posts:
            all_posts = all_posts[:max_posts]
            break

        if len(posts) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return all_posts


def fetch_post_content(base_url, slug):
    """Fetch full content of a single post via /api/v1/posts/{slug}."""
    url = f"{base_url}/api/v1/posts/{slug}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("body_html") or data.get("body") or data.get("truncated_body_text")
    except Exception as e:
        print(f"  [WARN] Could not fetch content for {slug}: {e}", file=sys.stderr)
    return None


def normalize_post(post, base_url):
    """Normalize a raw Substack post into a clean dict."""
    post_date = post.get("post_date") or post.get("published_at") or ""
    slug = post.get("slug", "")
    canonical = post.get("canonical_url") or f"{base_url}/p/{slug}"

    return {
        "title": post.get("title") or "",
        "subtitle": post.get("subtitle") or "",
        "slug": slug,
        "url": canonical,
        "date": post_date,
        "author": post.get("publishedBylines", [{}])[0].get("name", "") if post.get("publishedBylines") else "",
        "tags": [t.get("name", "") for t in post.get("postTags", [])],
        "image_url": post.get("cover_image") or post.get("social_image") or "",
        "word_count": post.get("wordcount") or 0,
        "reading_time": f"{(post.get('wordcount') or 0) // 250} min" if post.get("wordcount") else "",
        "reactions": post.get("reactions", {}).get("❤", 0) if isinstance(post.get("reactions"), dict) else 0,
        "comment_count": post.get("comment_count") or 0,
        "is_paid": post.get("audience") == "only_paid",
        "description": post.get("description") or post.get("truncated_body_text") or "",
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
                kw in f"{p.get('title', '')} {p.get('subtitle', '')} {p.get('description', '')} {' '.join(p.get('tags', []))}".lower()
                for kw in kw_lower
            )
        ]

    return filtered


def format_summary(posts):
    """Format posts as a readable summary table."""
    lines = [
        f"{'#':<4} {'Date':<12} {'Words':<7} {'Title'}",
        "-" * 100,
    ]
    for i, p in enumerate(posts, 1):
        date = (p.get("date") or "")[:10]
        title = (p.get("title") or "")[:60]
        subtitle = p.get("subtitle") or ""
        words = p.get("word_count") or ""
        reactions = p.get("reactions") or 0
        comments = p.get("comment_count") or 0
        line = f"{i:<4} {date:<12} {str(words):<7} {title}"
        if subtitle:
            line += f"\n{'':>25}{subtitle[:72]}"
        if reactions or comments:
            line += f"\n{'':>25}❤ {reactions}  💬 {comments}"
        lines.append(line)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Substack newsletter posts (no API key needed)",
    )
    parser.add_argument("--url", required=True, help="Substack publication URL (subdomain or custom domain)")
    parser.add_argument("--keywords", help="Filter by keywords (comma-separated, OR logic)")
    parser.add_argument("--days", type=int, help="Only include posts from last N days")
    parser.add_argument("--max-posts", type=int, help="Max posts to return")
    parser.add_argument("--full-content", action="store_true", help="Fetch full post HTML body (slower)")
    parser.add_argument("--output", choices=["json", "summary"], default="summary", help="Output format")

    args = parser.parse_args()

    # Resolve URL
    print(f"Resolving URL: {args.url}", file=sys.stderr)
    base_url = resolve_substack_url(args.url)
    print(f"Using base URL: {base_url}", file=sys.stderr)

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
                p["body_html"] = content

    # Output
    if args.output == "summary":
        print(f"\nResults: {len(posts)} posts\n")
        print(format_summary(posts))
    else:
        print(json.dumps(posts, indent=2))


if __name__ == "__main__":
    main()
