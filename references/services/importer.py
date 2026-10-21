from django.db import transaction

from ..models import Publication
from .crossref_api import fetch_crossref_json, fetch_crossref_works
from .external_records import Source, has_metadata, store_record
from .parser import parse_publication


def import_publication(pub, *, with_references=False, force_fetch=False):
    """
    Make sure the publication has its metadata, then parse it. With
    references, the cited publications are imported too, without their own
    references. Return False if the metadata could not be retrieved.
    """
    if not ensure_metadata(pub, force_fetch=force_fetch):
        return False
    with transaction.atomic():
        parse_publication(pub, parse_references=with_references)
    if with_references:
        import_cited_publications(pub)
    return True


def ensure_metadata(pub, force_fetch=False):
    """
    Fetch the metadata of a publication unless some is already stored: stored
    data is never fetched again without an explicit refresh.
    """
    if has_metadata(pub) and not force_fetch:
        return True
    json_data = fetch_crossref_json(pub.doi)
    if not json_data:
        return False
    store_record(pub, Source.CROSSREF, json_data)
    return True


def import_cited_publications(pub):
    """
    Import the cited publications never fetched, with one Crossref request per
    batch of DOIs. A DOI unknown to Crossref is marked as fetched, so that it is
    not requested again by later imports (an explicit action can still retry it).
    """
    targets = {target.doi: target for target in unfetched_cited_publications(pub)}
    if not targets:
        return
    works = fetch_crossref_works(list(targets))
    with transaction.atomic():
        for doi, json_data in works.items():
            store_cited_work(targets[doi], json_data)


def store_cited_work(pub, json_data):
    """Store the answer of Crossref; None (unknown DOI) is stored too."""
    store_record(pub, Source.CROSSREF, json_data)
    if json_data is not None:
        parse_publication(pub, parse_references=False)


def unfetched_cited_publications(pub):
    """Publications cited by pub, with a DOI, that Crossref was never asked about."""
    return (
        Publication.objects.filter(citations__source=pub)
        .exclude(doi="")
        .exclude(external_records__source=Source.CROSSREF)
        .distinct()
    )
