from .crossref_api import fetch_crossref_json
from .parser import parse_publication


def import_publication(pub, parse_references=True, force_fetch=False):
    """
    Fetch the Crossref JSON if needed (or if forced), then parse it into the publication.
    """
    if force_fetch or not pub.crossref_json:
        json_data = fetch_crossref_json(pub.doi)
        if json_data:
            pub.crossref_json = json_data
            pub.save(update_fields=["crossref_json"])
        else:
            return

    parse_publication(pub, parse_references=parse_references)
