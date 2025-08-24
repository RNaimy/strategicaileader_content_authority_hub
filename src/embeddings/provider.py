

"""Embedding provider abstraction and a deterministic hash-based fallback.

Phase 2 goal: keep the clustering code decoupled from the embedding
implementation so we can swap in a real model (e.g., OpenAI/Azure, local
vectorizer) without touching callers.

Usage:

    from src.embeddings.provider import get_embedding_provider
    provider = get_embedding_provider()
    vec = provider.embed_text("some text")
    vecs = provider.embed_texts(["a", "b"]) 

ENV:
- EMBEDDING_PROVIDER: selects the provider. Defaults to 'hash64'.
  You can also specify 'hash{D}' where D is the dimension, e.g., 'hash128'.
- EMBEDDING_DIM: optional override for dimension (int), used by hash provider.
"""
from __future__ import annotations

import os
import math
import hashlib
from abc import ABC, abstractmethod
from typing import Iterable, List

import numpy as np


# --------------------------- Base Abstraction --------------------------- #

class EmbeddingProvider(ABC):
    """Minimal provider interface.

    Providers must return a list[float] for a single text and list[list[float]]
    for a batch. All vectors should be the same dimension.
    """

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        raise NotImplementedError

    @abstractmethod
    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def dim(self) -> int:
        raise NotImplementedError


# --------------------- Deterministic Hash Provider ---------------------- #

class DeterministicHashEmbeddingProvider(EmbeddingProvider):
    """Fast, dependency-light, deterministic embeddings for testing.

    We map text -> seed via md5, generate a normal vector with that seed,
    then L2-normalize. This preserves cosine geometry enough for
    development and is *deterministic* across runs.
    """

    def __init__(self, dim: int = 64) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = int(dim)

    @property
    def dim(self) -> int:
        return self._dim

    def _embed_one(self, text: str) -> np.ndarray:
        # md5 is stable and available everywhere
        h = hashlib.md5(text.encode("utf-8")).digest()
        # Use 4 bytes to seed a RandomState for determinism
        seed = int.from_bytes(h[:4], byteorder="big", signed=False)
        rng = np.random.RandomState(seed)
        vec = rng.normal(loc=0.0, scale=1.0, size=self._dim).astype(np.float32)
        # L2 normalize (avoid div by zero)
        norm = float(np.linalg.norm(vec))
        if norm == 0.0 or math.isclose(norm, 0.0):
            return vec
        return (vec / norm).astype(np.float32)

    def embed_text(self, text: str) -> List[float]:
        return self._embed_one(text).tolist()

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        return [self._embed_one(t).tolist() for t in texts]


# ----------------------------- Factory --------------------------------- #

def _parse_hash_provider_name(name: str, default_dim: int) -> int:
    """Parse names like 'hash64' -> 64. Returns default_dim if not specified."""
    if not name.startswith("hash"):
        return default_dim
    suffix = name[4:]
    if not suffix:
        return default_dim
    try:
        return max(1, int(suffix))
    except ValueError:
        return default_dim


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = os.getenv("EMBEDDING_PROVIDER", "hash64").strip().lower()
    # dimension resolution order: EMBEDDING_DIM env override > parsed from name > default 64
    env_dim = os.getenv("EMBEDDING_DIM")
    default_dim = 64

    if provider_name.startswith("hash"):
        dim = default_dim
        if env_dim:
            try:
                dim = max(1, int(env_dim))
            except ValueError:
                dim = default_dim
        else:
            dim = _parse_hash_provider_name(provider_name, default_dim)
        return DeterministicHashEmbeddingProvider(dim=dim)

    # Placeholder for future providers (OpenAI, Azure, etc.)
    # if provider_name in {"openai", "azure_openai"}:
    #     return OpenAIEmbeddingProvider(...)

    # Fallback to hash64 if unknown provider requested
    return DeterministicHashEmbeddingProvider(dim=default_dim)


# ---------------------------- Convenience ------------------------------ #

def embed_text(text: str) -> List[float]:
    return get_embedding_provider().embed_text(text)


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    return get_embedding_provider().embed_texts(texts)