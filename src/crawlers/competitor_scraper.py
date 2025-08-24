"""
Lightweight competitor scraper scaffold.

Purpose
-------
Provide a minimal, testable scraper for competitor sites that:
- fetches pages (with retries and timeouts),
- optionally walks a sitemap.xml,
- extracts core fields (url, title, text, word_count, published_at guess),
- yields normalized results for later ingestion.

This is intentionally dependency-light. If we later want trafilatura/readability,
we can swap out `extract_content()` behind the same interface.

Usage (dev)
-----------
python -m src.crawlers.competitor_scraper --source https://example.com/sitemap.xml --mode sitemap --limit 50
python -m src.crawlers.competitor_scraper --source https://example.com --mode url --limit 10
"""

from __future__ import annotations

import re
import sys
import time
import json
import html
import argparse
import random
import datetime as dt
from dataclasses import dataclass, asdict
from typing import Iterable, Iterator, Optional, List, Dict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5
UA = "ContentAuthorityHubBot/0.1 (+https://github.com/RNaimy/strategicaileader_content_authority_hub)"

# Politeness & safety
MIN_BASE_DELAY = 0.5  # seconds between requests when robots.txt has no crawl-delay
JITTER_MAX = 0.75     # add up to this many seconds of random jitter to each wait
MAX_HTML_BYTES = 2_500_000  # skip very large responses

# Caches for politeness
_LAST_REQUEST_AT: dict[str, float] = {}

# -----------------------------
# Data structures
# -----------------------------

@dataclass
class ScrapeResult:
    url: str
    title: str
    text: str
    word_count: int
    published_at: Optional[str] = None  # ISO8601 if inferred
    fetched_at: str = dt.datetime.utcnow().isoformat()
    source: str = "competitor"

# -----------------------------
# Helpers
# -----------------------------

def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _netloc(url: str) -> str:
    return urlparse(url).netloc

def _polite_sleep_for(netloc: str, base_delay: float = MIN_BASE_DELAY) -> None:
    """Sleep to space out per-domain requests with jitter (ignores robots.txt)."""
    now = time.time()
    last = _LAST_REQUEST_AT.get(netloc, 0.0)
    jitter = random.uniform(0.0, JITTER_MAX)
    wait_until = last + base_delay + jitter
    if now < wait_until:
        time.sleep(wait_until - now)
    _LAST_REQUEST_AT[netloc] = time.time()

def fetch_url(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[requests.Response]:
    """
    GET with basic retries and a polite UA. Returns Response or None.
    """
    # Polite spacing with jitter (robots.txt ignored)
    _polite_sleep_for(_netloc(url))

    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            # Skip non-HTML or overly large responses
            ctype = resp.headers.get("content-type", "").lower()
            if "html" not in ctype:
                return None
            if resp.headers.get("content-length") and int(resp.headers["content-length"]) > MAX_HTML_BYTES:
                return None
            if not resp.headers.get("content-length") and len(resp.content) > MAX_HTML_BYTES:
                return None
            if resp.status_code >= 400:
                # 404/410 etc. don't retry except 5xx
                if 500 <= resp.status_code < 600 and attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF ** attempt + random.uniform(0.0, JITTER_MAX))
                    continue
                return None
            return resp
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep((RETRY_BACKOFF ** attempt) + random.uniform(0.0, JITTER_MAX))
                continue
            return None
    return None

def extract_content(url: str, html_text: str) -> ScrapeResult:
    soup = BeautifulSoup(html_text, "html.parser")

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string
    else:
        ogt = soup.select_one("meta[property='og:title']")
        if ogt and ogt.get("content"):
            title = ogt.get("content")

    title = html.unescape(_normalize_whitespace(title))

    # Main text (very simple heuristic: concat paragraphs)
    paragraphs = []
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        text = _normalize_whitespace(text)
        if text:
            paragraphs.append(text)

    body_text = _normalize_whitespace(" ".join(paragraphs))
    word_count = len(body_text.split()) if body_text else 0

    published_at = _guess_published_at(soup)

    return ScrapeResult(
        url=url,
        title=title,
        text=body_text,
        word_count=word_count,
        published_at=published_at,
    )

