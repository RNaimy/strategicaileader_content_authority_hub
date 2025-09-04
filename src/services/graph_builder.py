from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

try:
    # Local imports – these modules must exist in the project
    from src.db.session import SessionLocal
    from src.db.models import ContentLink, GraphMetric, ContentItem
    from src.services.link_extractor import extract_links, Link
except Exception as e:  # pragma: no cover - import errors should be visible in tests
    raise


@dataclass
class GraphConfig:
    damping: float = 0.85
    max_iter: int = 50
    tol: float = 1e-6


def _normalize_url(u: str | None) -> str | None:
    if not u:
        return None
    parts = urlsplit(u)
    # Drop fragments and query; normalize trailing slash
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = f"{parts.scheme}://{parts.netloc}{path}"
    return normalized


class GraphBuilder:
    """
    Build a directed graph from content_links and compute metrics:
    - degree_in, degree_out
    - PageRank
    - HITS (authority & hub)

    Persists into graph_metrics.
    """

    def __init__(self, db: Session | None = None, cfg: GraphConfig | None = None):
        self.db = db
        self.cfg = cfg or GraphConfig()

    # ---------- Public API ----------
    def run(self) -> int:
        """
        Recompute graph metrics for all internal links that resolve to a content_id.
        Returns number of rows written to graph_metrics.
        """
        close_db = False
        if self.db is None:
            self.db = SessionLocal()
            close_db = True

        try:
            # Load all known content item IDs up front so we always include orphans.
            all_node_ids = [int(cid) for (cid,) in self.db.query(ContentItem.id).all()]

            # If there are no content items at all, clear metrics and exit.
            if not all_node_ids:
                self.db.query(GraphMetric).delete()
                self.db.commit()
                return 0

            edges = self._load_edges(self.db)

            # If there are no edges, persist zero-degree metrics for all items.
            if not edges:
                self._persist_metrics(
                    nodes=all_node_ids,
                    deg_in={},
                    deg_out={},
                    pagerank={},
                    authority={},
                    hub={},
                )
                self.db.commit()
                return len(all_node_ids)

            # Build adjacency over the full node set so degree 0 items (orphans) are included.
            nodes = sorted(all_node_ids)
            out_adj, in_adj = self._build_adjacency(edges, nodes)

            deg_in = {n: len(in_adj[n]) for n in nodes}
            deg_out = {n: len(out_adj[n]) for n in nodes}

            pr = self._pagerank(out_adj, nodes)
            auth, hub = self._hits(out_adj, in_adj, nodes)

            # Persist: wipe and re-insert to keep it simple/idempotent
            self._persist_metrics(nodes, deg_in, deg_out, pr, auth, hub)
            self.db.commit()
            return len(nodes)
        finally:
            if close_db:
                try:
                    self.db.close()
                except Exception:
                    pass

    # ---------- Data Loading ----------
    def _load_edges(self, db: Session) -> List[Tuple[int, int]]:
        """
        Load directed edges (from_content_id -> to_content_id) for internal links that
        have a known to_content_id (skip edges to external URLs or unknown targets).
        """
        q = (
            db.query(ContentLink.from_content_id, ContentLink.to_content_id)
            .filter(ContentLink.is_internal.is_(True))
            .filter(ContentLink.to_content_id.isnot(None))
        )
        rows = q.all()
        # Ensure unique edges (avoid overweighting duplicates)
        uniq: set[Tuple[int, int]] = set()
        for frm, to in rows:
            if frm is None or to is None:
                continue
            if frm == to:
                # Avoid self-loops for centrality metrics stability
                continue
            uniq.add((int(frm), int(to)))
        return list(uniq)

    def _all_nodes_from_edges(self, edges: Iterable[Tuple[int, int]]) -> List[int]:
        s: set[int] = set()
        for u, v in edges:
            s.add(u)
            s.add(v)
        return sorted(s)

    def _build_adjacency(
        self, edges: Iterable[Tuple[int, int]], nodes: Iterable[int]
    ) -> Tuple[Dict[int, List[int]], Dict[int, List[int]]]:
        out_adj: Dict[int, List[int]] = {n: [] for n in nodes}
        in_adj: Dict[int, List[int]] = {n: [] for n in nodes}
        for u, v in edges:
            out_adj[u].append(v)
            in_adj[v].append(u)
        return out_adj, in_adj

    # ---------- Algorithms ----------
    def _pagerank(self, out_adj: Dict[int, List[int]], nodes: Iterable[int]) -> Dict[int, float]:
        """
        Power-iteration PageRank on a directed graph.
        """
        cfg = self.cfg
        nodes = list(nodes)
        n = len(nodes)
        if n == 0:
            return {}

        # Map node id to index for dense vectors
        idx = {node: i for i, node in enumerate(nodes)}
        pr = [1.0 / n] * n

        # Precompute out-degree and dangling nodes
        outdeg = [len(out_adj[node]) for node in nodes]
        dangling_idx = [i for i, d in enumerate(outdeg) if d == 0]

        for _ in range(cfg.max_iter):
            new_pr = [0.0] * n
            # Distribute from non-dangling
            for i, node in enumerate(nodes):
                outs = out_adj[node]
                if outs:
                    share = pr[i] / float(len(outs))
                    for v in outs:
                        new_pr[idx[v]] += cfg.damping * share

            # Distribute dangling mass uniformly
            if dangling_idx:
                dangling_mass = sum(pr[i] for i in dangling_idx)
                add = cfg.damping * dangling_mass / n
            else:
                add = 0.0

            # Teleportation + dangling
            base = (1.0 - cfg.damping) / n
            delta = 0.0
            for i in range(n):
                val = new_pr[i] + add + base
                delta += abs(val - pr[i])
                pr[i] = val

            if delta < cfg.tol:
                break

        return {node: pr[idx[node]] for node in nodes}

    def _hits(
        self,
        out_adj: Dict[int, List[int]],
        in_adj: Dict[int, List[int]],
        nodes: Iterable[int],
    ) -> Tuple[Dict[int, float], Dict[int, float]]:
        """
        Kleinberg's HITS algorithm (authority & hub scores), normalized each iteration.
        """
        nodes = list(nodes)
        if not nodes:
            return {}, {}

        # Initialize
        auth = {n: 1.0 for n in nodes}
        hub = {n: 1.0 for n in nodes}

        for _ in range(self.cfg.max_iter):
            # Update authority as sum of hubs of in-neighbors
            for n in nodes:
                auth[n] = sum(hub[i] for i in in_adj[n])
            # Normalize authority
            norm_a = (sum(v * v for v in auth.values()) or 1.0) ** 0.5
            for n in nodes:
                auth[n] /= norm_a

            # Update hub as sum of authorities of out-neighbors
            for n in nodes:
                hub[n] = sum(auth[j] for j in out_adj[n])
            # Normalize hub
            norm_h = (sum(v * v for v in hub.values()) or 1.0) ** 0.5
            for n in nodes:
                hub[n] /= norm_h

        return auth, hub

    # ---------- Persistence ----------
    def _persist_metrics(
        self,
        nodes: Iterable[int],
        deg_in: Dict[int, int],
        deg_out: Dict[int, int],
        pagerank: Dict[int, float],
        authority: Dict[int, float],
        hub: Dict[int, float],
    ) -> None:
        """
        Replace rows in graph_metrics for the given node set.
        """
        nodes = list(nodes)
        if not nodes:
            self.db.query(GraphMetric).delete()
            return

        # Remove any existing entries for these content_ids
        self.db.query(GraphMetric).filter(GraphMetric.content_id.in_(nodes)).delete(
            synchronize_session=False
        )

        now = datetime.utcnow()
        payload = []
        for cid in nodes:
            payload.append(
                GraphMetric(
                    content_id=cid,
                    degree_in=int(deg_in.get(cid, 0)),
                    degree_out=int(deg_out.get(cid, 0)),
                    pagerank=float(pagerank.get(cid, 0.0)) if pagerank else None,
                    authority=float(authority.get(cid, 0.0)) if authority else None,
                    hub=float(hub.get(cid, 0.0)) if hub else None,
                    last_computed_at=now,
                )
            )
        self.db.bulk_save_objects(payload)


