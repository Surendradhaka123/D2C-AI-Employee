"""
Hard citation enforcement for the chat layer.

Contract: every number (₹ amounts, percentages, counts) in a Claude response
MUST be followed by a citation tag [src:source:source_id].
Uncited numbers are blocked — they never reach the user.
"""

import re

# Matches number-like data claims: ₹ amounts, percentages, named counts.
_NUMBER_RE = re.compile(
    r"(?:"
    r"₹\s*[\d,]+(?:\.\d+)?"                              # ₹1,200 or ₹32,000/month
    r"|"
    r"\b\d[\d,]*(?:\.\d+)?\s*%"                          # 28% or 3.5%
    r"|"
    r"\b\d[\d,]+\s*(?:orders?|shipments?|records?|campaigns?)"  # 400 orders
    r")",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You are an AI analyst for D2C brands. You have access to tools that query real merchant data.

CITATION CONTRACT (non-negotiable):
- Every number you state — ₹ amounts, percentages, counts, ratios — MUST be immediately followed by a citation tag.
- Citation format: [src:source_name:source_id]  e.g. [src:shopify:5042] or [src:shiprocket:AWB10123]
- When a number comes from an aggregate (e.g. total revenue from 500 orders), cite it as [src:shopify:aggregate:500_orders].
- A number with no citation tag is a hallucination. Do not emit it under any circumstances.
- If you cannot cite a number, do not state it. Say instead: "I don't have grounded data for that."

WRITE OPERATIONS:
- You can annotate orders, flag NDR actions, and record budget recommendations via write tools.
- Write tools modify the local database only — nothing is sent to external systems.

Always use your tools before answering data questions. Never answer from memory or training data.
"""


def find_uncited_numbers(text: str) -> list[str]:
    """Return number-like strings that have no [src:...] within 80 chars after them."""
    violations = []
    for m in _NUMBER_RE.finditer(text):
        context_after = text[m.end():m.end() + 80]
        if "[src:" not in context_after:
            violations.append(m.group())
    return violations


def enforce_citations(text: str) -> tuple[bool, list[str]]:
    """
    Returns (is_clean, list_of_violations).
    is_clean=True means the response has no uncited numbers.
    """
    violations = find_uncited_numbers(text)
    return len(violations) == 0, violations


CITATION_RETRY_PROMPT = """Your previous response contained uncited numbers: {violations}

Every number you state must be followed by [src:source:id] using the IDs from your tool results.
If you cannot trace a number to a specific tool result, remove the claim entirely.
Please revise your response with proper citations for all numbers."""
