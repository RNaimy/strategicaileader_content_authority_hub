from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from src.db.session import get_db
from src.db.models import Site, ContentItem, ContentLink, ImprovementRecommendation

router = APIRouter(prefix="/improvement", tags=["improvement"])


def _normalize_domain(domain: str) -> str:
    """
    Best-effort normalization: strip scheme and leading www.
    """
    d = domain.strip().lower()
    for prefix in ("http://", "https://"):
        if d.startswith(prefix):
            d = d[len(prefix) :]
    if d.startswith("www."):
        d = d[4:]
    # trim any trailing slash
    return d.rstrip("/")


def _resolve_site(db: Session, domain: Optional[str], site_id: Optional[int]) -> Site:
    """
    Allow clients to pass either ?domain=... or ?site_id=...
    """
    if site_id is not None:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            raise HTTPException(
                status_code=404, detail=f"Site not found for id '{site_id}'"
            )
        return site

    if domain:
        norm = _normalize_domain(domain)
        site = db.query(Site).filter(Site.domain == norm).first()
        if not site:
            raise HTTPException(
                status_code=404, detail=f"Site not found for domain '{norm}'"
            )
        return site

    raise HTTPException(status_code=422, detail="Provide either 'domain' or 'site_id'.")


def _item_lookup(db: Session, ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not ids:
        return {}
    rows = (
        db.query(ContentItem.id, ContentItem.url, ContentItem.title)
        .filter(ContentItem.id.in_(ids))
        .all()
    )
    return {rid: {"url": url, "title": title} for rid, url, title in rows}


@router.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@router.post("/recompute")
def recompute_improvements(
    domain: Optional[str] = Query(
        None, description="Domain, e.g. strategicaileader.com"
    ),
    site_id: Optional[int] = Query(None, description="Alternative to domain"),
    limit: int = Query(1000, ge=1, le=10000),
    min_outbound: int = Query(2, ge=0, le=20),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Very lightweight heuristic 'recompute':
      - flags content with low outbound internal links as quick internal-link wins
      - flags content with missing freshness metadata as 'content_at_risk'
      - configurable threshold via min_outbound (default 2)
    """
    site = _resolve_site(db, domain, site_id)

    # Gather all items for the site
    items: List[ContentItem] = (
        db.query(ContentItem)
        .filter(ContentItem.site_id == site.id)
        .order_by(ContentItem.id.asc())
        .limit(limit)
        .all()
    )

    # Clear previous auto-generated recommendations for flags we own.
    # Our schema doesn't have a separate `source` column; we use the `flag` to scope.
    db.query(ImprovementRecommendation).filter(
        ImprovementRecommendation.site_id == site.id,
        ImprovementRecommendation.flag.in_(["internal_links", "content_at_risk"]),
    ).delete(synchronize_session=False)

    created = 0

    # Compute simple outbound counts for internal links per content item
    outbound_counts = dict(
        db.query(ContentLink.from_content_id, func.count(ContentLink.id))
        .filter(
            ContentLink.from_content_id.in_([i.id for i in items]),
            ContentLink.is_internal == True,  # only internal links
        )
        .group_by(ContentLink.from_content_id)
        .all()
    )

    for item in items:
        out_ct = int(outbound_counts.get(item.id, 0))

        # Heuristic 1: quick win on internal links if fewer than min_outbound outbound internal links
        if out_ct < min_outbound:
            needed = max(min_outbound - out_ct, 0)
            rec = ImprovementRecommendation(
                site_id=site.id,
                content_item_id=item.id,
                flag="internal_links",
                score=0.7,  # arbitrary demo score
                rationale={
                    "message": f"Add {needed} more internal link(s) from this page to closely related topics.",
                    "source": "heuristic",
                    "extra": {"current_outbound": out_ct, "target_min": min_outbound},
                },
            )
            db.add(rec)
            created += 1

        # Heuristic 2: content at risk if missing freshness_score/lastmod
        if (
            getattr(item, "freshness_score", None) is None
            and getattr(item, "lastmod", None) is None
        ):
            rec = ImprovementRecommendation(
                site_id=site.id,
                content_item_id=item.id,
                flag="content_at_risk",
                score=0.5,
                rationale={
                    "message": "Missing recency signals (lastmod/freshness). Consider updating or annotating.",
                    "source": "heuristic",
                    "extra": {
                        "freshness_score": getattr(item, "freshness_score", None),
                        "lastmod": getattr(item, "lastmod", None),
                    },
                },
            )
            db.add(rec)
            created += 1

    db.commit()

    return {
        "ok": True,
        "site": site.domain,
        "created": created,
        "total_items_scored": len(items),
    }


@router.get("/quick_wins")
def quick_wins(
    domain: Optional[str] = Query(None),
    site_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    include_item: bool = Query(
        False, description="If true, include url/title for each content item"
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return top internal-linking opportunities produced by recompute().
    """
    site = _resolve_site(db, domain, site_id)
    rows = (
        db.query(ImprovementRecommendation)
        .filter(
            ImprovementRecommendation.site_id == site.id,
            ImprovementRecommendation.flag == "internal_links",
        )
        .order_by(
            ImprovementRecommendation.score.desc().nullslast(),
            ImprovementRecommendation.id.asc(),
        )
        .limit(limit)
        .all()
    )

    item_meta: Dict[int, Dict[str, Any]] = {}
    if include_item:
        item_meta = _item_lookup(
            db, [r.content_item_id for r in rows if r.content_item_id]
        )

    def _row(r: ImprovementRecommendation) -> Dict[str, Any]:
        rationale = r.rationale or {}
        return {
            "id": r.id,
            "content_item_id": r.content_item_id,
            "flag": r.flag,
            "message": rationale.get("message"),
            "score": r.score,
            "extra": rationale.get("extra"),
            "source": rationale.get("source"),
            "item": item_meta.get(r.content_item_id) if include_item else None,
        }

    return {
        "site": site.domain,
        "total": len(rows),
        "items": [_row(r) for r in rows],
    }


@router.get("/content_at_risk")
def content_at_risk(
    domain: Optional[str] = Query(None),
    site_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    include_item: bool = Query(
        False, description="If true, include url/title for each content item"
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return 'content at risk' findings produced by recompute().
    """
    site = _resolve_site(db, domain, site_id)
    rows = (
        db.query(ImprovementRecommendation)
        .filter(
            ImprovementRecommendation.site_id == site.id,
            ImprovementRecommendation.flag == "content_at_risk",
        )
        .order_by(
            ImprovementRecommendation.score.desc().nullslast(),
            ImprovementRecommendation.id.asc(),
        )
        .limit(limit)
        .all()
    )

    item_meta: Dict[int, Dict[str, Any]] = {}
    if include_item:
        item_meta = _item_lookup(
            db, [r.content_item_id for r in rows if r.content_item_id]
        )

    def _row(r: ImprovementRecommendation) -> Dict[str, Any]:
        rationale = r.rationale or {}
        return {
            "id": r.id,
            "content_item_id": r.content_item_id,
            "flag": r.flag,
            "message": rationale.get("message"),
            "score": r.score,
            "extra": rationale.get("extra"),
            "source": rationale.get("source"),
            "item": item_meta.get(r.content_item_id) if include_item else None,
        }

    return {
        "site": site.domain,
        "total": len(rows),
        "items": [_row(r) for r in rows],
    }


@router.get("/summary")
def improvement_summary(
    domain: Optional[str] = Query(None),
    site_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return counts of recommendations by flag for the given site.
    """
    site = _resolve_site(db, domain, site_id)
    # total count
    total = (
        db.query(func.count(ImprovementRecommendation.id))
        .filter(ImprovementRecommendation.site_id == site.id)
        .scalar()
        or 0
    )
    # counts by flag
    rows = (
        db.query(
            ImprovementRecommendation.flag, func.count(ImprovementRecommendation.id)
        )
        .filter(ImprovementRecommendation.site_id == site.id)
        .group_by(ImprovementRecommendation.flag)
        .all()
    )
    by_flag = {flag: int(cnt) for flag, cnt in rows}
    return {"site": site.domain, "total": int(total), "by_flag": by_flag}
