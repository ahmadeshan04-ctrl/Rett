"""
Facebook scraper for Rett Syndrome community pages.
Uses Playwright with session cookies for authentication.
Collects posts, comments, reactions from public pages/posts.
"""

import asyncio
import json
import csv
import hashlib
import random
import os
import sys
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import async_playwright


# Seed search queries
SEARCH_QUERIES = [
    "Rett syndrome journey",
    "MECP2 gene therapy",
    "Neurogene Rett",
    "Taysha Rett",
    "NGN-401",
    "TSHA-102",
    "RTT gene therapy",
    "Rett syndrome clinical trial",
    "Rett syndrome",
]

OUTPUT_DIR = Path(__file__).parent / "output"
COOKIES_FILE = Path(__file__).parent / "cookies.json"
FAILED_URLS_FILE = OUTPUT_DIR / "failed_urls.txt"


def anonymize_name(real_name: str, mapping: dict) -> str:
    """Map a real display name to an anonymized Parent_NNN identifier."""
    if real_name not in mapping:
        mapping[real_name] = f"Parent_{len(mapping) + 1:03d}"
    return mapping[real_name]


def comment_hash(text: str, author_anon: str, date: str) -> str:
    """Generate dedup hash for a comment."""
    raw = f"{text.strip()}|{author_anon}|{date}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def random_delay(min_s=2.0, max_s=5.0):
    """Randomized delay between navigations to respect rate limits."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def load_cookies(context):
    """Load Facebook session cookies from JSON export file."""
    if not COOKIES_FILE.exists():
        print(f"ERROR: Cookie file not found at {COOKIES_FILE}")
        print("Please export your Facebook cookies using a browser extension")
        print("(e.g., EditThisCookie or Cookie-Editor) and save as cookies.json")
        sys.exit(1)

    with open(COOKIES_FILE, "r") as f:
        cookies_raw = json.load(f)

    # Normalize cookie format for Playwright
    cookies = []
    for c in cookies_raw:
        cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ".facebook.com"),
            "path": c.get("path", "/"),
        }
        # Playwright requires url or both domain+path
        if not cookie["domain"].startswith("."):
            cookie["domain"] = "." + cookie["domain"]
        cookies.append(cookie)

    await context.add_cookies(cookies)
    print(f"Loaded {len(cookies)} cookies")


async def check_login_wall(page) -> bool:
    """Check if the page hit a login wall."""
    url = page.url
    if "login" in url.lower() or "checkpoint" in url.lower():
        return True
    # Check for login modal overlay
    login_modal = await page.query_selector('[data-testid="login_form"]')
    if login_modal:
        return True
    return False


async def click_see_more(page):
    """Click all 'See More' buttons to expand truncated text."""
    see_more_buttons = await page.query_selector_all(
        '[role="button"]:has-text("See more"), '
        '[role="button"]:has-text("See More")'
    )
    for btn in see_more_buttons[:10]:  # Limit to avoid infinite loops
        try:
            await btn.click()
            await asyncio.sleep(0.5)
        except Exception:
            pass


async def expand_comments(page, max_expansions=20):
    """Click 'View more comments' / 'View previous comments' to load all."""
    for _ in range(max_expansions):
        more_btn = await page.query_selector(
            '[role="button"]:has-text("View more comments"), '
            '[role="button"]:has-text("View previous comments"), '
            '[role="button"]:has-text("View more replies")'
        )
        if not more_btn:
            break
        try:
            await more_btn.click()
            await asyncio.sleep(1.5)
        except Exception:
            break


async def scrape_post_page(page, url: str, name_map: dict) -> dict | None:
    """Scrape a single post page for text, comments, reactions."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        if await check_login_wall(page):
            return None

        # Expand content
        await click_see_more(page)
        await expand_comments(page)

        # Extract post text - try multiple selectors
        post_text = ""
        for selector in [
            '[data-ad-comet-preview="message"]',
            '[data-ad-preview="message"]',
            'div[dir="auto"][style]',
        ]:
            el = await page.query_selector(selector)
            if el:
                post_text = (await el.inner_text()).strip()
                if post_text:
                    break

        if not post_text:
            # Fallback: get the main content area text
            main = await page.query_selector('[role="main"]')
            if main:
                post_text = (await main.inner_text()).strip()[:2000]

        # Extract date
        post_date = ""
        time_els = await page.query_selector_all("abbr, span[id*='jsc'] a[href*='posts']")
        for tel in time_els[:5]:
            aria = await tel.get_attribute("aria-label")
            title = await tel.get_attribute("title")
            date_text = aria or title or ""
            if date_text and any(
                c.isdigit() for c in date_text
            ):
                post_date = date_text
                break
        if not post_date:
            post_date = datetime.now().strftime("%Y-%m-%d")

        # Extract reaction count
        reactions = 0
        reaction_els = await page.query_selector_all(
            '[aria-label*="reaction"], [aria-label*="like"], '
            'span[role="toolbar"] span'
        )
        for rel in reaction_els[:5]:
            label = await rel.get_attribute("aria-label") or ""
            nums = re.findall(r"[\d,]+", label)
            if nums:
                reactions = max(reactions, int(nums[0].replace(",", "")))

        # Extract comments
        comments = []
        seen_hashes = set()
        comment_elements = await page.query_selector_all(
            'div[aria-label*="Comment"], '
            'div[role="article"]'
        )

        for cel in comment_elements:
            try:
                # Author name
                author_el = await cel.query_selector("a[role='link'] span, a > strong")
                if not author_el:
                    continue
                real_name = (await author_el.inner_text()).strip()
                if not real_name:
                    continue
                author_anon = anonymize_name(real_name, name_map)

                # Comment text
                text_el = await cel.query_selector(
                    'div[dir="auto"], span[dir="auto"]'
                )
                if not text_el:
                    continue
                comment_text = (await text_el.inner_text()).strip()
                if not comment_text or len(comment_text) < 3:
                    continue

                # Comment date
                comment_date = ""
                time_el = await cel.query_selector("abbr, a[href*='comment_id']")
                if time_el:
                    comment_date = (
                        await time_el.get_attribute("aria-label")
                        or await time_el.get_attribute("title")
                        or ""
                    )
                if not comment_date:
                    comment_date = post_date

                # Comment likes
                comment_likes = 0
                like_el = await cel.query_selector(
                    '[aria-label*="reaction"], [aria-label*="like"]'
                )
                if like_el:
                    like_label = await like_el.get_attribute("aria-label") or ""
                    like_nums = re.findall(r"[\d,]+", like_label)
                    if like_nums:
                        comment_likes = int(like_nums[0].replace(",", ""))

                # Dedup
                h = comment_hash(comment_text, author_anon, comment_date)
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                comments.append(
                    {
                        "id": h,
                        "author_anon": author_anon,
                        "text": comment_text,
                        "date": comment_date,
                        "likes": comment_likes,
                    }
                )
            except Exception:
                continue

        return {
            "source_url": url,
            "post_text": post_text,
            "date": post_date,
            "reactions": reactions,
            "comments": comments,
        }

    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return None


