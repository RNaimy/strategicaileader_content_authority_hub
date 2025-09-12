from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Site, ContentItem, SODMetric
from src.services.sod import compute_sod_metrics_for_site

router = APIRouter()


@router.post("/sod/recompute")
def sod_recompute(
    domain: str = Query(None, description="The domain of the site"),
    site_id: int = Query(None, description="The ID of the site"),
    db: Session = Depends(get_db),
):
    # Find site by domain or site_id
    site = None
    if site_id is not None:
        site = db.query(Site).filter(Site.id == site_id).first()
    elif domain is not None:
        site = db.query(Site).filter(Site.domain == domain).first()
    else:
        raise HTTPException(status_code=400, detail="Must provide domain or site_id")
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    updated_count = compute_sod_metrics_for_site(db, site)
    return {"ok": True, "site": site.domain, "updated": updated_count}


@router.get("/sod/summary")
def sod_summary(
    domain: str = Query(None, description="The domain of the site"),
    site_id: int = Query(None, description="The ID of the site"),
    db: Session = Depends(get_db),
):
    site = None
    if site_id is not None:
        site = db.query(Site).filter(Site.id == site_id).first()
    elif domain is not None:
        site = db.query(Site).filter(Site.domain == domain).first()
    else:
        raise HTTPException(status_code=400, detail="Must provide domain or site_id")
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    sod_metrics = db.query(SODMetric).filter(SODMetric.site_id == site.id).all()
    count = len(sod_metrics)
    if count == 0:
        return {
            "site": site.domain,
            "count": 0,
            "average_overlap": None,
            "average_density": None,
        }
    avg_overlap = sum([m.overlap for m in sod_metrics]) / count
    avg_density = sum([m.density for m in sod_metrics]) / count
    return {
        "site": site.domain,
        "count": count,
        "average_overlap": avg_overlap,
        "average_density": avg_density,
    }
