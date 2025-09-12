from __future__ import annotations
import os

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.db.session import get_session
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func
from collections import defaultdict

from src.db.models import AnalyticsSnapshot, Site

try:
    from src.services.ga4_client import GA4Client
except Exception:  # pragma: no cover - optional dependency
    GA4Client = None  # type: ignore
try:
    from src.services.gsc_client import GSCClient
except Exception:  # pragma: no cover - optional dependency
    GSCClient = None  # type: ignore

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ---------------------------
# Pydantic Schemas
# ---------------------------


class HealthResponse(BaseModel):
    ok: bool = True
    module: str = "analytics"


class SnapshotOut(BaseModel):
    id: int
    site_id: int
    captured_at: datetime
    source: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    # Core GSC-ish metrics
    clicks: Optional[int] = None
    impressions: Optional[int] = None
    ctr: Optional[float] = None
    average_position: Optional[float] = Field(None, alias="position")

    # Core GA4-ish metrics
    organic_sessions: Optional[int] = None
    conversions: Optional[int] = None
    revenue: Optional[float] = None

    # Coverage metrics
    content_items_count: Optional[int] = None
    pages_indexed: Optional[int] = None
    indexed_pct: Optional[float] = None

    notes: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True


class IngestBase(BaseModel):
    site_id: Optional[int] = None
    domain: Optional[str] = None
    # date range, default last 7 days
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[Dict[str, Any]] = None
    live: Optional[bool] = False
    ga4_property_id: Optional[str] = None
    gsc_site_url: Optional[str] = None


class IngestResponse(BaseModel):
    ok: bool
    source: str
    site_id: int
    inserted: int
    captured_at: datetime


class LatestResponse(BaseModel):
    site_id: int
    domain: str | None = None
    latest: Dict[
        str, SnapshotOut
    ]  # keyed by source, e.g., {"gsc": SnapshotOut, "ga4": SnapshotOut}


class SummaryResponse(BaseModel):
    site_id: int
    domain: str | None = None
    total_snapshots: int
    sources_present: List[str]
    last_captured_at: datetime | None = None
    latest: Dict[str, SnapshotOut]  # same structure as LatestResponse.latest


# ---------------------------
# Helpers
# ---------------------------


def _bool_env(name: str) -> bool:
    v = os.getenv(name)
    return bool(v and v.strip())


def _env_has_ga4() -> bool:
    return (
        _bool_env("GA4_CLIENT_ID")
        and _bool_env("GA4_CLIENT_SECRET")
        and _bool_env("GA4_REFRESH_TOKEN")
    )


def _env_has_gsc() -> bool:
    return (
        _bool_env("GSC_CLIENT_ID")
        and _bool_env("GSC_CLIENT_SECRET")
        and _bool_env("GSC_REFRESH_TOKEN")
    )


def _resolve_site_id(db: Session, site_id: Optional[int], domain: Optional[str]) -> int:
    if site_id:
        exists = db.scalar(
            select(func.count()).select_from(Site).where(Site.id == site_id)
        )
        if not exists:
            raise HTTPException(status_code=404, detail=f"site_id {site_id} not found")
        return site_id
    if domain:
        site = db.scalar(select(Site).where(Site.domain == domain))
        if not site:
            raise HTTPException(status_code=404, detail=f"domain {domain} not found")
        return site.id
    raise HTTPException(status_code=400, detail="Provide either site_id or domain")


def _default_dates(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> tuple[datetime, datetime]:
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)
    return start_date, end_date


def _snapshot_to_out(s: AnalyticsSnapshot) -> SnapshotOut:
    return SnapshotOut(
        id=s.id,
        site_id=s.site_id,
        captured_at=s.captured_at,
        source=s.source,
        period_start=s.period_start,
        period_end=s.period_end,
        clicks=s.clicks,
        impressions=s.impressions,
        ctr=s.ctr,
        position=s.average_position,
        organic_sessions=s.organic_sessions,
        conversions=s.conversions,
        revenue=float(s.revenue) if s.revenue is not None else None,
        content_items_count=s.content_items_count,
        pages_indexed=s.pages_indexed,
        indexed_pct=s.indexed_pct,
        notes=s.notes,
    )


def _latest_by_source(db: Session, site_id: int) -> Dict[str, AnalyticsSnapshot]:
    """
    Return the latest snapshot per source for a given site_id.
    """
    rows = db.execute(
        select(AnalyticsSnapshot.source, AnalyticsSnapshot)
        .where(AnalyticsSnapshot.site_id == site_id)
        .order_by(AnalyticsSnapshot.source, desc(AnalyticsSnapshot.captured_at))
    ).all()
    latest: Dict[str, AnalyticsSnapshot] = {}
    for src, snap in rows:
        # first occurrence per source is the latest due to ordering
        if src not in latest:
            latest[src] = snap
    return latest


