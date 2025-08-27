from typing import List, Optional, Dict, Any

import os
import traceback

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, load_only
from sqlalchemy import or_, func

from src.db.session import get_db
from src.db.models import ContentItem
# Prefer the CRUD helper; provide a safe fallback if it's unavailable
try:
    from src.db.crud.content_crud import search_content_items  # type: ignore
except Exception:  # pragma: no cover - fallback path
    def search_content_items(db, q=None, domain=None, limit=20, offset=0):
        """Fallback search using direct ORM if CRUD module isn't available.
        Returns (total, rows) similar to the real helper.
        """
        qry = db.query(ContentItem)
        if domain:
            # Join to Site if relationship/column exists; otherwise skip silently
            try:
                from src.db.models import Site  # local import to avoid circulars
                qry = qry.join(Site, ContentItem.site_id == Site.id).filter(Site.domain == domain)
            except Exception:
                pass
        if q:
            like = f"%{q}%"
            qry = qry.filter((ContentItem.title.ilike(like)) | (ContentItem.url.ilike(like)))
        total = qry.count()
        rows = qry.order_by(ContentItem.id.desc()).offset(offset).limit(limit).all()
        return total, rows

# Embedding provider (hash-based fallback if real provider is unavailable)
try:
    from src.embeddings.provider import get_provider as get_embedding_provider  # type: ignore
except Exception:
    get_embedding_provider = None  # type: ignore

router = APIRouter(prefix="/content", tags=["content"])


class _HashEmbedder:
    """Deterministic, dependency-free embedding fallback."""
    def __init__(self, dim: int = 128):
        self.dim = dim
    def _vec(self, s: str):
        # Very simple, stable hash -> pseudo-vector
        acc = [0] * self.dim
        for idx, ch in enumerate(s or ""):
            h = (ord(ch) * 1315423911 + idx * 2654435761) & 0xFFFFFFFF
            acc[h % self.dim] += ((h >> 24) & 0xFF) - 128
        # L2 normalize
        import math
        norm = math.sqrt(sum(v * v for v in acc)) or 1.0
        return [round(v / norm, 6) for v in acc]
    def embed(self, text: str):
        return self._vec(text or "")
    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]

def _resolve_embedder():
    """Return an embedder with .embed() and .embed_batch(). Honors env if provider is available."""
    # Try external provider if present
    if get_embedding_provider:
        try:
            provider = os.getenv("EMBEDDING_PROVIDER", "") or None
            dim_env = os.getenv("EMBEDDING_DIM", "")
            dim = int(dim_env) if dim_env.isdigit() else None
            prov = get_embedding_provider(provider_name=provider or None, dim_override=dim)  # type: ignore
            # Must expose embed() and embed_batch()
            if hasattr(prov, "embed") and hasattr(prov, "embed_batch"):
                return prov
        except Exception:
            # Fall through to hash fallback
            pass
    # Fallback
    dim_env = os.getenv("EMBEDDING_DIM", "")
    dim = int(dim_env) if dim_env.isdigit() else 128
    return _HashEmbedder(dim=dim)


def _serialize_item(item: ContentItem) -> Dict[str, Any]:
    """Return a safe JSON-serializable subset of ContentItem fields."""
    return {
        "id": item.id,
        "url": item.url,
        "title": item.title,
        "word_count": item.word_count,
        "schema_types": item.schema_types or [],
        "freshness_score": item.freshness_score,
        "lastmod": item.lastmod.isoformat() if getattr(item, "lastmod", None) else None,
        "date_published": item.date_published.isoformat() if getattr(item, "date_published", None) else None,
        "date_modified": item.date_modified.isoformat() if getattr(item, "date_modified", None) else None,
    }


class ReembedRequest(BaseModel):
    domain: Optional[str] = Field(default=None, description="Restrict to this site domain")
    scope: str = Field(default="missing", description="One of: 'missing', 'all', or 'single'")
    batch_size: int = Field(default=200, ge=1, le=2000)
    provider: Optional[str] = Field(default=None, description="Override provider by name (if supported)")
    url: Optional[str] = Field(default=None, description="Required if scope is 'single'")


@router.get("/health")
def health() -> Dict[str, str]:
    """Lightweight health endpoint so imports don’t crash the app."""
    return {"status": "ok"}


