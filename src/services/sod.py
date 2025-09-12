"""
Phase 10 — Semantic Overlap & Density (SOD)
-------------------------------------------

This module computes two lightweight, DB-backed metrics for each content item:

1) sod_overlap_score  ∈ [0,1]
   A semantic "overlap with the site centroid" score. If embeddings are present
   on content_items.embedding (list[float] or JSON), we use cosine similarity
   vs. the mean vector for the site. If embeddings are missing, we fall back to
   token overlap over the title (Jaccard).

2) sod_density_score  ∈ [0,1]
   A link-density proxy based on internal graph degree. We compute
   (in_degree + out_degree) / max_degree within the site, using the
   content_links table (internal links only, when flagged).

Both numbers are meant to be quick heuristics that are:
- Fast: single SQL pass + small in-memory math
- Robust: degrade gracefully when data is sparse
- Interpretable: higher = “more central / well-connected”

NOTE: These are intentionally simple and deterministic so they can be run
      locally without an embedding service. If you later adopt a different
      embedder or clustering, you can swap the vectorization below.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import math
import json
import re
from collections import defaultdict

from sqlalchemy.orm import Session

try:
    # Prefer numpy for speed if available, but the math works fine without it.
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore

from src.db.models import ContentItem, ContentLink


# ----------------------------- Vector helpers ----------------------------- #


def _to_vector(embedding: Optional[object]) -> Optional[List[float]]:
    """
    Try to coerce a DB-stored embedding into a Python list[float].
    Supports: list, tuple, JSON string, or None.
    Returns None if it can't be interpreted.
    """
    if embedding is None:
        return None
    if isinstance(embedding, (list, tuple)):
        try:
            return [float(x) for x in embedding]
        except Exception:
            return None
    if isinstance(embedding, (bytes, bytearray)):
        # Some ORMs may store JSON as bytes
        try:
            data = json.loads(embedding.decode("utf-8"))
            return [float(x) for x in data]
        except Exception:
            return None
    if isinstance(embedding, str):
        try:
            data = json.loads(embedding)
            return [float(x) for x in data]
        except Exception:
            return None
    return None


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in [0,1] (return 0 if a or b is all-zero)."""
    # Manual fast-path to avoid hard numpy dependency.
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    sim = dot / (math.sqrt(na) * math.sqrt(nb))
    # Map [-1,1] -> [0,1] just in case
    return max(0.0, min(1.0, 0.5 * (sim + 1.0)))


def _mean_vector(vectors: List[List[float]]) -> Optional[List[float]]:
    if not vectors:
        return None
    length = len(vectors[0])
    # ensure all same length
    safe = [v for v in vectors if len(v) == length]
    if not safe:
        return None
    if np is not None:
        arr = np.asarray(safe, dtype=float)
        return arr.mean(axis=0).tolist()
    # Pure python mean
    sums = [0.0] * length
    for v in safe:
        for i, val in enumerate(v):
            sums[i] += val
    return [s / len(safe) for s in sums]


# ----------------------------- Token helpers ----------------------------- #


