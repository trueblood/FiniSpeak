PROCESSING_MODES = {"baseline", "concurrent", "streaming"}


def normalize_processing_mode(value):
    mode = str(value or "baseline").strip().casefold()
    if mode not in PROCESSING_MODES:
        raise ValueError(f"Unsupported processing mode: {mode}")
    return mode


def is_processing_tester(identity):
    # All signed-in users are participating in the current production trial.
    return bool(identity and identity.get("uid"))


def allowed_processing_modes(identity):
    return ["baseline", "concurrent", "streaming"] if is_processing_tester(identity) else ["baseline"]


def authorize_processing_mode(identity, value):
    mode = normalize_processing_mode(value)
    if mode != "baseline" and not is_processing_tester(identity):
        raise PermissionError("Experimental audio processing requires a signed-in user.")
    return mode
