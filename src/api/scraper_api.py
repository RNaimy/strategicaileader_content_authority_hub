# src/api/scraper_api.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime

from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import re
from src.db.session import database

import gzip
import io
from urllib.parse import urljoin
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/scraper", tags=["scraper"])


class SitemapRequest(BaseModel):
    site_id: int
    sitemap_url: Optional[str] = None
    domain: Optional[str] = None


class ScrapePageRequest(BaseModel):
    site_id: int
    url: str


class ScrapeBatchRequest(BaseModel):
    site_id: int
    limit: int = 50  # number of pending URLs to enrich


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "scraper"}


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_from_html(html: str) -> Dict[str, Optional[str]]:
    """Extract title, meta description and main text from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style/nav/footer/aside/header
    for tag in soup(
        ["script", "style", "noscript", "template", "nav", "footer", "aside", "header"]
    ):
        tag.decompose()

    # Prefer article/main content blocks if present
    main = soup.find("article") or soup.find("main") or soup.body or soup

    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    title = (
        title_tag.get("content")
        if title_tag and title_tag.name == "meta"
        else (title_tag.string if title_tag else None)
    )

    desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", property="og:description"
    )
    meta_description = desc_tag.get("content") if desc_tag else None

    # Basic heuristic for main text
    # Prefer paragraph-rich sections
    paragraphs = [p.get_text(" ", strip=True) for p in main.find_all("p")]
    if paragraphs:
        content_text = "\n\n".join(paragraphs)
    else:
        content_text = main.get_text(" ", strip=True)

    return {
        "title": _clean_text(title or ""),
        "meta_description": _clean_text(meta_description or ""),
        "content": _clean_text(content_text or ""),
    }


async def _upsert_content(
    site_id: int, url: str, fields: Dict[str, Optional[str]]
) -> int:
    """Insert or update a content_items row and return 1 if written."""
    now = datetime.utcnow()
    # Works for Postgres and SQLite thanks to the unique constraint on (site_id, url)
    query = """
        INSERT INTO content_items (site_id, url, title, meta_description, content, created_at, updated_at)
        VALUES (:site_id, :url, :title, :meta_description, :content, :created_at, :updated_at)
        ON CONFLICT (site_id, url) DO UPDATE
        SET title = EXCLUDED.title,
            meta_description = EXCLUDED.meta_description,
            content = EXCLUDED.content,
            updated_at = EXCLUDED.updated_at
    """
    await database.execute(
        query=query,
        values={
            "site_id": site_id,
            "url": url,
            "title": fields.get("title") or None,
            "meta_description": fields.get("meta_description") or None,
            "content": fields.get("content") or None,
            "created_at": now,
            "updated_at": now,
        },
    )
    return 1


async def _fetch_url_text(url: str) -> str:
    """Fetch a URL and return decoded text. Transparently handles .gz sitemaps."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "ContentHubBot/1.0"})
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.content
        is_gzip = (
            url.lower().endswith(".gz")
            or "gzip" in content_type
            or "application/x-gzip" in content_type
        )
        if is_gzip:
            try:
                raw = gzip.decompress(raw)
            except OSError:
                # Some servers send gzipped content without headers; try gzip fileobj fallback
                with io.BytesIO(resp.content) as bio:
                    with gzip.GzipFile(fileobj=bio) as gz:
                        raw = gz.read()
        # Best-effort decode
        try:
            return raw.decode(resp.encoding or "utf-8", errors="replace")
        except Exception:
            return raw.decode("utf-8", errors="replace")


