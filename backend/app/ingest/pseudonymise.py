"""Pseudonymisation of personal identifiers.

Rule 5 of the project charter: analyst names, usernames and IP addresses must
never reach the database or the UI in raw form. We use a stable salted SHA-256
so the same person maps to the same token across submissions (which detectors
need) while the original value cannot be recovered from the token.
"""
from __future__ import annotations

import hashlib
import re

import pandas as pd

from app.config import PSEUDO_SALT

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Generated usernames look like "first.last"; real extracts usually do too.
USERNAME_RE = re.compile(r"\b[a-z][a-z'\-]{1,20}\.[a-z][a-z'\-]{1,20}\b")


def pseudo(value: object, prefix: str, length: int = 10) -> str:
    """Stable salted token for one identifier."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return f"{prefix}-unknown"
    digest = hashlib.sha256(f"{PSEUDO_SALT}|{prefix}|{str(value).strip().lower()}".encode())
    return f"{prefix}-{digest.hexdigest()[:length]}"


def pseudo_series(series: pd.Series, prefix: str) -> pd.Series:
    """Vectorised pseudonymisation with a per-call cache for repeated values."""
    cache: dict[str, str] = {}

    def _one(v: object) -> str:
        key = "" if v is None else str(v)
        if key not in cache:
            cache[key] = pseudo(v, prefix)
        return cache[key]

    return series.map(_one)


def redact_text(text: object) -> str:
    """Replace IPs and usernames inside free text with stable pseudonyms.

    Artefact *shape* is preserved on purpose: detector D05 has to be able to
    tell a note that cites concrete evidence from one that cites nothing, and
    that must stay true after pseudonymisation.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text)
    s = IPV4_RE.sub(lambda m: pseudo(m.group(0), "ip", 8), s)
    s = USERNAME_RE.sub(lambda m: pseudo(m.group(0), "usr", 8), s)
    return s


def redact_series(series: pd.Series) -> pd.Series:
    cache: dict[str, str] = {}

    def _one(v: object) -> str:
        key = "" if v is None else str(v)
        if key not in cache:
            cache[key] = redact_text(v)
        return cache[key]

    return series.map(_one)


def contains_raw_identifier(text: str) -> bool:
    """True when a string still holds a raw IPv4 or first.last username."""
    if not text:
        return False
    return bool(IPV4_RE.search(text) or USERNAME_RE.search(text))
