"""
Complementary sources (OpenAlex): queried for every imported DOI, in addition to
Crossref and DataCite, whose data stays the reference for the bibliographic
record. Their answers are stored; they never overwrite anything.
"""

from django.db import transaction

from ...models import ExternalRecord, Publication
from ..sources.external_records import Source, has_record, store_record
from ..sources.openalex_api import (
    fetch_openalex_institutions,
    fetch_openalex_work,
    fetch_openalex_works,
)
from .affiliations import attach_affiliations
from .organizations import missing_ancestor_ids, organizations_for
from .parser import parse_publication


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
                complete_affiliations(targets[doi])


def complete_affiliations(pub):
    """
    Attach the affiliations of pub from its stored OpenAlex work. A publication without
    authors is parsed again first: when its preferred source lists none, it takes those
    of the OpenAlex work (#265). Return True when the affiliations are attached.
    """
    if not pub.authorpublication_set.exists():
        with transaction.atomic():
            parse_publication(pub, parse_references=False)
    return attach_affiliations(pub)


def cited_without_openalex(pub):
    return (
        Publication.objects.filter(citations__source=pub)
        .exclude(doi="")
        .exclude(external_records__source=Source.OPENALEX)
        .distinct()
    )


def complete_ancestors(works, refresh=False):
    """
    Create the ancestor organizations named in the lineages of the institutions
    but unknown yet (one request per batch), so that the parser can link them
    without any network access. With refresh, the known ancestors are requested
    again too, to repair their own ancestors.
    """
    institutions = [
        institution
        for work in works
        for authorship in work.get("authorships", [])
        for institution in authorship.get("institutions", [])
    ]
    missing = missing_ancestor_ids(institutions, include_known=refresh)
    if missing:
        # The institutions of the works too: an ancestor is linked only to known
        # organizations, and the CEA above the DRF may be named in the work only.
        fetched = fetch_openalex_institutions(missing).values()
        organizations_for(institutions + list(fetched))


def complete_existing_publications(fetch_missing=False, refresh_ancestors=False):
    """
    Complete the publications already in the database: attach their affiliations
    (with the hierarchy of their organizations) from the stored OpenAlex works, after
    taking the OpenAlex authors of those whose preferred source lists none (#265).
    Conflicts on the authors that no longer apply are closed. With fetch_missing, the
    publications with a DOI but no OpenAlex answer yet are first requested, one request
    per batch. With refresh_ancestors, the known
    ancestors are requested again. Return a summary of what was done.
    """
    fetched = fetch_missing_openalex() if fetch_missing else 0
    records = ExternalRecord.objects.filter(source=Source.OPENALEX, data__isnull=False)
    records = list(records.select_related("publication"))
    complete_ancestors([record.data for record in records], refresh=refresh_ancestors)
    without_authors = list(
        Publication.objects.filter(
            external_records__source=Source.OPENALEX,
            external_records__data__isnull=False,
            authorpublication__isnull=True,
        ).values_list("pk", flat=True)
    )
    attached = sum(complete_affiliations(record.publication) for record in records)
    with_new_authors = (
        Publication.objects.filter(pk__in=without_authors, authorpublication__isnull=False)
        .distinct()
        .count()
    )
    return {
        "fetched": fetched,
        "with_openalex": len(records),
        "attached": attached,
        "with_new_authors": with_new_authors,
    }


def fetch_missing_openalex():
    targets = {
        pub.doi: pub
        for pub in Publication.objects.exclude(doi="").exclude(
            external_records__source=Source.OPENALEX
        )
    }
    works = fetch_openalex_works(list(targets)) if targets else {}
    with transaction.atomic():
        for doi, work in works.items():
            store_record(targets[doi], Source.OPENALEX, work)
    return len(works)
