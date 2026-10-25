"""
JACoW proceedings (#160). The code of a paper written in a reference,
« JACoW-IPAC2019-WEPRB007 », gives its DOI at DataCite: 10.18429/JACoW-IPAC2019-WEPRB007
(the form of every paper DOI of JACoW). Written by the authors, the code is linked at
import like a DOI, but only once DataCite knows the DOI and its title matches the
reference: nothing is created otherwise, so a wrong or too old code leaves no empty
publication behind.
"""

import re

from django.db import transaction

from ..models import Publication
from .datacite_api import fetch_datacite_works
from .doi import normalize_doi
from .external_records import Source, store_record
from .metadata_formats import datacite_message
from .parser import parse_publication
from .preprints import similar_titles

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


def link_jacow_references(pub):
    """Link the references of pub to identify that give a JACoW code. Return their number."""
    codes = {}
    for ref in pub.cited_references.filter(target__isnull=True, unidentifiable=False, doi=""):
        if doi := written_jacow_doi(reference_text(ref)):
            codes[ref] = doi
    if not codes:
        return 0
    known = {target.doi: target for target in Publication.objects.with_dois(set(codes.values()))}
    unknown = sorted(set(codes.values()) - known.keys())
    records = fetch_datacite_works(unknown) if unknown else {}
    linked = 0
    for ref, doi in codes.items():
        target = known.get(doi)
        if target is None and matches(records.get(doi), ref):
            target = known[doi] = create_from_datacite(doi, records[doi])
        if target is not None and similar_titles(target.title, reference_text(ref)):
            ref.target = target
            ref.save(update_fields=["target"])
            linked += 1
    return linked


def matches(record, ref):
    """DataCite knows the DOI, under a title that the reference gives."""
    if not record:
        return False
    title = (datacite_message(record).get("title") or [""])[0]
    return similar_titles(title, reference_text(ref))


@transaction.atomic
def create_from_datacite(doi, record):
    pub = Publication.objects.create(doi=doi)
    store_record(pub, Source.DATACITE, record)
    parse_publication(pub, parse_references=False)
    return pub