# ---------- Public utilities for Phase 8 ----------
def build_link_index(db: Session) -> Dict[str, int]:
    """Return a mapping of normalized ContentItem.url -> ContentItem.id.
    Only rows with a non-null URL are included.
    """
    rows = db.query(ContentItem.id, ContentItem.url).filter(ContentItem.url.isnot(None)).all()
    index: Dict[str, int] = {}
    for cid, url in rows:
        norm = _normalize_url(url)
        if norm:
            index[norm] = int(cid)
    return index

def _make_absolute(to_url: str | None, base_url: str | None) -> str | None:
    if not to_url:
        return None
    from urllib.parse import urljoin
    if base_url:
        return urljoin(base_url, to_url)
    return to_url

def _resolve_links_for_content_id(
    db: Session,
    content_id: int,
    base_url: str | None,
    url_index: Dict[str, int],
) -> int:
    """
    Resolve internal links for a single content item by updating to_content_id
    based on the current url_index. Does not create or delete ContentLink rows.
    Returns number of rows updated.
    """
    if not url_index:
        return 0

    rows: List[ContentLink] = (
        db.query(ContentLink)
        .filter(ContentLink.from_content_id == content_id)
        .filter(ContentLink.is_internal.is_(True))
        .all()
    )
    updated = 0
    for row in rows:
        abs_url = _make_absolute(row.to_url, base_url)
        norm = _normalize_url(abs_url)

        candidates: list[str] = []
        if norm:
            candidates.append(norm)
            if norm.endswith("/"):
                candidates.append(norm.rstrip("/"))
            else:
                candidates.append(norm + "/")

        for c in candidates:
            if c and c in url_index:
                new_id = url_index[c]
                if row.to_content_id != new_id:
                    row.to_content_id = new_id
                    updated += 1
                break
    return updated

