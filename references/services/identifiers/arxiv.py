"""
arXiv identifiers, new (1706.03762) or old (hep-th/9901001), and the DOI that DataCite
gives every arXiv paper: 10.48550/arXiv.<identifier>. A version (v5) is ignored: the
DOI names the paper, whatever its version.
"""

import re

from .doi import is_valid_doi, normalize_doi

IDENTIFIER = r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"
VERSION = r"(?:v\d+)?"
# An identifier alone, as an eprint field gives it (#165): « arXiv:1706.03762v5 ».
BARE = re.compile(rf"(?:arXiv\s*:\s*)?{IDENTIFIER}{VERSION}", re.IGNORECASE)
# The link of its abstract page or of its PDF (#267).
LINK = re.compile(
    rf"(?:https?://)?(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/{IDENTIFIER}{VERSION}(?:\.pdf)?/?",
    re.IGNORECASE,
)
# An identifier written in a text by the authors of a bibliography (#227):
# « arXiv:1409.4842 », « arXiv preprint arXiv:1409.4842 », « http://arxiv.org/abs/1409.4842 ».
WRITTEN = re.compile(rf"(?:arXiv\s*:\s*|arxiv\.org/abs/|abs/){IDENTIFIER}", re.IGNORECASE)


def doi_of(identifier):
    """The DOI of an arXiv identifier: 10.48550/arxiv.1706.03762."""
    return normalize_doi(f"10.48550/arXiv.{identifier}")


def bare_arxiv_doi(value):
    """The DOI of a value that is an arXiv identifier and nothing else, or ""."""
    match = BARE.fullmatch((value or "").strip())
    return doi_of(match.group(1)) if match else ""


def arxiv_doi(text):
    """The DOI of an arXiv identifier or link typed by a user, or "" (#267)."""
    text = (text or "").strip()
    match = BARE.fullmatch(text) or LINK.fullmatch(text)
    return doi_of(match.group(1)) if match else ""


def written_arxiv_doi(text):
    """The DOI of the first arXiv identifier written in a text, or ""."""
    match = WRITTEN.search(text or "")
    return doi_of(match.group(1)) if match else ""


def typed_doi(text):
    """
    The DOI typed by a user, written as a DOI (with or without resolver) or as an
    arXiv identifier or link; "" if the text is neither.
    """
    doi = normalize_doi(text or "")
    return doi if is_valid_doi(doi) else arxiv_doi(text)
