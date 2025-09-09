from fastapi import APIRouter
from pydantic import BaseModel
from src.services.authority import compute_authority_signals
from datetime import datetime

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
            item = db.query(ContentItem).filter(ContentItem.id == payload.content_item_id).first()
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
