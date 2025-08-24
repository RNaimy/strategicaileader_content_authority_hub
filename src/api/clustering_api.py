"""
Implements clustering APIs for content embeddings, including preview, internal links, commit, clear, and health endpoints.

Endpoints:
- GET /clusters/health: Lightweight health check for the clustering router.
- GET /clusters/preview: Run lightweight k-means clustering on content embeddings and return top-N items per cluster without committing to the database.
- GET /clusters/internal-links: Suggest internal links between similar content items based on cosine similarity.
- POST /clusters/commit: Commit cluster assignments to the database for a given domain.
- POST /clusters/clear: Clear all cluster assignments for a given domain.
"""
from typing import List, Dict, Any, Optional, Tuple, cast
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import json
import os
import traceback
from urllib.parse import urlparse

"""
Clustering API:
- /clusters/preview: Run lightweight k-means clustering on content embeddings and return top-N items per cluster
- /clusters/internal-links: Suggest internal links between similar content items based on cosine similarity
"""

# DB imports
from src.db.session import SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from src.db.models import ContentItem, Site

router = APIRouter(prefix="/clusters", tags=["clustering"])  # mounted by src/main.py

def _debug_enabled() -> bool:
    val = os.getenv("APP_DEBUG", "").lower().strip()
    return val in {"1", "true", "yes", "on"}

# ----------------------------
# Helpers (no heavy deps)
# ----------------------------

def _get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _get_site_by_domain(db: Session, domain: str):
    return db.query(Site).filter(Site.domain == domain).first()


# --- URL helpers for internal link filtering ---
def _url_path(u: str) -> str:
    try:
        p = urlparse(u)
        # Normalize: strip trailing slash except for root
        path = p.path or "/"
        if path != "/":
            path = path.rstrip("/")
        return path
    except Exception:
        return u

def _is_homepage(u: str) -> bool:
    try:
        p = urlparse(u)
        return (p.path in ("", "/")) and (not p.query) and (not p.fragment)
    except Exception:
        return False


def _l2_normalize(vec: List[float]) -> List[float]:
    s = sum((float(x) * float(x)) for x in vec)
    if s <= 0.0:
        return [0.0 for _ in vec]
    inv = 1.0 / (s ** 0.5)
    return [float(x) * inv for x in vec]

def _rows_and_vectors(rows: List[ContentItem]) -> Tuple[List[ContentItem], List[List[float]]]:
    """
    Parse each row.embedding which may be a list, tuple, JSON string, or dict, and coerce to float vectors.
    Filters out rows with missing/invalid embeddings. Pads/truncates to common dimension.
    Returns (filtered_rows, normalized_vectors).
    """
    def to_vec(val: Any) -> List[float]:
        if val is None:
            return []
        # If stored as JSON text in SQLite, decode it
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                return []
        # If stored as a dict like {"data": [...]}, extract
        if isinstance(val, dict):
            val = val.get("data", [])
        if not isinstance(val, (list, tuple)):
            return []
        out: List[float] = []
        for x in val:
            try:
                out.append(float(x))
            except Exception:
                # skip non-numeric entries
                continue
        return out

    pairs: List[Tuple[ContentItem, List[float]]] = []
    for r in rows:
        vec = to_vec(getattr(r, "embedding", None))
        if vec:
            pairs.append((r, vec))

    if not pairs:
        return [], []

    # Determine common dimension
    dim = max(len(vec) for _, vec in pairs)
    normed: List[List[float]] = []
    keep_rows: List[ContentItem] = []
    for row, vec in pairs:
        if len(vec) < dim:
            vec = vec + [0.0] * (dim - len(vec))
        elif len(vec) > dim:
            vec = vec[:dim]
        normed.append([float(v) for v in vec])
        keep_rows.append(row)
    # L2-normalize all vectors for stable cosine scoring
    normed = [_l2_normalize(v) for v in normed]
    return keep_rows, normed

