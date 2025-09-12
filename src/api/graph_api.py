from fastapi import APIRouter
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from src.db import get_session
from src.models import ContentItem, ContentLink

router = APIRouter()

def _build_graph(db: Session) -> Dict[str, Any]:
    # Nodes: every content item
    items: List[ContentItem] = db.query(ContentItem).all()
    id_by_url = {it.url: it.id for it in items}
    nodes = [{"id": it.id, "url": it.url, "title": it.title or ""} for it in items]

    # Edges: internal links; include to_url passthrough for unresolved targets
    links: List[ContentLink] = db.query(ContentLink).all()
    edges: List[Dict[str, Any]] = []
    for lk in links:
        if not lk.from_content_id:
            continue
        target: Optional[int] = lk.to_content_id if lk.to_content_id else id_by_url.get(lk.to_url)
        edge = {
            "source": lk.from_content_id,
            "target": target,
            "to_url": lk.to_url,
            "rel": lk.rel or "",
            "nofollow": bool(lk.nofollow),
        }
        edges.append(edge)

    meta = {"nodes": len(nodes), "edges": len(edges)}
    return {"nodes": nodes, "edges": edges, "meta": meta}

# Simple in-memory cache
_GRAPH_CACHE: Dict[str, Any] = {"nodes": [], "edges": [], "meta": {"nodes": 0, "edges": 0}}

@router.post("/graph/recompute")
def graph_recompute() -> Dict[str, Any]:
    with get_session() as db:
        result = _build_graph(db)
    _GRAPH_CACHE.update(result)
    return {"ok": True, "meta": result["meta"]}

@router.get("/graph/export")
def graph_export() -> Dict[str, Any]:
    # Build on the fly if cache is empty
    if not _GRAPH_CACHE["nodes"]:
        with get_session() as db:
            result = _build_graph(db)
        _GRAPH_CACHE.update(result)
    return _GRAPH_CACHE