# Embedding info endpoint: returns provider/config/dim/sample norm without embedding any content
@router.get("/embedding-info")
def embedding_info(
    provider: Optional[str] = Query(None, description="Override provider name for inspection (does not re-embed)"),
    dim: Optional[int] = Query(None, ge=1, le=8192, description="Override embedding dimension for inspection"),
) -> Dict[str, Any]:
    """
    Returns the active embedding provider info without re-embedding any content.
    Useful for verifying environment configuration.
    """
    # Determine configured provider name (if any) and resolved embedder; allow query overrides
    configured = os.getenv("EMBEDDING_PROVIDER", "") or None
    dim_env = os.getenv("EMBEDDING_DIM", "")
    # Query param overrides take precedence over env
    requested_provider = provider or configured
    try:
        dim_override = dim if dim is not None else (int(dim_env) if dim_env.isdigit() else None)
    except Exception:
        dim_override = dim if dim is not None else None

    # Try explicit provider first if available, then fallback to resolver
    embedder = None
    provider_name = None

    if get_embedding_provider:
        try:
            prov = get_embedding_provider(provider_name=requested_provider, dim_override=dim_override)  # type: ignore
            if hasattr(prov, "embed") and hasattr(prov, "embed_batch"):
                embedder = prov
                provider_name = getattr(prov, "name", None) or requested_provider or "custom"
        except Exception:
            embedder = None

    if embedder is None:
        # Honor explicit dim override for the hash fallback
        if isinstance(dim_override, int):
            embedder = _HashEmbedder(dim=dim_override)
        else:
            embedder = _resolve_embedder()
        # Label fallback provider
        provider_name = getattr(embedder, "name", None) or ((requested_provider or configured) or "hash-fallback")

    # Determine effective dimension and sample vector norm
    try:
        # Prefer explicit .dim attribute if present
        eff_dim = getattr(embedder, "dim", None)
        if not eff_dim:
            sample_vec = embedder.embed("probe")  # type: ignore[attr-defined]
            eff_dim = len(sample_vec)
        else:
            sample_vec = embedder.embed("probe")  # type: ignore[attr-defined]
    except Exception:
        sample_vec = []
        eff_dim = None

    # Compute L2 norm of the sample embedding if available
    sample_norm = None
    if isinstance(sample_vec, list) and sample_vec:
        try:
            s = 0.0
            for v in sample_vec:
                s += float(v) * float(v)
            # Avoid sqrt import; exponent **0.5 is fine
            sample_norm = round(s ** 0.5, 6)
        except Exception:
            sample_norm = None

    return {
        "provider": provider_name,
        "configured_env": configured,
        "dim_env": dim_env or None,
        "requested_provider": provider,
        "requested_dim": dim,
        "effective_dim": eff_dim,
        "sample_norm": sample_norm,
    }


