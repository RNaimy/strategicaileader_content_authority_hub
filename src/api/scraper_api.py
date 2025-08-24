# src/api/scraper_api.py
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter(prefix="/scraper", tags=["scraper"])

@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "scraper"}