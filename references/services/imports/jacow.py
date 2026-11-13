"""
JACoW proceedings (#160). The code of a paper written in a reference,
« JACoW-IPAC2019-WEPRB007 », gives its DOI at DataCite: 10.18429/JACoW-IPAC2019-WEPRB007
(the form of every paper DOI of JACoW). Written by the authors, the code is linked at
import like a DOI, once DataCite confirms it (written_identifiers.py).
"""

import re

from ..identifiers.doi import normalize_doi

JACOW_CODE = re.compile(r"\bJACoW-([A-Za-z]+(?:19|20)\d\d)-([A-Za-z0-9]+)\b", re.IGNORECASE)
JACOW_DOI_PREFIX = "10.18429/jacow-"


def is_jacow(doi):
    """
    A paper of JACoW proceedings. The order of its authors at DataCite may differ from
    the article's, where the primary author comes first (#250): the page says so.
    """
    return doi.lower().startswith(JACOW_DOI_PREFIX)


def written_jacow_doi(text):
    """The DOI of the JACoW code written in a text, or ""."""
    match = JACOW_CODE.search(text or "")
    return normalize_doi(f"10.18429/JACoW-{match.group(1)}-{match.group(2)}") if match else ""


def without_jacow_code(text):
    """The text without its JACoW code, which a title search would not find."""
    return JACOW_CODE.sub("", text).strip(" .,;")


def reference_text(ref):
    """Every text of a reference: Crossref may put the code in any field."""
    return " ".join([ref.unstructured, *(str(value) for value in ref.raw.values())])
