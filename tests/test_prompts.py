from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class BrandProfile:
    name: str
    domain: str
    mission: str
    vision: str
    default_audience: str
    voice: str
    categories: List[str]
    primary_geo: Optional[str] = None  # For local SEO brands


# --- Predefined brand profiles ---

STRATEGIC_AI_LEADER = BrandProfile(
    name="StrategicAILeader",
    domain="https://www.strategicaileader.com",
    mission=(
        "StrategicAILeader.com empowers founders, executives, and rising professionals "
        "with actionable insights at the intersection of AI, operations, and growth strategy — "
        "delivered with a punch of personality. We blend business intelligence with infotainment "
        "to make complex ideas engaging, memorable, and downright bingeable."
    ),
    vision=(
        "To become the most trusted — and most enjoyable — digital destination for operationally-minded "
        "leaders navigating AI-driven transformation. StrategicAILeader.com is where serious strategy "
        "meets smart storytelling, helping today’s professionals think sharper, scale faster, and have a little fun while doing it."
    ),
    default_audience="Operational leaders, executives, and growth professionals",
    voice="Conversational, authoritative, pragmatic, high-signal, lightly playful.",
    categories=[
        "AI Strategy",
        "Operations",
        "Growth",
        "Leadership",
        "Marketing",
    ],
)

LIAS_FLOWERS = BrandProfile(
    name="LiasFlowers",
    domain="https://www.liasflowers.com",
    mission=(
        "Lia’s Flowers designs joyful, seasonal arrangements that make everyday moments feel special — "
        "backed by friendly service, fast local delivery, and sustainable sourcing."
    ),
    vision=(
        "Be the most loved neighborhood florist by making premium design accessible, reliable, and delightfully personal."
    ),
    default_audience="Local customers shopping for gifts, weddings, and events",
    voice="Warm, neighborly, upbeat, helpful, and trustworthy.",
    categories=[
        "Occasions",
        "Weddings",
        "Sympathy",
        "Plants",
        "Local Guides",
    ],
    primary_geo="Your City, Your State",
)
