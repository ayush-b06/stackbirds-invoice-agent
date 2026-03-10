"""
report_generator.py
Generates a polished, interactive HTML reconciliation report.
"""

from invoice_extractor import InvoiceData
from vendor_matcher import VendorMatchResult
from decision_engine import DecisionResult, LineItemResult
from excel_parser import Policy
import json


def generate_html_report(
    invoice: InvoiceData,
    vendor_result: VendorMatchResult,
    decision: DecisionResult,
    policy: Policy,
) -> str:
    status_color   = "#00e5a0" if decision.status == "APPROVED" else "#ff5c5c"
    status_bg      = "rgba(0,229,160,0.08)" if decision.status == "APPROVED" else "rgba(255,92,92,0.08)"
    status_icon    = "✓" if decision.status == "APPROVED" else "⚑"
    vendor_conf_pct = f"{vendor_result.confidence:.0%}"

    # Line items rows
    rows_html = ""
    for lr in decision.line_results:
        item   = lr.invoice_item
        is_ok  = lr.within_threshold is True or (lr.within_threshold is None and lr.flag_reason is None)
        row_class = "row-ok" if is_ok else "row-flag"
        variance_str = "—"
        variance_class = ""
        if lr.variance_pct is not None:
            sign = "+" if lr.variance_pct >= 0 else ""
            variance_str = f"{sign}{lr.variance_pct:.1%}"
            variance_class = "var-over" if lr.variance_pct > 0.001 else ("var-under" if lr.variance_pct < -0.001 else "var-ok")

        contracted_str = f"${lr.contracted_price:.2f}" if lr.contracted_price is not None else '<span class="na">Unmatched</span>'
        matched_sku = lr.matched_rate.sku if lr.matched_rate else '—'
        assumptions_html = ""
        if lr.assumptions:
            assumptions_html = f'<div class="assumption-tag">⚡ {lr.assumptions[0]}</div>'

        rows_html += f"""
        <tr class="{row_class}">
            <td>
                <div class="item-desc">{item.description}</div>
                <div class="item-sku">{item.sku or '—'} → {matched_sku}</div>
                {assumptions_html}
            </td>
            <td class="num">{item.quantity}</td>
            <td class="num">${item.unit_price:.2f}</td>
            <td class="num">{contracted_str}</td>
            <td class="num">${item.line_total:.2f}</td>
            <td class="num {variance_class}">{variance_str}</td>
            <td class="status-cell">{'<span class="badge-ok">OK</span>' if is_ok else '<span class="badge-flag">FLAG</span>'}</td>
        </tr>"""

    # flag the reasons
    flags_html = ""
    if decision.flag_reasons:
        flags_items = "".join(f'<li>{r}</li>' for r in decision.flag_reasons)
        flags_html = f'<ul class="flag-list">{flags_items}</ul>'

    # clarify questions
    questions_html = ""
    if decision.clarifying_questions:
        q_items = "".join(f'<li>{q}</li>' for q in decision.clarifying_questions)
        questions_html = f"""
        <div class="panel questions-panel">
            <div class="panel-header">Clarifying Questions for Human Review</div>
            <ul class="q-list">{q_items}</ul>
        </div>"""

    # Extraction warnings
    warnings_html = ""
    if invoice.extraction_warnings:
        w_items = "".join(f'<li>{w}</li>' for w in invoice.extraction_warnings)
        warnings_html = f'<div class="warn-box"><strong>Extraction Warnings:</strong><ul>{w_items}</ul></div>'

    total_variance_html = ""
    if decision.total_variance_amount is not None:
        sign = "+" if decision.total_variance_amount >= 0 else ""
        total_variance_html = f'<div class="stat-block"><div class="stat-label">Total Variance</div><div class="stat-value {("stat-neg" if decision.total_variance_amount > 0.01 else "stat-pos")}">{sign}${decision.total_variance_amount:.2f}</div></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invoice Reconciliation — {invoice.vendor_name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d0f14;
    --surface: #151820;
    --surface2: #1c2030;
    --border: rgba(255,255,255,0.07);
    --text: #e8eaf0;
    --muted: #6b7280;
    --accent: #4f8dff;
    --green: #00e5a0;
    --red: #ff5c5c;
    --yellow: #ffc84a;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'IBM Plex Sans', sans-serif;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }}

  /* ─── Scanline overlay ─── */
  body::before {{
    content: '';
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0,0,0,0.03) 2px,
      rgba(0,0,0,0.03) 4px
    );
    pointer-events: none;
    z-index: 1000;
  }}

  .container {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 40px 24px 80px;
  }}

  /* ─── Header ─── */
  .header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 40px;
    padding-bottom: 32px;
    border-bottom: 1px solid var(--border);
    animation: fadeSlide 0.5s ease both;
  }}

  .header-left .label {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.18em;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 6px;
  }}

  .header-left h1 {{
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.02em;
  }}

  .header-left .meta {{
    font-size: 12px;
    color: var(--muted);
    margin-top: 4px;
    font-family: var(--mono);
  }}

  .status-badge {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
  }}

  .status-pill {{
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.12em;
    padding: 8px 20px;
    border-radius: 4px;
    border: 1.5px solid {status_color};
    color: {status_color};
    background: {status_bg};
    animation: pulse 2s ease infinite;
  }}

  @keyframes pulse {{
    0%, 100% {{ box-shadow: 0 0 0 0 {status_color}40; }}
    50% {{ box-shadow: 0 0 0 8px {status_color}00; }}
  }}

  .conf-tag {{
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.1em;
  }}

  /* ─── Stats bar ─── */
  .stats-row {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin-bottom: 32px;
    animation: fadeSlide 0.5s ease 0.1s both;
  }}

  .stat-block {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 16px 18px;
    transition: border-color 0.2s;
  }}
  .stat-block:hover {{ border-color: rgba(79,141,255,0.3); }}

  .stat-label {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 4px;
  }}

  .stat-value {{
    font-family: var(--mono);
    font-size: 20px;
    font-weight: 600;
    color: var(--text);
  }}
  .stat-pos {{ color: var(--green); }}
  .stat-neg {{ color: var(--red); }}
  .stat-warn {{ color: var(--yellow); }}

  /* ─── Panel ─── */
  .panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 20px;
    overflow: hidden;
    animation: fadeSlide 0.5s ease 0.2s both;
  }}

  .panel-header {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 12px 18px;
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    user-select: none;
    transition: background 0.2s;
  }}
  .panel-header:hover {{ background: rgba(255,255,255,0.03); }}
  .panel-header .toggle {{ margin-left: auto; font-size: 12px; transition: transform 0.3s; }}
  .panel.collapsed .panel-header .toggle {{ transform: rotate(-90deg); }}
  .panel.collapsed .panel-body {{ display: none; }}

  .panel-body {{ padding: 18px; }}

  /* ─── Table ─── */
  .table-wrap {{
    overflow-x: auto;
    border-radius: 6px;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 12px;
  }}

  thead tr {{
    background: var(--surface2);
  }}

  th {{
    font-size: 9px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  th.num {{ text-align: right; }}

  td {{
    padding: 12px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  td.num {{ text-align: right; }}

  tr:last-child td {{ border-bottom: none; }}

  .row-ok {{ background: transparent; }}
  .row-flag {{ background: rgba(255,92,92,0.04); }}
  .row-flag:hover {{ background: rgba(255,92,92,0.07); }}
  .row-ok:hover {{ background: rgba(255,255,255,0.02); }}

  .item-desc {{ color: var(--text); margin-bottom: 2px; }}
  .item-sku {{ font-size: 10px; color: var(--muted); }}

  .var-ok {{ color: var(--green); }}
  .var-over {{ color: var(--red); }}
  .var-under {{ color: var(--yellow); }}
  .na {{ color: var(--muted); font-style: italic; }}

  .badge-ok {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 9px;
    letter-spacing: 0.1em;
    font-weight: 600;
    background: rgba(0,229,160,0.1);
    color: var(--green);
    border: 1px solid rgba(0,229,160,0.3);
  }}
  .badge-flag {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 9px;
    letter-spacing: 0.1em;
    font-weight: 600;
    background: rgba(255,92,92,0.1);
    color: var(--red);
    border: 1px solid rgba(255,92,92,0.3);
  }}

  .assumption-tag {{
    font-size: 10px;
    color: var(--yellow);
    margin-top: 4px;
    opacity: 0.8;
  }}

  /* ─── Flag panel ─── */
  .flag-panel {{ border-color: rgba(255,92,92,0.25); }}
  .flag-panel .panel-header {{ color: var(--red); }}

  .flag-list {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .flag-list li {{
    font-size: 13px;
    padding: 10px 14px;
    border-radius: 5px;
    background: rgba(255,92,92,0.06);
    border-left: 2px solid var(--red);
    color: #ffaaaa;
  }}

  /* ─── Questions panel ─── */
  .questions-panel {{ border-color: rgba(255,200,74,0.25); }}
  .questions-panel .panel-header {{ color: var(--yellow); }}

  .q-list {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .q-list li {{
    font-size: 13px;
    padding: 10px 14px;
    border-radius: 5px;
    background: rgba(255,200,74,0.06);
    border-left: 2px solid var(--yellow);
    color: #ffe8a0;
  }}

  /* ─── Warn box ─── */
  .warn-box {{
    padding: 12px 16px;
    background: rgba(255,200,74,0.05);
    border: 1px solid rgba(255,200,74,0.2);
    border-radius: 6px;
    margin-bottom: 20px;
    font-size: 12px;
    color: #ffe8a0;
  }}
  .warn-box ul {{ margin-top: 6px; padding-left: 18px; }}

  /* ─── Invoice meta grid ─── */
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 10px;
  }}
  .meta-item {{ display: flex; flex-direction: column; gap: 2px; }}
  .meta-item .k {{
    font-family: var(--mono);
    font-size: 9px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
  }}
  .meta-item .v {{
    font-family: var(--mono);
    font-size: 13px;
    color: var(--text);
  }}

  /* ─── Footer ─── */
  .footer {{
    margin-top: 48px;
    padding-top: 20px;
    border-top: 1px solid var(--border);
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
  }}

  /* ─── Animations ─── */
  @keyframes fadeSlide {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  .panel {{ animation: fadeSlide 0.4s ease both; }}
  .panel:nth-child(1) {{ animation-delay: 0.05s; }}
  .panel:nth-child(2) {{ animation-delay: 0.10s; }}
  .panel:nth-child(3) {{ animation-delay: 0.15s; }}
  .panel:nth-child(4) {{ animation-delay: 0.20s; }}

  /* confidence meter */
  .conf-bar-wrap {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 4px;
  }}
  .conf-bar-bg {{
    flex: 1;
    height: 4px;
    background: rgba(255,255,255,0.07);
    border-radius: 2px;
    overflow: hidden;
  }}
  .conf-bar-fill {{
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--accent), var(--green));
    transition: width 1s ease;
  }}
  .conf-pct {{ font-family: var(--mono); font-size: 11px; color: var(--muted); min-width: 36px; }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <div class="label">Invoice Reconciliation Report</div>
      <h1>{invoice.vendor_name}</h1>
      <div class="meta">
        #{invoice.invoice_number or 'N/A'} &nbsp;·&nbsp;
        {invoice.invoice_date or 'Date N/A'} &nbsp;·&nbsp;
        {invoice.currency} {invoice.total:.2f}
      </div>
    </div>
    <div class="status-badge">
      <div class="status-pill">{status_icon} {decision.status}</div>
      <div class="conf-tag">vendor conf {vendor_conf_pct}</div>
    </div>
  </div>

  <!-- Stats -->
  <div class="stats-row">
    <div class="stat-block">
      <div class="stat-label">Invoice Total</div>
      <div class="stat-value">${decision.total_invoice:.2f}</div>
    </div>
    <div class="stat-block">
      <div class="stat-label">Contracted Total</div>
      <div class="stat-value">{f"${decision.total_contracted:.2f}" if decision.total_contracted is not None else "—"}</div>
    </div>
    {total_variance_html}
    <div class="stat-block">
      <div class="stat-label">Line Items</div>
      <div class="stat-value">{len(invoice.line_items)}</div>
    </div>
    <div class="stat-block">
      <div class="stat-label">Flags</div>
      <div class="stat-value {'stat-neg' if decision.flag_reasons else 'stat-pos'}">{len(decision.flag_reasons)}</div>
    </div>
    <div class="stat-block">
      <div class="stat-label">Extraction Conf</div>
      <div class="stat-value {'stat-warn' if invoice.confidence < 0.8 else 'stat-pos'}">{invoice.confidence:.0%}</div>
    </div>
  </div>

  {warnings_html}

  <!-- Flags -->
  {'<div class="panel flag-panel"><div class="panel-header" onclick="togglePanel(this)">⚑ Flag Reasons <span class="toggle">▾</span></div><div class="panel-body">' + flags_html + '</div></div>' if decision.flag_reasons else ''}

  {questions_html}

  <!-- Invoice Details -->
  <div class="panel">
    <div class="panel-header" onclick="togglePanel(this)">Invoice Metadata <span class="toggle">▾</span></div>
    <div class="panel-body">
      <div class="meta-grid">
        <div class="meta-item"><div class="k">Vendor</div><div class="v">{invoice.vendor_name}</div></div>
        <div class="meta-item"><div class="k">Vendor Match</div>
          <div class="v">
            {vendor_result.matched_vendor.canonical_name if vendor_result.matched_vendor else 'No match'} ({vendor_result.match_method})
            <div class="conf-bar-wrap">
              <div class="conf-bar-bg"><div class="conf-bar-fill" style="width:{vendor_result.confidence*100:.0f}%"></div></div>
              <span class="conf-pct">{vendor_result.confidence:.0%}</span>
            </div>
          </div>
        </div>
        <div class="meta-item"><div class="k">Invoice #</div><div class="v">{invoice.invoice_number or '—'}</div></div>
        <div class="meta-item"><div class="k">Invoice Date</div><div class="v">{invoice.invoice_date or '—'}</div></div>
        <div class="meta-item"><div class="k">Due Date</div><div class="v">{invoice.due_date or '—'}</div></div>
        <div class="meta-item"><div class="k">Currency</div><div class="v">{invoice.currency}</div></div>
        <div class="meta-item"><div class="k">Tax</div><div class="v">{f"${invoice.tax_amount:.2f}" if invoice.tax_amount else '—'} {f"({invoice.tax_rate_pct:.1f}%)" if invoice.tax_rate_pct else ''}</div></div>
        <div class="meta-item"><div class="k">Shipping</div><div class="v">{f"${invoice.shipping:.2f}" if invoice.shipping else '—'}</div></div>
        <div class="meta-item"><div class="k">Variance Threshold</div><div class="v">{policy.variance_threshold_pct:.0%}</div></div>
      </div>
    </div>
  </div>

  <!-- Line Items -->
  <div class="panel">
    <div class="panel-header" onclick="togglePanel(this)">Line Item Comparison <span class="toggle">▾</span></div>
    <div class="panel-body" style="padding: 0;">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Description / SKU</th>
              <th class="num">Qty</th>
              <th class="num">Invoice Price</th>
              <th class="num">Contracted</th>
              <th class="num">Line Total</th>
              <th class="num">Variance</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Notes -->
  {'<div class="panel"><div class="panel-header" onclick="togglePanel(this)">Invoice Notes <span class="toggle">▾</span></div><div class="panel-body"><p style="font-size:13px;color:#aaa;">' + (invoice.notes or '') + '</p></div></div>' if invoice.notes else ''}

  <div class="footer">
    <span>Stackbirds Invoice Agent</span>
    <span>Safety over automation — flag early, review carefully</span>
  </div>

</div>

<script>
  function togglePanel(header) {{
    header.closest('.panel').classList.toggle('collapsed');
  }}

  // Animate conf bars on load
  document.addEventListener('DOMContentLoaded', () => {{
    document.querySelectorAll('.conf-bar-fill').forEach(bar => {{
      const w = bar.style.width;
      bar.style.width = '0%';
      setTimeout(() => bar.style.width = w, 100);
    }});
  }});
</script>
</body>
</html>"""
