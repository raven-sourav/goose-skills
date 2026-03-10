#!/usr/bin/env python3
"""
Download Meta Ad Library creatives with structured taxonomy for analysis.

Pipeline:
  1. Search ads via Meta Graph API (or load from previously saved JSON)
  2. Fetch each ad's snapshot page to extract image/video URLs
  3. Download creatives into a structured folder taxonomy
  4. Generate a manifest.json with metadata for each ad
  5. Generate an analysis_brief.md for image analysis

Taxonomy:
  output_dir/
  ├── manifest.json                     <- master index of all ads
  ├── analysis_brief.md                 <- ready-to-use analysis prompt
  ├── {company_slug}/
  │   ├── {YYYY-MM-DD}_{platform}_{ad_id}/
  │   │   ├── creative_1.jpg            <- primary creative image
  │   │   ├── creative_2.jpg            <- additional images (carousel)
  │   │   ├── video_thumb.jpg           <- video thumbnail if applicable
  │   │   └── metadata.json             <- ad copy, spend, impressions, etc.

Usage:
  # Search and download in one step
  python3 download_ad_creatives.py --search "HubSpot" --country US --max-ads 20

  # From previously saved JSON
  python3 download_ad_creatives.py --from-json hubspot_ads.json

  # Custom output directory
  python3 download_ad_creatives.py --search "Nike" --output-dir ./competitor_creatives

  # Skip image download (metadata only)
  python3 download_ad_creatives.py --search "Shopify" --metadata-only
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

# Import the search function from the direct API script
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from search_meta_ads_direct import get_access_token, search_ads, normalize_ad


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

DEFAULT_OUTPUT_DIR = Path("./ad_creatives")


def slugify(text):
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "_", text)
    text = re.sub(r"-+", "-", text)
    return text[:50]


def extract_images_from_snapshot(snapshot_url, access_token=None):
    """Fetch an ad snapshot page and extract image/video URLs.

    The snapshot URL renders the ad as an HTML page.
    We parse it to find embedded image and video sources.
    """
    images = []
    videos = []

    if not snapshot_url:
        return images, videos

    try:
        # The snapshot URL may need the access token appended
        url = snapshot_url
        if access_token and "access_token" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}access_token={access_token}"

        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return images, videos

        html = resp.text

        # Extract image URLs from various patterns
        # Pattern 1: Standard img src tags
        img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        for img_url in img_matches:
            if _is_valid_creative_url(img_url):
                images.append(img_url)

        # Pattern 2: CSS background-image URLs
        bg_matches = re.findall(r'background-image:\s*url\(["\']?([^"\')\s]+)["\']?\)', html)
        for bg_url in bg_matches:
            if _is_valid_creative_url(bg_url):
                images.append(bg_url)

        # Pattern 3: og:image meta tags
        og_matches = re.findall(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        og_matches += re.findall(r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html)
        for og_url in og_matches:
            if _is_valid_creative_url(og_url):
                images.append(og_url)

        # Pattern 4: Video source URLs
        vid_matches = re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html)
        vid_matches += re.findall(r'<video[^>]+src=["\']([^"\']+)["\']', html)
        for vid_url in vid_matches:
            videos.append(vid_url)

        # Pattern 5: JSON-embedded image URLs (common in React-rendered pages)
        json_img_matches = re.findall(r'"(?:src|image_url|imageUrl|url)":\s*"(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif)[^"]*)"', html)
        for json_url in json_img_matches:
            if _is_valid_creative_url(json_url):
                images.append(json_url)

        # Deduplicate while preserving order
        images = list(dict.fromkeys(images))
        videos = list(dict.fromkeys(videos))

    except Exception as e:
        print(f"  [WARN] Failed to parse snapshot: {e}", file=sys.stderr)

    return images, videos


def _is_valid_creative_url(url):
    """Filter out tracking pixels, icons, and non-creative images."""
    if not url or not url.startswith("http"):
        return False

    skip_patterns = [
        "pixel", "tracking", "beacon", "analytics",
        "1x1", "spacer", "blank", "transparent",
        "favicon", "icon", "logo",
        "emoji", "sticker",
        "static/images",  # Meta UI assets
        "rsrc.php",  # Facebook resources
    ]

    url_lower = url.lower()
    for pattern in skip_patterns:
        if pattern in url_lower:
            return False

    # Must be a reasonable image size (not a 1x1 pixel)
    # Check for common image extensions
    has_image_ext = any(ext in url_lower for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"])

    # Or from known CDN patterns
    is_cdn = any(cdn in url_lower for cdn in [
        "fbcdn", "cdninstagram", "scontent",
        "external", "media", "creative",
    ])

    return has_image_ext or is_cdn


def download_file(url, filepath):
    """Download a file from URL to local path."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()

        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return True
    except Exception as e:
        print(f"  [WARN] Download failed for {url}: {e}", file=sys.stderr)
        return False


