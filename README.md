# Stackbirds Invoice Processing Agent — Spring 2026

An LLM-powered invoice reconciliation agent that extracts, verifies, and approves or flags invoices against a reference Excel file. Built with safety over automation as the core design principle.

---

## Setup

```bash
git clone https://github.com/ayush-b06/stackbirds-invoice-agent
cd stackbirds-invoice-agent

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

```bash
cd agent

# Process a single invoice
python main.py \
  --invoice ../sample_data/invoice_clean.pdf \
  --excel   ../sample_data/reference.xlsx \
  --out     ../outputs

# Or pass API key directly
python main.py \
  --invoice invoice.jpg \
  --excel   reference.xlsx \
  --api-key sk-ant-...
```

---

## Outputs (per invoice run)

| File | Description |
|------|-------------|
| `{name}_{ts}_payload.json` | Structured decision payload (status, confidence, variance) |
| `{name}_{ts}_report.html`  | Interactive HTML reconciliation report — open in any browser |
| `{name}_{ts}_audit.json`   | Full audit trail with every assumption and decision |

---

## Reference Excel Format

The agent works with the Stackbirds-provided Excel file which has two sheets:

### `Approved Vendors` sheet
| vendor_name |
|-------------|
| Acme Supplies Inc. |
| BrightOffice LLC |

### `Extracted_LineItems_100` sheet
Historical invoice data used to derive contracted rates (median unit price per vendor + item):
| vendor_name | line_item_description | unit_price | ... |
|-------------|----------------------|------------|-----|

Contracted rates are automatically derived from the median historical unit price per vendor/item combination. No manual rate sheet needed.

---

## Decision Logic

**APPROVED** — all of the following must be true:
- Vendor matched in approved list (≥90% confidence)
- All line items matched to contracted rates
- All variances within policy threshold
- Invoice extraction confidence ≥80%
- Invoice subtotal consistent with line items

**FLAGGED** — any single condition fails. The system then:
1. Lists all specific flag reasons
2. Outputs 1–3 clarifying questions for the human reviewer
3. Records all assumptions made in the audit trail

---

## Architecture

See [`architecture.md`](architecture.md) for the one-page architecture explanation.

## Risks

See [`risks.md`](risks.md) for the top 5 risks and mitigations.