def _cosine(a: List[float], b: List[float]) -> float:
    """
    Compute cosine similarity between two vectors a and b using pure Python.
    Returns a float between 0 and 1 indicating similarity.
    """
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(min(len(a), len(b))):
        ai = float(a[i])
        bi = float(b[i])
        dot += ai * bi
        na += ai * ai
        nb += bi * bi
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def _kmeans(vectors: List[List[float]], k: int, max_iter: int = 50, seed: int = 42) -> List[int]:
    """Very small KMeans (euclidean) to avoid pulling sklearn.
    Returns a list of cluster assignments same length as vectors.
    Note: This is a lightweight implementation and may not scale well for very large datasets.
    """
    import random

    if k <= 0:
        k = 1
    k = min(k, len(vectors))

    rnd = random.Random(seed)
    # init: pick k random points as centroids
    centroids = [vectors[i][:] for i in rnd.sample(range(len(vectors)), k)]

    def dist2(u: List[float], v: List[float]) -> float:
        s = 0.0
        m = min(len(u), len(v))
        for i in range(m):
            d = float(u[i]) - float(v[i])
            s += d * d
        return s

    assigns = [0] * len(vectors)
    for _ in range(max_iter):
        # assign each vector to the closest centroid
        changed = False
        for idx, vec in enumerate(vectors):
            best_c = 0
            best_d = float("inf")
            for c, cent in enumerate(centroids):
                d = dist2(vec, cent)
                if d < best_d:
                    best_d = d
                    best_c = c
            if assigns[idx] != best_c:
                assigns[idx] = best_c
                changed = True
        # recompute centroids based on assignments
        new_centroids = [[0.0 for _ in range(len(vectors[0]))] for _ in range(k)]
        counts = [0] * k
        for a, vec in zip(assigns, vectors):
            counts[a] += 1
            m = min(len(vec), len(new_centroids[a]))
            for i in range(m):
                new_centroids[a][i] += float(vec[i])
        for c in range(k):
            if counts[c] > 0:
                for i in range(len(new_centroids[c])):
                    new_centroids[c][i] /= counts[c]
            else:
                # keep old centroid if empty cluster
                new_centroids[c] = centroids[c]
        centroids = new_centroids
        if not changed:
            break
    return assigns


def _normalize_vectors(rows: List[ContentItem]) -> List[List[float]]:
    """Pad/truncate embeddings to the same dimension and ensure float lists.
    Treat None embeddings as empty lists to avoid errors.
    Superseded by _rows_and_vectors for robust parsing.
    """
    vectors = [cast(List[float], r.embedding or []) for r in rows]
    if not vectors:
        return []
    dim = max(len(v) for v in vectors)
    normed: List[List[float]] = []
    for v in vectors:
        if len(v) < dim:
            v = v + [0.0] * (dim - len(v))
        elif len(v) > dim:
            v = v[:dim]
        normed.append([float(x) for x in v])
    return normed


def _centroids(assigns: List[int], vectors: List[List[float]], k: int) -> List[List[float]]:
    if not vectors:
        return []
    dim = len(vectors[0])
    cent = [[0.0 for _ in range(dim)] for _ in range(k)]
    counts = [0] * k
    for a, vec in zip(assigns, vectors):
        counts[a] += 1
        for i in range(dim):
            cent[a][i] += vec[i]
    for c in range(k):
        if counts[c] > 0:
            for i in range(dim):
                cent[c][i] /= counts[c]
        # normalize each centroid so cosine scores are in [0,1]
        cent[c] = _l2_normalize(cent[c])
    return cent


# ----------------------------
# Response schemas
# ----------------------------

class ClusterItem(BaseModel):
    url: str
    title: Optional[str] = None
    score: Optional[float] = None

class ClusterPreview(BaseModel):
    cluster_id: int
    size: int
    items: List[ClusterItem]

class PreviewResponse(BaseModel):
    domain: str
    k: int
    total_with_embeddings: int
    k_effective: int
    embedding_dim: int
    clusters: List[ClusterPreview]

class LinkSuggestion(BaseModel):
    source_url: str
    target_url: str
    similarity: float

class LinkSuggestionsResponse(BaseModel):
    domain: str
    suggestions: List[LinkSuggestion]

class CommitRequest(BaseModel):
    domain: str
    k: int = 8
    seed: int = 42
    max_items: int = 1000

class CommitResponse(BaseModel):
    domain: str
    k: int
    updated: int
    total_with_embeddings: int

class ClearRequest(BaseModel):
    domain: str

class ClearResponse(BaseModel):
    domain: str
    cleared: int


