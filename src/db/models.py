from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON, func
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)

    # Relationship
    content_items = relationship("ContentItem", back_populates="site")

    def __repr__(self):
        return f"<Site(domain={self.domain})>"


class ContentItem(Base):
    __tablename__ = "content_items"
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    url = Column(String(2048), nullable=False)  # match DB schema, drop global unique
    title = Column(String(512), nullable=True)
    meta_description = Column(Text, nullable=True)  # aligns with new column

    # --- fields that exist in the SQLite schema ---
    status_code = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    schema_types = Column(JSON, nullable=True)
    # Optional vector embedding for clustering / similarity
    embedding = Column(JSON, nullable=True)
    cluster_id = Column(Integer, nullable=True)
    lastmod = Column(DateTime, nullable=True)
    date_published = Column(DateTime, nullable=True)
    date_modified = Column(DateTime, nullable=True)
    freshness_score = Column(Float, nullable=True)
    freshness_source = Column(String(32), nullable=True)
    first_seen = Column(DateTime, server_default=func.now(), nullable=False)
    last_seen = Column(DateTime, server_default=func.now(), nullable=False)
    content_hash = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    site = relationship("Site", back_populates="content_items")

    def __repr__(self):
        return f"<ContentItem(url={self.url}, site={self.site_id})>"