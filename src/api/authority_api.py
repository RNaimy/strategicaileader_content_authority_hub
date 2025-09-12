from fastapi import APIRouter, Query, HTTPException
import traceback
from pydantic import BaseModel
from src.services.authority import compute_authority_signals
from datetime import datetime

# DB/model imports for new endpoints
from src.db.session import SessionLocal
from src.db.models import ContentLink, GraphMetric, Site, ContentItem

router = APIRouter()


class AnalyzeRequest(BaseModel):
    url: str | None = None
    html: str | None = None
    text: str | None = None
    persist: bool = False
    content_item_id: int | None = None


class BatchRequest(BaseModel):
    urls: list[str]
    persist: bool = False


@router.get("/health")
def health():
    return {"ok": True, "phase": 7, "service": "authority-signals"}


@router.post("/signals")
def signals(payload: AnalyzeRequest):
    content = payload.text or payload.html or ""
    result = compute_authority_signals(content)
    # Persist logic
    if payload.persist and payload.content_item_id is not None:
        try:
            from src.db.session import SessionLocal
            from src.db.models import ContentItem

            db = SessionLocal()
            item = (
                db.query(ContentItem)
                .filter(ContentItem.id == payload.content_item_id)
                .first()
            )
            if item:
                item.authority_expertise = result.get("expertise")
                item.authority_experience = result.get("experience")
                item.authority_trust = result.get("trust")
                item.authority_evidence = result.get("evidence")
                item.authority_clarity = result.get("clarity")
                item.authority_engagement = result.get("engagement")
                item.authority_last_scored_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        finally:
            try:
                db.close()
            except Exception:
                pass
    return {"signals": result}


@router.post("/score/batch")
def score_batch(payload: BatchRequest):
    results = []
    for url in payload.urls:
        # TODO: replace with real fetcher
        html = f"<html><body><p>Stub fetch for {url}</p></body></html>"
        signals = compute_authority_signals(html)
        results.append({"url": url, "signals": signals})
    return {"results": results}


# --- New Endpoints ---


@router.post("/graph/recompute")
def graph_recompute(domain: str = Query(...)):
    db = SessionLocal()
    try:
        site = db.query(Site).filter(Site.domain == domain).first()
        if not site:
            return {"detail": "Site not found"}

        # Count edges scoped to this site
        edges = (
            db.query(ContentLink)
            .join(ContentItem, ContentItem.id == ContentLink.from_content_id)
            .filter(ContentItem.site_id == site.id)
            .count()
        )

        # Count all content items belonging to this site (includes orphans)
        nodes = db.query(ContentItem).filter(ContentItem.site_id == site.id).count()

        return {"ok": True, "site": site.domain, "nodes": nodes, "edges": edges}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
    finally:
        db.close()



@router.get("/graph/export")
def graph_export(domain: str = Query(...)):
    db = SessionLocal()
    try:
        site = db.query(Site).filter(Site.domain == domain).first()
        if not site:
            return {"detail": "Site not found"}

        # Site-scoped items (nodes)
        items = db.query(ContentItem).filter(ContentItem.site_id == site.id).all()
        nodes = [{"id": it.id, "url": it.url, "title": it.title or ""} for it in items]

        # Build lookup maps for resolving edges
        from urllib.parse import urlparse
        id_by_url = {it.url: it.id for it in items}
        id_by_path = {}
        for it in items:
            try:
                p = urlparse(it.url)
                if p.path:
                    id_by_path[p.path] = it.id
            except Exception:
                pass

        # Site-scoped links (edges)
        links = (
            db.query(ContentLink)
            .join(ContentItem, ContentItem.id == ContentLink.from_content_id)
            .filter(ContentItem.site_id == site.id)
            .all()
        )

        edges = []
        for link in links:
            target_id = link.to_content_id
            if target_id is None:
                # Try resolving by absolute URL first
                if link.to_url and link.to_url in id_by_url:
                    target_id = id_by_url[link.to_url]
                else:
                    # Try resolving by path (e.g., "/pillar")
                    try:
                        if link.to_url and link.to_url in id_by_path:
                            target_id = id_by_path[link.to_url]
                    except Exception:
                        pass

            edges.append(
                {
                    "id": link.id,
                    "from_content_id": link.from_content_id,
                    "to_content_id": target_id,
                    "to_url": link.to_url,
                    "anchor_text": link.anchor_text,
                }
            )

        meta = {"nodes": len(nodes), "edges": len(edges)}
        return {"site": site.domain, "nodes": nodes, "edges": edges, "meta": meta}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
    finally:
        db.close()
