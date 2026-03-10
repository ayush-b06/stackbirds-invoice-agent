# Top 5 Risks & Mitigations

---

## 1. LLM Hallucination on Invoice Extraction

**Risk:** Claude misreads or fabricates a dollar amount, line item, or date — especially on low-quality scans, handwritten invoices, or dense layouts.

**Mitigation:**
- The extraction prompt explicitly instructs the model to use `null` for uncertain fields and populate `extraction_warnings`, never invent values.
- `confidence` score gates the pipeline: invoices below 0.80 confidence are automatically flagged for human review regardless of all other checks.
- Invoice subtotal is cross-verified against the sum of extracted line items; any discrepancy > $0.02 triggers a flag and a clarifying question.
- Future hardening: run two extraction passes with slightly different prompts and diff the outputs; large disagreements = flag.

---

## 2. Vendor Name Spoofing / Impersonation

**Risk:** A fraudulent invoice uses a name visually close to an approved vendor (e.g. "Acme Corp." vs "Acme Corp Inc.") and the fuzzy matcher approves it.

**Mitigation:**
- The 90% fuzzy threshold is intentionally conservative. 70–90% similarity always flags with a clarifying question rather than auto-approving.
- The audit trail records the *exact* matched canonical name and confidence, so reviewers can see what was compared.
- The Excel file supports explicit `aliases` — known safe variants — preventing false positives on legitimate name differences.
- Future hardening: require vendor ID or bank account number as secondary signal; flag any invoice whose payment details differ from prior approved invoices for the same vendor.

---

## 3. SKU / Rate Matching Errors

**Risk:** A line item description is ambiguous and fuzzy-matches the wrong contracted SKU, masking a pricing discrepancy.

**Mitigation:**
- Every assumption made during SKU matching is surfaced in both the HTML report and audit trail with its confidence score — reviewers see exactly why a match was made.
- Description-match confidence threshold is 0.75 (deliberately conservative); below that, the line item is flagged as unmatched rather than silently using a wrong rate.
- Variance threshold is pulled directly from the Excel policy sheet — the source of truth — and applied strictly.

---

## 4. Reference Excel Integrity

**Risk:** The Excel file itself is modified maliciously (e.g., a vendor added, a rate changed), or it contains data entry errors that cause legitimate invoices to be rejected or fraudulent ones approved.

**Mitigation:**
- The agent is read-only with respect to the Excel file — it never writes back to it.
- All `parse_warnings` (missing sheets, unexpected formats) are surfaced in the audit trail and HTML report.
- Future hardening: hash the Excel file at parse time and include the hash in every audit log; alert if the hash changes between runs; store the Excel in a version-controlled, access-controlled location (e.g. locked S3 bucket with CloudTrail logging).

---

## 5. Automation Creep / Over-Approval

**Risk:** As the system gains trust, humans stop reviewing FLAGGED invoices carefully, and eventually APPROVED invoices too — eliminating the human safeguard entirely.

**Mitigation:**
- The system is designed with a "safety over automation" default: a single failed check produces FLAGGED regardless of how many checks passed.
- Clarifying questions are always specific and actionable, not generic — making human review fast and meaningful, not a rubber-stamp.
- The audit trail is designed as a legal-grade record: every assumption and uncertainty is explicit and timestamped.
- Future hardening: implement approval rate monitoring (e.g., alert if >95% of invoices auto-approve in a period — that's a signal the thresholds are too loose or data is being manipulated). Require human sign-off on APPROVED invoices above a configurable dollar threshold.