# New response schema for cluster status
class ClusterStatusResponse(BaseModel):
    domain: str
    total_items: int
    total_with_embeddings: int
    total_with_cluster_id: int
    distinct_clusters: int
    embedding_dim: int


# ----------------------------
# Endpoints

# Health check for the clustering router
@router.get("/health")
def clusters_health():
    return {"ok": True}
# ----------------------------

# Cluster status/summary endpoint
@router.get("/status", response_model=ClusterStatusResponse)
def clusters_status(
    domain: str = Query(..., description="Site domain (e.g. strategicaileader.com)"),
    max_items: int = Query(5000, ge=1, le=20000, description="Max items to sample for embedding dimension"),
    db: Session = Depends(_get_db),
):
    """
    Lightweight status/summary for a site's clustering state.
    Reports counts and the inferred embedding dimension from current data.
    """
    try:
        site = _get_site_by_domain(db, domain)
        if not site:
            raise HTTPException(status_code=404, detail=f"Site not found for domain '{domain}'")

        total_items = (
            db.query(func.count(ContentItem.id))
            .filter(ContentItem.site_id == site.id)
            .scalar()
        ) or 0

        total_with_embeddings = (
            db.query(func.count(ContentItem.id))
            .filter(ContentItem.site_id == site.id)
            .filter(ContentItem.embedding.isnot(None))
            .scalar()
        ) or 0

        total_with_cluster_id = (
            db.query(func.count(ContentItem.id))
            .filter(ContentItem.site_id == site.id)
            .filter(ContentItem.cluster_id.isnot(None))
            .scalar()
        ) or 0

        # distinct non-null cluster ids
        distinct_clusters = (
            db.query(ContentItem.cluster_id)
            .filter(ContentItem.site_id == site.id)
            .filter(ContentItem.cluster_id.isnot(None))
            .distinct()
            .count()
        ) or 0

        # infer embedding dimension by sampling and normalizing
        sample_rows = (
            db.query(ContentItem)
            .filter(ContentItem.site_id == site.id)
            .filter(ContentItem.embedding.isnot(None))
            .limit(max_items)
            .all()
        )
        _, normed = _rows_and_vectors(sample_rows)
        embedding_dim = len(normed[0]) if normed else 0

        return ClusterStatusResponse(
            domain=domain,
            total_items=int(total_items),
            total_with_embeddings=int(total_with_embeddings),
            total_with_cluster_id=int(total_with_cluster_id),
            distinct_clusters=int(distinct_clusters),
            embedding_dim=embedding_dim,
        )
    except HTTPException:
        raise
    except Exception as e:
        if _debug_enabled():
            tb = "\n".join(traceback.format_exception_only(type(e), e)).strip()
            tb_tail = "\n".join(traceback.format_exc().splitlines()[-6:])
            raise HTTPException(status_code=500, detail=f"clusters_status error: {tb}\n{tb_tail}")
        raise HTTPException(status_code=500, detail="Internal error while fetching clustering status. Enable APP_DEBUG=1 for details.")
# ----------------------------