def _guess_published_at(soup: BeautifulSoup) -> Optional[str]:
    """
    Best-effort: look for common meta tags or time elements.
    Returns ISO8601 string if found.
    """
    # Common meta patterns
    selectors = [
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="article:published_time"]', "content"),
        ('meta[name="pubdate"]', "content"),
        ('meta[name="publish_date"]', "content"),
        ('meta[name="date"]', "content"),
        ("time[datetime]", "datetime"),
        ("meta[itemprop='datePublished']", "content"),
    ]
    for sel, attr in selectors:
        el = soup.select_one(sel)
        if el and el.get(attr):
            val = el.get(attr).strip()
            # Normalize a bit
            try:
                # Many formats; try fromisoformat first, else parse loosely
                return dt.datetime.fromisoformat(val.replace("Z", "+00:00")).isoformat()
            except Exception:
                # Loose regex fallback for YYYY-MM-DD
                m = re.search(r"\d{4}-\d{2}-\d{2}", val)
                if m:
                    try:
                        d = dt.datetime.strptime(m.group(0), "%Y-%m-%d")
                        return d.isoformat()
                    except Exception:
                        pass
    return None

def iter_sitemap_urls(sitemap_url: str, limit: Optional[int] = None) -> Iterator[str]:
    """
    Pull a (flat) sitemap.xml and yield <loc> urls.
    If the sitemap index references nested sitemaps, we fetch them too (1 level deep).
    """
    seen: set[str] = set()

    def _parse_sm(url: str):
        resp = fetch_url(url)
        if not resp or "xml" not in resp.headers.get("content-type", ""):
            return []
        soup = BeautifulSoup(resp.text, "xml")
        locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
        return locs

    queue = [sitemap_url]
    while queue:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        for loc in _parse_sm(sm):
            # If it looks like a nested sitemap, enqueue; else yield URL
            if loc.endswith(".xml"):
                queue.append(loc)
            else:
                yield loc
                if limit is not None:
                    limit -= 1
                    if limit <= 0:
                        return

def extract_links(base_url: str, html_text: str) -> List[str]:
    """
    Extract site-internal links that look like articles (very lenient).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    links: List[str] = []
    base_netloc = urlparse(base_url).netloc
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        abs_url = urljoin(base_url, href)
        u = urlparse(abs_url)
        if u.netloc != base_netloc:
            continue
        # crude filter to avoid nav/login/cart etc.
        if any(seg in u.path.lower() for seg in ("/tag/", "/category/", "/cart", "/account", "/login", "/search")):
            continue
        links.append(abs_url)
    # dedupe while preserving order
    seen = set()
    uniq = []
    for u in links:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq

# -----------------------------
# Public scraper
# -----------------------------

def scrape_from_sitemap(sitemap_url: str, limit: int = 200) -> Iterator[ScrapeResult]:
    for url in iter_sitemap_urls(sitemap_url, limit=limit):
        resp = fetch_url(url)
        if not resp:
            continue
        yield extract_content(url, resp.text)

def scrape_from_url(start_url: str, limit: int = 50) -> Iterator[ScrapeResult]:
    """
    Crawl starting page and follow internal links (shallow crawl).
    """
    start = fetch_url(start_url)
    if not start:
        return
    yield extract_content(start_url, start.text)

    count = 1
    for link in extract_links(start_url, start.text):
        if count >= limit:
            break
        resp = fetch_url(link)
        if not resp:
            continue
        yield extract_content(link, resp.text)
        count += 1

# -----------------------------
# CLI for quick experiments
# -----------------------------

def _cli() -> int:
    parser = argparse.ArgumentParser(description="Competitor scraper (scaffold)")
    parser.add_argument("--source", required=True, help="sitemap.xml or start URL")
    parser.add_argument("--mode", choices=["sitemap", "url"], default="sitemap")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", choices=["jsonl", "stdout"], default="stdout")
    args = parser.parse_args()

    if args.mode == "sitemap":
        it = scrape_from_sitemap(args.source, limit=args.limit)
    else:
        it = scrape_from_url(args.source, limit=args.limit)

    if args.output == "stdout":
        for item in it:
            print(f"- {item.url} | {item.title} ({item.word_count} words)")
    else:
        for item in it:
            print(json.dumps(asdict(item), ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(_cli())