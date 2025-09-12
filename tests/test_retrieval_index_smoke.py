import importlib

def test_index_module_importable():
    index = importlib.import_module("src.services.retrieval.index")
    assert hasattr(index, "build_index") or hasattr(index, "RetrievalIndex")

def test_build_index_and_search_basic():
    from src.services.retrieval.index import build_index
    docs = [
        ("doc1", "Internal linking boosts topical authority."),
        ("doc2", "Alembic manages database schema migrations."),
        ("doc3", "Use alembic upgrade head to apply migrations."),
    ]
    idx = build_index(docs)
    results = idx.search("How do I handle database migrations?", top_k=2)
    assert len(results) >= 1
    assert results[0][0] in {"doc2", "doc3", "doc1"}

def test_add_documents_then_search_with_class():
    from src.services.retrieval.index import RetrievalIndex
    idx = RetrievalIndex()
    idx.add_documents([
        ("a", "Embeddings turn text into vectors."),
        ("b", "Internal links distribute authority across a site."),
        ("c", "Chunking content helps retrieval granularity."),
    ])
    hits = idx.search("How do I split content for retrieval?", top_k=2)
    assert hits and hits[0][0] in {"c", "a", "b"}
