"""SQLAlchemy ORM models for invoice dispute investigation."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(Integer, primary_key=True, index=True)
    card_member_id = Column(String, nullable=False, index=True)
    merchant_id = Column(String, nullable=False, index=True)
    reason_code = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    evidence = relationship(
        "Evidence", back_populates="dispute", cascade="all, delete-orphan"
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id"), nullable=False, index=True)
    submitted_by = Column(String, nullable=False)
    evidence_type = Column(String, nullable=False)
    raw_text = Column(Text, nullable=True)
    parsed_fields = Column(JSON, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    dispute = relationship("Dispute", back_populates="evidence")


class BillingEvidence(Base):
    __tablename__ = "billing_evidence"

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id"), nullable=False, index=True)
    evidence_type = Column(String, nullable=False)
    submitted_by = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BillingCalculation(Base):
    __tablename__ = "billing_calculations"

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id"), nullable=False, index=True)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CaseAnalysis(Base):
    __tablename__ = "case_analyses"

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id"), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    findings = Column(JSON, nullable=False)
    missing_evidence = Column(JSON, nullable=False)
    resolution_options = Column(JSON, nullable=False)
    agent_status = Column(String, nullable=False, default="disabled")
    agent_interpretation = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReviewerAction(Base):
    __tablename__ = "reviewer_actions"

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id"), nullable=False, index=True)
    action = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    edited_findings = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class MockAdjustment(Base):
    __tablename__ = "mock_adjustments"
    __table_args__ = (UniqueConstraint("dispute_id", name="uq_mock_adjustment_dispute"),)

    id = Column(Integer, primary_key=True, index=True)
    dispute_id = Column(Integer, ForeignKey("disputes.id"), nullable=False, index=True)
    amount_cents = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    approved_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
