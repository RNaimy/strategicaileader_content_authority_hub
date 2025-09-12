from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re

# Reuse the same DB patterns used elsewhere in the app
# (graph APIs use src.db + src.models, so do the same here)
from src.db.session import get_session
from src.db.models import Site, ContentItem

# ContentChunk may or may not exist yet (depending on migrations)
try:
    from src.db.models import ContentChunk  # type: ignore
    HAS_CONTENT_CHUNK = True
except Exception:
    ContentChunk = None  # type: ignore
    HAS_CONTENT_CHUNK = False

router = APIRouter()

# ---------------------------
# Request/Response models
# ---------------------------
class ChunkRequest(BaseModel):
    domain: str
    chunk_sizes: List[int] = [800]
    overwrite: bool = False

class ScoreRequest(BaseModel):
    domain: str
    include_extractability: bool = True

# ---------------------------
# Helpers
# ---------------------------
_WORD_RE = re.compile(r"\w+")

def _get_site(db, domain: str) -> Optional[Site]:
    return db.query(Site).filter(Site.domain == domain).first()

def _item_text(item: ContentItem) -> str:
    # Best-effort across common fields
    for attr in ("content_text", "text", "extracted_text", "html_text", "body", "html"):
        if hasattr(item, attr):
            val = getattr(item, attr)
            if val:
                return str(val)
    # Fallback: title + url
    parts = [item.title or "", item.url or ""]
    return "\n".join([p for p in parts if p]).strip()

def _simple_tokenize(t: str) -> List[str]:
    return [w for w in _WORD_RE.findall(t.lower()) if w]

def _chunk_text(text: str, target: int) -> List[str]:
    tokens = _simple_tokenize(text)
    if not tokens:
        return []
    chunks: List[str] = []
    step = max(50, target)  # guard against tiny sizes
    for i in range(0, len(tokens), step):
        chunk_tokens = tokens[i:i + step]
        chunks.append(" ".join(chunk_tokens))
    return chunks

def _density_score(chunk: str) -> float:
    toks = _simple_tokenize(chunk)
    if not toks:
        return 0.0
    uniq = len(set(toks))
    return round(uniq / max(1, len(toks)), 3)

def _extractability_score(chunk: str) -> float:
    # Heuristic: sufficient length + sentence-like ending + structured hints
    length_ok = 60 <= len(chunk) <= 1200
    good_end = bool(re.search(r"[\.!?]$", chunk.strip()))
    has_lists = any(sym in chunk for sym in [":", "- ", "•", "\n-", "\n*", "\n1."])
    score = 0.0
    score += 0.4 if length_ok else 0.0
    score += 0.4 if good_end else 0.0
    score += 0.2 if has_lists else 0.0
    return round(score, 3)

# ---------------------------
# Routes
# ---------------------------
@router.post("/content/chunk")
def chunk_content(payload: ChunkRequest) -> Dict[str, Any]:
    with get_session() as db:
        site = _get_site(db, payload.domain)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")

        items: List[ContentItem] = db.query(ContentItem).filter(ContentItem.site_id == site.id).all()
        if not items:
            return {"ok": True, "domain": payload.domain, "chunked": 0, "persisted": False, "message": "No content items"}

        # If there is no ContentChunk model/table yet, compute counts only (no writes)
        if not HAS_CONTENT_CHUNK:
            total_chunks = 0
            for it in items:
                text = _item_text(it)
                for size in payload.chunk_sizes:
                    total_chunks += len(_chunk_text(text, size))
            return {
                "ok": True,
                "domain": payload.domain,
                "chunked": total_chunks,
                "persisted": False,
                "message": "ContentChunk model/table not available; returning counts only."
            }

        # Persist chunks (overwrite = delete then recreate)
        chunked = 0
        primary_size = payload.chunk_sizes[0] if payload.chunk_sizes else 800
        for it in items:
            text = _item_text(it)
            if not text:
                continue
            if payload.overwrite:
                db.query(ContentChunk).filter(ContentChunk.content_item_id == it.id).delete()
            parts = _chunk_text(text, primary_size)
            for idx, ch in enumerate(parts):
                # Insert via SQLAlchemy Core to match actual table columns
                tok_count = len(_simple_tokenize(ch))
                values = {
                    "site_id": site.id,
                    "content_item_id": it.id,
                    "chunk_order": idx,      # matches DB schema
                    "text": ch,
                    "token_count": tok_count,
                    "created_at": datetime.utcnow(),
                }
                db.execute(ContentChunk.__table__.insert().values(**values))
                chunked += 1
        db.commit()
        return {"ok": True, "domain": payload.domain, "chunked": chunked, "persisted": True}

