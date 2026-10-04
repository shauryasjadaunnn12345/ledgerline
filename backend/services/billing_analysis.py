"""Deterministic billing calculations and evidence-grounded case analysis."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


CENT = Decimal("0.01")
EVIDENCE_TYPES = {"invoice_line_item", "contract_rule", "usage_event", "payment_adjustment"}


def _decimal(value: Any, field: str, *, money: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a valid number") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a finite, non-negative number")
    if money and result != result.quantize(CENT):
        raise ValueError(f"{field} may have at most two decimal places")
    return result.quantize(CENT, rounding=ROUND_HALF_UP) if money else result


def normalize_evidence(evidence_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if evidence_type not in EVIDENCE_TYPES:
        raise ValueError(f"Unsupported billing evidence type: {evidence_type}")

    normalized = dict(data)
    if evidence_type == "invoice_line_item":
        for field in ("line_id", "description"):
            if not str(normalized.get(field, "")).strip():
                raise ValueError(f"{field} is required")
        normalized["quantity"] = str(_decimal(normalized.get("quantity"), "quantity"))
        normalized["unit_price"] = str(_decimal(normalized.get("unit_price"), "unit_price", money=True))
        normalized["billed_amount"] = str(_decimal(normalized.get("billed_amount"), "billed_amount", money=True))
    elif evidence_type == "contract_rule":
        for field in ("line_id", "description"):
            if not str(normalized.get(field, "")).strip():
                raise ValueError(f"{field} is required")
        normalized["allowed_unit_price"] = str(
            _decimal(normalized.get("allowed_unit_price"), "allowed_unit_price", money=True)
        )
        normalized["quantity_source"] = normalized.get("quantity_source", "invoice")
        if normalized["quantity_source"] not in {"invoice", "usage"}:
            raise ValueError("quantity_source must be 'invoice' or 'usage'")
    elif evidence_type == "usage_event":
        for field in ("line_id", "description"):
            if not str(normalized.get(field, "")).strip():
                raise ValueError(f"{field} is required")
        normalized["quantity"] = str(_decimal(normalized.get("quantity"), "quantity"))
    else:
        if normalized.get("kind") not in {"payment", "credit", "debit_adjustment"}:
            raise ValueError("kind must be payment, credit, or debit_adjustment")
        normalized["amount"] = str(_decimal(normalized.get("amount"), "amount", money=True))
        normalized.setdefault("reference", "")
        normalized.setdefault("description", normalized["kind"].replace("_", " ").title())

    return normalized


def _money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def analyze_billing(evidence: list[Any], dispute_description: str | None = None) -> dict[str, Any]:
    grouped: dict[str, list[Any]] = {kind: [] for kind in EVIDENCE_TYPES}
    for item in evidence:
        if item.evidence_type in grouped:
            grouped[item.evidence_type].append(item)

    line_groups: dict[str, list[Any]] = {}
    for item in grouped["invoice_line_item"]:
        line_groups.setdefault(item.payload["line_id"], []).append(item)

    lines = []
    line_evidence: dict[str, list[Any]] = {}
    conflicting_line_ids: set[str] = set()
    findings: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for line_id, records in line_groups.items():
        line_evidence[line_id] = records
        first = records[0]
        if any(record.payload != first.payload for record in records[1:]):
            conflicting_line_ids.add(line_id)
            citations = [f"BE-{record.id}" for record in records]
            findings.append({
                "kind": "conflicting_invoice_line",
                "text": f"Multiple different invoice records use line ID {line_id}; no amount was calculated for this line.",
                "citations": citations,
            })
            missing.append({
                "item": f"invoice_line_item:{line_id}",
                "reason": f"Provide one authoritative invoice line for {line_id}; the supplied records conflict.",
                "citations": citations,
            })
            continue
        lines.append(first)
        if len(records) > 1:
            findings.append({
                "kind": "duplicate_invoice_line",
                "text": f"Identical invoice evidence for line {line_id} was submitted {len(records)} times and counted once.",
                "citations": [f"BE-{record.id}" for record in records],
            })

    rules = {item.payload["line_id"]: item for item in grouped["contract_rule"]}
    usage_by_line: dict[str, list[Any]] = {}
    for item in grouped["usage_event"]:
        usage_by_line.setdefault(item.payload["line_id"], []).append(item)

    line_results: list[dict[str, Any]] = []
    invoice_total = Decimal("0.00")
    invoice_extension_total = Decimal("0.00")
    recalculated_total = Decimal("0.00")
    complete = bool(lines) and not conflicting_line_ids

    if not lines:
        missing.append({"item": "invoice_line_item", "reason": "Invoice line items are required to recalculate the bill.", "citations": []})

    for line in lines:
        line_data = line.payload
        line_id = line_data["line_id"]
        billed = Decimal(line_data["billed_amount"])
        invoice_total += billed
        rule = rules.get(line_id)
        line_sources = [f"BE-{source.id}" for source in line_evidence[line_id]]
        line_result = {
            "line_id": line_id,
            "description": line_data["description"],
            "billed_quantity": line_data["quantity"],
            "unit_price": line_data["unit_price"],
            "billed_amount": _money(billed),
            "expected_amount": None,
            "quantity_source": None,
            "citations": line_sources,
        }
        billed_from_line_price = (
            Decimal(line_data["quantity"]) * Decimal(line_data["unit_price"])
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        invoice_extension_total += billed_from_line_price
        line_result["invoice_calculated_amount"] = _money(billed_from_line_price)
        line_result["invoice_amount_variance"] = _money(billed - billed_from_line_price)
        if billed != billed_from_line_price:
            findings.append({
                "kind": "calculation_error",
                "text": (
                    f"{line_data['description']} lists {line_data['quantity']} units at "
                    f"{line_data['unit_price']} each, which totals {_money(billed_from_line_price)} "
                    f"rather than the billed amount {_money(billed)}."
                ),
                "citations": line_sources,
            })

        if rule is None:
            complete = False
            missing.append({
                "item": f"contract_rule:{line_id}",
                "reason": f"A pricing rule for invoice line {line_id} is missing.",
                "citations": line_sources,
            })
            findings.append({
                "kind": "unclear_contract_interpretation",
                "text": f"The contract price for {line_data['description']} cannot be verified without a matching rule.",
                "citations": line_sources,
            })
        else:
            rule_data = rule.payload
            line_sources.append(f"BE-{rule.id}")
            quantity = Decimal(line_data["quantity"])
            quantity_source = rule_data["quantity_source"]
            if quantity_source == "usage":
                usage_events = usage_by_line.get(line_id, [])
                if not usage_events:
                    complete = False
                    missing.append({
                        "item": f"usage_event:{line_id}",
                        "reason": f"Usage events for {line_data['description']} are required by the supplied pricing rule.",
                        "citations": [f"BE-{rule.id}"],
                    })
                    findings.append({
                        "kind": "missing_evidence",
                        "text": f"The rule prices {line_data['description']} by usage, but no matching usage events were supplied.",
                        "citations": [f"BE-{rule.id}"],
                    })
                    quantity = None
                else:
                    quantity = sum((Decimal(event.payload["quantity"]) for event in usage_events), Decimal("0"))
                    line_sources.extend(f"BE-{event.id}" for event in usage_events)

            line_result.update({
                "quantity_source": quantity_source,
                "citations": line_sources,
            })
            if quantity is not None:
                expected = (quantity * Decimal(rule_data["allowed_unit_price"])).quantize(CENT, rounding=ROUND_HALF_UP)
                line_result.update({
                    "expected_amount": _money(expected),
                    "recalculated_quantity": str(quantity),
                })
                recalculated_total += expected
                difference = billed - expected
                if difference:
                    findings.append({
                        "kind": "calculation_error",
                        "text": f"{line_data['description']} was billed at {_money(billed)}; supplied rule and quantity recalculate to {_money(expected)} (difference {_money(difference)}).",
                        "citations": line_sources,
                    })

        line_results.append(line_result)

    payments = Decimal("0.00")
    credits = Decimal("0.00")
    debit_adjustments = Decimal("0.00")
    payment_sources: list[str] = []
    for item in grouped["payment_adjustment"]:
        amount = Decimal(item.payload["amount"])
        payment_sources.append(f"BE-{item.id}")
        if item.payload["kind"] == "payment":
            payments += amount
        elif item.payload["kind"] == "credit":
            credits += amount
        else:
            debit_adjustments += amount

    if not grouped["payment_adjustment"]:
        missing.append({
            "item": "payment_adjustment",
            "reason": "Payment and adjustment history is needed to confirm the remaining balance.",
            "citations": [],
        })

    payment_history_complete = bool(grouped["payment_adjustment"])
    original_balance = (
        invoice_total - payments - credits + debit_adjustments
        if payment_history_complete and lines and not conflicting_line_ids
        else None
    )
    recalculated_balance = (
        recalculated_total - payments - credits + debit_adjustments
        if complete and payment_history_complete
        else None
    )
    if payment_sources:
        findings.append({
            "kind": "payment_history",
            "text": f"Payment history records {_money(payments)} in payments, {_money(credits)} in credits, and {_money(debit_adjustments)} in debit adjustments.",
            "citations": payment_sources,
        })

    if not findings and complete:
        findings.append({
            "kind": "no_calculation_variance",
            "text": "No arithmetic difference was found for the supplied invoice lines and pricing rules.",
            "citations": [f"BE-{item.id}" for item in lines + grouped["contract_rule"]],
        })
    elif not findings:
        findings.append({
            "kind": "insufficient_evidence",
            "text": "No calculation conclusion is available until the required invoice and pricing evidence is supplied.",
            "citations": [],
        })

    if not complete:
        summary = "The invoice cannot be fully recalculated because required billing evidence is missing."
    elif any(item["kind"] == "calculation_error" for item in findings):
        summary = "The supplied contract rules and usage evidence identify one or more invoice calculation differences."
    else:
        summary = "The supplied invoice lines and contract rules reconcile without a calculation difference."
    if dispute_description:
        summary += f" Customer dispute: {dispute_description.strip()}"

    options = []
    if complete and any(item["kind"] == "calculation_error" for item in findings):
        if invoice_total > recalculated_total:
            options.append({"action": "credit_difference", "amount": _money(invoice_total - recalculated_total), "label": "Approve a mock credit for the overbilled amount, subject to reviewer approval."})
        else:
            options.append({"action": "review_undercharge", "amount": None, "label": "Review the verified undercharge and contract terms before issuing a corrected balance."})
        options.append({"action": "correct_invoice", "amount": _money(recalculated_total), "label": "Issue a corrected invoice using the recalculated line amounts."})
    elif not complete:
        options.append({"action": "request_information", "amount": None, "label": "Request the missing billing evidence before deciding the disputed amount."})
    else:
        options.append({"action": "uphold_invoice", "amount": _money(invoice_total), "label": "Uphold the supplied invoice calculation, pending confirmation of payment history."})

    calculation = {
        "currency": "USD",
        "invoice_total": _money(invoice_total) if lines and not conflicting_line_ids else None,
        "invoice_extension_total": _money(invoice_extension_total) if lines and not conflicting_line_ids else None,
        "recalculated_total": _money(recalculated_total) if complete else None,
        "original_balance": _money(original_balance) if original_balance is not None else None,
        "recalculated_balance": _money(recalculated_balance) if recalculated_balance is not None else None,
        "payments_total": _money(payments),
        "credits_total": _money(credits),
        "debit_adjustments_total": _money(debit_adjustments),
        "payment_history_complete": payment_history_complete,
        "complete": complete,
        "lines": line_results,
    }
    return {
        "calculation": calculation,
        "summary": summary,
        "findings": findings,
        "missing_evidence": missing,
        "resolution_options": options,
    }