from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float, Numeric, func, UniqueConstraint, Index, Boolean
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    content_items = relationship("ContentItem", back_populates="site")
    analytics_snapshots = relationship("AnalyticsSnapshot", back_populates="site")

    def __repr__(self):
        return f"<Site(domain={self.domain})>"


class ContentItem(Base):
    __tablename__ = "content_items"

    __table_args__ = (
        UniqueConstraint("site_id", "url", name="uq_content_site_url"),
    )

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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    site = relationship("Site", back_populates="content_items")

    def __repr__(self):
        return f"<ContentItem(url={self.url}, site={self.site_id})>"


# AnalyticsSnapshot model (aligned with migration ce01e106f155)
class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint("site_id", "captured_at", "source", name="uq_snapshot_site_capture_source"),
        Index("ix_analytics_snapshots_site_id", "site_id"),
        Index("ix_analytics_snapshots_captured_at", "captured_at"),
        Index("ix_analytics_snapshots_source", "source"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    # snapshot metadata
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # relationships
    site = relationship("Site", back_populates="analytics_snapshots")

    def __repr__(self):
        return f"<AnalyticsSnapshot(site={self.site_id}, source={self.source}, captured_at={self.captured_at})>"