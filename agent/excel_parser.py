"""
excel_parser.py
Reads the source-of-truth Excel file containing:
  - Approved vendors (with aliases)
  - Contracted rates by SKU/service
  - Allowed price variance threshold
  - Tax/shipping policy notes
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class VendorRecord:
    canonical_name: str
    aliases: list[str]
    vendor_id: str


@dataclass
class ContractedRate:
    sku: str
    description: str
    unit_price: float
    unit: str


@dataclass
class Policy:
    variance_threshold_pct: float    
    tax_policy: str
    shipping_policy: str
    notes: str


@dataclass
class ExcelData:
    vendors: list[VendorRecord] = field(default_factory=list)
    rates: dict[str, ContractedRate] = field(default_factory=dict)  
    policy: Optional[Policy] = None
    parse_warnings: list[str] = field(default_factory=list)


def parse_excel(path: str) -> ExcelData:
    """
    Parses the reference Excel file. Expected sheet names:
      - "Vendors"    : approved vendor list
      - "Rates"      : contracted rates per SKU
      - "Policy"     : variance threshold + tax/shipping notes

    If sheet names differ, falls back to positional (sheet 0, 1, 2).
    """
    result = ExcelData()

    try:
        xl = pd.ExcelFile(path)
    except Exception as e:
        result.parse_warnings.append(f"Could not open Excel file: {e}")
        return result

    sheet_names = [s.lower() for s in xl.sheet_names]

    # vendors
    vendor_sheet = _find_sheet(xl, sheet_names, ["vendor", "vendors", "approved"], 0)
    if vendor_sheet is not None:
        df = vendor_sheet.fillna("")
        for _, row in df.iterrows():
            canonical = _coerce_str(row, ["vendor_name", "name", "canonical_name", df.columns[0]])
            vendor_id  = _coerce_str(row, ["vendor_id", "id"]) or canonical
            alias_raw  = _coerce_str(row, ["aliases", "alias", "also_known_as"]) or ""
            aliases    = [a.strip() for a in re.split(r"[;,|]", alias_raw) if a.strip()]
            if canonical:
                result.vendors.append(VendorRecord(canonical, aliases, vendor_id))
    else:
        result.parse_warnings.append("No 'Vendors' sheet found in Excel file.")

    # rates
    rate_sheet = _find_sheet(xl, sheet_names, ["rate", "rates", "contracted", "pricing"], 1)
    if rate_sheet is not None:
        df = rate_sheet.fillna("")
        for _, row in df.iterrows():
            sku         = _coerce_str(row, ["sku", "item_code", "code", df.columns[0]])
            description = _coerce_str(row, ["description", "item", "service", "name"])
            unit        = _coerce_str(row, ["unit", "uom", "unit_of_measure"]) or "each"
            price_raw   = _coerce_num(row, ["unit_price", "price", "contracted_price", "rate"])
            if sku and price_raw is not None:
                result.rates[sku.upper()] = ContractedRate(sku, description, price_raw, unit)
    else:
        result.parse_warnings.append("No 'Rates' sheet found in Excel file.")

    # policy
    policy_sheet = _find_sheet(xl, sheet_names, ["policy", "policies", "settings", "config"], 2)
    if policy_sheet is not None:
        df = policy_sheet.fillna("")
        
        kv = _try_kv(df)
        variance_pct = _parse_pct(kv.get("variance_threshold") or kv.get("variance") or "5%")
        result.policy = Policy(
            variance_threshold_pct=variance_pct,
            tax_policy=kv.get("tax_policy", ""),
            shipping_policy=kv.get("shipping_policy", ""),
            notes=kv.get("notes", ""),
        )
    else:
        result.parse_warnings.append("No 'Policy' sheet found; defaulting variance threshold to 5%.")
        result.policy = Policy(0.05, "", "", "Default policy applied.")

    return result



def _find_sheet(xl: pd.ExcelFile, lower_names: list, keywords: list, fallback_idx: int):
    for kw in keywords:
        for i, name in enumerate(lower_names):
            if kw in name:
                return xl.parse(xl.sheet_names[i])
    if fallback_idx < len(xl.sheet_names):
        return xl.parse(xl.sheet_names[fallback_idx])
    return None


def _coerce_str(row, candidates: list) -> str:
    for c in candidates:
        try:
            val = row[c]
            if val and str(val).strip():
                return str(val).strip()
        except (KeyError, TypeError):
            pass
    return ""


def _coerce_num(row, candidates: list) -> Optional[float]:
    for c in candidates:
        try:
            val = row[c]
            if val != "":
                return float(str(val).replace("$", "").replace(",", ""))
        except (KeyError, ValueError, TypeError):
            pass
    return None


def _try_kv(df: pd.DataFrame) -> dict:
    """Try to read a sheet as key-value pairs (first col = key, second col = value)."""
    result = {}
    if df.shape[1] >= 2:
        for _, row in df.iterrows():
            k = str(row.iloc[0]).strip().lower().replace(" ", "_")
            v = str(row.iloc[1]).strip()
            if k and k != "nan":
                result[k] = v
    return result


def _parse_pct(s: str) -> float:
    s = str(s).replace("%", "").strip()
    try:
        v = float(s)
        return v / 100 if v > 1 else v
    except ValueError:
        return 0.05
