"""
Affiliations of the author slots of a publication, from the institutions given by
OpenAlex. OpenAlex only completes: authorships are matched to the slots by position
and published name, and nothing is attached when they disagree. OpenAlex lists at
most 100 authors of a work: beyond, the first 100 are compared and attached (#265).
"""

import logging

from django.db import transaction

from ...models import AuthorPublication
from ..corrections.conflicts import Kind, close_obsolete, names_summary, report_conflict
from ..identifiers.names import same_person_name
from ..sources.external_records import Source
from .orcid_completion import complete_orcids
from .organizations import openalex_id, organizations_for

logger = logging.getLogger(__name__)

# OpenAlex never lists more authors for a work (#265).
OPENALEX_MAX_AUTHORS = 100


def attach_affiliations(pub):
    """
    Link the author slots of pub to their OpenAlex institutions, and complete the
    missing ORCIDs of their authors. Return False when the OpenAlex authors do not
    match the published ones (nothing is attached).
    """
    record = pub.external_records.filter(source=Source.OPENALEX, data__isnull=False).first()
    if record is None:
        return False
    slots = list(pub.authorpublication_set.order_by("order"))
    authorships = record.data.get("authorships", [])
    if not slots or not authorships:
        # An empty list contradicts nothing (#265): there is just nothing to attach.
        close_obsolete(Kind.AUTHORS_MISMATCH, publication=pub)
        return False
    slots = compared_slots(slots, authorships)
    if not authorships_match(slots, authorships):
        logger.warning("OpenAlex authors do not match the published ones for %s", pub)
        report_authors_mismatch(pub, slots, authorships)
        return False
    close_obsolete(Kind.AUTHORS_MISMATCH, publication=pub)
    link_slots(slots, authorships)
    complete_orcids(slots, authorships)
    return True


def compared_slots(slots, authorships):
    """
    The slots to compare with the OpenAlex authorships: all of them, or only the first
    100 when OpenAlex gives exactly 100 for a longer list, which it truncated (#265).
    """
    if len(authorships) == OPENALEX_MAX_AUTHORS and len(slots) > OPENALEX_MAX_AUTHORS:
        return slots[:OPENALEX_MAX_AUTHORS]
    return slots


def report_authors_mismatch(pub, slots, authorships):
    """Informative conflict: affiliations are not attached for this publication."""
    report_conflict(
        Kind.AUTHORS_MISMATCH,
        publication=pub,
        field="authors",
        current=names_summary([published_name(slot).strip() for slot in slots]),
        proposed=names_summary([a.get("raw_author_name") or "?" for a in authorships]),
        source=Source.OPENALEX,
    )


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
