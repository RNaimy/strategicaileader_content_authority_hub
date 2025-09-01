from typing import Dict

def compute_authority_signals(content: str) -> Dict[str, float | int]:
    text = (content or "").strip()
    if not text:
        return {
            "entity_coverage_score": 0.0,
            "citation_count": 0,
            "external_link_count": 0,
            "schema_presence": 0,
            "author_bylines": 0,
        }
    words = text.split()
    length_score = min(len(words) / 500.0, 1.0)
    return {
        "entity_coverage_score": round(0.3 + 0.7 * length_score, 3),
        "citation_count": 0,
        "external_link_count": 0,
        "schema_presence": 0,
        "author_bylines": 0,
    }