def get_file_extension(url, content_type=None):
    """Determine file extension from URL or content type."""
    # Try URL path
    parsed = urlparse(url)
    path = parsed.path.lower()

    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov"]:
        if ext in path:
            return ext

    # Fallback
    return ".jpg"


def build_ad_folder_name(ad, index):
    """Build a descriptive folder name for an ad."""
    date = (ad.get("start_date") or "unknown")[:10]
    platforms = "_".join(ad.get("platforms") or ["unknown"])[:20]
    page = slugify(ad.get("page_name") or "unknown")[:20]

    # Use a short hash of ad text for uniqueness
    ad_text = ad.get("ad_text") or str(index)
    text_hash = abs(hash(ad_text)) % 100000

    return f"{date}_{platforms}_{page}_{text_hash}"


def process_ads(
    ads,
    output_dir,
    access_token=None,
    metadata_only=False,
    search_query="",
):
    """Process a list of normalized ads: download creatives, build taxonomy."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "search_query": search_query,
        "total_ads": len(ads),
        "ads": [],
    }

    for i, ad in enumerate(ads, 1):
        page_name = ad.get("page_name") or "unknown"
        company_slug = slugify(page_name)
        folder_name = build_ad_folder_name(ad, i)
        ad_dir = output_dir / company_slug / folder_name

        print(f"[{i}/{len(ads)}] {page_name}: {(ad.get('ad_text') or '')[:50]}...", file=sys.stderr)

        # Build metadata
        ad_meta = {
            "index": i,
            "page_name": page_name,
            "page_id": ad.get("page_id", ""),
            "ad_text": ad.get("ad_text", ""),
            "link_title": ad.get("link_title", ""),
            "link_description": ad.get("link_description", ""),
            "link_caption": ad.get("link_caption", ""),
            "platforms": ad.get("platforms", []),
            "start_date": ad.get("start_date", ""),
            "stop_date": ad.get("stop_date", ""),
            "currency": ad.get("currency", ""),
            "spend_lower": ad.get("spend_lower", ""),
            "spend_upper": ad.get("spend_upper", ""),
            "impressions_lower": ad.get("impressions_lower", ""),
            "impressions_upper": ad.get("impressions_upper", ""),
            "demographic_distribution": ad.get("demographic_distribution", []),
            "delivery_by_region": ad.get("delivery_by_region", []),
            "snapshot_url": ad.get("ad_snapshot_url", ""),
            "creatives_downloaded": [],
        }

        if not metadata_only:
            # Extract image/video URLs from snapshot
            snapshot_url = ad.get("ad_snapshot_url", "")
            images, videos = extract_images_from_snapshot(snapshot_url, access_token)

            # Download images
            for j, img_url in enumerate(images[:5], 1):  # Max 5 images per ad
                ext = get_file_extension(img_url)
                filename = f"creative_{j}{ext}"
                filepath = ad_dir / filename

                if download_file(img_url, filepath):
                    ad_meta["creatives_downloaded"].append(filename)
                    print(f"  ✓ {filename}", file=sys.stderr)

            # Download video thumbnails (not full videos — too large)
            for j, vid_url in enumerate(videos[:2], 1):
                ad_meta.setdefault("video_urls", []).append(vid_url)

            # Small delay to be respectful
            time.sleep(1)

        # Save per-ad metadata
        ad_dir.mkdir(parents=True, exist_ok=True)
        (ad_dir / "metadata.json").write_text(json.dumps(ad_meta, indent=2, default=str))

        manifest["ads"].append({
            "folder": str(ad_dir.relative_to(output_dir)),
            "page_name": page_name,
            "ad_text_preview": (ad.get("ad_text") or "")[:100],
            "platforms": ad.get("platforms", []),
            "start_date": ad.get("start_date", ""),
            "spend_range": f"{ad.get('currency', '')} {ad.get('spend_lower', '')}-{ad.get('spend_upper', '')}",
            "creatives_count": len(ad_meta["creatives_downloaded"]),
        })

    # Save master manifest
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"\nManifest saved to {output_dir / 'manifest.json'}", file=sys.stderr)

    # Generate analysis brief
    _generate_analysis_brief(output_dir, manifest)

    return manifest


def _generate_analysis_brief(output_dir, manifest):
    """Generate an analysis_brief.md for running image analysis."""
    ads = manifest["ads"]
    companies = list(set(a["page_name"] for a in ads))

    brief = f"""# Ad Creative Analysis Brief

**Generated:** {manifest['generated_at']}
**Search query:** {manifest['search_query']}
**Total ads:** {manifest['total_ads']}
**Companies:** {', '.join(companies)}

---

## Folder Structure

```
{output_dir.name}/
├── manifest.json
├── analysis_brief.md
"""

    for company in companies:
        company_slug = slugify(company)
        company_ads = [a for a in ads if a["page_name"] == company]
        brief += f"├── {company_slug}/           ({len(company_ads)} ads)\n"
        for ad in company_ads[:3]:
            brief += f"│   ├── {ad['folder'].split('/')[-1]}/\n"
        if len(company_ads) > 3:
            brief += f"│   └── ... ({len(company_ads) - 3} more)\n"

    brief += f"""```

