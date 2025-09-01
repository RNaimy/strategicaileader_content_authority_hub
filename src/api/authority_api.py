from fastapi import APIRouter
from pydantic import BaseModel
from src.services.authority import compute_authority_signals

router = APIRouter()

class AnalyzeRequest(BaseModel):
    url: str | None = None
    html: str | None = None
    text: str | None = None

@router.get("/health")
def health():
    return {"ok": True, "phase": 7, "service": "authority-signals"}

@router.post("/signals")
def signals(payload: AnalyzeRequest):
    content = payload.text or payload.html or ""
    result = compute_authority_signals(content)
    return {"signals": result}
