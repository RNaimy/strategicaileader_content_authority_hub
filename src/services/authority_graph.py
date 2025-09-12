"""
Authority graph service.

This module computes simple link graph metrics for a site's content and
exposes helpers used by the authority API endpoints.

SQLite-safe: avoids ALTER/constraint ops, uses plain ORM upserts.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.db.models import ContentItem, ContentLink, GraphMetric, Site


class AuthorityGraphService:
    """Compute/export a very lightweight link graph for a site.

    Notes
    -----
    * Our `content_links` table does **not** have a `site_id` column.
      To scope to a site, we join via `from_content_id -> content_items.site_id`.
    * Seed data often stores only `to_url` (and leaves `to_content_id` NULL).
      We attempt to resolve internal links by matching the URL path to a
      content item's path for the same site.
    """

    @staticmethod
    def _site_content_ids(db: Session, site_id: int) -> Dict[int, str]:
        """Return mapping of content_id -> full URL for a site."""
        rows: List[Tuple[int, str]] = (
            db.query(ContentItem.id, ContentItem.url)
            .filter(ContentItem.site_id == site_id)
            .all()
        )
        return {cid: url for cid, url in rows}

    @staticmethod
    def _path(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            p = urlparse(url)
            return p.path or "/"
        except Exception:
            # URLs like "/pillar" are fine; treat as path already
            return url

    @classmethod
    def _build_path_index(cls, id_to_url: Dict[int, str]) -> Dict[str, int]:
        """Map URL path -> content_id for quick resolution of internal edges."""
        out: Dict[str, int] = {}
        for cid, full in id_to_url.items():
            path = cls._path(full)
            if path:
                out[path] = cid
        return out

    @classmethod
    def recompute(cls, db: Session, site: Site) -> Dict[str, object]:
        # Scope content and links to the site
        id_to_url = cls._site_content_ids(db, site.id)
        path_index = cls._build_path_index(id_to_url)
        content_ids = set(id_to_url.keys())

        # Fetch edges originating from this site's content
        edges: List[ContentLink] = (
            db.query(ContentLink)
            .join(ContentItem, ContentItem.id == ContentLink.from_content_id)
            .filter(ContentItem.site_id == site.id)
            .all()
        )

        # Compute simple degrees and opportunistically resolve to_content_id
        deg_in: Dict[int, int] = {cid: 0 for cid in content_ids}
        deg_out: Dict[int, int] = {cid: 0 for cid in content_ids}

        resolved = 0
        for e in edges:
            if e.from_content_id in content_ids:
                deg_out[e.from_content_id] += 1

            dest_cid: Optional[int] = None
            if e.to_content_id:
                dest_cid = e.to_content_id if e.to_content_id in content_ids else None
            else:
                # Try to resolve by path within the same site
                p = cls._path(e.to_url)
                if p and p in path_index:
                    dest_cid = path_index[p]

            if dest_cid is not None and dest_cid in content_ids:
                # Count inbound edge to the resolved destination
                deg_in[dest_cid] += 1

                # If the link wasn't resolved previously, persist the resolution
                if e.to_content_id != dest_cid:
                    e.to_content_id = dest_cid
                    resolved += 1
                # Mark internal if the destination is within the same site
                if e.is_internal is not True:
                    e.is_internal = True

        # Upsert GraphMetric rows per content item (SQLite-safe)
        for cid in content_ids:
            gm: Optional[GraphMetric] = (
                db.query(GraphMetric)
                .filter(GraphMetric.content_id == cid)
                .one_or_none()
            )
            if gm is None:
                gm = GraphMetric(
                    content_id=cid,
                    degree_in=deg_in.get(cid, 0),
                    degree_out=deg_out.get(cid, 0),
                    last_computed_at=func.current_timestamp(),
                )
                db.add(gm)
            else:
                gm.degree_in = deg_in.get(cid, 0)
                gm.degree_out = deg_out.get(cid, 0)
                gm.last_computed_at = func.current_timestamp()
        # Flush link updates before committing
        db.flush()
        db.commit()

        return {
            "ok": True,
            "site": site.domain,
            "nodes": len(content_ids),
            "edges": len(edges),
            "resolved_edges": resolved,
        }

    @classmethod
    def export(cls, db: Session, site: Site) -> Dict[str, object]:
        # Scope links by joining via from_content_id -> content_items.site_id
        links: List[ContentLink] = (
            db.query(ContentLink)
            .join(ContentItem, ContentItem.id == ContentLink.from_content_id)
            .filter(ContentItem.site_id == site.id)
            .all()
        )
        payload = {
            "site": site.domain,
            "edges": [
                {
                    "id": l.id,
                    "from_content_id": l.from_content_id,
                    "to_content_id": l.to_content_id,
                    "to_url": l.to_url,
                    "anchor_text": l.anchor_text,
                }
                for l in links
            ],
        }
        return payload