def resolve_unresolved_internal_links(db: Session) -> int:
    """
    Pass that attempts to resolve existing internal ContentLink rows whose
    to_content_id is NULL by matching normalized URLs against ContentItem.url.
    Returns number of links updated.
    """
    url_index = build_link_index(db)
    if not url_index:
        return 0

    # Join to fetch base page URL for each link's from_content_id
    rows = (
        db.query(ContentLink, ContentItem.url)
        .join(ContentItem, ContentItem.id == ContentLink.from_content_id)
        .filter(ContentLink.is_internal.is_(True))
        .filter(ContentLink.to_content_id.is_(None))
        .all()
    )

    updated = 0
    for link, base_url in rows:
        abs_url = _make_absolute(link.to_url, base_url)
        norm = _normalize_url(abs_url)

        candidates: list[str] = []
        if norm:
            candidates.append(norm)
            if norm.endswith("/"):
                candidates.append(norm.rstrip("/"))
            else:
                candidates.append(norm + "/")

        for c in candidates:
            if c and c in url_index:
                new_id = url_index[c]
                if link.to_content_id != new_id:
                    link.to_content_id = new_id
                    updated += 1
                break

    if updated:
        db.commit()
    return updated

def reextract_links(
    db: Session,
    items: Iterable[dict] | Iterable[int] | None = None,
) -> int:
    """Re-extract links for the provided items and persist into content_links.
    
    Parameters
    ----------
    db: Session
        SQLAlchemy session.
    items: Iterable[dict] | Iterable[int] | None
        If provided, each item should be either:
        - a dict with keys: `content_id` (int), `url` (str or None), and `html` (str), or
        - an int representing content_id (will be wrapped into dict with url=None and html="").
        If None, this function will **not**
        fetch HTML from the network; it simply returns 0 to keep tests fast
        and side-effect free. (The API layer can pass concrete items.)
    Returns
    -------
    int
        Number of `from_content_id` rows processed.
    """
    if not items:
        return 0

    url_index = build_link_index(db)
    processed = 0
    # We will determine per-item whether we have material (html or base_url) to work with.
    now = datetime.utcnow()

    try:
        for item in items:
            # Normalize item to dict with keys content_id, url, html
            if isinstance(item, dict):
                item_dict = item
            elif hasattr(item, '__table__') and hasattr(item, 'id'):
                # Assume SQLAlchemy ORM instance like ContentItem
                item_dict = {
                    "content_id": getattr(item, "id", None),
                    "url": getattr(item, "url", None),
                    "html": getattr(item, "html", "") or "",
                }
            elif isinstance(item, int):
                item_dict = {"content_id": item, "url": None, "html": ""}
            else:
                raise ValueError(f"Invalid item type: expected dict, ORM instance, or int, got {type(item)}")

            try:
                cid = int(item_dict["content_id"])  # raises if missing (intentional)
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(f"Item missing valid 'content_id': {item_dict}") from e

            base_url = item_dict.get("url")
            html = item_dict.get("html") or ""

            # If neither html nor url were provided, try to load from DB
            if (not (html.strip())) and (not base_url):
                db_item = db.query(ContentItem).get(cid)
                if db_item is not None:
                    base_url = base_url or getattr(db_item, "url", None)
                    # Prefer stored content if available
                    html_from_db = getattr(db_item, "content", None)
                    if isinstance(html_from_db, str):
                        html = html_from_db

            # Only proceed if we have *some* material; prefer to preserve if none
            has_html = bool(html and html.strip())
            has_base = base_url is not None
            had_material = bool(has_html or has_base)

            # Extract structured links (will be empty if no HTML)
            links: List[Link] = extract_links(html, base_url=base_url)

            if not had_material:
                # No URL or HTML to work with: do not wipe existing rows; skip clean/insert
                processed += 1
                continue

            if not has_html:
                # Resolve-only: keep existing rows and try to set to_content_id
                _resolve_links_for_content_id(db, cid, base_url, url_index)
                processed += 1
                continue

            # We have HTML: replace snapshot for this content item
            db.query(ContentLink).filter(ContentLink.from_content_id == cid).delete(
                synchronize_session=False
            )

            to_insert: List[ContentLink] = []
            for lk in links:
                to_cid = None
                abs_url = lk.to_url
                if lk.is_internal:
                    # Resolve relative URLs (e.g., "/pillar") against the page URL
                    abs_url = _make_absolute(lk.to_url, base_url)
                    norm = _normalize_url(abs_url)

                    # Try exact normalized match, then a trailing-slash variant
                    candidates: list[str] = []
                    if norm:
                        candidates.append(norm)
                        if norm.endswith("/"):
                            candidates.append(norm.rstrip("/"))
                        else:
                            candidates.append(norm + "/")

                    for c in candidates:
                        if c and c in url_index:
                            to_cid = url_index[c]
                            break

                to_insert.append(
                    ContentLink(
                        from_content_id=cid,
                        to_content_id=to_cid,
                        to_url=abs_url or lk.to_url,
                        anchor_text=lk.anchor_text,
                        rel=lk.rel,
                        nofollow=lk.nofollow,
                        is_internal=lk.is_internal,
                        created_at=now,
                    )
                )

            if to_insert:
                db.bulk_save_objects(to_insert)
            processed += 1
    except Exception as e:
        raise ValueError(f"Error processing items in reextract_links: {e}") from e

    db.commit()
    return processed

