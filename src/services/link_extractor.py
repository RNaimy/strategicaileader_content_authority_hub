"""
Link extraction utilities for building the authority graph.

- Parse <a> tags from arbitrary HTML
- Resolve relative URLs against a base URL
- Classify as internal vs external
- Detect rel/nofollow
- Optionally persist to the `content_links` table
- Optionally dedupe identical links
- Treat rel=ugc/sponsored as nofollow (configurable)

This module is intentionally dependency-light and uses only the Python stdlib,
so it works in constrained environments (e.g., CI) without adding bs4/lxml.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from typing import Iterable, List, Dict, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

# Optional ORM imports are done lazily in persistence helpers to avoid circular imports.


@dataclass
class Link:
  """Normalized representation of a hyperlink discovered in HTML."""

  href: str
  anchor_text: str
  rel: Optional[str]
  nofollow: bool
  is_internal: bool
  to_content_id: Optional[int] = None  # Optional: resolved ContentItem.id if internal

  def as_dict(self) -> Dict[str, object]:
    return asdict(self)

  @property
  def to_url(self) -> str:
    """Backward-compat alias for code/tests that expected `to_url`.
    Internally we store the normalized destination in `href`."""
    return self.href


class _AnchorParser(HTMLParser):
  """Minimal HTML parser to extract <a> elements robustly without external deps."""

  def __init__(self) -> None:
    super().__init__(convert_charrefs=True)
    self._in_a = False
    self._current_attrs: Dict[str, Optional[str]] = {}
    self._buffer: List[str] = []
    self.links: List[Tuple[Dict[str, Optional[str]], str]] = []

  def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
    if tag.lower() == "a":
      self._in_a = True
      self._current_attrs = {k.lower(): (v or "") for k, v in attrs}
      self._buffer = []

  def handle_data(self, data: str) -> None:
    if self._in_a:
      self._buffer.append(data)

  def handle_endtag(self, tag: str) -> None:
    if tag.lower() == "a" and self._in_a:
      anchor_text = ("".join(self._buffer)).strip()
      self.links.append((self._current_attrs, anchor_text))
      self._in_a = False
      self._current_attrs = {}
      self._buffer = []


# ----------------------------
# URL utilities
# ----------------------------

def _normalize_url(url: str) -> str:
  """
  Normalize a URL for comparison and storage:
    - lowercase scheme/host
    - strip default ports (80/443)
    - remove fragments
    - collapse empty paths to '/'
  """
  if not url:
    return url
  parsed = urlparse(url)
  scheme = (parsed.scheme or "").lower()
  netloc = (parsed.netloc or "").lower()

  # Strip default ports
  if netloc.endswith(":80") and scheme == "http":
    netloc = netloc[:-3]
  if netloc.endswith(":443") and scheme == "https":
    netloc = netloc[:-4]

  path = parsed.path or "/"
  query = parsed.query
  # Drop fragment
  fragment = ""
  normalized = urlunparse((scheme, netloc, path, "", query, fragment))
  return normalized


def _is_same_site(url_netloc: str, base_netloc: str) -> bool:
  """
  Decide if url_netloc is internal to base_netloc.
  Rules:
    - exact host match is internal
    - subdomain of base (e.g., blog.example.com over example.com) is internal
  """
  if not url_netloc or not base_netloc:
    return False
  if url_netloc == base_netloc:
    return True
  return url_netloc.endswith("." + base_netloc)


# ----------------------------
# Public API
# ----------------------------

def extract_links(
  html: str,
  *,
  base_url: Optional[str] = None,
  internal_domains: Optional[Iterable[str]] = None,
  treat_ugc_sponsored_as_nofollow: bool = True,
  dedupe: bool = True,
) -> List[Link]:
  """
  Extract and classify links from HTML.

  Args:
    html: Raw HTML to parse.
    base_url: If provided, relative hrefs will be resolved against it and internal/external
              classification will be based on its host (and any internal_domains provided).
    internal_domains: Additional domains to treat as internal (netlocs), e.g., {"cdn.example.com"}.
    treat_ugc_sponsored_as_nofollow: Treat rel="ugc|sponsored" as nofollow.
    dedupe: Remove duplicate links by normalized href.

  Returns:
    List[Link]
  """
  internal_domains = set(internal_domains or [])

  parser = _AnchorParser()
  try:
    parser.feed(html or "")
    parser.close()
  except Exception:
    # Be resilient to bad markup—return whatever we could parse
    pass

  base_netloc = ""
  if base_url:
    base_netloc = urlparse(base_url).netloc.lower()
    if base_netloc:
      internal_domains.add(base_netloc)

  seen: Set[str] = set()
  results: List[Link] = []
  for attrs, anchor_text in parser.links:
    raw_href = (attrs.get("href") or "").strip()
    if not raw_href:
      continue

    # Resolve relative URLs against base, if available
    absolute = _normalize_url(urljoin(base_url, raw_href) if base_url else raw_href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
      # skip mailto:, javascript:, etc.
      continue

    rel = (attrs.get("rel") or "").strip() or None
    rel_tokens = set((rel or "").lower().split()) if rel else set()
    nofollow = ("nofollow" in rel_tokens) or (treat_ugc_sponsored_as_nofollow and ("ugc" in rel_tokens or "sponsored" in rel_tokens))

    if dedupe:
      if absolute in seen:
        continue
      seen.add(absolute)

    netloc = parsed.netloc.lower()
    is_internal = any(_is_same_site(netloc, d) for d in internal_domains) if netloc else False

    results.append(
      Link(
        href=absolute,
        anchor_text=anchor_text,
        rel=rel,
        nofollow=nofollow,
        is_internal=is_internal,
      )
    )
  return results


def persist_links_for_content(
  db_session,
  *,
  from_content_id: int,
  html: str,
  base_url: Optional[str],
  url_to_content_id: Optional[Dict[str, int]] = None,
) -> int:
  """
  Parse links from HTML and persist to `content_links`.

  - Deletes existing rows for the given from_content_id (to keep it idempotent).
  - Tries to resolve internal links to known ContentItem IDs using `url_to_content_id`
    (a dict of normalized_url -> content_id). If not provided, it will lazy-load a map
    from the database.

  Returns:
    The number of links inserted.
  """
  # Lazy imports to avoid circular dependencies during Alembic autogenerate
  from src.db.models import ContentLink, ContentItem  # type: ignore

  links = extract_links(html, base_url=base_url)

  # Build resolver map if not provided
  if url_to_content_id is None:
    # Fetch all known URLs once; normalize for matching.
    rows = (
      db_session.query(ContentItem.id, ContentItem.url)
      .filter(ContentItem.url.isnot(None))
      .all()
    )
    url_to_content_id = { _normalize_url(url): cid for (cid, url) in rows if url }

  # Delete existing links for the page to keep a single source of truth per scrape
  db_session.query(ContentLink).filter(ContentLink.from_content_id == from_content_id).delete()

  # Prepare bulk objects
  to_insert = []
  for link in links:
    to_id = url_to_content_id.get(link.href) if link.is_internal else None
    to_insert.append(
      ContentLink(
        from_content_id=from_content_id,
        to_content_id=to_id,
        to_url=link.href if not to_id else None,  # Store URL only when we don't have a content_id
        anchor_text=link.anchor_text or None,
        rel=link.rel,
        nofollow=link.nofollow,
        is_internal=link.is_internal,
      )
    )

  if to_insert:
    db_session.bulk_save_objects(to_insert)
  db_session.commit()
  return len(to_insert)


__all__ = [
  "Link",
  "extract_links",
  "persist_links_for_content",
]