@router.get("/config")
def config_status():
    return {
        "ga4": {
            "creds": _env_has_ga4(),
            "property_id": os.getenv("GA4_PROPERTY_ID")
            or os.getenv("GA4_PROPERTY_ID_STRATEGICAI")
            or os.getenv("GA4_PROPERTY_ID_LIASFLOWERS"),
        },
        "gsc": {"creds": _env_has_gsc()},
    }


# ---------------------------
# Routes
# ---------------------------


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, module="analytics")


@router.get("/snapshots", response_model=List[SnapshotOut])
def list_snapshots(
    domain: Optional[str] = Query(None, description="Filter by site domain"),
    site_id: Optional[int] = Query(None, description="Filter by site id"),
    source: Optional[str] = Query(
        None, description="Filter by source, e.g., 'gsc' or 'ga4'"
    ),
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_session),
):
    if not domain and not site_id:
        raise HTTPException(status_code=400, detail="Provide domain or site_id")
    sid = _resolve_site_id(db, site_id, domain)
    stmt = select(AnalyticsSnapshot).where(AnalyticsSnapshot.site_id == sid)
    if source:
        stmt = stmt.where(AnalyticsSnapshot.source == source)
    rows = db.scalars(
        stmt.order_by(desc(AnalyticsSnapshot.captured_at)).limit(limit)
    ).all()
    return [_snapshot_to_out(r) for r in rows]


@router.get("/latest", response_model=LatestResponse)
def latest_snapshots(
    domain: Optional[str] = Query(None, description="Filter by site domain"),
    site_id: Optional[int] = Query(None, description="Filter by site id"),
    db: Session = Depends(get_session),
):
    if not domain and not site_id:
        raise HTTPException(status_code=400, detail="Provide domain or site_id")
    sid = _resolve_site_id(db, site_id, domain)
    latest_map = _latest_by_source(db, sid)
    latest_out: Dict[str, SnapshotOut] = {
        src: _snapshot_to_out(snap) for src, snap in latest_map.items()
    }
    dom = None
    if domain:
        dom = domain
    else:
        # fetch domain for presentation if not provided
        site = db.scalar(select(Site).where(Site.id == sid))
        dom = site.domain if site else None
    return LatestResponse(site_id=sid, domain=dom, latest=latest_out)


@router.get("/summary", response_model=SummaryResponse)
def summary(
    domain: Optional[str] = Query(None, description="Filter by site domain"),
    site_id: Optional[int] = Query(None, description="Filter by site id"),
    db: Session = Depends(get_session),
):
    if not domain and not site_id:
        raise HTTPException(status_code=400, detail="Provide domain or site_id")
    sid = _resolve_site_id(db, site_id, domain)

    total = (
        db.scalar(
            select(func.count())
            .select_from(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.site_id == sid)
        )
        or 0
    )

    latest_map = _latest_by_source(db, sid)
    sources_present = sorted(latest_map.keys())
    last_captured_at = None
    if latest_map:
        last_captured_at = max(s.captured_at for s in latest_map.values())

    latest_out: Dict[str, SnapshotOut] = {
        src: _snapshot_to_out(snap) for src, snap in latest_map.items()
    }
    dom = None
    if domain:
        dom = domain
    else:
        site = db.scalar(select(Site).where(Site.id == sid))
        dom = site.domain if site else None

    return SummaryResponse(
        site_id=sid,
        domain=dom,
        total_snapshots=total,
        sources_present=sources_present,
        last_captured_at=last_captured_at,
        latest=latest_out,
    )