def _tokens(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [
        t
        for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
        if t
    ]


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa = set(a)
    sb = set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    if union == 0:
        return 0.0
    return inter / union


# ------------------------------- Core logic ------------------------------- #


def _load_site_vectors(
    db: Session, site_id: int
) -> Tuple[List[Tuple[ContentItem, Optional[List[float]]]], Optional[List[float]]]:
    """Return (items_with_vectors, centroid_vector)."""
    items: List[ContentItem] = (
        db.query(ContentItem).filter(ContentItem.site_id == site_id).all()
    )
    pairs: List[Tuple[ContentItem, Optional[List[float]]]] = []
    vectors: List[List[float]] = []

    for it in items:
        vec = _to_vector(getattr(it, "embedding", None))
        pairs.append((it, vec))
        if vec is not None:
            vectors.append(vec)

    centroid = _mean_vector(vectors)
    return pairs, centroid


def _compute_overlap_scores(
    pairs: List[Tuple[ContentItem, Optional[List[float]]]],
    centroid_vec: Optional[List[float]],
) -> Dict[int, float]:
    """
    For items with an embedding, compute cosine vs. centroid.
    For items without an embedding, fall back to Jaccard(title, centroid-tokens) ~ 0
    (i.e., we will just use title-to-title Jaccard average if no centroid is available).
    """
    scores: Dict[int, float] = {}

    # If some items don't have vectors, precompute a "centroid token bag"
    # by concatenating all titles. This is a reasonable fallback.
    titles = [it.title or "" for it, _ in pairs]
    centroid_tokens = _tokens(" ".join(titles)) if titles else []

    for it, vec in pairs:
        score = 0.0
        if vec is not None and centroid_vec is not None:
            score = _cosine(vec, centroid_vec)
        else:
            # fallback to token overlap
            score = _jaccard(_tokens(it.title or ""), centroid_tokens)
        # clamp to [0,1]
        scores[it.id] = max(0.0, min(1.0, float(score)))
    return scores


def _compute_density_scores(db: Session, site_id: int) -> Dict[int, float]:
    """
    Build an internal-degree score in [0,1] for each content item:
      density = (in_degree + out_degree) / max_degree
    where in/out are counted from content_links rows. If the table is empty,
    all density scores are 0.
    """
    # out-degree counts
    out_counts: Dict[int, int] = defaultdict(int)
    in_counts: Dict[int, int] = defaultdict(int)

    # Count links for this site. We consider "internal" by is_internal flag if present;
    # but for robustness (older schemas), we will treat NULL as internal for same-domain edges.
    q = (
        db.query(ContentLink)
        .join(ContentItem, ContentItem.id == ContentLink.from_content_id)
        .filter(ContentItem.site_id == site_id)
    )
    for link in q:
        out_counts[link.from_content_id] += 1
        if link.to_content_id:
            in_counts[link.to_content_id] += 1

    # Collect all item ids in scope
    item_ids = {cid for cid in out_counts.keys()} | {cid for cid in in_counts.keys()}
    if not item_ids:
        return {}

    degrees: Dict[int, int] = {}
    maxdeg = 0
    for cid in item_ids:
        deg = out_counts.get(cid, 0) + in_counts.get(cid, 0)
        degrees[cid] = deg
        maxdeg = max(maxdeg, deg)

    if maxdeg == 0:
        return {cid: 0.0 for cid in item_ids}

    return {cid: float(deg) / float(maxdeg) for cid, deg in degrees.items()}


# ----------------------- Extractability (heuristic) ----------------------- #

_SENT_END_RE = re.compile(r"[.!?][\"')\]]?\s+$")
_BULLET_RE = re.compile(r"^\s*([-*•]+|\d+\.)\s+")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6}\s|\w[\w\s]{0,40}\s?:\s?$)")


def _split_blocks(text: str) -> List[str]:
    """
    Split content into lightweight 'blocks' using blank lines and headings/bullets as boundaries.
    Keeps order; trims whitespace; drops empty blocks.
    """
    if not text:
        return []
    # Normalize newlines
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split on blank lines first
    raw = [b.strip() for b in re.split(r"\n\s*\n", t)]
    blocks: List[str] = []
    for b in raw:
        if not b:
            continue
        # Further split when a heading/bullet appears mid-block
        lines = b.split("\n")
        cur: List[str] = []
        for ln in lines:
            if _HEADING_RE.match(ln) or _BULLET_RE.match(ln):
                if cur:
                    blocks.append("\n".join(cur).strip())
                    cur = []
                blocks.append(ln.strip())
            else:
                cur.append(ln)
        if cur:
            blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


def _looks_like_complete_sentence(s: str) -> bool:
    """
    Very cheap completeness heuristic: at least ~40 characters, contains a space,
    and ends with sentence punctuation.
    """
    if not s:
        return False
    s_stripped = s.strip()
    if len(s_stripped) < 40:
        return False
    if " " not in s_stripped:
        return False
    return bool(_SENT_END_RE.search(s_stripped + " "))