def compute_metrics(db: Session, cfg: GraphConfig | None = None) -> int:
    """Convenience facade that rebuilds graph metrics from content_links.
    Also attempts to resolve any unresolved internal links first.
    Returns the number of nodes written into graph_metrics.
    """
    try:
        resolve_unresolved_internal_links(db)
    except Exception:
        # Don't fail metric build if resolve step encounters a corner case
        pass
    return GraphBuilder(db=db, cfg=cfg).run()


# Convenience function

def recompute_graph_metrics(db: Session | None = None, cfg: GraphConfig | None = None) -> int:
    """
    One-shot helper for API or CLI to recompute metrics. Alias of compute_metrics().
    """
    return GraphBuilder(db=db, cfg=cfg).run()


# ---------- Export Utilities (Phase 6/Frontend graph viz) ----------

def _safe_getattr(obj, name: str, default=None):
    """Safely get an attribute from an ORM object without raising if missing."""
    try:
        return getattr(obj, name)
    except Exception:
        return default


def export_graph_json(
    db: Session,
    include_metrics: bool = True,
    include_fields: Tuple[str, ...] = ("url", "title", "cluster_id"),
) -> Dict[str, object]:
    """
    Export the current internal-link graph as a JSON-serializable dict for frontend viz.

    Structure
    ---------
    {
      "nodes": [
        {
          "id": <content_id>,
          "url": <url or None>,
          "title": <title or None>,
          "cluster_id": <cluster id if available>,
          "metrics": {"degree_in": int, "degree_out": int, "pagerank": float, "authority": float, "hub": float}
        },
        ...
      ],
      "edges": [
        {"source": <from_content_id>, "target": <to_content_id>},
        ...
      ],
      "meta": {"generated_at": iso8601_utc}
    }

    Notes
    -----
    - Only includes internal edges with a non-null `to_content_id` (same as metrics builder).
    - If `cluster_id` is not a column on ContentItem in this deployment, it will be omitted (None).
    """
    # 1) Load unique internal edges that resolve to a content_id
    rows = (
        db.query(ContentLink.from_content_id, ContentLink.to_content_id)
        .filter(ContentLink.is_internal.is_(True))
        .filter(ContentLink.to_content_id.isnot(None))
        .all()
    )

    uniq: set[Tuple[int, int]] = set()
    for frm, to in rows:
        if frm is None or to is None or frm == to:
            continue
        uniq.add((int(frm), int(to)))

    edges = [{"source": u, "target": v} for (u, v) in uniq]

    # 2) Collect node ids (from edges) and also any nodes that currently have metrics
    node_ids: set[int] = set()
    for u, v in uniq:
        node_ids.add(u)
        node_ids.add(v)

    if include_metrics:
        metric_ids = [cid for (cid,) in db.query(GraphMetric.content_id).all()]
        node_ids.update(int(x) for x in metric_ids)

    if not node_ids:
        return {"nodes": [], "edges": [], "meta": {"generated_at": datetime.utcnow().isoformat() + "Z"}}

    # 3) Fetch ContentItem metadata in one shot
    items: List[ContentItem] = (
        db.query(ContentItem).filter(ContentItem.id.in_(list(node_ids))).all()
    )
    by_id: Dict[int, ContentItem] = {int(obj.id): obj for obj in items}

    # 4) Fetch metrics if requested
    metrics_map: Dict[int, Dict[str, float | int]] = {}
    if include_metrics:
        mrows: List[GraphMetric] = (
            db.query(GraphMetric).filter(GraphMetric.content_id.in_(list(node_ids))).all()
        )
        for m in mrows:
            try:
                cid = int(m.content_id)
            except Exception:
                continue
            metrics_map[cid] = {
                "degree_in": int(m.degree_in or 0),
                "degree_out": int(m.degree_out or 0),
                "pagerank": float(m.pagerank or 0.0) if m.pagerank is not None else 0.0,
                "authority": float(m.authority or 0.0) if m.authority is not None else 0.0,
                "hub": float(m.hub or 0.0) if m.hub is not None else 0.0,
            }

    # 5) Assemble node payloads
    def _field(obj: ContentItem, name: str):
        if obj is None:
            return None
        # Gracefully handle deployments where certain fields may not exist
        if not hasattr(obj, name):
            return None
        return _safe_getattr(obj, name, None)

    nodes: List[Dict[str, object]] = []
    for cid in sorted(node_ids):
        ci = by_id.get(cid)
        node_obj: Dict[str, object] = {"id": cid}
        for f in include_fields:
            node_obj[f] = _field(ci, f)
        if include_metrics:
            node_obj["metrics"] = metrics_map.get(cid, {
                "degree_in": 0,
                "degree_out": 0,
                "pagerank": 0.0,
                "authority": 0.0,
                "hub": 0.0,
            })
        nodes.append(node_obj)

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {"generated_at": datetime.utcnow().isoformat() + "Z"},
    }


def compute_and_export_graph_json(
    db: Session,
    cfg: GraphConfig | None = None,
    include_metrics: bool = True,
    include_fields: Tuple[str, ...] = ("url", "title", "cluster_id"),
) -> Dict[str, object]:
    """Convenience helper: recompute graph metrics, then export JSON in one call."""
    compute_metrics(db, cfg=cfg)
    return export_graph_json(db, include_metrics=include_metrics, include_fields=include_fields)
