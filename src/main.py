from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI
from fastapi import Query, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db.models import ImprovementRecommendation
from src.db.session import get_db

from src.services.improvement import recompute_recommendations

from sqlalchemy import text

from src.db.session import get_session
from src.db_init import init_db

from datetime import datetime

# Import routers from the API package. Use try/except for optional ones so the app
# still boots even if a module is temporarily missing during development.
from src.api import clustering_router, content_router  # type: ignore

try:
    from src.api import inventory_router  # type: ignore
except Exception:  # pragma: no cover
    inventory_router = None  # type: ignore[assignment]

try:
    from src.api import scraper_router  # type: ignore
except Exception:  # pragma: no cover
    scraper_router = None  # type: ignore[assignment]


app = FastAPI(
    title="Content Authority Hub",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)


@app.on_event("startup")
def _startup() -> None:
    """Initialize the database on startup."""
    init_db()


@app.get("/")
def root() -> dict:
    routers: List[str] = ["/clusters", "/content"]
    if inventory_router is not None:
        routers.append("/inventory")
    if scraper_router is not None:
        routers.append("/scraper")
    return {
        "service": "Content Authority Hub",
        "routers": routers,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict:
    ok_db = False
    try:
        with get_session() as s:
            ok_db = s.execute(text("select 1")).scalar() == 1
    except Exception:
        ok_db = False
    return {"ok": True, "db": ok_db}


# Improvement Recommendation Endpoints
class ImprovementRecOut(BaseModel):
    id: int
    site_id: int
    content_item_id: Optional[int] = None
    flag: str
    score: Optional[float] = None
    rationale: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


@app.get("/improvement/quick_wins", response_model=List[ImprovementRecOut])
def get_quick_wins(
    site_id: int = Query(..., description="Site ID to scope results"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(ImprovementRecommendation)
        .filter(ImprovementRecommendation.site_id == site_id)
        .filter(ImprovementRecommendation.flag == "quick_win")
        .order_by(ImprovementRecommendation.score.desc().nullslast())
        .limit(limit)
    )
    return q.all()


@app.get("/improvement/content_at_risk", response_model=List[ImprovementRecOut])
def get_content_at_risk(
    site_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(ImprovementRecommendation)
        .filter(ImprovementRecommendation.site_id == site_id)
        .filter(ImprovementRecommendation.flag == "at_risk")
        .order_by(ImprovementRecommendation.score.desc().nullslast())
        .limit(limit)
    )
    return q.all()


@app.get("/improvement/topics_emerging", response_model=List[ImprovementRecOut])
def get_topics_emerging(
    site_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(ImprovementRecommendation)
        .filter(ImprovementRecommendation.site_id == site_id)
        .filter(ImprovementRecommendation.flag == "emerging_topic")
        .order_by(ImprovementRecommendation.score.desc().nullslast())
        .limit(limit)
    )
    return q.all()


# Router mounting
@app.post("/improvement/recompute")
def recompute(
    site_id: int = Query(..., description="Site ID to recompute recommendations for"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Dev helper: recompute Phase 9 recommendations and return a summary.
    """
    summary = recompute_recommendations(db, site_id=site_id, limit=limit)
    return {"site_id": site_id, "written": summary}

app.include_router(clustering_router)
app.include_router(content_router)
if inventory_router is not None:
    app.include_router(inventory_router)
if scraper_router is not None:
    app.include_router(scraper_router)