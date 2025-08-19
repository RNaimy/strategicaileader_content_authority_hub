import os, sys, importlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

MODULES = [
    "analysis.authority_score",
    "analysis.keyword_gap",
    "analysis.optimization_ai",
    "analysis.topic_clustering",
    "crawlers.blog_scraper",
    "crawlers.competitor_scraper",
    "crawlers.sitemap_parser",
    "gsc.gsc_client",
    "gsc.gsc_fetch",
    "gsc.gsc_parser",
    "reports.build_csv",
    "reports.export_notion",
    "reports.generate_pdf",
    "utils.db",
    "utils.gsc_helpers",
    "utils.logger",
    "utils.nlp",
    "utils.seo_rules",
]

def test_import_all_modules():
    failed = []
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as e:
            failed.append((name, str(e)))
    assert not failed, f"Failed imports: {failed}"