def _extract_urls_from_sitemap(xml_text: str) -> Dict[str, List[str]]:
    """
    Parse a sitemap or sitemap index and return dict with:
      - 'urls': list of page URLs from <urlset>
      - 'sitemaps': list of sitemap URLs from <sitemapindex>
    Handles namespace/no-namespace docs.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"urls": [], "sitemaps": []}

    # Determine namespace (if any)
    if root.tag.startswith("{"):
        ns_uri = root.tag.split("}", 1)[0][1:]
        ns = {"sm": ns_uri}
        url_elems = root.findall(".//sm:url/sm:loc", ns)
        sitemap_elems = root.findall(".//sm:sitemap/sm:loc", ns)
    else:
        ns = {}
        url_elems = root.findall(".//url/loc")
        sitemap_elems = root.findall(".//sitemap/loc")

    urls = [e.text.strip() for e in url_elems if e is not None and e.text]
    sitemaps = [e.text.strip() for e in sitemap_elems if e is not None and e.text]
    return {"urls": urls, "sitemaps": sitemaps}


async def _discover_sitemaps(domain: str) -> List[str]:
    """
    Try robots.txt discovery and fall back to common sitemap endpoints.
    Returns a de-duplicated list in priority order.
    """
    candidates: List[str] = []
    # robots.txt
    robots_url = f"https://{domain}/robots.txt"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(
                robots_url, headers={"User-Agent": "ContentHubBot/1.0"}
            )
            if r.status_code < 400 and r.text:
                for line in r.text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.lower().startswith("sitemap:"):
                        sm = line.split(":", 1)[1].strip()
                        if sm:
                            candidates.append(sm)
    except httpx.HTTPError:
        pass

    # Common fallbacks
    candidates.extend(
        [
            f"https://{domain}/sitemap_index.xml",
            f"https://{domain}/sitemap.xml",
        ]
    )

    # De-duplicate preserving order
    seen = set()
    out: List[str] = []
    for c in candidates:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out


async def _gather_all_sitemap_urls(
    entry_url: str, max_sitemaps: int = 50
) -> Dict[str, List[str]]:
    """
    Given a sitemap *or* sitemap index URL, return aggregated:
      {
        "from_sitemaps": [...list of sitemap URLs seen...],
        "page_urls": [...all page URLs found...]
      }
    Limits traversal to max_sitemaps to avoid abuse.
    """
    xml_text = await _fetch_url_text(entry_url)
    parsed = _extract_urls_from_sitemap(xml_text)
    page_urls: List[str] = []
    seen_sitemaps: List[str] = []

    if parsed["sitemaps"]:
        # It's an index — iterate child sitemaps
        for sm_url in parsed["sitemaps"][:max_sitemaps]:
            seen_sitemaps.append(sm_url)
            try:
                child_xml = await _fetch_url_text(sm_url)
                child_parsed = _extract_urls_from_sitemap(child_xml)
                page_urls.extend(child_parsed["urls"])
            except httpx.HTTPError:
                continue
    else:
        # It's a plain urlset
        page_urls = parsed["urls"]
        seen_sitemaps = []

    # Normalize simple duplicates
    uniq = []
    seen = set()
    for u in page_urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    return {"from_sitemaps": seen_sitemaps, "page_urls": uniq}


@router.post("/scrape-page")
async def scrape_page(req: ScrapePageRequest):
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        try:
            resp = await client.get(
                req.url, headers={"User-Agent": "ContentHubBot/1.0"}
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

    fields = _extract_from_html(resp.text)
    written = await _upsert_content(req.site_id, req.url, fields)

    return {
        "site_id": req.site_id,
        "url": req.url,
        "written": written,
        "title_len": len(fields.get("title", "") or ""),
        "meta_len": len(fields.get("meta_description", "") or ""),
        "content_len": len(fields.get("content", "") or ""),
    }


@router.post("/scrape")
async def scrape(req: ScrapePageRequest):
    """Alias for /scrape-page to match older clients/cURL examples."""
    return await scrape_page(req)


@router.post("/scrape-batch")
async def scrape_batch(req: ScrapeBatchRequest):
    # Fetch pending URLs for this site
    select_query = """
        SELECT url
        FROM content_items
        WHERE site_id = :site_id
          AND (title IS NULL OR content IS NULL OR title = '' OR content = '')
        ORDER BY id DESC
        LIMIT :limit
    """
    rows = await database.fetch_all(
        select_query, values={"site_id": req.site_id, "limit": req.limit}
    )
    urls = [r["url"] for r in rows]

    results: List[Dict[str, object]] = []
    if not urls:
        return {
            "site_id": req.site_id,
            "requested": req.limit,
            "processed": 0,
            "results": results,
        }

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(
                    url, headers={"User-Agent": "ContentHubBot/1.0"}
                )
                resp.raise_for_status()
                fields = _extract_from_html(resp.text)
                await _upsert_content(req.site_id, url, fields)
                results.append({"url": url, "ok": True, "title": fields.get("title")})
            except httpx.HTTPError as e:
                results.append({"url": url, "ok": False, "error": str(e)})

    return {
        "site_id": req.site_id,
        "requested": req.limit,
        "processed": len(results),
        "results": results,
    }


@router.post("/sitemap")
async def process_sitemap_post(data: SitemapRequest):
    # Determine which sitemap(s) to use
    chosen_sitemaps: List[str] = []
    if data.sitemap_url:
        chosen_sitemaps = [data.sitemap_url]
    elif data.domain:
        discovered = await _discover_sitemaps(data.domain)
        if not discovered:
            return {
                "error": "No sitemap endpoints discovered via robots.txt or defaults.",
                "site_id": data.site_id,
                "domain": data.domain,
            }
        chosen_sitemaps = discovered
    else:
        return {
            "error": "Either sitemap_url or domain must be provided",
            "site_id": data.site_id,
        }

    # Try each candidate until we successfully parse *something*
    aggregated_urls: List[str] = []
    used_sitemaps: List[str] = []
    traversed_children: List[str] = []
    for sm in chosen_sitemaps:
        try:
            result = await _gather_all_sitemap_urls(sm)
            if result["page_urls"]:
                aggregated_urls.extend(result["page_urls"])
                used_sitemaps.append(sm)
                traversed_children.extend(result["from_sitemaps"])
                break  # good enough
        except httpx.HTTPError as e:
            continue

    total_urls_found = len(aggregated_urls)

    insert_query = """
        INSERT INTO content_items (site_id, url, created_at, updated_at)
        VALUES (:site_id, :url, :created_at, :updated_at)
        ON CONFLICT (site_id, url) DO NOTHING
    """
    inserted_count = 0
    errors: List[str] = []
    now = datetime.utcnow()
    for url in aggregated_urls:
        try:
            # Executes an INSERT; if the row already exists, DO NOTHING means 0 rows affected.
            await database.execute(
                query=insert_query,
                values={
                    "site_id": data.site_id,
                    "url": url,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            # We can't rely on rowcount with `databases`, so check existence immediately after.
            exists = await database.fetch_one(
                query="SELECT id FROM content_items WHERE site_id=:site_id AND url=:url",
                values={"site_id": data.site_id, "url": url},
            )
            # If it existed before this insert, this still returns a row — to avoid overcounting,
            # only increment when the row wasn't there just before. The simplest safe heuristic:
            # increment if content was absent immediately prior; fall back to first-seen cache.
            # For reliability here, increment when the SELECT was empty before this loop iteration.
            # To implement that, do a pre-check:
        except IntegrityError:
            # Unique violation race — treat as "skipped"
            continue
        except Exception as e:
            errors.append(str(e))
            continue
        else:
            # We don't know if it was new or existing due to DO NOTHING; re-check using a pre-check.
            # Perform a prior existence check and re-insert only if absent is heavy; so approximate
            # by counting new rows via TRY INSERT followed by checking how many rows match with a
            # created_at ~ now(). This is good enough for batch ingestion.
            chk = await database.fetch_one(
                query="SELECT 1 FROM content_items WHERE site_id=:site_id AND url=:url AND created_at >= :ts",
                values={"site_id": data.site_id, "url": url, "ts": now},
            )
            if chk:
                inserted_count += 1
    if errors:
        # Non-fatal errors occurred; include a sample for visibility.
        return {
            "site_id": data.site_id,
            "domain": data.domain,
            "used_sitemaps": used_sitemaps,
            "child_sitemaps": traversed_children,
            "total_urls_found": total_urls_found,
            "inserted_count": inserted_count,
            "skipped_existing": total_urls_found - inserted_count,
            "errors_sample": errors[:5],
        }

    return {
        "site_id": data.site_id,
        "domain": data.domain,
        "used_sitemaps": used_sitemaps,
        "child_sitemaps": traversed_children,
        "total_urls_found": total_urls_found,
        "inserted_count": inserted_count,
        "skipped_existing": total_urls_found - inserted_count,
    }


@router.get("/sitemap")
async def process_sitemap_get(
    site_id: int = Query(...),
    domain: str = Query(...),
    limit: int = Query(0, ge=0, le=50000),
):
    # Discover endpoints and choose the first that yields URLs
    discovered = await _discover_sitemaps(domain)
    if not discovered:
        return {
            "error": "No sitemap endpoints discovered via robots.txt or defaults.",
            "site_id": site_id,
            "domain": domain,
        }

    aggregated_urls: List[str] = []
    used: str = ""
    children: List[str] = []
    for sm in discovered:
        try:
            result = await _gather_all_sitemap_urls(sm)
            urls = result["page_urls"]
            if limit and limit > 0:
                urls = urls[:limit]
            if urls:
                aggregated_urls = urls
                used = sm
                children = result["from_sitemaps"]
                break
        except httpx.HTTPError:
            continue

    total_urls_found = len(aggregated_urls)

    insert_query = """
        INSERT INTO content_items (site_id, url, created_at, updated_at)
        VALUES (:site_id, :url, :created_at, :updated_at)
        ON CONFLICT (site_id, url) DO NOTHING
    """
    inserted_count = 0
    errors: List[str] = []
    now = datetime.utcnow()
    for url in aggregated_urls:
        try:
            await database.execute(
                query=insert_query,
                values={
                    "site_id": site_id,
                    "url": url,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        except IntegrityError:
            continue
        except Exception as e:
            errors.append(str(e))
            continue
        else:
            chk = await database.fetch_one(
                query="SELECT 1 FROM content_items WHERE site_id=:site_id AND url=:url AND created_at >= :ts",
                values={"site_id": site_id, "url": url, "ts": now},
            )
            if chk:
                inserted_count += 1
    if errors:
        return {
            "site_id": site_id,
            "domain": domain,
            "sitemap_url": used,
            "child_sitemaps": children,
            "total_urls_found": total_urls_found,
            "inserted_count": inserted_count,
            "skipped_existing": total_urls_found - inserted_count,
            "errors_sample": errors[:5],
        }

    return {
        "site_id": site_id,
        "domain": domain,
        "sitemap_url": used,
        "child_sitemaps": children,
        "total_urls_found": total_urls_found,
        "inserted_count": inserted_count,
        "skipped_existing": total_urls_found - inserted_count,
    }
