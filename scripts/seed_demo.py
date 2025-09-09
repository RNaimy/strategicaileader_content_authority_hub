

#!/usr/bin/env python3
"""
Seed the database with a small demo graph for quick local testing.

Usage:
  python scripts/seed_demo.py [--domain DOMAIN] [--flush]

Reads DATABASE_URL from environment (e.g., postgresql+psycopg://user:pass@localhost:5432/appdb)
"""
from __future__ import annotations

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import sessionmaker

# Try to load .env if present (optional, no hard dependency)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


# --- Import your app models ---
# Make the script work whether the project is installed as a package,
# run from the repo root, or executed with/without PYTHONPATH=.
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# Try a few plausible module paths for the ORM models
_model_import_errors: list[str] = []
_models_candidates = [
    "src.models",
    "src.db.models",
    "src.database.models",
    "models",
    "strategicaileader_content_authority_hub.models",
]
Site = ContentItem = ContentLink = None  # type: ignore
for modname in _models_candidates:
    try:
        mod = __import__(modname, fromlist=["Site", "ContentItem", "ContentLink"])  # type: ignore
        Site = getattr(mod, "Site")  # type: ignore
        ContentItem = getattr(mod, "ContentItem")  # type: ignore
        ContentLink = getattr(mod, "ContentLink")  # type: ignore
        break
    except Exception as e:  # pragma: no cover
        _model_import_errors.append(f"{modname}: {e!r}")

if any(x is None for x in (Site, ContentItem, ContentLink)):
    msg = [
        "ERROR: Could not import models. Tried the following module paths:",
        *("  - " + s for s in _model_import_errors),
        "\nHints:",
        "  • If you use a src/ layout, run with:  PYTHONPATH=.:src python scripts/seed_demo.py --domain example.com",
        "  • Or install the project in editable mode:  pip install -e .",
        "  • Verify where your models live (e.g., src/models.py or src/db/models.py).",
    ]
    print("\n".join(msg))
    raise SystemExit(1)


def get_session() -> sessionmaker:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL is not set. Create a .env or export the variable.")
        sys.exit(1)
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def upsert_site(db, domain: str) -> Site:
    existing = db.execute(select(Site).where(Site.domain == domain)).scalar_one_or_none()
    if existing:
        return existing
    site = Site(domain=domain, name=domain)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def flush_demo_for_site(db, site_id: int) -> None:
    # Remove only demo content for this site based on our demo URLs pattern
    demo_host_fragments = ["example.com", "x.com", "y.com", "z.com", "demo.local"]
    db.execute(
        delete(ContentLink).where(ContentLink.from_content_id.in_(
            select(ContentItem.id).where(ContentItem.site_id == site_id)
        ))
    )
    db.execute(
        delete(ContentItem).where(
            (ContentItem.site_id == site_id)
            & (
                (ContentItem.url.contains(demo_host_fragments[0]))
                | (ContentItem.url.contains(demo_host_fragments[1]))
                | (ContentItem.url.contains(demo_host_fragments[2]))
                | (ContentItem.url.contains(demo_host_fragments[3]))
                | (ContentItem.url.contains(demo_host_fragments[4]))
            )
        )
    )
    db.commit()


def seed_demo(db, domain: str) -> None:
    site = upsert_site(db, domain)

    # Create a small but interesting graph (6 nodes, cross-links)
    items = [
        ContentItem(site_id=site.id, url=f"https://{domain}/intro", title="Intro"),
        ContentItem(site_id=site.id, url=f"https://{domain}/pillar", title="Pillar"),
        ContentItem(site_id=site.id, url=f"https://{domain}/posts/deep-dive", title="Deep Dive"),
        ContentItem(site_id=site.id, url=f"https://{domain}/how-to", title="How To"),
        ContentItem(site_id=site.id, url=f"https://{domain}/faq", title="FAQ"),
        ContentItem(site_id=site.id, url=f"https://{domain}/resources", title="Resources"),
    ]
    db.add_all(items)
    db.commit()
    for it in items:
        db.refresh(it)

    # Internal links via relative paths (exercise the resolver)
    links = [
        (items[0], "/pillar"),          # intro -> pillar
        (items[1], "/posts/deep-dive"), # pillar -> deep-dive
        (items[1], "/faq"),             # pillar -> faq
        (items[2], "/resources"),       # deep-dive -> resources
        (items[3], "/pillar"),          # how-to -> pillar
        (items[4], "/resources"),       # faq -> resources
    ]

    db.add_all([
        ContentLink(from_content_id=src.id, to_url=to_url, is_internal=True)
        for src, to_url in links
    ])
    db.commit()

    print(
        f"Seeded demo content for domain '{domain}'.\n"
        f" Nodes: {len(items)} | Edges: {len(links)}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed demo content for local testing")
    parser.add_argument(
        "--domain",
        default=os.getenv("DEMO_DOMAIN", "example.com"),
        help="Domain to attach demo content to (default: example.com)",
    )
    parser.add_argument(
        "--flush",
        action="store_true",
        help="Remove prior demo content for this site before seeding",
    )
    args = parser.parse_args(argv)

    SessionLocal = get_session()
    with SessionLocal() as db:
        if args.flush:
            site = upsert_site(db, args.domain)
            flush_demo_for_site(db, site.id)
            print(f"Flushed prior demo content for '{args.domain}'.")
        seed_demo(db, args.domain)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())