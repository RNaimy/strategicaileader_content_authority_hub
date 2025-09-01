from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import re
import json
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

# Optional (env-dependent). If unavailable, we fall back to a regex-based entity extractor.
try:  # pragma: no cover
    import spacy  # type: ignore
    _NLP = spacy.load("en_core_web_sm")  # small model if installed
except Exception:  # pragma: no cover
    _NLP = None


def _is_html(s: str) -> bool:
    return "</" in s or "<html" in s.lower() or "<body" in s.lower()


def _domain(url_or_host: str) -> str:
    try:
        p = urlparse(url_or_host)
        return p.netloc or url_or_host
    except Exception:
        return url_or_host


def html_to_text(html: str) -> str:
    if not html:
        return ""
    if BeautifulSoup is None:
        # Very naive fallback: strip tags
        return re.sub(r"<[^>]+>", " ", html)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def extract_jsonld(html: str) -> Tuple[bool, List[dict]]:
    if not html or BeautifulSoup is None:
        return False, []
    soup = BeautifulSoup(html, "html.parser")
    blocks: List[dict] = []
    present = False
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            blob = s.string or "{}"
            data = json.loads(blob)
            present = True
            if isinstance(data, list):
                blocks.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                blocks.append(data)
        except Exception:
            continue
    return present, blocks


def detect_byline(html: str, text: str, jsonld_blocks: List[dict]) -> Tuple[int, List[str]]:
    authors: List[str] = []
    # JSON-LD author fields
    for blk in jsonld_blocks:
        a = blk.get("author")
        if isinstance(a, dict):
            name = a.get("name")
            if isinstance(name, str) and name.strip():
                authors.append(name.strip())
        elif isinstance(a, list):
            for item in a:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str) and name.strip():
                        authors.append(name.strip())
    # Meta tags (if bs4 present)
    if BeautifulSoup is not None and html:
        soup = BeautifulSoup(html, "html.parser")
        for attr in ("name", "property"):
            for key in ("author", "article:author", "twitter:creator"):
                for m in soup.find_all("meta", attrs={attr: key}):
                    val = (m.get("content") or "").strip()
                    if val:
                        authors.append(val)
    # Visible text pattern
    for m in re.finditer(r"\bBy\s+([A-Z][\w\.-]+(?:\s+[A-Z][\w\.-]+)*)", text):
        authors.append(m.group(1).strip())

    # de-dup case-insensitively
    out: List[str] = []
    seen = set()
    for a in authors:
        key = a.lower()
        if key and key not in seen:
            out.append(a)
            seen.add(key)
    return len(out), out


def count_external_links(html: str, base_url: Optional[str] = None) -> Tuple[int, List[str]]:
    if not html:
        return 0, []
    if BeautifulSoup is None:
        hrefs = re.findall(r'href=["\'](https?://[^"\']+)', html, flags=re.I)
        domains = sorted(set(_domain(h) for h in hrefs))
        return len(hrefs), domains
    soup = BeautifulSoup(html, "html.parser")
    base_dom = _domain(base_url or "")
    hrefs: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http://") or href.startswith("https://"):
            # If base provided, exclude same-domain links; otherwise count all absolute
            if base_dom and _domain(href) == base_dom:
                continue
            hrefs.append(href)
    domains = sorted(set(_domain(h) for h in hrefs))
    return len(hrefs), domains


def _regex_entities(text: str) -> List[str]:
    # Simple heuristic: up to 4 consecutive Capitalized words (skip stop-starts)
    stop = {"The", "A", "An", "And", "Or", "In", "On", "Of", "For", "With", "By"}
    cands = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", text)
    out: List[str] = []
    seen = set()
    for c in cands:
        if c.split()[0] in stop:
            continue
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out[:200]


def extract_entities(text: str) -> List[str]:
    if not text:
        return []
    if _NLP is not None:  # pragma: no cover (depends on env)
        try:
            doc = _NLP(text)
            ents = [e.text.strip() for e in doc.ents if e.label_ in {"PERSON", "ORG", "GPE", "PRODUCT", "WORK_OF_ART"}]
            # dedupe
            out: List[str] = []
            seen = set()
            for e in ents:
                k = e.lower()
                if k and k not in seen:
                    out.append(e)
                    seen.add(k)
            return out[:200]
        except Exception:
            pass
    return _regex_entities(text)


def compute_authority_signals(content: str) -> Dict[str, float | int]:
    """Compute lightweight authority signals from raw text or HTML.

    Returns the keys used by Phase 7 MVP:
      - entity_coverage_score (0..1)
      - citation_count (int)
      - external_link_count (int)
      - schema_presence (0/1)
      - author_bylines (int)
    """
    raw = (content or "").strip()
    if not raw:
        return {
            "entity_coverage_score": 0.0,
            "citation_count": 0,
            "external_link_count": 0,
            "schema_presence": 0,
            "author_bylines": 0,
        }

    # If HTML, parse for links/schema; otherwise treat as plain text
    is_html = _is_html(raw)
    text = html_to_text(raw) if is_html else raw

    jsonld_present = False
    jsonld_blocks: List[dict] = []
    external_link_count = 0

    if is_html:
        jsonld_present, jsonld_blocks = extract_jsonld(raw)
        external_link_count, _domains = count_external_links(raw)

    # Entities and coverage score (entities per 300 words, capped at 1.0)
    words = text.split()
    n_words = max(len(words), 1)
    entities = extract_entities(text)
    ents_per_300w = len(entities) / max(n_words / 300.0, 1e-6)
    entity_coverage_score = max(0.0, min(ents_per_300w / 12.0, 1.0))  # heuristic scale

    # Citations: footnote-like patterns + explicit http(s) links inside text
    citation_like = len(re.findall(r"\[(?:\d{1,3}|fn:\w+)\]", text))
    http_links = len(re.findall(r"https?://\S+", text))
    citation_count = citation_like + http_links

    # Byline detection
    byline_count, _authors = detect_byline(raw if is_html else "", text, jsonld_blocks)

    return {
        "entity_coverage_score": round(float(entity_coverage_score), 3),
        "citation_count": int(citation_count),
        "external_link_count": int(external_link_count),
        "schema_presence": 1 if jsonld_present else 0,
        "author_bylines": int(byline_count),
    }
