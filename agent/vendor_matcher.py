"""
vendor_matcher.py
Fuzzy-matches an extracted vendor name against the approved vendor list.
Uses multiple similarity signals to produce a confidence score.
"""

import re
import difflib
from dataclasses import dataclass
from typing import Optional
from excel_parser import VendorRecord


@dataclass
class VendorMatchResult:
    matched: bool
    confidence: float                     # 0.0 – 1.0
    matched_vendor: Optional[VendorRecord]
    match_method: str                     # "exact", "alias", "fuzzy", "none"
    clarifying_questions: list[str]


FUZZY_AUTO_APPROVE_THRESHOLD  = 0.90   # ≥ this → matched
FUZZY_FLAG_THRESHOLD          = 0.70   # between 0.70–0.90 → flagged with question
                                        # < 0.70 → not matched


def match_vendor(extracted_name: str, vendors: list[VendorRecord]) -> VendorMatchResult:
    """
    Try to match `extracted_name` against the approved vendor list.
    Attempts in order: exact → alias → fuzzy.
    """
    normalized = _normalize(extracted_name)
    questions = []

    if not vendors:
        return VendorMatchResult(
            matched=False,
            confidence=0.0,
            matched_vendor=None,
            match_method="none",
            clarifying_questions=["No approved vendor list was loaded — cannot verify vendor."],
        )

    # 1. Exact match (case/punctuation insensitive)
    for vendor in vendors:
        if _normalize(vendor.canonical_name) == normalized:
            return VendorMatchResult(True, 1.0, vendor, "exact", [])

    # 2. Alias match
    for vendor in vendors:
        for alias in vendor.aliases:
            if _normalize(alias) == normalized:
                return VendorMatchResult(True, 0.97, vendor, "alias", [])

    # 3. Fuzzy match across canonical names + aliases
    best_score = 0.0
    best_vendor = None

    for vendor in vendors:
        candidates = [vendor.canonical_name] + vendor.aliases
        for c in candidates:
            score = _similarity(normalized, _normalize(c))
            if score > best_score:
                best_score = score
                best_vendor = vendor

    if best_score >= FUZZY_AUTO_APPROVE_THRESHOLD:
        return VendorMatchResult(True, best_score, best_vendor, "fuzzy", [])

    if best_score >= FUZZY_FLAG_THRESHOLD:
        questions.append(
            f'Invoice shows vendor "{extracted_name}" — closest approved vendor is '
            f'"{best_vendor.canonical_name}" (similarity {best_score:.0%}). '
            f"Can you confirm these are the same entity?"
        )
        return VendorMatchResult(False, best_score, best_vendor, "fuzzy", questions)

    questions.append(
        f'Vendor "{extracted_name}" does not match any approved vendor '
        f"(best match: {best_vendor.canonical_name if best_vendor else 'none'} at "
        f"{best_score:.0%}). Please confirm vendor authorization."
    )
    return VendorMatchResult(False, best_score, best_vendor, "none", questions)


def _normalize(s: str) -> str:
    """Lowercase, remove punctuation/extra whitespace, expand common abbreviations."""
    s = s.lower()
    s = re.sub(r"[.,\-_&']", " ", s)
    s = re.sub(r"\b(inc|llc|ltd|corp|co|company|incorporated|limited)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _similarity(a: str, b: str) -> float:
    """Combined similarity: SequenceMatcher + token-overlap bonus."""
    seq_score = difflib.SequenceMatcher(None, a, b).ratio()

    # Token overlap bonus
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if a_tokens and b_tokens:
        overlap = len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))
        return 0.7 * seq_score + 0.3 * overlap

    return seq_score
