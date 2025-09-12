"""
Lightweight embedding abstraction for Phase 9: Semantic Retrieval.

We provide a default, dependency-free "LocalHasherEmbedder" that turns text
into deterministic unit-length vectors using SHA-256. This keeps CI simple and
allows development without external services. If you set EMBEDDINGS_PROVIDER=openai
and have the `openai` package installed with OPENAI_API_KEY configured, we'll
use OpenAI embeddings instead.

Env vars:
- EMBEDDINGS_PROVIDER: "local" (default) or "openai"
- EMBEDDINGS_MODEL: model name for the provider (default depends on provider)
- EMBEDDINGS_DIM: integer; only used by local embedder (default 384)
- OPENAI_API_KEY: required for openai provider

Usage:
    from src.services.retrieval.embedder import get_embedder
    embedder = get_embedder()
    v = embedder.embed("hello world")
    V = embedder.embed_texts(["a", "b", "c"])
"""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from typing import Iterable, List, Sequence


# ---------------------------
# Base interface / contracts
# ---------------------------


class Embedder:
    """Minimal embedding interface used across the retrieval module."""

    model_name: str

    def embed(self, text: str) -> List[float]:
        """Embed a single string into a vector."""
        raise NotImplementedError

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a sequence of strings into vectors, in order."""
        # Default naive batching
        return [self.embed(t) for t in texts]

    @property
    def dimension(self) -> int:
        raise NotImplementedError


# ---------------------------
# Local, dependency-free embedder
# ---------------------------


@dataclass
class LocalHasherEmbedder(Embedder):
    """
    Deterministic, dependency-free embedder.

    Converts text to a fixed-size vector by:
    1) Taking SHA-256 of UTF-8 bytes.
    2) Expanding the 32-byte digest to requested dimension by repeating bytes.
    3) Mapping bytes to floats in [0, 1] and L2-normalizing.

    This is *not* semantically meaningful like a real embedder, but it's
    perfectly stable and fast for tests and local development.
    """

    dim: int = 384
    model_name: str = "local/sha256-hash-embedder"

    def _raw_bytes(self, text: str) -> bytes:
        return hashlib.sha256(text.encode("utf-8")).digest()

    def embed(self, text: str) -> List[float]:
        if self.dim <= 0:
            raise ValueError("dimension must be positive")
        digest = self._raw_bytes(text)
        # Expand digest deterministically to desired dimension
        vals = [digest[i % len(digest)] / 255.0 for i in range(self.dim)]
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        return [self.embed(t or "") for t in texts]

    @property
    def dimension(self) -> int:
        return self.dim


# ---------------------------
# OpenAI provider (optional)
# ---------------------------


class OpenAIEmbedder(Embedder):
    """
    Thin wrapper over OpenAI embeddings, imported lazily.

    Requires:
      - `pip install openai>=1`
      - OPENAI_API_KEY env var
    """

    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        self.model_name = model_name
        # Lazy import to avoid hard dependency in CI
        try:
            import openai  # type: ignore
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover - import guard
            raise RuntimeError(
                "OpenAI provider requested but `openai` package not available."
            ) from e
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:  # pragma: no cover - runtime config guard
            raise RuntimeError("OPENAI_API_KEY not set for OpenAIEmbedder")
        # Modern client
        self._client = OpenAI(api_key=api_key)  # type: ignore

        # probe dimension (cheap single call with empty text)
        try:
            resp = self._client.embeddings.create(model=self.model_name, input="")  # type: ignore
            self._dimension = len(resp.data[0].embedding)
        except Exception as e:  # pragma: no cover - network guard
            # Fallback to common dimension for known models
            self._dimension = 1536 if "3-small" in self.model_name else 3072
            # We don't raise here to keep dev experience smooth.

    def embed(self, text: str) -> List[float]:
        # Avoid network if text is empty; return zero-like unit vector
        if text is None:
            text = ""
        resp = self._client.embeddings.create(  # type: ignore
            model=self.model_name,
            input=text,
        )
        return list(resp.data[0].embedding)  # type: ignore

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        # Batched request when possible
        payload = [t or "" for t in texts]
        resp = self._client.embeddings.create(  # type: ignore
            model=self.model_name,
            input=payload,
        )
        return [list(d.embedding) for d in resp.data]  # type: ignore

    @property
    def dimension(self) -> int:
        return getattr(self, "_dimension", 1536)


# ---------------------------
# Factory
# ---------------------------


def get_embedder() -> Embedder:
    """
    Choose an embedder based on environment configuration.
    Defaults to LocalHasherEmbedder for zero-dependency reliability.
    """
    provider = (os.getenv("EMBEDDINGS_PROVIDER") or "local").lower()
    if provider == "openai":
        model = os.getenv("EMBEDDINGS_MODEL") or "text-embedding-3-small"
        try:
            return OpenAIEmbedder(model_name=model)
        except Exception:
            # Fall back to local if OpenAI is not available/misconfigured.
            pass

    # Local fallback
    dim_str = os.getenv("EMBEDDINGS_DIM")
    dim = int(dim_str) if (dim_str and dim_str.isdigit()) else 384
    return LocalHasherEmbedder(dim=dim)