#
# Preview clusters without committing to DB
@router.get("/preview", response_model=PreviewResponse)
def preview_clusters(
    domain: str = Query(..., description="Site domain to cluster (e.g. strategicaileader.com)"),
    k: int = Query(8, ge=1, le=50, description="Number of clusters (default 8)"),
    top_n: int = Query(5, ge=1, le=50, description="Top items to show per cluster"),
    max_items: int = Query(800, ge=1, le=5000, description="Max items to load (protects memory)"),
    db: Session = Depends(_get_db),
):
    try:
        site = _get_site_by_domain(db, domain)
        if not site:
            raise HTTPException(status_code=404, detail=f"Site not found for domain '{domain}'")

        rows = (
            db.query(ContentItem)
            .filter(ContentItem.site_id == site.id)
            .filter(ContentItem.embedding.isnot(None))
            .limit(max_items)
            .all()
        )
        rows, normed = _rows_and_vectors(rows)
        if not rows or not normed:
            raise HTTPException(
                status_code=400,
                detail=("No valid embeddings found for this domain. Ensure 'embedding' contains numeric arrays."),
            )

        assigns = _kmeans(normed, k=k)
        k_eff = (max(assigns) + 1) if assigns else 0
        if k_eff == 0:
            raise HTTPException(status_code=400, detail="Clustering produced zero clusters (no data)")
        dim = len(normed[0]) if normed else 0

        buckets: Dict[int, List[Tuple[float, ContentItem]]] = {i: [] for i in range(k_eff)}
        counts = [0] * k_eff
        for a in assigns:
            counts[a] += 1

        cent = _centroids(assigns, normed, k_eff)

        for a, vec, row in zip(assigns, normed, rows):
            sim = _cosine(vec, cent[a]) if counts[a] > 0 else 0.0
            buckets.setdefault(a, []).append((sim, row))

        clusters: List[ClusterPreview] = []
        for cid, items in buckets.items():
            items.sort(key=lambda t: t[0], reverse=True)
            top = [
                ClusterItem(url=it.url, title=it.title, score=round(score, 3))
                for score, it in items[:top_n]
            ]
            clusters.append(ClusterPreview(cluster_id=cid, size=len(items), items=top))

        clusters.sort(key=lambda c: c.size, reverse=True)

        return PreviewResponse(
            domain=domain,
            k=k,
            total_with_embeddings=len(rows),
            k_effective=k_eff,
            embedding_dim=dim,
            clusters=clusters,
        )
    except HTTPException:
        # re-raise FastAPI errors as-is
        raise
    except Exception as e:
        if _debug_enabled():
            tb = "\n".join(traceback.format_exception_only(type(e), e)).strip()
            tb_tail = "\n".join(traceback.format_exc().splitlines()[-6:])
            raise HTTPException(status_code=500, detail=f"preview_clusters error: {tb}\n{tb_tail}")
        raise HTTPException(status_code=500, detail="Internal error while generating preview. Enable APP_DEBUG=1 for details.")


#
# Suggest internal links between similar content items
@router.get("/internal-links", response_model=LinkSuggestionsResponse)
def internal_link_suggestions(
    domain: str = Query(..., description="Site domain (e.g. strategicaileader.com)"),
    per_item: int = Query(3, ge=1, le=10, description="Max suggestions per source"),
    min_sim: float = Query(0.45, ge=0.0, le=1.0, description="Cosine similarity threshold"),
    max_items: int = Query(1000, ge=2, le=5000, description="Max items to load for similarity graph"),
    fallback_when_empty: bool = Query(False, description="If no neighbors meet min_sim, still return the top per_item by similarity"),
    db: Session = Depends(_get_db),
):
    try:
        site = _get_site_by_domain(db, domain)
        if not site:
            raise HTTPException(status_code=404, detail=f"Site not found for domain '{domain}'")

        rows = (
            db.query(ContentItem)
            .filter(ContentItem.site_id == site.id)
            .filter(ContentItem.embedding.isnot(None))
            .limit(max_items)
            .all()
        )
        rows, vecs = _rows_and_vectors(rows)
        if len(rows) < 2 or not vecs:
            raise HTTPException(status_code=400, detail="Need at least 2 items with valid embeddings to suggest links.")

        suggestions: List[LinkSuggestion] = []
        # vecs from _rows_and_vectors are already L2-normalized
        for i, src in enumerate(rows):
            sims: List[Tuple[float, int]] = []
            for j, tgt in enumerate(rows):
                if i == j:
                    continue
                # Skip same-path pairs and homepage targets to avoid useless links
                if _url_path(rows[i].url) == _url_path(rows[j].url):
                    continue
                if _is_homepage(rows[j].url):
                    continue
                s = _cosine(vecs[i], vecs[j])
                sims.append((s, j))

            # Sort once, then filter by threshold
            sims.sort(reverse=True, key=lambda t: t[0])
            above = [(s, j) for (s, j) in sims if s >= min_sim]

            chosen = above[:per_item]
            if not chosen and fallback_when_empty:
                # Nothing cleared the bar: fall back to top-N regardless of threshold
                chosen = sims[:per_item]

            for s, j in chosen:
                if (not fallback_when_empty) and (s < min_sim):
                    continue
                suggestions.append(
                    LinkSuggestion(
                        source_url=src.url,
                        target_url=rows[j].url,
                        similarity=round(s, 3),
                    )
                )

        return LinkSuggestionsResponse(domain=domain, suggestions=suggestions)
    except HTTPException:
        raise
    except Exception as e:
        if _debug_enabled():
            tb = "\n".join(traceback.format_exception_only(type(e), e)).strip()
            tb_tail = "\n".join(traceback.format_exc().splitlines()[-6:])
            raise HTTPException(status_code=500, detail=f"internal_link_suggestions error: {tb}\n{tb_tail}")
        raise HTTPException(status_code=500, detail="Internal error while generating link suggestions. Enable APP_DEBUG=1 for details.")


