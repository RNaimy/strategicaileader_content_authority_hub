from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class PromptConfig:
    topic: str
    audience: str = "Growth-minded business leaders"
    tone: str = "conversational, human-like, authoritative, practical, concise"
    angle: str = "actionable playbook with clear takeaways"
    outline: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    call_to_action: Optional[str] = "Invite readers to subscribe to StrategicAILeader."
    constraints: Optional[List[str]] = field(
        default_factory=lambda: [
            "Write at a 9th–11th grade reading level.",
            "Avoid fluff—every paragraph must add value.",
            "Prefer active voice.",
            "Use short paragraphs (2–4 sentences) and scannable subheads.",
            "Include 1 brief, concrete example per major section.",
        ]
    )
    format: str = "markdown"  # markdown | html | text
    include_seo_block: bool = True

    mission_statement: Optional[str] = None
    vision_statement: Optional[str] = None
    primary_keyword: Optional[str] = None
    secondary_keywords: Optional[List[str]] = None
    internal_links: Optional[List[str]] = None
    include_examples: bool = True
    include_anecdotes: bool = False


def _bullet(lines: Optional[Iterable[str]], prefix: str = "- ") -> str:
    if not lines:
        return ""
    return "\n".join(f"{prefix}{line}" for line in lines)


def _csv(items: Optional[Iterable[str]]) -> str:
    if not items:
        return ""
    return ", ".join(items)


def build_article_prompt(cfg: PromptConfig) -> str:
    """
    Build a high-signal prompt for a long-form article aimed at topical authority.
    Generates: title options, outline, full draft, plus optional SEO block.
    """
    outline_block = _bullet(cfg.outline) if cfg.outline else ""
    keywords_csv = _csv(cfg.keywords)
    secondary_keywords_csv = _csv(cfg.secondary_keywords)
    sources_block = _bullet(cfg.sources, prefix="• ")
    constraints_block = _bullet(cfg.constraints)
    internal_links_block = (
        _bullet(cfg.internal_links, prefix="• ") if cfg.internal_links else ""
    )

    mission_context = (
        f"Mission: {cfg.mission_statement}" if cfg.mission_statement else ""
    )
    vision_context = f"Vision: {cfg.vision_statement}" if cfg.vision_statement else ""

    seo_block = ""
    if cfg.include_seo_block:
        seo_block = f"""
### SEO REQUIREMENTS
- Primary keyword: {cfg.primary_keyword or "(model choose primary keyword)"}.
- Secondary keywords: {secondary_keywords_csv or "(model choose related secondary keywords)"}.
- Use primary keyword in title, headers, and first 100 words.
- Naturally incorporate secondary keywords throughout the article.
- Generate AIOSEO-compatible SEO snippet including title tag (<= 60 chars), meta description (<= 155 chars), and URL slug (kebab-case).
"""

    prompt = f"""You are a veteran editor who specializes in B2B growth, AI, and operations.
Write a publication-ready article in {cfg.format}.

{mission_context}
{vision_context}

### TOPIC
{cfg.topic}

### AUDIENCE
{cfg.audience}

### TONE
Use a {cfg.tone} tone with idiomatic phrasing and a natural, conversational style.
Avoid jargon and overly formal language to engage readers effectively.

### ANGLE
{cfg.angle}

### STRUCTURE
{"Use this detailed expert content outline:\n" + outline_block if outline_block else "Propose a smart, detailed outline first, then write the article."}
- Introduction: hook, context, and thesis statement.
- Main sections: clear headings with actionable insights.
- Include examples and anecdotes where appropriate.
- Conclusion: summarize key takeaways and next steps.

### STYLE GUIDELINES
{constraints_block}
- Write in active voice.
- Avoid starting sentences with 'This'.
- Remove all em dashes (—) and replace with appropriate punctuation or conjunctions.
- Use short paragraphs (2-4 sentences).
- Include at least one concrete example per major section if {cfg.include_examples}.
- Include relevant anecdotes if {cfg.include_anecdotes}.

### SOURCES AND CITATIONS
{sources_block or "If you use external facts, cite them inline with (Source). Avoid fabrications."}

### INTERNAL LINKS
{internal_links_block or "Include relevant internal links to StrategicAILeader content where appropriate."}

### OUTPUT REQUIREMENTS
1) Provide 3 strong, varied title options incorporating the primary keyword.
2) Provide a tight, detailed outline.
3) Write the full article with H2/H3 headings, examples, anecdotes, and bullet lists where helpful.
4) End with a clear, compelling call to action: {cfg.call_to_action}
{seo_block}
"""
    return prompt.strip()


