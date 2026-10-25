"""
The figures of the home page (#151): a constant number of queries, whatever the size
of the base or of the corpus.
"""

from django.db.models import Count

from ..models import Author, CitedReference, Publication, UserPublication
from . import author_duplicates, pending

LATEST_COUNT = 5


def base_figures():
    return {
        "publications": Publication.objects.count(),
        "authors": Author.objects.count(),
        "citations": CitedReference.objects.filter(target__isnull=False).count(),
    }


def corpus_figures(user):
    """
    The size of the corpus, its latest publications, the most recent first, and the
    number of publications in each reading status.
    """
    entries = user.userpublication_set
    return {
        "count": entries.count(),
        "reading": reading_figures(entries),
        "latest": [
            entry.publication
            for entry in entries.select_related("publication").order_by("-added_at", "-pk")[
                :LATEST_COUNT
            ]
        ],
    }


def reading_figures(entries):
    """Each reading status, with its filter value in my references and its count."""
    counts = dict(entries.values_list("reading_status").annotate(Count("pk")).order_by())
    statuses = [*UserPublication.ReadingStatus.choices, ("", "Sans statut")]
    return [
        {"filter": status or "none", "label": label, "count": counts.get(status, 0)}
        for status, label in statuses
    ]


def to_do(user):
    """What waits for an action, with the probable duplicates the navigation leaves out."""
    return {
        "to_identify": pending.references_to_identify(user),
        "conflicts": pending.open_conflicts(),
        "duplicates": len(author_duplicates.duplicate_groups()),
    }
