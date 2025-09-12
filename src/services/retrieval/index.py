import numpy as np
from typing import List, Tuple, Any


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    if a.ndim > 1:
        a = a.flatten()
    if b.ndim > 1:
        b = b.flatten()
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom != 0 else 0.0


class InMemoryIndex:
    """Simple in-memory index storing embeddings and metadata."""

    def __init__(self):
        self.items: List[Tuple[np.ndarray, Any]] = []

    def add(self, embedding: np.ndarray, metadata: Any):
        self.items.append((embedding, metadata))

    def search(self, query_emb: np.ndarray, top_k: int = 5) -> List[Tuple[Any, float]]:
        """Return top-k results ranked by cosine similarity."""
        scored = [
            (meta, cosine_similarity(query_emb, emb)) for emb, meta in self.items
        ]
        return sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]


class SemanticRetriever:
    """Wrapper combining embedder and in-memory index."""

    def __init__(self, embedder):
        self.embedder = embedder
        self.index = InMemoryIndex()

    def add_content(self, text: str, metadata: Any):
        embedding = self.embedder.embed(text)
        self.index.add(np.array(embedding), metadata)

    def query(self, text: str, top_k: int = 5) -> List[Tuple[Any, float]]:
        query_emb = np.array(self.embedder.embed(text))
        return self.index.search(query_emb, top_k=top_k)


# --- Compatibility layer for smoke tests ---

class RetrievalIndex:
    """
    Minimal retrieval index API expected by tests.
    Internally wraps the existing SemanticRetriever + InMemoryIndex.
    """

    def __init__(self, embedder):
        self._retriever = SemanticRetriever(embedder)

    def add_document(self, text: str, metadata: Any) -> None:
        """Embed text and add to the in-memory index with its metadata."""
        self._retriever.add_content(text, metadata)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Any, float]]:
        """Return (metadata, score) results for the query."""
        return self._retriever.query(query, top_k=top_k)


def build_index(documents: List[Tuple[str, Any]], embedder) -> RetrievalIndex:
    """
    Convenience helper expected by tests:
    build an index from a list of (text, metadata) using the provided embedder.
    """
    idx = RetrievalIndex(embedder)
    for text, metadata in documents:
        idx.add_document(text, metadata)
    return idx


# Explicit export list to make intent clear
__all__ = [
    "cosine_similarity",
    "InMemoryIndex",
    "SemanticRetriever",
    "RetrievalIndex",
    "build_index",
]
