"""
Client of the public ORCID API: the record of a person (names, works), and the
names of several people in one search request.

Terms (checked on 2026-10-25): public API, free, no key; JSON only when asked
(Accept header). Asked on demand only, from the author page: an article can have
more than 1,000 authors, so ORCID is never asked at import (#59).
"""

from django.conf import settings

from . import http

ORCID_RECORD_URL = "https://pub.orcid.org/v3.0/{orcid}/record"
ORCID_SEARCH_URL = "https://pub.orcid.org/v3.0/expanded-search/"
# 50 ORCIDs: an URL of about 1,200 characters, answered in half a second (measured
# on 2026-10-25).
BATCH_SIZE = 50


def fetch_orcid_record(orcid):
    """Return the public record of an ORCID (person and works summary), or None."""
    return http.get_json(
        ORCID_RECORD_URL.format(orcid=orcid),
        headers={"Accept": "application/json"},
        service="ORCID",
        subject=f"ORCID {orcid}",
        contact=settings.CROSSREF_MAILTO,
    )


def fetch_orcid_names(orcids):
    """
    Names of several ORCIDs, one search request per batch of BATCH_SIZE (#220).
    Return {orcid: entry or None}: None when ORCID does not know the ORCID (or keeps
    it private). ORCIDs of a batch whose request failed are absent from the result.
    """
    names = {}
    for start in range(0, len(orcids), BATCH_SIZE):
        names.update(_search_batch(orcids[start : start + BATCH_SIZE]))
    return names


def _search_batch(orcids):
    data = http.get_json(
        ORCID_SEARCH_URL,
        params={"q": f"orcid:({' OR '.join(orcids)})", "rows": len(orcids)},
        headers={"Accept": "application/json"},
        service="ORCID",
        subject=f"batch of {len(orcids)} ORCIDs",
        contact=settings.CROSSREF_MAILTO,
    )
    if data is None:
        return {}
    found = {entry["orcid-id"]: entry for entry in data.get("expanded-result") or []}
    return {orcid: found.get(orcid) for orcid in orcids}
