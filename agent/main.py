"""
main.py
Invoice Processing Agent — Stackbirds Spring 2026

Orchestrates the full pipeline:
  1. Parse reference Excel
  2. Extract invoice via Claude vision
  3. Match vendor
  4. Compare line items / decide
  5. Emit: JSON payload, HTML report, audit trail JSON

Usage:
  python main.py --invoice path/to/invoice.pdf --excel path/to/reference.xlsx
  python main.py --invoice invoice.jpg --excel vendors.xlsx --out ./outputs
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

import anthropic

# Local imports
from excel_parser import parse_excel
from invoice_extractor import extract_invoice
from vendor_matcher import match_vendor
from decision_engine import run_decision
from audit_logger import build_audit_trail
from report_generator import generate_html_report


def main():
    parser = argparse.ArgumentParser(description="Stackbirds Invoice Processing Agent")
    parser.add_argument("--invoice", required=True, help="Path to invoice file (PDF/image)")
    parser.add_argument("--excel",   required=True, help="Path to reference Excel file")
    parser.add_argument("--out",     default="./outputs", help="Output directory")
    parser.add_argument("--api-key", default=None, help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    # ── Setup ────────────────────────────────────────────────────────────────
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: Set ANTHROPIC_API_KEY env var or pass --api-key", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    invoice_name = Path(args.invoice).stem
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix       = out_dir / f"{invoice_name}_{timestamp}"

    print(f"\n{'='*60}")
    print(f"  Stackbirds Invoice Agent")
    print(f"  Invoice : {args.invoice}")
    print(f"  Excel   : {args.excel}")
    print(f"{'='*60}\n")

    # ── Step 1: Load Excel ────────────────────────────────────────────────────
    print("[1/5] Loading reference Excel...")
    excel_data = parse_excel(args.excel)
    if excel_data.parse_warnings:
        for w in excel_data.parse_warnings:
            print(f"  ⚠  {w}")
    print(f"  ✓  {len(excel_data.vendors)} vendors | {len(excel_data.rates)} rates")
    print(f"  ✓  Variance threshold: {excel_data.policy.variance_threshold_pct:.0%}")

    # ── Step 2: Extract invoice ───────────────────────────────────────────────
    print("\n[2/5] Extracting invoice via Claude vision...")
    try:
        invoice = extract_invoice(args.invoice, client)
    except Exception as e:
        print(f"  ✗  Extraction failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓  Vendor: {invoice.vendor_name}")
    print(f"  ✓  {len(invoice.line_items)} line items | Total: {invoice.currency} {invoice.total:.2f}")
    print(f"  ✓  Confidence: {invoice.confidence:.0%}")
    if invoice.extraction_warnings:
        for w in invoice.extraction_warnings:
            print(f"  ⚠  {w}")

    # ── Step 3: Vendor match ──────────────────────────────────────────────────
    print("\n[3/5] Matching vendor...")
    vendor_result = match_vendor(invoice.vendor_name, excel_data.vendors)
    status_icon = "✓" if vendor_result.matched else "⚠"
    print(f"  {status_icon}  Matched={vendor_result.matched} | Method={vendor_result.match_method} | "
          f"Confidence={vendor_result.confidence:.0%}")

    # ── Step 4: Decision ──────────────────────────────────────────────────────
    print("\n[4/5] Running decision engine...")
    decision = run_decision(invoice, excel_data.rates, excel_data.policy, vendor_result)
    print(f"  {'✓' if decision.status == 'APPROVED' else '⚠'}  Status: {decision.status}")
    if decision.flag_reasons:
        for r in decision.flag_reasons:
            print(f"  ↳  {r}")

    # ── Step 5: Generate outputs ──────────────────────────────────────────────
    print("\n[5/5] Generating outputs...")

    # A. Structured JSON payload
    payload = {
        "status": decision.status,
        "vendor_match_confidence": round(decision.vendor_match_confidence, 4),
        "variance_detected": decision.variance_detected,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "vendor_name": invoice.vendor_name,
        "total_invoice": decision.total_invoice,
        "total_contracted": decision.total_contracted,
        "total_variance_amount": decision.total_variance_amount,
        "flag_reasons": decision.flag_reasons,
        "clarifying_questions": decision.clarifying_questions,
    }
    payload_path = f"{prefix}_payload.json"
    with open(payload_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  ✓  Decision payload → {payload_path}")

    # B. HTML reconciliation report
    html = generate_html_report(invoice, vendor_result, decision, excel_data.policy)
    report_path = f"{prefix}_report.html"
    with open(report_path, "w") as f:
        f.write(html)
    print(f"  ✓  HTML report       → {report_path}")

    # C. Audit trail
    trail = build_audit_trail(
        args.invoice, invoice, vendor_result, decision, excel_data.parse_warnings
    )
    audit_path = f"{prefix}_audit.json"
    with open(audit_path, "w") as f:
        f.write(trail.to_json())
    print(f"  ✓  Audit trail       → {audit_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  FINAL STATUS: {decision.status}")
    if decision.clarifying_questions:
        print(f"\n  Clarifying questions for human review:")
        for q in decision.clarifying_questions:
            print(f"  • {q}")
    print(f"{'='*60}\n")

    return 0 if decision.status == "APPROVED" else 1


if __name__ == "__main__":
    sys.exit(main())
