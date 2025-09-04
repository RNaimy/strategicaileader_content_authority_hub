from __future__ import annotations
from typing import List, Optional, Dict, Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import logging

# DB
from src.db.session import SessionLocal
from src.db.models import ContentLink, GraphMetric, ContentItem

# Optional services (keep imports lazy-safe)
try:
    from src.services.link_extractor import extract_links as _extract_links
except Exception:  # pragma: no cover
    _extract_links = None  # type: ignore

try:
    from src.services.graph_builder import recompute_graph_metrics as _recompute_graph_metrics
except Exception:  # pragma: no cover
    _recompute_graph_metrics = None  # type: ignore

try:
    from src.services.graph_builder import build_link_index as _build_link_index
except Exception:  # pragma: no cover
    _build_link_index = None  # type: ignore

try:
    from src.services.graph_builder import reextract_links as _reextract_links
except Exception:  # pragma: no cover
    _reextract_links = None  # type: ignore

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/graph", tags=["graph"])


# ---- Dependency injection helpers ----
def get_db_session() -> Iterable[Session]:
    """Provide a database session for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


# ----- Schemas -----
class ExtractLinksRequest(BaseModel):
    content_item_id: int = Field(gt=0)
    html: Optional[str] = None
    url: Optional[str] = None


class RecomputeRequest(BaseModel):
    content_ids: Optional[List[int]] = None


class ReindexRequest(BaseModel):
    limit: Optional[int] = Field(default=None, ge=1, le=5000)


# ----- Utilities -----
def _fetch_html(url: str, timeout: float = 10.0) -> str | None:
    """Lightweight HTML fetcher using stdlib only. Returns None on any failure."""
    if not url:
        return None
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AuthorityGraphBot/1.0 (+https://example.com)"
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Only accept HTML-ish responses
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype.lower():
                return None
            data = resp.read()
            try:
                return data.decode("utf-8", errors="ignore")
            except Exception:
                # Fallback for odd encodings
                return data.decode("latin-1", errors="ignore")
    except Exception:
        return None


# ----- Routes -----
@router.get("/health")
def health():
    """
    Health check and service discovery endpoint for the authority-graph API.
    Returns status and a list of available sub-routes for debugging and discoverability of graph routes.
    """
    return {
        "ok": True,
        "service": "authority-graph",
        "routers": [
            "/health",
            "/content/{content_id}/links",
            "/metrics/{content_id}",
            "/extract-links",
            "/recompute-metrics",
            "/reindex",
            "/reextract",
            "/view",
        ]
    }


@router.get("/content/{content_id}/links")
def get_links(content_id: int, db: Session = Depends(get_db_session)):
    rows = (
        db.query(ContentLink)
        .filter(ContentLink.from_content_id == content_id)
        .order_by(ContentLink.id.desc())
        .all()
    )
    return {
        "ok": True,
        "count": len(rows),
        "links": [
            {
                "id": r.id,
                "to_content_id": r.to_content_id,
                "to_url": r.to_url,
                "anchor_text": r.anchor_text,
                "rel": r.rel,
                "nofollow": r.nofollow,
                "is_internal": r.is_internal,
            }
            for r in rows
        ],
    }


@router.get("/metrics/{content_id}")
def get_metrics(content_id: int, db: Session = Depends(get_db_session)):
    m = (
        db.query(GraphMetric)
        .filter(GraphMetric.content_id == content_id)
        .order_by(GraphMetric.id.desc())
        .first()
    )
    if not m:
        return {"ok": True, "metrics": None}
    return {
        "ok": True,
        "metrics": {
                "content_id": m.content_id,
                "degree_in": m.degree_in,
                "degree_out": m.degree_out,
                "pagerank": m.pagerank,
                "authority": m.authority,
                "hub": m.hub,
                "last_computed_at": m.last_computed_at,
        },
    }


def _link_identity_dict(link: Any) -> Dict[str, Any]:
    """Canonical identity keys for duplicate detection.
    Accepts either a mapping (dict-like) or an object with attributes
    such as `to_url`, `anchor_text`, etc.
    """
    def _get(name: str, default=None):
        # support dict-like and attribute access
        if isinstance(link, dict):
            return link.get(name, default)
        return getattr(link, name, default)

    to_url = (_get("to_url") or "").strip() or None
    anchor_text = (_get("anchor_text") or "").strip() or None
    rel = (_get("rel") or "").strip() or None

    return {
        "to_content_id": _get("to_content_id"),
        "to_url": to_url,
        "anchor_text": anchor_text,
        "rel": rel,
        "nofollow": bool(_get("nofollow", False)),
        "is_internal": bool(_get("is_internal", False)),
    }


@router.post("/extract-links")
def extract_links(payload: ExtractLinksRequest, db: Session = Depends(get_db_session)):
    """
    Extract links for the given content item.

    Priority of HTML sources:
    1) `payload.html` if provided.
    2) Fetch from `payload.url` if provided.
    3) Look up ContentItem.url for `payload.content_item_id` and fetch that.

    Deduplicates based on (from_content_id, to_url, anchor_text, rel, nofollow, is_internal).
    If the extractor or fetch fails, returns `{"ok": True, "created": 0}` (non-fatal).
    """
    # Resolve HTML
    html: Optional[str] = payload.html
    resolved_url: Optional[str] = payload.url

    if html is None:
        if not resolved_url:
            # Try to look up the content URL if not explicitly provided
            ci = (
                db.query(ContentItem.url)
                .filter(ContentItem.id == payload.content_item_id)
                .first()
            )
            if ci:
                resolved_url = ci[0]

        if resolved_url:
            html = _fetch_html(resolved_url)

    if not html:
        # Nothing to extract from
        return {"ok": True, "created": 0}

    extracted = []
    if _extract_links:
        try:
            extracted = _extract_links(html, base_url=resolved_url)
            # Normalize to simple dicts if the extractor returns objects
            norm = []
            for l in extracted or []:
                if isinstance(l, dict):
                    norm.append(l)
                else:
                    # Try to read attributes commonly provided by the Link dataclass
                    norm.append({
                        "to_content_id": getattr(l, "to_content_id", None),
                        "to_url": getattr(l, "to_url", None),
                        "anchor_text": getattr(l, "anchor_text", None),
                        "rel": getattr(l, "rel", None),
                        "nofollow": bool(getattr(l, "nofollow", False)),
                        "is_internal": bool(getattr(l, "is_internal", False)),
                    })
            extracted = norm
        except Exception:
            extracted = []

    if not extracted:
        return {"ok": True, "created": 0}

    try:
        # Build a set of existing identities to avoid duplicates
        existing: set[tuple] = set()
        for row in (
            db.query(ContentLink)
            .filter(ContentLink.from_content_id == payload.content_item_id)
            .all()
        ):
            ident = (
                row.to_content_id,
                (row.to_url or None),
                (row.anchor_text or None),
                (row.rel or None),
                bool(row.nofollow),
                bool(row.is_internal),
            )
            existing.add(ident)

        created = 0
        for link in extracted:
            ident_dict = _link_identity_dict(link)
            ident_tuple = (
                ident_dict["to_content_id"],
                ident_dict["to_url"],
                ident_dict["anchor_text"],
                ident_dict["rel"],
                ident_dict["nofollow"],
                ident_dict["is_internal"],
            )
            if ident_tuple in existing:
                continue  # skip duplicates

            db.add(
                ContentLink(
                    from_content_id=payload.content_item_id,
                    to_content_id=ident_dict["to_content_id"],
                    to_url=ident_dict["to_url"],
                    anchor_text=ident_dict["anchor_text"],
                    rel=ident_dict["rel"],
                    nofollow=ident_dict["nofollow"],
                    is_internal=ident_dict["is_internal"],
                )
            )
            existing.add(ident_tuple)
            created += 1

        if created:
            db.commit()
        return {"ok": True, "created": created}
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("extract_links DB error")
        return {"ok": False, "created": 0, "error": str(e)}


@router.post("/recompute-metrics")
def recompute_metrics(payload: RecomputeRequest, db: Session = Depends(get_db_session)):
    """Recompute graph metrics for all or a subset of content IDs.
    Falls back to a stubbed response when the service isn't available.
    """
    if _recompute_graph_metrics:
        try:
            import inspect
            sig = inspect.signature(_recompute_graph_metrics)
            kwargs = {}
            if 'content_ids' in sig.parameters:
                kwargs['content_ids'] = payload.content_ids
            if 'db' in sig.parameters:
                kwargs['db'] = db
            count = _recompute_graph_metrics(**kwargs)
            return {"ok": True, "recomputed": int(count or 0)}
        except Exception as e:
            return {"ok": False, "recomputed": 0, "error": str(e)}
    return {"ok": True, "recomputed": 0}


@router.post("/reindex")
def reindex(payload: ReindexRequest = ReindexRequest(), db: Session = Depends(get_db_session)):
    """Build the in-DB link index (content_id <-> url map). If the real service exists, call it; otherwise no-op to keep API stable."""
    if _build_link_index:
        try:
            import inspect
            sig = inspect.signature(_build_link_index)
            kwargs = {}
            if 'limit' in sig.parameters:
                kwargs['limit'] = payload.limit
            if 'db' in sig.parameters:
                kwargs['db'] = db
            count = _build_link_index(**kwargs)
            return {"ok": True, "indexed": int(count or 0)}
        except Exception as e:
            return {"ok": False, "indexed": 0, "error": str(e)}
    return {"ok": True, "indexed": 0}


@router.post("/reextract")
def reextract(payload: RecomputeRequest = RecomputeRequest(), db: Session = Depends(get_db_session)):
    """Re-extract links for the given content IDs (or all, if None). Calls the real service when available; otherwise returns a stubbed count."""
    if _reextract_links:
        try:
            import inspect
            sig = inspect.signature(_reextract_links)
            kwargs = {}
            # Support either 'items' or 'content_ids' param names
            if 'items' in sig.parameters:
                kwargs['items'] = payload.content_ids
            elif 'content_ids' in sig.parameters:
                kwargs['content_ids'] = payload.content_ids
            if 'db' in sig.parameters:
                kwargs['db'] = db
            count = _reextract_links(**kwargs)
            return {"ok": True, "reextracted": int(count or 0)}
        except Exception as e:
            return {"ok": False, "reextracted": 0, "error": str(e)}
    return {"ok": True, "reextracted": 0}


@router.get("/view")
def view_graph(limit: int = 200, db: Session = Depends(get_db_session)):
    """Return a lightweight graph snapshot: nodes (content items) and edges (links).
    This is intentionally simple and avoids heavy joins so it stays fast.
    """
    # Gather recent edges up to a cap
    edges_q = (
        db.query(ContentLink)
        .order_by(ContentLink.id.desc())
        .limit(max(1, min(limit, 2000)))
    )
    edges_rows = edges_q.all()

    # Collect node IDs referenced by edges
    node_ids: set[int] = set(r.from_content_id for r in edges_rows)
    node_ids.update(r.to_content_id for r in edges_rows if r.to_content_id is not None)

    # Fetch node metadata
    if node_ids:
        nodes_rows = (
            db.query(ContentItem.id, ContentItem.title, ContentItem.url)
            .filter(ContentItem.id.in_(list(node_ids)))
            .all()
        )
    else:
        nodes_rows = []

    nodes = [
        {"id": r.id, "title": r.title, "url": r.url}
        for r in nodes_rows
    ]
    edges = [
        {
            "from": r.from_content_id,
            "to": r.to_content_id,
            "to_url": r.to_url,
            "anchor_text": r.anchor_text,
            "internal": r.is_internal,
            "nofollow": r.nofollow,
        }
        for r in edges_rows
    ]

    return {"ok": True, "nodes": nodes, "edges": edges, "count": {"nodes": len(nodes), "edges": len(edges)}}
