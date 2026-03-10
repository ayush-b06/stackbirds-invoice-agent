"""
decision_engine.py
Compares extracted invoice line items against contracted rates.
Produces a final APPROVE / FLAG decision with full rationale.
"""

import difflib
from dataclasses import dataclass, field
from typing import Optional
from invoice_extractor import InvoiceData, LineItem
from excel_parser import ContractedRate, Policy
from vendor_matcher import VendorMatchResult


@dataclass
class LineItemResult:
    invoice_item: LineItem
    matched_rate: Optional[ContractedRate]
    match_confidence: float
    contracted_price: Optional[float]
    invoice_price: float
    variance_pct: Optional[float]          # positive = overcharged
    variance_amount: Optional[float]
    within_threshold: Optional[bool]
    flag_reason: Optional[str]
    assumptions: list[str] = field(default_factory=list)


@dataclass
class DecisionResult:
    status: str                            # "APPROVED" | "FLAGGED"
    vendor_match_confidence: float
    variance_detected: bool
    line_results: list[LineItemResult]
    flag_reasons: list[str]
    clarifying_questions: list[str]
    assumptions: list[str]
    total_invoice: float
    total_contracted: Optional[float]
    total_variance_amount: Optional[float]


def run_decision(
    invoice: InvoiceData,
    rates: dict[str, ContractedRate],
    policy: Policy,
    vendor_result: VendorMatchResult,
) -> DecisionResult:
    """
    Core decision logic. APPROVED only if ALL of:
      - vendor matched with confidence ≥ 0.90
      - every line item matched a contracted rate
      - all variances within threshold
      - no extraction warnings that affect totals
    Otherwise: FLAGGED.
    """
    flag_reasons: list[str] = []
    clarifying_questions: list[str] = list(vendor_result.clarifying_questions)
    assumptions: list[str] = []
    line_results: list[LineItemResult] = []
    variance_detected = False

    # ── 1. Vendor check ─────────────────────────────────────────────────────
    if not vendor_result.matched:
        flag_reasons.append(
            f"Vendor not matched in approved list "
            f"(confidence {vendor_result.confidence:.0%}, method={vendor_result.match_method})"
        )

    # ── 2. Line-item matching ────────────────────────────────────────────────
    total_contracted = 0.0
    total_contracted_valid = True

    for item in invoice.line_items:
        result = _match_line_item(item, rates, policy)
        line_results.append(result)

        if result.flag_reason:
            flag_reasons.append(result.flag_reason)
        if result.assumptions:
            assumptions.extend(result.assumptions)

        if result.variance_pct is not None and abs(result.variance_pct) > 0.001:
            variance_detected = True

        if result.contracted_price is not None:
            total_contracted += result.contracted_price * item.quantity
        else:
            total_contracted_valid = False

    # ── 3. Total sanity check ────────────────────────────────────────────────
    # Recompute expected total from line items
    computed_subtotal = sum(i.line_total for i in invoice.line_items)
    if invoice.subtotal is not None:
        sub_diff = abs(computed_subtotal - invoice.subtotal)
        if sub_diff > 0.02:  # > 2 cents discrepancy
            flag_reasons.append(
                f"Invoice subtotal ({invoice.subtotal:.2f}) does not match sum of line items "
                f"({computed_subtotal:.2f}). Difference: {sub_diff:.2f}."
            )
            clarifying_questions.append(
                "The invoice subtotal does not match the sum of line items. "
                "Is there a discount, credit, or missing line item?"
            )

    # ── 4. Extraction confidence ─────────────────────────────────────────────
    if invoice.confidence < 0.80:
        flag_reasons.append(
            f"Invoice extraction confidence is low ({invoice.confidence:.0%}). "
            "Manual review of source document recommended."
        )
    if invoice.extraction_warnings:
        for w in invoice.extraction_warnings:
            flag_reasons.append(f"Extraction warning: {w}")

    # ── 5. Final verdict ─────────────────────────────────────────────────────
    status = "APPROVED" if not flag_reasons else "FLAGGED"

    total_variance = None
    if total_contracted_valid and total_contracted > 0:
        total_variance = invoice.total - total_contracted

    return DecisionResult(
        status=status,
        vendor_match_confidence=vendor_result.confidence,
        variance_detected=variance_detected,
        line_results=line_results,
        flag_reasons=flag_reasons,
        clarifying_questions=clarifying_questions,
        assumptions=assumptions,
        total_invoice=invoice.total,
        total_contracted=total_contracted if total_contracted_valid else None,
        total_variance_amount=total_variance,
    )


