def _parse_feature_flag(value: str | None) -> bool:
    """Parse FEATURE_LABEL_FILTERING env var (case-insensitive).

    Truthy:  true, 1, yes, on
    Falsy:   false, 0, no, off
    Default: true when unset or unrecognised (keeps filtering on).
    """
    if value is None:
        return True
    lower = value.strip().lower()
    if lower in ("true", "1", "yes", "on"):
        return True
    if lower in ("false", "0", "no", "off"):
        return False
    # Fallback to True for backwards-compat / unknown strings
    return True
