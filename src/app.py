# src/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.brands_api import router as brands_router

app = FastAPI(title="Content Authority Hub")

# CORS for local dev (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(brands_router)

# Static hosting (so /brands.html works)
app.mount("/", StaticFiles(directory="static", html=True), name="static")