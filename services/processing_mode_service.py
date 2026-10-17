PROCESSING_MODES = {"baseline", "concurrent", "streaming"}
PROCESSING_TESTER_EMAIL = "timtrueblood@outlook.com"


def normalize_processing_mode(value):
    mode = str(value or "streaming").strip().casefold()
    if mode not in PROCESSING_MODES:
        raise ValueError(f"Unsupported processing mode: {mode}")
    return mode


def is_processing_tester(identity):
    return str((identity or {}).get("email") or "").strip().casefold() == PROCESSING_TESTER_EMAIL


def allowed_processing_modes(identity):
    return ["baseline", "concurrent", "streaming"] if is_processing_tester(identity) else ["streaming"]


def authorize_processing_mode(identity, value):
    mode = normalize_processing_mode(value)
    # Baseline remains an internal safety fallback if streaming fails, but only
    # the designated tester can select a non-default method in the interface.
    if mode == "concurrent" and not is_processing_tester(identity):
        raise PermissionError("This processing method is restricted to the designated tester.")
    return mode
