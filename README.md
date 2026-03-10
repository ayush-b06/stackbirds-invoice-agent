# Stackbirds Invoice Processing Agent — Spring 2026

An LLM-powered invoice reconciliation agent that extracts, verifies, and approves or flags invoices against a reference Excel file. Built with safety over automation as the core design principle.

---

## Setup

```bash
git clone <your-repo>
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

The Excel file should have three sheets:

### `Vendors` sheet
| vendor_name | vendor_id | aliases |
|-------------|-----------|---------|
| Acme Corp | V001 | Acme; Acme Corporation |

### `Rates` sheet
| sku | description | unit_price | unit |
|-----|-------------|------------|------|
| SKU-001 | Widget Type A | 12.50 | each |

### `Policy` sheet (key-value format)
| key | value |
|-----|-------|
| variance_threshold | 5% |
| tax_policy | Tax exempt on services |
| shipping_policy | Shipping included in unit price |

The agent does flexible sheet/column name matching — exact names not required.

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
