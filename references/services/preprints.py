"""
arXiv preprints replaced by their published version (#227). The authors declare the
DOI of the journal version on arXiv; DataCite gives it as IsVersionOf. The version is
taken only if Crossref knows it as a publication (not posted-content: copies of arXiv
preprints are registered elsewhere under new DOIs) and its title is close enough to
the preprint's, since a typing error in the declared DOI would point to another work.
The publication keeps its corpus entries and citations, and the arXiv DOI in
preprint_doi; if the published version is already in the base, the preprint merges
into it.
"""

import re

from django.db import transaction

from ..models import Author, CitedReference, MetadataConflict, Publication
from .crossref_api import fetch_crossref_json, fetch_crossref_works
from .doi import is_valid_doi, normalize_doi
from .external_records import Source, store_record
from .metadata_formats import datacite_message
from .publication_moves import move_corpus_entries
from .search import normalize

ARXIV_PREFIX = "10.48550/arxiv."
VERSION_RELATIONS = {"IsVersionOf", "IsPreprintOf"}
PUBLISHED_TYPES = {
    "journal-article",
    "proceedings-article",
    "book-chapter",
    "book",
    "edited-book",
    "monograph",
}
# Share of the words of the shorter title found in the other one: a subtitle added or
# a word changed on publication is fine, another work is not.
TITLE_OVERLAP = 0.6


def is_arxiv(doi):
    return doi.lower().startswith(ARXIV_PREFIX)


def arxiv_id(doi):
    """1706.03762 for 10.48550/arXiv.1706.03762."""
    return doi[len(ARXIV_PREFIX) :]


def declared_version(datacite_data):
    """The DOI of the published version that an arXiv record declares, or None."""
    attributes = (datacite_data or {}).get("data", {}).get("attributes", {})
    for related in attributes.get("relatedIdentifiers") or []:
        if related.get("relationType") not in VERSION_RELATIONS:
            continue
        if related.get("relatedIdentifierType") != "DOI":
            continue
        doi = normalize_doi(related.get("relatedIdentifier", ""))
        if is_valid_doi(doi) and not is_arxiv(doi):
            return doi
    return None


def title_words(title):
    return {word for word in re.findall(r"\w+", normalize(title or "")) if len(word) > 2}


def similar_titles(first, second):
    words, other = title_words(first), title_words(second)
    if not words or not other:
        return False
    return len(words & other) / min(len(words), len(other)) >= TITLE_OVERLAP


def is_published_version(preprint_title, crossref_data):
    message = (crossref_data or {}).get("message", {})
    title = (message.get("title") or [""])[0]
    return message.get("type") in PUBLISHED_TYPES and similar_titles(preprint_title, title)


def preprint_title(datacite_data):
    return (datacite_message(datacite_data).get("title") or [""])[0]


def datacite_data(pub):
    record = pub.external_records.filter(source=Source.DATACITE, data__isnull=False).first()
    return record.data if record else None


def published_version(pub):
    """
    The publication that pub becomes: its published version if pub is an arXiv
    preprint that declares one and passes the checks, else pub itself.
    """
    if not is_arxiv(pub.doi):
        return pub
    data = datacite_data(pub)
    doi = declared_version(data)
    if doi is None:
        return pub
    crossref = fetch_crossref_json(doi)
    if not is_published_version(preprint_title(data), crossref):
        return pub
    return replace_preprint(pub, crossref)


def replace_cited_preprints(publications):
    """
    published_version for cited publications imported in batch: one Crossref request
    per batch for the declared versions. Return the publications replaced.
    """
    declared = {}
    for pub in publications:
        doi = declared_version(datacite_data(pub)) if is_arxiv(pub.doi) else None
        if doi:
            declared[pub] = doi
    if not declared:
        return []
    works = fetch_crossref_works(sorted(set(declared.values())))
    replaced = []
    for pub, doi in declared.items():
        crossref = works.get(doi)
        if is_published_version(preprint_title(datacite_data(pub)), crossref):
            replaced.append(replace_preprint(pub, crossref))
    return replaced


@transaction.atomic
def replace_preprint(pub, crossref_data):
    """
    pub takes the DOI of its published version and the Crossref answer about it; what
    was fetched for the preprint is dropped, to be parsed again. Return the publication
    that remains: pub, or the published version already in the base.
    """
    doi = normalize_doi(crossref_data["message"]["DOI"])
    existing = Publication.objects.filter(doi=doi).exclude(pk=pub.pk).first()
    if existing:
        return merge_into_published(pub, existing)
    author_ids = list(pub.authors.values_list("pk", flat=True))
    pub.external_records.all().delete()
    pub.cited_references.all().delete()
    pub.authorpublication_set.all().delete()
    Author.objects.filter(pk__in=author_ids, publications__isnull=True).delete()
    pub.preprint_doi, pub.doi = pub.doi, doi
    pub.save()
    store_record(pub, Source.CROSSREF, crossref_data)
    return pub


def merge_into_published(preprint, published):
    """The published version, already in the base, takes the place of the preprint."""
    CitedReference.objects.filter(target=preprint).update(target=published)
    move_corpus_entries(preprint, published)
    # The decision on a published version proposed for the preprint stays traced.
    preprint.conflicts.filter(kind=MetadataConflict.Kind.PUBLISHED_VERSION).update(
        publication=published
    )
    author_ids = list(preprint.authors.values_list("pk", flat=True))
    arxiv_doi = preprint.doi
    preprint.delete()
    Author.objects.filter(pk__in=author_ids, publications__isnull=True).delete()
    if not published.preprint_doi:
        published.preprint_doi = arxiv_doi
        published.save()
    return published


# What the page of an arXiv preprint says about its bibliography.
BIBLIOGRAPHY_NOT_FETCHED = "not_fetched"
BIBLIOGRAPHY_PDF_ONLY = "pdf"
BIBLIOGRAPHY_NOT_FOUND = "none"
BIBLIOGRAPHY_FOUND = "found"


def arxiv_bibliography(pub):
    """Where the bibliography of an arXiv preprint stands; None for another publication."""
    if not is_arxiv(pub.doi):
        return None
    record = pub.external_records.filter(source=Source.ARXIV, data__isnull=False).first()
    if record is None:
        return BIBLIOGRAPHY_NOT_FETCHED
    if record.data.get("source") == "pdf":
        return BIBLIOGRAPHY_PDF_ONLY
    return BIBLIOGRAPHY_FOUND if record.data.get("entries") else BIBLIOGRAPHY_NOT_FOUND
