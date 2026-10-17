"""Text normalisation shared by training AND serving. Owner: P2.

Placeholder only. P2 replaces the body: NFC, lowercase Latin, mask URLs, 4-8 digit codes,
phone-like strings and amounts.
"""
import unicodedata


def normalise(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()
