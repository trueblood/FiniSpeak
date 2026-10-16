import os


PROCESSING_MODES = {"baseline", "concurrent", "streaming"}


def normalize_processing_mode(value):
    mode = str(value or "baseline").strip().casefold()
    if mode not in PROCESSING_MODES:
        raise ValueError(f"Unsupported processing mode: {mode}")
    return mode


def is_processing_tester(identity):
    allowed = {uid.strip() for uid in os.getenv("FINISPEAK_PROCESSING_TESTER_UIDS", "").split(",") if uid.strip()}
    return bool(identity and identity.get("uid") in allowed)


def allowed_processing_modes(identity):
    return ["baseline", "concurrent", "streaming"] if is_processing_tester(identity) else ["baseline"]


def authorize_processing_mode(identity, value):
    mode = normalize_processing_mode(value)
    if mode != "baseline" and not is_processing_tester(identity):
        raise PermissionError("Experimental audio processing is limited to authorized testers.")
    return mode
