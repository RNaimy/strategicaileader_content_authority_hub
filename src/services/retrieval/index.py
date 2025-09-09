<instructions>
- Inside `src/services/retrieval/index.py`, add a new module to support semantic retrieval.
- Define an `InMemoryIndex` class that stores embeddings and provides search.
- Define a `SemanticRetriever` class that wraps the embedder and index, with methods to add content and query by semantic similarity.
- Ensure cosine similarity scoring is used, returning top-k results with scores.
</instructions>