async def discover_urls(page) -> list[str]:
    """Use Facebook search to discover relevant post/page URLs."""
    discovered = set()

    for query in SEARCH_QUERIES:
        print(f"  Searching: '{query}'")
        search_url = f"https://www.facebook.com/search/posts?q={quote_plus(query)}"

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            if await check_login_wall(page):
                print(f"    Login wall on search for '{query}' — logging and skipping")
                with open(FAILED_URLS_FILE, "a") as f:
                    f.write(f"{search_url} — login wall on search\n")
                await random_delay()
                continue

            # Scroll to load more results
            for _ in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

            # Collect all post links
            links = await page.query_selector_all('a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]')
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    # Normalize URL
                    if href.startswith("/"):
                        href = "https://www.facebook.com" + href
                    # Strip tracking params
                    href = href.split("?")[0] if "story_fbid" not in href else href
                    discovered.add(href)

            # Also look for page links
            page_links = await page.query_selector_all(
                'a[href*="facebook.com/"][role="link"]'
            )
            for pl in page_links:
                href = await pl.get_attribute("href") or ""
                if "/pages/" in href or any(
                    kw in href.lower()
                    for kw in ["rett", "mecp2", "neurogene", "taysha"]
                ):
                    discovered.add(href.split("?")[0])

            print(f"    Found {len(links)} post links")

        except Exception as e:
            print(f"    Error searching '{query}': {e}")
            with open(FAILED_URLS_FILE, "a") as f:
                f.write(f"{search_url} — error: {e}\n")

        await random_delay()

    print(f"\nTotal unique URLs discovered: {len(discovered)}")
    return list(discovered)


async def run_scraper():
    """Main scraper entry point."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clear failed URLs file
    if FAILED_URLS_FILE.exists():
        FAILED_URLS_FILE.unlink()

    name_map = {}  # real_name -> anonymized
    all_posts = []
    pages_scraped = 0
    total_comments = 0
    errors = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        await load_cookies(context)
        page = await context.new_page()

        # Step 1: Discovery
        print("=" * 60)
        print("STEP 1: Discovering URLs via Facebook Search")
        print("=" * 60)
        urls = await discover_urls(page)

        if not urls:
            print("\nNo URLs discovered. Check cookies and try again.")
            print("Creating sample output structure for pipeline testing...")
            await browser.close()
            return 0, 0, errors

        # Step 2: Scrape each URL
        print("\n" + "=" * 60)
        print("STEP 2: Scraping Posts & Comments")
        print("=" * 60)

        for i, url in enumerate(urls):
            print(f"\n[{i + 1}/{len(urls)}] Scraping: {url[:80]}...")
            result = await scrape_post_page(page, url, name_map)

            if result is None:
                errors += 1
                with open(FAILED_URLS_FILE, "a") as f:
                    f.write(f"{url} — scrape failed or login wall\n")
                continue

            post_id = hashlib.sha256(url.encode()).hexdigest()[:12]
            result["id"] = post_id
            all_posts.append(result)
            pages_scraped += 1
            total_comments += len(result["comments"])
            print(f"  -> {len(result['comments'])} comments collected")

            await random_delay()

        await browser.close()

    # Write raw_posts.json
    posts_file = OUTPUT_DIR / "raw_posts.json"
    with open(posts_file, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {posts_file} ({len(all_posts)} posts)")

    # Write raw_comments.csv
    csv_file = OUTPUT_DIR / "raw_comments.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["post_id", "comment_id", "author_anon", "date", "text", "likes"])
        for post in all_posts:
            for comment in post["comments"]:
                writer.writerow(
                    [
                        post["id"],
                        comment["id"],
                        comment["author_anon"],
                        comment["date"],
                        comment["text"],
                        comment["likes"],
                    ]
                )
    print(f"Wrote {csv_file}")

    return pages_scraped, total_comments, errors


if __name__ == "__main__":
    pages, comments, errs = asyncio.run(run_scraper())
    print(f"\n{'=' * 60}")
    print(f"SCRAPING SUMMARY")
    print(f"  Pages scraped: {pages}")
    print(f"  Comments collected: {comments}")
    print(f"  Errors: {errs}")
    print(f"{'=' * 60}")
