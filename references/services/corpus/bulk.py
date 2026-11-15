"""
Bulk actions on the publications checked in « Mon corpus » (#287), and in the
references and « Cité par » of a publication (#408): add them to the corpus, tag
them, change their reading status, take them away. The last three work on corpus
entries: in « Mon corpus », checked_entries gives them only when every publication
checked is in the user's corpus; on a publication, where the lists mix publications
in and out of it, those out of it are left aside, and counted.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count, Q

from ...models import CitedReference, Publication, UserPublication
from ..imports import fetch_queue
from . import tags
from .entries import (
    add_entry,
    add_identified,
    change_reading_status,
    queue_identified,
    queue_reading_status,
)


class InvalidSelection(ValueError):
    pass


def checked_ids(values):
    """The publication ids checked (the `publication` fields), the invalid ones dropped."""
    return {int(value) for value in values if str(value).isdigit()}


def listed_on(pub):
    """
    The ids of the publications a publication's page lists with a checkbox: its
    identified references and the publications citing it (#408).
    """
    cited = CitedReference.objects.filter(source=pub, target__isnull=False).values("target")
    citing = CitedReference.objects.filter(target=pub).values("source")
    return set(
        Publication.objects.filter(Q(pk__in=cited) | Q(pk__in=citing)).values_list("pk", flat=True)
    )


@dataclass
class Selection:
    """The corpus entries of the publications checked, and how many checked were left aside."""

    entries: list = field(default_factory=list)
    left_aside: int = 0


def checked_entries(user, values, *, partial=False):
    """
    The corpus entries of the publications checked; InvalidSelection when none is
    checked. In « Mon corpus », also when one of them is not in the user's corpus
    (another user's, or removed in another tab): nothing is done then. With partial
    (a publication's lists, #408), those out of the corpus are left aside, unless all
    of them are. Only the user's own entries are ever returned.
    """
    ids = checked_ids(values)
    if not ids:
        raise InvalidSelection("Cochez au moins une publication.")
    entries = list(
        UserPublication.objects.filter(user=user, publication_id__in=ids).select_related(
            "publication"
        )
    )
    if partial and entries:
        return Selection(entries, left_aside=len(ids) - len(entries))
    if partial:
        raise InvalidSelection(
            "Aucune publication cochée n'est dans votre corpus : rien n'a été fait."
        )
    if len(entries) != len(ids):
        raise InvalidSelection(
            "Une publication cochée n'est pas dans votre corpus : rien n'a été fait. "
            "Rechargez la page, puis recommencez."
        )
    return Selection(entries)


def checked_publications(values):
    """The publications checked; InvalidSelection when none is."""
    ids = checked_ids(values)
    if not ids:
        raise InvalidSelection("Cochez au moins une publication.")
    return list(Publication.objects.filter(pk__in=ids).order_by("pk"))


@dataclass
class BulkTagging:
    """What tagging the entries did: the label added, how many got it, how many were covered."""

    label: str = ""
    tagged: int = 0
    covered: int = 0


@transaction.atomic
def tag_entries(entries, raw):
    """Tag every entry as tags.tag_entry does; InvalidTag for an empty or too long name."""
    path = tags.canonical_path(entries[0].user, raw)
    if not path:
        raise tags.InvalidTag("Écrivez le nom du tag, par exemple « Projet/Groupe/… ».")
    result = BulkTagging(label=tags.label(path))
    for entry in entries:
        count_tagging(result, entry, path)
    return result


def count_tagging(result, entry, path):
    """Tag the entry with the canonical path, counted in result as tagged or covered."""
    if tags.tag_entry(entry, path).tag is None:
        result.covered += 1
    else:
        result.tagged += 1


@dataclass
class BulkAddition:
    """
    What adding to the corpus did: publications added, already there, their data
    queued or not retrieved; with a tag, what tagging them all did.
    """

    added: int = 0
    already: int = 0
    queued: int = 0
    failed: int = 0
    tagging: BulkTagging | None = None


def add_publications(user, publications, status="", raw_tag=""):
    """
    Add each publication to the corpus as its own « + » button does (corpus_add): a new
    entry with the status, its data retrieved by the queue with a worker (#378), else at
    once (a preprint may give way to its published version, #227). Those already in the
    corpus keep their entry and status. With a tag, every one of them gets it, as
    tag_entries does; InvalidTag for a too long one, before anything is added.
    """
    path = tags.canonical_path(user, raw_tag)
    result = BulkAddition(tagging=BulkTagging(label=tags.label(path)) if path else None)
    queued = fetch_queue.worker_alive()
    known = set(
        UserPublication.objects.filter(user=user, publication__in=publications).values_list(
            "publication_id", flat=True
        )
    )
    for pub in publications:
        entry = add_entry(user, pub, status)
        if path:
            count_tagging(result.tagging, entry, path)
        if pub.pk in known:
            result.already += 1
            continue
        result.added += 1
        if queued:
            result.queued += queue_identified(user, pub, status) is not None
        else:
            result.failed += add_identified(user, pub, status) is None
    return result


@dataclass
class BulkStatus:
    """What changing the status did: entries changed, bibliographies imported, queued, failed."""

    changed: int = 0
    imported: int = 0
    queued: int = 0
    failed: int = 0


def set_status(entries, status):
    """
    Give every entry the status. Leaving « à lire » imports the bibliography (#234): by
    the queue with a worker (#380), else at once, as for a single publication.
    """
    result = BulkStatus(changed=len(entries))
    queued = fetch_queue.worker_alive()
    for entry in entries:
        if queued:
            result.queued += queue_reading_status(entry, status) is not None
            continue
        imported = change_reading_status(entry, status)
        result.imported += bool(imported)
        result.failed += imported is None
    return result


@dataclass
class BulkRemoval:
    """What removing entries lost: entries, distinct tags, reading statuses, notes."""

    removed: int = 0
    tags: int = 0
    statuses: int = 0
    notes: int = 0


@transaction.atomic
def remove_entries(user, entries):
    """Take the entries away from the corpus, with their tags, status and note."""
    removed = UserPublication.objects.filter(pk__in=[entry.pk for entry in entries])
    lost = removed.aggregate(
        tags=Count("tags", distinct=True),
        statuses=Count("pk", filter=~Q(reading_status=""), distinct=True),
        notes=Count("pk", filter=~Q(note=""), distinct=True),
    )
    result = BulkRemoval(removed=len(entries), **lost)
    removed.delete()
    tags.forget_unused_tags(user)
    return result