def _is_quotable_block(block: str) -> bool:
    """
    Heuristics for a quotable block:
      - A heading alone is not quotable
      - Bulleted line by itself is quotable if it has 6+ words
      - Paragraph with >= 1 complete sentence is quotable
    """
    if not block:
        return False
    line_count = block.count("\n") + 1
    first_line = block.split("\n", 1)[0]
    if _HEADING_RE.match(first_line) and line_count == 1:
        return False
    if _BULLET_RE.match(first_line) and line_count == 1:
        return len(first_line.split()) >= 6
    # For paragraphs or multi-line blocks, require at least one complete sentence
    sentences = re.split(r"(?<=[.!?])\s+", block.strip())
    return any(_looks_like_complete_sentence(s) for s in sentences)


def compute_extractability_for_text(text: Optional[str]) -> Tuple[float, int, int]:
    """
    Return (extractability_score [0,1], total_blocks, quotable_blocks).
    Score = quotable_blocks / max(total_blocks, 1).
    """
    if not text:
        return 0.0, 0, 0
    blocks = _split_blocks(text)
    if not blocks:
        return 0.0, 0, 0
    quotable = sum(1 for b in blocks if _is_quotable_block(b))
    score = float(quotable) / float(len(blocks))
    return max(0.0, min(1.0, round(score, 4))), len(blocks), quotable


# ------------------------------ Public API ------------------------------- #


def recompute_sod_for_site(db: Session, site_id: int) -> Dict[str, object]:
    """
    Compute & persist SOD metrics for all items in a site.
    Writes:
      - ContentItem.sod_overlap_score
      - ContentItem.sod_density_score
    Returns a small summary dict.
    """
    pairs, centroid = _load_site_vectors(db, site_id)
    overlap_scores = _compute_overlap_scores(pairs, centroid)
    density_scores = _compute_density_scores(db, site_id)

    # Compute extractability per item using the raw content field (when present)
    # Fallback to title-only if content is missing.
    extractability: Dict[int, Tuple[float, int, int]] = {}
    for it, _ in pairs:
        text = (it.content or "") if hasattr(it, "content") else (it.title or "")
        score, total_blocks, quotable_blocks = compute_extractability_for_text(
            text or ""
        )
        extractability[it.id] = (score, total_blocks, quotable_blocks)

    updated = 0
    for it, _ in pairs:
        ov = round(overlap_scores.get(it.id, 0.0), 4)
        de = round(density_scores.get(it.id, 0.0), 4)
        ex_score, ex_blocks, _ = extractability.get(it.id, (0.0, 0, 0))
        changed = False

        if getattr(it, "sod_overlap_score", None) != ov:
            it.sod_overlap_score = ov  # type: ignore[attr-defined]
            changed = True
        if getattr(it, "sod_density_score", None) != de:
            it.sod_density_score = de  # type: ignore[attr-defined]
            changed = True
        # Optional columns: only set if the ORM model has them
        if (
            hasattr(it, "extractability_score")
            and getattr(it, "extractability_score", None) != ex_score
        ):
            it.extractability_score = ex_score  # type: ignore[attr-defined]
            changed = True
        if hasattr(it, "chunk_count") and getattr(it, "chunk_count", None) != ex_blocks:
            it.chunk_count = ex_blocks  # type: ignore[attr-defined]
            changed = True

        if changed:
            updated += 1

    if updated:
        db.commit()

    return {
        "ok": True,
        "site_id": site_id,
        "total_items": len(pairs),
        "updated": updated,
        "centroid_used": centroid is not None,
        "extractability": {
            "items_with_blocks": sum(1 for _, v in extractability.items() if v[1] > 0),
            "avg_score": round(
                (
                    sum(v[0] for v in extractability.values())
                    / max(len(extractability), 1)
                ),
                4,
            ),
        },
    }
