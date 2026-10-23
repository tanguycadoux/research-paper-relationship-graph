"""
The figures of the home page (#151): a constant number of queries, whatever the size
of the base or of the corpus.
"""

from ..models import Author, CitedReference, Publication
from . import author_duplicates, pending

LATEST_COUNT = 5


def base_figures():
    return {
        "publications": Publication.objects.count(),
        "authors": Author.objects.count(),
        "citations": CitedReference.objects.filter(target__isnull=False).count(),
    }


def corpus_figures(user):
    """The size of the corpus and its latest publications, the most recent first."""
    entries = user.userpublication_set
    return {
        "count": entries.count(),
        "latest": [
            entry.publication
            for entry in entries.select_related("publication").order_by("-added_at", "-pk")[
                :LATEST_COUNT
            ]
        ],
    }


def to_do(user):
    """What waits for an action, with the probable duplicates the navigation leaves out."""
    return {
        "to_identify": pending.references_to_identify(user),
        "conflicts": pending.open_conflicts(),
        "duplicates": len(author_duplicates.duplicate_groups()),
    }
