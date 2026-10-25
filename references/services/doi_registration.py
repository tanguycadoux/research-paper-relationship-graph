"""
Whether a DOI exists, asked to doi.org (/ra/), which answers for every registration
agency. The ACM Digital Library shows 10.5555/… identifiers that are not DOIs: linked
or added, they left empty publications in the base (#240).
"""

from ..models import Publication
from .http import get_json

# DOIs per request: /ra/ takes them separated by commas, in the URL.
BATCH_SIZE = 20


def registered_dois(dois):
    """{doi: True, False, or None when doi.org cannot answer}, BATCH_SIZE per request."""
    answers = {}
    for start in range(0, len(dois), BATCH_SIZE):
        batch = dois[start : start + BATCH_SIZE]
        data = get_json(
            f"https://doi.org/ra/{','.join(batch)}",
            service="doi.org",
            subject=f"{len(batch)} DOI" if len(batch) > 1 else batch[0],
        )
        known = {}
        if isinstance(data, list):
            known = {
                str(item.get("DOI", "")).lower(): "RA" in item
                for item in data
                if isinstance(item, dict)
            }
        answers |= {doi: known.get(doi) for doi in batch}
    return answers


def unregistered_dois(dois):
    """
    The DOIs that doi.org says do not exist, except those a publication of the base
    with metadata carries (no request for them). Unanswered DOIs are accepted.
    """
    dois = list(dict.fromkeys(dois))
    vouched = Publication.objects.with_dois(dois).filter(external_records__data__isnull=False)
    known = {doi for pair in vouched.values_list("doi", "preprint_doi") for doi in pair}
    to_check = [doi for doi in dois if doi not in known]
    return {doi for doi, registered in registered_dois(to_check).items() if registered is False}


def is_unregistered_doi(doi):
    return bool(unregistered_dois([doi]))


ACM_PSEUDO_DOI_PREFIX = "10.5555/"


def unregistered_message(doi):
    message = f"Le DOI {doi} n'est enregistré nulle part (doi.org ne le connaît pas)."
    if doi.startswith(ACM_PSEUDO_DOI_PREFIX):
        message += " Les identifiants 10.5555/… de l'ACM Digital Library ne sont pas des DOI."
    return message
