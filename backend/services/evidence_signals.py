"""
evidence_signals.py

Lightweight keyword/rule-based fallback detectors for evidence signals that
the LLM extraction schema may not capture (or couldn't, if parsing failed):
signature/delivery confirmation, and merchant policy compliance.

These are used in the resolve pipeline's feature-vector construction as a
fallback whenever the LLM's explicit extracted field is missing (None) --
if the LLM did return an explicit True/False, that's used directly and
these functions aren't consulted for that piece of evidence.

Negative phrasing is checked first and wins over a bare positive keyword
match, so text like "no signature on file" is correctly read as False
rather than matching on the word "signature" alone.
"""

import re

_SIGNATURE_NEGATIVE_PATTERNS = [
    r"no signature",
    r"without (?:a )?signature",
    r"signature (?:was |is )?not (?:on file|obtained|provided|required|available)",
    r"no sig(?:nature)? on file",
    r"lack(?:ing|s)? (?:a |any )?signature",
    r"unsigned",
]

_SIGNATURE_POSITIVE_PATTERNS = [
    r"signature (?:on file|confirmed|obtained|captured|provided|available)",
    r"signed for(?: by| the)?",
    r"recipient signed",
    r"delivered with signature",
    r"proof of delivery(?: with| includes| shows)? signature",
    r"signature confirmation",
]

_COMPLIANCE_NEGATIVE_PATTERNS = [
    r"(?:did not|didn't|failed to)(?:\s+\w+){0,2}\s+(?:comply|follow|meet)",
    r"not in compliance",
    r"policy violation",
    r"violat(?:ed|es|ing)(?:\s+\w+){0,2}\s+policy",
    r"out of compliance",
    r"non[- ]compliant",
]

_COMPLIANCE_POSITIVE_PATTERNS = [
    r"complie[sd]? with(?:\s+\w+){0,3}\s+policy",
    r"policy[- ]compliant",
    r"in compliance with",
    r"follow(?:ed|s)(?:\s+\w+){0,3}\s+policy",
    r"within policy",
    r"adher(?:ed|es|ence) to(?:\s+\w+){0,2}\s+policy",
    r"met (?:all )?policy requirements",
]


def _matches_any(patterns, text_lower: str) -> bool:
    return any(re.search(p, text_lower) for p in patterns)


def detect_signature_confirmation(text: str) -> bool:
    """
    Best-effort keyword detection of whether a signature/delivery
    confirmation was on file, from free text. Negative phrasing (e.g. "no
    signature on file") takes priority over a bare mention of the word
    "signature". Returns False if no clear signal either way.
    """
    if not text:
        return False
    text_lower = text.lower()

    if _matches_any(_SIGNATURE_NEGATIVE_PATTERNS, text_lower):
        return False
    if _matches_any(_SIGNATURE_POSITIVE_PATTERNS, text_lower):
        return True
    return False


def detect_policy_compliance(text: str) -> bool:
    """
    Best-effort keyword detection of whether merchant-submitted evidence
    indicates the merchant complied with its own return/refund policy.
    Returns False if no clear signal either way.
    """
    if not text:
        return False
    text_lower = text.lower()

    if _matches_any(_COMPLIANCE_NEGATIVE_PATTERNS, text_lower):
        return False
    if _matches_any(_COMPLIANCE_POSITIVE_PATTERNS, text_lower):
        return True
    return False


if __name__ == "__main__":
    tests = [
        ("Package marked delivered. No signature on file.", detect_signature_confirmation, False),
        ("Recipient signed for the package at the front desk.", detect_signature_confirmation, True),
        ("Delivered with signature confirmation attached.", detect_signature_confirmation, True),
        ("Package left at door, unsigned.", detect_signature_confirmation, False),
        ("We complied with our stated return policy in full.", detect_policy_compliance, True),
        ("Merchant failed to follow the refund policy on this order.", detect_policy_compliance, False),
        ("No mention of policy at all here.", detect_policy_compliance, False),
    ]
    for text, fn, expected in tests:
        result = fn(text)
        status = "OK" if result == expected else "MISMATCH"
        print(f"[{status}] {fn.__name__}({text!r}) = {result} (expected {expected})")
