from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/_debug/ping")
def ping() -> dict[str, str]:
    """Simple liveness check for local debugging."""
    return {"status": "ok"}


@router.get("/_debug/routes")
def list_routes(request: Request) -> dict[str, list[dict[str, object]]]:
    """Return a JSON description of mounted routes.

    Useful when verifying which routers are mounted in the running app.
    """
    app = request.app

    details: list[dict[str, object]] = []
    for r in app.router.routes:  # type: ignore[attr-defined]
        path = getattr(r, "path", None)
        name = getattr(r, "name", None)
        methods = sorted(list(getattr(r, "methods", []) or []))
        details.append(
            {
                "path": path,
                "name": name,
                "methods": methods,
            }
        )

    # Keep a simplified list too for quick grepping
    return {
        "paths": [d["path"] for d in details if d.get("path")],
        "routes": details,
    }
