from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float, func, UniqueConstraint, Index
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship
    content_items = relationship("ContentItem", back_populates="site")

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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    site = relationship("Site", back_populates="content_items")

    def __repr__(self):
        return f"<ContentItem(url={self.url}, site={self.site_id})>"


# New model: ImprovementRecommendation
class ImprovementRecommendation(Base):
    __tablename__ = "improvement_recommendations"
    __table_args__ = (
        Index("ix_improve_site_flag_score", "site_id", "flag", "score"),
    )

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, nullable=False, index=True)
    content_item_id = Column(Integer, ForeignKey("content_items.id"), nullable=True, index=True)

    # flag examples: "quick_win", "at_risk", "emerging_topic"
    flag = Column(String(64), nullable=False, index=True)
    score = Column(Float, nullable=True)  # higher = more urgent or higher lift
    rationale = Column(JSON, nullable=True)  # store rule outputs and metrics

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<ImprovementRecommendation(flag={self.flag}, site_id={self.site_id}, content_item_id={self.content_item_id})>"