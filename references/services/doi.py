import re

DOI_PREFIX_PATTERN = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_doi(raw):
    """
    Return the canonical form of a DOI: no resolver prefix, no spaces, lowercase.
    """
    if not raw:
        return ""
    doi = DOI_PREFIX_PATTERN.sub("", raw.strip())
    return doi.strip().lower()


def is_valid_doi(doi):
    """
    Check that a normalized DOI looks like '10.<registrant>/<suffix>'.
    """
    return bool(DOI_PATTERN.match(doi))
