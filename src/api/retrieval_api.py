from typing import List, Optional, Dict, Any, Tuple

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

# Local imports
try:
    from src.db.session import get_db  # type: ignore
    from src.db.models import ContentItem, Site  # type: ignore
except Exception:  # pragma: no cover - fallback for editable installs
    from db.session import get_db  # type: ignore
    from db.models import ContentItem, Site  # type: ignore

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class HealthPayload(BaseModel):
    status: str = "ok"
    ok: bool = True


@router.get("/health", response_model=HealthPayload)
def retrieval_health():
    """Lightweight readiness check for the retrieval API."""
    return HealthPayload()


class RetrievedNode(BaseModel):
    id: int
    url: str
    title: Optional[str] = None
    score: float = Field(ge=0, description="Simple relevance score (heuristic)")


class SearchResponse(BaseModel):
    query: str
    results: List[RetrievedNode]
    meta: Dict[str, Any] = {}


@router.get("/search", response_model=SearchResponse)
def semantic_search(
    q: str = Query(..., min_length=1, description="Search query"),
    site_id: Optional[int] = Query(None, description="Restrict to a specific site id"),
    domain: Optional[str] = Query(None, description="Restrict to a specific site by domain (e.g., example.com)"),
    top_k: int = Query(10, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Result offset for simple pagination"),
    db: Session = Depends(get_db),
):
    """Baseline semantic-retrieval endpoint.

    Phase 9 TODOs will swap this naive LIKE-based scoring for embedding
    similarity + ANN index. For now we return a stable shape so the UI
    can integrate immediately.

    Supports filtering by site via either site_id or domain, plus simple pagination via offset/top_k.
    """
    # Resolve site by either id or domain if provided
    resolved_site_id: Optional[int] = None
    if site_id is not None and domain is not None:
        # If both are provided, ensure they refer to the same site
        site_by_id = db.query(Site).filter(Site.id == site_id).first()
        if not site_by_id:
            raise HTTPException(status_code=404, detail="Site not found")
        site_by_domain = db.query(Site).filter(func.lower(Site.domain) == domain.lower()).first()
        if not site_by_domain:
            raise HTTPException(status_code=404, detail="Site (by domain) not found")
        if site_by_id.id != site_by_domain.id:
            raise HTTPException(status_code=400, detail="site_id and domain refer to different sites")
        resolved_site_id = site_by_id.id
    elif site_id is not None:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        resolved_site_id = site.id
    elif domain is not None:
        site = db.query(Site).filter(func.lower(Site.domain) == domain.lower()).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site (by domain) not found")
        resolved_site_id = site.id

    # Split on whitespace; if quotes are used, treat the quoted string as a single token (very light parsing)
    raw = q.strip()
    tokens: List[str] = []
    buf = ""
    in_quote = False
    for ch in raw:
        if ch == '"':
            in_quote = not in_quote
            if not in_quote and buf:
                tokens.append(buf)
                buf = ""
        elif ch.isspace() and not in_quote:
            if buf:
                tokens.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        tokens.append(buf)

    if not tokens:
        return SearchResponse(query=q, results=[], meta={"note": "empty query"})

    ilike_terms = [func.lower(ContentItem.title).like(f"%{t.lower()}%") for t in tokens]
    ilike_url = [func.lower(ContentItem.url).like(f"%{t.lower()}%") for t in tokens]
    predicate = or_(*(ilike_terms + ilike_url))

    query = db.query(ContentItem).filter(predicate)
    if resolved_site_id is not None:
        query = query.filter(ContentItem.site_id == resolved_site_id)

    candidates: List[ContentItem] = query.offset(offset).limit(min(top_k * 5, 500)).all()

    # Heuristic score: +2 for title token match, +1 for URL token match
    results: List[RetrievedNode] = []
    for c in candidates:
        title_l = (c.title or "").lower()
        url_l = (c.url or "").lower()
        score = 0.0
        for t in tokens:
            tl = t.lower()
            if tl in title_l:
                score += 2.0
            if tl in url_l:
                score += 1.0
        if score > 0:
            results.append(RetrievedNode(id=c.id, url=c.url, title=c.title, score=score))

    results.sort(key=lambda r: r.score, reverse=True)
    results = results[:top_k]

    return SearchResponse(
        query=q,
        results=results,
        meta={
            "algorithm": "heuristic-like-v0",
            "tokens": tokens,
            "total_candidates": len(candidates),
            "offset": offset,
            "site_id": resolved_site_id,
            "domain": domain,
        },
    )


class ReindexRequest(BaseModel):
    site_id: Optional[int] = Field(None, description="Restrict reindex to a site")
    domain: Optional[str] = Field(None, description="Restrict reindex to a site by domain")
    refresh_embeddings: bool = Field(
        True, description="Whether to recompute embeddings during reindex"
    )


@router.post("/reindex")
def reindex_corpus(payload: ReindexRequest, db: Session = Depends(get_db)):
    """Placeholder reindex endpoint.

    Phase 9 will wire this to the embedding pipeline + ANN index builder.
    Returning a simple status object keeps the contract stable.
    """
    # Validate site if provided via id or domain
    resolved_site_id: Optional[int] = None
    if payload.site_id is not None and payload.domain is not None:
        by_id = db.query(Site).filter(Site.id == payload.site_id).first()
        if not by_id:
            raise HTTPException(status_code=404, detail="Site not found")
        by_domain = db.query(Site).filter(func.lower(Site.domain) == payload.domain.lower()).first()
        if not by_domain:
            raise HTTPException(status_code=404, detail="Site (by domain) not found")
        if by_id.id != by_domain.id:
            raise HTTPException(status_code=400, detail="site_id and domain refer to different sites")
        resolved_site_id = by_id.id
    elif payload.site_id is not None:
        by_id = db.query(Site).filter(Site.id == payload.site_id).first()
        if not by_id:
            raise HTTPException(status_code=404, detail="Site not found")
        resolved_site_id = by_id.id
    elif payload.domain is not None:
        by_domain = db.query(Site).filter(func.lower(Site.domain) == payload.domain.lower()).first()
        if not by_domain:
            raise HTTPException(status_code=404, detail="Site (by domain) not found")
        resolved_site_id = by_domain.id

    return {
        "status": "accepted",
        "meta": {
            "site_id": resolved_site_id,
            "domain": payload.domain,
            "refresh_embeddings": payload.refresh_embeddings,
            "note": "Phase 9 will perform background reindex",
        },
    }


# Integrate router in app within src/main.py by including:
#   from src.api import retrieval_api
#   app.include_router(retrieval_api.router)
# Endpoints:
#   GET  /retrieval/health
#   GET  /retrieval/search?q=...&site_id=...&domain=...&top_k=10&amp;offset=0
#   POST /retrieval/reindex { "site_id": ..., "domain": "...", "refresh_embeddings": true }
