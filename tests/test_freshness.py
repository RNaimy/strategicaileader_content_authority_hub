

import math
from datetime import datetime, timedelta, timezone

import pytest

from src.services.freshness import FreshnessScorer


RFC3339 = "%Y-%m-%dT%H:%M:%SZ"


def _rfc3339(dt: datetime) -> str:
    # Ensure UTC and RFC3339 "Z" suffix
    return dt.astimezone(timezone.utc).strftime(RFC3339)


@pytest.mark.unit
@pytest.mark.order(1)
def test_today_scores_one():
    scorer = FreshnessScorer(half_life_days=30)
    now = datetime.now(timezone.utc)
    score = scorer.score_published_date(_rfc3339(now))
    assert 0.95 <= score <= 1.0, f"expected ~1.0 for today, got {score}"


@pytest.mark.unit
@pytest.mark.order(2)
@pytest.mark.parametrize(
    "days_ago, expected, tol",
    [
        (7, 2 ** (-7 / 30), 0.06),     # ~0.851
        (30, 0.5, 0.03),               # half-life
        (60, 0.25, 0.03),              # two half-lives
    ],
)
def test_decay_matches_half_life(days_ago, expected, tol):
    scorer = FreshnessScorer(half_life_days=30)
    then = datetime.now(timezone.utc) - timedelta(days=days_ago)
    score = scorer.score_published_date(_rfc3339(then))
    assert math.isfinite(score), "score should be finite"
    assert abs(score - expected) <= tol, (
        f"expected ~{expected:.3f} at {days_ago}d, got {score:.3f}"
    )


@pytest.mark.unit
@pytest.mark.order(3)
def test_future_dates_floor_to_zero():
    scorer = FreshnessScorer(half_life_days=30)
    future = datetime.now(timezone.utc) + timedelta(days=3)
    score = scorer.score_published_date(_rfc3339(future))
    assert score == 0.0


@pytest.mark.unit
@pytest.mark.order(4)
@pytest.mark.parametrize(
    "bad_value",
    [
        "",  # empty
        "not-a-date",
        "2025/01/01",  # wrong format
        None,
    ],
)
def test_invalid_inputs_return_zero(bad_value):
    scorer = FreshnessScorer()
    score = scorer.score_published_date(bad_value)  # type: ignore[arg-type]
    assert score == 0.0