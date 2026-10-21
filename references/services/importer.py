from django.utils import timezone

from .crossref_api import fetch_crossref_json
from .parser import parse_publication


def import_publication(pub, parse_references=True, force_fetch=False):
    """
    Fetch the Crossref JSON if it was never fetched (or if forced), then parse it
    into the publication.
    """
    if force_fetch or pub.crossref_fetched_at is None:
        json_data = fetch_crossref_json(pub.doi)
        if not json_data:
            return
        pub.crossref_json = json_data
        pub.crossref_fetched_at = timezone.now()
        pub.save(update_fields=["crossref_json", "crossref_fetched_at"])

    parse_publication(pub, parse_references=parse_references)
