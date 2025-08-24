# tests/smoke_test_routes.py
import json
import sys
import time
from typing import Dict, List, Tuple

import requests

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

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 2

if __name__ == "__main__":
    raise SystemExit(main())