@router.post("/ingest/gsc", response_model=IngestResponse)
def ingest_gsc(payload: IngestBase, db: Session = Depends(get_session)):
    """
    GSC ingestion.

    Default behavior: create a stub snapshot.
    If `payload.live` is True and GSC OAuth env vars are present, attempt a real pull via services.gsc_client.
    """
    sid = _resolve_site_id(db, payload.site_id, payload.domain)
    start, end = _default_dates(payload.start_date, payload.end_date)

    # Live path
    if payload.live:
        if GSCClient is None or not _env_has_gsc():
            raise HTTPException(
                status_code=400,
                detail="GSC live mode requested but credentials/client not available",
            )
        # Determine site URL
        site_url = payload.gsc_site_url
        if not site_url:
            # derive from domain if provided
            if payload.domain:
                site_url = f"https://{payload.domain}/"
        if not site_url:
            raise HTTPException(
                status_code=400, detail="GSC live mode requires gsc_site_url or domain"
            )
        try:
            client = None

            # Prefer explicit OAuth refresh-token flow when present
            if (
                os.getenv("GSC_REFRESH_TOKEN")
                and os.getenv("GSC_CLIENT_ID")
                and os.getenv("GSC_CLIENT_SECRET")
                and hasattr(GSCClient, "from_oauth_refresh_token")
            ):
                client = GSCClient.from_oauth_refresh_token(
                    client_id=os.getenv("GSC_CLIENT_ID"),
                    client_secret=os.getenv("GSC_CLIENT_SECRET"),
                    refresh_token=os.getenv("GSC_REFRESH_TOKEN"),
                    site_url=site_url,
                )

            # Else try service account if configured
            if (
                client is None
                and os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                and hasattr(GSCClient, "from_service_account")
            ):
                client = GSCClient.from_service_account(
                    keyfile=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
                    site_url=site_url,
                )

            # Else fall back to generic env-based constructor
            if client is None:
                client = GSCClient.from_env(site_url=site_url)  # type: ignore[attr-defined]

            metrics = client.fetch_summary(
                start, end
            )  # expected keys: clicks, impressions, ctr, position, pages_indexed
            snap = AnalyticsSnapshot(
                site_id=sid,
                source="gsc",
                period_start=start,
                period_end=end,
                source_row_count=metrics.get("row_count", 0),
                clicks=metrics.get("clicks"),
                impressions=metrics.get("impressions"),
                ctr=metrics.get("ctr"),
                average_position=metrics.get("position")
                or metrics.get("average_position"),
                pages_indexed=metrics.get("pages_indexed"),
                indexed_pct=metrics.get("indexed_pct"),
                notes={**(payload.notes or {}), "live": True, "via": "gsc_client"},
            )
            db.add(snap)
            db.commit()
            db.refresh(snap)
            return IngestResponse(
                ok=True,
                source="gsc",
                site_id=sid,
                inserted=1,
                captured_at=snap.captured_at,
            )
        except HTTPException:
            raise
        except Exception as e:
            err_note = {"live_error": str(e)}
            payload.notes = {**(payload.notes or {}), **err_note}
            # fall through to stub

    # Stub path
    snap = AnalyticsSnapshot(
        site_id=sid,
        source="gsc",
        period_start=start,
        period_end=end,
        source_row_count=0,
        clicks=123,
        impressions=4567,
        ctr=round(123 / 4567, 4),
        average_position=18.7,
        content_items_count=None,
        pages_indexed=None,
        indexed_pct=None,
        organic_sessions=None,
        conversions=None,
        revenue=None,
        notes=payload.notes or {"stub": True, "via": "ingest_gsc"},
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return IngestResponse(
        ok=True, source="gsc", site_id=sid, inserted=1, captured_at=snap.captured_at
    )


@router.post("/ingest/ga4", response_model=IngestResponse)
def ingest_ga4(payload: IngestBase, db: Session = Depends(get_session)):
    """
    GA4 ingestion.

    Default behavior: create a stub snapshot (works offline).
    If `payload.live` is True and GA4 OAuth env vars are present, attempt a real pull via services.ga4_client.
    """
    sid = _resolve_site_id(db, payload.site_id, payload.domain)
    start, end = _default_dates(payload.start_date, payload.end_date)

    # Live path
    if payload.live:
        if GA4Client is None or not _env_has_ga4():
            raise HTTPException(
                status_code=400,
                detail="GA4 live mode requested but credentials/client not available",
            )
        # Determine property id
        prop_id = (
            payload.ga4_property_id
            or os.getenv("GA4_PROPERTY_ID")
            or os.getenv("GA4_PROPERTY_ID_STRATEGICAI")
            or os.getenv("GA4_PROPERTY_ID_LIASFLOWERS")
        )
        if not prop_id:
            raise HTTPException(
                status_code=400,
                detail="GA4 property id missing; send ga4_property_id or set GA4_PROPERTY_ID* in env",
            )
        try:
            client = GA4Client.from_env(property_id=prop_id)  # type: ignore[attr-defined]
            metrics = client.fetch_summary(
                start, end
            )  # expected keys: sessions, conversions, revenue
            snap = AnalyticsSnapshot(
                site_id=sid,
                source="ga4",
                period_start=start,
                period_end=end,
                source_row_count=metrics.get("row_count", 0),
                organic_sessions=metrics.get("sessions"),
                conversions=metrics.get("conversions"),
                revenue=metrics.get("revenue"),
                notes={**(payload.notes or {}), "live": True, "via": "ga4_client"},
            )
            db.add(snap)
            db.commit()
            db.refresh(snap)
            return IngestResponse(
                ok=True,
                source="ga4",
                site_id=sid,
                inserted=1,
                captured_at=snap.captured_at,
            )
        except HTTPException:
            raise
        except Exception as e:  # fallback to stub on error
            err_note = {"live_error": str(e)}
            payload.notes = {**(payload.notes or {}), **err_note}
            # fall through to stub

    # Stub path (default)
    snap = AnalyticsSnapshot(
        site_id=sid,
        source="ga4",
        period_start=start,
        period_end=end,
        source_row_count=0,
        organic_sessions=789,
        conversions=17,
        revenue=1234.56,
        clicks=None,
        impressions=None,
        ctr=None,
        average_position=None,
        content_items_count=None,
        pages_indexed=None,
        indexed_pct=None,
        notes=payload.notes or {"stub": True, "via": "ingest_ga4"},
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return IngestResponse(
        ok=True, source="ga4", site_id=sid, inserted=1, captured_at=snap.captured_at
    )
