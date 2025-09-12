"""
Retrieval Pipeline Orchestrator (Phase 9)

This module wires together the Embedder, Vector Index, and (optional) Ranker
into a simple, testable workflow:

  index_all(db, site_id)  -> builds corpus and upserts vectors into the index
  query(db, site_id, q)   -> embeds query, vector-search, then optional re-rank

We keep the pipeline dependency-injected so unit tests can pass fakes/mocks
for the embedder / index / ranker independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
import logging

from sqlalchemy.orm import Session

try:
    # Preferred import path when used inside the project
    from src.db.models import ContentItem  # type: ignore
except Exception:  # pragma: no cover - fallback for tests/alt runners
    from db.models import ContentItem  # type: ignore

logger = logging.getLogger(__name__)


# ---------- Interfaces (to keep the pipeline decoupled) ----------------------


class Embedder(Protocol):
    """Embeds text into a vector."""

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]: ...
    def embed(self, text: str) -> List[float]: ...


class VectorIndex(Protocol):
    """Minimal vector index API used by the pipeline."""

    def upsert(
        self, items: Iterable[Tuple[int, List[float], Dict[str, Any]]]
    ) -> None: ...
    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        *,
        filter_site_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]: ...


class Ranker(Protocol):
    """Optional second-stage ranker."""

    def rerank(
        self, query: str, candidates: Sequence[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]: ...


# ---------- Data structures ---------------------------------------------------


@dataclass(frozen=True)
class PipelineConfig:
    """Config knobs for retrieval pipeline."""

    max_index_chars_per_doc: int = 3000  # simple safety cap
    search_candidates: int = 50  # first-stage recall
    default_top_k: int = 10  # final results to return
    text_field: str = "title"  # which field from ContentItem to embed


# ---------- Pipeline ----------------------------------------------------------


class RetrievalPipeline:
    """
    High-level orchestration of retrieval tasks.

    Dependencies (embedder, index, ranker) are injected so we can swap real
    implementations or test doubles.
    """

    def __init__(
        self,
        *,
        embedder: Embedder,
        index: VectorIndex,
        ranker: Optional[Ranker] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.embedder = embedder
        self.index = index
        self.ranker = ranker
        self.config = config or PipelineConfig()

    # ---- Indexing ----

    def index_all(self, db: Session, site_id: int) -> int:
        """
        Build corpus for a site and upsert vectors into the index.

        Returns the number of documents indexed.
        """
        docs = self._load_corpus(db, site_id)
        if not docs:
            logger.info("No documents found for site_id=%s; nothing to index", site_id)
            return 0

        texts = [self._doc_text(d) for d in docs]
        vectors = self.embedder.embed_texts(texts)

        payloads: List[Tuple[int, List[float], Dict[str, Any]]] = []
        for doc, vec in zip(docs, vectors):
            payloads.append(
                (
                    doc["id"],
                    vec,
                    {
                        "site_id": site_id,
                        "url": doc["url"],
                        "title": doc.get("title"),
                    },
                )
            )

        self.index.upsert(payloads)
        logger.info("Indexed %d documents for site_id=%s", len(payloads), site_id)
        return len(payloads)

    # ---- Querying ----

    def query(
        self,
        db: Session,
        site_id: int,
        query_text: str,
        *,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve documents for `query_text`, restricted to a site.

        1) Embed query
        2) Vector search (recall)
        3) Optional cross-encoder re-rank (precision)
        """
        if not query_text.strip():
            return []

        cfg = self.config
        qvec = self.embedder.embed(query_text)
        candidates = self.index.search(
            qvec,
            top_k=cfg.search_candidates,
            filter_site_id=site_id,
        )

        k = top_k or cfg.default_top_k

        if self.ranker and candidates:
            try:
                reranked = self.ranker.rerank(query_text, candidates, top_k=k)
                return reranked[:k]
            except Exception as e:  # defensive: ranking should never crash the API
                logger.exception("Ranker failed, falling back to ANN results: %s", e)

        # Fallback: first-stage results already sorted by similarity
        return candidates[:k]

    # ---- Helpers ----

    def _load_corpus(self, db: Session, site_id: int) -> List[Dict[str, Any]]:
        """Fetch minimal fields to index from the database."""
        # Only index items that have a URL and non-empty title/content
        items: List[ContentItem] = (
            db.query(ContentItem).filter(ContentItem.site_id == site_id).all()
        )
        docs: List[Dict[str, Any]] = []
        for it in items:
            text = getattr(it, self.config.text_field, None) or ""
            if not text:
                # You can expand to use `it.extracted_text` or `it.summary` later.
                continue
            docs.append({"id": it.id, "url": it.url, "title": it.title})
        return docs

    def _doc_text(self, doc: Dict[str, Any]) -> str:
        """Return the text that will be embedded, capped for safety."""
        text = doc.get("title") or ""
        if len(text) > self.config.max_index_chars_per_doc:
            return text[: self.config.max_index_chars_per_doc]
        return text
