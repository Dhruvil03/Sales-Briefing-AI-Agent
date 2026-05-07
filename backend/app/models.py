# backend/app/models.py
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, JSON, UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .db import Base


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name      = Column(String(255), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    sessions = relationship(
        "ResearchSession", back_populates="user", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Core session — one per (company + prospect) pair
# ---------------------------------------------------------------------------

class ResearchSession(Base):
    """
    The top-level entity. Everything else hangs off a session.
    user_id is nullable until auth (Step 7) is implemented.
    """
    __tablename__ = "research_sessions"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    company_url    = Column(String(2048), nullable=True)
    company_name   = Column(String(512),  nullable=True)   # extracted during research
    prospect_name  = Column(String(255),  nullable=True)
    call_date      = Column(DateTime(timezone=True), nullable=True)
    # booked | follow-up | not-interested | no-show | null (not yet called)
    call_outcome   = Column(String(50), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user             = relationship("User", back_populates="sessions")
    company_research = relationship(
        "CompanyResearch", back_populates="session",
        uselist=False, cascade="all, delete-orphan"
    )
    prospect_research = relationship(
        "ProspectResearch", back_populates="session",
        uselist=False, cascade="all, delete-orphan"
    )
    report       = relationship(
        "PreCallReport", back_populates="session",
        uselist=False, cascade="all, delete-orphan"
    )
    call_notes   = relationship(
        "CallNotes", back_populates="session",
        uselist=False, cascade="all, delete-orphan"
    )
    followup_email = relationship(
        "FollowUpEmail", back_populates="session",
        uselist=False, cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Company research
# ---------------------------------------------------------------------------

class CompanyResearch(Base):
    """
    Stores the crawled content and LLM summary for a company.
    signals: list of trigger events e.g.
      [{"type": "funding", "text": "Raised $50M Series B (Jan 2025)"}]
    source_id links to the Source/Chunk tables for future RAG use if needed.
    """
    __tablename__ = "company_research"
    __table_args__ = (UniqueConstraint("session_id"),)

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    raw_text   = Column(Text, nullable=True)
    summary    = Column(Text, nullable=True)
    signals    = Column(JSON, nullable=True)   # list[{type, text}]
    source_id  = Column(
        Integer, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ResearchSession", back_populates="company_research")
    source  = relationship("Source")


# ---------------------------------------------------------------------------
# Prospect research  (RAG lives here)
# ---------------------------------------------------------------------------

class ProspectResearch(Base):
    """
    Stores the multi-source scrape results and LLM prospect insights.
    sources_searched: list of URLs that were scraped.
    aggregated_text: raw combined text before RAG chunking.
    source_id: FK to Source → Chunks with embeddings (used by history search).
    """
    __tablename__ = "prospect_research"
    __table_args__ = (UniqueConstraint("session_id"),)

    id               = Column(Integer, primary_key=True, index=True)
    session_id       = Column(
        Integer, ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    sources_searched = Column(JSON, nullable=True)   # list[str] of URLs
    aggregated_text  = Column(Text, nullable=True)
    insights         = Column(Text, nullable=True)   # LLM output
    source_id        = Column(
        Integer, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ResearchSession", back_populates="prospect_research")
    source  = relationship("Source")


# ---------------------------------------------------------------------------
# Pre-call report
# ---------------------------------------------------------------------------

class PreCallReport(Base):
    __tablename__ = "precall_reports"
    __table_args__ = (UniqueConstraint("session_id"),)

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    report_md  = Column(Text, nullable=True)
    tone       = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ResearchSession", back_populates="report")


# ---------------------------------------------------------------------------
# Post-call
# ---------------------------------------------------------------------------

class CallNotes(Base):
    __tablename__ = "call_notes"
    __table_args__ = (UniqueConstraint("session_id"),)

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    notes_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session = relationship("ResearchSession", back_populates="call_notes")


class FollowUpEmail(Base):
    __tablename__ = "followup_emails"
    __table_args__ = (UniqueConstraint("session_id"),)

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    email_md   = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ResearchSession", back_populates="followup_email")


# ---------------------------------------------------------------------------
# RAG infrastructure (unchanged — still used by prospect research + history search)
# ---------------------------------------------------------------------------

class Source(Base):
    """
    A scraped web resource. Parent of Chunk rows.
    Used by ProspectResearch (multi-source aggregation) and history search.
    """
    __tablename__ = "sources"

    id         = Column(Integer, primary_key=True, index=True)
    url        = Column(Text, nullable=False)
    raw_text   = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chunks = relationship("Chunk", back_populates="source", cascade="all, delete-orphan")


class Chunk(Base):
    """
    Fixed-size text segment of a Source with a vector embedding.
    900 chars, 120-char overlap. Embedding stored as JSON float list.
    """
    __tablename__ = "chunks"

    id          = Column(Integer, primary_key=True, index=True)
    source_id   = Column(
        Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = Column(Integer, nullable=False)
    chunk_text  = Column(Text, nullable=False)
    embedding   = Column(JSON, nullable=True)   # list[float], normalized
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    source = relationship("Source", back_populates="chunks")


# ---------------------------------------------------------------------------
# Batch research  (Feature 3)
# ---------------------------------------------------------------------------

class BatchJob(Base):
    """
    Top-level entity for a CSV batch upload.
    status: running | done | partial (some rows failed)
    """
    __tablename__ = "batch_jobs"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    status     = Column(String(20), default="running")
    total_rows = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    rows = relationship("BatchRow", back_populates="batch", cascade="all, delete-orphan")


class BatchRow(Base):
    """
    One row from the uploaded CSV.
    status: queued | running | done | failed
    """
    __tablename__ = "batch_rows"

    id            = Column(Integer, primary_key=True, index=True)
    batch_id      = Column(Integer, ForeignKey("batch_jobs.id", ondelete="CASCADE"), nullable=False)
    row_index     = Column(Integer, nullable=False)
    prospect_name = Column(String(255), nullable=True)
    company_name  = Column(String(512), nullable=True)
    company_url   = Column(String(2048), nullable=True)
    status        = Column(String(20), default="queued")
    session_id    = Column(Integer, ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    error_msg     = Column(String(1000), nullable=True)

    batch = relationship("BatchJob", back_populates="rows")


# ---------------------------------------------------------------------------
# ICP scoring  (Feature 4)
# ---------------------------------------------------------------------------

class ICPProfile(Base):
    """
    User-defined Ideal Customer Profile. One per user (upsert).
    """
    __tablename__ = "icp_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    industry     = Column(String(300), nullable=True)
    company_size = Column(String(150), nullable=True)   # e.g. "50-500 employees"
    roles        = Column(String(500), nullable=True)   # e.g. "VP Sales, CRO, Head of Revenue"
    pain_points  = Column(Text, nullable=True)
    signals      = Column(Text, nullable=True)          # positive buying signals to look for
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")


class ICPScore(Base):
    """
    LLM-generated ICP fit score for a session (1-10).
    breakdown is a dict like {"industry": 8, "role": 9, "pain_match": 7, "signals": 6}
    """
    __tablename__ = "icp_scores"
    __table_args__ = (UniqueConstraint("session_id"),)

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    score      = Column(Integer, nullable=False)          # 1-10 overall
    breakdown  = Column(JSON, nullable=True)              # {criterion: score}
    reasoning  = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ResearchSession")


# ---------------------------------------------------------------------------
# Legacy — kept so existing routes don't break during migration.
# Will be removed in a later step once all routes are updated.
# ---------------------------------------------------------------------------

class ResearchRun(Base):
    __tablename__ = "research_runs"

    id         = Column(Integer, primary_key=True, index=True)
    run_type   = Column(String(50), nullable=False)
    input_text = Column(Text, nullable=True)
    input_meta = Column(Text, nullable=True)
    output_text = Column(Text, nullable=True)
    source     = Column(String(1024), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
