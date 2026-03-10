"""
audit_logger.py
Produces a structured audit trail documenting every step of the processing pipeline.
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from invoice_extractor import InvoiceData
from vendor_matcher import VendorMatchResult
from decision_engine import DecisionResult


@dataclass
class AuditEvent:
    timestamp: str
    stage: str
    action: str
    detail: str
    uncertainty: bool = False


@dataclass
class AuditTrail:
    run_id: str
    invoice_file: str
    processed_at: str
    events: list[AuditEvent] = field(default_factory=list)
    extraction_summary: dict = field(default_factory=dict)
    vendor_match_summary: dict = field(default_factory=dict)
    decision_summary: dict = field(default_factory=dict)
    final_status: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def build_audit_trail(
    invoice_file: str,
    invoice: InvoiceData,
    vendor_result: VendorMatchResult,
    decision: DecisionResult,
    excel_warnings: list[str],
) -> AuditTrail:
    import uuid
    run_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now(timezone.utc).isoformat()

    trail = AuditTrail(
        run_id=run_id,
        invoice_file=invoice_file,
        processed_at=now,
    )

    # Excel loading
    if excel_warnings:
        for w in excel_warnings:
            trail.events.append(AuditEvent(
                timestamp=now, stage="EXCEL_LOAD", action="WARNING",
                detail=w, uncertainty=True
            ))
    else:
        trail.events.append(AuditEvent(
            timestamp=now, stage="EXCEL_LOAD", action="SUCCESS",
            detail="Reference Excel loaded successfully."
        ))

    # invoice extraction
    trail.events.append(AuditEvent(
        timestamp=now, stage="EXTRACTION", action="COMPLETE",
        detail=f"Extracted invoice from '{invoice_file}' with confidence {invoice.confidence:.0%}.",
        uncertainty=invoice.confidence < 0.85
    ))
    for w in invoice.extraction_warnings:
        trail.events.append(AuditEvent(
            timestamp=now, stage="EXTRACTION", action="WARNING",
            detail=w, uncertainty=True
        ))
    trail.extraction_summary = {
        "vendor_name": invoice.vendor_name,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "line_item_count": len(invoice.line_items),
        "total": invoice.total,
        "currency": invoice.currency,
        "confidence": invoice.confidence,
        "warnings": invoice.extraction_warnings,
    }

    # match vendor
    trail.events.append(AuditEvent(
        timestamp=now, stage="VENDOR_MATCH", action="RESULT",
        detail=(
            f"Vendor '{invoice.vendor_name}' matched={vendor_result.matched}, "
            f"method={vendor_result.match_method}, "
            f"confidence={vendor_result.confidence:.0%}. "
            f"Matched to: {vendor_result.matched_vendor.canonical_name if vendor_result.matched_vendor else 'N/A'}"
        ),
        uncertainty=not vendor_result.matched
    ))
    trail.vendor_match_summary = {
        "extracted_name": invoice.vendor_name,
        "matched": vendor_result.matched,
        "match_method": vendor_result.match_method,
        "confidence": vendor_result.confidence,
        "canonical_name": vendor_result.matched_vendor.canonical_name if vendor_result.matched_vendor else None,
    }

    # compare line item
    for lr in decision.line_results:
        item = lr.invoice_item
        matched_sku = lr.matched_rate.sku if lr.matched_rate else "UNMATCHED"
        trail.events.append(AuditEvent(
            timestamp=now, stage="LINE_COMPARISON", action="ITEM",
            detail=(
                f"'{item.description}' (SKU: {item.sku or 'N/A'}) → contracted SKU: {matched_sku} | "
                f"invoice: {item.unit_price:.2f} contracted: {lr.contracted_price or 'N/A'} | "
                f"variance: {lr.variance_pct:.1%}" if lr.variance_pct is not None else
                f"'{item.description}' → no contracted rate found"
            ),
            uncertainty=lr.flag_reason is not None
        ))
        for a in lr.assumptions:
            trail.events.append(AuditEvent(
                timestamp=now, stage="LINE_COMPARISON", action="ASSUMPTION",
                detail=a, uncertainty=True
            ))

    # decision final
    for reason in decision.flag_reasons:
        trail.events.append(AuditEvent(
            timestamp=now, stage="DECISION", action="FLAG_REASON",
            detail=reason, uncertainty=True
        ))
    trail.events.append(AuditEvent(
        timestamp=now, stage="DECISION", action="FINAL",
        detail=f"Status: {decision.status}. Flag count: {len(decision.flag_reasons)}."
    ))
    trail.decision_summary = {
        "status": decision.status,
        "vendor_match_confidence": decision.vendor_match_confidence,
        "variance_detected": decision.variance_detected,
        "flag_count": len(decision.flag_reasons),
        "flag_reasons": decision.flag_reasons,
        "clarifying_questions": decision.clarifying_questions,
        "assumptions_made": decision.assumptions,
        "total_invoice": decision.total_invoice,
        "total_contracted": decision.total_contracted,
        "total_variance_amount": decision.total_variance_amount,
    }
    trail.final_status = decision.status

    return trail
