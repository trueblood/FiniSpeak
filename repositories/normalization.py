"""Canonical values shared by future repository implementations."""


def normalize_email(value):
    """Match the current browser's trim-and-lower email lookup behavior."""
    return str(value or "").strip().lower()


def normalize_phone(value):
    """Return the digits-only lookup key for a valid international number."""
    canonical = canonicalize_phone(value)
    return canonical[1:] if canonical else ""


def canonicalize_phone(value, default_calling_code="1"):
    """Return E.164-style storage, assuming the configured code for legacy local numbers."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = "".join(character for character in raw if character.isdigit())
    calling_code = str(default_calling_code or "").lstrip("+")
    if raw.startswith("+"):
        candidate = digits
    elif calling_code and len(digits) == 10:
        candidate = f"{calling_code}{digits}"
    elif calling_code and digits.startswith(calling_code) and len(digits) == 11:
        candidate = digits
    else:
        candidate = digits
    if not 8 <= len(candidate) <= 15 or candidate.startswith("0"):
        return ""
    return f"+{candidate}"
