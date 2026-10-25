import re

from .http import get_json

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


def is_registered(doi):
    """
    Whether doi.org knows the DOI, whatever its registration agency: True, False, or
    None when it cannot answer. The ACM shows 10.5555/… identifiers that are not
    DOIs (#240).
    """
    data = get_json(f"https://doi.org/ra/{doi}", service="doi.org", subject=doi)
    if not data or not isinstance(data, list):
        return None
    return "RA" in data[0]
