# Invoice Processing Agent — Architecture

## Overview

A five-stage Python pipeline that processes invoices (PDF or image) against a reference Excel file and produces three outputs: a structured JSON decision payload, a human-readable HTML report, and a JSON audit trail.

---

## Pipeline

```
Invoice File (PDF/image)       Reference Excel
       │                              │
       ▼                              ▼
┌─────────────────┐        ┌──────────────────┐
│ invoice_extractor│        │  excel_parser    │
│ (Claude Vision) │        │ Vendors, Rates,  │
│ → InvoiceData   │        │ Policy           │
└────────┬────────┘        └────────┬─────────┘
         │                          │
         ▼                          │
┌─────────────────┐                 │
│ vendor_matcher  │◄────────────────┘
│ Fuzzy matching  │
│ → VendorResult  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ decision_engine │
│ Line comparison │
│ Variance check  │
│ → DecisionResult│
└────────┬────────┘
         │
         ├──────────────────────────────────────┐
         ▼                                      ▼
┌──────────────────┐                 ┌─────────────────┐
│ report_generator │                 │  audit_logger   │
│ HTML report      │                 │  JSON audit     │
└──────────────────┘                 └─────────────────┘
```

---

## Component Decisions

**Invoice Extraction — `invoice_extractor.py`**
Uses Claude claude-sonnet-4-20250514 via the vision API (PDF or image as base64). A strict schema prompt instructs the model to return only JSON, set `confidence` 0–1, and populate `extraction_warnings` for any ambiguous fields rather than silently hallucinating values.

**Excel Parsing — `excel_parser.py`**
Uses pandas with flexible sheet/column name discovery. Falls back to positional sheet order if expected names aren't found. Missing sheets emit `parse_warnings` (never silent).

**Vendor Matching — `vendor_matcher.py`**
Three-tier matching: (1) exact normalized match, (2) alias match, (3) fuzzy `SequenceMatcher` + token overlap. Thresholds: ≥90% → matched, 70–90% → flagged with clarifying question, <70% → not matched.

**Decision Engine — `decision_engine.py`**
APPROVE only if: vendor matched, all line items have contracted rates, all variances within threshold, extraction confidence ≥80%, invoice subtotal consistent with line items. Any single failure → FLAGGED.

**Explainability**
Every assumption, fuzzy match, and uncertainty is recorded in both the HTML report and audit trail. The system never silently defaults.

---

## Stack
- Python 3.11+, `anthropic` SDK, `pandas`, `openpyxl`, `difflib` (stdlib)
- No external vector databases or complex orchestration frameworks — intentionally simple and auditable
- Output: static HTML report (zero dependencies, opens in any browser)
