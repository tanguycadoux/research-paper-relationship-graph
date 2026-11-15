"""
The figures of the home page (#151): a constant number of queries, whatever the size
of the base or of the corpus.
"""

from django.db.models import Count, Max

from ...models import Author, CitedReference, Publication, UserPublication
from . import pending

LATEST_COUNT = 5


def base_figures():
    """
    The size of the base, and the publications added last to a corpus (#278): those that
    entered the base as cited references, by hundreds, would hide them.
    """
    latest = (
        Publication.objects.annotate(last_added=Max("userpublication__added_at"))
        .filter(last_added__isnull=False)
        .order_by("-last_added", "-pk")[:LATEST_COUNT]
    )
    return {
        "publications": Publication.objects.count(),
        "authors": Author.objects.count(),
        "citations": CitedReference.objects.filter(target__isnull=False).count(),
        "latest": list(latest),
    }


def corpus_figures(user):
    """
    The size of the corpus, its latest entries (the publication and its reading status),
    the most recent first, the number of publications in each reading status, and what
    to read next.
    """
    entries = user.userpublication_set.select_related("publication")
    return {
        "count": entries.count(),
        "reading": reading_figures(entries),
        "latest": list(entries.order_by("-added_at", "-pk")[:LATEST_COUNT]),
        "next_to_read": next_to_read(entries),
    }


def next_to_read(entries, size=4):
    """
    What to read next (#278): the publications being read, the latest first, then those
    to read, the oldest first: they have waited longest.
    """
    statuses = UserPublication.ReadingStatus
    reading = entries.filter(reading_status=statuses.READING).order_by("-added_at", "-pk")
    to_read = entries.filter(reading_status=statuses.TO_READ).order_by("added_at", "pk")
    return [*reading[:size], *to_read[:size]][:size]


# The colour of each status in the reading bar of the home page: darker as it advances.
READING_COLORS = {"to_read": "bg-blue-300", "reading": "bg-blue-500", "read": "bg-blue-800"}


def reading_figures(entries):
    """
    Each reading status, with its filter value in my corpus, its count and its colour
    in the reading bar of the home page (#278).
    """
    counts = dict(entries.values_list("reading_status").annotate(Count("pk")).order_by())
    statuses = [*UserPublication.ReadingStatus.choices, ("", "Sans statut")]
    return [
        {
            "filter": status or "none",
            "label": label,
            "count": counts.get(status, 0),
            "color": READING_COLORS.get(status, "bg-gray-300"),
        }
        for status, label in statuses
    ]


def to_do(user):
    """What waits for an action, with the probable duplicates the navigation leaves out."""
    return {
        "to_identify": pending.references_to_identify(user),
        "conflicts": pending.open_conflicts(),
        "duplicates": pending.probable_duplicates(),
    }
