"""
Profile of an author from their public ORCID record (#59): the official name, the
other names they declared, and their works already in the base where they do not
appear. Informative only: nothing is changed in the base.
"""

from django.utils import timezone

from ..models import OrcidRecord, Publication
from .doi import normalize_doi
from .orcid_api import fetch_orcid_record


def refresh_orcid_record(author):
    """Ask ORCID for the record of the author. Return False if it did not answer."""
    data = fetch_orcid_record(author.orcid)
    if data is None:
        return False
    OrcidRecord.objects.update_or_create(
        orcid=author.orcid, defaults={"data": data, "fetched_at": timezone.now()}
    )
    return True


def orcid_profile(author):
    """The profile of the author from their stored ORCID record, or None."""
    record = OrcidRecord.objects.filter(orcid=author.orcid).first() if author.orcid else None
    if record is None:
        return None
    person = record.data.get("person") or {}
    groups = (record.data.get("activities-summary") or {}).get("works", {}).get("group") or []
    in_base = Publication.objects.filter(doi__in={doi for g in groups for doi in group_dois(g)})
    return {
        "name": official_name(person),
        "credit_name": value(person.get("name"), "credit-name"),
        "other_names": other_names(person),
        "work_count": len(groups),
        "in_base_count": in_base.count(),
        "without_author": in_base.exclude(pk__in=author.publications.values("pk")).order_by(
            "-publication_date", "title"
        ),
        "fetched_at": record.fetched_at,
    }


def official_name(person):
    name = person.get("name")
    return f"{value(name, 'given-names')} {value(name, 'family-name')}".strip()


def other_names(person):
    names = (person.get("other-names") or {}).get("other-name") or []
    return [n["content"] for n in sorted(names, key=lambda n: n.get("display-index", 0))]


def group_dois(group):
    """DOIs of a work (a group gathers the versions of a work from several sources)."""
    ids = (group.get("external-ids") or {}).get("external-id") or []
    dois = [
        normalize_doi(i.get("external-id-value") or "")
        for i in ids
        if i.get("external-id-type") == "doi" and i.get("external-id-relationship") == "self"
    ]
    return [doi for doi in dois if doi]  # never "": the books have no DOI


def value(field, key):
    """{'given-names': {'value': 'Josiah'}} -> 'Josiah' (fields are often null)."""
    return ((field or {}).get(key) or {}).get("value") or ""
