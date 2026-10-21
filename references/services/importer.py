from django.utils import timezone

from ..models import Publication
from .crossref_api import fetch_crossref_json
from .parser import parse_publication


def import_publication(pub, *, with_references=False, force_fetch=False):
    """
    Make sure the publication has its Crossref metadata, then parse it. With
    references, the cited publications are imported too, without their own
    references. Return False if the metadata could not be retrieved.
    """
    if not ensure_crossref_json(pub, force_fetch=force_fetch):
        return False
    parse_publication(pub, parse_references=with_references)
    if with_references:
        import_cited_publications(pub)
    return True


def ensure_crossref_json(pub, force_fetch=False):
    """
    Fetch the Crossref JSON of a publication, unless it was already fetched:
    Crossref is never called twice for the same publication without a refresh.
    """
    if pub.crossref_fetched_at and not force_fetch:
        return pub.crossref_json is not None
    json_data = fetch_crossref_json(pub.doi)
    if not json_data:
        return False
    store_crossref_json(pub, json_data)
    return True


def store_crossref_json(pub, json_data):
    pub.crossref_json = json_data
    pub.crossref_fetched_at = timezone.now()
    pub.save(update_fields=["crossref_json", "crossref_fetched_at"])


def import_cited_publications(pub):
    for target in unfetched_cited_publications(pub):
        import_publication(target)


def unfetched_cited_publications(pub):
    """Publications cited by pub, with a DOI, whose Crossref data was never fetched."""
    return (
        Publication.objects.filter(citations__source=pub, crossref_fetched_at__isnull=True)
        .exclude(doi="")
        .distinct()
    )
