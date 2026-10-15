"""Canonical values shared by future repository implementations."""


def normalize_email(value):
    """Match the current browser's trim-and-lower email lookup behavior."""
    return str(value or "").strip().lower()


def normalize_phone(value):
    """Return the canonical digits-only account lookup value."""
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits if 7 <= len(digits) <= 15 else ""
