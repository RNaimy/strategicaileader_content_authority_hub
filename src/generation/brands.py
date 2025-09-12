from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass(frozen=True)
class BrandProfile:
    """Reusable brand profile for prompt conditioning.

    Keep this intentionally light so prompts can stay fast and portable.
    """

    key: str
    name: str
    site_url: str
    mission: str
    vision: str

    # Voice & tone rails the generators should follow
    voice: str = (
        "Conversational, practical, high-signal. Mix of operator savvy and\n"
        "approachable thought leadership. Avoid fluff, prefer examples and\n"
        "frameworks."
    )

    audience: str = (
        "Operators, managers, and growth-minded leaders who value clear,\n"
        "actionable guidance."
    )

    # Optional helpers for templates that want defaults
    categories: List[str] = field(default_factory=list)
    default_keywords: List[str] = field(default_factory=list)

    # Freeform extra knobs prompt templates may consult
    meta: Dict[str, Any] = field(default_factory=dict)


# --- Strategic AI Leader ----------------------------------------------------

STRATEGIC_AI_LEADER = BrandProfile(
    key="strategic_ai_leader",
    name="StrategicAILeader",
    site_url="https://www.strategicaileader.com/",
    mission=(
        "StrategicAILeader.com empowers founders, executives, and rising\n"
        "professionals with actionable insights at the intersection of AI,\n"
        "operations, and growth strategy — delivered with a punch of\n"
        "personality. We blend business intelligence with infotainment to\n"
        "make complex ideas engaging, memorable, and downright bingeable."
    ),
    vision=(
        "To become the most trusted — and most enjoyable — digital\n"
        "destination for operationally-minded leaders navigating AI-driven\n"
        "transformation. StrategicAILeader.com is where serious strategy meets\n"
        "smart storytelling, helping today’s professionals think sharper,\n"
        "scale faster, and have a little fun while doing it."
    ),
    voice=(
        "Conversational, candid, slightly playful; authoritative without\n"
        "jargon. Use idiomatic phrases, short varied sentences, and real\n"
        "operator examples."
    ),
    audience=(
        "Founders, COOs, Heads of Growth, and new managers who want\n"
        "pragmatic systems, not theory."
    ),
    categories=[
        "AI Strategy",
        "Operations",
        "Growth",
        "Leadership",
        "Content Ops",
    ],
    default_keywords=[
        "AI operations",
        "topical authority",
        "workflow automation",
        "prompt engineering",
        "content velocity",
    ],
    meta={
        "house_style": "Use examples, mini case studies, and numbered playbooks.",
        "cta": "Invite readers to subscribe, comment, or book a strategy call.",
    },
)


# --- Lia's Flowers (local/e‑com ready) --------------------------------------

LIAS_FLOWERS = BrandProfile(
    key="lias_flowers",
    name="Lia’s Flowers",
    site_url="https://www.liasflowers.com/",
    mission=(
        "Deliver joy through thoughtfully designed bouquets and same‑day local\n"
        "delivery—making life’s moments easy to celebrate."
    ),
    vision=(
        "Be the most loved neighborhood florist by pairing artisan design with\n"
        "reliable, modern service."
    ),
    voice=(
        "Warm, neighborly, sensory language; confidence without hype. Keep it\n"
        "clear and helpful for fast local buyers."
    ),
    audience=(
        "Local shoppers seeking same‑day flowers for birthdays, sympathy,\n"
        "anniversaries, and events."
    ),
    categories=[
        "Bouquets",
        "Occasions",
        "Same‑Day Delivery",
        "Wedding & Events",
        "Care Tips",
    ],
    default_keywords=[
        "same‑day flower delivery",
        "local florist",
        "rose bouquets",
        "seasonal flowers",
        "wedding florals",
    ],
    meta={
        "service_area": ["Downtown", "Midtown", "Uptown"],
        "usp": "Artisan designs with guaranteed same‑day delivery before 2pm.",
    },
)


# Public exports for templates
__all__ = [
    "BrandProfile",
    "STRATEGIC_AI_LEADER",
    "LIAS_FLOWERS",
]
