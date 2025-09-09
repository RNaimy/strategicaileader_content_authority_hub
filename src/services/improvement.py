"""
Phase 9 - Continuous Improvement service layer.

This module provides small, composable helpers the API layer can call to:
  - fetch recommendations for Quick Wins, Content at Risk, and Topics Emerging
  - (dev) recompute simple recommendations to populate the table during local testing

The real scoring logic will evolve as Phases 10–13 land; start simple and additive.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.db.models import ImprovementRecommendation
try:
    # If ContentItem exists in your models, import it; if not, the recompute stub will skip content-based rules.
    from src.db.models import ContentItem  # type: ignore
    HAS_CONTENT_ITEM = True
except Exception:
    HAS_CONTENT_ITEM = False


# ---------------------------
# Read helpers used by the API
# ---------------------------

def get_quick_wins(db: Session, site_id: int, limit: int = 50) -> List[ImprovementRecommendation]:
    return (
        db.query(ImprovementRecommendation)
        .filter(ImprovementRecommendation.site_id == site_id)
        .filter(ImprovementRecommendation.flag == "quick_win")
        .order_by(ImprovementRecommendation.score.desc().nullslast())
        .limit(limit)
        .all()
    )


def get_content_at_risk(db: Session, site_id: int, limit: int = 50) -> List[ImprovementRecommendation]:
    return (
        db.query(ImprovementRecommendation)
        .filter(ImprovementRecommendation.site_id == site_id)
        .filter(ImprovementRecommendation.flag == "at_risk")
        .order_by(ImprovementRecommendation.score.desc().nullslast())
        .limit(limit)
        .all()
    )


def get_topics_emerging(db: Session, site_id: int, limit: int = 50) -> List[ImprovementRecommendation]:
    return (
        db.query(ImprovementRecommendation)
        .filter(ImprovementRecommendation.site_id == site_id)
        .filter(ImprovementRecommendation.flag == "emerging_topic")
        .order_by(ImprovementRecommendation.score.desc().nullslast())
        .limit(limit)
        .all()
    )


# ----------------------------------------
# Dev-only: simple recompute to seed data
# ----------------------------------------

def recompute_recommendations(db: Session, site_id: int, limit: int = 100) -> Dict[str, Any]:
    """
    Minimal, SQLite-safe seeding logic so you can test the Phase 9 endpoints locally.

    Strategy (simple & non-destructive):
      - Do not delete existing rows (idempotent-ish writes keyed by a hashable rationale signature).
      - If ContentItem exists:
          * Flag a few "stale" items as at_risk (updated_at older than 180d if available).
          * Flag a few items with long titles as quick_win (pretend snippet rewrite opportunity).
      - Always add one synthetic "emerging_topic" for the site so UI has something to render.

    Returns a summary dict with counts written by flag.
    """
    written = {"quick_win": 0, "at_risk": 0, "emerging_topic": 0}

    # Helper: insert if a similar rationale doesn't already exist for the same content/flag
    def _insert_unique(flag: str, score: Optional[float], rationale: Dict[str, Any], content_item_id: Optional[int] = None) -> None:
        existing = (
            db.query(ImprovementRecommendation)
            .filter(ImprovementRecommendation.site_id == site_id)
            .filter(ImprovementRecommendation.flag == flag)
            .filter(ImprovementRecommendation.content_item_id == content_item_id)
            .first()
        )
        if existing:
            # Update score/rationale if score would improve visibility
            if (score or 0) > (existing.score or 0):
                existing.score = score
                existing.rationale = rationale
            return

        rec = ImprovementRecommendation(
            site_id=site_id,
            content_item_id=content_item_id,
            flag=flag,
            score=score,
            rationale=rationale,
        )
        db.add(rec)

    # 1) at_risk: stale by updated_at (if present)
    if HAS_CONTENT_ITEM and hasattr(ContentItem, "updated_at"):
        cutoff = datetime.utcnow() - timedelta(days=180)
        stale_q = (
            db.query(ContentItem.id)
            .filter(ContentItem.site_id == site_id)
            .filter(ContentItem.updated_at < cutoff)  # type: ignore[attr-defined]
            .limit(limit // 2)
        )
        for (cid,) in stale_q.all():
            _insert_unique(
                flag="at_risk",
                score=0.85,  # static seed score for now
                rationale={
                    "reason": "stale_content",
                    "days_since_update": 180,
                },
                content_item_id=cid,
            )
            written["at_risk"] += 1

    # 2) quick_win: heuristic on title length (as a stand-in for low CTR snippet)
    if HAS_CONTENT_ITEM and hasattr(ContentItem, "title"):
        long_title_q = (
            db.query(ContentItem.id, func.length(ContentItem.title))
            .filter(ContentItem.site_id == site_id)
            .filter(func.length(ContentItem.title) > 60)  # type: ignore[arg-type]
            .limit(limit // 2)
        )
        for cid, title_len in long_title_q.all():
            _insert_unique(
                flag="quick_win",
                score=0.7 + min(0.2, (title_len - 60) / 100.0),  # slight lift for very long titles
                rationale={
                    "reason": "long_title_opt",
                    "title_length": int(title_len or 0),
                    "suggestion": "Shorten headline and tighten meta for better CTR.",
                },
                content_item_id=cid,
            )
            written["quick_win"] += 1

    # 3) topics_emerging: always add one site-level synthetic opportunity so UI isn't empty
    _insert_unique(
        flag="emerging_topic",
        score=0.65,
        rationale={
            "reason": "synthetic_seed",
            "note": "Replace with GSC cluster growth logic once metrics ingestion is wired.",
        },
        content_item_id=None,
    )
    written["emerging_topic"] += 1

    db.commit()
    return written
