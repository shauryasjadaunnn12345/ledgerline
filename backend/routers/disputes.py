"""Invoice-case lifecycle endpoints and deterministic billing reconciliation."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.db_models import (
    BillingCalculation,
    BillingEvidence,
    CaseAnalysis,
    Dispute,
    Evidence,
    MockAdjustment,
    ReviewerAction,
)
from backend.models.schemas import (
    DisputeCreate,
    DisputeOut,
    BillingEvidenceCreate,
    BillingEvidenceOut,
    MockAdjustmentCreate,
    ReviewerActionCreate,
    StatusOut,
)
from backend.services import billing_analysis, llm_parser

router = APIRouter(prefix="/disputes", tags=["disputes"])

def _reconciliation_is_stale(db: Session, dispute_id: int, calculation: BillingCalculation | None) -> bool:
    if calculation is None:
        return False
    latest_billing_id = (
        db.query(BillingEvidence.id)
        .filter(BillingEvidence.dispute_id == dispute_id)
        .order_by(BillingEvidence.id.desc())
        .limit(1)
        .scalar()
    ) or 0
    latest_evidence_id = (
        db.query(Evidence.id)
        .filter(Evidence.dispute_id == dispute_id)
        .order_by(Evidence.id.desc())
        .limit(1)
        .scalar()
    ) or 0
    return (
        latest_billing_id > calculation.result.get("evidence_high_watermark", 0)
        or latest_evidence_id > calculation.result.get("traditional_evidence_high_watermark", 0)
    )


def _case_status(dispute: Dispute, calculation: BillingCalculation | None, stale: bool) -> str:
    if (
        dispute.status == "pending_review"
        and calculation is not None
        and not stale
        and not calculation.result.get("complete", False)
    ):
        return "awaiting_information"
    return dispute.status


def _cached_interpretation_is_current(
    calculation: BillingCalculation | None,
    analysis: CaseAnalysis | None,
    current_calculation: dict,
    evidence_high_watermark: int,
    traditional_evidence_high_watermark: int,
) -> dict | None:
    if (
        calculation is None
        or analysis is None
        or analysis.agent_status not in {"complete", "cached"}
        or not analysis.agent_interpretation
        or calculation.result.get("evidence_high_watermark") != evidence_high_watermark
        or calculation.result.get("traditional_evidence_high_watermark")
        != traditional_evidence_high_watermark
    ):
        return None

    previous_calculation = dict(calculation.result)
    previous_calculation.pop("evidence_high_watermark", None)
    previous_calculation.pop("traditional_evidence_high_watermark", None)
    if previous_calculation != current_calculation:
        return None
    return analysis.agent_interpretation


def _adjustment_response(adjustment: MockAdjustment) -> dict:
    return {
        "id": adjustment.id,
        "dispute_id": adjustment.dispute_id,
        "amount": f"{Decimal(adjustment.amount_cents) / 100:.2f}",
        "reason": adjustment.reason,
        "approved_by": adjustment.approved_by,
        "created_at": adjustment.created_at,
    }


def _billing_evidence_response(evidence: BillingEvidence, duplicate_ignored: bool = False) -> dict:
    return {
        "id": evidence.id,
        "dispute_id": evidence.dispute_id,
        "evidence_type": evidence.evidence_type,
        "submitted_by": evidence.submitted_by,
        "payload": evidence.payload,
        "created_at": evidence.created_at,
        "duplicate_ignored": duplicate_ignored,
    }


@router.post("", response_model=DisputeOut)
def create_dispute(payload: DisputeCreate, db: Session = Depends(get_db)):
    dispute = Dispute(
        card_member_id=payload.customer_id,
        merchant_id="invoice_case",
        reason_code="invoice_dispute",
        amount=payload.amount,
        status="open",
    )
    db.add(dispute)
    db.commit()
    db.refresh(dispute)
    if payload.description and payload.description.strip():
        db.add(Evidence(
            dispute_id=dispute.id,
            submitted_by="customer",
            evidence_type="customer_dispute_description",
            raw_text=payload.description.strip(),
            parsed_fields=None,
        ))
        db.commit()
    return dispute


@router.get("/{dispute_id}/status", response_model=StatusOut)
def get_dispute_status(dispute_id: int, db: Session = Depends(get_db)):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    billing_count = db.query(BillingEvidence).filter(BillingEvidence.dispute_id == dispute_id).count()
    latest_calculation = (
        db.query(BillingCalculation)
        .filter(BillingCalculation.dispute_id == dispute_id)
        .order_by(BillingCalculation.created_at.desc(), BillingCalculation.id.desc())
        .first()
    )
    stale = _reconciliation_is_stale(db, dispute_id, latest_calculation)
    return StatusOut(
        dispute_id=dispute_id,
        status=_case_status(dispute, latest_calculation, stale),
        billing_evidence_count=billing_count,
        reconciliation_stale=stale,
    )


@router.post("/{dispute_id}/billing-evidence", response_model=BillingEvidenceOut)
def submit_billing_evidence(
    dispute_id: int, payload: BillingEvidenceCreate, db: Session = Depends(get_db)
):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    try:
        normalized = billing_analysis.normalize_evidence(payload.evidence_type, payload.data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if payload.evidence_type == "invoice_line_item":
        existing_lines = (
            db.query(BillingEvidence)
            .filter(
                BillingEvidence.dispute_id == dispute_id,
                BillingEvidence.evidence_type == "invoice_line_item",
            )
            .order_by(BillingEvidence.id.asc())
            .all()
        )
        same_id = [
            item for item in existing_lines
            if item.payload.get("line_id") == normalized["line_id"]
        ]
        if same_id:
            identical = next((item for item in same_id if item.payload == normalized), None)
            if identical:
                return _billing_evidence_response(identical, duplicate_ignored=True)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Invoice line ID '{normalized['line_id']}' already has different evidence. "
                    "Add supporting contract or usage evidence instead of a second invoice line."
                ),
            )

    evidence = BillingEvidence(
        dispute_id=dispute_id,
        evidence_type=payload.evidence_type,
        submitted_by=payload.submitted_by,
        payload=normalized,
    )
    db.add(evidence)
    if dispute.status in {"resolved", "pending_review", "reviewed", "rejected", "adjusted", "awaiting_information"}:
        dispute.status = "reopened"
        db.add(ReviewerAction(
            dispute_id=dispute_id,
            action="reopened_by_new_evidence",
            note="New billing evidence was added after an earlier conclusion.",
        ))
    db.commit()
    db.refresh(evidence)
    return _billing_evidence_response(evidence)


@router.get("/{dispute_id}/billing-evidence", response_model=list[BillingEvidenceOut])
def list_billing_evidence(dispute_id: int, db: Session = Depends(get_db)):
    if db.get(Dispute, dispute_id) is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return (
        db.query(BillingEvidence)
        .filter(BillingEvidence.dispute_id == dispute_id)
        .order_by(BillingEvidence.id.asc())
        .all()
    )


@router.post("/{dispute_id}/reconcile")
def reconcile_billing(dispute_id: int, db: Session = Depends(get_db)):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    evidence = (
        db.query(BillingEvidence)
        .filter(BillingEvidence.dispute_id == dispute_id)
        .order_by(BillingEvidence.id.asc())
        .all()
    )
    description_record = (
        db.query(Evidence)
        .filter(
            Evidence.dispute_id == dispute_id,
            Evidence.evidence_type == "customer_dispute_description",
        )
        .order_by(Evidence.id.desc())
        .first()
    )
    result = billing_analysis.analyze_billing(
        evidence,
        description_record.raw_text if description_record else None,
    )
    high_watermark = max((item.id for item in evidence), default=0)
    traditional_high_watermark = (
        db.query(Evidence.id)
        .filter(Evidence.dispute_id == dispute_id)
        .order_by(Evidence.id.desc())
        .limit(1)
        .scalar()
        or 0
    )
    agent_status, agent_interpretation = llm_parser.interpret_billing_case(
        evidence,
        result["calculation"],
        description_record.raw_text if description_record else None,
    )
    if agent_status == "unavailable":
        previous_analysis = (
            db.query(CaseAnalysis)
            .filter(CaseAnalysis.dispute_id == dispute_id)
            .filter(CaseAnalysis.agent_status == "complete")
            .filter(CaseAnalysis.agent_interpretation.isnot(None))
            .order_by(CaseAnalysis.id.desc())
            .first()
        )
        previous_calculation = (
            db.get(BillingCalculation, previous_analysis.id)
            if previous_analysis is not None
            else None
        )
        if previous_calculation and previous_calculation.dispute_id != dispute_id:
            previous_calculation = None
        cached_interpretation = _cached_interpretation_is_current(
            previous_calculation,
            previous_analysis,
            result["calculation"],
            high_watermark,
            traditional_high_watermark,
        )
        if cached_interpretation is not None:
            agent_status = "cached"
            agent_interpretation = cached_interpretation
    result["calculation"]["evidence_high_watermark"] = high_watermark
    result["calculation"]["traditional_evidence_high_watermark"] = traditional_high_watermark
    calculation = BillingCalculation(dispute_id=dispute_id, result=result["calculation"])
    analysis = CaseAnalysis(
        dispute_id=dispute_id,
        summary=result["summary"],
        findings=result["findings"],
        missing_evidence=result["missing_evidence"],
        resolution_options=result["resolution_options"],
        agent_status=agent_status,
        agent_interpretation=agent_interpretation,
    )
    db.add_all([calculation, analysis])
    dispute.status = "pending_review" if result["calculation"]["complete"] else "awaiting_information"
    db.commit()
    db.refresh(calculation)
    db.refresh(analysis)
    return {
        "calculation_id": calculation.id,
        "analysis_id": analysis.id,
        "calculation": calculation.result,
        "analysis": {
            "summary": analysis.summary,
            "findings": analysis.findings,
            "missing_evidence": analysis.missing_evidence,
            "resolution_options": analysis.resolution_options,
            "agent_status": analysis.agent_status,
            "agent_interpretation": analysis.agent_interpretation,
        },
        "is_stale": False,
    }


@router.get("/{dispute_id}/reconciliation")
def get_reconciliation(dispute_id: int, db: Session = Depends(get_db)):
    if db.get(Dispute, dispute_id) is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    calculation = (
        db.query(BillingCalculation)
        .filter(BillingCalculation.dispute_id == dispute_id)
        .order_by(BillingCalculation.created_at.desc(), BillingCalculation.id.desc())
        .first()
    )
    analysis = (
        db.query(CaseAnalysis)
        .filter(CaseAnalysis.dispute_id == dispute_id)
        .order_by(CaseAnalysis.created_at.desc(), CaseAnalysis.id.desc())
        .first()
    )
    if calculation is None or analysis is None:
        raise HTTPException(status_code=404, detail="No reconciliation found for this dispute")
    stale = _reconciliation_is_stale(db, dispute_id, calculation)
    latest_edit = (
        db.query(ReviewerAction)
        .filter(ReviewerAction.dispute_id == dispute_id, ReviewerAction.action == "edit")
        .order_by(ReviewerAction.id.desc())
        .first()
    )
    effective_findings = analysis.findings
    if (
        not stale
        and latest_edit
        and latest_edit.edited_findings is not None
        and latest_edit.created_at >= analysis.created_at
    ):
        effective_findings = latest_edit.edited_findings
    return {
        "calculation_id": calculation.id,
        "analysis_id": analysis.id,
        "calculation": calculation.result,
        "analysis": {
            "summary": analysis.summary,
            "findings": effective_findings,
            "missing_evidence": analysis.missing_evidence,
            "resolution_options": analysis.resolution_options,
            "agent_status": analysis.agent_status,
            "agent_interpretation": analysis.agent_interpretation,
        },
        "is_stale": stale,
    }


@router.post("/{dispute_id}/review")
def review_case(dispute_id: int, payload: ReviewerActionCreate, db: Session = Depends(get_db)):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if payload.action in {"accept", "edit", "reject"}:
        latest_calculation = (
            db.query(BillingCalculation)
            .filter(BillingCalculation.dispute_id == dispute_id)
            .order_by(BillingCalculation.id.desc())
            .first()
        )
        if latest_calculation is None:
            raise HTTPException(status_code=409, detail="Reconcile the invoice before reviewing findings")
        if _reconciliation_is_stale(db, dispute_id, latest_calculation):
            raise HTTPException(status_code=409, detail="New evidence was added; reconcile again before reviewing")
        if not latest_calculation.result.get("complete", False):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Required invoice and pricing or usage evidence is missing; "
                    "request information before accepting, editing, or rejecting findings"
                ),
            )
    action = ReviewerAction(
        dispute_id=dispute_id,
        action=payload.action,
        note=payload.note,
        edited_findings=payload.edited_findings,
    )
    dispute.status = {
        "accept": "reviewed",
        "edit": "reviewed",
        "reject": "rejected",
        "request_information": "awaiting_information",
    }[payload.action]
    db.add(action)
    db.commit()
    db.refresh(action)
    return {"id": action.id, "action": action.action, "status": dispute.status, "created_at": action.created_at}


@router.post("/{dispute_id}/adjustments")
def approve_mock_adjustment(
    dispute_id: int, payload: MockAdjustmentCreate, db: Session = Depends(get_db)
):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if not payload.amount.is_finite() or payload.amount <= 0 or payload.amount != payload.amount.quantize(Decimal("0.01")):
        raise HTTPException(status_code=422, detail="amount must be positive and have at most two decimal places")
    existing = db.query(MockAdjustment).filter(MockAdjustment.dispute_id == dispute_id).first()
    if existing:
        if (
            existing.amount_cents == int(payload.amount * 100)
            and existing.reason == payload.reason
            and existing.approved_by == payload.approved_by
        ):
            return _adjustment_response(existing)
        raise HTTPException(status_code=409, detail="A mock adjustment has already been approved for this dispute")
    calculation = (
        db.query(BillingCalculation)
        .filter(BillingCalculation.dispute_id == dispute_id)
        .order_by(BillingCalculation.id.desc())
        .first()
    )
    if calculation is None or not calculation.result.get("complete"):
        raise HTTPException(status_code=409, detail="A complete invoice reconciliation is required before approving an adjustment")
    if _reconciliation_is_stale(db, dispute_id, calculation):
        raise HTTPException(status_code=409, detail="New evidence was added; reconcile again before approving an adjustment")
    difference = max(
        Decimal(calculation.result["invoice_total"]) - Decimal(calculation.result["recalculated_total"]),
        Decimal("0.00"),
    )
    if payload.amount > difference:
        raise HTTPException(status_code=422, detail=f"Adjustment cannot exceed the verified overcharge of {difference:.2f}")
    adjustment = MockAdjustment(
        dispute_id=dispute_id,
        amount_cents=int(payload.amount * 100),
        reason=payload.reason,
        approved_by=payload.approved_by,
    )
    db.add(adjustment)
    db.add(ReviewerAction(
        dispute_id=dispute_id,
        action="approve_adjustment",
        note=f"Approved mock adjustment of {payload.amount:.2f}: {payload.reason}",
    ))
    dispute.status = "adjusted"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(MockAdjustment).filter(MockAdjustment.dispute_id == dispute_id).first()
        if existing and (
            existing.amount_cents == int(payload.amount * 100)
            and existing.reason == payload.reason
            and existing.approved_by == payload.approved_by
        ):
            return _adjustment_response(existing)
        raise HTTPException(status_code=409, detail="A mock adjustment has already been approved for this dispute")
    db.refresh(adjustment)
    return _adjustment_response(adjustment)


@router.post("/{dispute_id}/reopen")
def reopen_case(dispute_id: int, note: str = "New evidence or reconsideration", db: Session = Depends(get_db)):
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    dispute.status = "reopened"
    action = ReviewerAction(dispute_id=dispute_id, action="reopen", note=note)
    db.add(action)
    db.commit()
    return {"dispute_id": dispute_id, "status": dispute.status}


@router.get("/{dispute_id}/history")
def get_case_history(dispute_id: int, db: Session = Depends(get_db)):
    if db.get(Dispute, dispute_id) is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    actions = db.query(ReviewerAction).filter(ReviewerAction.dispute_id == dispute_id).order_by(ReviewerAction.id.asc()).all()
    calculations = db.query(BillingCalculation).filter(BillingCalculation.dispute_id == dispute_id).order_by(BillingCalculation.id.asc()).all()
    analyses = db.query(CaseAnalysis).filter(CaseAnalysis.dispute_id == dispute_id).order_by(CaseAnalysis.id.asc()).all()
    adjustments = db.query(MockAdjustment).filter(MockAdjustment.dispute_id == dispute_id).order_by(MockAdjustment.id.asc()).all()
    return {
        "reviewer_actions": actions,
        "calculations": calculations,
        "analyses": analyses,
        "adjustments": adjustments,
    }


