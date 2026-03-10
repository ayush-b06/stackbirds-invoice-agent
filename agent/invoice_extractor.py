"""
invoice_extractor.py
Uses Claude's vision API to extract structured invoice data from PDF or image files.
Returns a typed InvoiceData object plus extraction confidence metadata.
"""

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
try:
    import anthropic
except ImportError:
    anthropic = None 

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}

EXTRACTION_PROMPT = """
You are a precise invoice data extraction engine. Extract ALL structured data from this invoice.

Return a JSON object with EXACTLY this schema:
{
  "vendor_name": "string — exact name as shown on invoice",
  "vendor_address": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "string ISO format YYYY-MM-DD or null",
  "due_date": "string ISO format YYYY-MM-DD or null",
  "currency": "string e.g. USD",
  "line_items": [
    {
      "sku": "string or null — item code/SKU if present",
      "description": "string — item description",
      "quantity": number,
      "unit_price": number,
      "line_total": number,
      "unit": "string or null"
    }
  ],
  "subtotal": number or null,
  "tax_amount": number or null,
  "tax_rate_pct": number or null,
  "shipping": number or null,
  "total": number,
  "notes": "string or null — any special notes/terms on invoice",
  "extraction_warnings": ["list any fields that were unclear, ambiguous, or estimated"],
  "confidence": number between 0 and 1 — your overall confidence in the extraction
}

Rules:
- If a value is missing or illegible, use null — NEVER fabricate values
- If OCR quality is poor, lower the confidence score and add to extraction_warnings
- If the same item appears to be listed multiple times, note it in warnings
- line_total should equal quantity × unit_price; flag discrepancies in warnings
- Return ONLY the JSON object — no markdown, no explanation
"""


@dataclass
class LineItem:
    description: str
    quantity: float
    unit_price: float
    line_total: float
    sku: Optional[str] = None
    unit: Optional[str] = None


@dataclass
class InvoiceData:
    vendor_name: str
    invoice_number: Optional[str]
    invoice_date: Optional[str]
    due_date: Optional[str]
    currency: str
    line_items: list[LineItem]
    subtotal: Optional[float]
    tax_amount: Optional[float]
    tax_rate_pct: Optional[float]
    shipping: Optional[float]
    total: float
    vendor_address: Optional[str] = None
    notes: Optional[str] = None
    extraction_warnings: list[str] = field(default_factory=list)
    confidence: float = 1.0
    raw_json: dict = field(default_factory=dict)


def extract_invoice(file_path: str, client) -> InvoiceData:
    """
    Extract structured invoice data from a PDF or image file using Claude vision.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

    with open(path, "rb") as f:
        file_bytes = f.read()
    b64_data = base64.standard_b64encode(file_bytes).decode("utf-8")

    media_type = _get_media_type(ext)

    if ext == ".pdf":
        content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64_data,
                }
            },
            {"type": "text", "text": EXTRACTION_PROMPT}
        ]
    else:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                }
            },
            {"type": "text", "text": EXTRACTION_PROMPT}
        ]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )

    raw_text = response.content[0].text.strip()

    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw response:\n{raw_text}")

    return _parse_invoice_json(data)


def _parse_invoice_json(data: dict) -> InvoiceData:
    line_items = []
    for item in data.get("line_items", []):
        line_items.append(LineItem(
            description=item.get("description", "Unknown"),
            quantity=float(item.get("quantity") or 0),
            unit_price=float(item.get("unit_price") or 0),
            line_total=float(item.get("line_total") or 0),
            sku=item.get("sku"),
            unit=item.get("unit"),
        ))

    return InvoiceData(
        vendor_name=data.get("vendor_name", "Unknown Vendor"),
        vendor_address=data.get("vendor_address"),
        invoice_number=data.get("invoice_number"),
        invoice_date=data.get("invoice_date"),
        due_date=data.get("due_date"),
        currency=data.get("currency", "USD"),
        line_items=line_items,
        subtotal=_safe_float(data.get("subtotal")),
        tax_amount=_safe_float(data.get("tax_amount")),
        tax_rate_pct=_safe_float(data.get("tax_rate_pct")),
        shipping=_safe_float(data.get("shipping")),
        total=float(data.get("total") or 0),
        notes=data.get("notes"),
        extraction_warnings=data.get("extraction_warnings", []),
        confidence=float(data.get("confidence", 1.0)),
        raw_json=data,
    )


def _get_media_type(ext: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
