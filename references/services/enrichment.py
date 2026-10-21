"""
Complementary sources (OpenAlex): queried for every imported DOI, in addition to
Crossref and DataCite, whose data stays the reference for the bibliographic
record. Their answers are stored; they never overwrite anything.
"""

from django.db import transaction

from ..models import Publication
from .affiliations import attach_affiliations
from .external_records import Source, has_record, store_record
from .openalex_api import fetch_openalex_institutions, fetch_openalex_work, fetch_openalex_works
from .organizations import missing_ancestor_ids, organizations_for


def complete_with_openalex(pub, force_fetch=False):
    """
    Store the OpenAlex work of a publication (a free single lookup). An unknown DOI
    or a failure is not stored: a later explicit import may retry it.
    """
    if not pub.doi or (has_record(pub, Source.OPENALEX) and not force_fetch):
        return
    work = fetch_openalex_work(pub.doi)
    if work:
        store_record(pub, Source.OPENALEX, work)
        complete_ancestors([work])


def complete_cited_with_openalex(pub):
    """Store the OpenAlex works of the cited publications, one request per batch."""
    targets = {target.doi: target for target in cited_without_openalex(pub)}
    if not targets:
        return
    works = fetch_openalex_works(list(targets))
    complete_ancestors([work for work in works.values() if work])
    with transaction.atomic():
        for doi, work in works.items():
            store_record(targets[doi], Source.OPENALEX, work)
            if work:
                attach_affiliations(targets[doi])


def cited_without_openalex(pub):
    return (
        Publication.objects.filter(citations__source=pub)
        .exclude(doi="")
        .exclude(external_records__source=Source.OPENALEX)
        .distinct()
    )


def complete_ancestors(works):
    """
    Create the ancestor organizations named in the lineages of the institutions
    but unknown yet (one request per batch), so that the parser can link them
    without any network access.
    """
    institutions = [
        institution
        for work in works
        for authorship in work.get("authorships", [])
        for institution in authorship.get("institutions", [])
    ]
    missing = missing_ancestor_ids(institutions)
    if missing:
        organizations_for(list(fetch_openalex_institutions(missing).values()))
