from fastapi import FastAPI
from src.utils import db
from sqlalchemy import text

def create_app() -> FastAPI:
    app = FastAPI(title="Content Authority Hub")

    @app.get("/health")
    def health():
        # light DB ping (won't fail app if DB is down)
        try:
            with db.get_session() as s:
                ok = s.execute(text("select 1")).scalar() == 1
        except Exception:
            ok = False
        return {"ok": True, "db": ok}

    return app

app = create_app()