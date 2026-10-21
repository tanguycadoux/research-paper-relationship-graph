"""
Information already present in the stored Crossref answer of a publication,
displayed without any new request: venue, citation count, funders, licenses,
subjects and abstract.
"""

import html
import re

from .external_records import Source, records_by_source

JATS_TITLE = re.compile(r"<jats:title>.*?</jats:title>", re.DOTALL)
JATS_PARAGRAPH = re.compile(r"</?jats:p[^>]*>")
TAG = re.compile(r"<[^>]+>")
SPACES = re.compile(r"\s+")
SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([.,;:!?)])")


def crossref_details(pub):
    """Displayable details of the Crossref answer, or None if Crossref does not know pub."""
    message = (records_by_source(pub).get(Source.CROSSREF) or {}).get("message")
    if not message:
        return None
    return {
        "venue": clean_text(next(iter(message.get("container-title", [])), "")),
        "citation_count": message.get("is-referenced-by-count"),
        "subjects": [clean_text(subject) for subject in message.get("subject", [])],
        "funders": [funder_label(funder) for funder in message.get("funder", [])],
        "licenses": list(dict.fromkeys(lic["URL"] for lic in message.get("license", []))),
        "abstract": abstract_paragraphs(message.get("abstract", "")),
    }


def funder_label(funder):
    awards = ", ".join(funder.get("award", []))
    name = clean_text(funder.get("name", ""))
    return f"{name} ({awards})" if awards else name


def abstract_paragraphs(jats):
    """Paragraphs of a JATS abstract as plain text, without its 'Abstract' title."""
    text = JATS_TITLE.sub("", jats)
    return [clean_text(part) for part in JATS_PARAGRAPH.split(text) if clean_text(part)]


def clean_text(text):
    """Remove tags and HTML entities ('&#x201C;'), collapse spaces."""
    text = SPACES.sub(" ", html.unescape(TAG.sub(" ", text))).strip()
    return SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
