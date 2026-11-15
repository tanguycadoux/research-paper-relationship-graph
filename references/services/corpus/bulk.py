"""
Bulk actions on the publications checked in « Mon corpus » (#287): tag them, change
their reading status, take them away. Each action works on corpus entries, which
checked_entries gives only when every publication checked is in the user's corpus.
"""

from dataclasses import dataclass

from django.db import transaction

from ...models import UserPublication
from ..imports import fetch_queue
from . import tags
from .entries import change_reading_status, queue_reading_status


class InvalidSelection(ValueError):
    pass


def checked_ids(values):
    """The publication ids checked (the `publication` fields), the invalid ones dropped."""
    return {int(value) for value in values if str(value).isdigit()}


def checked_entries(user, values):
    """
    The corpus entries of the publications checked; InvalidSelection when none is
    checked, or when one of them is not in the user's corpus (another user's, or
    removed in another tab): nothing is done then.
    """
    ids = checked_ids(values)
    if not ids:
        raise InvalidSelection("Cochez au moins une publication.")
    entries = list(
        UserPublication.objects.filter(user=user, publication_id__in=ids).select_related(
            "publication"
        )
    )
    if len(entries) != len(ids):
        raise InvalidSelection(
            "Une publication cochée n'est pas dans votre corpus : rien n'a été fait. "
            "Rechargez la page, puis recommencez."
        )
    return entries


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
        if tags.tag_entry(entry, path).tag is None:
            result.covered += 1
        else:
            result.tagged += 1
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


@transaction.atomic
def remove_entries(user, entries):
    """Take the entries away from the corpus, with their tags and status; return how many."""
    UserPublication.objects.filter(pk__in=[entry.pk for entry in entries]).delete()
    tags.forget_unused_tags(user)
    return len(entries)
