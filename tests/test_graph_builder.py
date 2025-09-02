
from src.services.graph_builder import reextract_links


def test_reextract_links_accepts_int_ids():
    """Test that reextract_links accepts a list of integer content_ids without raising exceptions."""
    content_ids = [1, 2, 3]
    db_session = None  # Dummy session for unit-level test
    try:
        reextract_links(db_session, content_ids)
    except Exception as e:
        pytest.fail(f"reextract_links raised an exception with int ids: {e}")

import pytest

# Test the link extractor first (fast, no DB)
from src.services.link_extractor import extract_links


def test_extract_links_from_html():
    base_url = "https://example.com/posts/intro"
    html = (
        '<a href="/posts/deep-dive" rel="noopener">Read more</a>'
        '<a href="https://external.com/page" rel="nofollow">ext</a>'
        '<a href="#section">anchor</a>'
        '<a href="mailto:test@example.com">email</a>'
    )

    links = extract_links(html, base_url=base_url)

    # Expect only http(s) links, normalized and classified
    # Internal link should resolve against base_url
    internal = [l for l in links if l.is_internal]
    external = [l for l in links if not l.is_internal]

    assert any(
        l.to_url.startswith("https://example.com/posts/deep-dive") for l in internal
    ), links
    assert any(
        l.to_url.startswith("https://external.com/page") and l.nofollow is True
        for l in external
    ), links


# Optional smoke test for GraphBuilder if present. It will be xfailed until implemented.

gb = pytest.importorskip("src.services.graph_builder", reason="graph_builder not implemented yet")


@pytest.mark.xfail(reason="GraphBuilder build() behavior not finalized; enable when implemented")
def test_graph_builder_smoke(tmp_path):
    """Smoke test: ensure GraphBuilder module exposes a GraphBuilder class with build() method.
    This test doesn't assert DB side-effects yet; it just ensures the method can be invoked
    with minimal arguments without throwing (once implemented).
    """
    # Minimal content corpus
    docs = [
        {
            "id": 1,
            "url": "https://example.com/posts/intro",
            "html": '<a href="/posts/deep-dive">next</a>',
        },
        {
            "id": 2,
            "url": "https://example.com/posts/deep-dive",
            "html": '<a href="https://example.com/posts/intro">prev</a>',
        },
    ]

    # Instantiate and call. The concrete signature may evolve; adjust in implementation & un-xfail.
    builder_cls = getattr(gb, "GraphBuilder")
    builder = builder_cls()
    builder.build(docs)