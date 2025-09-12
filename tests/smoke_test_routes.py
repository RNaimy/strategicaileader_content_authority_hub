# tests/smoke_test_routes.py
import json
import sys
import time
from typing import Dict, List, Tuple

import requests
from urllib.parse import urlparse

BASE = "http://127.0.0.1:8001"


def get_paths() -> Dict[str, dict]:
    r = requests.get(f"{BASE}/openapi.json", timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("paths", {})


def expect_any(paths: Dict[str, dict], prefixes: List[str]) -> List[str]:
    found = []
    for p in paths.keys():
        for pref in prefixes:
            if p.startswith(pref):
                found.append(p)
                break
    return sorted(set(found))


def ping(url: str, method: str = "GET", **kwargs) -> Tuple[int, str]:
    func = getattr(requests, method.lower())
    r = func(f"{BASE}{url}", timeout=20, **kwargs)
    return r.status_code, r.text


# --- Helper functions for additional endpoint checks ---
def json_get(url: str, method: str = "GET", **kwargs):
    func = getattr(requests, method.lower())
    r = func(f"{BASE}{url}", timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def _no_substring_dupes(terms: List[str]) -> bool:
    # Ensure no term is a substring of another (case-insensitive)
    t = [x.lower().strip() for x in terms if x]
    for i in range(len(t)):
        for j in range(len(t)):
            if i == j:
                continue
            if t[i] in t[j]:
                return False
    return True


# --- Pytest-style tests for endpoints ---
import pytest


def test_clusters_topics_stopwords_dedupe():
    resp = json_get(
        "/clusters/topics?domain=strategicaileader.com"
        "&k=8&seed=42&top_n=6&samples_per_cluster=5"
        "&stopwords_extra=ai,seo,saas&dedupe_substrings=true"
    )
    clusters = resp.get("clusters", [])
    assert clusters, "No clusters returned"
    label_terms = clusters[0].get("label_terms", [])
    assert label_terms, "First cluster has no label_terms"
    assert _no_substring_dupes(
        label_terms
    ), f"label_terms have substring duplicates: {label_terms}"


def test_internal_links_with_exclude_regex():
    resp = json_get(
        "/clusters/internal-links?domain=strategicaileader.com"
        "&per_item=3&min_sim=0.5&exclude_regex=%5E/tag/|/category/"
        "&fallback_when_empty=true"
    )
    suggestions = resp.get("suggestions", [])
    assert (
        isinstance(suggestions, list) and len(suggestions) > 0
    ), "No suggestions returned"
    for s in suggestions:
        target = s.get("target_url", "")
        assert (
            "/tag/" not in target and "/category/" not in target
        ), f"target_url contains excluded path: {target}"


def main() -> int:
    print("Waiting for server ...")
    for _ in range(20):
        try:
            requests.get(f"{BASE}/docs", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    else:
        print("Server did not respond at /docs", file=sys.stderr)
        return 1

    paths = get_paths()
    print(f"Discovered {len(paths)} OpenAPI paths")

    expected_groups = {
        "content": ["/content"],
        "inventory": ["/inventory"],
        "clustering": ["/clusters"],
        "scraper": ["/scraper"],
        "brands": ["/brands"],
    }

    ok = True
    for name, prefs in expected_groups.items():
        hits = expect_any(paths, prefs)
        print(f"[{name}] matched paths: {len(hits)}")
        if not hits:
            print(f"  !! Missing any route starting with {prefs}", file=sys.stderr)
            ok = False

    # Light-touch endpoint pokes (status code only)
    checks = [
        ("GET", "/inventory/stats?domain=strategicaileader.com"),
        ("GET", "/inventory/list?domain=strategicaileader.com&limit=1"),
        ("GET", "/clusters/health?domain=strategicaileader.com"),
    ]
    for method, url in checks:
        try:
            sc, _ = ping(url, method=method)
            print(f"{method} {url} -> {sc}")
            if sc >= 500:
                ok = False
        except Exception as e:
            print(f"Error calling {method} {url}: {e}", file=sys.stderr)
            ok = False

    # --- Additional functional checks ---
    try:
        print("Testing /clusters/topics with stopwords & dedupe ...")
        topics = json_get(
            "/clusters/topics?domain=strategicaileader.com"
            "&k=8&seed=42&top_n=6&samples_per_cluster=5"
            "&stopwords_extra=ai,seo,saas&dedupe_substrings=true"
        )
        clusters = topics.get("clusters", [])
        if not clusters:
            print("  !! /clusters/topics returned no clusters", file=sys.stderr)
            ok = False
        else:
            lt = clusters[0].get("label_terms", [])
            if not lt:
                print(
                    "  !! /clusters/topics first cluster had no label_terms",
                    file=sys.stderr,
                )
                ok = False
            elif not _no_substring_dupes(lt):
                print(
                    f"  !! label_terms contain substring duplicates: {lt}",
                    file=sys.stderr,
                )
                ok = False
    except Exception as e:
        print(f"Error calling /clusters/topics: {e}", file=sys.stderr)
        ok = False

    try:
        print("Testing /clusters/internal-links with exclude_regex ...")
        # Exclude tag/ and category/ targets strictly; allow fallback to ensure non-empty
        links = json_get(
            "/clusters/internal-links?domain=strategicaileader.com"
            "&per_item=3&min_sim=0.5&exclude_regex=%5E/tag/|/category/"
            "&fallback_when_empty=true"
        )
        suggestions = links.get("suggestions", [])
        if not isinstance(suggestions, list) or len(suggestions) == 0:
            print(
                "  !! /clusters/internal-links returned no suggestions", file=sys.stderr
            )
            ok = False
        else:
            # Validate excluded patterns are not present in targets
            bad = [
                s
                for s in suggestions
                if (
                    "/tag/" in s.get("target_url", "")
                    or "/category/" in s.get("target_url", "")
                )
            ]
            if bad:
                print(
                    f"  !! exclude_regex did not filter some targets (showing 3): {bad[:3]}",
                    file=sys.stderr,
                )
                ok = False
    except Exception as e:
        print(f"Error calling /clusters/internal-links: {e}", file=sys.stderr)
        ok = False

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
