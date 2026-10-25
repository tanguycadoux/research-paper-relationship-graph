"""
Client of the public ORCID API: the record of a person (names, works).

Terms (checked on 2026-10-25): public API, free, no key; JSON only when asked
(Accept header). Asked on demand only, from the author page: an article can have
more than 1,000 authors, so ORCID is never asked at import (#59).
"""

from django.conf import settings

from . import http

ORCID_RECORD_URL = "https://pub.orcid.org/v3.0/{orcid}/record"


def fetch_orcid_record(orcid):
    """Return the public record of an ORCID (person and works summary), or None."""
    return http.get_json(
        ORCID_RECORD_URL.format(orcid=orcid),
        headers={"Accept": "application/json"},
        service="ORCID",
        subject=f"ORCID {orcid}",
        contact=settings.CROSSREF_MAILTO,
    )
