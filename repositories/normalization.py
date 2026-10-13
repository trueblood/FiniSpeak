"""Canonical values shared by future repository implementations."""


def normalize_email(value):
    """Match the current browser's trim-and-lower email lookup behavior."""
    return str(value or "").strip().lower()
