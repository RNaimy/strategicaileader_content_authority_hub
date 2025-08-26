from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI

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


# Router mounting
app.include_router(clustering_router)
app.include_router(content_router)
if inventory_router is not None:
    app.include_router(inventory_router)
if scraper_router is not None:
    app.include_router(scraper_router)