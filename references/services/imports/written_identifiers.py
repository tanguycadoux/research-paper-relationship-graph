"""
Identifiers written by the authors in a reference that gives no DOI: a JACoW code
(#160) or an arXiv identifier (#266). Both name a DOI at DataCite. A reference is
linked at import like a DOI, but only once DataCite knows the DOI and its title matches
the reference: nothing is created otherwise, so a wrong or too old identifier leaves no
empty publication behind. An arXiv preprint linked this way is then replaced by its
published version, when its authors declare one (#227).
"""

from typing import NamedTuple

from django.db import transaction

from ...models import CitedReference, Publication
from ..identifiers.arxiv import written_arxiv_doi
from ..sources.datacite_api import fetch_datacite_works
from ..sources.external_records import Source, store_record
from ..sources.metadata_formats import datacite_message
from .jacow import reference_text, written_jacow_doi
from .parser import parse_publication
from .preprints import replace_cited_preprints, similar_titles

# Tried in order on the text of a reference: a JACoW code is more specific.
EXTRACTORS = (written_jacow_doi, written_arxiv_doi)


class LinkReport(NamedTuple):
    found: int  # references that write an identifier
    linked: int  # linked to their publication
    replaced: int  # preprints replaced by their published version


def written_doi(ref):
    """The DOI of the first identifier written in a reference, or ""."""
    text = reference_text(ref)
    return next((doi for extract in EXTRACTORS if (doi := extract(text))), "")


def references_to_link(publications=None):
    """References to identify that give no DOI, of the given publications or of all."""
    references = CitedReference.objects.filter(target__isnull=True, unidentifiable=False, doi="")
    if publications is not None:
        references = references.filter(source__in=publications)
    return references


def link_written_identifiers(pub):
    """Link the references of pub that write a JACoW code or an arXiv identifier."""
    return link_references(references_to_link([pub]))


def link_references(references):
    """
    Link the references that write an identifier, with one DataCite request per batch
    for the DOIs that the base does not know. Return a LinkReport.
    """
    written = {ref: doi for ref in references if (doi := written_doi(ref))}
    if not written:
        return LinkReport(0, 0, 0)
    known = known_publications(set(written.values()))
    unknown = sorted(set(written.values()) - known.keys())
    records = fetch_datacite_works(unknown) if unknown else {}
    created = []
    linked = 0
    for ref, doi in written.items():
        target = known.get(doi)
        if target is None and matches(records.get(doi), ref):
            target = known[doi] = create_from_datacite(doi, records[doi])
            created.append(target)
        if target is not None and similar_titles(target.title, reference_text(ref)):
            ref.target = target
            ref.save(update_fields=["target"])
            linked += 1
    return LinkReport(len(written), linked, len(replace_preprints(created)))


def known_publications(dois):
    """{doi: Publication} of the base, also under the DOI of a replaced preprint (#227)."""
    known = {}
    for pub in Publication.objects.with_dois(dois):
        known[pub.doi] = pub
        if pub.preprint_doi:
            known[pub.preprint_doi] = pub
    return known


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


def replace_preprints(created):
    """The arXiv preprints just created become their declared published version (#227)."""
    replaced = replace_cited_preprints(created)
    for published in replaced:
        with transaction.atomic():
            parse_publication(published, parse_references=False)
    return replaced
