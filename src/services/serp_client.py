import os
from typing import Dict, List, Optional
import requests


class SERPClient:
    """
    Simple meta SERP client that can talk to either:
      - Google Custom Search JSON API (CSE)
      - Bing Web Search API (v7)
    Selection is controlled by environment variables via from_env().
    """

    def __init__(
        self,
        provider: str,
        google_api_key: Optional[str] = None,
        google_cx: Optional[str] = None,
        bing_api_key: Optional[str] = None,
    ):
        self.provider = provider.lower().strip()
        self.google_api_key = google_api_key
        self.google_cx = google_cx
        self.bing_api_key = bing_api_key

        if self.provider == "google":
            if not (self.google_api_key and self.google_cx):
                raise ValueError(
                    "Google CSE requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX."
                )
        elif self.provider == "bing":
            if not self.bing_api_key:
                raise ValueError("Bing requires BING_API_KEY.")
        else:
            raise ValueError(f"Unknown SERP provider: {provider}")

    # -------- Factory --------
    @classmethod
    def from_env(cls) -> "SERPClient":
        """
        Load configuration from environment variables.

        Supported env vars:
          - GOOGLE_CSE_API_KEY (preferred) or GOOGLE_CSE_KEY (legacy alias)
          - GOOGLE_CSE_CX
          - BING_API_KEY

        Provider selection:
          - Prefer Google if GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX are present.
          - Else fallback to Bing if BING_API_KEY is present.
          - Otherwise raise RuntimeError.
        """
        google_key = os.getenv("GOOGLE_CSE_API_KEY") or os.getenv("GOOGLE_CSE_KEY")
        google_cx = os.getenv("GOOGLE_CSE_CX")
        bing_key = os.getenv("BING_API_KEY")

        if google_key and google_cx:
            return cls(
                provider="google", google_api_key=google_key, google_cx=google_cx
            )
        if bing_key:
            return cls(provider="bing", bing_api_key=bing_key)

        raise RuntimeError(
            "No SERP provider configured. Set GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX or BING_API_KEY in your environment."
        )

    # -------- Public API --------
    def search(self, query: str, num: int = 5, market: str = "en-US") -> Dict:
        """
        Execute a web search using the configured provider.

        Returns a normalized dict:
        {
          "provider": "google" | "bing",
          "query": "...",
          "count": N,
          "items": [{"title": "...", "url": "...", "snippet": "..."}]
        }
        """
        query = (query or "").strip()
        num = max(1, min(int(num or 5), 50))  # clamp to [1,50]

        if self.provider == "google":
            raw = self._search_google_cse(query, num=num)
            items = _normalize_google_items(raw)
        elif self.provider == "bing":
            raw = self._search_bing(query, num=num, market=market)
            items = _normalize_bing_items(raw)
        else:
            raise RuntimeError(f"Unsupported provider: {self.provider}")

        return {
            "provider": self.provider,
            "query": query,
            "count": len(items),
            "items": items[:num],
            "raw": raw,  # keep for debugging; upstream can drop before returning to client if desired
        }

    # -------- Provider impls --------
    def _search_google_cse(self, query: str, num: int = 5) -> Dict:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": query,
            "cx": self.google_cx,
            "key": self.google_api_key,
            "num": num,
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Google CSE request failed {resp.status_code}: {resp.text}"
            )
        return resp.json()

    def _search_bing(self, query: str, num: int = 5, market: str = "en-US") -> Dict:
        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": self.bing_api_key}
        params = {
            "q": query,
            "count": num,
            "mkt": market,
            "responseFilter": "Webpages",
            "textDecorations": "false",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Bing Web Search failed {resp.status_code}: {resp.text}"
            )
        return resp.json()


# -------- Normalizers --------
def _normalize_google_items(raw: Dict) -> List[Dict]:
    items = []
    for it in (raw or {}).get("items", []) or []:
        items.append(
            {
                "title": it.get("title"),
                "url": it.get("link"),
                "snippet": it.get("snippet"),
                "source": "google",
            }
        )
    return items


def _normalize_bing_items(raw: Dict) -> List[Dict]:
    items = []
    web = (raw or {}).get("webPages", {})
    for it in web.get("value", []) or []:
        items.append(
            {
                "title": it.get("name"),
                "url": it.get("url"),
                "snippet": it.get("snippet"),
                "source": "bing",
            }
        )
    return items


if __name__ == "__main__":
    # Quick manual test
    try:
        client = SERPClient.from_env()
        out = client.search("site:example.com test", num=3, market="en-US")
        print(f"[{out['provider']}] {out['count']} results")
        for i, item in enumerate(out["items"], 1):
            print(f"{i}. {item['title']} — {item['url']}")
    except Exception as e:
        print("Error:", e)
