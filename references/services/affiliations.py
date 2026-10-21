"""
Affiliations of the author slots of a publication, from the institutions given by
OpenAlex. OpenAlex only completes: authorships are matched to the slots by position
and published name, and nothing is attached when they disagree.
"""

import logging

from django.db import transaction
from django.db.models import Count, Max, Min, Q

from ..models import AuthorPublication, Organization
from .external_records import Source
from .names import same_person_name

logger = logging.getLogger(__name__)


def attach_affiliations(pub):
    """
    Link the author slots of pub to their OpenAlex institutions. Return False when
    the OpenAlex authors do not match the published ones (nothing is attached).
    """
    record = pub.external_records.filter(source=Source.OPENALEX, data__isnull=False).first()
    if record is None:
        return False
    slots = list(pub.authorpublication_set.order_by("order"))
    authorships = record.data.get("authorships", [])
    if not authorships_match(slots, authorships):
        logger.warning("OpenAlex authors do not match the published ones for %s", pub)
        return False
    link_slots(slots, authorships)
    return True


def authorships_match(slots, authorships):
    """Same number of authors, and the same published name at each position."""
    return len(slots) == len(authorships) and all(
        same_person_name(published_name(slot), authorship.get("raw_author_name") or "")
        for slot, authorship in zip(slots, authorships, strict=True)
    )


def published_name(slot):
    return f"{slot.published_given_name} {slot.published_family_name}"


@transaction.atomic
def link_slots(slots, authorships):
    institutions = [authorship.get("institutions", []) for authorship in authorships]
    organizations = organizations_for([i for group in institutions for i in group])
    links = AuthorPublication.organizations.through
    links.objects.filter(authorpublication__in=slots).delete()
    links.objects.bulk_create(
        links(authorpublication=slot, organization=organizations[openalex_id(institution)])
        for slot, group in zip(slots, institutions, strict=True)
        for institution in {openalex_id(i): i for i in group}.values()
        if openalex_id(institution) in organizations
    )


def organizations_for(institutions):
    """
    {OpenAlex id: Organization} for the institutions, creating the missing ones.
    An organization is recognized by its OpenAlex id or by its ROR (OpenAlex
    sometimes merges institutions under a new id).
    """
    by_id = {openalex_id(i): i for i in institutions if openalex_id(i)}
    rors = {ror_id(i) for i in by_id.values() if ror_id(i)}
    existing = Organization.objects.filter(Q(openalex_id__in=by_id) | Q(ror__in=rors))
    by_oid = {org.openalex_id: org for org in existing}
    by_ror = {org.ror: org for org in existing if org.ror}
    found = {
        oid: by_oid.get(oid) or by_ror.get(ror_id(i))
        for oid, i in by_id.items()
        if oid in by_oid or ror_id(i) in by_ror
    }
    missing = [new_organization(i) for oid, i in by_id.items() if oid not in found]
    Organization.objects.bulk_create(missing)
    return found | {org.openalex_id: org for org in missing}


def new_organization(institution):
    return Organization(
        name=institution.get("display_name") or "",
        ror=ror_id(institution),
        openalex_id=openalex_id(institution),
        country_code=institution.get("country_code") or "",
    )


def ror_id(institution):
    """'https://ror.org/03f0apy98' -> '03f0apy98'."""
    return (institution.get("ror") or "").rsplit("/", 1)[-1]


def openalex_id(institution):
    """'https://openalex.org/I4210141222' -> 'I4210141222'."""
    return (institution.get("id") or "").rsplit("/", 1)[-1]


def organization_periods(author):
    """
    Organizations of an author with their period, computed from the publications:
    first and last publication date, and number of publications.
    """
    return (
        Organization.objects.filter(author_slots__author=author)
        .annotate(
            first_date=Min("author_slots__publication__publication_date"),
            last_date=Max("author_slots__publication__publication_date"),
            publication_count=Count("author_slots__publication", distinct=True),
        )
        .order_by("-last_date")
    )
