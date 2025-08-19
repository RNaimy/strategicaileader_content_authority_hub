from __future__ import annotations
"""
Lightweight NLP helpers used for keyword scoring and clustering.
These are intentionally dependency-free for fast unit testing.
"""
from typing import Dict, List, Tuple


def keyword_frequency(text: str, keywords: List[str]) -> Dict[str, int]:
    """Count case-insensitive keyword occurrences in *text*.

    Returns a dict like {"growth": 3, "seo": 1}.
    Empty or None keywords are handled safely.
    """
    text = text or ""
    lower = text.lower()
    out: Dict[str, int] = {}
    for k in (keywords or []):
        key = (k or "").lower()
        out[key] = lower.count(key) if key else 0
    return out


# Tokens we treat as non-meaningful when validating keyword presence
essentially_empty_tokens = {"", None}


def contains_all_keywords(text: str, keywords: List[str]) -> bool:
    """True if every keyword appears at least once, case-insensitive.

    Empty/None keywords are ignored. If no meaningful keywords are provided,
    the condition is considered satisfied.
    """
    normalized = [
        k for k in (keywords or [])
        if k not in essentially_empty_tokens and (k or "").strip()
    ]
    if not normalized:
        return True
    freq = keyword_frequency(text, normalized)
    return all(freq[(k or "").lower()] > 0 for k in normalized)


def top_keywords(text: str, keywords: List[str], top_n: int = 10) -> List[Tuple[str, int]]:
    """Return the top N ``(keyword, count)`` pairs by frequency, descending.

    Ties keep input order.
    """
    counts = keyword_frequency(text, keywords)
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[: top_n]