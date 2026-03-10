"""
generate_demo_outputs.py
Generates three example HTML reports (clean, messy, edge-case) using mock data.
Run this to produce sample outputs without needing real invoice files.

Usage: python generate_demo_outputs.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from invoice_extractor import InvoiceData, LineItem
from vendor_matcher import VendorMatchResult, VendorRecord
from decision_engine import DecisionResult, LineItemResult
from excel_parser import Policy, ContractedRate
from report_generator import generate_html_report
from audit_logger import build_audit_trail
import json
from pathlib import Path

out = Path("../outputs/demo")
out.mkdir(parents=True, exist_ok=True)

policy = Policy(
    variance_threshold_pct=0.05,
    tax_policy="Tax exempt on professional services",
    shipping_policy="Shipping included in unit price above $500 orders",
    notes=""
)


# invoice 1
rate_a = ContractedRate("SKU-001", "Widget Type A", 12.50, "each")
rate_b = ContractedRate("SKU-002", "Consulting Services (hr)", 150.00, "hour")

invoice_clean = InvoiceData(
    vendor_name="Acme Corporation",
    invoice_number="INV-2025-0847",
    invoice_date="2025-03-01",
    due_date="2025-03-31",
    currency="USD",
    line_items=[
        LineItem("Widget Type A", 100, 12.50, 1250.00, "SKU-001", "each"),
        LineItem("Consulting Services", 8,   150.00, 1200.00, "SKU-002", "hour"),
    ],
    subtotal=2450.00,
    tax_amount=0.0,
    tax_rate_pct=0.0,
    shipping=0.0,
    total=2450.00,
    notes="Net 30 payment terms. PO #PO-2025-112.",
    extraction_warnings=[],
    confidence=0.98,
)

vendor_clean = VendorMatchResult(
    matched=True, confidence=1.0,
    matched_vendor=VendorRecord("Acme Corporation", ["Acme Corp", "Acme"], "V001"),
    match_method="exact", clarifying_questions=[]
)

lr1 = LineItemResult(invoice_clean.line_items[0], rate_a, 1.0, 12.50, 12.50, 0.0, 0.0, True, None)
lr2 = LineItemResult(invoice_clean.line_items[1], rate_b, 1.0, 150.00, 150.00, 0.0, 0.0, True, None)

decision_clean = DecisionResult(
    status="APPROVED",
    vendor_match_confidence=1.0,
    variance_detected=False,
    line_results=[lr1, lr2],
    flag_reasons=[],
    clarifying_questions=[],
    assumptions=[],
    total_invoice=2450.00,
    total_contracted=2450.00,
    total_variance_amount=0.0,
)

html = generate_html_report(invoice_clean, vendor_clean, decision_clean, policy)
(out / "invoice1_clean_report.html").write_text(html)

payload = {"status": "APPROVED", "vendor_match_confidence": 1.0, "variance_detected": False,
           "invoice_number": "INV-2025-0847", "total_invoice": 2450.00, "total_contracted": 2450.00,
           "total_variance_amount": 0.0, "flag_reasons": [], "clarifying_questions": []}
(out / "invoice1_clean_payload.json").write_text(json.dumps(payload, indent=2))

trail = build_audit_trail("invoice1_clean.pdf", invoice_clean, vendor_clean, decision_clean, [])
(out / "invoice1_clean_audit.json").write_text(trail.to_json())
print("✓ Invoice 1 (clean) generated")


# invoice 2
rate_c = ContractedRate("SKU-003", "Industrial Pump Unit", 4200.00, "unit")
rate_d = ContractedRate("SKU-004", "Maintenance Kit",       85.00, "kit")

invoice_messy = InvoiceData(
    vendor_name="Globex Supplis Inc",  # Supplis??
    invoice_number=None,             # doesn't have invoice number as well
    invoice_date="2025-02-28",
    due_date=None,
    currency="USD",
    line_items=[
        LineItem("Industrial Pump Unit (Model X)", 2, 4410.00, 8820.00, "SKU-003", "unit"),
        LineItem("Maint. Kit",                     5, 85.00,   425.00,  "SKU-004", "kit"),
    ],
    subtotal=9245.00,
    tax_amount=739.60,
    tax_rate_pct=8.0,
    shipping=150.00,
    total=10134.60,
    notes=None,
    extraction_warnings=[
        "Invoice number field appears blank or cut off",
        "Low print quality on header section — vendor address not extracted",
    ],
    confidence=0.74,
)

vendor_messy = VendorMatchResult(
    matched=False, confidence=0.81,
    matched_vendor=VendorRecord("Globex Supplies Inc", ["Globex", "Globex Supply"], "V002"),
    match_method="fuzzy",
    clarifying_questions=[
        'Invoice shows vendor "Globex Supplis Inc" — closest approved vendor is '
        '"Globex Supplies Inc" (similarity 81%). Can you confirm these are the same entity?'
    ]
)

lr3 = LineItemResult(
    invoice_messy.line_items[0], rate_c, 0.92, 4200.00, 4410.00,
    0.05, 420.00, False,
    "Line item 'Industrial Pump Unit': invoice price 4410.00 vs contracted 4200.00 — "
    "overcharged by 5.0% ($420.00), exceeds 5% threshold.",
    ["Description fuzzy-matched to SKU-003 'Industrial Pump Unit' at 92% confidence."]
)
lr4 = LineItemResult(invoice_messy.line_items[1], rate_d, 0.88, 85.00, 85.00, 0.0, 0.0, True, None,
    ["SKU 'SKU-004' fuzzy-matched to contracted SKU 'SKU-004' (88% confidence)."])

decision_messy = DecisionResult(
    status="FLAGGED",
    vendor_match_confidence=0.81,
    variance_detected=True,
    line_results=[lr3, lr4],
    flag_reasons=[
        "Vendor not matched in approved list (confidence 81%, method=fuzzy)",
        "Line item 'Industrial Pump Unit': invoice price 4410.00 vs contracted 4200.00 — overcharged by 5.0%, exceeds 5% threshold.",
        "Invoice extraction confidence is low (74%). Manual review of source document recommended.",
        "Extraction warning: Invoice number field appears blank or cut off",
        "Extraction warning: Low print quality on header section — vendor address not extracted",
    ],
    clarifying_questions=[
        'Invoice shows vendor "Globex Supplis Inc" — closest approved vendor is '
        '"Globex Supplies Inc" (81% similarity). Can you confirm these are the same entity?',
        "Invoice #INV is missing. Can you provide the invoice number from the original document?",
    ],
    assumptions=["Description fuzzy-matched to SKU-003 'Industrial Pump Unit' at 92% confidence."],
    total_invoice=10134.60,
    total_contracted=9699.60,
    total_variance_amount=435.00,
)

html = generate_html_report(invoice_messy, vendor_messy, decision_messy, policy)
(out / "invoice2_messy_report.html").write_text(html)

payload = {"status": "FLAGGED", "vendor_match_confidence": 0.81, "variance_detected": True,
           "invoice_number": None, "total_invoice": 10134.60, "total_contracted": 9699.60,
           "total_variance_amount": 435.00,
           "flag_reasons": decision_messy.flag_reasons,
           "clarifying_questions": decision_messy.clarifying_questions}
(out / "invoice2_messy_payload.json").write_text(json.dumps(payload, indent=2))

trail = build_audit_trail("invoice2_messy.jpg", invoice_messy, vendor_messy, decision_messy, [])
(out / "invoice2_messy_audit.json").write_text(trail.to_json())
print("✓ Invoice 2 (messy) generated")


# invoice 3
invoice_edge = InvoiceData(
    vendor_name="TechParts Global LLC",   # not in the approved list lol
    invoice_number="TP-88210",
    invoice_date="2025-03-05",
    due_date="2025-04-05",
    currency="USD",
    line_items=[
        LineItem("Custom Fabrication Part #XR9", 10, 320.00, 3200.00, "XR9-CUSTOM", "each"),
        LineItem("Expedited Shipping Fee",         1, 450.00,  450.00, None,         None),
        LineItem("Unknown Service Bundle",         1, 1200.00,1200.00, "SVC-BUNDLE", None),
    ],
    subtotal=4650.00,   # actual sum = 4850.00
    tax_amount=388.00,
    tax_rate_pct=8.0,
    shipping=0.0,
    total=5238.00,
    notes="Expedited order per verbal agreement with procurement. Net 15.",
    extraction_warnings=["Subtotal on invoice appears to be manually altered (handwritten correction visible)"],
    confidence=0.61,
)

vendor_edge = VendorMatchResult(
    matched=False, confidence=0.31,
    matched_vendor=None,
    match_method="none",
    clarifying_questions=[
        '"TechParts Global LLC" does not match any approved vendor (best match: none at 31%). '
        "Please confirm vendor authorization before proceeding."
    ]
)

lr5 = LineItemResult(invoice_edge.line_items[0], None, 0.0, None, 320.00, None, None, None,
    "Line item 'Custom Fabrication Part #XR9' (SKU: XR9-CUSTOM) could not be matched to any contracted rate.")
lr6 = LineItemResult(invoice_edge.line_items[1], None, 0.0, None, 450.00, None, None, None,
    "Line item 'Expedited Shipping Fee' (SKU: N/A) could not be matched to any contracted rate.")
lr7 = LineItemResult(invoice_edge.line_items[2], None, 0.0, None, 1200.00, None, None, None,
    "Line item 'Unknown Service Bundle' (SKU: SVC-BUNDLE) could not be matched to any contracted rate.")

decision_edge = DecisionResult(
    status="FLAGGED",
    vendor_match_confidence=0.31,
    variance_detected=False,
    line_results=[lr5, lr6, lr7],
    flag_reasons=[
        "Vendor 'TechParts Global LLC' not matched in approved list (confidence 31%, method=none)",
        "Line item 'Custom Fabrication Part #XR9' could not be matched to any contracted rate.",
        "Line item 'Expedited Shipping Fee' could not be matched to any contracted rate.",
        "Line item 'Unknown Service Bundle' could not be matched to any contracted rate.",
        "Invoice subtotal (4650.00) does not match sum of line items (4850.00). Difference: 200.00.",
        "Invoice extraction confidence is low (61%). Manual review recommended.",
        "Extraction warning: Subtotal on invoice appears to be manually altered (handwritten correction visible)",
    ],
    clarifying_questions=[
        '"TechParts Global LLC" is not an approved vendor. Who authorized this purchase?',
        "None of the 3 line items match contracted SKUs. Is this a one-time purchase requiring a new contract?",
        "The invoice subtotal ($4,650) does not match the sum of line items ($4,850). Is there a credit or discount not shown?",
    ],
    assumptions=[],
    total_invoice=5238.00,
    total_contracted=None,
    total_variance_amount=None,
)

html = generate_html_report(invoice_edge, vendor_edge, decision_edge, policy)
(out / "invoice3_edgecase_report.html").write_text(html)

payload = {"status": "FLAGGED", "vendor_match_confidence": 0.31, "variance_detected": False,
           "invoice_number": "TP-88210", "total_invoice": 5238.00, "total_contracted": None,
           "total_variance_amount": None,
           "flag_reasons": decision_edge.flag_reasons,
           "clarifying_questions": decision_edge.clarifying_questions}
(out / "invoice3_edgecase_payload.json").write_text(json.dumps(payload, indent=2))

trail = build_audit_trail("invoice3_edge.pdf", invoice_edge, vendor_edge, decision_edge, [])
(out / "invoice3_edgecase_audit.json").write_text(trail.to_json())
print("✓ Invoice 3 (edge case) generated")

print(f"\nAll outputs → {out.resolve()}")