#
# Commit cluster assignments to the database
@router.post("/commit", response_model=CommitResponse)
def commit_clusters(payload: CommitRequest, db: Session = Depends(_get_db)):
    """
    Run k-means clustering on content embeddings for a domain and commit
    cluster assignments to the database. Returns the count of updated items.
    """
    try:
        site = _get_site_by_domain(db, payload.domain)
        if not site:
            raise HTTPException(status_code=404, detail=f"Site not found for domain '{payload.domain}'")

        rows = (
            db.query(ContentItem)
            .filter(ContentItem.site_id == site.id)
            .filter(ContentItem.embedding.isnot(None))
            .limit(payload.max_items)
            .all()
        )
        rows, normed = _rows_and_vectors(rows)
        if not rows or not normed:
            raise HTTPException(status_code=400, detail="No valid embeddings found; cannot commit clusters.")

        assigns = _kmeans(normed, k=payload.k, seed=payload.seed)

        # Ensure the DB has a 'cluster_id' column before attempting to write
        from sqlalchemy import inspect as _sa_inspect
        try:
            inspector = _sa_inspect(db.get_bind())
            cols = {c["name"] for c in inspector.get_columns("content_items")}
            if "cluster_id" not in cols:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Cannot commit clusters: 'cluster_id' column is missing in 'content_items'. "
                        "Add it via migration (e.g., Alembic) before committing."
                    ),
                )
        except HTTPException:
            raise
        except Exception as e:  # pragma: no cover - very unlikely
            if _debug_enabled():
                raise HTTPException(status_code=500, detail=f"Schema inspection failed: {e}")
            raise HTTPException(
                status_code=500,
                detail="Could not verify schema for 'content_items'. Ensure 'cluster_id' column exists.",
            )

        # Prepare bulk update mappings (only changed rows)
        updates = []
        for idx, row in enumerate(rows):
            if idx >= len(assigns):
                break
            cid = int(assigns[idx])
            if row.cluster_id != cid:
                updates.append({"id": row.id, "cluster_id": cid})

        updated = 0
        if updates:
            try:
                # Use bulk_update_mappings for efficiency
                db.bulk_update_mappings(ContentItem, updates)
                db.commit()
                updated = len(updates)
            except SQLAlchemyError as e:
                db.rollback()
                if _debug_enabled():
                    raise HTTPException(status_code=500, detail=f"Commit failed: {e}")
                raise HTTPException(status_code=500, detail="Failed to commit cluster assignments to the database.")
        else:
            # Nothing changed; still ensure session is clean
            db.flush()

        return CommitResponse(domain=payload.domain, k=payload.k, updated=updated, total_with_embeddings=len(rows))
    except HTTPException:
        raise
    except Exception as e:
        # Catch-all to avoid leaking tracebacks unless APP_DEBUG=1
        if _debug_enabled():
            tb = "\n".join(traceback.format_exception_only(type(e), e)).strip()
            tb_tail = "\n".join(traceback.format_exc().splitlines()[-6:])
            raise HTTPException(status_code=500, detail=f"commit_clusters error: {tb}\n{tb_tail}")
        raise HTTPException(status_code=500, detail="Internal error while committing clusters. Enable APP_DEBUG=1 for details.")


#
# Clear all cluster assignments for a domain
@router.post("/clear", response_model=ClearResponse)
def clear_clusters(payload: ClearRequest, db: Session = Depends(_get_db)):
    """
    Clear all cluster assignments for content items within a specified domain.
    Returns the number of items cleared.
    """
    site = _get_site_by_domain(db, payload.domain)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site not found for domain '{payload.domain}'")

    rows = (
        db.query(ContentItem)
        .filter(ContentItem.site_id == site.id)
        .filter(ContentItem.cluster_id.isnot(None))
        .all()
    )
    cleared = 0
    for row in rows:
        row.cluster_id = None
        cleared += 1
    if cleared:
        db.commit()

    return ClearResponse(domain=payload.domain, cleared=cleared)