---

## Analysis Dimensions

When reviewing these ad creatives, analyze across these dimensions:

### 1. Visual Patterns
- Color palette and brand consistency
- Image composition (product shots, lifestyle, abstract, UGC)
- Text overlay patterns (amount of text, placement, font style)
- Use of faces/people vs. product vs. illustration
- Visual hierarchy and focal points

### 2. Messaging Patterns
- Hook type (question, stat, pain point, benefit, social proof)
- Value proposition framing
- CTA language and placement
- Emotional tone (urgency, aspiration, fear, curiosity, trust)
- Competitor differentiation claims

### 3. Format & Platform Strategy
- Static image vs. carousel vs. video
- Platform-specific adaptations (Instagram story vs. feed vs. Facebook)
- Ad format choices relative to message type

### 4. Performance Signals
- Long-running ads (likely winners) vs. recently launched (tests)
- Higher spend range = more confidence in creative
- Multiple variants of same message = active testing

### 5. Competitive Gaps
- What visual styles are competitors NOT using?
- What messaging angles are missing?
- What platforms are underserved?
- Where is there creative fatigue (same style for months)?

---

## How to Run Analysis

### Option A: Claude Code image analysis
```bash
# Read individual creatives
# Claude can directly read and analyze images from the folder paths
```

### Option B: Batch comparison
Read the manifest.json, then read all creative images for a single competitor
to identify patterns across their ad portfolio.

### Option C: Cross-competitor comparison
Compare creative styles across companies — find differentiation opportunities
and white space for your own ads.

---

## Ad Index

| # | Company | Platforms | Start Date | Spend | Creatives | Ad Text |
|---|---------|-----------|------------|-------|-----------|---------|
"""

    for ad in ads:
        brief += f"| {ads.index(ad)+1} | {ad['page_name']} | {', '.join(ad['platforms'])} | {ad['start_date'][:10] if ad['start_date'] else 'N/A'} | {ad['spend_range']} | {ad['creatives_count']} | {ad['ad_text_preview'][:50]}... |\n"

    brief += "\n"

    (output_dir / "analysis_brief.md").write_text(brief)
    print(f"Analysis brief saved to {output_dir / 'analysis_brief.md'}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Download Meta Ad Library creatives with structured taxonomy",
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--search", help="Company name or keyword to search")
    source.add_argument("--from-json", help="Load ads from previously saved JSON file")

    parser.add_argument("--country", default="US", help="Country code (default: US)")
    parser.add_argument("--max-ads", type=int, default=25, help="Max ads (default: 25)")
    parser.add_argument("--active-only", action="store_true", default=True)
    parser.add_argument("--all-ads", action="store_true", help="Include inactive ads")
    parser.add_argument("--output-dir", default="./ad_creatives", help="Output directory")
    parser.add_argument("--metadata-only", action="store_true",
                        help="Save metadata only, skip image downloads")
    parser.add_argument("--token", help="Meta API access token")

    args = parser.parse_args()

    if args.from_json:
        # Load from file
        print(f"Loading ads from {args.from_json}...", file=sys.stderr)
        raw = json.loads(Path(args.from_json).read_text())
        if isinstance(raw, list):
            ads = raw
        elif isinstance(raw, dict) and "ads" in raw:
            ads = raw["ads"]
        else:
            ads = [raw]

        # Check if already normalized or raw
        if ads and "ad_text" not in ads[0] and "ad_creative_bodies" in ads[0]:
            ads = [normalize_ad(ad) for ad in ads]

        search_query = args.from_json
        access_token = None
    else:
        # Search via API
        access_token = get_access_token(args.token)
        active_only = not args.all_ads

        print(f"Searching Meta Ad Library for: \"{args.search}\"", file=sys.stderr)
        raw_ads = search_ads(
            access_token=access_token,
            search_terms=args.search,
            country=args.country,
            max_ads=args.max_ads,
            active_only=active_only,
        )
        ads = [normalize_ad(ad) for ad in raw_ads]
        search_query = args.search

        # Save raw JSON for reuse
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_file = output_dir / "raw_api_response.json"
        raw_file.write_text(json.dumps(raw_ads, indent=2, default=str))
        print(f"Raw API response saved to {raw_file}", file=sys.stderr)

    if not ads:
        print("No ads found.", file=sys.stderr)
        sys.exit(1)

    print(f"\nProcessing {len(ads)} ads...\n", file=sys.stderr)

    manifest = process_ads(
        ads=ads,
        output_dir=args.output_dir,
        access_token=access_token,
        metadata_only=args.metadata_only,
        search_query=search_query,
    )

    # Summary
    total_creatives = sum(a["creatives_count"] for a in manifest["ads"])
    companies = set(a["page_name"] for a in manifest["ads"])

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Done! {len(ads)} ads from {len(companies)} advertiser(s)", file=sys.stderr)
    print(f"  {total_creatives} creative images downloaded", file=sys.stderr)
    print(f"  Output: {args.output_dir}/", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
