"""
Profile of an author from what ORCID answered: the official name and the other
names they declared, from the full record (#59) or else from the grouped search
made at import (#220); and, from the full record only, their works already in the
base where they do not appear. Informative only: nothing is changed in the base.
"""

from django.utils import timezone

from ..models import OrcidRecord, Publication
from .doi import normalize_doi
from .orcid_api import fetch_orcid_record
from .orcid_names import update_holders


def refresh_orcid_record(author):
    """Ask ORCID for the record of the author. Return False if it did not answer."""
    data = fetch_orcid_record(author.orcid)
    if data is None:
        return False
    OrcidRecord.objects.update_or_create(
        orcid=author.orcid, defaults={"data": data, "fetched_at": timezone.now()}
    )
    name = (data.get("person") or {}).get("name")
    update_holders(author.orcid, value(name, "given-names"), value(name, "family-name"))
    return True


def orcid_profile(author):
    """
    The profile of the author from what ORCID answered, or None if never asked.
    Without the full record, the names come from the grouped search and the works
    are unknown (has_works); unknown is True when ORCID does not know the ORCID.
    """
    record = OrcidRecord.objects.filter(orcid=author.orcid).first() if author.orcid else None
    if record is None:
        return None
    if record.data is None:
        return search_profile(record)
    person = record.data.get("person") or {}
    groups = (record.data.get("activities-summary") or {}).get("works", {}).get("group") or []
    in_base = Publication.objects.with_dois({doi for g in groups for doi in group_dois(g)})
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
        "has_works": True,
    }


def search_profile(record):
    """The names given by the grouped search, without the works."""
    entry = record.search_data or {}
    names = f"{entry.get('given-names') or ''} {entry.get('family-names') or ''}"
    return {
        "name": names.strip(),
        "credit_name": entry.get("credit-name") or "",
        "other_names": entry.get("other-name") or [],
        "fetched_at": record.search_fetched_at,
        "has_works": False,
        "unknown": not entry,
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