@router.post("/semantic/score")
def semantic_score(payload: ScoreRequest) -> Dict[str, Any]:
    with get_session() as db:
        site = _get_site(db, payload.domain)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")

        if not HAS_CONTENT_CHUNK:
            return {"ok": False, "detail": "ContentChunk model/table not available; run migrations for Phase 10."}

        chunks: List[ContentChunk] = (
            db.query(ContentChunk)
            .join(ContentItem, ContentItem.id == ContentChunk.content_item_id)
            .filter(ContentItem.site_id == site.id)
            .all()
        )
        if not chunks:
            return {"ok": True, "scored": 0, "message": "No chunks found; run /content/chunk first."}

        scored = 0
        for ch in chunks:
            text = ch.text or ""
            d = _density_score(text)
            # Placeholder overlap (until GSC join is wired). Keep deterministic mid value.
            o = 0.5
            e = _extractability_score(text) if payload.include_extractability else None

            # Assign only if fields exist to avoid AttributeError on older schemas
            if hasattr(ch, "density_score"):
                setattr(ch, "density_score", d)
            if hasattr(ch, "overlap_score"):
                setattr(ch, "overlap_score", o)
            if e is not None and hasattr(ch, "extractability_score"):
                setattr(ch, "extractability_score", e)
            if hasattr(ch, "last_scored_at"):
                setattr(ch, "last_scored_at", datetime.utcnow())
            scored += 1
        db.commit()
        return {"ok": True, "domain": payload.domain, "scored": scored}

@router.get("/semantic/page/{item_id}")
def semantic_page(item_id: int = Path(..., ge=1)) -> Dict[str, Any]:
    with get_session() as db:
        it: Optional[ContentItem] = db.query(ContentItem).get(item_id)
        if not it:
            raise HTTPException(status_code=404, detail="Page not found")

        result: Dict[str, Any] = {"id": it.id, "url": it.url, "title": it.title or ""}
        if HAS_CONTENT_CHUNK:
            rows = db.query(ContentChunk).filter(ContentChunk.content_item_id == it.id).order_by(ContentChunk.chunk_index.asc()).all()
            chunks_out: List[Dict[str, Any]] = []
            for r in rows:
                row_out = {
                    "chunk_index": getattr(r, "chunk_index", None),
                    "tokens": getattr(r, "tokens", None),
                    "density_score": getattr(r, "density_score", None) if hasattr(r, "density_score") else None,
                    "overlap_score": getattr(r, "overlap_score", None) if hasattr(r, "overlap_score") else None,
                    "extractability_score": getattr(r, "extractability_score", None) if hasattr(r, "extractability_score") else None,
                }
                chunks_out.append(row_out)
            result["chunks"] = chunks_out
        else:
            result["chunks"] = []
        return result

@router.get("/semantic/dashboard")
def semantic_dashboard(domain: str = Query(...)) -> Dict[str, Any]:
    with get_session() as db:
        site = _get_site(db, domain)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")

        pages_out: List[Dict[str, Any]] = []
        items: List[ContentItem] = db.query(ContentItem).filter(ContentItem.site_id == site.id).all()
        for it in items:
            page = {"id": it.id, "url": it.url, "title": it.title or ""}
            # include page-level aggregates if schema has them
            for fld in ("avg_overlap_score", "avg_density_score"):
                if hasattr(it, fld):
                    page[fld] = getattr(it, fld)
            pages_out.append(page)

        quick_wins: List[Dict[str, Any]] = []
        if HAS_CONTENT_CHUNK:
            rows = (
                db.query(ContentChunk, ContentItem)
                .join(ContentItem, ContentItem.id == ContentChunk.content_item_id)
                .filter(ContentItem.site_id == site.id)
                .all()
            )
            for ch, it in rows:
                d = getattr(ch, "density_score", None)
                o = getattr(ch, "overlap_score", None)
                if d is None or o is None:
                    continue
                # Heuristics from the Phase 10 doc:
                if o >= 0.6 and d < 0.35:
                    quick_wins.append({"url": it.url, "title": it.title or "", "reason": "High overlap, low density"})
                if d >= 0.6 and o < 0.35:
                    quick_wins.append({"url": it.url, "title": it.title or "", "reason": "High density, low overlap"})

        return {"pages": pages_out, "quick_wins": quick_wins}
