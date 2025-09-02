import pytest
import uuid
from src.db.models import ContentItem, ContentLink, Site
from src.services.graph_builder import export_graph_json, compute_and_export_graph_json


@pytest.fixture()
def site(db):
    domain = f"test-{uuid.uuid4().hex}.local"
    s = Site(name=f"Test {domain}", domain=domain)
    db.add(s)
    db.commit()
    return s


def test_export_round_trip(db, site):
    a = ContentItem(site_id=site.id, url="https://x.com/a", title="A")
    b = ContentItem(site_id=site.id, url="https://x.com/b", title="B")
    db.add_all([a, b]); db.commit()
    db.add_all([
        ContentLink(from_content_id=a.id, to_url="/b", is_internal=True),
        ContentLink(from_content_id=b.id, to_url="/a", is_internal=True),
    ]); db.commit()

    out = compute_and_export_graph_json(db)
    ids = {n["id"] for n in out["nodes"]}
    # our two nodes should be present (other nodes may exist in the DB)
    assert {a.id, b.id} <= ids
    edge_pairs = {(e["source"], e["target"]) for e in out["edges"]}
    assert (a.id, b.id) in edge_pairs
    assert (b.id, a.id) in edge_pairs
    for n in out["nodes"]:
        if n["id"] in {a.id, b.id}:
            m = n["metrics"]
            assert {"degree_in", "degree_out", "pagerank", "authority", "hub"} <= m.keys()


def test_export_without_metrics(db):
    out = export_graph_json(db, include_metrics=False)
    for n in out["nodes"]:
        assert "metrics" not in n


def test_duplicate_and_self_loop_filtered(db, site):
    a = ContentItem(site_id=site.id, url="https://y.com/a", title="A"); db.add(a); db.commit()
    # Add a self-link (and a duplicate) — should be filtered out in export
    db.add_all([
        ContentLink(from_content_id=a.id, to_url="/a", is_internal=True),
        ContentLink(from_content_id=a.id, to_url="/a", is_internal=True),
    ]); db.commit()

    out = compute_and_export_graph_json(db)
    # no self-loop edges for this content id (other edges may exist globally)
    assert not any(e["source"] == a.id and e["target"] == a.id for e in out["edges"])


def test_cluster_id_and_meta_timestamp(db, site):
    # Only run this if ContentItem has a cluster_id column in this deployment
    if not hasattr(ContentItem, "cluster_id"):
        pytest.skip("cluster_id column not present on ContentItem")

    item = ContentItem(site_id=site.id, url="https://z.com/item", title="Item", cluster_id=42)
    db.add(item)
    db.commit()

    # Add a peer and a link so that exporter includes our node
    peer = ContentItem(site_id=site.id, url="https://z.com/peer", title="Peer")
    db.add(peer); db.commit()
    db.add(ContentLink(from_content_id=item.id, to_url="/peer", is_internal=True)); db.commit()

    out = compute_and_export_graph_json(db)
    node = next((n for n in out["nodes"] if n["id"] == item.id), out["nodes"][0])
    assert node.get("cluster_id") == 42

    assert "meta" in out and "generated_at" in out["meta"]
    assert isinstance(out["meta"]["generated_at"], str)
    assert out["meta"]["generated_at"].endswith("Z")


def test_relative_url_resolution_multi_site(db):
    # site A
    s1 = Site(name="Test A", domain="a.local"); db.add(s1); db.commit()
    a1 = ContentItem(site_id=s1.id, url="https://a.local/a", title="A1"); db.add(a1); db.commit()
    b1 = ContentItem(site_id=s1.id, url="https://a.local/b", title="B1"); db.add(b1); db.commit()
    db.add(ContentLink(from_content_id=a1.id, to_url="/b", is_internal=True)); db.commit()

    # site B
    s2 = Site(name="Test B", domain="b.local"); db.add(s2); db.commit()
    a2 = ContentItem(site_id=s2.id, url="https://b.local/a", title="A2"); db.add(a2); db.commit()
    b2 = ContentItem(site_id=s2.id, url="https://b.local/b", title="B2"); db.add(b2); db.commit()
    db.add(ContentLink(from_content_id=a2.id, to_url="/b", is_internal=True)); db.commit()

    out = compute_and_export_graph_json(db)
    edge_pairs = {(e["source"], e["target"]) for e in out["edges"]}
    assert (a1.id, b1.id) in edge_pairs  # resolved within same site A
    assert (a2.id, b2.id) in edge_pairs  # resolved within same site B
    # ensure no cross-site confusion
    assert (a1.id, b2.id) not in edge_pairs and (a2.id, b1.id) not in edge_pairs


def test_orphan_node_with_metrics_exports(db, site):
    # Create a node with metrics but no edges
    item = ContentItem(site_id=site.id, url="https://orph.local/x", title="Orphan"); db.add(item); db.commit()
    # Some pipelines may precompute metrics; simulate minimal metric presence
    # by calling compute first (which should at least include node), then export
    out = compute_and_export_graph_json(db)
    ids = {n["id"] for n in out["nodes"]}
    assert item.id in ids