def build_linkedin_prompt(cfg: PromptConfig, article_url: Optional[str] = None) -> str:
    """
    Short LinkedIn-native post optimized for engagement + authority.
    If `article_url` is provided, include it as the primary CTA link.
    """
    keywords_csv = _csv(cfg.keywords)
    link_line = f"\nLink to full article: {article_url}" if article_url else ""
    return f"""Write a LinkedIn post (180–240 words) in a {cfg.tone} voice for {cfg.audience}.
Topic: {cfg.topic}
Angle: {cfg.angle}
Must include:
- A scroll-stopping hook in the first 2 lines
- 1 compact framework or checklist
- 1 practical example
- Soft CTA: {cfg.call_to_action}{link_line}
Hashtags: choose 3–5 specific, non-generic tags derived from: {keywords_csv or "the topic"}. Prefer branded + niche tags over generic ones.
Place the CTA link on its own line at the end if present. Return plain text only, line-broken for LinkedIn readability (no markdown headers).""".strip()


def build_substack_prompt(
    cfg: PromptConfig,
    article_url: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """Substack-ready post scaffold with SEO pieces and CTA back to full article."""
    tags_csv = _csv(tags or cfg.keywords)
    link_line = (
        f"\nPrimary CTA: Read the full article → {article_url}" if article_url else ""
    )
    return f"""Create a Substack post in {cfg.format}.
Topic: {cfg.topic}
Audience: {cfg.audience}
Tone: {cfg.tone}
Angle: {cfg.angle}

Include:
- Subhead (1 line) that amplifies the hook
- SEO Title (<=60 chars) with primary keyword
- SEO Meta Description (<=155 chars)
- Body (400–700 words): concise narrative with 2–3 skim-friendly subheads, 1 actionable framework, and a concrete example
- Substack tags (5–8): {tags_csv or "choose relevant tags"}
- Final CTA that links back to the full blog article{link_line}

Formatting:
- Keep paragraphs short (2–4 sentences).
- Use plain text or basic markdown, no HTML tables.
- Avoid em dashes; use commas or conjunctions instead.
""".strip()


def build_seo_snippets_prompt(cfg: PromptConfig) -> str:
    """
    Generate SEO metadata/snippets independently.
    """
    keywords_csv = _csv(cfg.keywords)
    return f"""Create SEO snippets for an article.
Topic: {cfg.topic}
Audience: {cfg.audience}
Tone: {cfg.tone}
Angle: {cfg.angle}
Primary keywords: {keywords_csv or "(choose semantically-related terms)"}

Output:
- Title tag (<=60 chars)
- Meta description (<=155 chars)
- Kebab-case URL slug
- 5–8 semantic keywords
- 3 FAQ Q&A pairs with crisp 1–2 sentence answers
Return as plain text with clear labels.""".strip()


def build_multichannel_bundle(
    cfg: PromptConfig,
    *,
    article_url: Optional[str] = None,
    substack_tags: Optional[List[str]] = None,
    include_seo_snippets: bool = True,
) -> dict:
    """Return a dict containing prompts for blog article, LinkedIn, Substack, and SEO snippets."""
    bundle = {
        "article": build_article_prompt(cfg),
        "linkedin": build_linkedin_prompt(cfg, article_url=article_url),
        "substack": build_substack_prompt(
            cfg, article_url=article_url, tags=substack_tags
        ),
    }
    if include_seo_snippets:
        bundle["seo_snippets"] = build_seo_snippets_prompt(cfg)
    return bundle
