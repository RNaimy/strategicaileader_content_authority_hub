from __future__ import annotations

import os
from fastapi.staticfiles import StaticFiles

from src.api.authority_api import router as authority_router
try:
    from src.api.graph_api import router as graph_router  # type: ignore
except Exception:  # pragma: no cover
    graph_router = None  # type: ignore[assignment]
from typing import List

from fastapi import FastAPI, APIRouter, Query

from sqlalchemy import text

from src.db.session import get_session
from src.db_init import init_db

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

try:
    from src.api import analytics_router  # type: ignore
except Exception:  # pragma: no cover
    analytics_router = None  # type: ignore[assignment]

try:
    from src.api import intelligence_router  # type: ignore
except Exception:  # pragma: no cover
    intelligence_router = None  # type: ignore[assignment]


app = FastAPI(
    title="Content Authority Hub",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# Serve graph exports (e.g., JSON/CSV dumps) as static files
# Directory is ensured to exist during startup; however, we also create it here
# to avoid mount-time errors when running without startup (e.g., some tests).
os.makedirs("graph/export", exist_ok=True)
app.mount("/graph-export", StaticFiles(directory="graph/export"), name="graph-export")


@app.on_event("startup")
def _startup() -> None:
    """Initialize the database on startup."""
    os.makedirs("graph/export", exist_ok=True)
    init_db()


@app.get("/")
def root() -> dict:
    routers: List[str] = ["/clusters", "/content", "/authority"]
    if inventory_router is not None:
        routers.append("/inventory")
    if scraper_router is not None:
        routers.append("/scraper")
    if analytics_router is not None:
        routers.append("/analytics")
    if intelligence_router is not None:
        routers.append("/intelligence")
    # Graph API endpoints (authority graph, links, metrics)
    if graph_router is not None:
        routers.append("/graph")
    routers.append("/graph-export")
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


# Router mounting

# --- Graph router registration with robust fallback ---

def _make_graph_fallback_router() -> APIRouter:
    r = APIRouter()

    @r.get("/graph/export")
    def _graph_export_proxy(include_metrics: bool = Query(True)):
        from src.services.graph_builder import compute_and_export_graph_json
        with get_session() as s:
            return compute_and_export_graph_json(s, include_metrics=include_metrics)

    @r.post("/graph/recompute")
    def _graph_recompute_proxy(include_metrics: bool = Query(True)):
        from src.services.graph_builder import recompute_graph_metrics, compute_and_export_graph_json
        with get_session() as s:
            recompute_graph_metrics(s)
            return compute_and_export_graph_json(s, include_metrics=include_metrics)

    return r

# If a dedicated graph router is available, include it (it should declare its own /graph prefix/paths)
if graph_router is not None:
    app.include_router(graph_router, tags=["graph"])  # do not add a prefix; router defines its own

# Ensure mandatory graph endpoints exist; if not, mount a minimal fallback so tests and CLI don't 404

def _has_path(p: str) -> bool:
    # FastAPI/Starlette routes may expose either `.path` or `.path_format` depending on type
    for rt in app.routes:
        rp = getattr(rt, "path", None)
        rpf = getattr(rt, "path_format", None)
        if rp == p or rpf == p:
            return True
    return False

if not _has_path("/graph/export") or not _has_path("/graph/recompute"):
    app.include_router(_make_graph_fallback_router(), tags=["graph-fallback"])

app.include_router(authority_router, prefix="/authority", tags=["authority"])
app.include_router(clustering_router)
app.include_router(content_router)
if inventory_router is not None:
    app.include_router(inventory_router)
if scraper_router is not None:
    app.include_router(scraper_router)
if analytics_router is not None:
    app.include_router(analytics_router)
if intelligence_router is not None:
    app.include_router(intelligence_router)

__all__ = ["app"]