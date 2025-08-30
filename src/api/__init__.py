# src/api/__init__.py
"""API package initialization.

Exposes shared routers for easy import elsewhere, e.g.:

    from src.api import content_router, clustering_router, inventory_router, scraper_router, get_routers
"""

from __future__ import annotations

# Import routers
from .clustering_api import router as clustering_router
from .content_api import router as content_router
from .inventory_api import router as inventory_router
from .scraper_api import router as scraper_router
from .analytics_api import router as analytics_router
from .intelligence_api import router as intelligence_router

__all__ = [
    "clustering_router",
    "content_router",
    "inventory_router",
    "scraper_router",
    "analytics_router",
    "intelligence_router",
    "get_routers",
]

def get_routers():
    """Return all routers as a list.

    Useful in app startup code, e.g.:

        for r in get_routers():
            app.include_router(r)
    """
    return [
        clustering_router,
        content_router,
        inventory_router,
        scraper_router,
        analytics_router,
        intelligence_router,
    ]
