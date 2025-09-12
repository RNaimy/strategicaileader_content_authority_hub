"""
Lightweight Brands API.

Provides CRUD operations for managing brands:
- List brands
- Retrieve a brand by key
- Create/upsert a brand
- Update a brand (partial)
- Delete a brand

This module exports both a FastAPI `router` (mounted at `/brands`) and a ready-to-use FastAPI `app` mounted at `/api`.

Tests monkeypatch `BRANDS_JSON` to point at a temp file containing `{"brands": []}`. Read/write helpers are resilient when the file is missing or empty.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Response
from fastapi import status
from fastapi.responses import JSONResponse
import re
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from pathlib import Path
import json

# Storage location (tests will monkeypatch this value)
BRANDS_JSON: str = str(Path(__file__).with_name("brands.json"))

# --------------------------- Pydantic models --------------------------- #


class Brand(BaseModel):
    key: str = Field(..., description="Stable identifier for the brand")
    name: Optional[str] = Field(None, description="Human readable name")
    site_url: Optional[str] = Field(None, description="Primary site URL")
    audience: Optional[str] = None
    categories: Optional[List[str]] = None
    default_keywords: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


class BrandUpdate(BaseModel):
    name: Optional[str] = None
    site_url: Optional[str] = None
    audience: Optional[str] = None
    categories: Optional[List[str]] = None
    default_keywords: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


# --------------------------- helpers --------------------------- #


def _read_store() -> Dict[str, List[Dict[str, Any]]]:
    path = Path(BRANDS_JSON)
    if not path.exists():
        return {"brands": []}
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return {"brands": []}
        data = json.loads(text)
        if (
            isinstance(data, dict)
            and "brands" in data
            and isinstance(data["brands"], list)
        ):
            return data
        # Tolerate just a list
        if isinstance(data, list):
            # Defensive: tolerate stores that are a bare list, not expected in normal runs.
            return {"brands": data}  # pragma: no cover
    except Exception:  # pragma: no cover
        # On any parse error, behave as an empty store (keeps tests robust)
        return {"brands": []}
    return {"brands": []}  # pragma: no cover


def _write_store(data: Dict[str, List[Dict[str, Any]]]) -> None:
    path = Path(BRANDS_JSON)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _find_index(brands: List[Dict[str, Any]], key: str) -> int:
    for i, b in enumerate(brands):
        if b.get("key") == key:
            return i
    return -1


def _validate_key(key: str) -> None:
    """Enforce a simple key format for stability across environments."""
    if not key or not isinstance(key, str):
        raise HTTPException(status_code=400, detail="Key is required")
    if not re.match(r"^[A-Za-z0-9._-]+$", key):
        raise HTTPException(
            status_code=400,
            detail="Key may contain letters, numbers, dot, underscore, or dash",
        )


# --------------------------- router --------------------------- #

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("/", summary="List brands")
def list_brands(
    q: Optional[str] = None, category: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Return the collection (enveloped) with optional filtering:
    - q: case-insensitive substring match against `key`, `name`, or `audience`
    - category: requires the value to be present in `categories`
    Results are sorted by `key` ascending for stability.
    """
    data = _read_store()
    items = data.get("brands", [])
    qnorm = (q or "").strip().lower()
    catnorm = (category or "").strip().lower()

    def keep(b: Dict[str, Any]) -> bool:
        ok = True
        if qnorm:
            hay = " ".join(
                [
                    str(b.get("key", "")),
                    str(b.get("name", "")),
                    str(b.get("audience", "")),
                ]
            ).lower()
            ok = qnorm in hay
        if ok and catnorm:
            cats = [c.lower() for c in (b.get("categories") or [])]
            ok = catnorm in cats
        return ok

    filtered = [b for b in items if keep(b)]
    filtered.sort(key=lambda x: (str(x.get("key", "")).lower()))
    return {"brands": filtered}


@router.post("/", summary="Create or upsert a brand")
def create_brand(brand: Brand):
    """Create a new brand. If the key already exists, upsert and return 200."""
    _validate_key(brand.key)
    data = _read_store()
    brands = data.setdefault("brands", [])
    idx = _find_index(brands, brand.key)
    payload = brand.model_dump(exclude_none=True)
    if idx == -1:
        brands.append(payload)
        _write_store(data)
        # Return 201 on first creation
        return JSONResponse(
            status_code=status.HTTP_201_CREATED, content=brand.model_dump()
        )
    # Upsert existing
    brands[idx].update(payload)
    _write_store(data)
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=Brand(**brands[idx]).model_dump()
    )


@router.get("/{key}", summary="Get a brand by key")
def get_brand(key: str) -> Brand:
    _validate_key(key)
    data = _read_store()
    brands = data.get("brands", [])
    idx = _find_index(brands, key)
    if idx == -1:
        raise HTTPException(status_code=404, detail="Brand not found")
    return Brand(**brands[idx])


@router.put("/{key}", summary="Update a brand (partial)")
def update_brand(key: str, upd: BrandUpdate) -> Brand:
    _validate_key(key)
    data = _read_store()
    brands = data.get("brands", [])
    idx = _find_index(brands, key)
    if idx == -1:
        raise HTTPException(status_code=404, detail="Brand not found")
    # Apply partial updates
    patch = upd.model_dump(exclude_none=True)
    brands[idx].update(patch)
    _write_store(data)
    return Brand(**brands[idx])


@router.delete(
    "/{key}", status_code=204, summary="Delete a brand", response_class=Response
)
def delete_brand(key: str) -> Response:
    _validate_key(key)
    data = _read_store()
    brands = data.get("brands", [])
    idx = _find_index(brands, key)
    if idx == -1:
        raise HTTPException(status_code=404, detail="Brand not found")
    brands.pop(idx)
    _write_store(data)
    return Response(status_code=204)


# --------------- FastAPI app that mounts our router under /api --------------- #

app = FastAPI(title="Content Authority Hub API (tests)")
app.include_router(router, prefix="/api")

__all__ = ["router", "app", "BRANDS_JSON", "Brand", "BrandUpdate"]