@router.get("/search")
def search(
    q: Optional[str] = Query(None, description="Search query for title/url."),
    domain: Optional[str] = Query(None, description="Filter by site domain (optional)."),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Search content items using the CRUD helper. Returns total + items."""
    # content_crud.search_content_items historically accepted (db, q, limit, offset)
    # Some versions also accept domain. Call defensively to support both.
    try:
        try:
            total, rows = search_content_items(db, q=q, domain=domain, limit=limit, offset=offset)  # type: ignore[arg-type]
        except TypeError:
            total, rows = search_content_items(db, q=q, limit=limit)  # type: ignore[misc]
        return {"total": total, "items": [_serialize_item(r) for r in rows]}
    except TypeError:
        # Retain legacy TypeError handling for backward compatibility
        total, rows = search_content_items(db, q=q, limit=limit)  # type: ignore[misc]
        return {"total": total, "items": [_serialize_item(r) for r in rows]}
    except Exception as error:
        # Log or print the error for visibility
        print(f"Error during search_content_items: {error}")
        raise HTTPException(status_code=500, detail=f"Search failed: {error}")


@router.get("/item/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = db.get(ContentItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    return _serialize_item(item)


# Developer-only debug endpoint: returns raw error details/traceback if a search fails.
# This route is enabled only when the environment variable APP_DEBUG is truthy.
@router.get("/debug/search")
def debug_search(
    q: Optional[str] = Query(None, description="Search query for title/url."),
    domain: Optional[str] = Query(None, description="Filter by site domain (optional)."),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Developer-only debug endpoint: returns raw error details/traceback if a search fails.
    This route is enabled only when the environment variable APP_DEBUG is truthy
    (e.g., '1', 'true', 'yes').
    """
    debug_on = os.getenv("APP_DEBUG", "").lower() in {"1", "true", "yes"}
    if not debug_on:
        # Hide existence of this route unless explicitly enabled
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        # Attempt the real search, mirroring /content/search behavior
        try:
            total, rows = search_content_items(db, q=q, domain=domain, limit=limit, offset=offset)  # type: ignore[arg-type]
        except TypeError:
            total, rows = search_content_items(db, q=q, limit=limit)  # type: ignore[misc]
        return {
            "ok": True,
            "total": total,
            "items": [_serialize_item(r) for r in rows],
        }
    except Exception as exc:
        tb = traceback.format_exc()
        return {
            "ok": False,
            "error": str(exc),
            "traceback": tb,
            "params": {"q": q, "domain": domain, "limit": limit, "offset": offset},
        }

@router.post("/reembed")
def reembed(req: ReembedRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    # Resolve embedder (optionally overridden provider name)
    embedder = None
    if get_embedding_provider and req.provider:
        try:
            dim_env = os.getenv("EMBEDDING_DIM", "")
            dim = int(dim_env) if dim_env.isdigit() else None
            embedder = get_embedding_provider(provider_name=req.provider, dim_override=dim)  # type: ignore
        except Exception:
            embedder = None
    if embedder is None:
        embedder = _resolve_embedder()

    # Build base query
    qry = db.query(ContentItem)
    if req.domain:
        try:
            from src.db.models import Site
            qry = qry.join(Site, ContentItem.site_id == Site.id).filter(Site.domain == req.domain)
        except Exception:
            # Silently ignore domain filter if Sites table isn't present
            pass

    if req.scope == "missing":
        # Consider NULL or empty JSON array using SQL function for robustness on Postgres
        qry = qry.filter(
            or_(
                ContentItem.embedding.is_(None),
                func.json_array_length(ContentItem.embedding) == 0,
            )
        )
    elif req.scope == "all":
        pass
    elif req.scope == "single":
        if not req.url:
            raise HTTPException(status_code=400, detail="url must be provided when scope is 'single'")
        qry = qry.filter(ContentItem.url == req.url)
    else:
        raise HTTPException(status_code=400, detail="scope must be one of: 'missing', 'all', or 'single'")

    # Load only the columns we need so we don't require optional columns that may not exist in older DBs
    qry = qry.options(load_only(ContentItem.id, ContentItem.title, ContentItem.url, ContentItem.embedding))

    total = qry.count()
    if total == 0:
        return {
            "ok": True,
            "requested_scope": req.scope,
            "domain": req.domain,
            "provider": req.provider or os.getenv("EMBEDDING_PROVIDER", "") or "hash-fallback",
            "batch_size": req.batch_size,
            "total_matched": 0,
            "updated": 0,
        }
    updated = 0

    # Stream in batches
    offset = 0
    bs = req.batch_size
    while True:
        batch = qry.order_by(ContentItem.id.asc()).offset(offset).limit(bs).all()
        if not batch:
            break
        texts = []
        for it in batch:
            # Prefer title; fall back to URL
            texts.append((it.title or "") + " " + (it.url or ""))
        # Compute embeddings
        try:
            vecs = embedder.embed_batch(texts)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Embedding provider failed: {exc}")
        # Assign and stage
        for it, vec in zip(batch, vecs):
            # Ensure Postgres JSON column receives a plain list[float]
            try:
                it.embedding = list(map(float, vec))
            except Exception:
                # As a fallback, coerce to list if vec is a numpy-like array
                it.embedding = [float(x) for x in list(vec)]
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"DB commit failed: {exc}")
        updated += len(batch)
        offset += len(batch)

    return {
        "ok": True,
        "requested_scope": req.scope,
        "domain": req.domain,
        "provider": req.provider or os.getenv("EMBEDDING_PROVIDER", "") or "hash-fallback",
        "batch_size": req.batch_size,
        "total_matched": total,
        "updated": updated,
    }