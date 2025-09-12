# src/api/__init__.py
"""API package exports for FastAPI routers.

This module centralizes router imports and avoids merge conflicts by
guarding optional routers with safe imports. It also exposes a helper
`get_routers()` that returns only available routers, and mounts the
retrieval router only when ENABLE_RETRIEVAL is truthy.
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

# --- Core routers (expected to exist) ---
from .clustering_api import router as clustering_router  # type: ignore
from .content_api import router as content_router  # type: ignore


# --- Optional routers (guarded imports) ---
def _optional_router(module_name: str):
    try:
        mod = __import__(f"{__name__}.{module_name}", fromlist=["router"])
        return getattr(mod, "router", None)
    except Exception as e:  # pragma: no cover
        logger.debug("Optional router '%s' not available: %s", module_name, e)
        return None


inventory_router = _optional_router("inventory_api")
scraper_router = _optional_router("scraper_api")
analytics_router = _optional_router("analytics_api")
intelligence_router = _optional_router("intelligence_api")
retrieval_router = _optional_router("retrieval_api")

__all__ = [
    "clustering_router",
    "content_router",
    "inventory_router",
    "scraper_router",
    "analytics_router",
    "intelligence_router",
    "retrieval_router",
    "get_routers",
]


def get_routers():
    """Return a list of routers that should be mounted."""
    routers = [clustering_router, content_router]

    # Add any optional routers that successfully imported
    for r in (inventory_router, scraper_router, analytics_router, intelligence_router):
        if r is not None:
            routers.append(r)

    # Retrieval is opt-in via env flag and must be importable
    enable_retrieval = os.getenv("ENABLE_RETRIEVAL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if enable_retrieval and retrieval_router is not None:
        routers.append(retrieval_router)
        logger.info("retrieval: enabled and mounted")
    else:
        logger.debug(
            "retrieval: enabled_env=%s, router_available=%s (not mounted)",
            enable_retrieval,
            retrieval_router is not None,
        )

    return routers