def _match_line_item(
    item: LineItem,
    rates: dict[str, ContractedRate],
    policy: Policy,
) -> LineItemResult:
    assumptions = []
    flag_reason = None

    # Try SKU lookup first (exact, then normalized)
    matched_rate = None
    match_conf = 0.0

    if item.sku:
        sku_key = item.sku.upper().strip()
        if sku_key in rates:
            matched_rate = rates[sku_key]
            match_conf = 1.0
        else:
            # Try fuzzy SKU match
            best_sku, best_score = _fuzzy_key_match(sku_key, list(rates.keys()))
            if best_score >= 0.85:
                matched_rate = rates[best_sku]
                match_conf = best_score
                assumptions.append(
                    f"SKU '{item.sku}' fuzzy-matched to contracted SKU '{best_sku}' "
                    f"({best_score:.0%} confidence)."
                )

    # Fallback: description-based fuzzy match
    if matched_rate is None:
        best_sku, best_score = _description_match(item.description, rates)
        if best_score >= 0.75:
            matched_rate = rates[best_sku]
            match_conf = best_score
            assumptions.append(
                f"No SKU on line item; matched by description to '{matched_rate.sku}' "
                f"({best_score:.0%} confidence)."
            )

    # Compute variance
    contracted_price = matched_rate.unit_price if matched_rate else None
    invoice_price    = item.unit_price
    variance_pct     = None
    variance_amount  = None
    within_threshold = None

    if contracted_price is not None and contracted_price > 0:
        variance_pct    = (invoice_price - contracted_price) / contracted_price
        variance_amount = (invoice_price - contracted_price) * item.quantity
        within_threshold = abs(variance_pct) <= policy.variance_threshold_pct

        if not within_threshold:
            direction = "overcharged" if variance_pct > 0 else "undercharged"
            flag_reason = (
                f"Line item '{item.description}': invoice price {invoice_price:.2f} vs "
                f"contracted {contracted_price:.2f} — {direction} by "
                f"{abs(variance_pct):.1%} ({abs(variance_amount):.2f}), "
                f"exceeds {policy.variance_threshold_pct:.0%} threshold."
            )
    elif contracted_price is None:
        flag_reason = (
            f"Line item '{item.description}' (SKU: {item.sku or 'N/A'}) "
            "could not be matched to any contracted rate."
        )

    return LineItemResult(
        invoice_item=item,
        matched_rate=matched_rate,
        match_confidence=match_conf,
        contracted_price=contracted_price,
        invoice_price=invoice_price,
        variance_pct=variance_pct,
        variance_amount=variance_amount,
        within_threshold=within_threshold,
        flag_reason=flag_reason,
        assumptions=assumptions,
    )


def _fuzzy_key_match(query: str, keys: list[str]) -> tuple[str, float]:
    if not keys:
        return ("", 0.0)
    scores = [(k, difflib.SequenceMatcher(None, query, k).ratio()) for k in keys]
    return max(scores, key=lambda x: x[1])


def _description_match(description: str, rates: dict[str, ContractedRate]) -> tuple[str, float]:
    if not rates:
        return ("", 0.0)
    desc_lower = description.lower()
    scores = []
    for sku, rate in rates.items():
        candidate = (rate.description or "").lower()
        score = difflib.SequenceMatcher(None, desc_lower, candidate).ratio()
        # Bonus: word overlap
        a_words = set(desc_lower.split())
        b_words = set(candidate.split())
        if a_words and b_words:
            overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
            score = 0.6 * score + 0.4 * overlap
        scores.append((sku, score))
    return max(scores, key=lambda x: x[1])
