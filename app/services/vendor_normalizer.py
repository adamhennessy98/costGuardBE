from __future__ import annotations

import re
from typing import Final

_CANONICAL_NAMES: Final[dict[str, str]] = {
    "amazonwebservices": "amazon web services",
    "aws": "amazon web services",
    "amazonaws": "amazon web services",
    "amazon": "amazon",
    "microsoftazure": "microsoft azure",
    "azure": "microsoft azure",
    "googlecloudplatform": "google cloud platform",
    "gcp": "google cloud platform",
    "googlecloud": "google cloud platform",
}


def normalize_vendor_name(raw: str) -> str:
    """Normalize vendor names to a canonical lowercase form.

    Applies canonical mappings for common aliases and otherwise strips extra
    punctuation/whitespace so "AWS" and "Amazon Web Services" map to the same
    stored value.
    """

    cleaned = (raw or "").strip().lower()
    if not cleaned:
        return ""

    alnum = re.sub(r"[^a-z0-9]", "", cleaned)
    if alnum in _CANONICAL_NAMES:
        return _CANONICAL_NAMES[alnum]

    normalized = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
    return normalized
