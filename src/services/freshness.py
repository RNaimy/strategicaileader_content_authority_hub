
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timezone
from typing import Optional, Union


DateLike = Union[str, date, datetime]


@dataclass
class FreshnessScorer:
    """Exponential freshness scoring with a configurable half-life.

    * Today (age=0 days) => score = 1.0
    * At `half_life_days` => score = 0.5
    * Future dates => 0.0
    * Invalid inputs => 0.0
    """

    half_life_days: float = 30.0
    floor: float = 0.0
    ceil: float = 1.0

    def _parse_date(self, value: DateLike) -> Optional[date]:
        """Parse a date from:
        - str in YYYY-MM-DD
        - RFC3339/ISO8601 datetime strings (e.g., 2025-08-28T12:34:56Z)
        - `date` or `datetime`
        Returns None on failure.
        """
        if isinstance(value, datetime):
            # Keep calendar date only
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            # 1) Try plain date first
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                pass
            # 2) Try RFC3339/ISO8601, allowing trailing 'Z'
            try:
                iso = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso)
                # Normalize to UTC date to avoid local offset surprises
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                return dt.date()
            except Exception:
                pass
            # 3) Last resort: take first 10 chars if they look like a date
            if len(s) >= 10:
                head = s[:10]
                try:
                    return datetime.strptime(head, "%Y-%m-%d").date()
                except Exception:
                    return None
            return None
        return None

    def score_published_date(self, value: DateLike) -> float:
        d = self._parse_date(value)
        if not d:
            return 0.0

        # Use UTC for today to keep tests deterministic across timezones
        today = datetime.now(timezone.utc).date()
        delta_days = (today - d).days

        # Future dates => zero
        if delta_days < 0:
            return 0.0

        # Exponential half-life decay
        score = self.ceil * (0.5 ** (delta_days / float(self.half_life_days)))

        # Clamp to [floor, ceil]
        if score < self.floor:
            score = self.floor
        if score > self.ceil:
            score = self.ceil
        return float(score)


if __name__ == "__main__":
    scorer = FreshnessScorer(half_life_days=30)
    demo_values: list[DateLike] = [
        datetime.now(timezone.utc),  # now (UTC)
        datetime.now(timezone.utc).strftime("%Y-%m-%d"),  # plain date string
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),  # RFC3339
    ]
    for v in demo_values:
        print(v, "->", scorer.score_published_date(v))
