from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Float,
    Numeric,
    Boolean,
    func,
    UniqueConstraint,
    Index,
)

from sqlalchemy.orm import relationship, declarative_base, backref

Base = declarative_base()


class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    content_items = relationship(
        "ContentItem", back_populates="site", passive_deletes=True
    )
    analytics_snapshots = relationship(
        "AnalyticsSnapshot", back_populates="site", passive_deletes=True
    )
    graph_metrics = relationship(
        "GraphMetric", back_populates="site", passive_deletes=True
    )

    def __repr__(self):
        return f"<Site(domain={self.domain})>"


class ContentItem(Base):
    __tablename__ = "content_items"

    __table_args__ = (UniqueConstraint("site_id", "url", name="uq_content_site_url"),)

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    # DB has "url" as TEXT; using Text keeps parity and avoids length constraints
    url = Column(Text, nullable=False)

    title = Column(String(500), nullable=True)
    meta_description = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)

    # Crawling/analysis metadata (optional)
    status_code = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    schema_types = Column(JSON, nullable=True)

    # Timestamps from sitemaps / page metadata
    lastmod = Column(DateTime(timezone=True), nullable=True)
    date_published = Column(DateTime(timezone=True), nullable=True)
    date_modified = Column(DateTime(timezone=True), nullable=True)

    # Freshness tracking
    freshness_score = Column(Float, nullable=True)
    freshness_source = Column(String(50), nullable=True)

    # Observability
    first_seen = Column(DateTime(timezone=True), nullable=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)

    # Content change tracking / notes
    content_hash = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)

    # Optional vector embedding for clustering / similarity
    embedding = Column(JSON, nullable=True)
    cluster_id = Column(Integer, nullable=True)

    # Authority signals (Phase 7)
    authority_entity_score = Column(Float, nullable=True)
    authority_citation_count = Column(Integer, nullable=True)
    authority_external_links = Column(Integer, nullable=True)
    authority_schema_present = Column(Boolean, nullable=True)
    authority_author_bylines = Column(Integer, nullable=True)
    authority_last_scored_at = Column(DateTime(timezone=True), nullable=True)

    # --- Phase 10 aggregates (page-level) ---
    sod_overlap_score = Column(
        Float, nullable=True
    )  # average or weighted overlap across chunks
    sod_density_score = Column(
        Float, nullable=True
    )  # topical density / keyword coverage
    extractability_score = Column(
        Float, nullable=True
    )  # LLM-extractability (clarity/quotability)
    chunk_count = Column(Integer, nullable=True)  # number of chunks derived

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship
    site = relationship("Site", back_populates="content_items")

    # Reverse relationship: improvement recommendations tied to this item
    improvement_recommendations = relationship(
        "ImprovementRecommendation",
        back_populates="content_item",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ContentItem(url={self.url}, site={self.site_id})>"


# --- Phase 8: Authority Graph Models -----------------------------------------


class ContentLink(Base):
    """
    Edge in the authority graph between two content items or an external URL.
    Mirrors Alembic migration 3391bd7240f4.
    """

    __tablename__ = "content_links"
    __table_args__ = (
        UniqueConstraint(
            "from_content_id",
            "to_content_id",
            "to_url",
            "anchor_text",
            name="uq_content_links_edge",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Source content item (delete cascades)
    from_content_id = Column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    # Target content item (optional; set NULL on delete) or external URL
    to_content_id = Column(
        Integer, ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True
    )

    to_url = Column(String(2048), nullable=True)
    anchor_text = Column(String(512), nullable=True)
    rel = Column(String(64), nullable=True)
    nofollow = Column(Boolean, nullable=False, server_default="0")
    is_internal = Column(Boolean, nullable=False, server_default="0")
    extra = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    # Relationships
    from_content = relationship(
        "ContentItem",
        foreign_keys=[from_content_id],
        backref=backref("outgoing_links", passive_deletes=True),
        passive_deletes=True,
    )
    to_content = relationship(
        "ContentItem",
        foreign_keys=[to_content_id],
        backref=backref("incoming_links", passive_deletes=True),
        passive_deletes=True,
    )

    def __repr__(self):
        dst = (
            self.to_content_id
            if self.to_content_id is not None
            else (self.to_url or "external")
        )
        return f"<ContentLink({self.from_content_id} -> {dst}, anchor={self.anchor_text!r})>"


class GraphMetric(Base):
    """
    Daily/periodic authority metrics per site.
    Mirrors Alembic migration 3391bd7240f4.
    """

    __tablename__ = "graph_metrics"
    __table_args__ = (
        Index("ix_graph_metrics_site_id", "site_id"),
        Index("ix_graph_metrics_metric_date", "metric_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )

    metric_date = Column(DateTime(timezone=True), nullable=True)
    page_authority = Column(Float, nullable=True)
    cluster_authority = Column(Float, nullable=True)
    domain_authority = Column(Float, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    site = relationship("Site", back_populates="graph_metrics", passive_deletes=True)

    def __repr__(self):
        return f"<GraphMetric(site={self.site_id}, date={self.metric_date}, da={self.domain_authority})>"


# New model: ImprovementRecommendation
class ImprovementRecommendation(Base):
    # Relationships
    content_item = relationship(
        "ContentItem", back_populates="improvement_recommendations"
    )
    __tablename__ = "improvement_recommendations"
    __table_args__ = (Index("ix_improve_site_flag_score", "site_id", "flag", "score"),)

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, nullable=False, index=True)
    content_item_id = Column(
        Integer, ForeignKey("content_items.id"), nullable=True, index=True
    )

    # flag examples: "quick_win", "at_risk", "emerging_topic"
    flag = Column(String(64), nullable=False, index=True)
    score = Column(Float, nullable=True)  # higher = more urgent or higher lift
    rationale = Column(JSON, nullable=True)  # store rule outputs and metrics

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self):
        return f"<ImprovementRecommendation(flag={self.flag}, site_id={self.site_id}, content_item_id={self.content_item_id})>"


# AnalyticsSnapshot model (aligned with migration ce01e106f155)
class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "site_id", "captured_at", "source", name="uq_snapshot_site_capture_source"
        ),
        Index("ix_analytics_snapshots_site_id", "site_id"),
        Index("ix_analytics_snapshots_captured_at", "captured_at"),
        Index("ix_analytics_snapshots_source", "source"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )

    # snapshot metadata
    captured_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source = Column(String(30), nullable=False)

    # reporting window
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)

    # source/system counts
    source_row_count = Column(Integer, nullable=True)
    content_items_count = Column(Integer, nullable=True)
    pages_indexed = Column(Integer, nullable=True)
    indexed_pct = Column(Float, nullable=True)

    # performance metrics
    average_position = Column(Float, nullable=True)
    ctr = Column(Float, nullable=True)
    clicks = Column(Integer, nullable=True)
    impressions = Column(Integer, nullable=True)
    organic_sessions = Column(Integer, nullable=True)
    conversions = Column(Integer, nullable=True)
    revenue = Column(Numeric(12, 2), nullable=True)

    # misc
    notes = Column(JSON, nullable=True)

    # bookkeeping
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # relationships
    site = relationship(
        "Site", back_populates="analytics_snapshots", passive_deletes=True
    )

    def __repr__(self):
        return f"<AnalyticsSnapshot(site={self.site_id}, source={self.source}, captured_at={self.captured_at})>"


# --- Phase 6: Intelligence / SERP caching models ---------------------------------


class SerpCache(Base):
    """
    Lightweight cache of external SERP responses (e.g., Google CSE or Bing Web Search)
    to avoid hammering third‑party APIs and to enable reproducible evaluations.

    Design notes:
    - `cache_key` should be a deterministic hash of (engine, query, market) and any other
      request parameters used by the client. It is left to the caller to compute and provide.
    - We keep the full `items` payload (normalized list of results) and optionally `raw`
      (provider-specific raw JSON).
    """

    __tablename__ = "serp_cache"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_serp_cache_key"),
        Index("ix_serp_cache_engine", "engine"),
        Index("ix_serp_cache_fetched_at", "fetched_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )

    engine = Column(
        String(20), nullable=False, default="google"
    )  # e.g., "google_cse" or "bing"
    query = Column(Text, nullable=False)
    market = Column(String(20), nullable=True)  # e.g., "en-US"
    cache_key = Column(String(64), nullable=False)

    fetched_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Normalized results (list of {title,url,snippet,position,...})
    items = Column(JSON, nullable=True)

    # Provider-specific raw JSON (optional)
    raw = Column(JSON, nullable=True)

    total_results = Column(Integer, nullable=True)
    notes = Column(JSON, nullable=True)

    # Relationship
    site = relationship("Site")

    def __repr__(self):
        return f"<SerpCache(engine={self.engine}, query={self.query[:40]!r}...)>"


class IntelligenceAnswer(Base):
    """
    Simple log of Q&amp;A responses returned by /intelligence endpoints.
    Useful for evaluation, regression tests, and analytics.
    """

    __tablename__ = "intelligence_answers"
    __table_args__ = (
        Index("ix_intel_answers_site_id", "site_id"),
        Index("ix_intel_answers_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )

    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    # Optional structured metadata about how the answer was produced
    meta = Column(JSON, nullable=True)
    # Sources cited (e.g., list of URLs or document ids)
    sources = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    site = relationship("Site")

    def __repr__(self):
        return (
            f"<IntelligenceAnswer(site={self.site_id}, created_at={self.created_at})>"
        )


# --- Phase 10: Second-Order Derivations (SOD) - Content chunks -------------------


class ContentChunk(Base):
    """
    Atomic chunks derived from ContentItem.content for embeddings, retrieval, and SOD.
    - A chunk belongs to a specific ContentItem (on delete: cascade).
    - (content_item_id, chunk_order) is unique to keep deterministic slicing.
    """

    __tablename__ = "content_chunks"
    __table_args__ = (
        UniqueConstraint("content_item_id", "chunk_order", name="uq_chunk_item_order"),
        Index("ix_content_chunks_site_id", "site_id"),
        Index("ix_content_chunks_item_id", "content_item_id"),
        Index("ix_content_chunks_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    content_item_id = Column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )

    # Stable ordering within a document
    chunk_order = Column(Integer, nullable=False)

    # Raw chunk text (post-splitting/cleaning)
    text = Column(Text, nullable=False)

    # Optional metadata
    token_count = Column(Integer, nullable=True)
    checksum = Column(String(64), nullable=True)  # e.g., sha256 of normalized text
    method = Column(String(50), nullable=True)  # e.g., "markdown", "html", "semantic"

    # Vector embedding used for retrieval
    embedding = Column(JSON, nullable=True)

    # --- Phase 10 SOD metrics per chunk ---
    overlap_score = Column(Float, nullable=True)
    density_score = Column(Float, nullable=True)
    extractability_score = Column(Float, nullable=True)

    # Bookkeeping
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    site = relationship("Site", passive_deletes=True)
    content_item = relationship("ContentItem", passive_deletes=True)

    def __repr__(self):
        return f"<ContentChunk(item={self.content_item_id}, order={self.chunk_order})>"


# --- Phase 13: Prompt Fingerprints ------------------------------------------------


class PromptFingerprint(Base):
    """
    Canonicalized prompt signatures for reproducible experiments and caching.
    Provides a stable identity for a prompt + variables + model version.
    """

    __tablename__ = "prompt_fingerprints"
    __table_args__ = (
        UniqueConstraint(
            "site_id", "name", "version", name="uq_prompt_site_name_version"
        ),
        UniqueConstraint("hash", name="uq_prompt_hash"),
        Index("ix_prompt_fingerprints_site_id", "site_id"),
        Index("ix_prompt_fingerprints_hash", "hash"),
        Index("ix_prompt_fingerprints_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )

    # Human-friendly identifier and version for this prompt
    name = Column(String(200), nullable=False)
    version = Column(String(50), nullable=False, default="v1")

    # Canonical SHA-256 (or similar) of the fully rendered prompt spec
    hash = Column(String(64), nullable=False)

    # Storage for the prompt template and variables used to render it
    template = Column(Text, nullable=False)
    variables = Column(JSON, nullable=True)

    # Optional execution metadata
    model_id = Column(String(100), nullable=True)  # e.g., "gpt-4o-mini-2025-05-xx"
    temperature = Column(Float, nullable=True)
    top_p = Column(Float, nullable=True)
    notes = Column(JSON, nullable=True)

    # Bookkeeping
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    site = relationship("Site")

    def __repr__(self):
        return f"<PromptFingerprint(name={self.name!r}, version={self.version}, hash={self.hash[:8]}...)>"
