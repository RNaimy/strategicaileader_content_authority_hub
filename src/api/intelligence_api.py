from __future__ import annotations

import os
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from src.services.serp_client import SERPClient

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

@router.get("/")
def index():
    return {
        "module": "intelligence",
        "endpoints": [
            "/intelligence/health",
            "/intelligence/config",
            "/intelligence/qa",
            "/intelligence/serp",
        ],
    }


# ---------- Models ----------

class QARequest(BaseModel):
    question: str = Field(..., description="Natural-language question")
    domain: Optional[str] = Field(None, description="Restrict context to a known site domain")
    top_k: int = Field(5, ge=1, le=50, description="Max items to retrieve from vector store")


class SERPRequest(BaseModel):
    query: str = Field(..., description="Search query (can include site: filters etc.)")
    num: int = Field(5, ge=1, le=50, description="Number of results to return")
    market: Optional[str] = Field(None, description="Market/locale code, e.g. en-US")


# ---------- Routes ----------

@router.get("/health")
def health():
    return {"ok": True, "module": "intelligence"}


@router.get("/config")
def config():
    # Report only presence/absence, never secret values
    return {
        "openai": {"configured": bool(os.getenv("OPENAI_API_KEY"))},
        "serp": {"bing": bool(os.getenv("BING_API_KEY")), "google_cx": bool(os.getenv("GOOGLE_CSE_CX"))},
    }


@router.post("/qa")
def qa(req: QARequest):
    # normalize inputs (do not change current contract)
    question = (req.question or "").strip()
    top_k = max(1, min(50, int(req.top_k)))
    domain = (req.domain or None)
    """
    Placeholder for retrieval-augmented QA.
    Tests currently xfail against this endpoint.
    Return HTTP 501 to indicate not implemented yet.
    """
    payload = {
        "ok": False,
        "message": "QA endpoint is not implemented yet. This is a Phase 6 placeholder.",
        "echo": {"question": question, "domain": domain, "top_k": top_k},
    }
    return JSONResponse(status_code=501, content=payload)


@router.post("/serp")
def serp(req: SERPRequest):
    query = (req.query or "").strip()
    num = max(1, min(50, int(req.num)))
    market = (req.market or None)

    # Determine provider and attempt live search if configured
    provider = None
    if os.getenv("GOOGLE_CSE_API_KEY") and os.getenv("GOOGLE_CSE_CX"):
        provider = "google_cse"
    elif os.getenv("BING_API_KEY"):
        provider = "bing"

    client = SERPClient.from_env()
    if client is None or provider is None:
        payload = {
            "ok": False,
            "message": "SERP endpoint not configured. Set GOOGLE_CSE_API_KEY+GOOGLE_CSE_CX or BING_API_KEY.",
            "echo": {"query": query, "num": num, "market": market},
        }
        return JSONResponse(status_code=501, content=payload)

    try:
        results = client.search(query=query, num=num, market=market)
        return {
            "ok": True,
            "provider": provider,
            "query": query,
            "num": num,
            "market": market,
            "results": results,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(e),
                "provider": provider,
                "echo": {"query": query, "num": num, "market": market},
            },
        )