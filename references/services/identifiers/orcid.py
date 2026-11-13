def normalize_orcid(raw):
    """'https://orcid.org/0000-0002-1825-0097' -> '0000-0002-1825-0097'."""
    return (raw or "").strip().rsplit("/", 1)[-1]
