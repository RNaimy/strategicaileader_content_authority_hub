

"""API package initialization.

This module exposes shared routers for easy import elsewhere, e.g.:

    from api import brands_router

"""
from __future__ import annotations

# Re-export the Brands router so app.py can import cleanly
from .brands_api import router as brands_router  # noqa: F401

__all__ = ["brands_router"]
__version__ = "0.1.0"