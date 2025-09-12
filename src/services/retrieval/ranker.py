"""Lightweight ranking utilities for semantic retrieval.

This module provides:
- BM25Ranker: simple lexical scorer you can feed documents into and query.
- rrf_combine: reciprocal-rank-fusion over multiple ranked lists.
- HybridRanker: combines a semantic index (implements `.search`) with BM25 using RRF.

It’s intentionally dependency-free and fast enough for tests / small corpora.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple, Sequence, Optional
import math
import re

# ----------------------------
# Common types
# ----------------------------


@dataclass(frozen=True)
class ScoredHit:
    id: int
    score: float


# ----------------------------
# Tiny tokenizer
# ----------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_STOP = {
    # minimal list, just enough to reduce noise
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "as",
    "at",
    "from",
    "that",
    "this",
    "it",
}


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOP]


# ----------------------------
# BM25 Ranker (Okapi)
# ----------------------------


class BM25Ranker:
    """Very small BM25 implementation.

    Usage:
        bm = BM25Ranker()
        bm.add(doc_id, text)
        hits = bm.search("query text", top_k=10)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._df: Dict[str, int] = {}
        self._tf: Dict[int, Dict[str, int]] = {}
        self._doc_len: Dict[int, int] = {}
        self._N = 0
        self._avgdl = 0.0

    def add(self, doc_id: int, text: str) -> None:
        tokens = _tokenize(text)
        if not tokens:
            tokens = [""]  # avoid div-by-zero later; token that won't match query
        self._N += 1
        self._doc_len[doc_id] = len(tokens)
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        self._tf[doc_id] = tf
        for t in set(tokens):
            self._df[t] = self._df.get(t, 0) + 1
        self._avgdl = sum(self._doc_len.values()) / self._N

    def _idf(self, term: str) -> float:
        # BM25+ idf variant with 0.5 smoothing
        df = self._df.get(term, 0)
        if df == 0 or self._N == 0:
            return 0.0
        return math.log(1 + (self._N - df + 0.5) / (df + 0.5))

    def score(self, query: str, doc_id: int) -> float:
        if doc_id not in self._tf:
            return 0.0
        tokens = _tokenize(query)
        dl = self._doc_len.get(doc_id, 0)
        if dl == 0:
            return 0.0
        K = self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1.0))
        score = 0.0
        tf = self._tf[doc_id]
        for q in tokens:
            f = tf.get(q, 0)
            if f == 0:
                continue
            idf = self._idf(q)
            score += idf * (f * (self.k1 + 1)) / (f + K)
        return score

    def search(self, query: str, top_k: int = 10) -> List[ScoredHit]:
        if self._N == 0:
            return []
        pairs = [(doc_id, self.score(query, doc_id)) for doc_id in self._tf.keys()]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return [ScoredHit(id=d, score=s) for d, s in pairs[:top_k] if s > 0]


# ----------------------------
# Reciprocal Rank Fusion (RRF)
# ----------------------------


def rrf_combine(
    ranked_lists: Sequence[Sequence[ScoredHit]],
    k: int = 10,
    rank_constant: int = 60,
) -> List[ScoredHit]:
    """Combine multiple ranked lists via Reciprocal Rank Fusion.

    Each list is treated equally; only ranks matter, not raw scores.
    """
    scores: Dict[int, float] = {}
    for hits in ranked_lists:
        for rank, hit in enumerate(hits, start=1):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (rank_constant + rank)
    out = [ScoredHit(id=i, score=s) for i, s in scores.items()]
    out.sort(key=lambda h: h.score, reverse=True)
    return out[:k]


# ----------------------------
# Hybrid ranker
# ----------------------------


class HybridRanker:
    """Fuse semantic vector search with BM25 via RRF.

    The `semantic_index` object must expose a `search(query: str, top_k: int) -> List[ScoredHit]`
    returning integer IDs compatible with BM25 document IDs.
    """

    def __init__(self, semantic_index, bm25: Optional[BM25Ranker] = None) -> None:
        self.semantic_index = semantic_index
        self.bm25 = bm25 or BM25Ranker()

    def add_document(
        self, doc_id: int, text: str, vector: Optional[Sequence[float]] = None
    ) -> None:
        # semantic_index is responsible for consuming vectors; we try to call a common interface
        if hasattr(self.semantic_index, "add"):
            if vector is not None:
                self.semantic_index.add(doc_id, vector)
            else:
                # if index knows how to embed internally
                self.semantic_index.add(doc_id, text)  # type: ignore[arg-type]
        self.bm25.add(doc_id, text)

    def search(self, query: str, top_k: int = 10, rrf_k: int = 60) -> List[ScoredHit]:
        sem_hits = []
        if hasattr(self.semantic_index, "search"):
            sem_hits = self.semantic_index.search(query, top_k=top_k)  # type: ignore[attr-defined]
        lex_hits = self.bm25.search(query, top_k=top_k)
        return rrf_combine([sem_hits, lex_hits], k=top_k, rank_constant=rrf_k)


__all__ = [
    "ScoredHit",
    "BM25Ranker",
    "rrf_combine",
    "HybridRanker",
]
